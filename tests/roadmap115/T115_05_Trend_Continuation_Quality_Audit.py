# -*- coding: utf-8 -*-
"""RoadMap115 / T115-05 — якість продовження ACTIVE-трендів.

TEST_ONLY. Без змін production, MD7 і параметрів алгоритму.
Ті самі вхідні події й модельні ордери T115-01...04.

33% — лише НЕПІДТВЕРДЖЕНА гіпотеза T115-03. Рішення про вихід
приймається тільки після завершеного M15 close, виконання — на
майбутньому доступному M15 open. Не використовується MACD.

Усі оцінки після раннього виходу та після пропущеного входу —
ретроспективні outcome labels, НЕ причинні торгові сигнали.
NEW_CLOSE_PEAK: найбільший close усередині ACTIVE після виконання
33%-виходу перевищив найкращий ACTIVE close ДО виконання виходу
у напрямку ордера (порівняння відносно тієї самої entry price).
POSITIVE_PAIRED_TAIL: фактична модельна різниця PnL між утриманням
до Alligator ENDING і достроковим 33%-виходом того ж входу.
Ці визначення НЕ еквівалентні: пік міг оновитися, але не зберегтися.

Для трендів без входу ціна входу НЕ домислюється. Рух між close
ACTIVE-сигналу й пізнішими завершеними ACTIVE close — лише hindsight,
не реалізований і не гарантований PnL. Цензуровані тренди окремі.
OHLC mid, без спреду/комісії/прослизання; відсутні M15 не заповнюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    M15,
    PERIODS,
    Bar,
    _aggregate_m1,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_UP,
    PIP,
    ObservedState,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    _simulate_variant,
)
from T115_04_Alligator_Trend_Coverage_Audit_FIXED import (  # noqa: E402
    Observation,
    Trend,
    _audit,
    _trade_index,
    _trends,
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


@dataclass(frozen=True, slots=True)
class Quality:
    """Детермінований підсумок атрибуції без оптимізації параметрів."""

    trend_total: int
    early_exits: int
    early_no_later_active: int
    early_with_later_active: int
    buckets_remaining: tuple[int, int, int, int]
    new_close_peaks: int
    no_new_close_peaks: int
    peak_extension_sum_pips: float
    favorable_post_exit: int
    favorable_post_exit_sum_pips: float
    end_active_close_up: int
    end_active_close_down: int
    end_active_close_flat: int
    paired_tail_up: int
    paired_tail_down: int
    paired_tail_flat: int
    paired_tail_gain_pips: float
    paired_tail_saved_pips: float
    paired_tail_net_pips: float
    new_peak_tail_up: int
    new_peak_tail_not_up: int
    no_peak_tail_up: int
    no_peak_tail_not_up: int
    favorable_peak_but_nonpositive_tail: int
    gap_affected_pairs: int
    gap_affected_net_pips: float
    no_entry: int
    no_entry_gap: int
    no_entry_at_end: int
    no_entry_ended: int
    no_entry_censored: int
    no_entry_later_active: int
    no_entry_later_favorable: int
    no_entry_later_close_peak_pips: float
    no_entry_last_close_positive: int
    no_entry_last_close_negative: int
    no_entry_last_close_flat: int
    no_entry_last_close_net_pips: float
    no_entry_missing_intervals: int
    no_entry_active_bars: int
    median_remaining_active_bars: float


def _signed(direction: str) -> int:
    """Напрямок фактичного модельного ордера, а не майбутнього руху."""
    return 1 if direction == DIRECTION_UP else -1


def _trend_bars(
    steps: list[tuple[Bar, Observation]],
    trend: Trend,
) -> list[Bar]:
    """Тільки ACTIVE-бари, без завершального не-ACTIVE спостереження."""
    end = trend.end_signal_index
    return [
        bar
        for bar, _ in steps[trend.start_index : end if end is not None else len(steps)]
    ]


def _quality(steps: list[tuple[Bar, Observation]]) -> Quality:
    """Незмінні симулятори; майбутні close тільки для outcome labels."""
    baseline = _simulate(steps)
    variant = _simulate_variant(steps, use_33=True)
    control = _audit(steps)
    trends = _trends(steps)
    base_trades = _trade_index(baseline.trades)
    variant_trades = _trade_index(variant.trades)
    assert base_trades.keys() == variant_trades.keys()
    assert len(trends) == control.total

    early = no_later = has_later = new_peaks = no_peaks = 0
    positive_after = end_up = end_down = end_flat = 0
    tail_up = tail_down = tail_flat = 0
    new_up = new_not_up = old_up = old_not_up = 0
    positive_peak_bad_tail = gap_pairs = 0
    peak_extension = post_gain = tail_gain = tail_saved = 0.0
    tail_net = gap_net = 0.0
    remaining_bins = [0, 0, 0, 0]
    remaining_counts: list[int] = []
    no_entry = no_gap = no_end = no_ended = no_censored = 0
    no_later_active = no_later_positive = no_up = no_down = no_flat = 0
    no_peak_sum = no_last_net = 0.0
    no_missing = no_active_bars = 0

    for trend in trends:
        bars = _trend_bars(steps, trend)
        assert bars and bars[0] == steps[trend.start_index][0]
        _, signal = steps[trend.start_index]
        next_index = trend.start_index + 1
        next_candle = steps[next_index][0] if next_index < len(steps) else None
        available = (
            next_candle is not None and next_candle.timestamp == signal.available_at
        )
        sign = _signed(trend.direction)

        if not available:
            no_entry += 1
            assert signal.available_at not in base_trades
            if next_candle is None:
                no_end += 1
            else:
                no_gap += 1
                intervals = int((next_candle.timestamp - signal.available_at) / M15)
                assert intervals >= 1
                no_missing += intervals
            no_ended += int(trend.end_signal_index is not None)
            no_censored += int(trend.end_signal_index is None)
            later = bars[1:]
            no_active_bars += len(later)
            no_later_active += int(bool(later))
            if later:
                movements = [sign * (bar.close - bars[0].close) / PIP for bar in later]
                mfe = max(0.0, *movements)
                no_later_positive += int(mfe > EPS)
                no_peak_sum += mfe
                end_value = movements[-1]
                no_last_net += end_value
                no_up += int(end_value > EPS)
                no_down += int(end_value < -EPS)
                no_flat += int(abs(end_value) <= EPS)
            continue

        base = base_trades.get(signal.available_at)
        candidate = variant_trades.get(signal.available_at)
        if base is None:
            assert candidate is None
            assert trend.end_signal_index is None
            continue
        assert candidate is not None
        assert base.entry_at == candidate.entry_at == signal.available_at
        assert base.direction == candidate.direction == trend.direction
        assert base.entry_price == candidate.entry_price
        if candidate.exit_reason != EXIT_33_REASON:
            assert base == candidate
            continue

        early += 1
        assert trend.end_signal_index is not None
        assert candidate.exit_at <= base.exit_at
        before = [bar for bar in bars if bar.timestamp < candidate.exit_at]
        after = [bar for bar in bars if bar.timestamp >= candidate.exit_at]
        assert before
        remaining_counts.append(len(after))
        no_later += int(not after)
        has_later += int(bool(after))
        bucket = (
            0 if not after else 1 if len(after) <= 3 else 2 if len(after) <= 11 else 3
        )
        remaining_bins[bucket] += 1

        previous_peak = max(
            sign * (bar.close - candidate.entry_price) / PIP for bar in before
        )
        after_peaks = [
            sign * (bar.close - candidate.entry_price) / PIP for bar in after
        ]
        updated_peak = bool(after_peaks) and max(after_peaks) > previous_peak + EPS
        new_peaks += int(updated_peak)
        no_peaks += int(not updated_peak)
        if updated_peak:
            peak_extension += max(after_peaks) - previous_peak

        following_gain = max(
            [0.0] + [sign * (bar.close - candidate.exit_price) / PIP for bar in after]
        )
        positive_after += int(following_gain > EPS)
        post_gain += following_gain
        if after:
            last_move = sign * (after[-1].close - candidate.exit_price) / PIP
            end_up += int(last_move > EPS)
            end_down += int(last_move < -EPS)
            end_flat += int(abs(last_move) <= EPS)

        tail = base.pips - candidate.pips
        tail_net += tail
        is_good_tail = tail > EPS
        if is_good_tail:
            tail_up += 1
            tail_gain += tail
        elif tail < -EPS:
            tail_down += 1
            tail_saved -= tail
        else:
            tail_flat += 1
        new_up += int(updated_peak and is_good_tail)
        new_not_up += int(updated_peak and not is_good_tail)
        old_up += int(not updated_peak and is_good_tail)
        old_not_up += int(not updated_peak and not is_good_tail)
        positive_peak_bad_tail += int(following_gain > EPS and not is_good_tail)
        if base.exit_gap or candidate.exit_gap:
            gap_pairs += 1
            gap_net += tail

    assert early == control.variant_33
    assert no_entry == control.without_entry
    assert no_gap == baseline.entry_skipped_gap
    assert no_end == baseline.entry_unfilled_at_end
    assert no_ended + no_censored == no_entry
    assert no_later + has_later == early
    assert sum(remaining_bins) == early
    assert sum(remaining_counts) == control.uncovered_active_bars
    assert positive_after == control.favorable_continuations
    assert math.isclose(post_gain, control.post_exit_close_peak_sum_pips, abs_tol=1e-6)
    assert (tail_up, tail_down, tail_flat) == (
        control.tail_positive_count,
        control.tail_negative_count,
        control.tail_flat_count,
    )
    assert math.isclose(tail_net, control.tail_net_pips, abs_tol=1e-6)
    assert math.isclose(tail_gain, control.tail_positive_pips, abs_tol=1e-6)
    assert math.isclose(tail_saved, -control.tail_negative_pips, abs_tol=1e-6)
    assert gap_pairs == control.gap_affected_pairs
    assert math.isclose(gap_net, control.gap_affected_tail_pips, abs_tol=1e-6)
    assert new_up + new_not_up + old_up + old_not_up == early
    assert end_up + end_down + end_flat == has_later

    return Quality(
        trend_total=len(trends),
        early_exits=early,
        early_no_later_active=no_later,
        early_with_later_active=has_later,
        buckets_remaining=(
            remaining_bins[0],
            remaining_bins[1],
            remaining_bins[2],
            remaining_bins[3],
        ),
        new_close_peaks=new_peaks,
        no_new_close_peaks=no_peaks,
        peak_extension_sum_pips=peak_extension,
        favorable_post_exit=positive_after,
        favorable_post_exit_sum_pips=post_gain,
        end_active_close_up=end_up,
        end_active_close_down=end_down,
        end_active_close_flat=end_flat,
        paired_tail_up=tail_up,
        paired_tail_down=tail_down,
        paired_tail_flat=tail_flat,
        paired_tail_gain_pips=tail_gain,
        paired_tail_saved_pips=tail_saved,
        paired_tail_net_pips=tail_net,
        new_peak_tail_up=new_up,
        new_peak_tail_not_up=new_not_up,
        no_peak_tail_up=old_up,
        no_peak_tail_not_up=old_not_up,
        favorable_peak_but_nonpositive_tail=positive_peak_bad_tail,
        gap_affected_pairs=gap_pairs,
        gap_affected_net_pips=gap_net,
        no_entry=no_entry,
        no_entry_gap=no_gap,
        no_entry_at_end=no_end,
        no_entry_ended=no_ended,
        no_entry_censored=no_censored,
        no_entry_later_active=no_later_active,
        no_entry_later_favorable=no_later_positive,
        no_entry_later_close_peak_pips=no_peak_sum,
        no_entry_last_close_positive=no_up,
        no_entry_last_close_negative=no_down,
        no_entry_last_close_flat=no_flat,
        no_entry_last_close_net_pips=no_last_net,
        no_entry_missing_intervals=no_missing,
        no_entry_active_bars=no_active_bars,
        median_remaining_active_bars=(
            statistics.median(remaining_counts) if remaining_counts else 0.0
        ),
    )


def _synthetic_checks() -> None:
    """Окремі тести продовження, згасання, gap і цензурування."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    up = ALLIGATOR_REGIME_TREND_UP
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    none_phase = ALLIGATOR_REGIME_PHASE_NONE

    def make(offset: int, op: float, close: float, phase: str, regime: str):
        sample_bar = Bar(
            start + offset * M15,
            op,
            max(op, close) + 0.0001,
            min(op, close) - 0.0001,
            close,
        )
        return sample_bar, ObservedState(
            timestamp=sample_bar.timestamp,
            available_at=sample_bar.timestamp + M15,
            regime_phase=phase,
            regime=regime,
        )

    sample = [
        make(0, 1.1000, 1.1000, active, up),
        make(1, 1.1000, 1.1009, active, up),
        make(2, 1.1009, 1.1005, active, up),
        make(3, 1.1004, 1.1006, active, up),
        make(4, 1.1006, 1.1012, active, up),
        make(5, 1.1012, 1.1012, ending, up),
        make(6, 1.1010, 1.1010, none_phase, ALLIGATOR_REGIME_FLAT),
        make(8, 1.1010, 1.1010, active, up),
        make(10, 1.1008, 1.1008, ending, up),
        make(11, 1.1008, 1.1008, none_phase, ALLIGATOR_REGIME_FLAT),
        make(12, 1.1008, 1.1008, active, up),
        make(13, 1.1008, 1.1008, active, up),
    ]
    first = _quality(sample)
    assert first.trend_total == 3 and first.early_exits == 1
    assert first.new_close_peaks == first.paired_tail_up == 1
    assert first.no_entry == first.no_entry_gap == 1
    assert first.no_entry_ended == 1 and first.no_entry_censored == 0
    assert first.no_entry_later_active == 0
    assert first.no_entry_missing_intervals == 1
    assert first.early_with_later_active == 1
    assert first.buckets_remaining == (0, 1, 0, 0)
    assert math.isclose(first.paired_tail_net_pips, 6.0, abs_tol=EPS)

    faded = list(sample)
    faded[4] = make(4, 1.1006, 1.1002, active, up)
    faded[5] = make(5, 1.1002, 1.1002, ending, up)
    faded[6] = make(6, 1.1001, 1.1001, none_phase, ALLIGATOR_REGIME_FLAT)
    second = _quality(faded)
    assert second.new_close_peaks == second.paired_tail_up == 0
    assert second.paired_tail_down == 1
    assert math.isclose(second.paired_tail_net_pips, -3.0, abs_tol=EPS)

    # Пропущений вхід: є наступний ACTIVE close, але немає суміжного open.
    extra = list(sample)
    extra[8] = make(10, 1.1010, 1.1012, active, up)
    extra[9] = make(11, 1.1012, 1.1012, ending, up)
    extra[10] = make(12, 1.1012, 1.1012, none_phase, ALLIGATOR_REGIME_FLAT)
    third = _quality(extra)
    # Offset 9 відсутній: без входу тренд мав наступний ACTIVE close.
    assert third.early_exits == 1
    assert third.no_entry == 2 and third.no_entry_gap == 1
    assert third.no_entry_at_end == 1
    assert third.no_entry_later_active == 1
    assert third.no_entry_later_favorable == 1
    assert math.isclose(third.no_entry_later_close_peak_pips, 2.0, abs_tol=EPS)

    # ACTIVE на останньому барі: майбутнього open немає, тренд цензурований.
    last_only = [make(0, 1.1000, 1.1000, active, up)]
    censored = _quality(last_only)
    assert censored.no_entry == censored.no_entry_at_end == 1
    assert censored.no_entry_censored == 1
    assert censored.no_entry_gap == 0
    print("SYNTHETIC_TREND_CONTINUATION_QUALITY=OK")


def _fingerprint(path: Path) -> str | None:
    """Контроль побайтової незмінності важливих production-файлів."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_period(label: str, filename: str, expected: tuple, profile) -> None:
    """Порівняти ту саму історію й той самий профіль, двічі."""
    path = ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    m1, selected, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    steps = list(_states(bars, profile))
    baseline = _simulate(steps)
    assert (
        len(bars),
        baseline.entry_signals,
        baseline.buy_signals,
        baseline.sell_signals,
        baseline.next_open_available,
    ) == expected, f"ENTRY_POPULATION_CHANGED: {label}"
    first = _quality(steps)
    second = _quality(steps)
    assert first == second, f"NONDETERMINISTIC: {label}"
    assert first.no_entry + baseline.entries == first.trend_total
    print(
        f"PERIOD={label}|SOURCE_M1={m1}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|CUTOFF_UTC="
        f"{cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"TRENDS_ACTIVE={first.trend_total}|EARLY_33={first.early_exits}|"
        f"REMAINING_ACTIVE_BARS_BUCKETS_0_1TO3_4TO11_12PLUS="
        f"{','.join(map(str, first.buckets_remaining))}|"
        f"MEDIAN_REMAINING_ACTIVE_BARS="
        f"{first.median_remaining_active_bars:.1f}"
    )
    print(
        f"CLOSE_PEAK_AFTER_33|NEW_PEAK={first.new_close_peaks}|"
        f"NO_NEW_PEAK={first.no_new_close_peaks}|"
        f"NEW_PEAK_EXTENSION_PIPS_HINDSIGHT="
        f"{first.peak_extension_sum_pips:.2f}|"
        f"FAVORABLE_POST_EXIT_CLOSE={first.favorable_post_exit}|"
        f"POST_EXIT_BEST_GAIN_PIPS_HINDSIGHT="
        f"{first.favorable_post_exit_sum_pips:.2f}"
    )
    print(
        f"LAST_ACTIVE_CLOSE_VS_33_EXIT_OPEN|UP={first.end_active_close_up}|"
        f"DOWN={first.end_active_close_down}|"
        f"FLAT={first.end_active_close_flat}|"
        f"NO_LATER_ACTIVE_CLOSE={first.early_no_later_active}"
    )
    print(
        f"PAIRED_ALLIGATOR_VS_33|HOLD_BETTER={first.paired_tail_up}|"
        f"EARLY_BETTER={first.paired_tail_down}|"
        f"SAME={first.paired_tail_flat}|"
        f"MISSED_POSITIVE_PIPS={first.paired_tail_gain_pips:.2f}|"
        f"AVOIDED_NEGATIVE_PIPS={first.paired_tail_saved_pips:.2f}|"
        f"NET_TAIL_PIPS={first.paired_tail_net_pips:.2f}"
    )
    print(
        f"CLOSE_PEAK_X_PAIRED_TAIL|NEW_PEAK_HOLD_BETTER="
        f"{first.new_peak_tail_up}|NEW_PEAK_EARLY_NOT_WORSE="
        f"{first.new_peak_tail_not_up}|NO_NEW_PEAK_HOLD_BETTER="
        f"{first.no_peak_tail_up}|NO_NEW_PEAK_EARLY_NOT_WORSE="
        f"{first.no_peak_tail_not_up}|"
        f"FAVORABLE_CLOSE_BUT_EARLY_NOT_WORSE="
        f"{first.favorable_peak_but_nonpositive_tail}"
    )
    print(
        f"EXIT_GAPS|PAIRS={first.gap_affected_pairs}|"
        f"NET_TAIL_PIPS={first.gap_affected_net_pips:.2f}"
    )
    print(
        f"NO_ENTRY|TOTAL={first.no_entry}|MISSING_NEXT_OPEN_GAP="
        f"{first.no_entry_gap}|AT_SERIES_END={first.no_entry_at_end}|"
        f"ENDED={first.no_entry_ended}|CENSORED={first.no_entry_censored}|"
        f"MISSING_M15_INTERVALS={first.no_entry_missing_intervals}|"
        f"OBSERVED_LATER_ACTIVE_BARS={first.no_entry_active_bars}"
    )
    print(
        f"NO_ENTRY_CLOSE_OUTCOME_HINDSIGHT|"
        f"HAS_LATER_ACTIVE_CLOSE={first.no_entry_later_active}|"
        f"FAVORABLE_AFTER_SIGNAL={first.no_entry_later_favorable}|"
        f"POST_SIGNAL_CLOSE_PEAK_SUM_PIPS="
        f"{first.no_entry_later_close_peak_pips:.2f}|"
        f"LAST_CLOSE_POSITIVE={first.no_entry_last_close_positive}|"
        f"LAST_CLOSE_NEGATIVE={first.no_entry_last_close_negative}|"
        f"LAST_CLOSE_FLAT={first.no_entry_last_close_flat}|"
        f"LAST_CLOSE_NET_PIPS={first.no_entry_last_close_net_pips:.2f}"
    )
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK|T115_04_BASELINE_MATCH=OK")


def main() -> None:
    """Не змінювати ані production, ані попередні тестові алгоритми."""
    protected = (
        ROOT / "core" / "workspace_alligator.py",
        ROOT / "core" / "workspace_indicator_profile.py",
        ROOT / "doc" / "LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in protected}
    print("T115-05|TEST_ONLY|TREND_CONTINUATION_QUALITY_AUDIT")
    print("33_PERCENT=HYPOTHESIS_ONLY|OUTCOME_ONLY_HINDSIGHT=True")
    print("ENTRY_EXIT_SIMULATORS_UNCHANGED=T115-02,T115-03")
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
    print("T115_05_TREND_CONTINUATION_QUALITY_AUDIT=OK")


if __name__ == "__main__":
    main()
