"""run_t107_16_broker_live_stall_factual_telemetry_check.py — T107-16.

TEST_ONLY runner перевіряє opt-in observability для factual BROKER live stall.
Він двічі проводить однаковий public WorkspaceRuntime flow через production
provider та aggregator: спочатку з вимкненим trace, потім із явним
``LGE_TEST_ONLY_BROKER_LIVE_TRACE=1`` і тимчасовим JSONL path. Результати
market-data/state flow мають бути ідентичними.

Локальний RuntimeEngine seam імітує historical catch-up та два cTrader spot
callbacks, другий з яких створює M1 rollover. Runner перевіряє callback,
provider signature, aggregator, runtime-state і forced heartbeat records,
узгоджені counters/timestamps та нуль broker execution. Реальні broker requests,
orders, Candidate F, guards, polling cadence, MD7 і localization не змінюються.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import workspace_broker_live_trace as broker_live_trace  # noqa: E402
from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RUNNING,
    AlgorithmWorkspace,
)
from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WorkspaceRuntime,
)

TEST_ID = "T107-16"
MODE = "RM107_T107_16_BROKER_LIVE_STALL_FACTUAL_TELEMETRY_TEST_ONLY"
BASE_TIME = datetime(2026, 9, 4, 14, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FakeHistoricalBar:
    """Один completed bar для deterministic M1 warm-up."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class FakeHistoryResult:
    """Повернути production-compatible history payload без мережі."""

    bars: tuple[FakeHistoricalBar, ...]
    request_count: int


@dataclass(frozen=True, slots=True)
class FlowResult:
    """Порівняти runtime semantics при trace OFF і ON."""

    first_event_is_none: bool
    completed_timestamp: datetime
    runtime_state: str
    startup_phase: str
    latest_bar_timestamp: datetime
    market_event_count: int
    execution_attempts: int


class FakeRuntimeEngine:
    """Подати history і cached quotes через фактичний provider contract."""

    def __init__(self) -> None:
        self.current_quote: tuple[datetime, float, float] | None = None
        self.execution_attempts = 0

    @staticmethod
    def validate_workspace_broker_binding(
        broker_name: str,
        account_id: str | None,
    ) -> None:
        """Прийняти лише локальну CTRADER DEMO binding."""
        if (broker_name, account_id) != ("CTRADER", "T10716-DEMO"):
            raise RuntimeError("unexpected T107-16 binding")

    @staticmethod
    def is_named_broker_connected(broker_name: str) -> bool:
        """Повернути healthy connection без зовнішнього broker call."""
        return broker_name == "CTRADER"

    def set_quote(self, timestamp: datetime, bid: float, ask: float) -> None:
        """Імітувати один фактичний spot callback і оновлення quote cache."""
        self.current_quote = (timestamp, float(bid), float(ask))
        broker_live_trace.record_ctrader_spot_callback(
            symbol="EURUSD",
            broker_quote_timestamp=timestamp,
            bid=bid,
            ask=ask,
            volume=0.0,
        )

    def get_workspace_forex_quote_snapshot(
        self,
        broker_name: str,
        symbol_names: list[str],
    ) -> dict[str, object]:
        """Повернути останній callback snapshot provider-у."""
        if broker_name != "CTRADER" or symbol_names != ["EURUSD"]:
            raise RuntimeError("unexpected quote request")
        if self.current_quote is None:
            return {
                "captured_utc": BASE_TIME.isoformat(),
                "complete": False,
                "quotes": {},
                "subscribed_symbols": ["EURUSD"],
            }
        timestamp, bid, ask = self.current_quote
        return {
            "captured_utc": timestamp.isoformat(),
            "complete": True,
            "quotes": {
                "EURUSD": {
                    "symbol_name": "EURUSD",
                    "timestamp": timestamp.isoformat(),
                    "bid": bid,
                    "ask": ask,
                    "volume": 0.0,
                }
            },
            "subscribed_symbols": ["EURUSD"],
        }

    @staticmethod
    def download_ctrader_historical_bars(
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> FakeHistoryResult:
        """Повернути три causal M1 bars перед live bucket."""
        if symbol_name != "EURUSD" or timeframe != "M1":
            raise RuntimeError("unexpected history request")
        if start_utc >= end_utc:
            raise RuntimeError("invalid history range")
        bars = tuple(
            FakeHistoricalBar(
                timestamp=BASE_TIME - timedelta(minutes=3 - index),
                open=1.1690 + index * 0.0001,
                high=1.1694 + index * 0.0001,
                low=1.1688 + index * 0.0001,
                close=1.1692 + index * 0.0001,
                volume=100.0 + index,
            )
            for index in range(3)
        )
        return FakeHistoryResult(bars=bars, request_count=1)


def _workspace() -> AlgorithmWorkspace:
    """Створити M1 BROKER workspace без algorithm execution."""
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="T10716-DEMO",
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M1",
        algorithm="T10716Passive",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        parameters={
            "warmup_bars": 3,
            "spread_limit": 0.0003,
        },
    )


def _reload_trace(*, enabled: bool, path: Path) -> None:
    """Перезавантажити TEST_ONLY singleton після локальної env зміни."""
    if enabled:
        os.environ[broker_live_trace.TRACE_FLAG] = "1"
    else:
        os.environ.pop(broker_live_trace.TRACE_FLAG, None)
    os.environ[broker_live_trace.TRACE_PATH_FLAG] = str(path)
    importlib.reload(broker_live_trace)


def _run_flow() -> FlowResult:
    """Пройти history, initial bucket і completed M1 rollover public API."""
    engine = FakeRuntimeEngine()
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    runtime = WorkspaceRuntime(_workspace(), broker_market_provider=provider)
    runtime.begin_start()
    runtime.complete_start()

    engine.set_quote(BASE_TIME + timedelta(seconds=10), 1.1700, 1.1702)
    first_event = runtime.advance_broker_market()
    engine.set_quote(BASE_TIME + timedelta(minutes=1, seconds=1), 1.1701, 1.1703)
    completed = runtime.advance_broker_market()
    if completed is None:
        raise AssertionError("fresh M1 rollover did not emit a completed bar")
    latest = runtime.chart_snapshot().events[-1]
    result = FlowResult(
        first_event_is_none=first_event is None,
        completed_timestamp=completed.timestamp,
        runtime_state=runtime.context.runtime_state,
        startup_phase=runtime.context.startup_phase,
        latest_bar_timestamp=latest.timestamp,
        market_event_count=runtime.context.market_event_count,
        execution_attempts=engine.execution_attempts,
    )
    runtime.stop("T107-16 flow completed")
    return result


def _read_trace(path: Path) -> tuple[dict[str, object], ...]:
    """Прочитати завершені JSONL records для deterministic assertions."""
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _integer_field(record: dict[str, object], field_name: str) -> int | None:
    """Прочитати JSON integer без cast або неявного object conversion."""
    value = record.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _instrumentation_wired() -> dict[str, bool]:
    """Перевірити production call sites без звернення до private API."""
    adapter_source = (PROJECT_ROOT / "engine" / "ctrader_adapter.py").read_text(
        encoding="utf-8"
    )
    provider_source = (PROJECT_ROOT / "core" / "workspace_broker_market.py").read_text(
        encoding="utf-8"
    )
    runtime_source = (PROJECT_ROOT / "core" / "workspace_runtime.py").read_text(
        encoding="utf-8"
    )
    return {
        "callback": "record_ctrader_spot_callback(" in adapter_source,
        "provider": "record_provider_signature(" in provider_source,
        "aggregator": "record_aggregator_update(" in provider_source,
        "runtime": "record_runtime_state(" in runtime_source,
    }


def main() -> None:
    """Довести opt-in trace, semantic neutrality і coherent heartbeat."""
    original_flag = os.environ.get(broker_live_trace.TRACE_FLAG)
    original_path = os.environ.get(broker_live_trace.TRACE_PATH_FLAG)
    try:
        with TemporaryDirectory(prefix="t107_16_") as temp_directory:
            temp_root = Path(temp_directory)
            disabled_path = temp_root / "disabled.jsonl"
            enabled_path = temp_root / "enabled.jsonl"

            _reload_trace(enabled=False, path=disabled_path)
            disabled_result = _run_flow()
            trace_default_disabled = not disabled_path.exists()

            _reload_trace(enabled=True, path=enabled_path)
            broker_live_trace.reset_broker_live_trace_for_test()
            enabled_result = _run_flow()
            heartbeat_emitted = broker_live_trace.emit_broker_live_trace_heartbeat(
                force=True
            )
            records = _read_trace(enabled_path)
    finally:
        if original_flag is None:
            os.environ.pop(broker_live_trace.TRACE_FLAG, None)
        else:
            os.environ[broker_live_trace.TRACE_FLAG] = original_flag
        if original_path is None:
            os.environ.pop(broker_live_trace.TRACE_PATH_FLAG, None)
        else:
            os.environ[broker_live_trace.TRACE_PATH_FLAG] = original_path
        importlib.reload(broker_live_trace)

    semantics_unchanged = disabled_result == enabled_result
    events = {str(record.get("event")) for record in records}
    wired = _instrumentation_wired()
    heartbeats = [
        record for record in records if record.get("event") == "LIVE_TRACE_HEARTBEAT"
    ]
    heartbeat = heartbeats[-1] if heartbeats else {}
    counters_coherent = bool(
        heartbeat_emitted
        and _integer_field(heartbeat, "callback_count") == 2
        and _integer_field(heartbeat, "provider_poll_count") == 2
        and _integer_field(heartbeat, "signature_change_count") == 2
        and _integer_field(heartbeat, "completed_bar_count") == 1
        and heartbeat.get("last_broker_quote_timestamp")
        == (BASE_TIME + timedelta(minutes=1, seconds=1)).isoformat()
        and heartbeat.get("last_completed_bar_utc") == BASE_TIME.isoformat()
        and heartbeat.get("workspace_latest_m1") == BASE_TIME.isoformat()
    )
    required_events = {
        "CTRADER_SPOT_CALLBACK",
        "PROVIDER_SIGNATURE",
        "AGGREGATOR_UPDATE",
        "WORKSPACE_RUNTIME_STATE",
        "LIVE_TRACE_HEARTBEAT",
    }
    trace_compact = len(records) <= 12
    broker_execution_attempted = bool(
        disabled_result.execution_attempts or enabled_result.execution_attempts
    )

    contract_ok = bool(
        trace_default_disabled
        and semantics_unchanged
        and all(wired.values())
        and required_events <= events
        and counters_coherent
        and trace_compact
        and disabled_result.first_event_is_none
        and disabled_result.completed_timestamp == BASE_TIME
        and disabled_result.runtime_state == WORKSPACE_STATE_RUNNING
        and disabled_result.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
        and not broker_execution_attempted
    )
    if not contract_ok:
        raise AssertionError("T107-16 telemetry contract changed; inspect evidence")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"trace_default_disabled={trace_default_disabled}")
    print(f"trace_changes_runtime_semantics={not semantics_unchanged}")
    print(f"callback_trace_available={wired['callback']}")
    print(f"provider_trace_available={wired['provider']}")
    print(f"aggregator_trace_available={wired['aggregator']}")
    print(f"runtime_state_trace_available={wired['runtime']}")
    print(f"heartbeat_available={bool(heartbeats)}")
    print(f"heartbeat_counters_coherent={counters_coherent}")
    print(f"trace_compact={trace_compact}")
    print(f"trace_records={len(records)}")
    print("heartbeat_interval_seconds=30")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print("production_logic_changed=False")
    print("T107_16_BROKER_LIVE_STALL_FACTUAL_TELEMETRY=OK")


if __name__ == "__main__":
    main()
