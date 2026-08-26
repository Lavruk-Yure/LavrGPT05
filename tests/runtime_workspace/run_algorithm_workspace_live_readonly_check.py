# -*- coding: utf-8 -*-
"""Runtime check for broker-backed WSP Live Read-only market events."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
    AlgorithmWorkspace,
)
from core.workspace_broker_market import (  # noqa: E402
    RuntimeEngineWorkspaceMarketProvider,
)
from engine.ib_fx_external_exposure import (  # noqa: E402
    IB_FX_GUARD_ALLOWED,
    IBFxExternalExposureGuardDecision,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_LOAD_DATA,
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_WAIT_BROKER,
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
    WorkspaceRuntime,
)


@dataclass(frozen=True, slots=True)
class FakeBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class FakeHistoryResult:
    bars: tuple[FakeBar, ...]


class FakeRuntimeEngine:
    def __init__(self) -> None:
        self.validated: list[tuple[str, str | None]] = []
        self.quote_calls: list[tuple[str, tuple[str, ...]]] = []
        self.execution_attempts = 0
        self._connected = {"CTRADER": True, "IB": True}
        self._quote_index: dict[str, int] = {"CTRADER": 0, "IB": 0}
        self._quotes: dict[str, tuple[tuple[str, float, float], ...]] = {
            "CTRADER": (
                ("2026-07-28T08:30:00Z", 1.17074, 1.17086),
                ("2026-07-28T08:30:00Z", 1.17074, 1.17086),
                ("2026-07-28T08:30:10Z", 1.17080, 1.17092),
                ("2026-07-28T08:45:00Z", 1.17082, 1.17094),
            ),
            "IB": (
                ("2026-07-28T09:30:00Z", 1.35000, 1.35030),
                ("2026-07-28T09:30:01Z", 1.35005, 1.35015),
                ("2026-07-28T09:30:10Z", 1.35008, 1.35018),
            ),
        }

    @staticmethod
    def refresh_ib_fx_external_exposure_guard(
        *,
        account_id: str,
        symbol_name: str,
        runtime_mode: str,
    ) -> IBFxExternalExposureGuardDecision:
        return IBFxExternalExposureGuardDecision(
            allowed=True,
            reason_code=IB_FX_GUARD_ALLOWED,
            reason_text=(
                "Synthetic current IB evidence contains no external exposure: "
                f"account={account_id}, symbol={symbol_name}, "
                f"mode={runtime_mode}"
            ),
        )

    def validate_workspace_broker_binding(
        self,
        broker_name: str,
        account_id: str | None,
    ) -> None:
        if not self.is_named_broker_connected(broker_name):
            raise RuntimeError(f"Workspace broker is not connected: {broker_name}")
        binding = (broker_name, account_id)
        if binding not in {
            ("CTRADER", "46368962"),
            ("IB", "DUM513747"),
        }:
            raise RuntimeError("unexpected broker binding")
        self.validated.append(binding)

    def is_named_broker_connected(self, broker_name: str) -> bool:
        return bool(self._connected.get(str(broker_name).upper(), False))

    def set_connected(self, broker_name: str, connected: bool) -> None:
        self._connected[str(broker_name).upper()] = bool(connected)

    def replace_quotes(
        self,
        broker_name: str,
        rows: tuple[tuple[str, float, float], ...],
    ) -> None:
        broker = str(broker_name).upper()
        self._quotes[broker] = rows
        self._quote_index[broker] = 0

    @staticmethod
    def download_ctrader_historical_bars(**_kwargs) -> FakeHistoryResult:
        return FakeHistoryResult(
            bars=(
                FakeBar(
                    datetime(2026, 7, 28, 8, 0, tzinfo=UTC),
                    1.1698,
                    1.1702,
                    1.1696,
                    1.1700,
                    120.0,
                ),
                FakeBar(
                    datetime(2026, 7, 28, 8, 15, tzinfo=UTC),
                    1.1700,
                    1.1706,
                    1.1699,
                    1.1705,
                    140.0,
                ),
            )
        )

    @staticmethod
    def download_ib_historical_bars(**_kwargs) -> FakeHistoryResult:
        return FakeHistoryResult(
            bars=(
                FakeBar(
                    datetime(2026, 7, 28, 9, 0, tzinfo=UTC),
                    1.3490,
                    1.3496,
                    1.3488,
                    1.3494,
                    0.0,
                ),
                FakeBar(
                    datetime(2026, 7, 28, 9, 15, tzinfo=UTC),
                    1.3494,
                    1.3501,
                    1.3492,
                    1.3499,
                    0.0,
                ),
            )
        )

    def get_workspace_forex_quote_snapshot(
        self,
        broker_name: str,
        symbol_names: list[str],
    ) -> dict:
        broker = broker_name.upper()
        symbols = tuple(sorted(symbol_names))
        self.quote_calls.append((broker, symbols))
        if not symbols:
            return {
                "captured_utc": "2026-07-28T10:00:00Z",
                "complete": True,
                "quotes": {},
                "subscribed_symbols": [],
            }
        rows = self._quotes[broker]
        index = min(self._quote_index[broker], len(rows) - 1)
        timestamp, bid, ask = rows[index]
        self._quote_index[broker] += 1
        quotes = {
            symbol: {
                "symbol_name": symbol,
                "timestamp": timestamp,
                "bid": bid,
                "ask": ask,
                "volume": 0.0,
            }
            for symbol in symbols
        }
        return {
            "captured_utc": timestamp,
            "complete": True,
            "quotes": quotes,
            "subscribed_symbols": list(symbols),
        }


def _workspace(
    *,
    broker: str,
    account_id: str,
    symbol: str,
) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker=broker,
        account_id=account_id,
        account_mode="DEMO" if broker == "CTRADER" else "PAPER",
        symbol=symbol,
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
    )


def _start_running_pair() -> tuple[
    FakeRuntimeEngine,
    WorkspaceRuntime,
    WorkspaceRuntime,
]:
    engine = FakeRuntimeEngine()
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    ctrader_runtime = WorkspaceRuntime(
        _workspace(
            broker="CTRADER",
            account_id="46368962",
            symbol="EURUSD",
        ),
        broker_market_provider=provider,
    )
    ib_runtime = WorkspaceRuntime(
        _workspace(
            broker="IB",
            account_id="DUM513747",
            symbol="GBPUSD",
        ),
        broker_market_provider=provider,
    )

    for runtime in (ctrader_runtime, ib_runtime):
        runtime.begin_start()
        runtime.complete_start()

    assert ctrader_runtime.advance_broker_market() is not None
    assert ctrader_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert ib_runtime.advance_broker_market() is not None
    assert ib_runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert ib_runtime.advance_broker_market() is not None
    assert ib_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    return engine, ctrader_runtime, ib_runtime


def _check_invalid_live_quotes() -> None:
    engine, ctrader_runtime, ib_runtime = _start_running_pair()
    chart_before = ctrader_runtime.chart_snapshot().events
    current_event_before = ctrader_runtime.context.current_market_event
    engine.replace_quotes(
        "CTRADER",
        (
            ("2026-07-28T08:30:20Z", 1.17120, 1.17110),
            ("2026-07-28T08:30:21Z", 0.0, 1.17110),
            ("2026-07-28T08:30:22Z", -1.0, 1.17110),
            ("2026-07-28T08:30:23Z", 1.17110, 0.0),
            ("2026-07-28T08:30:24Z", 1.17110, -1.0),
            ("2026-07-28T08:30:20Z", 1.17110, 1.17120),
        ),
    )

    for _ in range(5):
        assert ctrader_runtime.advance_broker_market() is None
        assert ctrader_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
        assert ctrader_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
        assert ctrader_runtime.context.last_error is None
        assert ctrader_runtime.context.current_market_event == current_event_before
        assert ctrader_runtime.chart_snapshot().events == chart_before
        assert ctrader_runtime.can_form_signal()

    recovered_event = ctrader_runtime.advance_broker_market()
    assert recovered_event is not None
    assert recovered_event.bid == 1.17110
    assert recovered_event.ask == 1.17120
    assert ctrader_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert ctrader_runtime.chart_snapshot().events != chart_before
    assert not any(entry.event == "RUNTIME_ERROR" for entry in ctrader_runtime.journal)

    ctrader_runtime.begin_stop()
    ctrader_runtime.complete_stop()
    ib_runtime.begin_stop()
    ib_runtime.complete_stop()

    startup_engine = FakeRuntimeEngine()
    startup_engine.replace_quotes(
        "CTRADER",
        (
            ("2026-07-28T08:30:20Z", 1.17120, 1.17110),
            ("2026-07-28T08:30:21Z", 0.0, 1.17110),
            ("2026-07-28T08:30:20Z", 1.17110, 1.17120),
        ),
    )
    startup_provider = RuntimeEngineWorkspaceMarketProvider(startup_engine)
    startup_runtime = WorkspaceRuntime(
        _workspace(
            broker="CTRADER",
            account_id="46368962",
            symbol="EURUSD",
        ),
        broker_market_provider=startup_provider,
    )
    startup_runtime.begin_start()
    startup_runtime.complete_start()
    startup_chart = startup_runtime.chart_snapshot().events
    assert startup_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD

    for _ in range(2):
        assert startup_runtime.advance_broker_market() is None
        assert startup_runtime.context.runtime_state == WORKSPACE_STATE_STARTING
        assert (
            startup_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
        )
        assert startup_runtime.context.last_error is None
        assert startup_runtime.chart_snapshot().events == startup_chart

    assert startup_runtime.advance_broker_market() is not None
    assert startup_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert startup_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
    assert not any(entry.event == "RUNTIME_ERROR" for entry in startup_runtime.journal)
    startup_runtime.begin_stop()
    startup_runtime.complete_stop()


def main() -> None:
    engine = FakeRuntimeEngine()
    provider = RuntimeEngineWorkspaceMarketProvider(engine)
    ctrader_runtime = WorkspaceRuntime(
        _workspace(
            broker="CTRADER",
            account_id="46368962",
            symbol="EURUSD",
        ),
        broker_market_provider=provider,
    )
    ib_runtime = WorkspaceRuntime(
        _workspace(
            broker="IB",
            account_id="DUM513747",
            symbol="GBPUSD",
        ),
        broker_market_provider=provider,
    )

    startup_poll_blocked = True
    for runtime in (ctrader_runtime, ib_runtime):
        runtime.begin_start()
        quote_calls_before = len(engine.quote_calls)
        validated_before = len(engine.validated)
        assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_LOAD_DATA
        assert runtime.advance_broker_market() is None
        assert runtime.context.runtime_state == WORKSPACE_STATE_STARTING
        assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_LOAD_DATA
        assert len(engine.quote_calls) == quote_calls_before
        assert len(engine.validated) == validated_before
        runtime.complete_start()
        assert runtime.context.runtime_state == WORKSPACE_STATE_STARTING
        assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
        assert runtime.context.warmup_bars_processed == 2
        assert runtime.context.market_event_count == 2
        assert len(runtime.chart_snapshot().events) == 2
        assert not runtime.can_form_signal()

    ctrader_event = ctrader_runtime.advance_broker_market()
    assert ctrader_event is not None
    assert ctrader_event.broker == "CTRADER"
    assert ctrader_event.symbol == "EURUSD"
    assert ctrader_event.source_mode == WORKSPACE_DATA_MODE_BROKER
    assert ctrader_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert ctrader_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
    assert ctrader_runtime.can_form_signal()

    ib_wide_event = ib_runtime.advance_broker_market()
    assert ib_wide_event is not None
    assert ib_wide_event.broker == "IB"
    assert ib_wide_event.symbol == "GBPUSD"
    assert ib_runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert not ib_runtime.can_form_signal()
    ib_recovery_event = ib_runtime.advance_broker_market()
    assert ib_recovery_event is not None
    assert ib_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert ib_runtime.can_form_signal()

    duplicate = ctrader_runtime.advance_broker_market()
    assert duplicate is None
    updated = ctrader_runtime.advance_broker_market()
    assert updated is not None
    assert updated.timestamp == ctrader_event.timestamp
    assert updated.high > ctrader_event.high
    assert len(ctrader_runtime.chart_snapshot().events) == 3
    next_bar = ctrader_runtime.advance_broker_market()
    assert next_bar is not None
    assert next_bar.timestamp > updated.timestamp
    assert len(ctrader_runtime.chart_snapshot().events) == 4

    assert engine.validated == [
        ("CTRADER", "46368962"),
        ("IB", "DUM513747"),
    ]
    assert all(
        broker != "CTRADER" or symbols in {("EURUSD",), ()}
        for broker, symbols in engine.quote_calls
    )
    assert all(
        broker != "IB" or symbols == ("GBPUSD",)
        for broker, symbols in engine.quote_calls
    )
    assert engine.execution_attempts == 0

    ctrader_runtime.begin_stop()
    ctrader_runtime.complete_stop()
    assert ctrader_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
    assert ("CTRADER", ()) in engine.quote_calls
    ib_runtime.begin_stop()
    ib_runtime.complete_stop()
    assert ib_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
    assert ("IB", ()) in engine.quote_calls

    ctrader_events = [
        entry for entry in ctrader_runtime.journal if entry.event == "EVENT_ACCEPTED"
    ]
    ib_events = [
        entry for entry in ib_runtime.journal if entry.event == "EVENT_ACCEPTED"
    ]
    assert ctrader_events
    assert ib_events
    assert any(
        entry.event == "LIVE_QUOTE_RECEIVED" for entry in ctrader_runtime.journal
    )
    assert any(entry.event == "LIVE_BAR_OPENED" for entry in ctrader_runtime.journal)
    assert startup_poll_blocked

    first_stop_engine, first_ctrader, first_ib = _start_running_pair()
    first_ctrader.begin_stop()
    first_ctrader.complete_stop()
    assert first_ctrader.context.runtime_state == WORKSPACE_STATE_STOPPED
    ib_calls_before = len(first_stop_engine.quote_calls)
    assert first_ib.advance_broker_market() is not None
    assert first_ib.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert len(first_stop_engine.quote_calls) == ib_calls_before + 1
    assert first_stop_engine.quote_calls[-1] == ("IB", ("GBPUSD",))
    first_ib.begin_stop()
    first_ib.complete_stop()

    second_stop_engine, second_ctrader, second_ib = _start_running_pair()
    second_ib.begin_stop()
    second_ib.complete_stop()
    assert second_ib.context.runtime_state == WORKSPACE_STATE_STOPPED
    ctrader_calls_before = len(second_stop_engine.quote_calls)
    assert second_ctrader.advance_broker_market() is None
    assert second_ctrader.advance_broker_market() is not None
    assert second_ctrader.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert len(second_stop_engine.quote_calls) == ctrader_calls_before + 2
    assert second_stop_engine.quote_calls[-1] == (
        "CTRADER",
        ("EURUSD",),
    )
    second_ctrader.begin_stop()
    second_ctrader.complete_stop()

    reconnect_engine, reconnect_ctrader, reconnect_ib = _start_running_pair()
    reconnect_chart_before = reconnect_ctrader.chart_snapshot().events
    reconnect_algorithm = reconnect_ctrader.algorithm
    reconnect_engine.set_connected("CTRADER", False)
    assert reconnect_ctrader.advance_broker_market() is None
    assert reconnect_ctrader.context.runtime_state == WORKSPACE_STATE_STARTING
    assert (
        reconnect_ctrader.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_BROKER
    )
    assert not reconnect_ctrader.can_form_signal()
    assert reconnect_ctrader.chart_snapshot().events == reconnect_chart_before
    assert reconnect_ctrader.algorithm is reconnect_algorithm
    disconnect_entries = [
        entry
        for entry in reconnect_ctrader.journal
        if entry.event == "BROKER_DISCONNECTED"
    ]
    assert len(disconnect_entries) == 1
    assert reconnect_ctrader.advance_broker_market() is None
    assert (
        len(
            [
                entry
                for entry in reconnect_ctrader.journal
                if entry.event == "BROKER_DISCONNECTED"
            ]
        )
        == 1
    )
    assert reconnect_ib.advance_broker_market() is not None
    assert reconnect_ib.context.runtime_state == WORKSPACE_STATE_RUNNING

    validated_before_reconnect = len(reconnect_engine.validated)
    reconnect_engine.set_connected("CTRADER", True)
    assert reconnect_ctrader.advance_broker_market() is None
    assert (
        reconnect_ctrader.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
    )
    assert len(reconnect_engine.validated) == validated_before_reconnect + 1
    assert reconnect_ctrader.advance_broker_market() is not None
    assert reconnect_ctrader.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert reconnect_ctrader.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
    assert reconnect_ctrader.can_form_signal()
    assert reconnect_ctrader.algorithm is reconnect_algorithm
    reconnect_chart_after = reconnect_ctrader.chart_snapshot().events
    assert len(reconnect_chart_after) >= len(reconnect_chart_before)
    assert reconnect_chart_after[:2] == reconnect_chart_before[:2]
    assert any(
        entry.event == "BROKER_RECONNECTED" for entry in reconnect_ctrader.journal
    )
    assert any(
        entry.event == "MARKET_DATA_RESUBSCRIBED" for entry in reconnect_ctrader.journal
    )
    reconnect_ctrader.begin_stop()
    reconnect_ctrader.complete_stop()
    reconnect_ib.begin_stop()
    reconnect_ib.complete_stop()

    startup_engine = FakeRuntimeEngine()
    startup_engine.set_connected("IB", False)
    startup_provider = RuntimeEngineWorkspaceMarketProvider(startup_engine)
    startup_runtime = WorkspaceRuntime(
        _workspace(
            broker="IB",
            account_id="DUM513747",
            symbol="GBPUSD",
        ),
        broker_market_provider=startup_provider,
    )
    startup_runtime.begin_start()
    startup_runtime.complete_start()
    assert startup_runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert startup_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_BROKER
    assert startup_runtime.algorithm is not None
    assert not startup_runtime.chart_snapshot().events
    startup_engine.set_connected("IB", True)
    assert startup_runtime.advance_broker_market() is not None
    assert startup_runtime.context.warmup_bars_processed == 2
    assert startup_runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert startup_runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
    assert startup_runtime.advance_broker_market() is not None
    assert startup_runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    startup_runtime.begin_stop()
    startup_runtime.complete_stop()

    _check_invalid_live_quotes()

    print("Algorithm Workspace Live Read-only result")
    print("  brokers=CTRADER,IB")
    print("  historical_warmup_bars=2")
    print("  startup_poll_before_complete_blocked=True")
    print("  startup_waits_for_live_spread=True")
    print("  ctrader_running=True")
    print("  ib_wide_spread_blocked=True")
    print("  ib_spread_recovery_running=True")
    print("  duplicate_quote_ignored=True")
    print("  current_bar_replaced=True")
    print("  next_timeframe_bucket_opened=True")
    print("  cross_broker_events_isolated=True")
    print("  broker_execution_attempted=False")
    print("  subscriptions_released_on_stop=True")
    print("  independent_stop_keeps_other_running=True")
    print("  disconnect_enters_wait_broker=True")
    print("  reconnect_revalidates_binding=True")
    print("  reconnect_preserves_chart_and_algorithm=True")
    print("  initial_disconnected_start_waits_for_broker=True")
    print("  market_data_resubscribed_without_duplicates=True")
    print("  invalid_live_quotes_ignored=True")
    print("  invalid_startup_quotes_wait_for_valid_spread=True")
    print("  last_valid_chart_preserved=True")
    print("  invalid_quote_does_not_enter_error=True")
    print("ALGORITHM_WORKSPACE_LIVE_READONLY_CHECK=OK")


if __name__ == "__main__":
    main()
