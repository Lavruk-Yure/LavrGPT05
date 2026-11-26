"""T116-46 TEST_ONLY — EURUSD SpotEvent + scoped guard, тільки офлайн."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116.run_t116_29_sdk_outbound_transport_guard import (
    FakeClient,
    FakeFrameSender,
    FakeTcpProtocol,
    WireCase,
)
from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    make_reader,
    new_spot_subscription,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_46_demo_eurusd_quotes_offline import (
    BASELINE_NAMES,
    EXTENDED_REQUEST_NAMES,
    OBSERVED_EURUSD_SYMBOL_ID,
    SUBSCRIBE_NAME,
    SUCCESS,
    guarded_scoped_quote_subscription,
    sdk_schema_preflight,
    validate_spot_subscription,
)


def synthetic_protobuf() -> tuple[ModuleType, ModuleType]:
    """Побудувати справжні protobuf-типи в пам'яті без cTrader SDK."""
    schema = getattr(descriptor_pb2, "FileDescriptorProto")()
    schema.name = "t11646_quotes.proto"
    schema.package = "t11646"
    schema.syntax = "proto2"
    kind = getattr(descriptor_pb2, "FieldDescriptorProto")

    def field(
        field_node: Any,
        field_name: str,
        number: int,
        field_type: int,
        *,
        repeated: bool = False,
        required: bool = False,
        default: str = "",
    ) -> None:
        item = field_node.field.add()
        item.name = field_name
        item.number = number
        item.type = field_type
        item.label = (
            kind.LABEL_REPEATED
            if repeated
            else kind.LABEL_REQUIRED if required else kind.LABEL_OPTIONAL
        )
        if default:
            item.default_value = default

    names = (
        *EXTENDED_REQUEST_NAMES,
        "ProtoOAUnsubscribeSpotsReq",
        "ProtoOANewOrderReq",
        "ProtoOASpotEvent",
        "ProtoOASubscribeSpotsRes",
        "ProtoMessage",
    )
    for index, name in enumerate(names):
        node = schema.message_type.add()
        node.name = name
        if name == "ProtoMessage":
            field(node, "payloadType", 1, kind.TYPE_UINT32, required=True)
            field(node, "payload", 2, kind.TYPE_BYTES, required=True)
            continue
        field(node, "payloadType", 1, kind.TYPE_UINT32, default=str(2200 + index))
        if name not in {"ProtoOAApplicationAuthReq", "ProtoHeartbeatEvent"}:
            field(node, "ctidTraderAccountId", 2, kind.TYPE_INT64, required=True)
        if name in {SUBSCRIBE_NAME, "ProtoOAUnsubscribeSpotsReq"}:
            field(node, "symbolId", 3, kind.TYPE_INT64, repeated=True)
            field(node, "subscribeToSpotTimestamp", 4, kind.TYPE_BOOL)
        if name == "ProtoOASpotEvent":
            field(node, "symbolId", 3, kind.TYPE_INT64, required=True)
            field(node, "bid", 4, kind.TYPE_UINT64)
            field(node, "ask", 5, kind.TYPE_UINT64)
            field(node, "timestamp", 6, kind.TYPE_INT64)
    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    requests = ModuleType("t11646_requests")
    common = ModuleType("t11646_common")
    for name in names:
        message_type = message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11646.{name}")
        )
        setattr(
            common if name in {"ProtoMessage", "ProtoHeartbeatEvent"} else requests,
            name,
            message_type,
        )
    return requests, common


def make_message(requests: ModuleType, name: str, **fields: int) -> Message:
    """Зібрати один синтетичний protobuf із простими полями."""
    message = getattr(requests, name)()
    for name_field, value in fields.items():
        setattr(message, name_field, value)
    return message


class DummySender:
    """Транспорт лише для читача: жодних мережевих звернень."""

    def send(self, _message: Message) -> None:
        pass


def denied_actions(
    message: Message,
    client: FakeClient,
    tcp: FakeTcpProtocol,
    samples: WireCase,
) -> tuple[Callable[[], None], ...]:
    """Повернути три незалежні outbound шляхи для одного protobuf."""
    return (
        lambda: client.send(message),
        lambda: tcp.send(message, instant=True),
        lambda: getattr(FakeFrameSender, "sendString")(tcp, samples.packet(message)),
    )


def test_t116_46_demo_eurusd_quotes_preflight() -> None:
    """Підтвердити контракт котирувань і заборону TCP без запуску Client."""
    denied = 0
    requests, common = synthetic_protobuf()
    samples = WireCase(requests, common)
    tcp = FakeTcpProtocol()
    tcp.envelope_class = samples.envelope_class
    client = FakeClient(tcp)
    request = new_spot_subscription(requests, OBSERVED_EURUSD_SYMBOL_ID)
    request_type = getattr(requests, SUBSCRIBE_NAME)
    validate_spot_subscription(request, request_type)

    bad_requests: list[Message] = []
    for account_id, symbols, timestamp in (
        (DEMO_API_ACCOUNT_ID + 1, [1], True),
        (DEMO_API_ACCOUNT_ID, [], True),
        (DEMO_API_ACCOUNT_ID, [2], True),
        (DEMO_API_ACCOUNT_ID, [1, 2], True),
        (DEMO_API_ACCOUNT_ID, [1, 1], True),
        (DEMO_API_ACCOUNT_ID, [1], False),
    ):
        candidate = request_type()
        candidate.ctidTraderAccountId = account_id
        candidate.symbolId.extend(symbols)
        candidate.subscribeToSpotTimestamp = timestamp
        bad_requests.append(candidate)
    missing_timestamp = request_type()
    missing_timestamp.ctidTraderAccountId = DEMO_API_ACCOUNT_ID
    missing_timestamp.symbolId.append(1)
    bad_requests.append(missing_timestamp)
    with external_tcp_denied():
        for candidate in bad_requests:
            with pytest.raises(PermissionError):
                validate_spot_subscription(candidate, request_type)
            denied += 1

        assert outbound.PERMITTED_REQUEST_NAMES == BASELINE_NAMES
        baseline_unscoped = outbound.UNSCOPED_REQUEST_NAMES
        baseline_send = getattr(FakeClient, "send")
        with outbound.guarded_sdk_outbound(
            client_type=FakeClient,
            tcp_protocol_type=FakeTcpProtocol,
            frame_sender_type=FakeFrameSender,
            request_messages=requests,
            common_messages=common,
        ):
            with pytest.raises(PermissionError):
                client.send(request)
            denied += 1

        with guarded_scoped_quote_subscription(
            client_type=FakeClient,
            tcp_protocol_type=FakeTcpProtocol,
            frame_sender_type=FakeFrameSender,
            request_messages=requests,
            common_messages=common,
        ):
            client.send(request)
            tcp.send(request, instant=True)
            getattr(FakeFrameSender, "sendString")(tcp, samples.packet(request))
            assert len(tcp.transport.writes) == 3
            for candidate in bad_requests:
                for invocation in denied_actions(candidate, client, tcp, samples):
                    with pytest.raises(PermissionError):
                        invocation()
                    denied += 1
            for name in ("ProtoOANewOrderReq", "ProtoOAUnsubscribeSpotsReq"):
                forbidden = samples.new(name, ctidTraderAccountId=DEMO_API_ACCOUNT_ID)
                for invocation in denied_actions(forbidden, client, tcp, samples):
                    with pytest.raises(PermissionError):
                        invocation()
                    denied += 1
            with pytest.raises(PermissionError):
                getattr(FakeFrameSender, "sendString")(tcp, b"broken")
            denied += 1
            assert len(tcp.transport.writes) == 3
        assert outbound.PERMITTED_REQUEST_NAMES == BASELINE_NAMES
        assert outbound.UNSCOPED_REQUEST_NAMES == baseline_unscoped
        assert getattr(FakeClient, "send") is baseline_send

        # SpotEvent є вхідною подією, не вихідним дозволеним запитом.
        current = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
        reader = make_reader(
            symbol_id=OBSERVED_EURUSD_SYMBOL_ID,
            sender=DummySender(),
            messages=requests,
            heartbeat_type=getattr(common, "ProtoHeartbeatEvent"),
            now_utc=lambda: current,
        )
        spot = make_message(
            requests,
            "ProtoOASpotEvent",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            symbolId=1,
            bid=109375,
            ask=109377,
            timestamp=int(current.timestamp() * 1000),
        )
        first = reader.on_spot_event(spot)
        assert first is not None
        assert first.bid == 1.09375 and first.ask == 1.09377
        assert first.raw_bid_present and first.raw_ask_present
        assert first.side_age_seconds == 0
        assert first.broker_event_utc == current
        assert first.zero_spread_origin == "NOT_ZERO"
        current += timedelta(seconds=10)
        bid_only = make_message(
            requests,
            "ProtoOASpotEvent",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            symbolId=1,
            bid=109377,
        )
        merged = reader.on_spot_event(bid_only)
        assert merged is not None
        assert merged.raw_bid_present and not merged.raw_ask_present
        assert merged.side_age_seconds == 10
        assert merged.zero_spread_origin == "CACHE_MERGE_EQUAL"
        assert merged.broker_event_utc is None
        for account_id, symbol_id in (
            (DEMO_API_ACCOUNT_ID + 1, 1),
            (DEMO_API_ACCOUNT_ID, 2),
        ):
            foreign = make_message(
                requests,
                "ProtoOASpotEvent",
                ctidTraderAccountId=account_id,
                symbolId=symbol_id,
                bid=109376,
            )
            assert reader.on_spot_event(foreign) is None
            denied += 1
        assert len(reader.records) == 2
        with pytest.raises(PermissionError):
            reader.send_read_only(spot)
        denied += 1

    assert sdk_schema_preflight() in {
        "NOT_INSTALLED_LOCAL_RUNNER",
        "VERIFIED_NO_EXTERNAL_NETWORK",
    }
    assert denied == 39, denied
    print("T116-46 TEST_ONLY | DEMO EURUSD SpotEvent OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("observed_eurusd_symbol_id=1_FROM_T116_44")
    print("spot_bid_ask_partial_updates=VERIFIED_SYNTHETIC")
    print("spot_timestamp_optional=VERIFIED_SYNTHETIC")
    print("trade_requests=DENIED")
    print("outbound_guard=SCOPED_SUBSCRIBE_EXACT_ID_THREE_LEVELS")
    print("baseline_t116_29=RESTORED")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(SUCCESS)
