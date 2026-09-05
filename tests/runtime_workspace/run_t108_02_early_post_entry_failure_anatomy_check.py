"""run_t108_02_early_post_entry_failure_anatomy_check.py — T108-02.

TEST_ONLY runner запускає незмінений registered current-production Candidate F
Replay окремо для 2025 і 2026 через канонічний T105-18 harness. Factual trade
diagnostics поєднуються з completed M1 execution bars, уже перевіреними
T108-01, щоб описати перші 1, 2, 3 і 5 bars після фактичного entry однаково
для WIN, LOSS і BREAK_EVEN populations.

Для кожного доступного горизонту runner рахує directional close-to-entry
position у R, cumulative favorable/adverse excursions, стан відносно entry та
перевагу adverse excursion. Entry bar є першим completed execution bar. Якщо
trade factual закрита на horizon bar, використовується factual close price;
після close path не продовжується і дальші горизонти явно мають стан
CLOSED_BEFORE_HORIZON.

Post-entry bars використовуються лише як outcome anatomy, не як entry feature.
Runner не створює entry-filter, alternative exit, індикатор, S/R rule або
production threshold, не виконує sweep/optimization і не змінює factual close.
Cross-period verdict має наперед визначене descriptive правило: на horizons
1/3/5 LOSS повинні мати і нижчу median net-R, і більшу below-entry rate за WIN
в кожному періоді; інакше pattern визнається нестабільним. Production hashes,
baseline totals, completed-bar chronology та broker safety перевіряються.
"""

from __future__ import annotations

import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
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
    PROTECTION_CLOSE_REASONS,
    _bar_excursions,
    _close_excursions,
    _execution_events,
    _outcome,
    _trade_events,
)

from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402

TEST_ID = "T108-02"
MODE = "RM108_T108_02_EARLY_POST_ENTRY_FAILURE_ANATOMY_TEST_ONLY"
HORIZONS = (1, 2, 3, 5)
VERDICT_HORIZONS = (1, 3, 5)
AVAILABLE = "AVAILABLE"
CLOSED_BEFORE_HORIZON = "CLOSED_BEFORE_HORIZON"
ABOVE_ENTRY = "ABOVE_ENTRY"
BELOW_ENTRY = "BELOW_ENTRY"
FLAT = "FLAT"
EARLY_FAILURE_PATTERN_PRESENT = "EARLY_FAILURE_PATTERN_PRESENT"
EARLY_FAILURE_PATTERN_NOT_STABLE = (
    "EARLY_FAILURE_PATTERN_NOT_STABLE_CROSS_PERIOD"
)


@dataclass(frozen=True, slots=True)
class HorizonAnatomy:
    """Одна factual trade на фіксованому completed-bar horizon."""

    horizon: int
    status: str
    signed_excursion_r: float | None
    favorable_excursion_r: float | None
    adverse_excursion_r: float | None
    close_position_r: float | None
    entry_state: str
    adverse_ge_favorable: bool | None


@dataclass(frozen=True, slots=True)
class EarlyFailureRow:
    """Ранні completed-bar outcomes однієї factual production trade."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    horizons: tuple[HorizonAnatomy, ...]
    first_positive_bar: int | None
    first_negative_bar: int | None
    first_bar_direction_relative_to_trade: str

    def horizon(self, bar_count: int) -> HorizonAnatomy:
        """Повернути snapshot заданого predeclared horizon."""

        matches = tuple(item for item in self.horizons if item.horizon == bar_count)
        assert len(matches) == 1
        return matches[0]


def _position_r(
    trade: WorkspaceHistoricalTradeDiagnostic,
    price: float,
) -> float:
    """Обчислити directional mark-to-market position у factual risk units."""

    direction = 1.0 if trade.direction == "BUY" else -1.0
    risk = trade.stop_loss_distance * trade.volume
    assert risk > 0.0
    profit = (price - trade.entry_price) * trade.volume * direction
    return profit / risk


def _entry_state(value: float) -> str:
    """Класифікувати close point як above, below або flat до entry."""

    if value > EPSILON:
        return ABOVE_ENTRY
    if value < -EPSILON:
        return BELOW_ENTRY
    return FLAT


def _endpoint_price(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> float:
    """Повернути factual close price на trade close bar або bar close."""

    if event.timestamp == trade.close_timestamp:
        return trade.close_price
    return event.close


def _available_horizon(
    trade: WorkspaceHistoricalTradeDiagnostic,
    selected: tuple[WorkspaceMarketEvent, ...],
    horizon: int,
) -> HorizonAnatomy:
    """Обчислити cumulative excursions і endpoint на доступному horizon."""

    prefix = selected[:horizon]
    assert len(prefix) == horizon
    maximum_favorable = 0.0
    maximum_adverse = 0.0
    for event in prefix:
        protected_close = (
            event.timestamp == trade.close_timestamp
            and trade.close_reason in PROTECTION_CLOSE_REASONS
        )
        if protected_close:
            favorable, adverse = _close_excursions(trade)
        else:
            favorable, adverse = _bar_excursions(trade, event)
            if event.timestamp == trade.close_timestamp:
                close_favorable, close_adverse = _close_excursions(trade)
                favorable = max(favorable, close_favorable)
                adverse = min(adverse, close_adverse)
        maximum_favorable = max(maximum_favorable, favorable)
        maximum_adverse = min(maximum_adverse, adverse)

    risk = trade.stop_loss_distance * trade.volume
    assert risk > 0.0
    favorable_r = maximum_favorable / risk
    adverse_r = -maximum_adverse / risk
    endpoint_r = _position_r(trade, _endpoint_price(trade, prefix[-1]))
    signed_excursion_r = endpoint_r
    assert math.isclose(
        signed_excursion_r,
        endpoint_r,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )
    return HorizonAnatomy(
        horizon=horizon,
        status=AVAILABLE,
        signed_excursion_r=signed_excursion_r,
        favorable_excursion_r=favorable_r,
        adverse_excursion_r=adverse_r,
        close_position_r=endpoint_r,
        entry_state=_entry_state(endpoint_r),
        adverse_ge_favorable=adverse_r + EPSILON >= favorable_r,
    )


def _closed_horizon(horizon: int) -> HorizonAnatomy:
    """Позначити horizon, який лежить строго після factual close."""

    return HorizonAnatomy(
        horizon=horizon,
        status=CLOSED_BEFORE_HORIZON,
        signed_excursion_r=None,
        favorable_excursion_r=None,
        adverse_excursion_r=None,
        close_position_r=None,
        entry_state=CLOSED_BEFORE_HORIZON,
        adverse_ge_favorable=None,
    )


def _build_row(
    period: str,
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    timestamps: tuple[datetime, ...],
) -> EarlyFailureRow:
    """Побудувати predeclared early horizons однієї factual trade."""

    selected = _trade_events(trade, events, timestamps)
    snapshots = tuple(
        _available_horizon(trade, selected, horizon)
        if len(selected) >= horizon
        else _closed_horizon(horizon)
        for horizon in HORIZONS
    )

    first_positive_bar: int | None = None
    first_negative_bar: int | None = None
    first_direction = FLAT
    for bar_number, event in enumerate(selected, start=1):
        position_r = _position_r(trade, _endpoint_price(trade, event))
        state = _entry_state(position_r)
        if bar_number == 1:
            first_direction = state
        if first_positive_bar is None and state == ABOVE_ENTRY:
            first_positive_bar = bar_number
        if first_negative_bar is None and state == BELOW_ENTRY:
            first_negative_bar = bar_number

    return EarlyFailureRow(
        period=period,
        trade=trade,
        outcome=_outcome(trade),
        horizons=snapshots,
        first_positive_bar=first_positive_bar,
        first_negative_bar=first_negative_bar,
        first_bar_direction_relative_to_trade=first_direction,
    )


def _run_anatomy_period(spec: PeriodSpec) -> tuple[EarlyFailureRow, ...]:
    """Запустити canonical Replay та отримати early rows усіх trades."""

    runtime, _, broker_requests = _run_period(spec)
    assert broker_requests == 0
    assert not _broker_execution_attempted(runtime)
    execution = runtime.replay_execution
    summary = runtime.historical_summary
    assert execution is not None and summary is not None
    events = _execution_events(runtime)
    timestamps = tuple(event.timestamp for event in events)
    rows = tuple(
        _build_row(spec.code, trade, events, timestamps)
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
    rows: tuple[EarlyFailureRow, ...],
    outcome: str,
) -> tuple[EarlyFailureRow, ...]:
    """Вибрати одну factual outcome population."""

    selected = tuple(row for row in rows if row.outcome == outcome)
    assert selected
    return selected


def _available_values(
    rows: tuple[EarlyFailureRow, ...],
    horizon: int,
) -> tuple[float, ...]:
    """Повернути endpoint R лише для trades, живих до horizon включно."""

    collected: list[float] = []
    for row in rows:
        snapshot = row.horizon(horizon)
        if snapshot.status != AVAILABLE:
            continue
        assert snapshot.close_position_r is not None
        collected.append(snapshot.close_position_r)
    values = tuple(collected)
    assert values
    return values


def _below_entry_counts(
    rows: tuple[EarlyFailureRow, ...],
    horizon: int,
) -> tuple[int, int, int]:
    """Порахувати below, available і closed-before для одного horizon."""

    snapshots = tuple(row.horizon(horizon) for row in rows)
    available = tuple(item for item in snapshots if item.status == AVAILABLE)
    closed = len(snapshots) - len(available)
    below = sum(item.entry_state == BELOW_ENTRY for item in available)
    assert len(available) + closed == len(rows)
    return below, len(available), closed


def _print_required_summary(
    period: str,
    rows: tuple[EarlyFailureRow, ...],
) -> None:
    """Надрукувати below-entry counts і net-R medians WIN проти LOSS."""

    for outcome in (OUTCOME_LOSS, OUTCOME_WIN):
        population = _selected(rows, outcome)
        label = outcome.lower()
        for horizon in HORIZONS:
            below, available, closed = _below_entry_counts(population, horizon)
            suffix = "bar" if horizon == 1 else "bars"
            print(
                f"{period}_{label}_below_entry_after_{horizon}_{suffix}={below}"
            )
            print(
                f"{period}_{label}_available_after_{horizon}_{suffix}={available}"
            )
            print(
                f"{period}_{label}_closed_before_{horizon}_{suffix}={closed}"
            )
        for horizon in VERDICT_HORIZONS:
            median = statistics.median(_available_values(population, horizon))
            suffix = "bar" if horizon == 1 else "bars"
            print(
                f"{period}_{label}_first_{horizon}_{suffix}_net_r_median="
                f"{median:.4f}"
            )


def _optional_median(values: tuple[int, ...]) -> str:
    """Надрукувати median first-event bar або NONE для порожньої group."""

    if not values:
        return "NONE"
    return f"{statistics.median(values):g}"


def _print_outcome_comparison(
    period: str,
    rows: tuple[EarlyFailureRow, ...],
) -> None:
    """Порівняти WIN/LOSS/BE всіма замовленими horizon metrics."""

    print(f"OUTCOME_COMPARISON_{period}")
    for outcome in OUTCOMES:
        population = _selected(rows, outcome)
        label = outcome.lower()
        directions = Counter(
            row.first_bar_direction_relative_to_trade for row in population
        )
        positive_bars: list[int] = []
        negative_bars: list[int] = []
        for row in population:
            if row.first_positive_bar is not None:
                positive_bars.append(row.first_positive_bar)
            if row.first_negative_bar is not None:
                negative_bars.append(row.first_negative_bar)
        first_positive = tuple(positive_bars)
        first_negative = tuple(negative_bars)
        print(
            f"  {label}_first_bar_direction="
            f"above:{directions[ABOVE_ENTRY]},below:{directions[BELOW_ENTRY]},"
            f"flat:{directions[FLAT]}"
        )
        print(
            f"  {label}_first_positive_bar_median="
            f"{_optional_median(first_positive)},"
            f"none:{len(population) - len(first_positive)}"
        )
        print(
            f"  {label}_first_negative_bar_median="
            f"{_optional_median(first_negative)},"
            f"none:{len(population) - len(first_negative)}"
        )
        for horizon in HORIZONS:
            snapshots = tuple(
                row.horizon(horizon)
                for row in population
                if row.horizon(horizon).status == AVAILABLE
            )
            if not snapshots:
                print(
                    f"  {label}_after_{horizon}=available:0,"
                    f"closed_before:{len(population)},metrics:NONE"
                )
                continue
            signed: list[float] = []
            favorable: list[float] = []
            adverse: list[float] = []
            close_positions: list[float] = []
            for snapshot in snapshots:
                assert snapshot.signed_excursion_r is not None
                assert snapshot.favorable_excursion_r is not None
                assert snapshot.adverse_excursion_r is not None
                assert snapshot.close_position_r is not None
                signed.append(snapshot.signed_excursion_r)
                favorable.append(snapshot.favorable_excursion_r)
                adverse.append(snapshot.adverse_excursion_r)
                close_positions.append(snapshot.close_position_r)
            states = Counter(snapshot.entry_state for snapshot in snapshots)
            adverse_dominant = sum(
                snapshot.adverse_ge_favorable is True for snapshot in snapshots
            )
            closed = len(population) - len(snapshots)
            print(
                f"  {label}_after_{horizon}=available:{len(snapshots)},"
                f"closed_before:{closed},signed_r_median:"
                f"{statistics.median(signed):+.4f},favorable_r_median:"
                f"{statistics.median(favorable):.4f},adverse_r_median:"
                f"{statistics.median(adverse):.4f},close_position_r_median:"
                f"{statistics.median(close_positions):+.4f},"
                f"above:{states[ABOVE_ENTRY]},below:{states[BELOW_ENTRY]},"
                f"flat:{states[FLAT]},adverse_ge_favorable:{adverse_dominant}"
            )


def _optional_bar(value: int | None) -> str:
    """Надрукувати first-event bar або явне NONE."""

    return "NONE" if value is None else str(value)


def _horizon_text(item: HorizonAnatomy) -> str:
    """Стиснути один horizon для per-trade audit row."""

    if item.status == CLOSED_BEFORE_HORIZON:
        return CLOSED_BEFORE_HORIZON
    assert item.signed_excursion_r is not None
    assert item.favorable_excursion_r is not None
    assert item.adverse_excursion_r is not None
    assert item.close_position_r is not None
    return (
        f"signed:{item.signed_excursion_r:+.4f},"
        f"fav:{item.favorable_excursion_r:.4f},"
        f"adv:{item.adverse_excursion_r:.4f},"
        f"close:{item.close_position_r:+.4f},"
        f"state:{item.entry_state},adv_ge_fav:{item.adverse_ge_favorable}"
    )


def _print_trade_rows(
    rows_by_period: dict[str, tuple[EarlyFailureRow, ...]],
) -> None:
    """Надрукувати однакову compact anatomy для всіх factual trades."""

    print("FACTUAL_EARLY_POST_ENTRY_ROWS")
    print(
        "  period|trade_id/time|outcome|side|first_positive_bar|"
        "first_negative_bar|first_bar_direction|after_1|after_2|after_3|after_5"
    )
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            trade = row.trade
            horizon_text = "|".join(
                _horizon_text(row.horizon(horizon)) for horizon in HORIZONS
            )
            print(
                f"  {period}|{trade.position_id}/{trade.entry_timestamp.isoformat()}|"
                f"{row.outcome}|{trade.direction}|"
                f"{_optional_bar(row.first_positive_bar)}|"
                f"{_optional_bar(row.first_negative_bar)}|"
                f"{row.first_bar_direction_relative_to_trade}|{horizon_text}"
            )


def _period_pattern(rows: tuple[EarlyFailureRow, ...]) -> bool:
    """Застосувати predeclared directional separation rule одного періоду."""

    losses = _selected(rows, OUTCOME_LOSS)
    wins = _selected(rows, OUTCOME_WIN)
    for horizon in VERDICT_HORIZONS:
        loss_values = _available_values(losses, horizon)
        win_values = _available_values(wins, horizon)
        loss_below, loss_available, _ = _below_entry_counts(losses, horizon)
        win_below, win_available, _ = _below_entry_counts(wins, horizon)
        median_separated = (
            statistics.median(loss_values) + EPSILON
            < statistics.median(win_values)
        )
        rate_separated = (
            loss_below / loss_available
            > win_below / win_available + EPSILON
        )
        if not median_separated or not rate_separated:
            return False
    return True


def main() -> None:
    """Запустити T108-02 і повернути factual cross-period verdict."""

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
        _print_required_summary(period, rows)
        _print_outcome_comparison(period, rows)

    period_patterns = {
        period: _period_pattern(rows_by_period[period])
        for period in ("2025", "2026")
    }
    pattern_stable = all(period_patterns.values())
    verdict = (
        EARLY_FAILURE_PATTERN_PRESENT
        if pattern_stable
        else EARLY_FAILURE_PATTERN_NOT_STABLE
    )
    print(f"early_failure_pattern_2025={period_patterns['2025']}")
    print(f"early_failure_pattern_2026={period_patterns['2026']}")
    print(
        "verdict_rule=LOSS_MEDIAN_NET_LT_WIN_AND_LOSS_BELOW_RATE_GT_WIN_"
        "AT_1_3_5_IN_EACH_PERIOD"
    )
    print(f"verdict={verdict}")
    print("entry_bar_is_first_completed_execution_bar=True")
    print("closed_trade_extended_after_close=False")
    print("post_entry_bars_used_for_outcome_anatomy_only=True")
    print("new_entry_filter_created=False")
    print("alternative_exit_simulated=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("new_indicator_created=False")
    print("support_resistance_used=False")
    print("completed_market_events_only=True")
    print("lookahead_used=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    _print_trade_rows(rows_by_period)
    print("T108_02_EARLY_POST_ENTRY_FAILURE_ANATOMY=OK")


if __name__ == "__main__":
    main()
