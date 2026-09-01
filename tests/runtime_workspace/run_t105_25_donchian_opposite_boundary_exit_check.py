"""run_t105_25_donchian_opposite_boundary_exit_check.py — модуль T105-25.

TEST_ONLY runner перевіряє єдиний post-entry scenario на фактичній current
production population Candidate F після Stochastic 14/1/3 CURRENT_BAR reject:
BUY закривається, коли completed M15 close нижчий за previous Lower20, а SELL —
коли close вищий за previous Upper20. Baseline/runtime harness, paired metrics,
entry identity та broker-safety assertions повторно використовуються з T105-24.

Donchian N20/Shift=0 для bar t обчислюється тільки з completed M15 bars
[t-20, t); current bar і future bars до reference не входять. Production M1
hard SL/TP та незмінний PD обробляються до structural exit на завершенні M15
bar. Runner друкує aggregate comparison, attribution, row-level boundary events
і timing, але не змінює production wiring, entry logic, PD, SL/TP або recovery.
PASS підтверджує лише валідність TEST_ONLY paired experiment і не означає
productionize.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from run_t105_24_donchian_exit_structure_check import (  # noqa: E402
    DONCHIAN_EXIT_REASON,
    DONCHIAN_PERIOD,
    DONCHIAN_SHIFT,
    EPSILON,
    EXPECTATIONS,
    M15_DELTA,
    PERIODS,
    PairedTrade,
    _average_hold_minutes,
    _broker_execution_attempted,
    _completed_bars_before_close,
    _donchian_exit_price,
    _event_index_by_timestamp,
    _metrics,
    _paired_diagnostic,
    _production_hashes,
    _reason_count,
    _run_period,
    _summary_text,
)

TEST_ID = "T105-25"
MODE = "RM105_T105_25_DONCHIAN_OPPOSITE_BOUNDARY_EXIT_TEST_ONLY"


@dataclass(frozen=True, slots=True)
class DonchianBoundaryExitEvent:
    """Row-level diagnostic одного causal opposite-boundary exit."""

    entry_timestamp: datetime
    exit_timestamp: datetime
    side: str
    boundary: float
    donchian_exit_price: float
    baseline_close_reason: str
    baseline_pnl: float
    donchian_pnl: float
    pnl_delta: float
    bars_after_entry: int
    m15_bars_before_baseline_close: int


def _previous_boundaries(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
) -> tuple[float, float] | None:
    """Повернути previous Upper20/Lower20 без current або future bars."""
    if index < DONCHIAN_PERIOD:
        return None
    current = events[index]
    reference_start = index - DONCHIAN_PERIOD
    reference = events[reference_start:index]
    assert len(reference) == DONCHIAN_PERIOD
    assert all(event.timeframe == "M15" for event in reference)
    assert all(event.timestamp < current.timestamp for event in reference)
    assert current not in reference
    upper = max(float(event.high) for event in reference)
    lower = min(float(event.low) for event in reference)
    return upper, lower


def _opposite_boundary_break(
    event: WorkspaceMarketEvent,
    side: str,
    upper: float,
    lower: float,
) -> bool:
    """Перевірити єдине T105-25 opposite-boundary правило."""
    if side == "BUY":
        return float(event.close) < lower
    assert side == "SELL"
    return float(event.close) > upper


def _boundary_for_side(side: str, upper: float, lower: float) -> float:
    """Повернути adverse boundary, релевантну напряму угоди."""
    if side == "BUY":
        return lower
    assert side == "SELL"
    return upper


def _paired_trade(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    index_by_timestamp: dict[datetime, int],
) -> PairedTrade:
    """Застосувати causal opposite-boundary exit до незмінної entry."""
    entry_index = index_by_timestamp[trade.entry_timestamp]
    baseline_bars = _completed_bars_before_close(
        events,
        entry_index,
        trade.close_timestamp,
    )

    for index in range(entry_index, len(events)):
        event = events[index]
        completed_at: datetime = event.timestamp + M15_DELTA
        if completed_at > trade.close_timestamp:
            break
        boundaries = _previous_boundaries(events, index)
        if boundaries is None:
            continue
        upper, lower = boundaries
        if not _opposite_boundary_break(
            event,
            trade.direction,
            upper,
            lower,
        ):
            continue
        close_price = _donchian_exit_price(event, trade.direction)
        direction = 1.0 if trade.direction == "BUY" else -1.0
        pnl = (close_price - trade.entry_price) * trade.volume * direction
        return PairedTrade(
            baseline=trade,
            close_timestamp=completed_at,
            close_price=close_price,
            close_reason=DONCHIAN_EXIT_REASON,
            pnl=pnl,
            holding_seconds=(completed_at - trade.entry_timestamp).total_seconds(),
            donchian_event_index=index,
            bars_after_entry=index - entry_index + 1,
            baseline_bars_before_close=baseline_bars,
        )

    return PairedTrade(
        baseline=trade,
        close_timestamp=trade.close_timestamp,
        close_price=trade.close_price,
        close_reason=trade.close_reason,
        pnl=trade.final_profit,
        holding_seconds=trade.holding_seconds,
        donchian_event_index=None,
        bars_after_entry=None,
        baseline_bars_before_close=baseline_bars,
    )


def _exit_events(
    rows: tuple[PairedTrade, ...],
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[DonchianBoundaryExitEvent, ...]:
    """Матеріалізувати boundary та paired facts усіх Donchian exits."""
    result: list[DonchianBoundaryExitEvent] = []
    for row in rows:
        event_index = row.donchian_event_index
        if event_index is None:
            continue
        assert row.bars_after_entry is not None
        boundaries = _previous_boundaries(events, event_index)
        assert boundaries is not None
        upper, lower = boundaries
        event = events[event_index]
        assert _opposite_boundary_break(
            event,
            row.baseline.direction,
            upper,
            lower,
        )
        result.append(
            DonchianBoundaryExitEvent(
                entry_timestamp=row.baseline.entry_timestamp,
                exit_timestamp=row.close_timestamp,
                side=row.baseline.direction,
                boundary=_boundary_for_side(
                    row.baseline.direction,
                    upper,
                    lower,
                ),
                donchian_exit_price=row.close_price,
                baseline_close_reason=row.baseline.close_reason,
                baseline_pnl=row.baseline.final_profit,
                donchian_pnl=row.pnl,
                pnl_delta=row.pnl - row.baseline.final_profit,
                bars_after_entry=row.bars_after_entry,
                m15_bars_before_baseline_close=row.baseline_bars_before_close,
            )
        )
    return tuple(result)


def _baseline_rows(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    index_by_timestamp: dict[datetime, int],
) -> tuple[PairedTrade, ...]:
    """Побудувати незмінні factual rows у форматі paired harness."""
    return tuple(
        PairedTrade(
            baseline=trade,
            close_timestamp=trade.close_timestamp,
            close_price=trade.close_price,
            close_reason=trade.close_reason,
            pnl=trade.final_profit,
            holding_seconds=trade.holding_seconds,
            donchian_event_index=None,
            bars_after_entry=None,
            baseline_bars_before_close=_completed_bars_before_close(
                events,
                index_by_timestamp[trade.entry_timestamp],
                trade.close_timestamp,
            ),
        )
        for trade in trades
    )


def _print_period(spec) -> None:
    """Запустити baseline, boundary variant та assertions одного period."""
    runtime, _rejects, broker_requests = _run_period(spec)
    engine = runtime.replay_execution
    session = runtime.replay_session
    summary = runtime.historical_summary
    assert engine is not None and session is not None and summary is not None
    assert session.completed and broker_requests == 0
    assert not _broker_execution_attempted(runtime)

    baseline_trades = engine.trade_diagnostics()
    events = tuple(session.events)
    index_by_timestamp = _event_index_by_timestamp(events)
    rows = tuple(
        _paired_trade(trade, events, index_by_timestamp) for trade in baseline_trades
    )
    baseline_rows = _baseline_rows(
        baseline_trades,
        events,
        index_by_timestamp,
    )
    baseline_metrics = _metrics(baseline_rows)
    variant_metrics = _metrics(rows)
    paired = _paired_diagnostic(rows)
    exits = _exit_events(rows, events)
    expected = EXPECTATIONS[spec.code]

    assert baseline_metrics.trades == summary.opened_trades == expected.trades
    assert baseline_metrics.profit_factor is not None
    assert summary.profit_factor is not None
    assert math.isclose(
        baseline_metrics.net_profit,
        summary.net_profit,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )
    assert math.isclose(
        baseline_metrics.profit_factor,
        summary.profit_factor,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )
    assert math.isclose(
        baseline_metrics.maximum_drawdown,
        summary.maximum_drawdown,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )
    baseline_entry_count = len(baseline_trades)
    donchian_variant_entry_count = len(rows)
    assert baseline_entry_count == donchian_variant_entry_count
    assert paired.same_entries
    assert paired.donchian_exit_events == len(exits)
    assert (
        paired.unchanged_trades + paired.improved_trades + paired.worsened_trades
        == baseline_entry_count
    )
    assert math.isclose(
        variant_metrics.net_profit - baseline_metrics.net_profit,
        paired.net_paired_delta,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )

    baseline_hold = _average_hold_minutes(baseline_rows)
    variant_hold = _average_hold_minutes(rows)
    pf_delta = (
        "NONE"
        if variant_metrics.profit_factor is None
        else (f"{variant_metrics.profit_factor - baseline_metrics.profit_factor:+.4f}")
    )
    print(f"  period={spec.code}")
    print(f"    BASELINE={_summary_text(baseline_metrics)}")
    print(
        "    DONCHIAN_OPPOSITE_BOUNDARY_EXIT="
        f"{_summary_text(variant_metrics)},"
        f"DONCHIAN_EXIT:{variant_metrics.close_reason_count(DONCHIAN_EXIT_REASON)}"
    )
    print(
        "    DELTA="
        f"net:{variant_metrics.net_profit - baseline_metrics.net_profit:+.2f},"
        f"PF:{pf_delta},"
        "DD:"
        f"{variant_metrics.maximum_drawdown - baseline_metrics.maximum_drawdown:+.2f},"
        f"wins:{variant_metrics.winning_trades - baseline_metrics.winning_trades:+d},"
        f"losses:{variant_metrics.losing_trades - baseline_metrics.losing_trades:+d},"
        f"average_hold_minutes:{variant_hold - baseline_hold:+.2f}"
    )
    print(
        "    PAIRED="
        f"same_entries:{paired.same_entries},"
        f"donchian_exit_events:{paired.donchian_exit_events},"
        f"unchanged_trades:{paired.unchanged_trades},"
        f"improved_trades:{paired.improved_trades},"
        f"worsened_trades:{paired.worsened_trades},"
        f"sum_improved_delta:{paired.sum_improved_delta:+.2f},"
        f"sum_worsened_delta:{paired.sum_worsened_delta:+.2f},"
        f"net_paired_delta:{paired.net_paired_delta:+.2f}"
    )
    print(
        "    PAIRED_BASELINE_REASONS="
        f"improved_from_baseline_SL:{_reason_count(paired.improved_from, 'STOP_LOSS')},"
        "improved_from_baseline_PD:"
        f"{_reason_count(paired.improved_from, 'PROFIT_DRAWDOWN')},"
        "improved_from_baseline_TP:"
        f"{_reason_count(paired.improved_from, 'TAKE_PROFIT')},"
        f"worsened_from_baseline_SL:{_reason_count(paired.worsened_from, 'STOP_LOSS')},"
        "worsened_from_baseline_PD:"
        f"{_reason_count(paired.worsened_from, 'PROFIT_DRAWDOWN')},"
        "worsened_from_baseline_TP:"
        f"{_reason_count(paired.worsened_from, 'TAKE_PROFIT')}"
    )
    for exit_event in exits:
        print(
            "    DONCHIAN_EXIT_EVENT="
            f"entry_timestamp:{exit_event.entry_timestamp.isoformat()},"
            f"exit_timestamp:{exit_event.exit_timestamp.isoformat()},"
            f"side:{exit_event.side},"
            f"boundary:{exit_event.boundary:.5f},"
            f"donchian_exit_price:{exit_event.donchian_exit_price:.5f},"
            f"baseline_close_reason:{exit_event.baseline_close_reason},"
            f"baseline_pnl:{exit_event.baseline_pnl:+.2f},"
            f"donchian_pnl:{exit_event.donchian_pnl:+.2f},"
            f"pnl_delta:{exit_event.pnl_delta:+.2f}"
        )
    timing = [event.bars_after_entry for event in exits]
    baseline_timing = [event.m15_bars_before_baseline_close for event in exits]
    timing_text = (
        "NONE"
        if not timing
        else (
            f"median_bars_after_entry:{statistics.median(timing):.1f},"
            f"min_bars_after_entry:{min(timing)},"
            f"max_bars_after_entry:{max(timing)},"
            "median_M15_bars_before_baseline_close:"
            f"{statistics.median(baseline_timing):.1f}"
        )
    )
    print(f"    DONCHIAN_EXIT_TIMING={timing_text}")
    print(
        "    ENTRY_IDENTITY="
        f"baseline_entry_count:{baseline_entry_count},"
        f"donchian_variant_entry_count:{donchian_variant_entry_count}"
    )


def main() -> None:
    """Виконати T105-25 і надрукувати marker лише після повного PASS."""
    production_before = _production_hashes()
    assert DONCHIAN_PERIOD == 20 and DONCHIAN_SHIFT == 0

    print("T105-25 Donchian Opposite Boundary Exit Check")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  scenario=OPPOSITE_BOUNDARY_BREAK_AFTER_ENTRY")
    print("  rule=BUY_CLOSE_LT_PREVIOUS_LOWER20__SELL_CLOSE_GT_PREVIOUS_UPPER20")
    print("  donchian_period=20")
    print("  donchian_shift=0")
    for spec in PERIODS:
        _print_period(spec)

    assert _production_hashes() == production_before
    print("  donchian_previous_completed_M15_only=True")
    print("  donchian_current_bar_reference_excluded=True")
    print("  future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  production_entry_logic_changed=False")
    print("  production_stochastic_gate_active=True")
    print("  donchian_entry_gate=False")
    print("  donchian_exit_test_only=True")
    print("  donchian_production_gate=False")
    print("  production_hard_sl_tp_priority_on_same_bar=True")
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_sl_geometry=max(signal_bar_range,spread*10)")
    print("  production_tp_geometry=2R")
    print("  negative_pd_recovery_unchanged=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  pass_does_not_mean_productionize=True")
    print("T105_25_DONCHIAN_OPPOSITE_BOUNDARY_EXIT=OK")


if __name__ == "__main__":
    main()
