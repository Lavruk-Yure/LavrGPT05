# -*- coding: utf-8 -*-
"""RoadMap115 / T115-03 — гіпотеза 33% додаткового виходу.

TEST_ONLY. Не визначає canonical 33% exit rule, бо формулу не зафіксовано.
РОБОЧА ГІПОТЕЗА: якщо після входу за завершеними M15 CLOSE був
позитивний максимум unrealized PnL, а поточний completed M15 CLOSE
втратив >= 33% цього максимуму, подати сигнал виходу.
Виконати сигнал лише за open першого доступного майбутнього M15.
Вихід Alligator з T115-02 лишається; при одночасному сигналі він має
пріоритет у назві причини. Жодних intrabar high/low для 33% немає.

Порівнюємо з T115-02: однакові дані, entry, OHLC mid, без trading costs.
Це не production Profit Drawdown 35% і не пропозиція замінити його.
"""

from __future__ import annotations

from dataclasses import replace
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
    ClosedTrade,
    ObservedState,
    OpenPosition,
    PendingAction,
    Result,
    _direction,
    _exit_reason,
    _fingerprint,
    _metrics,
    _simulate,
    _states,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_TREND_UP,
)

ROOT = Path(__file__).resolve().parents[2]
EXIT_33_THRESHOLD = 0.33
EXIT_33_REASON = "CLOSE_PEAK_GIVEBACK_33"


def _simulate_variant(steps, *, use_33: bool) -> Result:
    """Незалежна гілка з незмінним baseline-диспетчером T115-02."""
    result = Result()
    previous_bar_at = previous_phase = None
    last_candidate_available_at = None
    pending = None
    position = None
    max_favorable_close_pips = 0.0

    for index, (bar, observation) in enumerate(steps):
        assert observation.timestamp == bar.timestamp
        assert observation.available_at == bar.timestamp + M15
        if previous_bar_at is not None:
            assert bar.timestamp > previous_bar_at
            if bar.timestamp != previous_bar_at + M15:
                result.incomplete_time_gaps += 1
        previous_bar_at = bar.timestamp

        # Спочатку виконання сигналів ПІСЛЯ попереднього close.
        if last_candidate_available_at is not None:
            if bar.timestamp == last_candidate_available_at:
                result.next_open_available += 1
            last_candidate_available_at = None

        if pending is not None:
            assert bar.timestamp >= pending.available_at
            if pending.action == "ENTRY":
                assert position is None
                if bar.timestamp == pending.available_at:
                    position = OpenPosition(
                        direction=pending.direction,
                        entry_at=bar.timestamp,
                        entry_price=bar.open,
                        entry_index=index,
                    )
                    max_favorable_close_pips = 0.0
                    result.entries += 1
                else:
                    result.entry_skipped_gap += 1
            else:
                assert pending.action == "EXIT" and position is not None
                gap = bar.timestamp != pending.available_at
                signed = 1 if position.direction == DIRECTION_UP else -1
                pips = signed * (bar.open - position.entry_price) / PIP
                result.trades.append(
                    ClosedTrade(
                        direction=position.direction,
                        entry_at=position.entry_at,
                        exit_at=bar.timestamp,
                        entry_price=position.entry_price,
                        exit_price=bar.open,
                        pips=pips,
                        holding_bars=index - position.entry_index,
                        holding_minutes=int(
                            (bar.timestamp - position.entry_at).total_seconds() // 60
                        ),
                        exit_reason=pending.reason,
                        exit_gap=gap,
                    )
                )
                result.exited_by_reason[pending.reason] = (
                    result.exited_by_reason.get(pending.reason, 0) + 1
                )
                result.exit_gap_fills += int(gap)
                position = None
                max_favorable_close_pips = 0.0
            pending = None

        # Після open читаємо ТІЛЬКИ завершений поточний M15.
        active = observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        if position is not None:
            reason = _exit_reason(
                observation.regime_phase,
                observation.regime,
                position.direction,
            )
            if use_33:
                signed = 1 if position.direction == DIRECTION_UP else -1
                close_pips = signed * (bar.close - position.entry_price) / PIP
                max_favorable_close_pips = max(max_favorable_close_pips, close_pips)
                if reason is None and max_favorable_close_pips > 0:
                    retained = max_favorable_close_pips * (1 - EXIT_33_THRESHOLD)
                    if close_pips <= retained:
                        reason = EXIT_33_REASON
            if reason is not None:
                pending = PendingAction(
                    action="EXIT",
                    available_at=observation.available_at,
                    signal_at=observation.timestamp,
                    reason=reason,
                )
                result.exits_signaled += 1

        if active and previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
            direction = _direction(observation.regime)
            result.entry_signals += 1
            result.buy_signals += int(direction == DIRECTION_UP)
            result.sell_signals += int(direction != DIRECTION_UP)
            last_candidate_available_at = observation.available_at
            if position is None and pending is None:
                pending = PendingAction(
                    action="ENTRY",
                    available_at=observation.available_at,
                    signal_at=observation.timestamp,
                    direction=direction,
                )
            else:
                result.ignored_while_occupied += 1
        previous_phase = observation.regime_phase

    if pending is not None:
        if pending.action == "ENTRY":
            result.entry_unfilled_at_end = 1
        else:
            result.exit_pending_at_end = 1
    result.open_at_end = int(position is not None)
    assert result.entries == len(result.trades) + result.open_at_end
    assert result.exits_signaled == len(result.trades) + result.exit_pending_at_end
    assert result.entry_signals == (
        result.entries
        + result.entry_skipped_gap
        + result.entry_unfilled_at_end
        + result.ignored_while_occupied
    )
    assert result.entry_signals == result.buy_signals + result.sell_signals
    return result


def _synthetic_checks() -> None:
    """Підтвердити час 33%-сигналу та відсутність intrabar look-ahead."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    up = ALLIGATOR_REGIME_TREND_UP
    active = ALLIGATOR_REGIME_PHASE_ACTIVE

    def make(offset, op, close, phase=active):
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
            regime=up if phase == active else ALLIGATOR_REGIME_FLAT,
        )

    # Peak +9 pips, потім +5: giveback 4/9 > 33%; fill на наступному open.
    sample = [
        make(0, 1.1000, 1.1000),
        make(1, 1.1000, 1.1009),
        make(2, 1.1009, 1.1005),
        make(3, 1.1004, 1.1004),
        make(4, 1.1003, 1.1003, ALLIGATOR_REGIME_PHASE_ENDING),
        make(5, 1.1002, 1.1002, ALLIGATOR_REGIME_PHASE_NONE),
    ]
    baseline = _simulate(sample)
    assert _simulate_variant(sample, use_33=False) == baseline
    early = _simulate_variant(sample, use_33=True)
    assert len(early.trades) == 1
    assert early.trades[0].exit_reason == EXIT_33_REASON
    assert early.trades[0].exit_at == start + 3 * M15
    assert abs(early.trades[0].pips - 4.0) < 1e-9
    assert baseline.trades[0].exit_reason == "ENDING"

    # Intrabar low може пробити 33%, але close лишається високим.
    low_only = list(sample)
    bar, obs = low_only[2]
    # Контроль: close +8 pips; наступний close також +8 pips.
    low_only[2] = replace(bar, close=1.1008, low=1.0980), obs
    next_bar, next_obs = low_only[3]
    low_only[3] = replace(next_bar, high=1.1009, close=1.1008), next_obs
    unchanged = _simulate_variant(low_only, use_33=True)
    assert unchanged.trades[0].exit_reason == "ENDING"

    # 33% не має спрацьовувати, якщо позитивного close-peak ще не було.
    no_peak = [
        make(0, 1.1000, 1.1000),
        make(1, 1.1000, 1.0999),
        make(2, 1.0999, 1.0997),
        make(3, 1.0997, 1.0995, ALLIGATOR_REGIME_PHASE_ENDING),
        make(4, 1.0995, 1.0995, ALLIGATOR_REGIME_PHASE_NONE),
    ]
    assert _simulate_variant(no_peak, use_33=True).exited_by_reason == {"ENDING": 1}
    print("SYNTHETIC_33_CLOSE_CAUSALITY=OK")


def _run_period(label: str, filename: str, expected: tuple, profile) -> None:
    path = ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source_m1, selected_m1, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    states = list(_states(bars, profile))
    baseline = _simulate(states)
    baseline_copy = _simulate_variant(states, use_33=False)
    assert baseline == baseline_copy, f"BASELINE_MISMATCH: {label}"
    assert (
        len(bars),
        baseline.entry_signals,
        baseline.buy_signals,
        baseline.sell_signals,
        baseline.next_open_available,
    ) == expected, f"T115_01_POPULATION_MISMATCH: {label}"
    new_first = _simulate_variant(states, use_33=True)
    new_second = _simulate_variant(states, use_33=True)
    assert new_first == new_second, f"NONDETERMINISTIC: {label}"
    assert baseline.entry_signals == new_first.entry_signals
    assert baseline.buy_signals == new_first.buy_signals
    assert baseline.sell_signals == new_first.sell_signals
    assert baseline.next_open_available == new_first.next_open_available
    causes = ",".join(
        f"{key}:{value}" for key, value in sorted(new_first.exited_by_reason.items())
    )
    print(
        f"PERIOD={label}|SOURCE_M1={source_m1}|SELECTED_M1={selected_m1}|"
        f"COMPLETED_M15={len(bars)}|ENTRY_EVENTS={baseline.entry_signals}|"
        f"NEXT_OPEN_AVAILABLE={baseline.next_open_available}"
    )
    print(f"BASELINE_T115_02|PERIOD={label}|{_metrics(baseline)}")
    print(f"HYPOTHESIS_33|PERIOD={label}|{_metrics(new_first)}")
    print(
        f"EXITS_33={new_first.exited_by_reason.get(EXIT_33_REASON, 0)}|"
        f"EXIT_REASON_COUNTS={causes}|OPEN_AT_END={new_first.open_at_end}|"
        f"EXIT_GAP_FILLS={new_first.exit_gap_fills}"
    )
    print(f"BASELINE_IDENTICAL={label}:OK|REPLAY_TWICE_DETERMINISTIC={label}:OK")


def main() -> None:
    """Зберегти ізоляцію експерименту від production та MD7."""
    guarded = (
        ROOT / "core" / "workspace_alligator.py",
        ROOT / "core" / "workspace_indicator_profile.py",
        ROOT / "doc" / "LGE_Runtime_07.md",
    )
    before = {path.as_posix(): _fingerprint(path) for path in guarded}
    print("T115-03|TEST_ONLY|33_PERCENT_CLOSE_PEAK_GIVEBACK_HYPOTHESIS")
    print("HYPOTHESIS_ONLY=True|33_FORMULA_NOT_CANONICALLY_CONFIRMED=True")
    print("EXIT_MEASURE=COMPLETED_M15_CLOSE|EXIT_EXECUTION=NEXT_AVAILABLE_M15_OPEN")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {
        path.as_posix(): _fingerprint(path) for path in guarded
    }, "PRODUCTION_OR_MD7_MODIFIED"
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("gross_mid_only=True|spread_commission_slippage_included=False")
    print("production_changed=False|md7_changed=False")
    print("T115_03_ALLIGATOR_EXIT_33_HYPOTHESIS=OK")


if __name__ == "__main__":
    main()
