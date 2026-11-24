"""T116-23 TEST_ONLY — автономний cTrader SDK без створення TCP Client."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    make_reader,
    new_spot_subscription,
    new_symbols_request,
    resolve_eurusd_id,
    sdk_client_spec,
    sdk_message_type,
)

BRIDGE_FILE = Path(__file__).with_name("t116_23_sdk_offline_bridge.py")
SYNTHETIC_ID = 923451


class FakeEndpoints:
    """Тестові endpoints не призводять до мережевих підключень."""

    PROTOBUF_DEMO_HOST = "demo.test.invalid"
    PROTOBUF_LIVE_HOST = "live.test.invalid"
    PROTOBUF_PORT = 5035


class FakeProtocol:
    """Маркер типу протоколу для контролю фабрики."""


class FakeClient:
    """Тестовий конструктор, який тільки зберігає параметри."""

    def __init__(self, host: str, port: int, protocol: type) -> None:
        self.host = host
        self.port = port
        self.protocol = protocol
        self.network_calls = 0


class FakeSender:
    """Зберігає дозволені protobuf тільки в оперативній пам'яті."""

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> None:
        self.sent.append(message)


def synthetic_sdk() -> tuple[ModuleType, ModuleType]:
    """Створити proto2-схему, сумісну за полями з необхідним API SDK."""
    file_proto = getattr(descriptor_pb2, "FileDescriptorProto")()
    file_proto.name = "t11623_sdk_contract.proto"
    file_proto.package = "t11623"
    file_proto.syntax = "proto2"
    descriptor_type = getattr(descriptor_pb2, "FieldDescriptorProto")

    def field(
        field_owner: object,
        field_name: str,
        number: int,
        kind: int,
        *,
        required: bool = False,
        repeated: bool = False,
        type_name: str = "",
    ) -> None:
        item = getattr(field_owner, "field").add()
        item.name = field_name
        item.number = number
        item.type = kind
        item.label = (
            descriptor_type.LABEL_REPEATED
            if repeated
            else (
                descriptor_type.LABEL_REQUIRED
                if required
                else descriptor_type.LABEL_OPTIONAL
            )
        )
        if type_name:
            item.type_name = type_name

    def add_message(message_name: str) -> object:
        message_node = file_proto.message_type.add()
        message_node.name = message_name
        return message_node

    light = add_message("ProtoOALightSymbol")
    field(light, "symbolId", 1, descriptor_type.TYPE_INT64, required=True)
    field(light, "symbolName", 2, descriptor_type.TYPE_STRING)
    field(light, "enabled", 3, descriptor_type.TYPE_BOOL)

    request_names = (
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
        "ProtoOASubscribeSpotsReq",
        "ProtoOAUnsubscribeSpotsReq",
        "ProtoOANewOrderReq",
    )
    for name in request_names:
        node = add_message(name)
        field(
            node,
            "ctidTraderAccountId",
            1,
            descriptor_type.TYPE_INT64,
            required=name != "ProtoOAApplicationAuthReq",
        )
        if name in {"ProtoOASubscribeSpotsReq", "ProtoOAUnsubscribeSpotsReq"}:
            field(node, "symbolId", 2, descriptor_type.TYPE_INT64, repeated=True)
            field(node, "subscribeToSpotTimestamp", 3, descriptor_type.TYPE_BOOL)

    response = add_message("ProtoOASymbolsListRes")
    field(response, "ctidTraderAccountId", 1, descriptor_type.TYPE_INT64, required=True)
    field(
        response,
        "symbol",
        2,
        descriptor_type.TYPE_MESSAGE,
        repeated=True,
        type_name=".t11623.ProtoOALightSymbol",
    )
    spot = add_message("ProtoOASpotEvent")
    field(spot, "ctidTraderAccountId", 1, descriptor_type.TYPE_INT64, required=True)
    field(spot, "symbolId", 2, descriptor_type.TYPE_INT64, required=True)
    field(spot, "bid", 3, descriptor_type.TYPE_UINT64)
    field(spot, "ask", 4, descriptor_type.TYPE_UINT64)
    field(spot, "timestamp", 5, descriptor_type.TYPE_INT64)
    add_message("ProtoHeartbeatEvent")

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)
    messages = ModuleType("t11623_fake_messages")
    common = ModuleType("t11623_fake_common")
    for name in (
        *request_names,
        "ProtoOASymbolsListRes",
        "ProtoOALightSymbol",
        "ProtoOASpotEvent",
        "ProtoHeartbeatEvent",
    ):
        cls = message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11623.{name}")
        )
        setattr(common if name == "ProtoHeartbeatEvent" else messages, name, cls)
    return messages, common


def new_message(messages: ModuleType, name: str, **values: int) -> Message:
    """Встановити поля без constructor kwargs динамічних protobuf."""
    message = sdk_message_type(messages, name)()
    for key, value in values.items():
        setattr(message, key, value)
    return message


def fake_symbols_response(
    messages: ModuleType,
    *,
    account_id: int = DEMO_API_ACCOUNT_ID,
    symbols: tuple[tuple[str, int, bool], ...] = (("EUR/USD", SYNTHETIC_ID, True),),
) -> Message:
    """Синтетична відповідь SymbolsListRes, не твердження про ID брокера."""
    response = new_message(
        messages, "ProtoOASymbolsListRes", ctidTraderAccountId=account_id
    )
    for name, symbol_id, enabled in symbols:
        symbol = getattr(response, "symbol").add()
        symbol.symbolId = symbol_id
        symbol.symbolName = name
        symbol.enabled = enabled
    assert response.IsInitialized()
    return response


def exercise_messages(
    messages: ModuleType,
    common: ModuleType,
    *,
    real_sdk: bool,
) -> None:
    """Провести контракт на синтетичних або справжніх protobuf-класах."""
    symbols_request = new_symbols_request(messages)
    assert symbols_request.IsInitialized()
    assert int(getattr(symbols_request, "ctidTraderAccountId")) == DEMO_API_ACCOUNT_ID

    with pytest.raises(PermissionError):
        resolve_eurusd_id(
            messages,
            fake_symbols_response(messages, account_id=DEMO_API_ACCOUNT_ID + 1),
        )
    with pytest.raises(ValueError):
        resolve_eurusd_id(
            messages,
            fake_symbols_response(messages, symbols=(("GBPUSD", SYNTHETIC_ID, True),)),
        )
    with pytest.raises(ValueError):
        resolve_eurusd_id(
            messages,
            fake_symbols_response(messages, symbols=(("EURUSD", SYNTHETIC_ID, False),)),
        )
    with pytest.raises(ValueError):
        resolve_eurusd_id(
            messages,
            fake_symbols_response(
                messages,
                symbols=(
                    ("EURUSD", SYNTHETIC_ID, True),
                    ("EUR/USD", SYNTHETIC_ID + 1, True),
                ),
            ),
        )

    response = fake_symbols_response(messages)
    symbol_id = resolve_eurusd_id(messages, response)
    assert symbol_id == SYNTHETIC_ID
    spot_request = new_spot_subscription(messages, symbol_id)
    assert spot_request.IsInitialized()
    assert list(getattr(spot_request, "symbolId")) == [symbol_id]
    assert bool(getattr(spot_request, "subscribeToSpotTimestamp"))
    sender = FakeSender()
    reader = make_reader(
        symbol_id=symbol_id,
        sender=sender,
        messages=messages,
        heartbeat_type=sdk_message_type(common, "ProtoHeartbeatEvent"),
        now_utc=lambda: datetime(2026, 11, 24, 12, 0, tzinfo=UTC),
    )
    reader.send_read_only(symbols_request)
    reader.send_read_only(spot_request)
    assert len(sender.sent) == 2

    order = new_message(
        messages, "ProtoOANewOrderReq", ctidTraderAccountId=DEMO_API_ACCOUNT_ID
    )
    with pytest.raises(PermissionError):
        reader.send_read_only(order)
    with pytest.raises(PermissionError):
        reader.reject_raw_packet(b"TEST_ONLY_FORBIDDEN")
    assert len(sender.sent) == 2

    spot = new_message(
        messages,
        "ProtoOASpotEvent",
        ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        symbolId=symbol_id,
        bid=109375,
        ask=109377,
        timestamp=1795521600000,
    )
    observed = reader.on_spot_event(spot)
    assert observed is not None
    assert observed.raw_bid_present and observed.raw_ask_present
    assert observed.bid == 1.09375 and observed.ask == 1.09377
    assert (
        reader.on_spot_event(
            new_message(
                messages,
                "ProtoOASpotEvent",
                ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
                symbolId=symbol_id + 1,
                bid=109375,
                ask=109377,
            )
        )
        is None
    )
    if real_sdk:
        print("actual_sdk_messages_and_spot_event=VERIFIED_NO_NETWORK")


def test_t116_23_standalone_ctrader_sdk_integration() -> None:
    """Звірити standalone reader із SDK без справжнього Client() та TCP."""
    code = ast.parse(BRIDGE_FILE.read_text(encoding="utf-8"))
    imports = [
        node.module or "" for node in ast.walk(code) if isinstance(node, ast.ImportFrom)
    ]
    imports.extend(
        alias.name
        for node in ast.walk(code)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden = ("LGE", "engine", "core", "ibapi", "PySide6")
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in forbidden
        for name in imports
    )

    synthetic_messages, synthetic_common = synthetic_sdk()
    exercise_messages(synthetic_messages, synthetic_common, real_sdk=False)

    offline_spec = sdk_client_spec(FakeEndpoints, FakeProtocol)
    fake_client = FakeClient(
        offline_spec.demo_host, offline_spec.port, offline_spec.protocol
    )
    assert isinstance(fake_client, FakeClient)
    assert fake_client.host == FakeEndpoints.PROTOBUF_DEMO_HOST
    assert fake_client.port == FakeEndpoints.PROTOBUF_PORT
    assert fake_client.protocol is FakeProtocol
    assert fake_client.network_calls == 0

    sdk_status = "NOT_INSTALLED_IN_LOCAL_RUNNER"
    if find_spec("ctrader_open_api") is not None:
        sdk_endpoints, sdk_client_type, protocol, messages, common = (
            load_real_sdk_types()
        )
        # Не конструювати SDK Client: його __init__ може відкривати сокет.
        assert isinstance(sdk_client_type, type)
        spec = sdk_client_spec(sdk_endpoints, protocol)
        actual_client = FakeClient(spec.demo_host, spec.port, spec.protocol)
        assert isinstance(actual_client, FakeClient)
        assert actual_client.host == spec.demo_host
        assert actual_client.host != spec.live_host
        assert actual_client.protocol is protocol
        assert actual_client.network_calls == 0
        exercise_messages(messages, common, real_sdk=True)
        sdk_status = "VERIFIED_NO_NETWORK"

    print("T116-23 TEST_ONLY | standalone cTrader SDK schema integration")
    print("reader_imports_lge_runtime_ib=NO")
    print("sdk_client_real_constructor=NOT_CALLED_NO_NETWORK")
    print("sdk_demo_endpoint_factory=VERIFIED_FAKE_CLIENT")
    print("symbol_id_source=SYMBOLS_LIST_RESPONSE_ONLY")
    print("actual_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print("account_mismatch_disabled_ambiguous_symbol=BLOCKED")
    print("subscribe_timestamp=True")
    print("trading_and_raw_transport=BLOCKED")
    print(f"actual_ctrader_sdk={sdk_status}")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-23=GREEN_OFFLINE_STANDALONE_SDK_INTEGRATION")
