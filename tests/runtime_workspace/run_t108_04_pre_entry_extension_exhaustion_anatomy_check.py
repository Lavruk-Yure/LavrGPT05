"""run_t108_04_pre_entry_extension_exhaustion_anatomy_check.py — T108-04.

TEST_ONLY runner запускає незмінений registered current-production Candidate F
Replay окремо для 2025 і 2026 через канонічний T105-18 harness. Для кожної
factual trade він бере completed signal M15 та causal sequence попередніх
completed M15 bars, доступних не пізніше factual entry, і описує pre-entry
directional move на фіксованих windows 1/2/3/5.

Anatomy нормує moves та fixed-window range extension factual stop distance 1R,
вимірює directional close location, consecutive directional bars, signal range
відносно median попередніх п'яти M15 і cumulative move відносно signal range.
Endpoint усіх price features — close завершеного signal M15; factual entry
timestamp лише доводить доступність даних, а entry price не використовується.
Distance from recent opposite extreme є явним alias fixed 3/5-bar adverse range
extreme, тому runner не створює pivot, support/resistance або інший індикатор.

Post-entry bars використовуються тільки production engine для factual outcome,
але не читаються anatomy logic. Runner не створює filter/exit/threshold і не
виконує sweep/optimization. Conservative verdict вимагає вищу LOSS median за
WIN для всіх наперед визначених extension features одночасно в 2025 і 2026;
будь-яка cross-period суперечність повертає NOT_STABLE. Для numeric features
друкуються count, mean, median, Q1, Q3 та окремі factual rows усіх 13 LOSS.
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
from run_t108_03_signal_bar_terminal_m1_momentum_anatomy_check import (  # noqa: E402, E501
    _signed_return_r,
)

from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T108-04"
MODE = "RM108_T108_04_PRE_ENTRY_EXTENSION_EXHAUSTION_ANATOMY_TEST_ONLY"
M15_MINUTES = 15
WINDOWS = (1, 2, 3, 5)
LOSS_GT_WIN = "LOSS_GT_WIN"
LOSS_LE_WIN = "LOSS_LE_WIN"
PRE_ENTRY_EXTENSION_PATTERN_PRESENT = "PRE_ENTRY_EXTENSION_PATTERN_PRESENT"
PRE_ENTRY_EXTENSION_PATTERN_NOT_STABLE = (
    "PRE_ENTRY_EXTENSION_PATTERN_NOT_STABLE_CROSS_PERIOD"
)


@dataclass(frozen=True, slots=True)
class PreEntryExtensionRow:
    """Causal fixed-window extension anatomy однієї factual trade."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    signed_move_1_m15_r: float
    signed_move_2_m15_r: float
    signed_move_3_m15_r: float
    signed_move_5_m15_r: float
    directional_range_extension_3_m15_r: float
    directional_range_extension_5_m15_r: float
    close_location_in_3_m15_range: float
    close_location_in_5_m15_range: float
    consecutive_directional_m15_count_before_entry: int
    distance_from_recent_opposite_extreme_3_m15_r: float
    distance_from_recent_opposite_extreme_5_m15_r: float
    signal_bar_range_vs_previous_5_median: float
    pre_entry_move_3_m15_vs_signal_range: float
    pre_entry_move_5_m15_vs_signal_range: float


@dataclass(frozen=True, slots=True)
class NumericStats:
    """Descriptive numeric statistics без threshold selection."""

    count: int
    mean: float
    median: float
    q1: float
    q3: float


NUMERIC_FEATURES = (
    "signed_move_1_m15_r",
    "signed_move_2_m15_r",
    "signed_move_3_m15_r",
    "signed_move_5_m15_r",
    "directional_range_extension_3_m15_r",
    "directional_range_extension_5_m15_r",
    "close_location_in_3_m15_range",
    "close_location_in_5_m15_range",
    "consecutive_directional_m15_count_before_entry",
    "distance_from_recent_opposite_extreme_3_m15_r",
    "distance_from_recent_opposite_extreme_5_m15_r",
    "signal_bar_range_vs_previous_5_median",
    "pre_entry_move_3_m15_vs_signal_range",
    "pre_entry_move_5_m15_vs_signal_range",
)
EXTENSION_FEATURES = (
    "signed_move_1_m15_r",
    "signed_move_2_m15_r",
    "signed_move_3_m15_r",
    "signed_move_5_m15_r",
    "directional_range_extension_3_m15_r",
    "directional_range_extension_5_m15_r",
    "close_location_in_3_m15_range",
    "close_location_in_5_m15_range",
    "consecutive_directional_m15_count_before_entry",
    "signal_bar_range_vs_previous_5_median",
    "pre_entry_move_3_m15_vs_signal_range",
    "pre_entry_move_5_m15_vs_signal_range",
)


def _window(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    count: int,
) -> tuple[WorkspaceMarketEvent, ...]:
    """Вибрати count completed M15, завершених не пізніше entry."""

    assert count in WINDOWS and signal_index >= count - 1
    selected = events[signal_index - count + 1 : signal_index + 1]
    assert len(selected) == count
    return selected


def _directional_net_price(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    """Повернути directional open-to-close move M15 sequence у price units."""

    direction = 1.0 if trade.direction == "BUY" else -1.0
    return (events[-1].close - events[0].open) * direction


def _range_extension_r(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    """Виміряти signal close від adverse fixed-window range extreme у R."""

    close = events[-1].close
    if trade.direction == "BUY":
        distance = close - min(event.low for event in events)
    else:
        distance = max(event.high for event in events) - close
    assert distance >= -EPSILON
    return max(distance, 0.0) / trade.stop_loss_distance


def _directional_close_location(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    """Нормувати signal close всередині fixed-window directional range."""

    low = min(event.low for event in events)
    high = max(event.high for event in events)
    width = high - low
    assert width > 0.0
    raw = (events[-1].close - low) / width
    directional = raw if trade.direction == "BUY" else 1.0 - raw
    assert -EPSILON <= directional <= 1.0 + EPSILON
    return min(max(directional, 0.0), 1.0)


def _consecutive_directional_count(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> int:
    """Порахувати безперервні aligned M15 назад від signal bar."""

    count = 0
    for event in reversed(events[: signal_index + 1]):
        signed = _signed_return_r(trade, event.open, event.close)
        if signed <= EPSILON:
            break
        count += 1
    return count


def _build_row(
    period: str,
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
) -> PreEntryExtensionRow:
    """Обчислити causal extension features однієї factual trade."""

    signal = events[signal_index]
    expected_entry = signal.timestamp + timedelta(minutes=M15_MINUTES)
    assert signal.timestamp == trade.signal_timestamp
    assert trade.entry_timestamp == expected_entry
    causal_events = events[: signal_index + 1]
    assert all(
        event.timestamp + timedelta(minutes=M15_MINUTES) <= trade.entry_timestamp
        for event in causal_events
    )
    assert signal_index >= 5
    windows = {count: _window(events, signal_index, count) for count in WINDOWS}
    moves_r = {
        count: _signed_return_r(
            trade,
            window[0].open,
            window[-1].close,
        )
        for count, window in windows.items()
    }
    extension_3 = _range_extension_r(trade, windows[3])
    extension_5 = _range_extension_r(trade, windows[5])
    signal_range = signal.high - signal.low
    assert signal_range > 0.0
    previous_ranges = tuple(
        event.high - event.low for event in events[signal_index - 5 : signal_index]
    )
    assert len(previous_ranges) == 5 and all(value > 0.0 for value in previous_ranges)
    previous_median = statistics.median(previous_ranges)
    assert previous_median > 0.0
    return PreEntryExtensionRow(
        period=period,
        trade=trade,
        outcome=_outcome(trade),
        signed_move_1_m15_r=moves_r[1],
        signed_move_2_m15_r=moves_r[2],
        signed_move_3_m15_r=moves_r[3],
        signed_move_5_m15_r=moves_r[5],
        directional_range_extension_3_m15_r=extension_3,
        directional_range_extension_5_m15_r=extension_5,
        close_location_in_3_m15_range=_directional_close_location(
            trade,
            windows[3],
        ),
        close_location_in_5_m15_range=_directional_close_location(
            trade,
            windows[5],
        ),
        consecutive_directional_m15_count_before_entry=(
            _consecutive_directional_count(trade, events, signal_index)
        ),
        distance_from_recent_opposite_extreme_3_m15_r=extension_3,
        distance_from_recent_opposite_extreme_5_m15_r=extension_5,
        signal_bar_range_vs_previous_5_median=signal_range / previous_median,
        pre_entry_move_3_m15_vs_signal_range=(
            _directional_net_price(trade, windows[3]) / signal_range
        ),
        pre_entry_move_5_m15_vs_signal_range=(
            _directional_net_price(trade, windows[5]) / signal_range
        ),
    )


def _run_anatomy_period(spec: PeriodSpec) -> tuple[PreEntryExtensionRow, ...]:
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
    rows: tuple[PreEntryExtensionRow, ...],
    outcome: str,
) -> tuple[PreEntryExtensionRow, ...]:
    """Вибрати одну factual outcome population."""

    selected = tuple(row for row in rows if row.outcome == outcome)
    assert selected
    return selected


def _feature_values(
    rows: tuple[PreEntryExtensionRow, ...],
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
    rows: tuple[PreEntryExtensionRow, ...],
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
    losses: tuple[PreEntryExtensionRow, ...],
    wins: tuple[PreEntryExtensionRow, ...],
    feature: str,
) -> str:
    """Порівняти LOSS і WIN medians у predeclared extension direction."""

    loss_median = statistics.median(_feature_values(losses, feature))
    win_median = statistics.median(_feature_values(wins, feature))
    return LOSS_GT_WIN if loss_median > win_median + EPSILON else LOSS_LE_WIN


def _period_extension_directions(
    rows: tuple[PreEntryExtensionRow, ...],
) -> dict[str, str]:
    """Повернути extension median directions одного factual періоду."""

    losses = _selected(rows, OUTCOME_LOSS)
    wins = _selected(rows, OUTCOME_WIN)
    return {
        feature: _median_direction(losses, wins, feature)
        for feature in EXTENSION_FEATURES
    }


def _print_loss_rows(
    rows_by_period: dict[str, tuple[PreEntryExtensionRow, ...]],
) -> None:
    """Надрукувати compact pre-entry anatomy усіх 13 factual LOSS."""

    print("FACTUAL_LOSS_PRE_ENTRY_EXTENSION_ROWS")
    print(
        "  period|trade_id/time|side|move_1_r|move_2_r|move_3_r|move_5_r|"
        "extension_3_r|extension_5_r|close_location_3|close_location_5|"
        "consecutive_directional|signal_range_vs_prev5_median|"
        "move_3_vs_signal_range|move_5_vs_signal_range"
    )
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            if row.outcome != OUTCOME_LOSS:
                continue
            trade = row.trade
            print(
                f"  {period}|{trade.position_id}/{trade.entry_timestamp.isoformat()}|"
                f"{trade.direction}|{row.signed_move_1_m15_r:+.4f}|"
                f"{row.signed_move_2_m15_r:+.4f}|"
                f"{row.signed_move_3_m15_r:+.4f}|"
                f"{row.signed_move_5_m15_r:+.4f}|"
                f"{row.directional_range_extension_3_m15_r:.4f}|"
                f"{row.directional_range_extension_5_m15_r:.4f}|"
                f"{row.close_location_in_3_m15_range:.4f}|"
                f"{row.close_location_in_5_m15_range:.4f}|"
                f"{row.consecutive_directional_m15_count_before_entry}|"
                f"{row.signal_bar_range_vs_previous_5_median:.4f}|"
                f"{row.pre_entry_move_3_m15_vs_signal_range:+.4f}|"
                f"{row.pre_entry_move_5_m15_vs_signal_range:+.4f}"
            )


def main() -> None:
    """Запустити T108-04 і повернути conservative factual verdict."""

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
        period: _period_extension_directions(rows_by_period[period])
        for period in ("2025", "2026")
    }
    for feature in EXTENSION_FEATURES:
        print(f"median_direction_2025_{feature}={directions['2025'][feature]}")
        print(f"median_direction_2026_{feature}={directions['2026'][feature]}")
    stable = all(
        directions[period][feature] == LOSS_GT_WIN
        for period in ("2025", "2026")
        for feature in EXTENSION_FEATURES
    )
    verdict = (
        PRE_ENTRY_EXTENSION_PATTERN_PRESENT
        if stable
        else PRE_ENTRY_EXTENSION_PATTERN_NOT_STABLE
    )
    print(
        "stable_pattern_rule=ALL_PREDECLARED_EXTENSION_FEATURES_"
        "LOSS_MEDIAN_GT_WIN_IN_2025_AND_2026"
    )
    print(f"verdict={verdict}")
    print("pre_entry_endpoint=COMPLETED_SIGNAL_M15_CLOSE")
    print("recent_opposite_extreme_metric=FIXED_WINDOW_ADVERSE_RANGE_EXTREME")
    print("distance_metric_alias_matches_range_extension=True")
    print("completed_m15_before_entry_only=True")
    print("lookahead_used=False")
    print("post_entry_bars_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("new_indicator_created=False")
    print("new_entry_filter_created=False")
    print("alternative_exit_simulated=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    _print_loss_rows(rows_by_period)
    print("T108_04_PRE_ENTRY_EXTENSION_EXHAUSTION_ANATOMY=OK")


if __name__ == "__main__":
    main()
