"""run_t108_03_signal_bar_terminal_m1_momentum_anatomy_check.py — T108-03.

TEST_ONLY runner запускає незмінений registered current-production Candidate F
Replay окремо для 2025 і 2026 через канонічний T105-18 harness. Для кожної
factual trade він знаходить completed signal M15 і рівно 15 constituent
completed M1 bars від signal timestamp включно до factual entry виключно.
Відновлений M1 OHLC додатково звіряється з factual signal M15.

Price-action anatomy нормує directional M15 return і terminal returns останніх
1/2/3/5 M1 тим самим factual 1R, рахує aligned bars, causal close location,
порівнює terminal three-bar momentum з попередніми дванадцятьма M1 та позначає
описовий reversal усередині signal bar. Жодний M1 на entry або після entry не
потрапляє у feature set; post-entry outcomes використовуються лише для
групування factual WIN, LOSS і BREAK_EVEN.

Runner не створює indicator, entry-filter, threshold або alternative exit і не
виконує sweep/optimization. Conservative cross-period verdict вимагає, щоб усі
наперед визначені terminal weakness features мали нижчу LOSS median за WIN і в
2025, і в 2026; будь-яка суперечність повертає NOT_STABLE. Для всіх numeric
features друкуються count, mean, median, Q1 і Q3, окремо — factual rows 13 LOSS,
production hashes, completed-bar causality та broker-safety markers.
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
    _execution_events,
    _outcome,
)

from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T108-03"
MODE = "RM108_T108_03_SIGNAL_BAR_TERMINAL_M1_MOMENTUM_ANATOMY_TEST_ONLY"
EXPECTED_CONSTITUENT_M1 = 15
TERMINAL_WINDOWS = (1, 2, 3, 5)
MOMENTUM_WEAKER = "WEAKER"
MOMENTUM_STRONGER = "STRONGER"
MOMENTUM_EQUAL = "EQUAL"
LOSS_LT_WIN = "LOSS_LT_WIN"
LOSS_GE_WIN = "LOSS_GE_WIN"
SIGNAL_TERMINAL_WEAKNESS_PRESENT = "SIGNAL_TERMINAL_WEAKNESS_PRESENT"
SIGNAL_TERMINAL_WEAKNESS_NOT_STABLE = (
    "SIGNAL_TERMINAL_WEAKNESS_NOT_STABLE_CROSS_PERIOD"
)


@dataclass(frozen=True, slots=True)
class SignalTerminalRow:
    """Causal terminal-M1 anatomy однієї factual production trade."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    signal_m15_signed_return_r: float
    terminal_m1_signed_return_r: float
    terminal_2_m1_net_r: float
    terminal_3_m1_net_r: float
    terminal_5_m1_net_r: float
    terminal_3_aligned_count: int
    terminal_5_aligned_count: int
    terminal_last_m1_aligned: bool
    signal_m15_close_location: float
    directional_close_location: float
    earlier_signal_segment_net_r: float
    terminal_minus_earlier_r: float
    terminal_to_earlier_ratio: float | None
    terminal_momentum_vs_earlier_momentum: str
    reversal_inside_signal_bar: bool


@dataclass(frozen=True, slots=True)
class NumericStats:
    """Descriptive statistics однієї numeric feature без tuning."""

    count: int
    mean: float
    median: float
    q1: float
    q3: float


NUMERIC_FEATURES = (
    "signal_m15_signed_return_r",
    "terminal_m1_signed_return_r",
    "terminal_2_m1_net_r",
    "terminal_3_m1_net_r",
    "terminal_5_m1_net_r",
    "terminal_3_aligned_count",
    "terminal_5_aligned_count",
    "signal_m15_close_location",
    "directional_close_location",
    "earlier_signal_segment_net_r",
    "terminal_minus_earlier_r",
    "terminal_to_earlier_ratio",
)
WEAKNESS_FEATURES = (
    "terminal_m1_signed_return_r",
    "terminal_2_m1_net_r",
    "terminal_3_m1_net_r",
    "terminal_5_m1_net_r",
    "terminal_3_aligned_count",
    "terminal_5_aligned_count",
    "directional_close_location",
    "terminal_minus_earlier_r",
)


def _direction(trade: WorkspaceHistoricalTradeDiagnostic) -> float:
    """Повернути +1 для BUY і -1 для SELL."""

    assert trade.direction in {"BUY", "SELL"}
    return 1.0 if trade.direction == "BUY" else -1.0


def _signed_return_r(
    trade: WorkspaceHistoricalTradeDiagnostic,
    start_price: float,
    end_price: float,
) -> float:
    """Нормувати directional price move factual stop distance одного trade."""

    assert trade.stop_loss_distance > 0.0
    return (
        (end_price - start_price)
        * _direction(trade)
        / trade.stop_loss_distance
    )


def _constituent_m1(
    trade: WorkspaceHistoricalTradeDiagnostic,
    m1_by_timestamp: dict[datetime, WorkspaceMarketEvent],
) -> tuple[WorkspaceMarketEvent, ...]:
    """Вибрати рівно 15 completed M1 signal bucket до factual entry."""

    expected_entry = trade.signal_timestamp + timedelta(minutes=15)
    assert trade.entry_timestamp == expected_entry
    timestamps = tuple(
        trade.signal_timestamp + timedelta(minutes=minute)
        for minute in range(EXPECTED_CONSTITUENT_M1)
    )
    events = tuple(m1_by_timestamp[timestamp] for timestamp in timestamps)
    assert len(events) == EXPECTED_CONSTITUENT_M1
    assert all(event.timeframe == "M1" for event in events)
    assert all(event.timestamp < trade.entry_timestamp for event in events)
    assert events[-1].timestamp + timedelta(minutes=1) == trade.entry_timestamp
    return events


def _assert_signal_matches_constituents(
    signal: WorkspaceMarketEvent,
    events: tuple[WorkspaceMarketEvent, ...],
) -> None:
    """Звірити factual M15 OHLC з causal constituent M1 aggregation."""

    assert signal.timeframe == "M15"
    assert signal.timestamp == events[0].timestamp
    comparisons = (
        (signal.open, events[0].open),
        (signal.high, max(event.high for event in events)),
        (signal.low, min(event.low for event in events)),
        (signal.close, events[-1].close),
    )
    assert all(
        math.isclose(actual, expected, rel_tol=0.0, abs_tol=EPSILON)
        for actual, expected in comparisons
    )


def _terminal_net_r(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    count: int,
) -> float:
    """Повернути directional net move останніх count constituent M1."""

    assert 1 <= count <= len(events)
    terminal = events[-count:]
    return _signed_return_r(trade, terminal[0].open, terminal[-1].close)


def _aligned_count(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> int:
    """Порахувати M1 closes, спрямовані у бік майбутнього trade."""

    return sum(
        _signed_return_r(trade, event.open, event.close) > EPSILON
        for event in events
    )


def _momentum_comparison(terminal: float, earlier: float) -> str:
    """Описати terminal momentum відносно earlier signal segment."""

    if terminal < earlier - EPSILON:
        return MOMENTUM_WEAKER
    if terminal > earlier + EPSILON:
        return MOMENTUM_STRONGER
    return MOMENTUM_EQUAL


def _build_row(
    period: str,
    trade: WorkspaceHistoricalTradeDiagnostic,
    signal: WorkspaceMarketEvent,
    events: tuple[WorkspaceMarketEvent, ...],
) -> SignalTerminalRow:
    """Обчислити causal terminal price-action features однієї trade."""

    _assert_signal_matches_constituents(signal, events)
    signal_return = _signed_return_r(trade, signal.open, signal.close)
    terminal_values = {
        count: _terminal_net_r(trade, events, count)
        for count in TERMINAL_WINDOWS
    }
    terminal_three = terminal_values[3]
    earlier = _signed_return_r(trade, events[0].open, events[-4].close)
    difference = terminal_three - earlier
    ratio = (
        terminal_three / earlier
        if abs(earlier) > EPSILON
        else None
    )
    signal_range = signal.high - signal.low
    assert signal_range > 0.0
    close_location = (signal.close - signal.low) / signal_range
    assert -EPSILON <= close_location <= 1.0 + EPSILON
    directional_location = (
        close_location if trade.direction == "BUY" else 1.0 - close_location
    )
    last_m1_return = _signed_return_r(
        trade,
        events[-1].open,
        events[-1].close,
    )
    return SignalTerminalRow(
        period=period,
        trade=trade,
        outcome=_outcome(trade),
        signal_m15_signed_return_r=signal_return,
        terminal_m1_signed_return_r=last_m1_return,
        terminal_2_m1_net_r=terminal_values[2],
        terminal_3_m1_net_r=terminal_three,
        terminal_5_m1_net_r=terminal_values[5],
        terminal_3_aligned_count=_aligned_count(trade, events[-3:]),
        terminal_5_aligned_count=_aligned_count(trade, events[-5:]),
        terminal_last_m1_aligned=last_m1_return > EPSILON,
        signal_m15_close_location=close_location,
        directional_close_location=directional_location,
        earlier_signal_segment_net_r=earlier,
        terminal_minus_earlier_r=difference,
        terminal_to_earlier_ratio=ratio,
        terminal_momentum_vs_earlier_momentum=_momentum_comparison(
            terminal_three,
            earlier,
        ),
        reversal_inside_signal_bar=(
            signal_return > EPSILON and terminal_three < -EPSILON
        ),
    )


def _run_anatomy_period(spec: PeriodSpec) -> tuple[SignalTerminalRow, ...]:
    """Запустити canonical Replay і побудувати causal pre-entry anatomy."""

    runtime, _, broker_requests = _run_period(spec)
    assert broker_requests == 0
    assert not _broker_execution_attempted(runtime)
    session = runtime.replay_session
    execution = runtime.replay_execution
    summary = runtime.historical_summary
    assert session is not None and session.completed
    assert execution is not None and summary is not None
    m1_events = _execution_events(runtime)
    m1_by_timestamp = {event.timestamp: event for event in m1_events}
    assert len(m1_by_timestamp) == len(m1_events)
    signals = {event.timestamp: event for event in session.events}
    rows = tuple(
        _build_row(
            spec.code,
            trade,
            signals[trade.signal_timestamp],
            _constituent_m1(trade, m1_by_timestamp),
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


def _feature_values(
    rows: tuple[SignalTerminalRow, ...],
    feature: str,
) -> tuple[float, ...]:
    """Витягти наявні finite numeric values без заміни missing ratio."""

    values: list[float] = []
    for row in rows:
        value = getattr(row, feature)
        if value is None:
            continue
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        number = float(value)
        assert math.isfinite(number)
        values.append(number)
    assert values
    return tuple(values)


def _numeric_stats(values: tuple[float, ...]) -> NumericStats:
    """Порахувати mean/median/inclusive quartiles однієї population."""

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


def _selected(
    rows: tuple[SignalTerminalRow, ...],
    outcome: str,
) -> tuple[SignalTerminalRow, ...]:
    """Вибрати одну factual outcome population."""

    selected = tuple(row for row in rows if row.outcome == outcome)
    assert selected
    return selected


def _print_statistics(
    period: str,
    rows: tuple[SignalTerminalRow, ...],
) -> None:
    """Надрукувати однакові numeric stats WIN/LOSS/BE populations."""

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
        comparison = Counter(
            row.terminal_momentum_vs_earlier_momentum for row in population
        )
        print(
            "  terminal_momentum_vs_earlier_momentum="
            f"WEAKER:{comparison[MOMENTUM_WEAKER]},"
            f"STRONGER:{comparison[MOMENTUM_STRONGER]},"
            f"EQUAL:{comparison[MOMENTUM_EQUAL]}"
        )
        print(
            "  terminal_last_m1_aligned="
            f"true:{sum(row.terminal_last_m1_aligned for row in population)},"
            f"false:{sum(not row.terminal_last_m1_aligned for row in population)}"
        )
        print(
            "  reversal_inside_signal_bar="
            f"true:{sum(row.reversal_inside_signal_bar for row in population)},"
            f"false:{sum(not row.reversal_inside_signal_bar for row in population)}"
        )


def _median_direction(
    losses: tuple[SignalTerminalRow, ...],
    wins: tuple[SignalTerminalRow, ...],
    feature: str,
) -> str:
    """Порівняти LOSS і WIN medians без threshold optimization."""

    loss_median = statistics.median(_feature_values(losses, feature))
    win_median = statistics.median(_feature_values(wins, feature))
    return LOSS_LT_WIN if loss_median < win_median - EPSILON else LOSS_GE_WIN


def _period_weakness_directions(
    rows: tuple[SignalTerminalRow, ...],
) -> dict[str, str]:
    """Повернути predeclared terminal weakness directions одного періоду."""

    losses = _selected(rows, OUTCOME_LOSS)
    wins = _selected(rows, OUTCOME_WIN)
    return {
        feature: _median_direction(losses, wins, feature)
        for feature in WEAKNESS_FEATURES
    }


def _print_loss_rows(
    rows_by_period: dict[str, tuple[SignalTerminalRow, ...]],
) -> None:
    """Надрукувати compact causal terminal anatomy усіх 13 LOSS."""

    print("FACTUAL_LOSS_SIGNAL_TERMINAL_ROWS")
    print(
        "  period|trade_id/time|side|signal_m15_r|terminal_1_r|terminal_2_r|"
        "terminal_3_r|terminal_5_r|aligned_3|aligned_5|last_aligned|"
        "close_location|directional_close_location|earlier_r|"
        "terminal_minus_earlier_r|terminal_to_earlier_ratio|momentum_vs_earlier|"
        "reversal_inside_signal_bar"
    )
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            if row.outcome != OUTCOME_LOSS:
                continue
            ratio = (
                "NONE"
                if row.terminal_to_earlier_ratio is None
                else f"{row.terminal_to_earlier_ratio:+.4f}"
            )
            trade = row.trade
            print(
                f"  {period}|{trade.position_id}/{trade.entry_timestamp.isoformat()}|"
                f"{trade.direction}|{row.signal_m15_signed_return_r:+.4f}|"
                f"{row.terminal_m1_signed_return_r:+.4f}|"
                f"{row.terminal_2_m1_net_r:+.4f}|"
                f"{row.terminal_3_m1_net_r:+.4f}|"
                f"{row.terminal_5_m1_net_r:+.4f}|"
                f"{row.terminal_3_aligned_count}|{row.terminal_5_aligned_count}|"
                f"{row.terminal_last_m1_aligned}|"
                f"{row.signal_m15_close_location:.4f}|"
                f"{row.directional_close_location:.4f}|"
                f"{row.earlier_signal_segment_net_r:+.4f}|"
                f"{row.terminal_minus_earlier_r:+.4f}|{ratio}|"
                f"{row.terminal_momentum_vs_earlier_momentum}|"
                f"{row.reversal_inside_signal_bar}"
            )


def main() -> None:
    """Запустити T108-03 і повернути conservative factual verdict."""

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
        period: _period_weakness_directions(rows_by_period[period])
        for period in ("2025", "2026")
    }
    for feature in WEAKNESS_FEATURES:
        print(f"median_direction_2025_{feature}={directions['2025'][feature]}")
        print(f"median_direction_2026_{feature}={directions['2026'][feature]}")
    stable = all(
        directions[period][feature] == LOSS_LT_WIN
        for period in ("2025", "2026")
        for feature in WEAKNESS_FEATURES
    )
    verdict = (
        SIGNAL_TERMINAL_WEAKNESS_PRESENT
        if stable
        else SIGNAL_TERMINAL_WEAKNESS_NOT_STABLE
    )
    print(
        "stable_pattern_rule=ALL_PREDECLARED_TERMINAL_WEAKNESS_FEATURES_"
        "LOSS_MEDIAN_LT_WIN_IN_2025_AND_2026"
    )
    print(f"verdict={verdict}")
    print("completed_signal_m15_only=True")
    print("constituent_m1_count_per_signal=15")
    print("constituent_m1_completed_before_entry_only=True")
    print("post_entry_bars_used=False")
    print("lookahead_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("new_indicator_created=False")
    print("new_entry_filter_created=False")
    print("alternative_exit_simulated=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    _print_loss_rows(rows_by_period)
    print("T108_03_SIGNAL_BAR_TERMINAL_M1_MOMENTUM_ANATOMY=OK")


if __name__ == "__main__":
    main()
