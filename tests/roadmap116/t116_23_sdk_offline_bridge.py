"""T116-23 TEST_ONLY — інтеграція схеми cTrader SDK без TCP та LGE.

Реальний Client НЕ створюється: у Python SDK конструктор може
ініціювати мережеве з'єднання. Для офлайн-перевірки використовуй лише
підмінений конструктор, а protobuf бери зі схеми SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from types import ModuleType

from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import (
    ALLOWED_REQUEST_NAMES,
    DEMO_API_ACCOUNT_ID,
    StandaloneDemoQuoteReader,
    ReadOnlySender,
)


@dataclass(frozen=True, slots=True)
class DemoClientSpec:
    """Параметри Client; конструктор SDK навмисно не викликається."""

    demo_host: str
    live_host: str
    port: int
    protocol: type


def sdk_client_spec(endpoints: object, protocol: type) -> DemoClientSpec:
    """Взяти DEMO endpoint зі справжніх констант SDK, не з рядка."""
    demo = getattr(endpoints, "PROTOBUF_DEMO_HOST", None)
    live = getattr(endpoints, "PROTOBUF_LIVE_HOST", None)
    port = getattr(endpoints, "PROTOBUF_PORT", None)
    if not isinstance(demo, str) or not demo:
        raise ValueError("T116-23: SDK DEMO host не визначено")
    if not isinstance(live, str) or not live or demo == live:
        raise ValueError("T116-23: DEMO/LIVE endpoint не відокремлено")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
        raise ValueError("T116-23: некоректний порт SDK")
    if not isinstance(protocol, type):
        raise TypeError("T116-23: protocol має бути класом")
    return DemoClientSpec(demo, live, port, protocol)


def sdk_message_type(messages: ModuleType, name: str) -> type[Message]:
    """Перевірити наявність справжнього protobuf-класу за назвою."""
    result = getattr(messages, name, None)
    if not isinstance(result, type) or not issubclass(result, Message):
        raise TypeError(f"T116-23: protobuf-клас {name} відсутній")
    return result


def new_symbols_request(messages: ModuleType) -> Message:
    """Запит символів тільки для дозволеного DEMO API ID."""
    request = sdk_message_type(messages, "ProtoOASymbolsListReq")()
    setattr(request, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID)
    if not request.IsInitialized():
        raise ValueError("T116-23: неповний SymbolsListReq")
    return request


def resolve_eurusd_id(messages: ModuleType, response: Message) -> int:
    """Визначити EURUSD тільки з фактичної SymbolsListRes цього рахунку.

    Не використовувати резервні чи вигадані symbolId, а також archivedSymbol.
    """
    response_type = sdk_message_type(messages, "ProtoOASymbolsListRes")
    if type(response) is not response_type or not response.IsInitialized():
        raise ValueError("T116-23: неправильна або неповна SymbolsListRes")
    if int(getattr(response, "ctidTraderAccountId", 0)) != DEMO_API_ACCOUNT_ID:
        raise PermissionError("T116-23: SymbolsListRes чужого рахунку")
    matches: list[int] = []
    for item in getattr(response, "symbol"):
        symbol_name = str(getattr(item, "symbolName", ""))
        normalized = symbol_name.upper().replace("/", "")
        if normalized != "EURUSD":
            continue
        if "enabled" in item.DESCRIPTOR.fields_by_name and item.HasField("enabled"):
            if not bool(getattr(item, "enabled")):
                continue
        symbol_id = int(getattr(item, "symbolId", 0))
        if symbol_id > 0:
            matches.append(symbol_id)
    if len(matches) != 1:
        raise ValueError("T116-23: EURUSD відсутній або неоднозначний")
    return matches[0]


def new_spot_subscription(messages: ModuleType, symbol_id: int) -> Message:
    """Вимагати timestamp та лише ID, отриманий із SymbolsListRes."""
    if symbol_id <= 0:
        raise ValueError("T116-23: символ не визначено")
    request = sdk_message_type(messages, "ProtoOASubscribeSpotsReq")()
    setattr(request, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID)
    getattr(request, "symbolId").append(symbol_id)
    setattr(request, "subscribeToSpotTimestamp", True)
    if not request.IsInitialized():
        raise ValueError("T116-23: неповний SubscribeSpotsReq")
    return request


def reader_allowlist(messages: ModuleType) -> dict[str, type[Message]]:
    """Білий список лише тих запитів, чиї класи є в SDK."""
    allowed: dict[str, type[Message]] = {}
    for name in ALLOWED_REQUEST_NAMES:
        if name == "ProtoHeartbeatEvent":
            continue
        allowed[name] = sdk_message_type(messages, name)
    return allowed


def load_real_sdk_types() -> tuple[object, type, type, ModuleType, ModuleType]:
    """Тільки імпорт SDK. Справжній Client не створюємо."""
    package = import_module("ctrader_open_api")
    endpoints = import_module("ctrader_open_api.endpoints")
    requests = import_module("ctrader_open_api.messages.OpenApiMessages_pb2")
    common = import_module("ctrader_open_api.messages.OpenApiCommonMessages_pb2")
    client_type = getattr(package, "Client")
    protocol_type = getattr(package, "TcpProtocol")
    if not isinstance(client_type, type) or not isinstance(protocol_type, type):
        raise TypeError("T116-23: SDK Client або TcpProtocol — не клас")
    if not isinstance(requests, ModuleType) or not isinstance(common, ModuleType):
        raise TypeError("T116-23: protobuf-модулі SDK недоступні")
    return getattr(endpoints, "EndPoints"), client_type, protocol_type, requests, common


def make_reader(
    *, symbol_id: int, sender: ReadOnlySender, messages: ModuleType,
    heartbeat_type: type[Message], now_utc: Callable[[], datetime],
) -> StandaloneDemoQuoteReader:
    """Зібрати читач з реальних protobuf-класів та визначеного символу."""
    allowed = reader_allowlist(messages)
    allowed["ProtoHeartbeatEvent"] = heartbeat_type
    return StandaloneDemoQuoteReader(
        account_mode="DEMO", account_id=DEMO_API_ACCOUNT_ID,
        symbol_id=symbol_id, sender=sender,
        allowed_types=allowed,
        spot_event_type=sdk_message_type(messages, "ProtoOASpotEvent"),
        now_utc=now_utc,
    )
