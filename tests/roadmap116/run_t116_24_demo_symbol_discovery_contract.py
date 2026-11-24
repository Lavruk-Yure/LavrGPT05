"""T116-24 TEST_ONLY — офлайн-перевірка cTrader DEMO Symbol Discovery."""

from __future__ import annotations

import ast
import socket
from importlib.util import find_spec
from ipaddress import ip_address
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    new_symbols_request,
)
from tests.roadmap116.t116_24_demo_symbol_discovery import DemoSymbolDiscovery

SOURCE = Path(__file__).with_name("t116_24_demo_symbol_discovery.py")
SYNTHETIC_SYMBOL_ID = 987654


class MemorySender:
    """Приймати повідомлення тільки до пам'яті, без мережі."""

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> None:
        self.sent.append(message)


def synthetic_sdk_messages() -> ModuleType:
    """Мінімальна proto2-схема потрібних auth/symbol повідомлень."""
    schema = getattr(descriptor_pb2, "FileDescriptorProto")()
    schema.name = "t11624_offline.proto"
    schema.package = "t11624"
    schema.syntax = "proto2"
    field_type = getattr(descriptor_pb2, "FieldDescriptorProto")

    def add(name: str, fields: tuple[tuple[str, int, int, bool], ...]) -> None:
        added_message = schema.message_type.add()
        added_message.name = name
        for added_name, added_number, added_kind, added_required in fields:
            added_field = added_message.field.add()
            added_field.name = added_name
            added_field.number = added_number
            added_field.type = added_kind
            if added_required:
                added_field.label = field_type.LABEL_REQUIRED
            else:
                added_field.label = field_type.LABEL_OPTIONAL

    account = ("ctidTraderAccountId", 2, field_type.TYPE_INT64, True)
    add(
        "ProtoOAApplicationAuthReq",
        (
            ("clientId", 2, field_type.TYPE_STRING, True),
            ("clientSecret", 3, field_type.TYPE_STRING, True),
        ),
    )
    add("ProtoOAApplicationAuthRes", ())
    add(
        "ProtoOAAccountAuthReq",
        (
            account,
            ("accessToken", 3, field_type.TYPE_STRING, True),
        ),
    )
    add("ProtoOAAccountAuthRes", (account,))
    add(
        "ProtoOASymbolsListReq",
        (
            account,
            ("includeArchivedSymbols", 3, field_type.TYPE_BOOL, False),
        ),
    )

    light = schema.message_type.add()
    light.name = "ProtoOALightSymbol"
    for field_name, number, kind, required in (
        ("symbolId", 1, field_type.TYPE_INT64, True),
        ("symbolName", 2, field_type.TYPE_STRING, False),
        ("enabled", 3, field_type.TYPE_BOOL, False),
    ):
        element = light.field.add()
        element.name = field_name
        element.number = number
        element.type = kind
        element.label = (
            field_type.LABEL_REQUIRED if required else field_type.LABEL_OPTIONAL
        )

    response = schema.message_type.add()
    response.name = "ProtoOASymbolsListRes"
    account_field = response.field.add()
    account_field.name = account[0]
    account_field.number = account[1]
    account_field.type = account[2]
    account_field.label = field_type.LABEL_REQUIRED
    symbols_field = response.field.add()
    symbols_field.name = "symbol"
    symbols_field.number = 3
    symbols_field.type = field_type.TYPE_MESSAGE
    symbols_field.label = field_type.LABEL_REPEATED
    symbols_field.type_name = ".t11624.ProtoOALightSymbol"
    add("ProtoOANewOrderReq", (account,))

    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    module = ModuleType("t11624_test_only_messages")
    for message_node in schema.message_type:
        message_type = message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11624.{message_node.name}")
        )
        setattr(module, message_node.name, message_type)
    return module


def proto(messages: ModuleType, name: str, **values: Any) -> Message:
    """Створити динамічний protobuf без kwargs конструктора."""
    cls = getattr(messages, name)
    message: Message = cls()
    for field_name, value in values.items():
        setattr(message, field_name, value)
    return message


def symbols_response(
    messages: ModuleType,
    *,
    account_id: int = DEMO_API_ACCOUNT_ID,
    names: tuple[tuple[str, int, bool], ...] = (("EURUSD", SYNTHETIC_SYMBOL_ID, True),),
) -> Message:
    """Використовувати лише синтетичний ID, не реальний symbolId."""
    response = proto(messages, "ProtoOASymbolsListRes", ctidTraderAccountId=account_id)
    for name, symbol_id, enabled in names:
        item = getattr(response, "symbol").add()
        item.symbolId = symbol_id
        item.symbolName = name
        item.enabled = enabled
    assert response.IsInitialized()
    return response


def exercise(messages: ModuleType) -> int:
    """Перевірити однаковий контракт для synthetic та справжнього SDK."""
    sender = MemorySender()
    discovery = DemoSymbolDiscovery(
        account_mode="DEMO",
        account_id=DEMO_API_ACCOUNT_ID,
        messages=messages,
        sender=sender,
    )
    with pytest.raises(RuntimeError):
        discovery.send_symbols_list()
    with pytest.raises(RuntimeError):
        discovery.send_read_only(new_symbols_request(messages))
    with pytest.raises(PermissionError):
        DemoSymbolDiscovery(
            account_mode="LIVE",
            account_id=DEMO_API_ACCOUNT_ID,
            messages=messages,
            sender=sender,
        )
    with pytest.raises(PermissionError):
        DemoSymbolDiscovery(
            account_mode="DEMO",
            account_id=DEMO_API_ACCOUNT_ID + 1,
            messages=messages,
            sender=sender,
        )
    with pytest.raises(PermissionError):
        discovery.send_read_only(
            proto(
                messages,
                "ProtoOANewOrderReq",
                ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            )
        )
    with pytest.raises(PermissionError):
        discovery.reject_raw_packet(b"TEST_ONLY_RAW_PACKET")
    assert not sender.sent

    discovery.send_application_auth(
        client_id="TEST_ONLY_CLIENT_ID", client_secret="TEST_ONLY_SECRET"
    )
    assert sender.sent[-1].DESCRIPTOR.name == "ProtoOAApplicationAuthReq"
    discovery.accept_application_auth(proto(messages, "ProtoOAApplicationAuthRes"))
    discovery.send_account_auth(access_token="TEST_ONLY_ACCESS_TOKEN")
    assert sender.sent[-1].DESCRIPTOR.name == "ProtoOAAccountAuthReq"
    with pytest.raises(PermissionError):
        discovery.accept_account_auth(
            proto(
                messages,
                "ProtoOAAccountAuthRes",
                ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1,
            )
        )
    assert discovery.phase == "ACCOUNT_AUTH_SENT"
    discovery.accept_account_auth(
        proto(
            messages, "ProtoOAAccountAuthRes", ctidTraderAccountId=DEMO_API_ACCOUNT_ID
        )
    )
    with pytest.raises(PermissionError):
        archived_request = new_symbols_request(messages)
        setattr(archived_request, "includeArchivedSymbols", True)
        discovery.send_read_only(archived_request)
    discovery.send_symbols_list()
    request = sender.sent[-1]
    assert request.DESCRIPTOR.name == "ProtoOASymbolsListReq"
    assert int(getattr(request, "ctidTraderAccountId")) == DEMO_API_ACCOUNT_ID
    assert not bool(getattr(request, "includeArchivedSymbols"))
    assert request.IsInitialized()
    assert len(sender.sent) == 3

    with pytest.raises(PermissionError):
        discovery.accept_symbols_list(
            symbols_response(messages, account_id=DEMO_API_ACCOUNT_ID + 1)
        )
    with pytest.raises(ValueError):
        discovery.accept_symbols_list(
            symbols_response(messages, names=(("GBPUSD", 111, True),))
        )
    with pytest.raises(ValueError):
        discovery.accept_symbols_list(
            symbols_response(messages, names=(("EURUSD", SYNTHETIC_SYMBOL_ID, False),))
        )
    with pytest.raises(ValueError):
        discovery.accept_symbols_list(
            symbols_response(
                messages,
                names=(
                    ("EURUSD", SYNTHETIC_SYMBOL_ID, True),
                    ("EUR/USD", SYNTHETIC_SYMBOL_ID + 1, True),
                ),
            )
        )
    assert discovery.phase == "SYMBOLS_REQUESTED"
    assert discovery.symbol_id is None
    result = discovery.accept_symbols_list(symbols_response(messages))
    assert result == SYNTHETIC_SYMBOL_ID
    assert discovery.phase == "RESOLVED"
    with pytest.raises(RuntimeError):
        discovery.send_symbols_list()
    with pytest.raises(RuntimeError):
        discovery.send_read_only(new_symbols_request(messages))
    assert len(sender.sent) == 3
    return result


def test_t116_24_demo_symbol_discovery_contract() -> None:
    """Суворий порядок, DEMO ID і read-only protobuf без TCP."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imports = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    imports.extend(
        item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for item in node.names
    )
    forbidden = ("LGE", "engine", "core", "ibapi", "PySide6", "socket")
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in forbidden
        for name in imports
    )

    external_attempts: list[str] = []
    loopback_attempts = 0
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_loopback(address: object) -> bool:
        """Дозволити тільки числову loopback-адресу для Twisted Waker."""
        if not isinstance(address, tuple) or len(address) < 2:
            return False
        host, port = address[:2]
        if not isinstance(host, str) or not isinstance(port, int):
            return False
        try:
            return ip_address(host).is_loopback
        except ValueError:
            return False

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        nonlocal loopback_attempts
        if is_loopback(address):
            loopback_attempts += 1
            original_connect(sock, address)
            return
        external_attempts.append("connect")
        raise AssertionError("T116-24: зовнішнє TCP-з'єднання заборонене")

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        nonlocal loopback_attempts
        if is_loopback(address):
            loopback_attempts += 1
            return original_connect_ex(sock, address)
        external_attempts.append("connect_ex")
        raise AssertionError("T116-24: зовнішнє TCP-з'єднання заборонене")

    with (
        patch.object(socket.socket, "connect", guarded_connect),
        patch.object(socket.socket, "connect_ex", guarded_connect_ex),
    ):
        # Контроль: жодне з двох TCP API не випускає зовнішній пакет.
        with socket.socket() as probe:
            with pytest.raises(AssertionError, match="зовнішнє TCP"):
                probe.connect(("192.0.2.1", 443))
            with pytest.raises(AssertionError, match="зовнішнє TCP"):
                probe.connect_ex(("192.0.2.1", 443))
        assert external_attempts == ["connect", "connect_ex"]
        external_attempts.clear()

        # Twisted створює службове loopback-з'єднання під час імпорту.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as local_client:
                local_client.connect(listener.getsockname())
                accepted, _ = listener.accept()
                accepted.close()
        assert loopback_attempts == 1

        synthetic_id = exercise(synthetic_sdk_messages())
        sdk_status = "NOT_INSTALLED_IN_LOCAL_RUNNER"
        if find_spec("ctrader_open_api") is not None:
            _, _, _, messages, _ = load_real_sdk_types()
            assert exercise(messages) == synthetic_id
            sdk_status = "VERIFIED_NO_EXTERNAL_NETWORK"

    assert not external_attempts
    print("external_tcp_connect_and_connect_ex=BLOCKED")
    print("local_twisted_loopback=ALLOWED")
    print(f"sdk_import_loopback_connections={loopback_attempts - 1}")
    print("T116-24 TEST_ONLY | DEMO-only symbol discovery")
    print("authorization_order=APPLICATION_ACCOUNT_SYMBOLS")
    print("demo_api_account_id=46368962")
    print("symbols_request_include_archived=FALSE")
    print("eurusd_id_source=SYMBOLS_LIST_RESPONSE_ONLY")
    print("synthetic_symbol_id_used_for_test=YES")
    print("actual_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print("foreign_disabled_missing_ambiguous=BLOCKED")
    print("trading_unknown_raw=BLOCKED")
    print(f"actual_ctrader_sdk={sdk_status}")
    print("sdk_client_real_constructor=NOT_CALLED")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-24=GREEN_OFFLINE_DEMO_SYMBOL_DISCOVERY_CONTRACT")
