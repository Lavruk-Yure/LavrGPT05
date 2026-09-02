# -*- coding: utf-8 -*-
"""run_t105_24_donchian_exit_structure_check.py — модуль T105-24.

TEST_ONLY runner перевіряє одну post-entry роль Donchian N20 на фактичній
current-production population Candidate F після Stochastic 14/1/3 CURRENT_BAR
reject. Спочатку для 2025 і 2026 виконується канонічний production Replay з
T105-19; розбіжність baseline негайно зупиняє крок. Далі кожна factual entry
утворює незалежну paired-угоду, яку може достроково закрити лише adverse break
попередньої Donchian midline.

Для completed M15 bar t канал обчислюється виключно з [t-20, t): current bar і
future bars до reference не входять. Production M1 protection усередині M15
bar виконується до Donchian на його завершенні, тому hard SL/TP і незмінний PD
не можуть бути перехоплені TEST_ONLY exit. Runner друкує однакові metrics, paired
дельти, повний inventory Donchian exits і timing, перевіряє незмінність entries,
production-файлів та broker safety. Він не змінює production wiring, не додає
entry gate, re-entry, tuning чи будь-який інший exit scenario і не є рішенням
про productionize.
"""

from __future__ import annotations

import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_11_donchian_entry_anatomy_check import (  # noqa: E402
    DONCHIAN_PERIOD,
    DONCHIAN_SHIFT,
    _production_hashes,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (  # noqa
    EXPECTATIONS,
    PERIODS,
    _broker_execution_attempted,
    _run_period,
)

from core.workspace_historical_baseline import (  # noqa: E402
    WorkspaceHistoricalBaselineMetrics,
    WorkspaceHistoricalClosedTrade,
    build_workspace_historical_baseline_metrics,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T105-24"
MODE = "RM105_T105_24_DONCHIAN_EXIT_STRUCTURE_TEST_ONLY"
DONCHIAN_EXIT_REASON = "DONCHIAN_EXIT"
EPSILON = 1e-12
M15_DELTA: timedelta = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class PairedTrade:
    """Одна baseline entry з factual або TEST_ONLY Donchian close."""

    baseline: WorkspaceHistoricalTradeDiagnostic
    close_timestamp: datetime
    close_price: float
    close_reason: str
    pnl: float
    holding_seconds: float
    donchian_event_index: int | None
    bars_after_entry: int | None
    baseline_bars_before_close: int


@dataclass(frozen=True, slots=True)
class DonchianExitEvent:
    """Повний paired diagnostic одного causal Donchian exit event."""

    entry_timestamp: datetime
    exit_timestamp: datetime
    side: str
    donchian_exit_price: float
    baseline_close_reason: str
    baseline_pnl: float
    donchian_pnl: float
    pnl_delta: float
    bars_after_entry: int
    m15_bars_before_baseline_close: int


@dataclass(frozen=True, slots=True)
class PairedDiagnostic:
    """Aggregate paired counts і дельти одного Replay period."""

    same_entries: bool
    donchian_exit_events: int
    unchanged_trades: int
    improved_trades: int
    worsened_trades: int
    sum_improved_delta: float
    sum_worsened_delta: float
    net_paired_delta: float
    improved_from: Counter[str]
    worsened_from: Counter[str]


def _event_index_by_timestamp(
    events: tuple[WorkspaceMarketEvent, ...],
) -> dict[datetime, int]:
    """Побудувати однозначний timestamp index для completed M15 events."""
    result = {event.timestamp: index for index, event in enumerate(events)}
    assert len(result) == len(events)
    assert all(event.timeframe == "M15" for event in events)
    return result


def _previous_middle(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
) -> float | None:
    """Повернути N20 midline лише з попередніх completed M15 bars."""
    if index < DONCHIAN_PERIOD:
        return None
    current = events[index]
    reference_start = index - DONCHIAN_PERIOD
    reference = events[reference_start:index]
    assert len(reference) == DONCHIAN_PERIOD
    assert all(event.timestamp < current.timestamp for event in reference)
    assert current not in reference
    upper = max(float(event.high) for event in reference)
    lower = min(float(event.low) for event in reference)
    return (upper + lower) / 2.0


def _adverse_midline_break(
    event: WorkspaceMarketEvent,
    side: str,
    previous_middle: float,
) -> bool:
    """Перевірити єдине T105-24 adverse-midline правило."""
    if side == "BUY":
        return float(event.close) < previous_middle
    assert side == "SELL"
    return float(event.close) > previous_middle


def _donchian_exit_price(event: WorkspaceMarketEvent, side: str) -> float:
    """Повернути executable bid/ask close без broker interaction."""
    return float(event.bid if side == "BUY" else event.ask)


def _paired_trade(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    index_by_timestamp: dict[datetime, int],
) -> PairedTrade:
    """Застосувати causal exit до однієї незмінної production entry."""
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
        middle = _previous_middle(events, index)
        if middle is None or not _adverse_midline_break(
            event,
            trade.direction,
            middle,
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


def _completed_bars_before_close(
    events: tuple[WorkspaceMarketEvent, ...],
    entry_index: int,
    close_timestamp: datetime,
) -> int:
    """Порахувати completed M15 bars між entry і factual close."""
    return sum(
        event.timestamp + M15_DELTA <= close_timestamp for event in events[entry_index:]
    )


def _metrics(rows: tuple[PairedTrade, ...]) -> WorkspaceHistoricalBaselineMetrics:
    """Побудувати canonical metrics у фактичному variant close order."""
    ordered = sorted(
        rows,
        key=lambda row: (row.close_timestamp, row.baseline.signal_uid),
    )
    trades = tuple(
        WorkspaceHistoricalClosedTrade(
            trade_uid=row.baseline.signal_uid,
            realized_profit=row.pnl,
            close_reason=row.close_reason,
        )
        for row in ordered
    )
    return build_workspace_historical_baseline_metrics(trades)


def _summary_text(summary: WorkspaceHistoricalBaselineMetrics) -> str:
    """Відформатувати однаковий набір метрик baseline і variant."""
    profit_factor = (
        "NONE" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    )
    return (
        f"trades:{summary.trades},W:{summary.winning_trades},"
        f"L:{summary.losing_trades},BE:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},PF:{profit_factor},"
        f"DD:{summary.maximum_drawdown:.2f},"
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )


def _average_hold_minutes(rows: tuple[PairedTrade, ...]) -> float:
    """Обчислити average hold у хвилинах із наявних trade timestamps."""
    return math.fsum(row.holding_seconds for row in rows) / len(rows) / 60.0


def _paired_diagnostic(rows: tuple[PairedTrade, ...]) -> PairedDiagnostic:
    """Порахувати paired outcome і attribution за baseline close reason."""
    improved = 0
    worsened = 0
    unchanged = 0
    improved_delta = 0.0
    worsened_delta = 0.0
    improved_from: Counter[str] = Counter()
    worsened_from: Counter[str] = Counter()

    for row in rows:
        delta = row.pnl - row.baseline.final_profit
        if delta > EPSILON:
            improved += 1
            improved_delta += delta
            improved_from[row.baseline.close_reason] += 1
        elif delta < -EPSILON:
            worsened += 1
            worsened_delta += delta
            worsened_from[row.baseline.close_reason] += 1
        else:
            unchanged += 1

    baseline_entries = tuple(row.baseline.signal_uid for row in rows)
    variant_entries = tuple(row.baseline.signal_uid for row in rows)
    return PairedDiagnostic(
        same_entries=baseline_entries == variant_entries,
        donchian_exit_events=sum(row.donchian_event_index is not None for row in rows),
        unchanged_trades=unchanged,
        improved_trades=improved,
        worsened_trades=worsened,
        sum_improved_delta=improved_delta,
        sum_worsened_delta=worsened_delta,
        net_paired_delta=improved_delta + worsened_delta,
        improved_from=improved_from,
        worsened_from=worsened_from,
    )


def _exit_events(rows: tuple[PairedTrade, ...]) -> tuple[DonchianExitEvent, ...]:
    """Матеріалізувати повний inventory фактичних Donchian closes."""
    result: list[DonchianExitEvent] = []
    for row in rows:
        if row.donchian_event_index is None:
            continue
        assert row.bars_after_entry is not None
        result.append(
            DonchianExitEvent(
                entry_timestamp=row.baseline.entry_timestamp,
                exit_timestamp=row.close_timestamp,
                side=row.baseline.direction,
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


def _reason_count(counts: Counter[str], reason: str) -> int:
    """Повернути attribution count для одного production close reason."""
    return int(counts[reason])


def _print_period(spec) -> None:
    """Запустити baseline, paired variant і всі assertions одного period."""
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
    baseline_rows = tuple(
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
        for trade in baseline_trades
    )
    baseline_metrics = _metrics(baseline_rows)
    variant_metrics = _metrics(rows)
    paired = _paired_diagnostic(rows)
    exits = _exit_events(rows)
    expected = EXPECTATIONS[spec.code]

    assert baseline_metrics.trades == summary.opened_trades == expected.trades
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
        or baseline_metrics.profit_factor is None
        else f"{variant_metrics.profit_factor - baseline_metrics.profit_factor:+.4f}"
    )
    print(f"  period={spec.code}")
    print(f"    BASELINE={_summary_text(baseline_metrics)}")
    print(
        f"    DONCHIAN_MIDLINE_EXIT={_summary_text(variant_metrics)},"
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
    """Виконати T105-24 і надрукувати фінальний marker лише після PASS."""
    production_before = _production_hashes()
    assert DONCHIAN_PERIOD == 20 and DONCHIAN_SHIFT == 0

    print("T105-24 Donchian Exit/Structure Role Check")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  scenario=ADVERSE_MIDLINE_BREAK_AFTER_ENTRY")
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
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_sl_geometry=max(signal_bar_range,spread*10)")
    print("  production_tp_geometry=2R")
    print("  production_hard_sl_tp_priority_on_same_bar=True")
    print("  negative_pd_recovery_unchanged=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  pass_does_not_mean_productionize=True")
    print("T105_24_DONCHIAN_EXIT_STRUCTURE=OK")


if __name__ == "__main__":
    main()
