# -*- coding: utf-8 -*-
"""RoadMap115 / T115-07 — швидкість реакції BUY/SELL (TEST_ONLY).

Пари входів і виходів: незмінні T115-02 / T115-03 (33% — гіпотеза).
Дані: завершені M15 із M1 cTrader; профіль Candidate F, без MACD.

Всі сигнали споживають лише поточний completed M15, виконання —
на наступному наявному open. Майбутні піки, швидкості й результати
використовуються ВИКЛЮЧНО як ретроспективні outcome labels.

Швидкості — pips / фактично минулі 15-хвилинні слоти UTC (wall-time),
а не / кількість наявних свічок. Пропуски M15 не домальовуються.
Позитивний close-peak обчислюється лише за ACTIVE close ПІСЛЯ входу.
Перший максимум ACTIVE close використовується для часу до піку;
для 33% реконструюється ПЕРШИЙ фактичний causal trigger і його
ПОТОЧНИЙ running close-peak, без підглядання майбутнього.

Mid OHLC, gross pips, без SL/TP, спреду, комісій, прослизання.
Жодних змін production/MD7, broker_requests=0, жодної оптимізації.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    Bar,
    CANONICAL_2026_END,
    M15,
    PERIODS,
    _aggregate_m1,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    ClosedTrade,
    DIRECTION_DOWN,
    DIRECTION_UP,
    ObservedState,
    PIP,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    EXIT_33_THRESHOLD,
    _simulate_variant,
)
from T115_04_Alligator_Trend_Coverage_Audit_FIXED import (  # noqa: E402
    Observation,
    Trend,
    _trade_index,
    _trends,
)
from T115_06_Alligator_Trend_Exposure_Attribution import (  # noqa: E402
    _audit_exposure,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorRuntimeProfile,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-7
SLOT_SECONDS = int(M15.total_seconds())


@dataclass(frozen=True, slots=True)
class Reaction:
    """Фактично закрита пара; усі швидкості — outcome, не сигнал."""

    direction: str
    entry_at: datetime
    base_pips: float
    rule33_pips: float
    early_33: bool
    gap_affected_pair: bool
    internal_active_gap: bool
    peak_positive: bool
    entry_to_peak_slots: int | None
    peak_gain_pips: float
    runup_pips_per_slot: float | None
    peak_to_ending_slots: int | None
    fade_pips_per_slot: float | None
    peak_to_33_slots: int | None
    giveback_pips_per_slot: float | None
    signal33_to_ending_slots: int | None
    signal33_to_ending_observed: int | None
    exit33_to_base_fill_slots: int | None


@dataclass(frozen=True, slots=True)
class Audit:
    """Повний список пар для однакового порівняння 2025/2026."""

    rows: tuple[Reaction, ...]
    total_trends: int
    entries: int
    no_entry: int
    open_end: int
    base_closed: int
    rule33_closed: int
    active_gap_trends: int


def _slots(start: datetime, end: datetime) -> int:
    """Реальний UTC-час у кратних M15, у тому числі через розриви."""
    delta = (end - start).total_seconds()
    rounded = round(delta / SLOT_SECONDS)
    assert math.isclose(delta, rounded * SLOT_SECONDS, abs_tol=1e-6)
    assert rounded >= 0
    return int(rounded)


def _signed(direction: str) -> int:
    """Нормувати BUY і SELL до однакового сприятливого знаку."""
    assert direction in (DIRECTION_UP, DIRECTION_DOWN)
    return 1 if direction == DIRECTION_UP else -1


def _first_33_trigger(
    steps: list[tuple[Bar, Observation]],
    start_index: int,
    ending_index: int,
    trade: ClosedTrade,
) -> tuple[int, int, float, float]:
    """Реконструювати running-peak і перший 33% сигнал каузально.

    Повертає: signal index, latest new peak index, peak pips,
    поточний close pips. Жодного bar після signal не читає.
    """
    running_peak = 0.0
    peak_index: int | None = None
    sign = _signed(trade.direction)
    for index in range(start_index, ending_index):
        candle, observation = steps[index]
        assert observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        assert observation.available_at == candle.timestamp + M15
        close_pips = sign * (candle.close - trade.entry_price) / PIP
        if close_pips > running_peak:
            running_peak = close_pips
            peak_index = index
        if running_peak > 0 and close_pips <= (
            running_peak * (1 - EXIT_33_THRESHOLD)
        ):
            assert peak_index is not None
            return index, peak_index, running_peak, close_pips
    raise AssertionError(f"EARLY_EXIT_SIGNAL_NOT_FOUND: {trade.entry_at}")


def _one_reaction(
    steps: list[tuple[Bar, Observation]],
    trend: Trend,
    baseline: ClosedTrade,
    variant: ClosedTrade,
) -> Reaction:
    """Аудит лише після завершення пари; торгові правила не змінює."""
    end_index = trend.end_signal_index
    assert end_index is not None
    sign = _signed(trend.direction)
    assert baseline.entry_at == variant.entry_at
    assert baseline.entry_price == variant.entry_price
    assert baseline.direction == variant.direction == trend.direction
    assert baseline.exit_reason == "ENDING"
    end_bar, end_observation = steps[end_index]
    assert end_observation.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING
    assert baseline.exit_at >= end_observation.available_at

    start_index = trend.start_index
    entry_index = start_index + 1
    assert steps[entry_index][0].timestamp == baseline.entry_at
    active = steps[entry_index:end_index]
    segment = steps[start_index:end_index + 1]
    active_gap = any(
        second[0].timestamp != first[0].timestamp + M15
        for first, second in zip(segment, segment[1:])
    )
    positive_peak = False
    best_peak_index: int | None = None
    best_gain = 0.0
    for offset, (candle, _) in enumerate(active):
        gain = sign * (candle.close - baseline.entry_price) / PIP
        if gain > best_gain + EPS:
            positive_peak = True
            best_gain = gain
            best_peak_index = entry_index + offset

    entry_to_peak: int | None = None
    runup_speed: float | None = None
    peak_to_ending: int | None = None
    fade_speed: float | None = None
    if positive_peak:
        assert best_peak_index is not None
        peak_bar = steps[best_peak_index][0]
        entry_to_peak = _slots(baseline.entry_at, peak_bar.timestamp + M15)
        assert entry_to_peak > 0
        runup_speed = best_gain / entry_to_peak
        peak_to_ending = _slots(peak_bar.timestamp, end_bar.timestamp)
        assert peak_to_ending > 0
        ending_close_pips = sign * (
            end_bar.close - baseline.entry_price
        ) / PIP
        fade_speed = max(0.0, best_gain - ending_close_pips) / peak_to_ending

    early = variant.exit_reason == EXIT_33_REASON
    peak_to_33: int | None = None
    giveback_speed: float | None = None
    signal_to_end: int | None = None
    signal_to_end_observed: int | None = None
    fill_to_fill: int | None = None
    if early:
        signal_index, local_peak_index, local_peak, signal_close = (
            _first_33_trigger(steps, entry_index, end_index, variant)
        )
        signal_bar = steps[signal_index][0]
        signal_known_at = steps[signal_index][1].available_at
        assert variant.exit_at >= signal_known_at
        assert variant.exit_at <= baseline.exit_at
        assert steps[signal_index + 1][0].timestamp == variant.exit_at
        assert variant.exit_gap == (variant.exit_at != signal_known_at)
        peak_time = steps[local_peak_index][0].timestamp
        peak_to_33 = _slots(peak_time, signal_bar.timestamp)
        assert peak_to_33 > 0
        giveback_speed = (local_peak - signal_close) / peak_to_33
        signal_to_end = _slots(signal_bar.timestamp, end_bar.timestamp)
        signal_to_end_observed = end_index - signal_index
        fill_to_fill = _slots(variant.exit_at, baseline.exit_at)
        assert signal_to_end > 0
        assert signal_to_end >= signal_to_end_observed
        assert fill_to_fill >= 0
    else:
        assert variant == baseline, "NON_EARLY_TRADE_CHANGED"

    return Reaction(
        direction=trend.direction,
        entry_at=baseline.entry_at,
        base_pips=baseline.pips,
        rule33_pips=variant.pips,
        early_33=early,
        gap_affected_pair=baseline.exit_gap or variant.exit_gap,
        internal_active_gap=active_gap,
        peak_positive=positive_peak,
        entry_to_peak_slots=entry_to_peak,
        peak_gain_pips=best_gain,
        runup_pips_per_slot=runup_speed,
        peak_to_ending_slots=peak_to_ending,
        fade_pips_per_slot=fade_speed,
        peak_to_33_slots=peak_to_33,
        giveback_pips_per_slot=giveback_speed,
        signal33_to_ending_slots=signal_to_end,
        signal33_to_ending_observed=signal_to_end_observed,
        exit33_to_base_fill_slots=fill_to_fill,
    )


def _audit_speed(steps: list[tuple[Bar, Observation]]) -> Audit:
    """Зв'язати незмінні парні угоди з ACTIVE-трендами та часом."""
    baseline = _simulate(steps)
    variant = _simulate_variant(steps, use_33=True)
    trends = _trends(steps)
    base_index = _trade_index(baseline.trades)
    variant_index = _trade_index(variant.trades)
    assert base_index.keys() == variant_index.keys()
    assert baseline.entries == variant.entries
    assert baseline.entry_skipped_gap == variant.entry_skipped_gap
    assert baseline.open_at_end == variant.open_at_end
    assert len(trends) == baseline.entry_signals

    rows: list[Reaction] = []
    missing_entry = active_gap_trends = open_end = 0
    for trend in trends:
        begin = trend.start_index
        end = trend.end_signal_index
        if end is not None:
            segment = steps[begin:end + 1]
            active_gap_trends += int(any(
                second[0].timestamp != first[0].timestamp + M15
                for first, second in zip(segment, segment[1:])
            ))
        available_at = steps[begin][1].available_at
        entry_possible = (
            begin + 1 < len(steps)
            and steps[begin + 1][0].timestamp == available_at
        )
        if not entry_possible:
            missing_entry += 1
            assert available_at not in base_index
            continue
        base = base_index.get(available_at)
        rule33 = variant_index.get(available_at)
        if base is None:
            assert rule33 is None and end is None
            open_end += 1
            continue
        assert rule33 is not None
        rows.append(_one_reaction(steps, trend, base, rule33))

    assert missing_entry == baseline.entry_skipped_gap + baseline.entry_unfilled_at_end
    assert len(rows) == len(baseline.trades) == len(variant.trades)
    assert baseline.entries == len(rows) + open_end
    assert open_end == baseline.open_at_end
    assert missing_entry + baseline.entries == len(trends)
    assert math.isclose(
        sum(row.base_pips for row in rows),
        sum(trade.pips for trade in baseline.trades), abs_tol=EPS,
    )
    assert math.isclose(
        sum(row.rule33_pips for row in rows),
        sum(trade.pips for trade in variant.trades), abs_tol=EPS,
    )
    return Audit(
        rows=tuple(rows), total_trends=len(trends),
        entries=baseline.entries, no_entry=missing_entry,
        open_end=open_end, base_closed=len(baseline.trades),
        rule33_closed=len(variant.trades),
        active_gap_trends=active_gap_trends,
    )


def _quantile(values: list[float], fraction: float) -> float | None:
    """Лінійний інтерпольований квантиль; порожня вибірка — NONE."""
    if not values:
        return None
    assert 0 <= fraction <= 1
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _fmt(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.2f}"


def _values(rows: list[Reaction], field: str) -> list[float]:
    """Без None; лише фактичні outcome-метрики завершених угод."""
    return [float(value) for row in rows
            if (value := getattr(row, field)) is not None]


def _direction_report(label: str, direction: str, rows: list[Reaction]) -> None:
    """Однакові метрики та одиниці для BUY і SELL обох періодів."""
    assert rows and all(row.direction == direction for row in rows)
    early = [row for row in rows if row.early_33]
    tails = [row.base_pips - row.rule33_pips for row in early]
    tail_up = sum(tail for tail in tails if tail > EPS)
    tail_down = sum(-tail for tail in tails if tail < -EPS)
    gap_rows = sum(row.gap_affected_pair for row in early)
    positive = sum(row.peak_positive for row in rows)
    gross_base = sum(row.base_pips for row in rows)
    gross_rule33 = sum(row.rule33_pips for row in rows)
    largest = sorted((abs(tail) for tail in tails), reverse=True)
    concentration = (
        100 * sum(largest[:5]) / sum(largest) if sum(largest) > EPS else 0.0
    )
    assert math.isclose(tail_up - tail_down, gross_base - gross_rule33,
                        abs_tol=EPS)
    print(
        f"DIRECTION={direction}|PERIOD={label}|CLOSED={len(rows)}|"
        f"POSITIVE_ACTIVE_CLOSE_PEAK={positive}|"
        f"NO_POSITIVE_ACTIVE_CLOSE_PEAK={len(rows) - positive}|"
        f"INTERNAL_ACTIVE_GAP_TRADES="
        f"{sum(row.internal_active_gap for row in rows)}|"
        f"EARLY_33={len(early)}|EARLY_33_PCT="
        f"{100 * len(early) / len(rows):.2f}"
    )
    print(
        f"DEVELOPMENT={direction}|PERIOD={label}|"
        f"ENTRY_TO_BEST_CLOSE_MEDIAN_M15="
        f"{_fmt(_median(_values(rows, 'entry_to_peak_slots')))}|"
        f"ENTRY_TO_BEST_CLOSE_P75_M15="
        f"{_fmt(_quantile(_values(rows, 'entry_to_peak_slots'), 0.75))}|"
        f"BEST_CLOSE_MEDIAN_PIPS="
        f"{_fmt(_median(_values(rows, 'peak_gain_pips')))}|"
        f"RUNUP_MEDIAN_PIPS_PER_M15="
        f"{_fmt(_median(_values(rows, 'runup_pips_per_slot')))}|"
        f"BEST_CLOSE_TO_ENDING_MEDIAN_M15="
        f"{_fmt(_median(_values(rows, 'peak_to_ending_slots')))}|"
        f"FADE_MEDIAN_PIPS_PER_M15="
        f"{_fmt(_median(_values(rows, 'fade_pips_per_slot')))}"
    )
    print(
        f"RESPONSE_33={direction}|PERIOD={label}|"
        f"RUNNING_PEAK_TO_33_MEDIAN_M15="
        f"{_fmt(_median(_values(early, 'peak_to_33_slots')))}|"
        f"GIVEBACK_MEDIAN_PIPS_PER_M15="
        f"{_fmt(_median(_values(early, 'giveback_pips_per_slot')))}|"
        f"SIGNAL_33_TO_ENDING_MEDIAN_WALL_M15="
        f"{_fmt(_median(_values(early, 'signal33_to_ending_slots')))}|"
        f"SIGNAL_33_TO_ENDING_MEDIAN_OBS_M15="
        f"{_fmt(_median(_values(early, 'signal33_to_ending_observed')))}|"
        f"EXIT_33_TO_BASE_FILL_MEDIAN_M15="
        f"{_fmt(_median(_values(early, 'exit33_to_base_fill_slots')))}"
    )
    print(
        f"PAIRED_RESULT={direction}|PERIOD={label}|"
        f"HOLD_BETTER={sum(t > EPS for t in tails)}|"
        f"EARLY_BETTER={sum(t < -EPS for t in tails)}|"
        f"SAME={sum(abs(t) <= EPS for t in tails)}|"
        f"MISSED_PIPS={tail_up:.2f}|SAVED_PIPS={tail_down:.2f}|"
        f"TAIL_BASE_MINUS_33={sum(tails):.2f}|"
        f"GAP_AFFECTED_PAIRS={gap_rows}|"
        f"TOP5_ABS_TAIL_SHARE_PCT={concentration:.2f}"
    )


def _synthetic_checks() -> None:
    """BUY/SELL дзеркально, causal 33, gaps, no-entry та censored."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    none = ALLIGATOR_REGIME_PHASE_NONE

    def make(
        offset: int, op: float, close: float, phase: str, direction: str,
    ) -> tuple[Bar, ObservedState]:
        candle = Bar(
            start + offset * M15, op,
            max(op, close) + 0.0001,
            min(op, close) - 0.0001, close,
        )
        regime = (
            ALLIGATOR_REGIME_TREND_UP if direction == DIRECTION_UP
            else ALLIGATOR_REGIME_TREND_DOWN
        ) if phase != none else ALLIGATOR_REGIME_FLAT
        return candle, ObservedState(
            timestamp=candle.timestamp,
            available_at=candle.timestamp + M15,
            regime_phase=phase,
            regime=regime,
        )

    def sample(direction: str) -> list[tuple[Bar, ObservedState]]:
        center = 1.1000
        multiplier = 1 if direction == DIRECTION_UP else -1
        prices = (0, 0, 9, 5, 13, 12, 12)
        opens = (0, 0, 0, 9, 5, 13, 12)
        phases = (none, active, active, active, active, ending, none)
        return [
            make(
                index, center + multiplier * opens[index] * PIP,
                center + multiplier * prices[index] * PIP,
                phases[index], direction,
            ) for index in range(len(prices))
        ]

    # Перша ACTIVE-свічка — сигнал. Вхід лише на наступному open.
    # Для простоти сигнал ACTIVE на index=1; максимум +9 на index=2,
    # 33%-сигнал +5 на index=3, локальний ранній вихід — index=4.
    buy = _audit_speed(sample(DIRECTION_UP))
    sell = _audit_speed(sample(DIRECTION_DOWN))
    assert buy.total_trends == sell.total_trends == 1
    assert buy.entries == sell.entries == 1
    assert buy.base_closed == sell.base_closed == 1
    assert buy.rows[0].early_33 and sell.rows[0].early_33
    assert buy.rows[0].entry_to_peak_slots == sell.rows[0].entry_to_peak_slots
    assert buy.rows[0].peak_to_33_slots == sell.rows[0].peak_to_33_slots == 1
    assert buy.rows[0].signal33_to_ending_slots == 2
    assert sell.rows[0].signal33_to_ending_slots == 2
    assert math.isclose(buy.rows[0].peak_gain_pips, 13, abs_tol=EPS)
    assert math.isclose(sell.rows[0].peak_gain_pips, 13, abs_tol=EPS)

    # Пропущена M15 при виконанні раннього виходу: сигнал раніше,
    # фактичний fill пізніше; швидкість визначає часовий інтервал.
    gapped = sample(DIRECTION_UP)
    del gapped[4]
    gap_audit = _audit_speed(gapped)
    assert gap_audit.rows[0].early_33
    assert gap_audit.rows[0].gap_affected_pair
    assert gap_audit.rows[0].signal33_to_ending_slots == 2
    assert gap_audit.rows[0].signal33_to_ending_observed == 1

    # Немає суміжного open після ACTIVE: жодної вигаданої позиції.
    missed = sample(DIRECTION_UP)
    del missed[2]
    missed_audit = _audit_speed(missed)
    assert missed_audit.entries == 0
    assert missed_audit.no_entry == 1 and not missed_audit.rows

    # Незавершений ACTIVE — не враховувати як закриту угоду.
    censored = sample(DIRECTION_UP)[:4]
    censored_audit = _audit_speed(censored)
    assert censored_audit.open_end == 1
    assert censored_audit.base_closed == 0
    print("SYNTHETIC_DIRECTIONAL_REACTION_CAUSALITY=OK")


def _fingerprint(path: Path) -> str | None:
    """Контроль незмінності production та MD7."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _run_period(
    label: str, filename: str, expected: tuple[int, ...],
    profile: WorkspaceAlligatorRuntimeProfile,
) -> None:
    history = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source, selected, bars = _aggregate_m1(history, int(label[:4]), cutoff)
    steps = list(_states(bars, profile))
    base = _simulate(steps)
    assert (
        len(bars), base.entry_signals, base.buy_signals,
        base.sell_signals, base.next_open_available,
    ) == expected, f"T115_01_POPULATION_CHANGED: {label}"
    first = _audit_speed(steps)
    second = _audit_speed(steps)
    assert first == second, f"NONDETERMINISTIC: {label}"
    preceding = _audit_exposure(steps)
    assert preceding.trends == first.total_trends
    assert preceding.entries == first.entries
    assert preceding.no_entries == first.no_entry
    assert preceding.open_end == first.open_end
    assert preceding.closed_alligator == first.base_closed
    assert preceding.closed_33 == first.rule33_closed
    assert math.isclose(
        preceding.alligator_gross_pips,
        sum(row.base_pips for row in first.rows), abs_tol=1e-6,
    )
    assert math.isclose(
        preceding.rule33_gross_pips,
        sum(row.rule33_pips for row in first.rows), abs_tol=1e-6,
    )
    buy_rows = [row for row in first.rows if row.direction == DIRECTION_UP]
    sell_rows = [row for row in first.rows if row.direction == DIRECTION_DOWN]
    assert len(buy_rows) + len(sell_rows) == first.base_closed
    buy_early = [row for row in buy_rows if row.early_33]
    sell_early = [row for row in sell_rows if row.early_33]
    assert len(buy_early) == preceding.by_direction[0].early
    assert len(sell_early) == preceding.by_direction[1].early
    assert math.isclose(
        sum(row.base_pips - row.rule33_pips for row in buy_early),
        preceding.by_direction[0].net_tail_pips, abs_tol=EPS,
    )
    assert math.isclose(
        sum(row.base_pips - row.rule33_pips for row in sell_early),
        preceding.by_direction[1].net_tail_pips, abs_tol=EPS,
    )
    print(
        f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|CUTOFF_UTC="
        f"{cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"TREND_ORDERS|TOTAL={first.total_trends}|WITH_ENTRY={first.entries}|"
        f"WITHOUT_ENTRY={first.no_entry}|CLOSED_ALLIGATOR="
        f"{first.base_closed}|CLOSED_33={first.rule33_closed}|"
        f"OPEN_AT_END={first.open_end}|"
        f"INTERNAL_GAP_TRENDS={first.active_gap_trends}"
    )
    _direction_report(label, DIRECTION_UP, buy_rows)
    _direction_report(label, DIRECTION_DOWN, sell_rows)
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK|BASELINES_T115_01_TO_06=OK")


def main() -> None:
    """Тільки локальні файли; виходи та production не модифікуємо."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-07|TEST_ONLY|DIRECTIONAL_REACTION_SPEED_AUDIT")
    print("33_PERCENT=HYPOTHESIS_ONLY|OUTCOME_HINDSIGHT_ONLY=True")
    print("SPEED_UNITS=PIPS_PER_ELAPSED_15MIN_UTC|SOURCE=COMPLETED_M15_CLOSE")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False|broker_requests=0")
    print("gross_mid_only=True|spread_commission_slippage_included=False")
    print("production_changed=False|md7_changed=False")
    print("T115_07_DIRECTIONAL_REACTION_SPEED_AUDIT=OK")


if __name__ == "__main__":
    main()
