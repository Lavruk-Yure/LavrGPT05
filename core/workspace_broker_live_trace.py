"""workspace_broker_live_trace.py — TEST_ONLY telemetry BROKER live stall.

Модуль збирає компактний JSONL trace для чотирьох меж: cTrader spot callback,
workspace provider signature guard, live-bar aggregator і WorkspaceRuntime.
Instrumentation активується лише через ``LGE_TEST_ONLY_BROKER_LIVE_TRACE=1``;
без flag усі public record-функції негайно повертаються без файлових операцій,
зміни counters або впливу на market-data semantics.

При активному flag callback і signature counters оновлюються на кожній події,
але детальні samples throttled. ``LIVE_TRACE_HEARTBEAT`` раз на 30 секунд
зберігає фактичний прогрес усіх меж та latest bars M1/M5/M15. Помилка запису
trace навмисно не може зупинити broker runtime. Модуль не підписується на
market data, не змінює polling, guards, aggregation та не виконує orders.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

TRACE_FLAG = "LGE_TEST_ONLY_BROKER_LIVE_TRACE"
TRACE_PATH_FLAG = "LGE_TEST_ONLY_BROKER_LIVE_TRACE_PATH"
TRACE_HEARTBEAT_SECONDS = 30.0
TRACE_SAMPLE_SECONDS = 5.0
DEFAULT_TRACE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "runtime_temp"
    / "t107_16_broker_live_trace.jsonl"
)


def _flag_enabled(value: object) -> bool:
    """Нормалізувати лише явні truthy значення TEST_ONLY flag."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


_TRACE_ENABLED = _flag_enabled(os.environ.get(TRACE_FLAG))
_TRACE_PATH = Path(os.environ.get(TRACE_PATH_FLAG) or DEFAULT_TRACE_PATH)


@dataclass(slots=True)
class _BrokerLiveTraceState:
    """Зберігати bounded in-memory counters і останні factual timestamps."""

    callback_count: int = 0
    provider_poll_count: int = 0
    signature_change_count: int = 0
    completed_bar_count: int = 0
    last_callback_utc: str | None = None
    last_broker_quote_timestamp: str | None = None
    last_signature_change_utc: str | None = None
    last_completed_bar_utc: str | None = None
    workspace_latest_bars: dict[str, str | None] = field(default_factory=dict)
    workspace_timeframes: dict[str, str] = field(default_factory=dict)
    last_provider_results: dict[str, str] = field(default_factory=dict)
    last_aggregator_buckets: dict[str, str] = field(default_factory=dict)
    last_runtime_states: dict[str, str] = field(default_factory=dict)
    last_callback_sample_monotonic: float = 0.0
    last_signature_sample_monotonic: dict[str, float] = field(default_factory=dict)
    last_heartbeat_monotonic: float = 0.0


_STATE = _BrokerLiveTraceState()
_LOCK = threading.RLock()


def broker_live_trace_enabled() -> bool:
    """Повернути startup-resolved стан TEST_ONLY instrumentation."""
    return _TRACE_ENABLED


def broker_live_trace_path() -> Path:
    """Повернути configured JSONL path без створення файла."""
    return _TRACE_PATH


def _utc_now_iso() -> str:
    """Повернути aware UTC timestamp для receive/trace chronology."""
    return datetime.now(UTC).isoformat()


def _timestamp_text(value: object) -> str | None:
    """Нормалізувати timestamp-like value без зміни broker payload."""
    if value is None:
        return None
    if isinstance(value, datetime):
        timestamp = value
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC).isoformat()
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0.0:
            return None
        if raw > 10_000_000_000.0:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(value)
    text = str(value or "").strip()
    return text or None


def _json_value(value: object) -> object:
    """Перетворити trace fields на bounded JSON-compatible values."""
    if isinstance(value, datetime):
        return _timestamp_text(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_event(event: str, **fields: object) -> None:
    """Append one JSONL event; trace I/O failure never affects runtime."""
    if not _TRACE_ENABLED:
        return
    payload = {
        "event": str(event),
        "trace_utc": _utc_now_iso(),
        **{key: _json_value(value) for key, value in fields.items()},
    }
    try:
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    except OSError:
        return


def record_ctrader_spot_callback(
    *,
    symbol: str,
    broker_quote_timestamp: object,
    bid: object,
    ask: object,
    volume: object = None,
) -> None:
    """Count every cTrader callback and write a throttled factual sample."""
    if not _TRACE_ENABLED:
        return
    now_monotonic = time.monotonic()
    receive_utc = _utc_now_iso()
    quote_timestamp = _timestamp_text(broker_quote_timestamp)
    with _LOCK:
        _STATE.callback_count += 1
        _STATE.last_callback_utc = receive_utc
        if quote_timestamp is not None:
            _STATE.last_broker_quote_timestamp = quote_timestamp
        emit_sample = bool(
            _STATE.callback_count == 1
            or now_monotonic - _STATE.last_callback_sample_monotonic
            >= TRACE_SAMPLE_SECONDS
        )
        if emit_sample:
            _STATE.last_callback_sample_monotonic = now_monotonic
        callback_count = _STATE.callback_count
    if emit_sample:
        _write_event(
            "CTRADER_SPOT_CALLBACK",
            receive_utc=receive_utc,
            broker_quote_timestamp=quote_timestamp,
            symbol=str(symbol or "").strip().upper(),
            bid=bid,
            ask=ask,
            volume=volume,
            callback_count=callback_count,
        )


def record_provider_poll(*, workspace_uid: str, timeframe: str) -> None:
    """Count each provider poll without logging every 250-ms scheduler cycle."""
    if not _TRACE_ENABLED:
        return
    with _LOCK:
        _STATE.provider_poll_count += 1
        _STATE.workspace_timeframes[str(workspace_uid)] = str(timeframe).upper()
    emit_broker_live_trace_heartbeat()


def record_provider_signature(
    *,
    workspace_uid: str,
    timeframe: str,
    quote_timestamp: object,
    signature: object,
    signature_changed: bool,
    guard_result: str,
) -> None:
    """Record signature changes and guard transitions with bounded sampling."""
    if not _TRACE_ENABLED:
        return
    uid = str(workspace_uid)
    result = str(guard_result or "UNKNOWN").strip().upper()
    now_monotonic = time.monotonic()
    change_utc: str | None = None
    with _LOCK:
        previous_result = _STATE.last_provider_results.get(uid)
        _STATE.last_provider_results[uid] = result
        _STATE.workspace_timeframes[uid] = str(timeframe).upper()
        if signature_changed:
            _STATE.signature_change_count += 1
            change_utc = _utc_now_iso()
            _STATE.last_signature_change_utc = change_utc
        last_sample = _STATE.last_signature_sample_monotonic.get(uid, 0.0)
        emit_sample = bool(
            previous_result != result
            or (
                signature_changed
                and now_monotonic - last_sample >= TRACE_SAMPLE_SECONDS
            )
        )
        if emit_sample:
            _STATE.last_signature_sample_monotonic[uid] = now_monotonic
        signature_change_count = _STATE.signature_change_count
    if emit_sample:
        _write_event(
            "PROVIDER_SIGNATURE",
            workspace_uid=uid,
            timeframe=str(timeframe).upper(),
            quote_timestamp=_timestamp_text(quote_timestamp),
            signature=signature,
            signature_changed=bool(signature_changed),
            guard_result=result,
            signature_change_utc=change_utc,
            signature_change_count=signature_change_count,
        )


def record_aggregator_update(
    *,
    workspace_uid: str,
    timeframe: str,
    quote_timestamp: object,
    current_bucket: object,
    quote_accepted: bool,
    guard_result: str,
    rollover: bool,
    completed_bar_timestamp: object = None,
) -> None:
    """Record first bucket, guard rejection and every completed rollover."""
    if not _TRACE_ENABLED:
        return
    uid = str(workspace_uid)
    bucket_text = _timestamp_text(current_bucket) or ""
    completed_text = _timestamp_text(completed_bar_timestamp)
    with _LOCK:
        previous_bucket = _STATE.last_aggregator_buckets.get(uid)
        if bucket_text:
            _STATE.last_aggregator_buckets[uid] = bucket_text
        emit_event = bool(
            previous_bucket != bucket_text
            or not quote_accepted
            or rollover
            or completed_text is not None
        )
        if completed_text is not None:
            _STATE.completed_bar_count += 1
            _STATE.last_completed_bar_utc = completed_text
        completed_bar_count = _STATE.completed_bar_count
    if emit_event:
        _write_event(
            "AGGREGATOR_UPDATE",
            workspace_uid=uid,
            timeframe=str(timeframe).upper(),
            quote_timestamp=_timestamp_text(quote_timestamp),
            current_bucket=bucket_text or None,
            quote_accepted=bool(quote_accepted),
            guard_result=str(guard_result or "UNKNOWN").strip().upper(),
            rollover=bool(rollover),
            completed_bar_timestamp=completed_text,
            completed_bar_count=completed_bar_count,
        )


def record_runtime_state(
    *,
    workspace_uid: str,
    timeframe: str,
    incoming_event_timestamp: object,
    spread: object,
    state_before: str,
    state_after: str,
    latest_bar_timestamp: object,
) -> None:
    """Record runtime event/state changes and update heartbeat latest bars."""
    if not _TRACE_ENABLED:
        return
    uid = str(workspace_uid)
    latest_text = _timestamp_text(latest_bar_timestamp)
    normalized_timeframe = str(timeframe).upper()
    with _LOCK:
        previous_state = _STATE.last_runtime_states.get(uid)
        _STATE.last_runtime_states[uid] = str(state_after)
        _STATE.workspace_timeframes[uid] = normalized_timeframe
        _STATE.workspace_latest_bars[uid] = latest_text
        emit_event = bool(
            incoming_event_timestamp is not None
            or previous_state != str(state_after)
            or str(state_before) != str(state_after)
        )
    if emit_event:
        _write_event(
            "WORKSPACE_RUNTIME_STATE",
            workspace_uid=uid,
            timeframe=normalized_timeframe,
            incoming_event_timestamp=_timestamp_text(incoming_event_timestamp),
            spread=spread,
            state_before=str(state_before),
            state_after=str(state_after),
            latest_bar_timestamp=latest_text,
        )


def emit_broker_live_trace_heartbeat(*, force: bool = False) -> bool:
    """Emit one compact heartbeat after interval or on explicit TEST_ONLY force."""
    if not _TRACE_ENABLED:
        return False
    now_monotonic = time.monotonic()
    with _LOCK:
        if (
            not force
            and _STATE.last_heartbeat_monotonic > 0.0
            and now_monotonic - _STATE.last_heartbeat_monotonic
            < TRACE_HEARTBEAT_SECONDS
        ):
            return False
        _STATE.last_heartbeat_monotonic = now_monotonic
        latest_by_timeframe: dict[str, str | None] = {
            "M1": None,
            "M5": None,
            "M15": None,
        }
        for uid, timeframe in _STATE.workspace_timeframes.items():
            if timeframe not in latest_by_timeframe:
                continue
            candidate = _STATE.workspace_latest_bars.get(uid)
            current = latest_by_timeframe[timeframe]
            if candidate is not None and (current is None or candidate > current):
                latest_by_timeframe[timeframe] = candidate
        snapshot = {
            "callback_count": _STATE.callback_count,
            "last_callback_utc": _STATE.last_callback_utc,
            "last_broker_quote_timestamp": _STATE.last_broker_quote_timestamp,
            "provider_poll_count": _STATE.provider_poll_count,
            "signature_change_count": _STATE.signature_change_count,
            "last_signature_change_utc": _STATE.last_signature_change_utc,
            "completed_bar_count": _STATE.completed_bar_count,
            "last_completed_bar_utc": _STATE.last_completed_bar_utc,
            "workspace_latest_m1": latest_by_timeframe["M1"],
            "workspace_latest_m5": latest_by_timeframe["M5"],
            "workspace_latest_m15": latest_by_timeframe["M15"],
        }
    _write_event("LIVE_TRACE_HEARTBEAT", current_utc=_utc_now_iso(), **snapshot)
    return True


def reset_broker_live_trace_for_test() -> None:
    """Reset only in-memory TEST_ONLY state for deterministic runner checks."""
    if not _TRACE_ENABLED:
        return
    global _STATE
    with _LOCK:
        _STATE = _BrokerLiveTraceState()
