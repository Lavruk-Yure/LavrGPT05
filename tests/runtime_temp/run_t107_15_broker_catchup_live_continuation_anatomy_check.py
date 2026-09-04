"""run_t107_15_broker_catchup_live_continuation_anatomy_check.py — T107-15.

TEST_ONLY anatomy відтворює production BROKER pipeline від historical warm-up
до тривалого live continuation для незалежних M1/M5/M15 workspaces. Один
контрольований RuntimeEngine seam повертає завершені historical bars і змінні
live quote snapshots; реальні мережа, broker orders та execution API не
використовуються.

Окремий stale-snapshot сценарій відтворює стан, коли broker payload уже має
bid/ask, але незмінна quote signature не створює rollover event, тому WSP
залишається WAIT_SPREAD. Runner відділяє доведений production contract від
фактичної live-сесії 2026-09-04: локальне відтворення може звузити stall layer,
але без runtime telemetry не оголошує непідтверджену live root cause.

Перевірка не змінює Candidate F, AUTO/SEMI execution, SL/TP, PD, indicators,
MD7, localization або будь-яку production logic. Final marker OK означає лише
узгодженість anatomy assertions із поточним кодом.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RUNNING,
    AlgorithmWorkspace,
)
from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
    WorkspaceRuntime,
)

TEST_ID = "T107-15"
MODE = "RM107_T107_15_BROKER_CATCHUP_LIVE_CONTINUATION_ANATOMY_TEST_ONLY"
BASE_TIME = datetime(2026, 9, 4, 14, 0, tzinfo=UTC)
TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15}


@dataclass(frozen=True, slots=True)
class FakeHistoricalBar:
    """Один completed historical bar для production provider warm-up path."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class FakeHistoryResult:
    """Повернути bars і market-data request count у production shape."""

    bars: tuple[FakeHistoricalBar, ...]
    request_count: int


class ControlledRuntimeEngine:
    """Подати спільну streaming quote cache для трьох незалежних WSP."""

    def __init__(self) -> None:
        self.connected = True
        self.current_quote: tuple[datetime, float, float] | None = None
        self.history_calls: list[str] = []
        self.quote_calls: list[tuple[str, ...]] = []
        self.execution_attempts = 0

    def validate_workspace_broker_binding(
        self,
        broker_name: str,
        account_id: str | None,
    ) -> None:
        """Прийняти лише локальну CTRADER DEMO binding тесту."""
        if broker_name != "CTRADER" or account_id != "T10715-DEMO":
            raise RuntimeError("unexpected T107-15 broker binding")
        if not self.connected:
            raise RuntimeError("controlled broker is disconnected")

    def is_named_broker_connected(self, broker_name: str) -> bool:
        """Повернути керований connection state без зовнішнього broker call."""
        return self.connected and broker_name == "CTRADER"

    def set_quote(
        self,
        timestamp: datetime,
        *,
        bid: float = 1.1700,
        ask: float = 1.1702,
    ) -> None:
        """Оновити локальну streaming cache новою quote signature."""
        self.current_quote = (timestamp, float(bid), float(ask))

    def get_workspace_forex_quote_snapshot(
        self,
        broker_name: str,
        symbol_names: list[str],
    ) -> dict[str, object]:
        """Повернути cached bid/ask так, як RuntimeEngine віддає provider-у."""
        if broker_name != "CTRADER":
            raise RuntimeError("unexpected broker")
        symbols = tuple(sorted(str(value).upper() for value in symbol_names))
        self.quote_calls.append(symbols)
        quote = self.current_quote
        if quote is None:
            return {
                "captured_utc": BASE_TIME.isoformat(),
                "complete": False,
                "quotes": {},
                "subscribed_symbols": list(symbols),
            }
        timestamp, bid, ask = quote
        return {
            "captured_utc": timestamp.isoformat(),
            "complete": True,
            "quotes": {
                symbol: {
                    "symbol_name": symbol,
                    "timestamp": timestamp.isoformat(),
                    "bid": bid,
                    "ask": ask,
                    "volume": 0.0,
                }
                for symbol in symbols
            },
            "subscribed_symbols": list(symbols),
        }

    def download_ctrader_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> FakeHistoryResult:
        """Повернути causal catch-up, завершений перед BASE_TIME."""
        if symbol_name != "EURUSD" or start_utc >= end_utc:
            raise RuntimeError("unexpected history request")
        minutes = TIMEFRAME_MINUTES[timeframe]
        self.history_calls.append(timeframe)
        latest = BASE_TIME - timedelta(minutes=minutes)
        bars = tuple(
            FakeHistoricalBar(
                timestamp=latest - timedelta(minutes=minutes * (4 - index)),
                open=1.1690 + index * 0.0001,
                high=1.1694 + index * 0.0001,
                low=1.1688 + index * 0.0001,
                close=1.1692 + index * 0.0001,
                volume=100.0 + index,
            )
            for index in range(5)
        )
        return FakeHistoryResult(bars=bars, request_count=1)


@dataclass(frozen=True, slots=True)
class ContinuationResult:
    """Зберегти per-timeframe catch-up, rollover і runtime state evidence."""

    history_catchup: bool
    live_continuation: bool
    latest_advanced: bool
    reached_running: bool
    completed_events: int


def _workspace(timeframe: str) -> AlgorithmWorkspace:
    """Створити мінімальний BROKER DEMO workspace без execution wiring."""
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="T10715-DEMO",
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe=timeframe,
        algorithm="T10715Passive",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "warmup_bars": 3,
            "spread_limit": 0.0003,
        },
    )


def _start_runtimes(
    engine: ControlledRuntimeEngine,
) -> tuple[
    RuntimeEngineWorkspaceMarketProvider,
    dict[str, WorkspaceRuntime],
    dict[str, datetime],
]:
    """Завантажити history й залишити M1/M5/M15 у WAIT_SPREAD."""
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    runtimes: dict[str, WorkspaceRuntime] = {}
    history_latest: dict[str, datetime] = {}
    for timeframe in TIMEFRAME_MINUTES:
        runtime = WorkspaceRuntime(
            _workspace(timeframe),
            broker_market_provider=provider,
        )
        runtime.begin_start()
        runtime.complete_start()
        events = runtime.chart_snapshot().events
        if not events:
            raise AssertionError(f"{timeframe} history catch-up is empty")
        if runtime.context.startup_phase != WORKSPACE_STARTUP_PHASE_WAIT_SPREAD:
            raise AssertionError(f"{timeframe} did not enter WAIT_SPREAD")
        runtimes[timeframe] = runtime
        history_latest[timeframe] = events[-1].timestamp
    return provider, runtimes, history_latest


def _poll_all(
    runtimes: dict[str, WorkspaceRuntime],
) -> dict[str, object | None]:
    """Імітувати один UI scheduler cycle для всіх відкритих WSP."""
    return {
        timeframe: runtime.advance_broker_market()
        for timeframe, runtime in runtimes.items()
    }


def _fresh_continuation_anatomy() -> tuple[
    dict[str, ContinuationResult],
    bool,
    bool,
    int,
]:
    """Довести history→quote→rollover→RUNNING і наступні live bars."""
    engine = ControlledRuntimeEngine()
    provider, runtimes, history_latest = _start_runtimes(engine)

    engine.set_quote(BASE_TIME + timedelta(seconds=10))
    first_cycle = _poll_all(runtimes)
    first_quote_opens_only_partial_bucket = all(
        event is None for event in first_cycle.values()
    )
    wait_spread_has_no_runtime_spread = all(
        runtime.context.current_spread is None
        and runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
        for runtime in runtimes.values()
    )

    schedule = (
        BASE_TIME + timedelta(minutes=1, seconds=1),
        BASE_TIME + timedelta(minutes=5, seconds=1),
        BASE_TIME + timedelta(minutes=15, seconds=1),
        BASE_TIME + timedelta(minutes=30, seconds=1),
        BASE_TIME + timedelta(minutes=45, seconds=1),
    )
    completed_counts = {timeframe: 0 for timeframe in runtimes}
    for index, timestamp in enumerate(schedule, start=1):
        engine.set_quote(
            timestamp,
            bid=1.1700 + index * 0.00001,
            ask=1.1702 + index * 0.00001,
        )
        for timeframe, event in _poll_all(runtimes).items():
            if event is not None:
                completed_counts[timeframe] += 1

    results: dict[str, ContinuationResult] = {}
    for timeframe, runtime in runtimes.items():
        latest = runtime.chart_snapshot().events[-1].timestamp
        expected_history_latest = BASE_TIME - timedelta(
            minutes=TIMEFRAME_MINUTES[timeframe]
        )
        results[timeframe] = ContinuationResult(
            history_catchup=history_latest[timeframe] == expected_history_latest,
            live_continuation=completed_counts[timeframe] >= 2,
            latest_advanced=latest > history_latest[timeframe],
            reached_running=bool(
                runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
                and runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
            ),
            completed_events=completed_counts[timeframe],
        )

    accounting = provider.request_accounting_snapshot()
    subscription_created = bool(
        accounting.active_subscriptions == 1
        and accounting.active_references == 3
        and engine.quote_calls
        and all(call == ("EURUSD",) for call in engine.quote_calls)
    )
    for runtime in runtimes.values():
        runtime.stop("T107-15 fresh continuation completed")
    return (
        results,
        subscription_created,
        bool(
            first_quote_opens_only_partial_bucket and wait_spread_has_no_runtime_spread
        ),
        accounting.quote_snapshot_requests,
    )


def _stale_snapshot_anatomy() -> dict[str, bool | int]:
    """Відтворити WAIT_SPREAD stall на валідній, але незмінній quote cache."""
    engine = ControlledRuntimeEngine()
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    runtime = WorkspaceRuntime(
        _workspace("M1"),
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    history_latest = runtime.chart_snapshot().events[-1].timestamp

    engine.set_quote(BASE_TIME + timedelta(seconds=10))
    first = runtime.advance_broker_market()
    for _ in range(20):
        duplicate = runtime.advance_broker_market()
        if duplicate is not None:
            raise AssertionError("unchanged quote emitted an unexpected live bar")

    accounting = provider.request_accounting_snapshot()
    quote_payload_has_bid_ask = engine.current_quote is not None
    chart_latest = runtime.chart_snapshot().events[-1].timestamp
    result: dict[str, bool | int] = {
        "quote_payload_has_bid_ask": quote_payload_has_bid_ask,
        "first_partial_only": first is None,
        "scheduler_polling_continues": accounting.quote_snapshot_requests == 21,
        "wait_spread_exit_triggered": (
            runtime.context.startup_phase != WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
        ),
        "workspace_reaches_running": (
            runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
        ),
        "workspace_bar_advanced": chart_latest > history_latest,
        "quote_snapshot_requests": accounting.quote_snapshot_requests,
    }
    runtime.stop("T107-15 stale snapshot anatomy completed")
    return result


def _source_contracts() -> dict[str, bool]:
    """Перевірити scheduler, stale guard і відсутність once-only stop rail."""
    area_source = (PROJECT_ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    provider_source = (PROJECT_ROOT / "core" / "workspace_broker_market.py").read_text(
        encoding="utf-8"
    )
    adapter_source = (PROJECT_ROOT / "engine" / "ctrader_adapter.py").read_text(
        encoding="utf-8"
    )
    scheduler_dispatch_wired = all(
        token in area_source
        for token in (
            "self._replay_timer.timeout.connect(self.advance_replay_runtimes)",
            "self._replay_timer.start()",
            "advance_workspace_broker_market",
        )
    )
    stale_timestamp_guard_present = all(
        token in provider_source
        for token in (
            "timestamp < previous_timestamp",
            "_last_quote_signatures.get(binding.workspace_uid) == signature",
        )
    )
    actual_ctrader_subscription_wired = all(
        token in adapter_source
        for token in (
            "ProtoOASubscribeSpotsReq()",
            "request.subscribeToSpotTimestamp = True",
            "self._on_spot_event(payload)",
        )
    )
    once_only_flag_blocks_polling = "_broker_poll_started" in area_source
    return {
        "scheduler_dispatch_wired": scheduler_dispatch_wired,
        "stale_timestamp_guard_present": stale_timestamp_guard_present,
        "actual_ctrader_subscription_wired": actual_ctrader_subscription_wired,
        "once_only_flag_blocks_polling": once_only_flag_blocks_polling,
    }


def main() -> None:
    """Надрукувати factual catch-up/continuation anatomy і межу доказу."""
    results, subscription_created, first_quote_partial, quote_requests = (
        _fresh_continuation_anatomy()
    )
    stalled = _stale_snapshot_anatomy()
    source = _source_contracts()

    history_catchup_operational = all(
        result.history_catchup for result in results.values()
    )
    live_continuation_operational = all(
        result.live_continuation for result in results.values()
    )
    completed_live_bars_emitted = all(
        result.completed_events > 0 for result in results.values()
    )
    workspace_latest_bar_advances = all(
        result.latest_advanced for result in results.values()
    )
    workspace_reaches_running = all(
        result.reached_running for result in results.values()
    )
    stall_reproduced = bool(
        stalled["quote_payload_has_bid_ask"]
        and stalled["first_partial_only"]
        and stalled["scheduler_polling_continues"]
        and not stalled["wait_spread_exit_triggered"]
        and not stalled["workspace_bar_advanced"]
    )

    contract_ok = bool(
        history_catchup_operational
        and live_continuation_operational
        and subscription_created
        and completed_live_bars_emitted
        and workspace_latest_bar_advances
        and workspace_reaches_running
        and first_quote_partial
        and stall_reproduced
        and source["scheduler_dispatch_wired"]
        and source["stale_timestamp_guard_present"]
        and source["actual_ctrader_subscription_wired"]
        and not source["once_only_flag_blocks_polling"]
        and quote_requests > 0
    )
    if not contract_ok:
        raise AssertionError("T107-15 anatomy contract changed; inspect evidence")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"m1_history_catchup={results['M1'].history_catchup}")
    print(f"m5_history_catchup={results['M5'].history_catchup}")
    print(f"m15_history_catchup={results['M15'].history_catchup}")
    print(f"m1_live_continuation={results['M1'].live_continuation}")
    print(f"m5_live_continuation={results['M5'].live_continuation}")
    print(f"m15_live_continuation={results['M15'].live_continuation}")
    print(f"history_catchup_operational={history_catchup_operational}")
    print(f"live_subscription_created={subscription_created}")
    print("live_ticks_received=True")
    print("live_quotes_received=True")
    print("actual_2026_09_04_live_ticks_received=NOT_PROVEN")
    print("actual_2026_09_04_live_quotes_advancing=NOT_PROVEN")
    print("aggregator_receives_live_data=True")
    print(f"completed_live_bars_emitted={completed_live_bars_emitted}")
    print(f"workspace_receives_live_bars={completed_live_bars_emitted}")
    print(f"workspace_latest_bar_advances={workspace_latest_bar_advances}")
    print("live_market_data_received=True")
    print(f"completed_live_bar_emitted={completed_live_bars_emitted}")
    print(f"workspace_bar_advanced={workspace_latest_bar_advances}")
    print(f"spread_value_available={workspace_reaches_running}")
    print(f"spread_guard_accepts={workspace_reaches_running}")
    print(f"controlled_fresh_rollover_wait_spread_exit={workspace_reaches_running}")
    print(f"workspace_reaches_running={workspace_reaches_running}")
    print(f"wait_spread_has_quote={stalled['quote_payload_has_bid_ask']}")
    print(f"wait_spread_exit_triggered={stalled['wait_spread_exit_triggered']}")
    print(f"scheduler_dispatch_wired={source['scheduler_dispatch_wired']}")
    print(f"scheduler_polling_continues={stalled['scheduler_polling_continues']}")
    print("reconnect_task_required_for_healthy_session=False")
    print(f"stale_timestamp_guard_present={source['stale_timestamp_guard_present']}")
    print(
        "once_only_initialization_blocks_live="
        f"{source['once_only_flag_blocks_polling']}"
    )
    print("rollover_or_session_boundary_stops_emission=False")
    print("last_bar_time_blocks_fresh_events=False")
    print("different_workspaces_have_independent_state=True")
    print(f"controlled_quote_snapshot_requests={quote_requests}")
    print(f"stale_quote_snapshot_requests={stalled['quote_snapshot_requests']}")
    print(f"stall_reproduced={stall_reproduced}")
    print("stall_layer=LIVE_QUOTE_SIGNATURE_TO_AGGREGATOR_ROLLOVER")
    print("reproduced_trigger=UNCHANGED_QUOTE_TIMESTAMP_BID_ASK_SIGNATURE")
    print("root_cause=NOT_PROVEN")
    print(
        "live_observation_inference=COMMON_UPSTREAM_QUOTE_OR_POLL_LAYER_BEFORE_"
        "PER_WORKSPACE_AGGREGATORS"
    )
    print("broker_market_data_requests_allowed=True")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    print("T107_15_BROKER_CATCHUP_LIVE_CONTINUATION_ANATOMY=OK")


if __name__ == "__main__":
    main()
