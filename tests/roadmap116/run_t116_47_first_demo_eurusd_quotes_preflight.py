"""T116-47 TEST_ONLY — перевірка DEMO quotes без TCP та справжнього Client."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116.run_t116_25_demo_network_safety_preflight import FakeClock
from tests.roadmap116.run_t116_29_sdk_outbound_transport_guard import (
    FakeClient,
    FakeFrameSender,
    FakeTcpProtocol,
    WireCase,
)
from tests.roadmap116.run_t116_32_demo_network_readonly_discovery_preflight import (
    FakeScheduler,
    FakeSdkClient,
)
from tests.roadmap116.t116_26_process_watchdog import SupervisedResult
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import BridgedCredentials
from tests.roadmap116.t116_47_first_demo_eurusd_quotes_network import (
    APPROVAL_VALUE,
    APPROVAL_VARIABLE,
    CHILD_SUCCESS,
    CLI_CONFIRMATION,
    OFFLINE_SUCCESS,
    ORDERS_CONFIRMATION,
    PARENT_SUCCESS,
    WSP_CONFIRMATION,
    QuoteNetworkController,
    approved,
    exact_quotes_outbound,
    main,
    prepare_child_environment,
    safe_failure_code,
    safe_failure_diagnostics,
    supervise_network_child,
    verified_quote,
)

CREDENTIALS = BridgedCredentials(
    client_id="T11647_CLIENT_ONLY",
    client_secret="T11647_SECRET_ONLY",
    access_token="T11647_TOKEN_ONLY",
)


def synthetic_sdk() -> tuple[ModuleType, ModuleType]:
    """Створити сумісні зі SDK proto2-повідомлення тільки в пам'яті."""
    schema = getattr(descriptor_pb2, "FileDescriptorProto")()
    schema.name = "t11647_quotes.proto"
    schema.package = "t11647"
    schema.syntax = "proto2"
    field_kind = getattr(descriptor_pb2, "FieldDescriptorProto")
    names = (
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
        "ProtoOASubscribeSpotsReq",
        "ProtoOAUnsubscribeSpotsReq",
        "ProtoOANewOrderReq",
        "ProtoOAApplicationAuthRes",
        "ProtoOAAccountAuthRes",
        "ProtoOASubscribeSpotsRes",
        "ProtoOASpotEvent",
        "ProtoHeartbeatEvent",
        "ProtoMessage",
        "ProtoOAErrorRes",
    )

    def add_field(
        proto_node: Any,
        field_name: str,
        number: int,
        field_type: int,
        *,
        required: bool = False,
        repeated: bool = False,
        default: str = "",
    ) -> None:
        item = proto_node.field.add()
        item.name = field_name
        item.number = number
        item.type = field_type
        item.label = (
            field_kind.LABEL_REPEATED
            if repeated
            else field_kind.LABEL_REQUIRED if required else field_kind.LABEL_OPTIONAL
        )
        if default:
            item.default_value = default

    for index, message_name in enumerate(names):
        message_node = schema.message_type.add()
        message_node.name = message_name
        if message_name == "ProtoMessage":
            add_field(
                message_node, "payloadType", 1, field_kind.TYPE_UINT32, required=True
            )
            add_field(message_node, "payload", 2, field_kind.TYPE_BYTES, required=True)
            continue
        add_field(
            message_node,
            "payloadType",
            1,
            field_kind.TYPE_UINT32,
            default=str(3100 + index),
        )
        if message_name not in {
            "ProtoOAApplicationAuthReq",
            "ProtoOAApplicationAuthRes",
            "ProtoHeartbeatEvent",
        }:
            add_field(
                message_node,
                "ctidTraderAccountId",
                2,
                field_kind.TYPE_INT64,
                required=True,
            )
        if message_name == "ProtoOAApplicationAuthReq":
            add_field(
                message_node, "clientId", 2, field_kind.TYPE_STRING, required=True
            )
            add_field(
                message_node, "clientSecret", 3, field_kind.TYPE_STRING, required=True
            )
        if message_name == "ProtoOAAccountAuthReq":
            add_field(
                message_node, "accessToken", 3, field_kind.TYPE_STRING, required=True
            )
        if message_name == "ProtoOASymbolsListReq":
            add_field(message_node, "includeArchivedSymbols", 3, field_kind.TYPE_BOOL)
        if message_name in {
            "ProtoOASubscribeSpotsReq",
            "ProtoOAUnsubscribeSpotsReq",
        }:
            add_field(message_node, "symbolId", 3, field_kind.TYPE_INT64, repeated=True)
            add_field(message_node, "subscribeToSpotTimestamp", 4, field_kind.TYPE_BOOL)
        if message_name == "ProtoOASpotEvent":
            add_field(message_node, "symbolId", 3, field_kind.TYPE_INT64, required=True)
            add_field(message_node, "bid", 4, field_kind.TYPE_UINT64)
            add_field(message_node, "ask", 5, field_kind.TYPE_UINT64)
            add_field(message_node, "timestamp", 6, field_kind.TYPE_INT64)
    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    messages = ModuleType("t11647_requests")
    common = ModuleType("t11647_common")
    for message_name in names:
        klass = message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11647.{message_name}")
        )
        setattr(
            (
                common
                if message_name in {"ProtoMessage", "ProtoHeartbeatEvent"}
                else messages
            ),
            message_name,
            klass,
        )
    return messages, common


def new_message(messages: ModuleType, name: str, **values: Any) -> Message:
    message: Message = getattr(messages, name)()
    for field_name, value in values.items():
        setattr(message, field_name, value)
    return message


def envelope(common: ModuleType, payload: Message) -> Message:
    wrapper: Message = getattr(common, "ProtoMessage")()
    setattr(wrapper, "payloadType", getattr(payload, "payloadType"))
    setattr(wrapper, "payload", payload.SerializeToString())
    return wrapper


def run_session(
    messages: ModuleType,
    common: ModuleType,
) -> tuple[QuoteNetworkController, FakeSdkClient, FakeScheduler, FakeClock]:
    client = FakeSdkClient()
    scheduler = FakeScheduler()
    clock = FakeClock()
    controller = QuoteNetworkController(
        client=client,
        messages=messages,
        common=common,
        clock=clock,
        schedule=scheduler.schedule,
        now=lambda: datetime(2026, 11, 26, 13, 30, tzinfo=UTC),
        on_finished=lambda: None,
        credentials=CREDENTIALS,
    )
    controller.start()
    client.dispatch_connected()
    return controller, client, scheduler, clock


def feed_authorized(
    client: FakeSdkClient,
    messages: ModuleType,
    common: ModuleType,
) -> None:
    client.dispatch_message(
        envelope(
            common,
            new_message(
                messages,
                "ProtoOAApplicationAuthRes",
            ),
        )
    )
    client.dispatch_message(
        envelope(
            common,
            new_message(
                messages,
                "ProtoOAAccountAuthRes",
                ctidTraderAccountId=46368962,
            ),
        )
    )
    client.dispatch_message(
        envelope(
            common,
            new_message(
                messages,
                "ProtoOASubscribeSpotsRes",
                ctidTraderAccountId=46368962,
            ),
        )
    )


def good_quote() -> SupervisedResult:
    lines = (
        "demo_api_account_id=46368962",
        "symbol_id=1",
        "bid=1.09375",
        "ask=1.09377",
        "broker_timestamp_utc=2026-11-26T13:30:00.000Z",
        "quote_kind=FIRST_RECEIVED_SNAPSHOT_NOT_LIVE_PROOF",
        "production_changes=0",
        CHILD_SUCCESS,
    )
    return SupervisedResult(
        returncode=0,
        hard_timeout=False,
        reaped=True,
        stdout="\n".join(lines) + "\n",
        stderr="",
    )


def test_t116_47_first_demo_eurusd_quotes_preflight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Фактичні quotes далі — тільки після окремого офлайн GREEN."""
    denied = 0
    messages, common = synthetic_sdk()
    base = outbound.PERMITTED_REQUEST_NAMES
    with external_tcp_denied():
        controller, client, _scheduler, _clock = run_session(messages, common)
        assert [item.DESCRIPTOR.name for item in client.sent] == [
            "ProtoOAApplicationAuthReq",
        ]
        feed_authorized(client, messages, common)
        assert [item.DESCRIPTOR.name for item in client.sent] == [
            "ProtoOAApplicationAuthReq",
            "ProtoOAAccountAuthReq",
            "ProtoOASubscribeSpotsReq",
        ]
        bid = new_message(
            messages,
            "ProtoOASpotEvent",
            ctidTraderAccountId=46368962,
            symbolId=1,
            bid=109375,
        )
        client.dispatch_message(envelope(common, bid))
        assert controller.quote is None
        ask = new_message(
            messages,
            "ProtoOASpotEvent",
            ctidTraderAccountId=46368962,
            symbolId=1,
            ask=109377,
            timestamp=1795699800000,
        )
        client.dispatch_message(envelope(common, ask))
        assert controller.error_code is None
        assert controller.quote is not None
        assert controller.quote.bid == 1.09375
        assert controller.quote.ask == 1.09377
        assert client.stop_calls == 1

        # Реально спостережений порядок: SpotEvent перед SubscribeSpotsRes.
        early, early_client, _, _ = run_session(messages, common)
        early_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAApplicationAuthRes",
                ),
            )
        )
        early_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        assert early.phase == "SUBSCRIBE_SENT"
        early_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=1,
                    bid=109375,
                ),
            )
        )
        early_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=1,
                    ask=109377,
                ),
            )
        )
        assert early.error_code is None
        assert early.quote is None and early_client.stop_calls == 0
        early_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASubscribeSpotsRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        assert early.quote is not None and early.error_code is None
        assert early.quote.bid == 1.09375 and early.quote.ask == 1.09377
        assert early_client.stop_calls == 1

        # Після раннього Bid і підтвердження підписки Ask завершує знімок.
        partial, partial_client, _, _ = run_session(messages, common)
        partial_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAApplicationAuthRes",
                ),
            )
        )
        partial_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        partial_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=1,
                    bid=109375,
                ),
            )
        )
        partial_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASubscribeSpotsRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        assert partial.quote is None and partial.error_code is None
        partial_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=1,
                    ask=109377,
                ),
            )
        )
        assert partial.quote is not None and partial.error_code is None

        # Ранній SpotEvent не може обійти контроль account і SubscribeRes.
        invalid_early, invalid_client, _, _ = run_session(messages, common)
        invalid_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAApplicationAuthRes",
                ),
            )
        )
        invalid_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        invalid_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=2,
                    bid=109375,
                    ask=109377,
                ),
            )
        )
        assert invalid_early.error_code == "INVALID_RESPONSE"
        assert invalid_early.failure_class == "SPOT_REJECTED"
        denied += 1

        invalid_ack, invalid_ack_client, _, _ = run_session(messages, common)
        invalid_ack_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAApplicationAuthRes",
                ),
            )
        )
        invalid_ack_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        invalid_ack_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=1,
                    bid=109375,
                    ask=109377,
                ),
            )
        )
        assert invalid_ack.quote is None
        invalid_ack_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASubscribeSpotsRes",
                    ctidTraderAccountId=46368963,
                ),
            )
        )
        assert invalid_ack.error_code == "INVALID_RESPONSE"
        assert invalid_ack.quote is None
        denied += 1

        missing_ack, missing_client, missing_scheduler, missing_clock = run_session(
            messages,
            common,
        )
        missing_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAApplicationAuthRes",
                ),
            )
        )
        missing_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        missing_client.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=1,
                    bid=109375,
                    ask=109377,
                ),
            )
        )
        assert missing_ack.quote is None
        missing_clock.seconds += 61
        missing_scheduler.tick()
        assert missing_ack.error_code == "QUOTE_SESSION_TIMEOUT"
        assert missing_ack.quote is None
        denied += 1

        for invalid in (
            new_message(
                messages, "ProtoOAAccountAuthRes", ctidTraderAccountId=46368962
            ),
            new_message(
                messages,
                "ProtoOASpotEvent",
                ctidTraderAccountId=46368962,
                symbolId=1,
                bid=109375,
                ask=109377,
            ),
        ):
            current, fake, _, _ = run_session(messages, common)
            fake.dispatch_message(envelope(common, invalid))
            assert current.error_code == "INVALID_RESPONSE"
            assert fake.stop_calls == 1
            denied += 1

        for wrong in (
            (46368963, 1),
            (46368962, 2),
        ):
            current, fake, _, _ = run_session(messages, common)
            feed_authorized(fake, messages, common)
            fake.dispatch_message(
                envelope(
                    common,
                    new_message(
                        messages,
                        "ProtoOASpotEvent",
                        ctidTraderAccountId=wrong[0],
                        symbolId=wrong[1],
                        bid=109375,
                        ask=109377,
                    ),
                )
            )
            assert current.error_code == "INVALID_RESPONSE"
            denied += 1

        # Безпечні категорії не містять protobuf-даних або секретів.
        current, fake, _, _ = run_session(messages, common)
        fake.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        assert current.error_code == "INVALID_RESPONSE"
        assert current.failure_phase == "APP_SENT"
        assert current.failure_inbound == "ProtoOAAccountAuthRes"
        assert current.failure_class == "UNEXPECTED_RESPONSE_ORDER"
        denied += 1

        current, fake, _, _ = run_session(messages, common)
        fake.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOAErrorRes",
                    ctidTraderAccountId=46368962,
                ),
            )
        )
        assert current.error_code == "INVALID_RESPONSE"
        assert current.failure_phase == "APP_SENT"
        assert current.failure_inbound == "SDK_ERROR_RESPONSE"
        assert current.failure_class == "DECODE_REJECTED"
        denied += 1

        current, fake, _, _ = run_session(messages, common)
        wrong_payload = envelope(
            common,
            new_message(
                messages,
                "ProtoOAApplicationAuthRes",
            ),
        )
        setattr(wrong_payload, "payloadType", 99999)
        fake.dispatch_message(wrong_payload)
        assert current.error_code == "INVALID_RESPONSE"
        assert current.failure_inbound == "UNRECOGNIZED"
        assert current.failure_class == "DECODE_REJECTED"
        denied += 1

        current, fake, _, _ = run_session(messages, common)
        feed_authorized(fake, messages, common)
        fake.dispatch_message(
            envelope(
                common,
                new_message(
                    messages,
                    "ProtoOASpotEvent",
                    ctidTraderAccountId=46368962,
                    symbolId=2,
                    bid=109375,
                    ask=109377,
                ),
            )
        )
        assert current.error_code == "INVALID_RESPONSE"
        assert current.failure_phase == "SUBSCRIBED"
        assert current.failure_class == "SPOT_REJECTED"
        denied += 1

        current, fake, scheduler, clock = run_session(messages, common)
        clock.seconds += 61
        scheduler.tick()
        assert current.error_code == "QUOTE_SESSION_TIMEOUT"
        denied += 1
        current, fake, _, _ = run_session(messages, common)
        fake.dispatch_disconnected("TEST_ONLY")
        assert current.error_code == "DISCONNECTED_BEFORE_QUOTE"
        denied += 1
        current, fake, _, _ = run_session(messages, common)
        fake.pending[0].reject("TEST_ONLY")
        assert current.error_code == "SDK_SEND_FAILED"
        denied += 1

        tcp = FakeTcpProtocol()
        wire = WireCase(messages, common)
        tcp.envelope_class = wire.envelope_class
        fake_client = FakeClient(tcp)
        authorized_account = new_message(
            messages,
            "ProtoOAAccountAuthReq",
            ctidTraderAccountId=46368962,
            accessToken=CREDENTIALS.access_token,
        )
        wrong_token = new_message(
            messages,
            "ProtoOAAccountAuthReq",
            ctidTraderAccountId=46368962,
            accessToken="WRONG",
        )
        symbols = new_message(
            messages,
            "ProtoOASymbolsListReq",
            ctidTraderAccountId=46368962,
        )
        trade = new_message(
            messages,
            "ProtoOANewOrderReq",
            ctidTraderAccountId=46368962,
        )
        subscription = new_message(
            messages,
            "ProtoOASubscribeSpotsReq",
            ctidTraderAccountId=46368962,
            subscribeToSpotTimestamp=True,
        )
        getattr(subscription, "symbolId").append(1)
        with exact_quotes_outbound(
            client_type=FakeClient,
            tcp_protocol_type=FakeTcpProtocol,
            frame_sender_type=FakeFrameSender,
            request_messages=messages,
            common_messages=common,
            access_token=CREDENTIALS.access_token,
        ):
            for authorized in (authorized_account, subscription):
                fake_client.send(authorized)
                tcp.send(authorized, instant=True)
                getattr(FakeFrameSender, "sendString")(tcp, wire.packet(authorized))
            assert len(tcp.transport.writes) == 6
            for invalid in (wrong_token, symbols, trade):
                for operation in (
                    lambda: fake_client.send(invalid),
                    lambda: tcp.send(invalid, instant=True),
                    lambda: getattr(FakeFrameSender, "sendString")(
                        tcp, wire.packet(invalid)
                    ),
                ):
                    with pytest.raises(PermissionError):
                        operation()
                    denied += 1
        assert outbound.PERMITTED_REQUEST_NAMES == base

        env = {
            key: os.environ[key]
            for key in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
            if key in os.environ
        }
        env[APPROVAL_VARIABLE] = APPROVAL_VALUE
        assert not approved(confirmation=None, environment=env)
        denied += 1
        assert not approved(confirmation=CLI_CONFIRMATION, environment={})
        denied += 1
        assert approved(confirmation=CLI_CONFIRMATION, environment=env)
        with pytest.raises(PermissionError):
            prepare_child_environment(
                CREDENTIALS,
                environment=env,
                orders="WRONG",
                wsp=WSP_CONFIRMATION,
            )
        denied += 1
        child_env = prepare_child_environment(
            CREDENTIALS,
            environment=env,
            orders=ORDERS_CONFIRMATION,
            wsp=WSP_CONFIRMATION,
        )
        assert approved(
            confirmation=CLI_CONFIRMATION,
            environment=child_env,
            child=True,
        )
        with patch(
            "tests.roadmap116.t116_47_first_demo_eurusd_quotes_network."
            "run_network_child",
            side_effect=AssertionError("мережа заборонена"),
        ) as network:
            assert (
                main(
                    ["--offline-preflight"],
                    sdk_check=lambda: ("VERIFIED_NO_EXTERNAL_NETWORK"),
                )
                == 0
            )
            assert network.call_count == 0
            with pytest.raises(PermissionError):
                main(["--demo-network", "--confirm", CLI_CONFIRMATION], environment=env)
            denied += 1
        assert OFFLINE_SUCCESS in capsys.readouterr().out

        result = good_quote()

        class FakeProcess:
            """Підставний supervisor child, тільки в пам'яті."""

            def __init__(self) -> None:
                self.killed = False

            def communicate(self, timeout: float) -> tuple[str, str]:
                assert timeout == 75 and not self.killed
                return result.stdout, ""

            def wait(self) -> int:
                return 0 if not self.killed else 124

            def poll(self) -> int:
                return 0 if not self.killed else 124

            def kill(self) -> None:
                self.killed = True

        def fake_popen(argv: list[str], **kwargs: Any) -> FakeProcess:
            assert argv[1:3] == [
                "-m",
                ("tests.roadmap116.t116_47_first_demo_eurusd_quotes_network"),
            ]
            assert kwargs["shell"] is False
            assert kwargs["env"] == child_env
            assert kwargs["stdin"] == subprocess.DEVNULL
            return FakeProcess()

        supervised = supervise_network_child(child_env, popen=fake_popen)
        assert verified_quote(supervised) is not None
        assert verified_quote(result) is not None
        with patch.dict(os.environ, env, clear=False):
            assert (
                main(
                    ["--demo-network", "--confirm", CLI_CONFIRMATION],
                    ask=lambda prompt: (
                        ORDERS_CONFIRMATION if "Orders" in prompt else WSP_CONFIRMATION
                    ),
                    ask_password=lambda _: "TEST_ONLY_PASSWORD",
                    credential_reader=lambda _: CREDENTIALS,
                    runner=lambda _: supervised,
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                )
                == 0
            )
        output = capsys.readouterr().out
        assert PARENT_SUCCESS in output
        assert CREDENTIALS.access_token not in output
        assert CREDENTIALS.client_secret not in output
        for damaged in (
            SupervisedResult(1, False, True, result.stdout, ""),
            SupervisedResult(0, True, True, result.stdout, ""),
            SupervisedResult(0, False, True, result.stdout, "secret"),
            SupervisedResult(0, False, True, result.stdout + "EXTRA\n", ""),
            SupervisedResult(
                0, False, True, result.stdout.replace("symbol_id=1", "symbol_id=2"), ""
            ),
            SupervisedResult(
                0, False, True, result.stdout.replace("ask=1.09377", "ask=1.00000"), ""
            ),
        ):
            assert verified_quote(damaged) is None
            denied += 1
        assert (
            safe_failure_code(
                SupervisedResult(
                    124,
                    True,
                    True,
                    "secret",
                    "secret",
                )
            )
            == "HARD_PROCESS_TIMEOUT"
        )
        denied += 1

        safe_lines = (
            "failure_phase=APP_SENT\n"
            "failure_inbound=SDK_ERROR_RESPONSE\n"
            "failure_class=DECODE_REJECTED\n"
            "failure_code=INVALID_RESPONSE\n"
        )
        rejected = SupervisedResult(1, False, True, safe_lines, "")
        assert safe_failure_diagnostics(rejected) == safe_lines.splitlines()[:3]
        assert safe_failure_code(rejected) == "INVALID_RESPONSE"
        denied += 1

        with patch.dict(os.environ, env, clear=False):
            assert (
                main(
                    ["--demo-network", "--confirm", CLI_CONFIRMATION],
                    ask=lambda question: (
                        ORDERS_CONFIRMATION
                        if "Orders" in question
                        else WSP_CONFIRMATION
                    ),
                    ask_password=lambda _: "TEST_ONLY_PASSWORD",
                    credential_reader=lambda _: CREDENTIALS,
                    runner=lambda _: rejected,
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                )
                == 1
            )
        rendered = capsys.readouterr().out
        assert all(line in rendered for line in safe_lines.splitlines())
        assert CREDENTIALS.access_token not in rendered
        assert CREDENTIALS.client_secret not in rendered
        denied += 1

        for dangerous in (
            safe_lines + "TOKEN=TOP_SECRET\n",
            safe_lines.replace("SDK_ERROR_RESPONSE", "TOP_SECRET"),
            safe_lines.replace("APP_SENT", "APP_SENT;TOP_SECRET"),
        ):
            assert (
                safe_failure_diagnostics(
                    SupervisedResult(1, False, True, dangerous, "")
                )
                == []
            )
            denied += 1
    print("T116-47 TEST_ONLY | first DEMO EURUSD quotes network OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("request_order=APPLICATION_ACCOUNT_SUBSCRIBE_SPOT")
    print("quote_snapshot=VERIFIED_SYNTHETIC_PARTIAL_BID_ASK")
    print("early_spot_before_ack=BUFFERED_ACK_REQUIRED")
    print("strict_outbound=APPLICATION_ACCOUNT_SUBSCRIBE_HEARTBEAT_ONLY")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(OFFLINE_SUCCESS)
