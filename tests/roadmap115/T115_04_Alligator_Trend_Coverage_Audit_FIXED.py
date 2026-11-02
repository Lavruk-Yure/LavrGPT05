# -*- coding: utf-8 -*-
"""RoadMap115 / T115-04 — аудит покриття ACTIVE-трендів ордерами.

TEST_ONLY, не production Replay. Два режими: T115-02 (тільки
Alligator) і T115-03 (Alligator + гіпотеза 33% за completed M15 close).
Входи та виходи беруться з НЕЗМІНЕНИХ симуляторів T115-02/03.

Тренд = безперервна серія completed M15 зі станом ACTIVE, що
починається на переході не-ACTIVE -> ACTIVE і завершується на першому
completed M15 зі станом не-ACTIVE. Напрямок — на старті ACTIVE.
Зміни напрямку всередині ACTIVE обліковуються окремо, а не створюють
новий сигнал входу (узгоджено з T115-01/02).

Закритий ордер НЕ означає завершений тренд: 33% може закрити ордер
раніше, залишивши частину тієї ж ACTIVE-фази без позиції.

Рух після виходу (tail) — post-factum outcome, НЕ сигнал чи доступна
для торгівлі можливість. Tail = PnL за Alligator мінус PnL за 33%
для ТОГО САМОГО входу; позитивний tail означає недоотриманий рух,
негативний — збережені пункти. Ціни: OHLC mid, без торгових витрат.
Якщо для виходу був розрив історії, його tail показаний окремо.
Відсутній сусідній M15 open — невиконаний вхід, без вигаданої ціни.
Цензуровані наприкінці історії тренди не трактуються як завершені.
"""

from __future__ import annotations

import hashlib
import math
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
    DIRECTION_UP,
    ObservedState,
    PIP,
    _direction,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    _simulate_variant,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorObservation,
)

ROOT = Path(__file__).resolve().parents[2]
Observation = WorkspaceAlligatorObservation | ObservedState


@dataclass(slots=True)
class Trend:
    """Межі ACTIVE визначаються лише після закриття відповідних M15."""

    start_index: int
    direction: str
    end_signal_index: int | None = None
    direction_flips: int = 0


@dataclass(frozen=True, slots=True)
class Coverage:
    """Аудит усіх трендів і парних фактичних модельних угод."""

    total: int
    ended: int
    censored: int
    direction_flips: int
    with_entry: int
    without_entry: int
    baseline_closed: int
    variant_closed: int
    still_open: int
    base_ending: int
    variant_ending: int
    variant_33: int
    early_filled_before_end: int
    no_active_bars_after_33_fill: int
    uncovered_active_bars: int
    favorable_continuations: int
    tail_positive_count: int
    tail_negative_count: int
    tail_flat_count: int
    tail_positive_pips: float
    tail_negative_pips: float
    tail_net_pips: float
    no_gap_tail_pips: float
    gap_affected_tail_pips: float
    gap_affected_pairs: int
    post_exit_close_peak_sum_pips: float


def _trends(steps: list[tuple[Bar, Observation]]) -> list[Trend]:
    """Виявляти ACTIVE за послідовними completed observations."""
    trends: list[Trend] = []
    current: Trend | None = None
    last_direction: str | None = None
    for i, (candle, obs) in enumerate(steps):
        assert obs.timestamp == candle.timestamp
        assert obs.available_at == candle.timestamp + M15
        active = obs.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        if active:
            direction = _direction(obs.regime)
            if current is None:
                current = Trend(i, direction)
                trends.append(current)
            elif direction != last_direction:
                current.direction_flips += 1
            last_direction = direction
        else:
            if current is not None:
                current.end_signal_index = i
                current = None
            last_direction = None
    return trends


def _trade_index(trades: list[ClosedTrade]) -> dict[datetime, ClosedTrade]:
    """В одного входу може бути не більше одного виконаного виходу."""
    lookup = {trade.entry_at: trade for trade in trades}
    assert len(lookup) == len(trades), "DUPLICATE_ENTRY_TRADE"
    return lookup


def _audit(steps: list[tuple[Bar, Observation]]) -> Coverage:
    """Облік лише за тим самим входом; майбутнє тільки для outcome."""
    baseline = _simulate(steps)
    variant = _simulate_variant(steps, use_33=True)
    trends = _trends(steps)
    base_trades = _trade_index(baseline.trades)
    var_trades = _trade_index(variant.trades)
    assert base_trades.keys() == var_trades.keys(), "PAIRED_ENTRIES_CHANGED"
    assert baseline.entries == variant.entries
    assert baseline.entry_signals == variant.entry_signals == len(trends)
    assert baseline.ignored_while_occupied == variant.ignored_while_occupied == 0
    assert baseline.entry_skipped_gap == variant.entry_skipped_gap
    assert baseline.entry_unfilled_at_end == variant.entry_unfilled_at_end
    assert baseline.open_at_end == variant.open_at_end
    assert baseline.exited_by_reason.get("ENDING", 0) == len(baseline.trades)

    ended = with_entry = no_entry = open_end = 0
    base_ending = var_ending = var_33 = 0
    filled_early = without_active_after = active_bars_uncovered = 0
    positive_continuations = positive = negative = flat = 0
    positive_pips = negative_pips = tail_net = clean_tail = gap_tail = 0.0
    gap_pairs = 0
    post_exit_close_peak_sum = 0.0
    used: set[datetime] = set()
    for trend in trends:
        start_idx = trend.start_index
        _, start_obs = steps[start_idx]
        entry_time = start_obs.available_at
        if trend.end_signal_index is not None:
            ended += 1
            assert trend.end_signal_index > start_idx
        entry_available = (
            start_idx + 1 < len(steps)
            and steps[start_idx + 1][0].timestamp == entry_time
        )
        if not entry_available:
            no_entry += 1
            assert entry_time not in base_trades
            continue
        with_entry += 1
        base = base_trades.get(entry_time)
        early = var_trades.get(entry_time)
        if base is None:
            assert early is None
            open_end += 1  # Можливий також ENDING без наступного open.
            continue
        assert early is not None
        used.add(entry_time)
        assert base.direction == early.direction == trend.direction
        assert base.entry_price == early.entry_price
        assert base.exit_reason == "ENDING"
        assert trend.end_signal_index is not None
        assert base.exit_at >= steps[trend.end_signal_index][1].available_at
        base_ending += 1
        if early.exit_reason == "ENDING":
            var_ending += 1
            assert base == early, "ALLIGATOR_ONLY_PAIR_DIFFERS"
            continue
        assert early.exit_reason == EXIT_33_REASON
        var_33 += 1
        assert early.exit_at <= base.exit_at
        ending_known_at = steps[trend.end_signal_index][1].available_at
        filled_early += int(early.exit_at < ending_known_at)
        remaining = [
            candle for candle, _ in steps[
                start_idx:trend.end_signal_index
            ] if candle.timestamp >= early.exit_at
        ]
        active_bars_uncovered += len(remaining)
        without_active_after += int(not remaining)
        sign = 1 if early.direction == DIRECTION_UP else -1
        max_close_gain = max(
            [0.0] + [
                sign * (candle.close - early.exit_price) / PIP
                for candle in remaining
            ]
        )
        positive_continuations += int(max_close_gain > 1e-7)
        post_exit_close_peak_sum += max_close_gain
        tail = base.pips - early.pips
        tail_net += tail
        if tail > 1e-7:
            positive += 1
            positive_pips += tail
        elif tail < -1e-7:
            negative += 1
            negative_pips += tail
        else:
            flat += 1
        if early.exit_gap or base.exit_gap:
            gap_pairs += 1
            gap_tail += tail
        else:
            clean_tail += tail

    assert used == base_trades.keys()
    assert ended + sum(t.end_signal_index is None for t in trends) == len(trends)
    assert with_entry + no_entry == len(trends)
    assert with_entry == baseline.entries
    assert no_entry == baseline.entry_skipped_gap + baseline.entry_unfilled_at_end
    assert open_end == baseline.open_at_end
    assert base_ending == len(baseline.trades)
    assert var_ending + var_33 == len(variant.trades)
    assert positive + negative + flat == var_33
    assert math.isclose(tail_net, sum(t.pips for t in baseline.trades) -
                        sum(t.pips for t in variant.trades), abs_tol=1e-7)
    assert math.isclose(tail_net, positive_pips + negative_pips, abs_tol=1e-7)
    assert math.isclose(tail_net, clean_tail + gap_tail, abs_tol=1e-7)
    return Coverage(
        total=len(trends), ended=ended, censored=len(trends) - ended,
        direction_flips=sum(t.direction_flips for t in trends),
        with_entry=with_entry, without_entry=no_entry,
        baseline_closed=len(baseline.trades), variant_closed=len(variant.trades),
        still_open=open_end, base_ending=base_ending,
        variant_ending=var_ending, variant_33=var_33,
        early_filled_before_end=filled_early,
        no_active_bars_after_33_fill=without_active_after,
        uncovered_active_bars=active_bars_uncovered,
        favorable_continuations=positive_continuations,
        tail_positive_count=positive, tail_negative_count=negative,
        tail_flat_count=flat, tail_positive_pips=positive_pips,
        tail_negative_pips=negative_pips, tail_net_pips=tail_net,
        no_gap_tail_pips=clean_tail,
        gap_affected_tail_pips=gap_tail, gap_affected_pairs=gap_pairs,
        post_exit_close_peak_sum_pips=post_exit_close_peak_sum,
    )


def _synthetic_checks() -> None:
    """Парний tail, no-entry через gap, завершений і незавершений тренд."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    up = ALLIGATOR_REGIME_TREND_UP

    def make(offset: int, op: float, close: float, phase: str, regime: str):
        candle = Bar(
            start + offset * M15, op,
            max(op, close) + 0.0001,
            min(op, close) - 0.0001, close,
        )
        return candle, ObservedState(
            timestamp=candle.timestamp,
            available_at=candle.timestamp + M15,
            regime_phase=phase, regime=regime,
        )

    steps = [
        make(0, 1.1000, 1.1000, active, up),
        make(1, 1.1000, 1.1009, active, up),
        make(2, 1.1009, 1.1005, active, up),
        make(3, 1.1004, 1.1006, active, up),
        make(4, 1.1006, 1.1012, active, up),
        make(5, 1.1012, 1.1012, ending, up),
        make(6, 1.1010, 1.1010, ALLIGATOR_REGIME_PHASE_NONE,
             ALLIGATOR_REGIME_FLAT),
        make(8, 1.1010, 1.1010, active, up),
        make(10, 1.1008, 1.1008, ending, up),
        make(11, 1.1008, 1.1008, ALLIGATOR_REGIME_PHASE_NONE,
             ALLIGATOR_REGIME_FLAT),
        make(12, 1.1008, 1.1008, active, up),
        make(13, 1.1008, 1.1008, active, up),
    ]
    summary = _audit(steps)
    assert summary.total == 3 and summary.ended == 2 and summary.censored == 1
    assert summary.with_entry == 2 and summary.without_entry == 1
    assert summary.baseline_closed == summary.variant_closed == 1
    assert summary.still_open == 1
    assert summary.variant_33 == 1 and summary.variant_ending == 0
    assert summary.uncovered_active_bars == 2
    assert summary.early_filled_before_end == 1
    assert summary.favorable_continuations == 1
    assert math.isclose(summary.tail_net_pips, 6.0, abs_tol=1e-7)
    print("SYNTHETIC_TREND_COVERAGE_CAUSALITY=OK")


def _fingerprint(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_period(label: str, filename: str, expected: tuple, profile) -> None:
    """Повний період: контроль подій T115-01, парних угод T115-02/03."""
    path = ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    m1, selected_m1, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    steps = list(_states(bars, profile))
    baseline = _simulate(steps)
    assert (
        len(bars), baseline.entry_signals, baseline.buy_signals,
        baseline.sell_signals, baseline.next_open_available,
    ) == expected, f"ENTRY_POPULATION_MISMATCH: {label}"
    first = _audit(steps)
    second = _audit(steps)
    assert first == second, f"NONDETERMINISTIC: {label}"
    assert first.total == baseline.entry_signals
    print(
        f"PERIOD={label}|SOURCE_M1={m1}|SELECTED_M1={selected_m1}|"
        f"COMPLETED_M15={len(bars)}|CUTOFF_UTC="
        f"{cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"TRENDS_TOTAL_ACTIVE={first.total}|TRENDS_ENDED={first.ended}|"
        f"TRENDS_CENSORED_END={first.censored}|"
        f"ACTIVE_DIRECTION_FLIPS={first.direction_flips}|"
        f"TRENDS_WITH_ENTRY={first.with_entry}|"
        f"TRENDS_WITHOUT_ENTRY={first.without_entry}|"
        f"MODEL_ORDERS_CLOSED_ALLIGATOR={first.baseline_closed}|"
        f"MODEL_ORDERS_CLOSED_33={first.variant_closed}|"
        f"MODEL_POSITIONS_OPEN_AT_END={first.still_open}"
    )
    print(
        f"ALLIGATOR_TRENDS_COVERED_UNTIL_ENDING={first.base_ending}|"
        f"WITH_33_TRENDS_COVERED_UNTIL_ENDING={first.variant_ending}|"
        f"WITH_33_TRENDS_CLOSED_BEFORE_ENDING_SIGNAL={first.variant_33}|"
        f"EARLY_FILLED_BEFORE_END_KNOWN={first.early_filled_before_end}|"
        f"EARLY_WITH_ZERO_FURTHER_ACTIVE_BARS="
        f"{first.no_active_bars_after_33_fill}|"
        f"ACTIVE_M15_BARS_AFTER_EARLY_EXIT={first.uncovered_active_bars}"
    )
    print(
        f"EARLY_EXIT_WITH_FAVORABLE_LATER_ACTIVE_CLOSE="
        f"{first.favorable_continuations}|"
        f"POST_EXIT_ACTIVE_CLOSE_PEAK_SUM_PIPS_HINDSIGHT="
        f"{first.post_exit_close_peak_sum_pips:.2f}"
    )
    print(
        f"PAIRED_TAIL_TO_ALLIGATOR_ENDING|"
        f"POSITIVE_COUNT={first.tail_positive_count}|"
        f"NEGATIVE_COUNT={first.tail_negative_count}|"
        f"FLAT_COUNT={first.tail_flat_count}|"
        f"MISSED_POSITIVE_PIPS={first.tail_positive_pips:.2f}|"
        f"AVOIDED_NEGATIVE_PIPS={-first.tail_negative_pips:.2f}|"
        f"NET_TAIL_PIPS={first.tail_net_pips:.2f}|"
        f"NO_GAP_NET_PIPS={first.no_gap_tail_pips:.2f}|"
        f"GAP_AFFECTED_PAIRS={first.gap_affected_pairs}|"
        f"GAP_AFFECTED_NET_PIPS={first.gap_affected_tail_pips:.2f}"
    )
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK|PAIRED_ENTRY_MATCH={label}:OK")


def main() -> None:
    """Тест виключно для дослідження; не торкається production і MD7."""
    protected = (
        ROOT / "core" / "workspace_alligator.py",
        ROOT / "core" / "workspace_indicator_profile.py",
        ROOT / "doc" / "LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in protected}
    print("T115-04|TEST_ONLY|ALLIGATOR_TREND_COVERAGE_AUDIT")
    print("33_PERCENT=HYPOTHESIS_ONLY|EXIT_EVALUATION=COMPLETED_M15_CLOSE")
    print("OUTCOME_TAIL_HINDSIGHT_ONLY=True|TRADING_COSTS_INCLUDED=False")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {str(path): _fingerprint(path) for path in protected}
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("production_changed=False|md7_changed=False")
    print("T115_04_ALLIGATOR_TREND_COVERAGE_AUDIT=OK")


if __name__ == "__main__":
    main()
