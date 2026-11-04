# -*- coding: utf-8 -*-
"""RoadMap115 / T115-09 — окремий Replay гібридного виходу.

TEST_ONLY. Однакові сигнали входу для трьох сценаріїв:
  A: BUY/SELL -> Alligator ENDING (T115-02);
  B: BUY/SELL -> Alligator ENDING або 33% (T115-03);
  C: BUY -> Alligator ENDING; SELL -> ENDING або 33%.

33% — НЕ затверджене правило: peak прибутку за completed M15 close,
відступ на 33% від позитивного peak; виконання на наступному доступному
M15 open. Внутрішньобарні high/low не використовуються. Жодних MACD,
SL/TP, комісій, спреду, прослизання, брокера чи змін production/MD7.

Гібрид обрано за результатами 2025/2026; ці періоди НЕ є незалежною
out-of-sample перевіркою його придатності до production.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

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
    ClosedTrade,
    ObservedState,
    OpenPosition,
    PendingAction,
    PIP,
    Result,
    _direction,
    _exit_reason,
    _fingerprint,
    _metrics,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    EXIT_33_THRESHOLD,
    _simulate_variant,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-7
HYBRID_33_DIRECTIONS = frozenset({DIRECTION_DOWN})
BOTH_DIRECTIONS = frozenset({DIRECTION_UP, DIRECTION_DOWN})


def _simulate_directional(
    steps: Iterable[
        tuple[Bar, WorkspaceAlligatorObservation | ObservedState]
    ],
    *,
    use_33_for: frozenset[str],
) -> Result:
    """Симулювати рішення лише на completed close, виконання — з open."""
    assert use_33_for <= BOTH_DIRECTIONS
    result = Result()
    previous_bar_at: datetime | None = None
    previous_phase: str | None = None
    last_candidate_available_at: datetime | None = None
    pending: PendingAction | None = None
    position: OpenPosition | None = None
    max_favorable_close_pips = 0.0

    for index, (current_bar, observation) in enumerate(steps):
        assert observation.timestamp == current_bar.timestamp
        assert observation.available_at == current_bar.timestamp + M15
        if previous_bar_at is not None:
            assert current_bar.timestamp > previous_bar_at
            if current_bar.timestamp != previous_bar_at + M15:
                result.incomplete_time_gaps += 1
        previous_bar_at = current_bar.timestamp

        # На open дозволені тільки попередні завершені сигнали.
        if last_candidate_available_at is not None:
            if current_bar.timestamp == last_candidate_available_at:
                result.next_open_available += 1
            last_candidate_available_at = None

        if pending is not None:
            assert current_bar.timestamp >= pending.available_at
            if pending.action == "ENTRY":
                assert position is None
                if current_bar.timestamp == pending.available_at:
                    position = OpenPosition(
                        direction=pending.direction,
                        entry_at=current_bar.timestamp,
                        entry_price=current_bar.open,
                        entry_index=index,
                    )
                    max_favorable_close_pips = 0.0
                    result.entries += 1
                else:
                    result.entry_skipped_gap += 1
            else:
                assert pending.action == "EXIT" and position is not None
                is_gap = current_bar.timestamp != pending.available_at
                signed = 1 if position.direction == DIRECTION_UP else -1
                realized_pips = signed * (
                    current_bar.open - position.entry_price
                ) / PIP
                result.trades.append(ClosedTrade(
                    direction=position.direction,
                    entry_at=position.entry_at,
                    exit_at=current_bar.timestamp,
                    entry_price=position.entry_price,
                    exit_price=current_bar.open,
                    pips=realized_pips,
                    holding_bars=index - position.entry_index,
                    holding_minutes=int(
                        (current_bar.timestamp - position.entry_at)
                        .total_seconds() // 60
                    ),
                    exit_reason=pending.reason,
                    exit_gap=is_gap,
                ))
                result.exited_by_reason[pending.reason] = (
                    result.exited_by_reason.get(pending.reason, 0) + 1
                )
                result.exit_gap_fills += int(is_gap)
                position = None
                max_favorable_close_pips = 0.0
            pending = None

        # Тільки після open обробляємо completed close поточного бару.
        active = observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        if position is not None:
            reason = _exit_reason(
                observation.regime_phase,
                observation.regime,
                position.direction,
            )
            if position.direction in use_33_for:
                signed = 1 if position.direction == DIRECTION_UP else -1
                close_pips = signed * (
                    current_bar.close - position.entry_price
                ) / PIP
                max_favorable_close_pips = max(
                    max_favorable_close_pips, close_pips
                )
                if reason is None and max_favorable_close_pips > 0:
                    retained = max_favorable_close_pips * (
                        1 - EXIT_33_THRESHOLD
                    )
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
            result.sell_signals += int(direction == DIRECTION_DOWN)
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
    assert result.exits_signaled == (
        len(result.trades) + result.exit_pending_at_end
    )
    assert result.entry_signals == (
        result.entries + result.entry_skipped_gap
        + result.entry_unfilled_at_end + result.ignored_while_occupied
    )
    assert result.entry_signals == result.buy_signals + result.sell_signals
    return result


def _sample(
    start: datetime,
    offset: int,
    opening: float,
    closing: float,
    phase: str,
    regime: str,
) -> tuple[Bar, ObservedState]:
    """Побудувати синтетичний completed M15 без використання майбутнього."""
    timestamp = start + offset * M15
    sample_bar = Bar(
        timestamp, opening, max(opening, closing) + PIP,
        min(opening, closing) - PIP, closing,
    )
    return sample_bar, ObservedState(
        timestamp=timestamp,
        available_at=timestamp + M15,
        regime_phase=phase,
        regime=regime,
    )


def _check_trade_selection(
    baseline: Result,
    full33: Result,
    hybrid: Result,
) -> None:
    """Довести збіг кожної BUY/SELL угоди з потрібним еталоном."""
    all_results = (baseline, full33, hybrid)
    for other in all_results[1:]:
        assert other.entry_signals == baseline.entry_signals
        assert other.buy_signals == baseline.buy_signals
        assert other.sell_signals == baseline.sell_signals
        assert other.next_open_available == baseline.next_open_available
        assert other.entries == baseline.entries
        assert other.entry_skipped_gap == baseline.entry_skipped_gap
        assert other.ignored_while_occupied == baseline.ignored_while_occupied
        assert other.open_at_end == baseline.open_at_end
        assert other.exit_pending_at_end == baseline.exit_pending_at_end
        assert len(other.trades) == len(baseline.trades)
        assert other.incomplete_time_gaps == baseline.incomplete_time_gaps

    for original, all33, chosen in zip(
        baseline.trades, full33.trades, hybrid.trades, strict=True,
    ):
        assert original.entry_at == all33.entry_at == chosen.entry_at
        assert original.entry_price == all33.entry_price == chosen.entry_price
        assert original.direction == all33.direction == chosen.direction
        target = original if chosen.direction == DIRECTION_UP else all33
        assert chosen == target, "HYBRID_SELECTION_MISMATCH"

    selected_buy = sum(
        trade.pips for trade in baseline.trades
        if trade.direction == DIRECTION_UP
    )
    selected_sell = sum(
        trade.pips for trade in full33.trades
        if trade.direction == DIRECTION_DOWN
    )
    hybrid_total = sum(trade.pips for trade in hybrid.trades)
    assert math.isclose(
        selected_buy + selected_sell, hybrid_total, abs_tol=EPS,
    ), "GROSS_COMPONENT_MISMATCH"
    assert hybrid.exited_by_reason.get(EXIT_33_REASON, 0) == sum(
        trade.exit_reason == EXIT_33_REASON
        for trade in full33.trades
        if trade.direction == DIRECTION_DOWN
    )


def _synthetic_checks() -> None:
    """Перевірити BUY/SELL і пріоритет рішення після completed close."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    none = ALLIGATOR_REGIME_PHASE_NONE
    up = ALLIGATOR_REGIME_TREND_UP
    down = ALLIGATOR_REGIME_TREND_DOWN
    flat = ALLIGATOR_REGIME_FLAT
    synthetic_steps = [
        _sample(start, 0, 1.1000, 1.1000, active, up),
        _sample(start, 1, 1.1000, 1.1009, active, up),
        _sample(start, 2, 1.1009, 1.1005, active, up),
        _sample(start, 3, 1.1004, 1.1004, active, up),
        _sample(start, 4, 1.1003, 1.1003, ending, up),
        _sample(start, 5, 1.1002, 1.1002, none, flat),
        _sample(start, 6, 1.1002, 1.1002, active, down),
        _sample(start, 7, 1.1002, 1.0993, active, down),
        _sample(start, 8, 1.0993, 1.0997, active, down),
        _sample(start, 9, 1.0998, 1.0998, active, down),
        _sample(start, 10, 1.0999, 1.0999, ending, down),
        _sample(start, 11, 1.1000, 1.1000, none, flat),
    ]
    original = _simulate(synthetic_steps)
    no33 = _simulate_directional(synthetic_steps, use_33_for=frozenset())
    full33 = _simulate_variant(synthetic_steps, use_33=True)
    both = _simulate_directional(
        synthetic_steps, use_33_for=BOTH_DIRECTIONS,
    )
    hybrid = _simulate_directional(
        synthetic_steps, use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert no33 == original and both == full33
    assert len(hybrid.trades) == 2
    _check_trade_selection(original, full33, hybrid)
    assert hybrid.trades[0].exit_reason == "ENDING"
    assert hybrid.trades[0].exit_at == start + 5 * M15
    assert hybrid.trades[1].exit_reason == EXIT_33_REASON
    assert hybrid.trades[1].exit_at == start + 9 * M15

    # Intrabar high/low не повинні змінювати рішення SELL.
    altered = list(synthetic_steps)
    sell_bar, sell_state = altered[7]
    altered[7] = Bar(
        sell_bar.timestamp, sell_bar.open,
        sell_bar.high + 50 * PIP,
        sell_bar.low - 50 * PIP,
        sell_bar.close,
    ), sell_state
    altered_hybrid = _simulate_directional(
        altered, use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert altered_hybrid == hybrid

    # Відсутній суміжний open: пропущений entry, без підміни ціни.
    missing_open = [synthetic_steps[0], *synthetic_steps[2:]]
    skipped = _simulate_directional(
        missing_open, use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert skipped.entry_skipped_gap == 1
    assert skipped.entries == 1
    assert len(skipped.trades) == 1
    print("SYNTHETIC_DIRECTIONAL_HYBRID_CAUSALITY=OK")


def _run_period(
    label: str,
    filename: str,
    expected: tuple[int, ...],
    profile: WorkspaceAlligatorRuntimeProfile,
) -> None:
    """Три реальні Replay та незалежна попарна звірка входів."""
    path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source_count, selected_count, bars = _aggregate_m1(
        path, int(label[:4]), cutoff,
    )
    states = list(_states(bars, profile))
    baseline = _simulate(states)
    full33 = _simulate_variant(states, use_33=True)
    no33_copy = _simulate_directional(states, use_33_for=frozenset())
    full33_copy = _simulate_directional(
        states, use_33_for=BOTH_DIRECTIONS,
    )
    hybrid = _simulate_directional(
        states, use_33_for=HYBRID_33_DIRECTIONS,
    )
    hybrid_again = _simulate_directional(
        states, use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert baseline == no33_copy, f"T115_02_MISMATCH: {label}"
    assert full33 == full33_copy, f"T115_03_MISMATCH: {label}"
    assert hybrid == hybrid_again, f"HYBRID_NONDETERMINISTIC: {label}"
    assert (
        len(bars), baseline.entry_signals, baseline.buy_signals,
        baseline.sell_signals, baseline.next_open_available,
    ) == expected, f"T115_01_POPULATION_MISMATCH: {label}"
    _check_trade_selection(baseline, full33, hybrid)

    early = hybrid.exited_by_reason.get(EXIT_33_REASON, 0)
    expected_early = 233 if label == "2025" else 180
    assert early == expected_early, f"EXIT_33_COUNT_MISMATCH: {label}"
    print(
        f"PERIOD={label}|SOURCE_M1={source_count}|"
        f"SELECTED_M1={selected_count}|COMPLETED_M15={len(bars)}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"TREND_ORDERS|PERIOD={label}|ACTIVE={baseline.entry_signals}|"
        f"WITH_ENTRY={hybrid.entries}|"
        f"WITHOUT_ENTRY={baseline.entry_signals - hybrid.entries}|"
        f"CLOSED={len(hybrid.trades)}|OPEN_AT_END={hybrid.open_at_end}|"
        f"ENTRY_GAP_SKIPPED={hybrid.entry_skipped_gap}|"
        f"EXIT_GAP_FILLS={hybrid.exit_gap_fills}"
    )
    print(f"ALLIGATOR_ONLY|PERIOD={label}|{_metrics(baseline)}")
    print(f"ALLIGATOR_PLUS_33|PERIOD={label}|{_metrics(full33)}")
    print(f"HYBRID_BUY_ALLIGATOR_SELL_33|PERIOD={label}|{_metrics(hybrid)}")
    reason_counts = ",".join(
        f"{name}:{count}" for name, count
        in sorted(hybrid.exited_by_reason.items())
    )
    print(
        f"HYBRID_EXITS|PERIOD={label}|EARLY_SELL_33={early}|"
        f"ENDING={hybrid.exited_by_reason.get('ENDING', 0)}|"
        f"REASONS={reason_counts}"
    )
    for direction in (DIRECTION_UP, DIRECTION_DOWN):
        subset = [
            trade for trade in hybrid.trades
            if trade.direction == direction
        ]
        summary = math.fsum(trade.pips for trade in subset)
        print(
            f"HYBRID_DIRECTION={direction}|PERIOD={label}|"
            f"CLOSED={len(subset)}|GROSS_PIPS={summary:.2f}|"
            f"EARLY_33={sum(
                trade.exit_reason == EXIT_33_REASON for trade in subset
            )}|"
            f"EXIT_GAP_FILLS={sum(trade.exit_gap for trade in subset)}"
        )
    delta_base = math.fsum(trade.pips for trade in hybrid.trades) - math.fsum(
        trade.pips for trade in baseline.trades
    )
    delta_33 = math.fsum(trade.pips for trade in hybrid.trades) - math.fsum(
        trade.pips for trade in full33.trades
    )
    print(
        f"PAIRED_DELTA|PERIOD={label}|"
        f"HYBRID_MINUS_ALLIGATOR={delta_base:.2f}|"
        f"HYBRID_MINUS_ALL33={delta_33:.2f}"
    )
    print(
        f"T115_02_BASELINE_IDENTICAL={label}:OK|"
        f"T115_03_BASELINE_IDENTICAL={label}:OK|"
        f"HYBRID_TWICE_DETERMINISTIC={label}:OK|"
        f"HYBRID_ENTRY_PAIRS={label}:OK"
    )


def main() -> None:
    """Виконати ізольований дослід без зміни production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-09|TEST_ONLY|DIRECTIONAL_HYBRID_EXIT_REPLAY")
    print("HYBRID=BUY_ALLIGATOR_ENDING|SELL_33_OR_ENDING")
    print("33_PERCENT=HYPOTHESIS_ONLY|POST_HOC_VARIANT=True")
    print("ENTRY=NEXT_CONTIGUOUS_M15_OPEN|EXIT=NEXT_AVAILABLE_M15_OPEN")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print(
        "completed_bars_only=True|trade_decisions_look_ahead=False|"
        "broker_requests=0"
    )
    print("gross_mid_only=True|spread_commission_slippage_included=False")
    print("production_changed=False|md7_changed=False")
    print("T115_09_DIRECTIONAL_HYBRID_EXIT_REPLAY=OK")


if __name__ == "__main__":
    main()
