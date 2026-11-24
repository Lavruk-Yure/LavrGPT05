"""T116-19 TEST_ONLY — сирі сторони cTrader SpotEvent без production-змін.

Звичайний запуск/pytest: тільки синтетичні події, мережа вимкнена.
Режим --live: тимчасово перехоплює callback у поточному процесі LGE,
записує обмежений JSONL і блокує торгові методи cTrader Adapter.
"""

from __future__ import annotations

import ast
import builtins
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_FILE = ROOT / "engine" / "ctrader_adapter.py"
MAX_LIVE_EVENTS = 3000
MAX_LIVE_JSONL_BYTES = 2 * 1024 * 1024
LIVE_QT_TIMEOUT_SECONDS = 60
LIVE_PROCESS_TIMEOUT_SECONDS = 75
LIVE_WORKER_ENV = "T116_20D_SUPERVISED_WORKER"


def scalar_float(value: object) -> float | None:
    """Перетворити числовий scalar protobuf без небезпечного приведення object."""
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def broker_time(value: object) -> str | None:
    """Нормалізувати timestamp події брокера в UTC без вигаданого часу."""
    raw = scalar_float(value)
    if raw is None or raw <= 0:
        return None
    seconds = raw / 1000 if raw > 10_000_000_000 else raw
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def utc_dt(value: str | None) -> datetime | None:
    """Розібрати справжній UTC-час, коли він наявний."""
    return datetime.fromisoformat(value) if value else None


class RawSpotRecorder:
    """Зберігати окрему часову вісь Bid/Ask та raw-presence кожної події."""

    def __init__(
        self,
        *,
        path: Path | None = None,
        max_events: int = MAX_LIVE_EVENTS,
        max_file_bytes: int = MAX_LIVE_JSONL_BYTES,
    ):
        if max_file_bytes <= 0:
            raise ValueError("TEST_ONLY: max_file_bytes повинен бути додатним")
        self.path = path
        self.max_events = max_events
        self.max_file_bytes = max_file_bytes
        self.records: list[dict[str, object]] = []
        self.seen = 0
        self.file_errors = 0
        self.byte_limit_reached = False
        self.byte_limit_hits = 0
        self._last_sides: dict[int, dict[str, str | None]] = {}
        self._lock = threading.Lock()

    def observe(
        self,
        *,
        symbol_id: int,
        symbol: str,
        event_timestamp: object,
        received_at: datetime,
        raw_bid: object,
        raw_ask: object,
        cached_bid: object,
        cached_ask: object,
    ) -> None:
        """Записати факт із payload і кешу, не впливаючи на callback."""
        now = received_at.astimezone(UTC).isoformat()
        event_utc = broker_time(event_timestamp)
        raw_bid_number = scalar_float(raw_bid)
        raw_ask_number = scalar_float(raw_ask)
        valid_bid = raw_bid_number is not None and raw_bid_number > 0
        valid_ask = raw_ask_number is not None and raw_ask_number > 0
        bid = scalar_float(cached_bid)
        ask = scalar_float(cached_ask)

        with self._lock:
            self.seen += 1
            if len(self.records) >= self.max_events or self.byte_limit_reached:
                return
            sides = self._last_sides.setdefault(symbol_id, {
                "bid_received": None,
                "ask_received": None,
                "bid_broker": None,
                "ask_broker": None,
            })
            if valid_bid:
                sides["bid_received"] = now
                sides["bid_broker"] = event_utc
            if valid_ask:
                sides["ask_received"] = now
                sides["ask_broker"] = event_utc
            bid_time = utc_dt(sides["bid_received"])
            ask_time = utc_dt(sides["ask_received"])
            broker_bid_time = utc_dt(sides["bid_broker"])
            broker_ask_time = utc_dt(sides["ask_broker"])
            received_gap = (
                abs((bid_time - ask_time).total_seconds())
                if bid_time is not None and ask_time is not None
                else None
            )
            broker_gap = (
                abs((broker_bid_time - broker_ask_time).total_seconds())
                if broker_bid_time is not None and broker_ask_time is not None
                else None
            )
            equal = bid is not None and ask is not None and bid == ask
            zero_origin = (
                "RAW_BOTH_EQUAL" if valid_bid and valid_ask
                else "CACHE_MERGE_EQUAL" if valid_bid or valid_ask
                else "NO_VALID_RAW_SIDE"
            ) if equal else "NOT_ZERO"
            row: dict[str, object] = {
                "event": "T116_19_RAW_SPOT",
                "received_utc": now,
                "broker_event_utc": event_utc,
                "symbol": symbol,
                "raw_bid_present": raw_bid is not None,
                "raw_ask_present": raw_ask is not None,
                "raw_bid": (
                    raw_bid_number / 100000
                    if raw_bid_number is not None and raw_bid_number > 0 else None
                ),
                "raw_ask": (
                    raw_ask_number / 100000
                    if raw_ask_number is not None and raw_ask_number > 0 else None
                ),
                "merged_bid": bid,
                "merged_ask": ask,
                "merged_spread": (
                    ask - bid if bid is not None and ask is not None else None
                ),
                "bid_last_received_utc": sides["bid_received"],
                "ask_last_received_utc": sides["ask_received"],
                "bid_last_broker_utc": sides["bid_broker"],
                "ask_last_broker_utc": sides["ask_broker"],
                "side_receive_gap_seconds": received_gap,
                "side_broker_gap_seconds": broker_gap,
                "zero_spread_origin": zero_origin,
            }
            if self.path is not None:
                # Рахувати саме байти UTF-8 без автоматичної заміни кінців рядків.
                encoded = (
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                ).encode("utf-8")
                if len(encoded) > self.max_file_bytes:
                    self.byte_limit_reached = True
                    self.byte_limit_hits += 1
                    return
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("ab") as output:
                        if output.tell() + len(encoded) > self.max_file_bytes:
                            self.byte_limit_reached = True
                            self.byte_limit_hits += 1
                            return
                        output.write(encoded)
                except OSError:
                    self.file_errors += 1
                    return
            self.records.append(row)


def instrument_spot_callback(
    original: Callable[..., object], recorder: RawSpotRecorder,
    *, symbol_name: Callable[[int], str],
) -> Callable[..., object]:
    """Обгорнути production callback, зберігши його результат і винятки."""

    def traced_callback(session: object, payload: object) -> object:
        account = int(getattr(payload, "ctidTraderAccountId", 0) or 0)
        config = getattr(session, "config", None)
        expected = int(getattr(config, "ctid_trader_account_id", 0) or 0)
        symbol_id = int(getattr(payload, "symbolId", 0) or 0)
        eligible = account == expected and account > 0 and symbol_id > 0
        raw_bid = None
        raw_ask = None
        event_time = None
        if eligible:
            reader = getattr(session, "_optional_proto_scalar")
            raw_bid = reader(payload, "bid")
            raw_ask = reader(payload, "ask")
            event_time = reader(payload, "timestamp")

        # Торгова й ринкова production-логіка виконується незміненою.
        result = original(session, payload)
        if not eligible:
            return result
        try:
            symbol = symbol_name(symbol_id)
            if symbol.upper() != "EURUSD":
                return result
            cache = getattr(session, "_spot_prices", {})
            quote = dict(cache.get(symbol_id) or {})
            recorder.observe(
                symbol_id=symbol_id,
                symbol=symbol,
                event_timestamp=event_time,
                received_at=datetime.now(UTC),
                raw_bid=raw_bid,
                raw_ask=raw_ask,
                cached_bid=quote.get("bid"),
                cached_ask=quote.get("ask"),
            )
        except (AttributeError, LookupError, TypeError, ValueError, OSError):
            # Збій виключно TEST_ONLY-телеметрії не перериває ринковий callback.
            recorder.file_errors += 1
        return result

    return traced_callback


def install_ib_network_guard(
    *,
    ib_adapter: type[object],
    ib_session_manager: type[object],
    ib_runtime_service: type[object],
    ib_api_client: type[object],
) -> tuple[str, ...]:
    """TEST_ONLY: заборонити відомі точки IB-з'єднання до запуску LGE."""
    boundaries = (
        (ib_adapter, ("connect",)),
        (ib_session_manager, ("connect_demo", "connect_live", "reconnect")),
        (ib_runtime_service, ("connect_demo", "connect_live", "reconnect")),
        (ib_api_client, ("connect",)),
    )
    # Спочатку перевірити всі точки. Якщо API змінився — запуск зупинити.
    for owner, methods in boundaries:
        for name in methods:
            if not callable(getattr(owner, name, None)):
                raise RuntimeError(
                    "T116-20B TEST_ONLY: IB boundary not found: "
                    f"{owner.__name__}.{name}"
                )

    def deny_ib_connect(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("T116-20B TEST_ONLY: будь-яке IB-підключення заборонено")

    installed: list[str] = []
    for owner, methods in boundaries:
        for name in methods:
            setattr(owner, name, deny_ib_connect)
            installed.append(f"{owner.__name__}.{name}")
    return tuple(installed)


@contextmanager
def isolate_real_config_writes(
    config_manager: type[object], protected_path: Path,
) -> Iterator[None]:
    """TEST_ONLY: дозволити читання LGE.conf, але заборонити його зміну.

    Обмеження: це захист файлових API поточного процесу, не системна ACL.
    """
    required = getattr(config_manager, "save", None)
    if not callable(required):
        raise RuntimeError("T116-20C TEST_ONLY: ConfigManager.save не знайдено")

    protected = {
        os.path.normcase(os.path.realpath(protected_path)),
        os.path.normcase(os.path.realpath(protected_path.with_suffix(".conf.bad"))),
    }

    def is_protected(path: object) -> bool:
        if not isinstance(path, (str, bytes, os.PathLike)):
            return False
        try:
            path_text = os.fsdecode(path)
            return os.path.normcase(os.path.realpath(path_text)) in protected
        except (TypeError, ValueError, OSError):
            return False

    def deny_write() -> None:
        raise RuntimeError("T116-20C TEST_ONLY: запис реального LGE.conf заборонено")

    def guarded_save(*_args: object, **_kwargs: object) -> None:
        deny_write()

    original_path_open = Path.open
    original_builtin_open = builtins.open
    original_os_open = os.open
    original_path_replace = Path.replace
    original_path_rename = Path.rename
    original_path_unlink = Path.unlink
    original_os_replace = os.replace
    original_os_rename = os.rename
    original_os_unlink = os.unlink
    original_os_remove = os.remove

    def is_write_mode(mode: str) -> bool:
        return any(flag in mode for flag in "wax+")

    def guarded_path_open(path: Path, mode: str = "r", *args: Any,
                          **kwargs: Any) -> Any:
        if is_protected(path) and is_write_mode(mode):
            deny_write()
        return original_path_open(path, mode, *args, **kwargs)

    def guarded_builtin_open(path: Any, mode: str = "r", *args: Any,
                             **kwargs: Any) -> Any:
        if is_protected(path) and is_write_mode(mode):
            deny_write()
        return original_builtin_open(path, mode, *args, **kwargs)

    def guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        write_flags = (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        )
        if is_protected(path) and flags & write_flags:
            deny_write()
        return original_os_open(path, flags, *args, **kwargs)

    def guarded_path_replace(path: Path, target: Any) -> Path:
        if is_protected(path) or is_protected(target):
            deny_write()
        return original_path_replace(path, target)

    def guarded_path_rename(path: Path, target: Any) -> Path:
        if is_protected(path) or is_protected(target):
            deny_write()
        return original_path_rename(path, target)

    def guarded_path_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if is_protected(path):
            deny_write()
        original_path_unlink(path, *args, **kwargs)

    def guarded_os_replace(src: Any, dst: Any, *args: Any,
                           **kwargs: Any) -> None:
        if is_protected(src) or is_protected(dst):
            deny_write()
        original_os_replace(src, dst, *args, **kwargs)

    def guarded_os_rename(src: Any, dst: Any, *args: Any,
                          **kwargs: Any) -> None:
        if is_protected(src) or is_protected(dst):
            deny_write()
        original_os_rename(src, dst, *args, **kwargs)

    def guarded_os_unlink(path: Any, *args: Any, **kwargs: Any) -> None:
        if is_protected(path):
            deny_write()
        original_os_unlink(path, *args, **kwargs)

    def guarded_os_remove(path: Any, *args: Any, **kwargs: Any) -> None:
        if is_protected(path):
            deny_write()
        original_os_remove(path, *args, **kwargs)

    # Підміни діють під час імпорту LGE та до завершення LGE.main().
    with (
        patch.object(config_manager, "save", guarded_save),
        patch.object(Path, "open", guarded_path_open),
        patch.object(builtins, "open", guarded_builtin_open),
        patch.object(os, "open", guarded_os_open),
        patch.object(Path, "replace", guarded_path_replace),
        patch.object(Path, "rename", guarded_path_rename),
        patch.object(Path, "unlink", guarded_path_unlink),
        patch.object(os, "replace", guarded_os_replace),
        patch.object(os, "rename", guarded_os_rename),
        patch.object(os, "unlink", guarded_os_unlink),
        patch.object(os, "remove", guarded_os_remove),
    ):
        yield


# Лише неторгові protobuf-запити, які використовує поточний cTrader Adapter.
CTRADER_READ_ONLY_PROTO_NAMES = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAGetAccountListByAccessTokenReq",
    "ProtoOAAccountAuthReq",
    "ProtoOATraderReq",
    "ProtoOAAssetListReq",
    "ProtoOASubscribeSpotsReq",
    "ProtoOAUnsubscribeSpotsReq",
    "ProtoOAGetTrendbarsReq",
    "ProtoOAReconcileReq",
    "ProtoOAOrderListReq",
    "ProtoOADealListReq",
    "ProtoOAGetPositionUnrealizedPnLReq",
)
CTRADER_UNSCOPED_PROTO_NAMES = frozenset({
    "ProtoOAApplicationAuthReq",
    "ProtoOAGetAccountListByAccessTokenReq",
    "ProtoHeartbeatEvent",
})
AUTHORIZED_DEMO_API_ID = 46368962


@contextmanager
def isolate_ctrader_outbound_protobuf(
    *,
    protocol_type: type[object] | None = None,
    request_messages: object | None = None,
    common_messages: object | None = None,
) -> Iterator[None]:
    """TEST_ONLY: пропускати лише відомі неторгові protobuf до TCP.

    Перевіряти і protobuf-об'єкт, і готовий ProtoMessage перед sendString.
    Невідомі типи, байти без конверта та чужі рахунки заборонені.
    """
    if all(
        item is None
        for item in (protocol_type, request_messages, common_messages)
    ):
        from ctrader_open_api import TcpProtocol
        from ctrader_open_api.messages import OpenApiCommonMessages_pb2
        from ctrader_open_api.messages import OpenApiMessages_pb2

        protocol_type = TcpProtocol
        request_messages = OpenApiMessages_pb2
        common_messages = OpenApiCommonMessages_pb2
    elif any(
        item is None
        for item in (protocol_type, request_messages, common_messages)
    ):
        raise RuntimeError("T116-20G: потрібні всі три компоненти SDK")

    if protocol_type is None:
        raise RuntimeError("T116-20G: TcpProtocol відсутній")

    permitted: dict[type[object], tuple[str, int]] = {}
    payload_types: dict[int, type[object]] = {}
    for name in (*CTRADER_READ_ONLY_PROTO_NAMES, "ProtoHeartbeatEvent"):
        module = (
            common_messages if name == "ProtoHeartbeatEvent"
            else request_messages
        )
        message_class = getattr(module, name, None)
        if not isinstance(message_class, type):
            raise RuntimeError(f"T116-20G: protobuf-клас {name} відсутній")
        sample = message_class()
        payload_type = getattr(sample, "payloadType", None)
        if not isinstance(payload_type, int) or payload_type <= 0:
            raise RuntimeError(f"T116-20G: payloadType {name} некоректний")
        if payload_type in payload_types:
            raise RuntimeError("T116-20G: дубль payloadType")
        permitted[message_class] = name, payload_type
        payload_types[payload_type] = message_class

    envelope_class = getattr(common_messages, "ProtoMessage", None)
    if not isinstance(envelope_class, type):
        raise RuntimeError("T116-20G: ProtoMessage відсутній")

    original_send = getattr(protocol_type, "send", None)
    original_send_string = getattr(protocol_type, "sendString", None)
    if not callable(original_send) or not callable(original_send_string):
        raise RuntimeError("T116-20G: мережевий API SDK не знайдено")

    def validate_request(request: object) -> None:
        definition = permitted.get(type(request))
        if definition is None:
            raise RuntimeError("T116-20G: protobuf не у білому списку")
        name, expected_payload = definition
        if getattr(request, "payloadType", None) != expected_payload:
            raise RuntimeError("T116-20G: payloadType змінено")
        initialized = getattr(request, "IsInitialized", None)
        if not callable(initialized) or not initialized():
            raise RuntimeError("T116-20G: неповний protobuf")
        if name not in CTRADER_UNSCOPED_PROTO_NAMES:
            account_id = getattr(request, "ctidTraderAccountId", None)
            if account_id != AUTHORIZED_DEMO_API_ID:
                raise RuntimeError("T116-20G: нецільовий DEMO API ID")

    def validate_bytes(packet: object) -> None:
        if not isinstance(packet, bytes):
            raise RuntimeError("T116-20G: тільки protobuf-конверт у байтах")
        try:
            envelope = envelope_class()
            envelope.ParseFromString(packet)
            if not envelope.IsInitialized():
                raise ValueError("незаповнений protobuf-конверт")
            request_class = payload_types.get(envelope.payloadType)
            if request_class is None:
                raise ValueError("невідомий payloadType")
            request = request_class()
            request.ParseFromString(envelope.payload)
        except Exception as exc:
            raise RuntimeError("T116-20G: небезпечний TCP payload") from exc
        validate_request(request)

    def guarded_send(client: object, message: object,
                     *args: Any, **kwargs: Any) -> Any:
        validate_request(message)
        return original_send(client, message, *args, **kwargs)

    def guarded_send_string(client: object, packet: object,
                            *args: Any, **kwargs: Any) -> Any:
        validate_bytes(packet)
        return original_send_string(client, packet, *args, **kwargs)

    with (
        patch.object(protocol_type, "send", guarded_send),
        patch.object(protocol_type, "sendString", guarded_send_string),
    ):
        yield


def load_production_callback() -> tuple[Callable[..., object], Callable[..., object]]:
    """Взяти реальні методи callback без імпорту мережевих бібліотек."""
    tree = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CTraderAdapter"
    )
    methods: dict[str, Callable[..., object]] = {}
    for name in ("_on_spot_event", "_optional_proto_scalar"):
        function = next(
            node for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        function.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        scope: dict[str, Any] = {
            "ctr_symbols": SimpleNamespace(
                get_symbol_name=lambda _: "EURUSD"
            ),
            "broker_live_trace": SimpleNamespace(
                record_ctrader_spot_callback=lambda **_: None
            ),
        }
        exec(compile(module, str(ADAPTER_FILE), "exec"), scope)
        methods[name] = scope[name]
    return methods["_on_spot_event"], methods["_optional_proto_scalar"]


class OfflineSession:
    """Ізольований кеш для виклику реального callback у тесті."""

    def __init__(self, reader: Callable[..., object]):
        self.config = SimpleNamespace(ctid_trader_account_id=777)
        self._spot_prices: dict[int, dict[str, object]] = {}
        self._spot_event = Event()
        self._optional_proto_scalar = reader

    @staticmethod
    def is_session_alive() -> bool:
        return True


def fake_event(ts: datetime, *, bid: int | None = None,
               ask: int | None = None) -> SimpleNamespace:
    """Створити payload із заданою наявністю protobuf-полів."""
    present = {"timestamp"}
    if bid is not None:
        present.add("bid")
    if ask is not None:
        present.add("ask")
    return SimpleNamespace(
        ctidTraderAccountId=777,
        symbolId=55,
        timestamp=int(ts.timestamp() * 1000),
        bid=bid,
        ask=ask,
        HasField=lambda key: key in present,
    )


def test_t116_19_ctrader_raw_spot_telemetry() -> None:
    """Довести, що raw presence розрізняє два джерела нульового spread."""
    actual_callback, scalar_reader = load_production_callback()
    recorder = RawSpotRecorder(max_events=20)
    wrapped = instrument_spot_callback(
        actual_callback, recorder, symbol_name=lambda _: "EURUSD"
    )
    session = OfflineSession(scalar_reader)
    t0 = datetime(2026, 11, 23, 13, 0, tzinfo=UTC)
    wrapped(session, fake_event(t0, bid=109375, ask=109377))
    wrapped(session, fake_event(t0 + timedelta(minutes=5), bid=109377))
    assert len(recorder.records) == 2
    assert recorder.records[1]["zero_spread_origin"] == "CACHE_MERGE_EQUAL"
    assert recorder.records[1]["raw_bid_present"] is True
    assert recorder.records[1]["raw_ask_present"] is False
    assert recorder.records[1]["side_broker_gap_seconds"] == 300

    second = OfflineSession(scalar_reader)
    wrapped(second, fake_event(t0 + timedelta(minutes=5), bid=109377, ask=109377))
    assert recorder.records[2]["zero_spread_origin"] == "RAW_BOTH_EQUAL"
    assert recorder.records[2]["raw_bid_present"] is True
    assert recorder.records[2]["raw_ask_present"] is True
    assert recorder.records[2]["side_broker_gap_seconds"] == 0

    # Відсутність зміни стану й telemetry за чужого broker account.
    other = fake_event(t0, bid=109380, ask=109381)
    other.ctidTraderAccountId = 999
    wrapped(session, other)
    assert len(recorder.records) == 3
    assert recorder.path is None
    assert recorder.file_errors == 0
    print("T116-19 TEST_ONLY | raw cTrader SpotEvent instrumentation")
    print("production_spot_callback=EXECUTED")
    print("raw_side_field_presence=CAPTURED")
    print("per_side_receive_and_broker_time=CAPTURED")
    print("cache_merged_zero_spread=DISAMBIGUATED")
    print("raw_both_equal_zero_spread=DISAMBIGUATED")
    print("mixed_side_broker_gap_seconds=300")
    print("live_spot_events=NOT_CAPTURED_OFFLINE")
    print("actual_2026_11_23_1300_quote_origin=NOT_PROVEN")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("T116-19=GREEN_OFFLINE_RAW_SPOT_TELEMETRY_CONTRACT")


def launch_live_supervised(
    *, run_process: Callable[..., object] = subprocess.run,
) -> int:
    """TEST_ONLY: зовнішній ліміт процесу навіть за завислого Qt-циклу."""
    command = [sys.executable, str(Path(__file__).resolve()), "--live-worker"]
    environment = {**os.environ, LIVE_WORKER_ENV: "1"}
    try:
        result = run_process(
            command,
            cwd=str(ROOT),
            env=environment,
            timeout=LIVE_PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # Аварійне завершення дочірнього процесу не гарантує graceful disconnect.
        print("T116-20D: LIVE worker перевищив жорсткий ліміт часу", flush=True)
        return 124
    return_code = getattr(result, "returncode", None)
    if not isinstance(return_code, int):
        raise RuntimeError("T116-20D: відсутній код завершення дочірнього процесу")
    return return_code


def launch_live_diagnostics() -> None:
    """Явно запустити LGE зі спостереженням raw quotes; не для pytest."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from engine import ctrader_adapter
    from engine.ib_adapter import IBAdapter
    from engine.ib_session_manager import IBSessionManager
    from engine.services.ib_runtime_service import IBRuntimeService
    from ibapi.client import EClient

    # Захистити IB до import LGE, включно з auto-connect та reconnect.
    ib_guards = install_ib_network_guard(
        ib_adapter=IBAdapter,
        ib_session_manager=IBSessionManager,
        ib_runtime_service=IBRuntimeService,
        ib_api_client=EClient,
    )
    print(f"T116-20B TEST_ONLY | IB blocked: {len(ib_guards)}/8", flush=True)

    trace_name = f"t116_19_ctrader_raw_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
    output = ROOT / "tests" / "runtime_temp" / trace_name
    recorder = RawSpotRecorder(path=output)
    adapter = ctrader_adapter.CTraderAdapter
    constructed_adapters: list[Any] = []
    original_init: Callable[..., None] = getattr(adapter, "__init__")

    def demo_only_init(self: object, config: object, logger: object = None) -> None:
        if str(getattr(config, "account_mode", "")).upper() != "DEMO":
            raise RuntimeError("T116-19 TEST_ONLY: LIVE-рахунок заборонено")
        if getattr(config, "ctid_trader_account_id", None) != 46368962:
            raise RuntimeError("T116-19 TEST_ONLY: дозволено лише DEMO API ID 46368962")
        # Включити до cleanup навіть адаптер із незавершеним __init__.
        constructed_adapters.append(self)
        original_init(self, config, logger)

    setattr(adapter, "__init__", demo_only_init)
    setattr(
        adapter,
        "_on_spot_event",
        instrument_spot_callback(
            getattr(adapter, "_on_spot_event"),
            recorder,
            symbol_name=ctrader_adapter.ctr_symbols.get_symbol_name,
        ),
    )

    def deny_trade(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("T116-19 TEST_ONLY: брокерські торгові дії заблоковано")

    for name in (
        "place_market_buy", "place_market_sell", "place_market_order",
        "close_position", "modify_position_sl_tp",
    ):
        setattr(adapter, name, deny_trade)
    print(f"T116-19 LIVE TEST_ONLY | EURUSD raw SpotEvent -> {output}", flush=True)
    print("ctrader_account_mode=DEMO_ONLY", flush=True)
    print("ctrader_trade_methods=BLOCKED; IB_Gateway=DO_NOT_START", flush=True)
    print(
        "Під час діагностики: Orders OFF, WSP MANUAL, без ручних ордерів.",
        flush=True,
    )
    from core.app_paths import ROOT_CONF_PATH
    from core.config_manager import ConfigManager

    @contextmanager
    def ctrader_disconnect_guard() -> Iterator[None]:
        """Закрити всі створені cTrader-адаптери після LGE або винятку."""
        # Утримувати protobuf guard активним до завершення disconnect().
        with isolate_ctrader_outbound_protobuf():
            try:
                yield
            finally:
                failures = 0
                for active_adapter in reversed(constructed_adapters):
                    try:
                        active_adapter.disconnect()
                    except Exception as exc:
                        failures += 1
                        print(
                            "T116-20E TEST_ONLY: cTrader disconnect failed: "
                            f"{type(exc).__name__}",
                            file=sys.stderr,
                            flush=True,
                        )
                print(
                    "T116-20E TEST_ONLY | "
                    f"disconnect_attempts={len(constructed_adapters)} "
                    f"disconnect_failures={failures}",
                    flush=True,
                )

    # Cleanup діє від імпорту LGE й охоплює помилки запуску GUI.
    with ctrader_disconnect_guard():
        # Захист до import LGE: міграція й backup_bad_conf не змінять конфіг.
        with isolate_real_config_writes(ConfigManager, ROOT_CONF_PATH):
            import LGE
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication

            original_application = LGE.QApplication

            def timed_application(argv: list[str]) -> QApplication:
                """Запустити таймер одразу після створення справжнього QApplication."""
                application = original_application(argv)
                timeout_timer = QTimer(application)
                timeout_timer.setSingleShot(True)
                timeout_timer.timeout.connect(application.quit)
                timeout_timer.start(LIVE_QT_TIMEOUT_SECONDS * 1000)
                return application

            def deny_restart() -> None:
                raise RuntimeError("T116-20D TEST_ONLY: restart LGE заборонено")

            sys.argv = [str(ROOT / "LGE.py")]
            try:
                with (
                    patch.object(LGE, "QApplication", timed_application),
                    patch.object(LGE, "_restart_application", deny_restart),
                ):
                    LGE.main()
            finally:
                print(f"raw_events={recorder.seen}", flush=True)
                print(f"recorded_events={len(recorder.records)}", flush=True)
                print(f"trace_file_errors={recorder.file_errors}", flush=True)
                print(f"jsonl_byte_cap={recorder.max_file_bytes}", flush=True)
                print(
                    f"jsonl_byte_cap_reached={recorder.byte_limit_reached}",
                    flush=True,
                )
                print(f"jsonl_byte_cap_hits={recorder.byte_limit_hits}", flush=True)
                print(f"trace_path={output}", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--live"]:
        raise SystemExit(launch_live_supervised())
    if sys.argv[1:] == ["--live-worker"]:
        if os.environ.get(LIVE_WORKER_ENV) != "1":
            raise SystemExit("T116-20D: запуск worker без supervisor заборонений")
        launch_live_diagnostics()
    elif not sys.argv[1:]:
        test_t116_19_ctrader_raw_spot_telemetry()
    else:
        raise SystemExit("Використання: script.py [--live]")
