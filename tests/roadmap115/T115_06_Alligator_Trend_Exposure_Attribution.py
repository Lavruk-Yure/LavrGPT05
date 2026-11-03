# -*- coding: utf-8 -*-
"""RoadMap115 / T115-06 — покриття ACTIVE-трендів і якість виходів.

TEST_ONLY: без production-змін, MACD, оптимізації та broker requests.
Входи/виходи відтворюють НЕЗМІНЕНІ T115-02 і T115-03.
Правило 33% — непідтверджена дослідницька гіпотеза.

Одиниця покриття — завершений ACTIVE M15 ПІСЛЯ сигнального M15.
Позиція покриває цей бар, якщо відкрита на його open та не закрита
до цього open. Відсутні M15 не створюються і не рахуються.
Пропущені входи не отримують вигаданої ціни або виконання.

Групування за кількістю ACTIVE-барів ПІСЛЯ раннього виходу,
нові піки та paired tail — лише ретроспективні outcome labels,
які НІКОЛИ не використовуються для торгових рішень.
Ціна — OHLC mid, без спреду, комісій і прослизання.
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
    DIRECTION_DOWN,
    DIRECTION_UP,
    ObservedState,
    PIP,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    _simulate_variant,
)
from T115_04_Alligator_Trend_Coverage_Audit_FIXED import (  # noqa: E402
    Observation,
    _audit,
    _trade_index,
    _trends,
)
from T115_05_Trend_Continuation_Quality_Audit import (  # noqa: E402
    _quality,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_TREND_UP,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-7
BUCKET_NAMES = ("0", "1_TO_3", "4_TO_11", "12_PLUS")


@dataclass(slots=True)
class Group:
    """Результати ранніх виходів для одного незмінного набору подій."""

    early: int = 0
    hold_better: int = 0
    early_better: int = 0
    same: int = 0
    new_close_peak: int = 0
    favorable_later_close: int = 0
    uncovered_active_bars: int = 0
    gap_pairs: int = 0
    missed_positive_pips: float = 0.0
    avoided_negative_pips: float = 0.0
    net_tail_pips: float = 0.0

    def add(
        self,
        *,
        tail: float,
        new_close_peak: bool,
        favorable_later_close: bool,
        remaining: int,
        gap: bool,
    ) -> None:
        """Класифікація за вже завершеним результатом обох симуляцій."""
        self.early += 1
        self.new_close_peak += int(new_close_peak)
        self.favorable_later_close += int(favorable_later_close)
        self.uncovered_active_bars += remaining
        self.gap_pairs += int(gap)
        self.net_tail_pips += tail
        if tail > EPS:
            self.hold_better += 1
            self.missed_positive_pips += tail
        elif tail < -EPS:
            self.early_better += 1
            self.avoided_negative_pips -= tail
        else:
            self.same += 1


@dataclass(frozen=True, slots=True)
class Summary:
    """Детермінований звіт; cohort-мітки НЕ є entry/exit-фільтрами."""

    trends: int
    entries: int
    no_entries: int
    closed_alligator: int
    closed_33: int
    open_end: int
    active_bars: int
    signal_bars: int
    post_signal_active_bars: int
    no_entry_post_signal_bars: int
    alligator_covered_bars: int
    rule33_covered_bars: int
    uncovered_after_33_bars: int
    alligator_gross_pips: float
    rule33_gross_pips: float
    total: Group
    by_direction: tuple[Group, Group]
    by_remaining: tuple[Group, Group, Group, Group]


def _bucket(remaining: int) -> int:
    """Постфактум-групи ті самі, що в T115-05."""
    if remaining == 0:
        return 0
    if remaining <= 3:
        return 1
    if remaining <= 11:
        return 2
    return 3


def _exposed_bars(
    bars: list[Bar], entry_at: datetime, exit_at: datetime | None,
) -> int:
    """Покриття за часовими межами модельного ордера, без future fill."""
    return sum(
        1 for bar in bars
        if bar.timestamp >= entry_at
        and (exit_at is None or bar.timestamp < exit_at)
    )


def _audit_exposure(steps: list[tuple[Bar, Observation]]) -> Summary:
    """Однакова популяція трендів/входів у baseline та 33%-гіпотезі."""
    baseline = _simulate(steps)
    variant = _simulate_variant(steps, use_33=True)
    original = _audit(steps)
    quality = _quality(steps)
    trends = _trends(steps)
    base_trades = _trade_index(baseline.trades)
    variant_trades = _trade_index(variant.trades)
    assert base_trades.keys() == variant_trades.keys()
    assert baseline.entries == variant.entries == original.with_entry
    assert len(trends) == original.total == quality.trend_total

    all_active = signal_bars = post_signal = no_entry_bars = 0
    base_covered = rule33_covered = 0
    early_uncovered = 0
    total = Group()
    buy = Group()
    sell = Group()
    by_remaining = [Group() for _ in BUCKET_NAMES]
    no_entries = open_end = 0

    for trend in trends:
        end = trend.end_signal_index
        bars = [bar for bar, _ in steps[
            trend.start_index:end if end is not None else len(steps)
        ]]
        assert bars
        signal = steps[trend.start_index][1]
        entry_at = signal.available_at
        assert bars[0].timestamp == signal.timestamp
        all_active += len(bars)
        signal_bars += 1
        post_signal += len(bars) - 1

        next_index = trend.start_index + 1
        entry_possible = (
            next_index < len(steps)
            and steps[next_index][0].timestamp == entry_at
        )
        if not entry_possible:
            no_entries += 1
            no_entry_bars += len(bars) - 1
            assert entry_at not in base_trades
            continue

        base = base_trades.get(entry_at)
        rule33 = variant_trades.get(entry_at)
        if base is None:
            assert rule33 is None and end is None
            open_end += 1
            base_covered += _exposed_bars(bars, entry_at, None)
            rule33_covered += _exposed_bars(bars, entry_at, None)
            continue
        assert rule33 is not None
        assert base.entry_at == rule33.entry_at == entry_at
        assert base.entry_price == rule33.entry_price
        assert base.direction == rule33.direction == trend.direction

        base_covered += _exposed_bars(bars, entry_at, base.exit_at)
        rule33_covered += _exposed_bars(bars, entry_at, rule33.exit_at)
        if rule33.exit_reason != EXIT_33_REASON:
            assert rule33 == base
            continue

        assert end is not None and rule33.exit_at <= base.exit_at
        before = [bar for bar in bars if bar.timestamp < rule33.exit_at]
        after = [bar for bar in bars if bar.timestamp >= rule33.exit_at]
        assert before
        remaining = len(after)
        early_uncovered += remaining
        signed = 1 if rule33.direction == DIRECTION_UP else -1
        prior_peak = max(
            signed * (bar.close - rule33.entry_price) / PIP
            for bar in before
        )
        future_peak = max(
            [float("-inf")] + [
                signed * (bar.close - rule33.entry_price) / PIP
                for bar in after
            ]
        )
        new_peak = future_peak > prior_peak + EPS
        favorable = any(
            signed * (bar.close - rule33.exit_price) / PIP > EPS
            for bar in after
        )
        tail = base.pips - rule33.pips
        gap = base.exit_gap or rule33.exit_gap
        groups = (
            total,
            buy if rule33.direction == DIRECTION_UP else sell,
            by_remaining[_bucket(remaining)],
        )
        for group in groups:
            group.add(
                tail=tail,
                new_close_peak=new_peak,
                favorable_later_close=favorable,
                remaining=remaining,
                gap=gap,
            )

    assert all_active == signal_bars + post_signal
    assert no_entries == original.without_entry == quality.no_entry
    assert open_end == original.still_open
    assert all_active >= post_signal >= base_covered >= rule33_covered
    assert base_covered - rule33_covered == early_uncovered
    assert early_uncovered == original.uncovered_active_bars
    assert total.early == original.variant_33 == quality.early_exits
    assert total.uncovered_active_bars == early_uncovered
    assert total.hold_better == quality.paired_tail_up
    assert total.early_better == quality.paired_tail_down
    assert total.same == quality.paired_tail_flat
    assert total.new_close_peak == quality.new_close_peaks
    assert total.favorable_later_close == quality.favorable_post_exit
    assert total.gap_pairs == quality.gap_affected_pairs
    assert math.isclose(
        total.net_tail_pips, quality.paired_tail_net_pips, abs_tol=1e-6
    )
    assert math.isclose(
        total.missed_positive_pips, quality.paired_tail_gain_pips,
        abs_tol=1e-6,
    )
    assert math.isclose(
        total.avoided_negative_pips, quality.paired_tail_saved_pips,
        abs_tol=1e-6,
    )
    assert tuple(group.early for group in by_remaining) == (
        quality.buckets_remaining[0], quality.buckets_remaining[1],
        quality.buckets_remaining[2], quality.buckets_remaining[3],
    )
    assert sum(group.early for group in (buy, sell)) == total.early
    assert sum(group.uncovered_active_bars for group in by_remaining) == (
        early_uncovered
    )
    assert math.isclose(
        total.net_tail_pips,
        sum(trade.pips for trade in baseline.trades)
        - sum(trade.pips for trade in variant.trades),
        abs_tol=1e-6,
    )
    return Summary(
        trends=len(trends), entries=baseline.entries,
        no_entries=no_entries, closed_alligator=len(baseline.trades),
        closed_33=len(variant.trades), open_end=open_end,
        active_bars=all_active, signal_bars=signal_bars,
        post_signal_active_bars=post_signal,
        no_entry_post_signal_bars=no_entry_bars,
        alligator_covered_bars=base_covered,
        rule33_covered_bars=rule33_covered,
        uncovered_after_33_bars=early_uncovered,
        alligator_gross_pips=sum(t.pips for t in baseline.trades),
        rule33_gross_pips=sum(t.pips for t in variant.trades),
        total=total, by_direction=(buy, sell),
        by_remaining=(
            by_remaining[0], by_remaining[1],
            by_remaining[2], by_remaining[3],
        ),
    )


def _synthetic_checks() -> None:
    """Покриття, 33%-ранній вихід, пропущений open та censored tail."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    none = ALLIGATOR_REGIME_PHASE_NONE
    up = ALLIGATOR_REGIME_TREND_UP

    def make(offset: int, op: float, close: float, phase: str):
        sample_bar = Bar(
            start + offset * M15, op,
            max(op, close) + 0.0001,
            min(op, close) - 0.0001,
            close,
        )
        regime = up if phase != none else ALLIGATOR_REGIME_FLAT
        return sample_bar, ObservedState(
            timestamp=sample_bar.timestamp,
            available_at=sample_bar.timestamp + M15,
            regime_phase=phase,
            regime=regime,
        )

    sample = [
        make(0, 1.1000, 1.1000, active),
        make(1, 1.1000, 1.1009, active),
        make(2, 1.1009, 1.1005, active),
        make(3, 1.1004, 1.1006, active),
        make(4, 1.1006, 1.1012, active),
        make(5, 1.1012, 1.1012, ending),
        make(6, 1.1010, 1.1010, none),
        make(8, 1.1010, 1.1010, active),
        make(10, 1.1008, 1.1008, ending),
        make(11, 1.1008, 1.1008, none),
        make(12, 1.1008, 1.1008, active),
        make(13, 1.1008, 1.1008, active),
    ]
    first = _audit_exposure(sample)
    assert first.trends == 3 and first.entries == 2
    assert first.no_entries == 1 and first.open_end == 1
    assert first.active_bars == 8 and first.signal_bars == 3
    assert first.post_signal_active_bars == 5
    assert first.alligator_covered_bars == 5
    assert first.rule33_covered_bars == 3
    assert first.uncovered_after_33_bars == 2
    assert first.total.early == first.total.hold_better == 1
    assert first.by_remaining[1].early == 1
    assert first.by_direction[0].early == 1
    assert first.total.new_close_peak == 1
    assert math.isclose(first.total.net_tail_pips, 6.0, abs_tol=EPS)

    faded = list(sample)
    faded[4] = make(4, 1.1006, 1.1002, active)
    faded[5] = make(5, 1.1002, 1.1002, ending)
    faded[6] = make(6, 1.1001, 1.1001, none)
    second = _audit_exposure(faded)
    assert second.alligator_covered_bars == first.alligator_covered_bars
    assert second.rule33_covered_bars == first.rule33_covered_bars
    assert second.total.early_better == 1
    assert second.total.new_close_peak == 0
    assert math.isclose(second.total.net_tail_pips, -3.0, abs_tol=EPS)

    # Є майбутній ACTIVE close, але немає суміжного open: не відкривати.
    gap = list(sample)
    gap[8] = make(10, 1.1010, 1.1012, active)
    gap[9] = make(11, 1.1012, 1.1012, ending)
    gap[10] = make(12, 1.1012, 1.1012, none)
    third = _audit_exposure(gap)
    assert third.no_entries == 2
    assert third.no_entry_post_signal_bars == 1
    assert third.post_signal_active_bars == 5
    assert third.alligator_covered_bars == 4
    assert third.rule33_covered_bars == 2

    print("SYNTHETIC_TREND_EXPOSURE_ATTRIBUTION=OK")


def _fingerprint(path: Path) -> str | None:
    """Захист production та MD7 від випадкових змін під час тесту."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _group_line(label: str, group: Group) -> str:
    """Однакові показники для напряму й групи раннього виходу."""
    return (
        f"{label}|EARLY={group.early}|HOLD_BETTER={group.hold_better}|"
        f"EARLY_BETTER={group.early_better}|SAME={group.same}|"
        f"NEW_CLOSE_PEAK={group.new_close_peak}|"
        f"FAVORABLE_LATER_CLOSE={group.favorable_later_close}|"
        f"UNCOVERED_ACTIVE_BARS={group.uncovered_active_bars}|"
        f"GAP_PAIRS={group.gap_pairs}|"
        f"MISSED_PIPS={group.missed_positive_pips:.2f}|"
        f"SAVED_PIPS={group.avoided_negative_pips:.2f}|"
        f"TAIL_NET_PIPS={group.net_tail_pips:.2f}"
    )


def _run_period(label: str, filename: str, expected: tuple[int, ...], profile):
    """Однакові 2025/2026, два прогони й контроль незмінних базових тестів."""
    history = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source, selected, bars = _aggregate_m1(history, int(label[:4]), cutoff)
    steps = list(_states(bars, profile))
    base = _simulate(steps)
    assert (
        len(bars), base.entry_signals, base.buy_signals,
        base.sell_signals, base.next_open_available,
    ) == expected, f"ENTRY_POPULATION_CHANGED: {label}"
    first = _audit_exposure(steps)
    second = _audit_exposure(steps)
    assert first == second, f"NONDETERMINISTIC: {label}"
    assert first.entries + first.no_entries == first.trends

    potential = first.post_signal_active_bars
    baseline_share = 100 * first.alligator_covered_bars / potential
    rule33_share = 100 * first.rule33_covered_bars / potential
    print(
        f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|CUTOFF_UTC="
        f"{cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"TREND_ORDERS|TOTAL={first.trends}|WITH_ENTRY={first.entries}|"
        f"WITHOUT_ENTRY={first.no_entries}|CLOSED_ALLIGATOR="
        f"{first.closed_alligator}|CLOSED_33={first.closed_33}|"
        f"OPEN_AT_END={first.open_end}"
    )
    print(
        f"TREND_EXPOSURE|ACTIVE_BARS={first.active_bars}|"
        f"SIGNAL_BARS={first.signal_bars}|"
        f"POST_SIGNAL_ACTIVE_BARS={potential}|"
        f"NO_ENTRY_POST_SIGNAL_BARS="
        f"{first.no_entry_post_signal_bars}|"
        f"ALLIGATOR_COVERED_BARS={first.alligator_covered_bars}|"
        f"ALLIGATOR_COVERAGE_PCT={baseline_share:.2f}|"
        f"RULE33_COVERED_BARS={first.rule33_covered_bars}|"
        f"RULE33_COVERAGE_PCT={rule33_share:.2f}|"
        f"UNCOVERED_AFTER_33_BARS="
        f"{first.uncovered_after_33_bars}"
    )
    print(
        f"PAIRED_GROSS|ALLIGATOR={first.alligator_gross_pips:.2f}|"
        f"WITH_33={first.rule33_gross_pips:.2f}|"
        f"DELTA_33_MINUS_BASE="
        f"{first.rule33_gross_pips - first.alligator_gross_pips:.2f}"
    )
    print(_group_line("EARLY_33_TOTAL", first.total))
    for name, group in zip((DIRECTION_UP, DIRECTION_DOWN), first.by_direction):
        print(_group_line(f"BY_DIRECTION={name}", group))
    for name, group in zip(BUCKET_NAMES, first.by_remaining):
        print(_group_line(f"REMAINING_ACTIVE_BARS={name}", group))
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK|BASELINES_T115_01_TO_05=OK")


def main() -> None:
    """Лише читання історії та незмінних TEST_ONLY симуляторів."""
    protected = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in protected}
    print("T115-06|TEST_ONLY|ALLIGATOR_TREND_EXPOSURE_ATTRIBUTION")
    print("33_PERCENT=HYPOTHESIS_ONLY|OUTCOME_HINDSIGHT_ONLY=True")
    print("COVERAGE=OBSERVED_COMPLETED_ACTIVE_M15_POST_SIGNAL")
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
    print("T115_06_ALLIGATOR_TREND_EXPOSURE_ATTRIBUTION=OK")


if __name__ == "__main__":
    main()
