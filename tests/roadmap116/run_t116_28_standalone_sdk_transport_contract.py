"""T116-28 TEST_ONLY — штатний SDK callback -> автономний читач, без TCP.

Не викликає конструктор Client, не запускає reactor і не використовує
реальних credentials. Тест перевіряє інтеграцію вхідного конверта SDK,
але не є дозволом запускати мережевий транспорт.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from ipaddress import ip_address
from types import ModuleType
from typing import Any, Callable
from unittest.mock import patch

import pytest
from google.protobuf.message import DecodeError, Message

from tests.roadmap116.run_t116_22_standalone_demo_quote_reader_contract import (
    fake_message_classes,
)
from tests.roadmap116.run_t116_24_demo_symbol_discovery_contract import (
    proto,
    symbols_response,
    synthetic_sdk_messages,
)
from tests.roadmap116.run_t116_25_demo_network_safety_preflight import (
    FakeClock,
    FakeEndpoints,
    FakeProtocol,
    FakeTransport,
)
from tests.roadmap116.t116_22_standalone_demo_reader import (
    DEMO_API_ACCOUNT_ID,
    StandaloneDemoQuoteReader,
)
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    sdk_message_type,
)
from tests.roadmap116.t116_24_demo_symbol_discovery import DemoSymbolDiscovery
from tests.roadmap116.t116_25_demo_network_safety import OfflineDemoSafetySession

SYNTHETIC_EURUSD_ID = 87201


@dataclass(slots=True)
class FakeEnvelope:
    """TEST_ONLY конверт для локального запуску без установленого SDK."""

    payloadType: int
    payload: bytes
    clientMsgId: str = ""

    def initialized(self) -> bool:
        return self.payloadType > 0 and isinstance(self.payload, bytes)


def _missing_received_callback(_client: object, _envelope: object) -> None:
    """Відхилити подію, якщо callback ще не встановлено."""
    raise RuntimeError("T116-28: callback відсутній")


class FakeSdkClient:
    """Надає тільки callback API, без конструктора мережевого Client."""

    def __init__(self) -> None:
        self._messageReceivedCallback: Callable[[object, object], None] = (
            _missing_received_callback
        )
        self._responseDeferreds: dict[str, object] = {}

    def set_message_received_callback(
        self, callback: Callable[[object, object], None]
    ) -> None:
        self._messageReceivedCallback = callback

    def _received(self, envelope: object) -> None:
        self._messageReceivedCallback(self, envelope)


# Сумісні назви SDK призначаються динамічно, без PyCharm PEP8 зауважень.
setattr(FakeEnvelope, "IsInitialized", FakeEnvelope.initialized)
setattr(
    FakeSdkClient,
    "setMessageReceivedCallback",
    FakeSdkClient.set_message_received_callback,
)


class SdkInboundBridge:
    """Приймати лише очікувані відповіді та SpotEvent із SDK-конверта."""

    def __init__(
        self,
        *,
        messages: ModuleType,
        discovery: DemoSymbolDiscovery,
        envelope_type: type,
        spot_type: type[Message],
        payload_ids: dict[str, int],
        clock: list[datetime],
        sender: OfflineDemoSafetySession,
    ) -> None:
        self.messages = messages
        self.discovery = discovery
        self.envelope_type = envelope_type
        self.spot_type = spot_type
        self.clock = clock
        self.sender = sender
        self.reader: StandaloneDemoQuoteReader | None = None
        names = (
            "ProtoOAApplicationAuthRes",
            "ProtoOAAccountAuthRes",
            "ProtoOASymbolsListRes",
            "ProtoOASpotEvent",
        )
        if set(payload_ids) != set(names) or len(set(payload_ids.values())) != 4:
            raise ValueError("T116-28: неоднозначні payloadType")
        self.registry = {
            payload_ids[name]: (
                spot_type
                if name == "ProtoOASpotEvent"
                else sdk_message_type(messages, name)
            )
            for name in names
        }

    def received(self, _client: object, envelope: object) -> None:
        if type(envelope) is not self.envelope_type:
            raise PermissionError("T116-28: нетипізований TCP-конверт")
        initialized = getattr(envelope, "IsInitialized", None)
        if not callable(initialized) or not initialized():
            raise PermissionError("T116-28: неповний конверт")
        payload_type = int(getattr(envelope, "payloadType", 0))
        cls = self.registry.get(payload_type)
        if cls is None:
            raise PermissionError("T116-28: чужий або торговий payloadType")
        payload = cls()
        try:
            payload.ParseFromString(getattr(envelope, "payload"))
        except (DecodeError, TypeError, ValueError) as exc:
            raise PermissionError("T116-28: пошкоджений protobuf") from exc
        if not payload.IsInitialized():
            raise PermissionError("T116-28: неповна відповідь")
        name = payload.DESCRIPTOR.name
        if name == "ProtoOAApplicationAuthRes":
            self.discovery.accept_application_auth(payload)
        elif name == "ProtoOAAccountAuthRes":
            self.discovery.accept_account_auth(payload)
        elif name == "ProtoOASymbolsListRes":
            symbol_id = self.discovery.accept_symbols_list(payload)
            self.reader = StandaloneDemoQuoteReader(
                account_mode="DEMO",
                account_id=DEMO_API_ACCOUNT_ID,
                symbol_id=symbol_id,
                sender=self.sender,
                allowed_types={},
                spot_event_type=self.spot_type,
                now_utc=lambda: self.clock[0],
            )
        elif name == "ProtoOASpotEvent":
            if self.reader is None:
                raise PermissionError("T116-28: SpotEvent до визначення символу")
            self.reader.on_spot_event(payload)


def run_contract(
    messages: ModuleType,
    spot_type: type[Message],
    envelope_type: type,
    client_type: type,
    payload_ids: dict[str, int],
    endpoints: object,
    protocol: type,
) -> None:
    """Обробити відповіді через callback Client без конструювання Client."""
    now = [datetime(2026, 11, 24, 13, 0, tzinfo=UTC)]
    transport = FakeTransport()
    guarded = OfflineDemoSafetySession(
        endpoints=endpoints,
        protocol=protocol,
        requested_host=getattr(endpoints, "PROTOBUF_DEMO_HOST"),
        requested_port=getattr(endpoints, "PROTOBUF_PORT"),
        account_mode="DEMO",
        account_id=DEMO_API_ACCOUNT_ID,
        messages=messages,
        transport=transport,
        monotonic_clock=FakeClock(),
    )
    discovery = DemoSymbolDiscovery(
        account_mode="DEMO",
        account_id=DEMO_API_ACCOUNT_ID,
        messages=messages,
        sender=guarded,
    )
    bridge = SdkInboundBridge(
        messages=messages,
        discovery=discovery,
        envelope_type=envelope_type,
        spot_type=spot_type,
        payload_ids=payload_ids,
        clock=now,
        sender=guarded,
    )
    sdk_client = FakeSdkClient()
    # Виклик штатних методів реального Client — без його __init__().
    set_callback = getattr(client_type, "setMessageReceivedCallback", None)
    receive_callback = getattr(client_type, "_received", None)
    if not callable(set_callback) or not callable(receive_callback):
        raise RuntimeError("T116-28: SDK callback API відсутній")
    set_callback(sdk_client, bridge.received)

    def receive(payload: Message) -> None:
        identifier = payload_ids[payload.DESCRIPTOR.name]
        if envelope_type is FakeEnvelope:
            envelope = FakeEnvelope(identifier, payload.SerializeToString())
        else:
            envelope = envelope_type()
            setattr(envelope, "payloadType", identifier)
            setattr(envelope, "payload", payload.SerializeToString())
        receive_callback(sdk_client, envelope)

    with guarded:
        discovery.send_application_auth(
            client_id="TEST_ONLY_ID", client_secret="TEST_ONLY_SECRET"
        )
        with pytest.raises(RuntimeError, match="послідовність"):
            receive(
                proto(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
                )
            )
        receive(proto(messages, "ProtoOAApplicationAuthRes"))
        discovery.send_account_auth(access_token="TEST_ONLY_TOKEN")
        with pytest.raises(PermissionError):
            receive(
                proto(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1,
                )
            )
        receive(
            proto(
                messages,
                "ProtoOAAccountAuthRes",
                ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            )
        )
        discovery.send_symbols_list()
        receive(
            symbols_response(
                messages,
                names=(("EURUSD", SYNTHETIC_EURUSD_ID, True),),
            )
        )
        assert discovery.symbol_id == SYNTHETIC_EURUSD_ID
        assert bridge.reader is not None

        event = spot_type()
        setattr(event, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID)
        setattr(event, "symbolId", SYNTHETIC_EURUSD_ID)
        setattr(event, "bid", 109375)
        setattr(event, "ask", 109377)
        receive(event)
        now[0] += timedelta(seconds=300)
        next_event = spot_type()
        setattr(next_event, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID)
        setattr(next_event, "symbolId", SYNTHETIC_EURUSD_ID)
        setattr(next_event, "bid", 109377)
        receive(next_event)
        assert len(bridge.reader.records) == 2
        last = bridge.reader.records[-1]
        assert last.zero_spread_origin == "CACHE_MERGE_EQUAL"
        assert last.side_age_seconds == 300

        with pytest.raises(PermissionError):
            bridge.received(sdk_client, b"RAW_TCP_BYTES")
        with pytest.raises(PermissionError):
            bridge.received(sdk_client, FakeEnvelope(999999, b"x"))
        with pytest.raises(PermissionError):
            guarded.send(
                proto(
                    messages,
                    "ProtoOANewOrderReq",
                    ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
                )
            )
        with pytest.raises(PermissionError):
            guarded.send(
                proto(
                    messages,
                    "ProtoOASymbolsListReq",
                    ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
                )
            )
    assert transport.disconnect_calls == 1
    assert [item.DESCRIPTOR.name for item in transport.sent] == [
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
    ]


def test_t116_28_standalone_sdk_transport_contract() -> None:
    """Перевірити SDK callback, protobuf і read-only sender без мережі."""
    # Локально — synthetic SDK; на LAVRUK додатково справжній пакет SDK.
    messages = synthetic_sdk_messages()
    spot_type = fake_message_classes()["ProtoOASpotEvent"]
    fake_types = {
        "ProtoOAApplicationAuthRes": 201,
        "ProtoOAAccountAuthRes": 202,
        "ProtoOASymbolsListRes": 203,
        "ProtoOASpotEvent": 204,
    }
    run_contract(
        messages,
        spot_type,
        FakeEnvelope,
        FakeSdkClient,
        fake_types,
        FakeEndpoints(),
        FakeProtocol,
    )

    sdk_status = "NOT_INSTALLED_LOCAL_RUNNER"
    if find_spec("ctrader_open_api") is not None:
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        attempts: list[str] = []

        def allowed_loopback(address: object) -> bool:
            if not isinstance(address, tuple) or len(address) < 2:
                return False
            host = address[0]
            if not isinstance(host, str):
                return False
            try:
                return ip_address(host).is_loopback
            except ValueError:
                return False

        def guard_connect(sock: socket.socket, address: Any) -> None:
            if not allowed_loopback(address):
                attempts.append("connect")
                raise AssertionError("T116-28: зовнішня мережа заборонена")
            original_connect(sock, address)

        def guard_connect_ex(sock: socket.socket, address: Any) -> int:
            if not allowed_loopback(address):
                attempts.append("connect_ex")
                raise AssertionError("T116-28: зовнішня мережа заборонена")
            return original_connect_ex(sock, address)

        with (
            patch.object(socket.socket, "connect", guard_connect),
            patch.object(socket.socket, "connect_ex", guard_connect_ex),
        ):
            endpoints, client_type, protocol, real_messages, common = (
                load_real_sdk_types()
            )
            envelope_type = getattr(common, "ProtoMessage")
            real_spot = sdk_message_type(real_messages, "ProtoOASpotEvent")
            real_types = {
                name: int(
                    getattr(sdk_message_type(real_messages, name)(), "payloadType")
                )
                for name in fake_types
            }
            run_contract(
                real_messages,
                real_spot,
                envelope_type,
                client_type,
                real_types,
                endpoints,
                protocol,
            )
        assert not attempts
        sdk_status = "VERIFIED_NO_EXTERNAL_NETWORK"

    print("T116-28 TEST_ONLY | SDK callback -> standalone reader")
    print("sdk_client_constructor=NOT_CALLED")
    print("sdk_inbound_callback=EXECUTED")
    print("demo_authorization_and_eurusd=VERIFIED_SYNTHETIC_RESPONSE")
    print("raw_spot_bid_ask=RECEIVED")
    print("stale_side_age_seconds=300")
    print("trading_unknown_raw=BLOCKED_BY_APPLICATION_POLICY")
    print(f"actual_ctrader_sdk={sdk_status}")
    print("sdk_protocol_tcp_send=NOT_EXERCISED")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-28=GREEN_OFFLINE_SDK_CALLBACK_INTEGRATION")
