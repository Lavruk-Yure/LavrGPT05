"""run_t108_05_pre_entry_volatility_choppiness_anatomy_check.py — T108-05.

TEST_ONLY runner запускає незмінений registered current-production Candidate F
Replay окремо для 2025 і 2026 через канонічний T105-18 harness. Для кожної
factual trade він бере completed signal M15 і raw price-action context попередніх
3/5/10 completed M15 bars, повністю доступних до factual entry.

Volatility anatomy нормує signal та mean historical ranges factual 1R і
порівнює signal range з historical means. Choppiness anatomy рахує зміни знаку
directional close-to-close moves, median body/range, absolute net path efficiency
та середній overlap сусідніх ranges. Previous windows виключають signal bar;
N direction changes використовують N close-to-close moves і тому N+1 causal
closes. Overlap fraction ділить overlap width на менший range пари.

Post-entry data не читаються як feature: factual WIN/LOSS/BE є лише outcome
labels. Runner не створює ATR, ADX, Choppiness Index, indicator, filter, exit чи
threshold і не виконує sweep/optimization. Conservative stable verdict вимагає,
щоб більше половини predeclared metrics підтримали очікуваний choppiness
direction в обох періодах і жодна metric не змінила LOSS-vs-WIN direction між
2025 та 2026. Друкуються count, mean, median, Q1, Q3 та factual rows 13 LOSS.
"""

from __future__ import annotations

import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_10_pd_35_production_regression_check import (  # noqa: E402
    PeriodSpec,
)
from run_t105_15_stochastic_entry_anatomy_check import (  # noqa: E402
    _production_hashes,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (  # noqa: E402, E501
    EXPECTATIONS,
    PERIODS,
    _broker_execution_attempted,
    _run_period,
)
from run_t108_01_residual_loss_post_entry_path_anatomy_check import (  # noqa: E402, E501
    EPSILON,
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    OUTCOMES,
    _outcome,
)

from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T108-05"
MODE = "RM108_T108_05_PRE_ENTRY_VOLATILITY_CHOPPINESS_ANATOMY_TEST_ONLY"
M15_MINUTES = 15
WINDOWS = (3, 5, 10)
HIGHER = "HIGHER"
LOWER = "LOWER"
EQUAL = "EQUAL"
PRE_ENTRY_CHOPPINESS_PATTERN_PRESENT = "PRE_ENTRY_CHOPPINESS_PATTERN_PRESENT"
PRE_ENTRY_CHOPPINESS_PATTERN_NOT_STABLE = (
    "PRE_ENTRY_CHOPPINESS_PATTERN_NOT_STABLE_CROSS_PERIOD"
)


@dataclass(frozen=True, slots=True)
class PreEntryChoppinessRow:
    """Raw pre-entry volatility/choppiness anatomy однієї factual trade."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    signal_bar_range_r: float
    previous_3_m15_mean_range_r: float
    previous_5_m15_mean_range_r: float
    previous_10_m15_mean_range_r: float
    signal_range_vs_prev_3_mean: float
    signal_range_vs_prev_5_mean: float
    signal_range_vs_prev_10_mean: float
    previous_3_m15_direction_changes: int
    previous_5_m15_direction_changes: int
    previous_10_m15_direction_changes: int
    previous_3_m15_body_to_range_median: float
    previous_5_m15_body_to_range_median: float
    previous_10_m15_body_to_range_median: float
    previous_3_m15_net_move_to_sum_range: float
    previous_5_m15_net_move_to_sum_range: float
    previous_10_m15_net_move_to_sum_range: float
    overlap_ratio_prev_3: float
    overlap_ratio_prev_5: float


@dataclass(frozen=True, slots=True)
class NumericStats:
    """Descriptive numeric statistics без threshold selection."""

    count: int
    mean: float
    median: float
    q1: float
    q3: float


NUMERIC_FEATURES = (
    "signal_bar_range_r",
    "previous_3_m15_mean_range_r",
    "previous_5_m15_mean_range_r",
    "previous_10_m15_mean_range_r",
    "signal_range_vs_prev_3_mean",
    "signal_range_vs_prev_5_mean",
    "signal_range_vs_prev_10_mean",
    "previous_3_m15_direction_changes",
    "previous_5_m15_direction_changes",
    "previous_10_m15_direction_changes",
    "previous_3_m15_body_to_range_median",
    "previous_5_m15_body_to_range_median",
    "previous_10_m15_body_to_range_median",
    "previous_3_m15_net_move_to_sum_range",
    "previous_5_m15_net_move_to_sum_range",
    "previous_10_m15_net_move_to_sum_range",
    "overlap_ratio_prev_3",
    "overlap_ratio_prev_5",
)
EXPECTED_DIRECTIONS = {
    "signal_bar_range_r": HIGHER,
    "previous_3_m15_mean_range_r": HIGHER,
    "previous_5_m15_mean_range_r": HIGHER,
    "previous_10_m15_mean_range_r": HIGHER,
    "signal_range_vs_prev_3_mean": HIGHER,
    "signal_range_vs_prev_5_mean": HIGHER,
    "signal_range_vs_prev_10_mean": HIGHER,
    "previous_3_m15_direction_changes": HIGHER,
    "previous_5_m15_direction_changes": HIGHER,
    "previous_10_m15_direction_changes": HIGHER,
    "previous_3_m15_body_to_range_median": LOWER,
    "previous_5_m15_body_to_range_median": LOWER,
    "previous_10_m15_body_to_range_median": LOWER,
    "previous_3_m15_net_move_to_sum_range": LOWER,
    "previous_5_m15_net_move_to_sum_range": LOWER,
    "previous_10_m15_net_move_to_sum_range": LOWER,
    "overlap_ratio_prev_3": HIGHER,
    "overlap_ratio_prev_5": HIGHER,
}


def _previous_window(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    count: int,
) -> tuple[WorkspaceMarketEvent, ...]:
    """Вибрати count completed M15 строго перед signal bar."""

    assert count in WINDOWS and signal_index >= count
    selected = events[signal_index - count:signal_index]
    assert len(selected) == count
    return selected


def _mean_range_r(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    """Нормувати mean raw M15 range factual stop distance 1R."""

    assert trade.stop_loss_distance > 0.0
    return statistics.fmean(event.high - event.low for event in events) / (
        trade.stop_loss_distance
    )


def _direction_changes(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> int:
    """Порахувати зміни знаку серед N directional close-to-close moves."""

    assert len(events) >= 3
    direction = 1.0 if trade.direction == "BUY" else -1.0
    signs: list[int] = []
    for previous, current in zip(events, events[1:]):
        move = (current.close - previous.close) * direction
        if move > EPSILON:
            signs.append(1)
        elif move < -EPSILON:
            signs.append(-1)
        else:
            signs.append(0)
    return sum(
        previous != 0 and current != 0 and previous != current
        for previous, current in zip(signs, signs[1:])
    )


def _body_to_range_median(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """Повернути median absolute body/range raw M15 window."""

    ratios: list[float] = []
    for event in events:
        width = event.high - event.low
        assert width > 0.0
        ratios.append(abs(event.close - event.open) / width)
    return statistics.median(ratios)


def _net_move_to_sum_range(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """Виміряти absolute net path efficiency відносно суми ranges."""

    total_range = sum(event.high - event.low for event in events)
    assert total_range > 0.0
    net_move = abs(events[-1].close - events[0].open)
    return net_move / total_range


def _overlap_ratio(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """Усереднити overlap width як частку меншого range сусідньої пари."""

    ratios: list[float] = []
    for previous, current in zip(events, events[1:]):
        previous_range = previous.high - previous.low
        current_range = current.high - current.low
        denominator = min(previous_range, current_range)
        assert denominator > 0.0
        overlap = max(
            0.0,
            min(previous.high, current.high) - max(previous.low, current.low),
        )
        ratios.append(overlap / denominator)
    assert ratios
    return statistics.fmean(ratios)


def _build_row(
    period: str,
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> PreEntryChoppinessRow:
    """Обчислити raw causal volatility/choppiness features однієї trade."""

    signal = events[signal_index]
    expected_entry = signal.timestamp + timedelta(minutes=M15_MINUTES)
    assert signal.timestamp == trade.signal_timestamp
    assert trade.entry_timestamp == expected_entry
    assert signal_index >= max(WINDOWS) + 1
    windows = {
        count: _previous_window(events, signal_index, count)
        for count in WINDOWS
    }
    direction_windows = {
        count: events[signal_index - count - 1:signal_index]
        for count in WINDOWS
    }
    assert all(len(direction_windows[count]) == count + 1 for count in WINDOWS)
    causal_events = events[:signal_index + 1]
    assert all(
        event.timestamp + timedelta(minutes=M15_MINUTES) <= trade.entry_timestamp
        for event in causal_events
    )
    signal_range = signal.high - signal.low
    assert signal_range > 0.0 and trade.stop_loss_distance > 0.0
    mean_ranges = {
        count: statistics.fmean(event.high - event.low for event in window)
        for count, window in windows.items()
    }
    assert all(value > 0.0 for value in mean_ranges.values())
    return PreEntryChoppinessRow(
        period=period,
        trade=trade,
        outcome=_outcome(trade),
        signal_bar_range_r=signal_range / trade.stop_loss_distance,
        previous_3_m15_mean_range_r=_mean_range_r(trade, windows[3]),
        previous_5_m15_mean_range_r=_mean_range_r(trade, windows[5]),
        previous_10_m15_mean_range_r=_mean_range_r(trade, windows[10]),
        signal_range_vs_prev_3_mean=signal_range / mean_ranges[3],
        signal_range_vs_prev_5_mean=signal_range / mean_ranges[5],
        signal_range_vs_prev_10_mean=signal_range / mean_ranges[10],
        previous_3_m15_direction_changes=_direction_changes(
            trade,
            direction_windows[3],
        ),
        previous_5_m15_direction_changes=_direction_changes(
            trade,
            direction_windows[5],
        ),
        previous_10_m15_direction_changes=_direction_changes(
            trade,
            direction_windows[10],
        ),
        previous_3_m15_body_to_range_median=_body_to_range_median(windows[3]),
        previous_5_m15_body_to_range_median=_body_to_range_median(windows[5]),
        previous_10_m15_body_to_range_median=_body_to_range_median(windows[10]),
        previous_3_m15_net_move_to_sum_range=_net_move_to_sum_range(windows[3]),
        previous_5_m15_net_move_to_sum_range=_net_move_to_sum_range(windows[5]),
        previous_10_m15_net_move_to_sum_range=_net_move_to_sum_range(
            windows[10]
        ),
        overlap_ratio_prev_3=_overlap_ratio(windows[3]),
        overlap_ratio_prev_5=_overlap_ratio(windows[5]),
    )


def _run_anatomy_period(spec: PeriodSpec) -> tuple[PreEntryChoppinessRow, ...]:
    """Запустити canonical Replay і побудувати causal pre-entry rows."""

    runtime, _, broker_requests = _run_period(spec)
    assert broker_requests == 0
    assert not _broker_execution_attempted(runtime)
    session = runtime.replay_session
    execution = runtime.replay_execution
    summary = runtime.historical_summary
    assert session is not None and session.completed
    assert execution is not None and summary is not None
    events = session.events
    assert all(event.timeframe == "M15" for event in events)
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    assert len(event_index) == len(events)
    rows = tuple(
        _build_row(
            spec.code,
            trade,
            events,
            event_index[trade.signal_timestamp],
        )
        for trade in execution.trade_diagnostics()
    )
    expected = EXPECTATIONS[spec.code]
    counts = Counter(row.outcome for row in rows)
    assert len(rows) == expected.trades == summary.opened_trades
    assert (
        counts[OUTCOME_WIN],
        counts[OUTCOME_LOSS],
        counts[OUTCOME_BREAK_EVEN],
    ) == (expected.wins, expected.losses, expected.break_even)
    return rows


def _selected(
    rows: tuple[PreEntryChoppinessRow, ...],
    outcome: str,
) -> tuple[PreEntryChoppinessRow, ...]:
    """Вибрати одну factual outcome population."""

    selected = tuple(row for row in rows if row.outcome == outcome)
    assert selected
    return selected


def _feature_values(
    rows: tuple[PreEntryChoppinessRow, ...],
    feature: str,
) -> tuple[float, ...]:
    """Витягти finite numeric feature values однієї population."""

    values: list[float] = []
    for row in rows:
        value = getattr(row, feature)
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        number = float(value)
        assert math.isfinite(number)
        values.append(number)
    assert values
    return tuple(values)


def _numeric_stats(values: tuple[float, ...]) -> NumericStats:
    """Порахувати mean/median/inclusive Q1/Q3 без optimization."""

    assert values
    if len(values) == 1:
        q1 = q3 = values[0]
    else:
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        q1, q3 = quartiles[0], quartiles[2]
    return NumericStats(
        count=len(values),
        mean=statistics.fmean(values),
        median=statistics.median(values),
        q1=q1,
        q3=q3,
    )


def _print_statistics(
    period: str,
    rows: tuple[PreEntryChoppinessRow, ...],
) -> None:
    """Надрукувати однакові numeric stats WIN/LOSS/BE."""

    for outcome in OUTCOMES:
        population = _selected(rows, outcome)
        print(f"STATS_{period}_{outcome}")
        for feature in NUMERIC_FEATURES:
            stats = _numeric_stats(_feature_values(population, feature))
            print(
                f"  {feature}=count:{stats.count},mean:{stats.mean:+.6f},"
                f"median:{stats.median:+.6f},q1:{stats.q1:+.6f},"
                f"q3:{stats.q3:+.6f}"
            )


def _median_direction(
    losses: tuple[PreEntryChoppinessRow, ...],
    wins: tuple[PreEntryChoppinessRow, ...],
    feature: str,
) -> str:
    """Повернути factual LOSS-vs-WIN median direction."""

    loss_median = statistics.median(_feature_values(losses, feature))
    win_median = statistics.median(_feature_values(wins, feature))
    if loss_median > win_median + EPSILON:
        return HIGHER
    if loss_median < win_median - EPSILON:
        return LOWER
    return EQUAL


def _period_directions(
    rows: tuple[PreEntryChoppinessRow, ...],
) -> dict[str, str]:
    """Повернути factual median directions усіх choppiness metrics."""

    losses = _selected(rows, OUTCOME_LOSS)
    wins = _selected(rows, OUTCOME_WIN)
    return {
        feature: _median_direction(losses, wins, feature)
        for feature in NUMERIC_FEATURES
    }


def _print_loss_rows(
    rows_by_period: dict[str, tuple[PreEntryChoppinessRow, ...]],
) -> None:
    """Надрукувати compact volatility/choppiness rows усіх 13 LOSS."""

    print("FACTUAL_LOSS_PRE_ENTRY_CHOPPINESS_ROWS")
    print(
        "  period|trade_id/time|side|signal_range_r|mean_range_3_r|"
        "mean_range_5_r|mean_range_10_r|signal_vs_3|signal_vs_5|signal_vs_10|"
        "changes_3|changes_5|changes_10|body_range_3|body_range_5|"
        "body_range_10|efficiency_3|efficiency_5|efficiency_10|"
        "overlap_3|overlap_5"
    )
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            if row.outcome != OUTCOME_LOSS:
                continue
            trade = row.trade
            print(
                f"  {period}|{trade.position_id}/{trade.entry_timestamp.isoformat()}|"
                f"{trade.direction}|{row.signal_bar_range_r:.4f}|"
                f"{row.previous_3_m15_mean_range_r:.4f}|"
                f"{row.previous_5_m15_mean_range_r:.4f}|"
                f"{row.previous_10_m15_mean_range_r:.4f}|"
                f"{row.signal_range_vs_prev_3_mean:.4f}|"
                f"{row.signal_range_vs_prev_5_mean:.4f}|"
                f"{row.signal_range_vs_prev_10_mean:.4f}|"
                f"{row.previous_3_m15_direction_changes}|"
                f"{row.previous_5_m15_direction_changes}|"
                f"{row.previous_10_m15_direction_changes}|"
                f"{row.previous_3_m15_body_to_range_median:.4f}|"
                f"{row.previous_5_m15_body_to_range_median:.4f}|"
                f"{row.previous_10_m15_body_to_range_median:.4f}|"
                f"{row.previous_3_m15_net_move_to_sum_range:.4f}|"
                f"{row.previous_5_m15_net_move_to_sum_range:.4f}|"
                f"{row.previous_10_m15_net_move_to_sum_range:.4f}|"
                f"{row.overlap_ratio_prev_3:.4f}|{row.overlap_ratio_prev_5:.4f}"
            )


def main() -> None:
    """Запустити T108-05 і повернути conservative factual verdict."""

    production_before = _production_hashes()
    rows_by_period = {spec.code: _run_anatomy_period(spec) for spec in PERIODS}
    assert _production_hashes() == production_before

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    for period in ("2025", "2026"):
        rows = rows_by_period[period]
        counts = Counter(row.outcome for row in rows)
        print(f"{period}_trades={len(rows)}")
        print(f"{period}_wins={counts[OUTCOME_WIN]}")
        print(f"{period}_losses={counts[OUTCOME_LOSS]}")
        print(f"{period}_break_even={counts[OUTCOME_BREAK_EVEN]}")
        _print_statistics(period, rows)

    directions = {
        period: _period_directions(rows_by_period[period])
        for period in ("2025", "2026")
    }
    support_both = 0
    contradictions = 0
    for feature in NUMERIC_FEATURES:
        direction_2025 = directions["2025"][feature]
        direction_2026 = directions["2026"][feature]
        expected = EXPECTED_DIRECTIONS[feature]
        supports = direction_2025 == direction_2026 == expected
        contradicts = (
            direction_2025 != EQUAL
            and direction_2026 != EQUAL
            and direction_2025 != direction_2026
        )
        support_both += supports
        contradictions += contradicts
        print(f"expected_direction_{feature}={expected}")
        print(f"median_direction_2025_{feature}={direction_2025}")
        print(f"median_direction_2026_{feature}={direction_2026}")
        print(f"cross_period_support_{feature}={supports}")
        print(f"cross_period_contradiction_{feature}={contradicts}")
    majority_required = len(NUMERIC_FEATURES) // 2 + 1
    stable = support_both >= majority_required and contradictions == 0
    verdict = (
        PRE_ENTRY_CHOPPINESS_PATTERN_PRESENT
        if stable
        else PRE_ENTRY_CHOPPINESS_PATTERN_NOT_STABLE
    )
    print(f"stable_supporting_metrics={support_both}/{len(NUMERIC_FEATURES)}")
    print(f"stable_majority_required={majority_required}")
    print(f"cross_period_contradictory_metrics={contradictions}")
    print(
        "stable_pattern_rule=EXPECTED_DIRECTION_IN_BOTH_PERIODS_FOR_MAJORITY_"
        "AND_ZERO_CROSS_PERIOD_CONTRADICTIONS"
    )
    print(f"verdict={verdict}")
    print("previous_windows_exclude_signal_bar=True")
    print("direction_change_moves=N_CLOSE_TO_CLOSE_MOVES_FROM_N_PLUS_1_BARS")
    print("flat_close_to_close_moves_ignored=True")
    print("net_move_to_sum_range_semantics=ABSOLUTE_PATH_EFFICIENCY")
    print("overlap_ratio_semantics=OVERLAP_WIDTH_DIVIDED_BY_SMALLER_PAIR_RANGE")
    print("canonical_atr_adx_choppiness_indicator_used=False")
    print("completed_m15_before_entry_only=True")
    print("lookahead_used=False")
    print("post_entry_bars_used=False")
    print("factual_outcome_used_as_label_only=True")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("new_indicator_created=False")
    print("new_entry_filter_created=False")
    print("alternative_exit_simulated=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    _print_loss_rows(rows_by_period)
    print("T108_05_PRE_ENTRY_VOLATILITY_CHOPPINESS_ANATOMY=OK")


if __name__ == "__main__":
    main()
