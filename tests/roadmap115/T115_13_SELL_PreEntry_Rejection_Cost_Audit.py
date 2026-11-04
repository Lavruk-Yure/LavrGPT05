# -*- coding: utf-8 -*-
"""RoadMap115 / T115-13 — ціна відхилення SELL за pre-entry рухом.

TEST_ONLY. Критерій сформовано POST HOC після T115-12:
три суміжні завершені M15 перед сигналом ACTIVE мають показати
рух униз за close. Якщо зміна <= 0 pip, SELL пропускаємо.
Якщо три попередні суміжні бари недоступні, SELL залишаємо.

Рішення приймається виключно на completed ACTIVE signal close.
BUY та гібридні виходи T115-09 не змінюються. Результати
2025/2026 НЕ є незалежною out-of-sample перевіркою.
Витрати 0.40 pip за завершену угоду — гіпотетичний сценарій T115-10.
Жодних змін production/MD7, MACD або broker requests.
"""

from __future__ import annotations

import math
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
    DIRECTION_DOWN,
    DIRECTION_UP,
    PIP,
    ClosedTrade,
    OpenPosition,
    PendingAction,
    Result,
    _direction,
    _exit_reason,
    _fingerprint,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    EXIT_33_THRESHOLD,
)
from T115_09_Directional_Hybrid_Exit_Replay import (  # noqa: E402
    HYBRID_33_DIRECTIONS,
    _simulate_directional,
)
from T115_10_Directional_Hybrid_Cost_Sensitivity import (
    SCENARIOS,
    CostScenario,
)
from T115_10_Directional_Hybrid_Cost_Sensitivity import (  # noqa: E402
    _metrics as _cost_metrics,
)
from T115_12_SELL_Failed_Development_Anatomy_FIXED import (  # noqa: E402
    FAILED,
    Evidence,
    Observation,
    _audit,
    _prior_three_move,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_TREND_DOWN,
    WorkspaceAlligatorRuntimeProfile,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-7
COST = next(item for item in SCENARIOS if item.name == "MID_040")


@dataclass(frozen=True, slots=True)
class GateCounts:
    """Причинний облік кандидатів на момент завершеного сигналу."""

    rejected_signals: int
    unknown_history_signals: int
    accepted_sell_signals: int


def _reject_sell(
    steps: list[tuple[Bar, Observation]],
    signal_index: int,
) -> bool:
    """Лише відомі на signal close M15; unknown не відхиляємо."""
    previous_move = _prior_three_move(steps, signal_index)
    return previous_move is not None and previous_move <= EPS


def _simulate_gated(
    steps: list[tuple[Bar, Observation]],
) -> tuple[Result, GateCounts]:
    """Контрольний Replay: лише доданий causal SELL entry gate.

    Інші правила — дослівно за контрактом T115-09. Вихід гібрида
    після completed close, виконання на next available open.
    """
    result = Result()
    previous_bar_at: datetime | None = None
    previous_phase: str | None = None
    last_candidate_available_at: datetime | None = None
    pending: PendingAction | None = None
    position: OpenPosition | None = None
    max_favorable_close_pips = 0.0
    rejected = unknown = accepted_sell = 0

    for index, (bar, observation) in enumerate(steps):
        assert observation.timestamp == bar.timestamp
        assert observation.available_at == bar.timestamp + M15
        if previous_bar_at is not None:
            assert bar.timestamp > previous_bar_at
            if bar.timestamp != previous_bar_at + M15:
                result.incomplete_time_gaps += 1
        previous_bar_at = bar.timestamp

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
                realized = signed * (bar.open - position.entry_price) / PIP
                result.trades.append(
                    ClosedTrade(
                        direction=position.direction,
                        entry_at=position.entry_at,
                        exit_at=bar.timestamp,
                        entry_price=position.entry_price,
                        exit_price=bar.open,
                        pips=realized,
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

        # Цей completed close доступний лише після поточного open.
        active = observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        if position is not None:
            reason = _exit_reason(
                observation.regime_phase,
                observation.regime,
                position.direction,
            )
            if position.direction in HYBRID_33_DIRECTIONS:
                signed = 1 if position.direction == DIRECTION_UP else -1
                close_pips = signed * (bar.close - position.entry_price) / PIP
                max_favorable_close_pips = max(
                    max_favorable_close_pips,
                    close_pips,
                )
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
            result.sell_signals += int(direction == DIRECTION_DOWN)
            last_candidate_available_at = observation.available_at
            if position is None and pending is None:
                if direction == DIRECTION_DOWN:
                    known_move = _prior_three_move(steps, index)
                    if known_move is None:
                        unknown += 1
                    elif _reject_sell(steps, index):
                        rejected += 1
                        previous_phase = observation.regime_phase
                        continue
                    accepted_sell += 1
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
    assert result.exits_signaled == (len(result.trades) + result.exit_pending_at_end)
    assert result.entry_signals == (
        result.entries
        + result.entry_skipped_gap
        + result.entry_unfilled_at_end
        + result.ignored_while_occupied
        + rejected
    )
    assert result.entry_signals == result.buy_signals + result.sell_signals
    assert accepted_sell + rejected == (
        result.sell_signals - result.ignored_while_occupied
    )
    return result, GateCounts(rejected, unknown, accepted_sell)


def _synthetic_checks() -> None:
    """Перевірити відмову, допуск, unknown і причинність high/low."""
    from T115_09_Directional_Hybrid_Exit_Replay import _sample

    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    down = ALLIGATOR_REGIME_TREND_DOWN

    # Попередні три completed close: рух угору -> відмова SELL.
    bad = [
        _sample(start, i, close, close, "STARTING", down)
        for i, close in enumerate((1.1000, 1.1001, 1.1002))
    ]
    bad.extend(
        (
            _sample(start, 3, 1.1002, 1.1003, active, down),
            _sample(start, 4, 1.1003, 1.1004, active, down),
            _sample(start, 5, 1.1004, 1.1004, ending, down),
            _sample(start, 6, 1.1004, 1.1004, ending, down),
        )
    )
    full = _simulate_directional(bad, use_33_for=HYBRID_33_DIRECTIONS)
    filtered, counters = _simulate_gated(bad)
    assert len(full.trades) == 1 and not filtered.trades
    assert counters.rejected_signals == 1
    assert _reject_sell(bad, 3)

    # За тим самим шаблоном рух униз -> SELL не змінюється.
    good = list(bad)
    for i, price in enumerate((1.1010, 1.1009, 1.1008)):
        good[i] = _sample(start, i, price, price, "STARTING", down)
    good[3] = _sample(start, 3, 1.1008, 1.1005, active, down)
    same, good_counts = _simulate_gated(good)
    assert same == _simulate_directional(
        good,
        use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert good_counts.rejected_signals == 0
    assert not _reject_sell(good, 3)

    # Немає 3 суміжних M15 -> не робити висновок із прогалини.
    unknown = bad[2:]
    allowed, unknown_counts = _simulate_gated(unknown)
    original = _simulate_directional(
        unknown,
        use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert allowed == original
    assert unknown_counts.unknown_history_signals == 1

    # Майбутній intrabar high/low не впливає на рішення entry gate.
    altered = list(bad)
    candle, obs = altered[4]
    altered[4] = (
        Bar(
            candle.timestamp,
            candle.open,
            candle.high + 100 * PIP,
            candle.low - 100 * PIP,
            candle.close,
        ),
        obs,
    )
    assert _simulate_gated(bad) == _simulate_gated(altered)

    # Зміна наступного close не впливає на gate в signal bar.
    late = list(bad)
    late[4] = _sample(start, 4, 1.1003, 1.0950, active, down)
    assert _reject_sell(late, 3) == _reject_sell(bad, 3)
    assert _simulate_gated(late)[1] == counters
    print("SYNTHETIC_PRE_ENTRY_SELL_GATE_CAUSALITY=OK")


def _report_metrics(
    label: str,
    variant: str,
    trades: list[ClosedTrade],
    scenario: CostScenario,
) -> None:
    """Однакові метрики baseline і відхилень, closed-only."""
    result = _cost_metrics(trades, scenario)
    print(
        f"METRICS|PERIOD={label}|VARIANT={variant}|"
        f"SCENARIO={scenario.name}|CLOSED={result.closed}|"
        f"WINS={result.wins}|LOSSES={result.losses}|FLAT={result.flat}|"
        f"WIN_RATE_PCT={result.win_rate_pct:.2f}|"
        f"GROSS_PIPS={result.gross_pips:.2f}|"
        f"NET_PIPS={result.net_pips:.2f}|"
        f"COST_PIPS={result.costs_pips:.2f}|"
        f"PF_NET={result.profit_factor_net:.3f}|"
        f"MAX_CLOSED_DD_PIPS={result.max_closed_dd_net_pips:.2f}"
    )


def _run_period(
    label: str,
    filename: str,
    expected: tuple[int, ...],
    profile: WorkspaceAlligatorRuntimeProfile,
) -> None:
    """Незмінний baseline, окремий causal Replay і paired attribution."""
    path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source, selected, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    assert len(bars) == expected[0]
    steps = list(_states(bars, profile))
    baseline = _simulate_directional(
        steps,
        use_33_for=HYBRID_33_DIRECTIONS,
    )
    gated, gate = _simulate_gated(steps)
    assert (gated, gate) == _simulate_gated(steps)
    assert (
        len(bars),
        baseline.entry_signals,
        baseline.buy_signals,
        baseline.sell_signals,
        baseline.next_open_available,
    ) == expected
    reference = (
        (800, -214.80, 408, 392)
        if label == "2025"
        else (
            505,
            190.90,
            277,
            228,
        )
    )
    count, gross, sell_count, buy_count = reference
    assert len(baseline.trades) == count
    assert math.isclose(
        math.fsum(t.pips for t in baseline.trades),
        gross,
        abs_tol=0.005,
    )
    assert sum(t.direction == DIRECTION_DOWN for t in baseline.trades) == (sell_count)
    assert sum(t.direction == DIRECTION_UP for t in baseline.trades) == (buy_count)

    # Окрема популяція T115-12 використовується тільки для атрибуції.
    evidence: tuple[Evidence, ...] = _audit(steps)
    evidence_by_entry = {row.entry_at: row for row in evidence}
    baseline_by_entry = {trade.entry_at: trade for trade in baseline.trades}
    assert len(baseline_by_entry) == len(baseline.trades)
    assert len(evidence_by_entry) == sell_count
    assert all(entry in baseline_by_entry for entry in evidence_by_entry)

    kept_by_entry = {trade.entry_at: trade for trade in gated.trades}
    assert len(kept_by_entry) == len(gated.trades)
    assert all(
        entry in baseline_by_entry and trade == baseline_by_entry[entry]
        for entry, trade in kept_by_entry.items()
    )
    rejected_trades = [
        trade for trade in baseline.trades if trade.entry_at not in kept_by_entry
    ]
    assert all(t.direction == DIRECTION_DOWN for t in rejected_trades)
    assert len(baseline.trades) == (len(gated.trades) + len(rejected_trades))
    assert all(
        t.entry_at in kept_by_entry
        for t in baseline.trades
        if t.direction == DIRECTION_UP
    )
    for trade in baseline.trades:
        if trade.direction != DIRECTION_DOWN:
            continue
        known = evidence_by_entry[trade.entry_at].prior_three_to_signal_pips
        expect_reject = known is not None and known <= EPS
        assert (trade in rejected_trades) == expect_reject

    rejected_evidence = [evidence_by_entry[t.entry_at] for t in rejected_trades]
    rejected_failed = sum(x.group == FAILED for x in rejected_evidence)
    expected_gate = (
        (216, -236.00, 63, 584) if label == "2025" else (138, 13.90, 37, 367)
    )
    assert len(rejected_trades) == expected_gate[0]
    assert math.isclose(
        math.fsum(t.pips for t in rejected_trades),
        expected_gate[1],
        abs_tol=0.005,
    )
    assert rejected_failed == expected_gate[2]
    assert len(gated.trades) == expected_gate[3]
    all_failed = sum(x.group == FAILED for x in evidence)
    original_sell = [t for t in baseline.trades if t.direction == DIRECTION_DOWN]
    retained_sell = [t for t in gated.trades if t.direction == DIRECTION_DOWN]
    rejected_wins = sum(t.pips > EPS for t in rejected_trades)
    rejected_losses = sum(t.pips < -EPS for t in rejected_trades)
    rejected_flat = len(rejected_trades) - rejected_wins - rejected_losses
    rejected_profit = math.fsum(t.pips for t in rejected_trades if t.pips > EPS)
    rejected_loss = math.fsum(t.pips for t in rejected_trades if t.pips < -EPS)
    assert math.isclose(
        math.fsum(t.pips for t in baseline.trades)
        - math.fsum(t.pips for t in gated.trades),
        math.fsum(t.pips for t in rejected_trades),
        abs_tol=1e-6,
    )

    print(
        f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"POPULATION|PERIOD={label}|SELL_SIGNALS="
        f"{baseline.sell_signals}|SELL_CLOSED={sell_count}|"
        f"BUY_CLOSED={buy_count}|BASELINE_CLOSED={count}|"
        f"GATED_CLOSED={len(gated.trades)}|"
        f"BASELINE_OPEN_END={baseline.open_at_end}|"
        f"GATED_OPEN_END={gated.open_at_end}"
    )
    print(
        f"ENTRY_GATE|PERIOD={label}|RULE=PRIOR3_CLOSE_SELL_MOVE_LE_0|"
        f"REJECTED_SIGNALS={gate.rejected_signals}|"
        f"UNKNOWN_HISTORY_SIGNALS_KEPT={gate.unknown_history_signals}|"
        f"ACCEPTED_SELL_SIGNALS={gate.accepted_sell_signals}|"
        f"REJECTED_CLOSED_SELL={len(rejected_trades)}|"
        f"RETAINED_CLOSED_SELL={len(retained_sell)}|"
        f"ENTRY_GAPS_GATED={gated.entry_skipped_gap}|"
        f"IGNORED_GATED={gated.ignored_while_occupied}"
    )
    print(
        f"REJECTION_COST|PERIOD={label}|REJECTED_WIN={rejected_wins}|"
        f"REJECTED_LOSS={rejected_losses}|REJECTED_FLAT={rejected_flat}|"
        f"PROFITABLE_SELL_PIPS_FOREGONE={rejected_profit:.2f}|"
        f"LOSING_SELL_PIPS_AVOIDED={-rejected_loss:.2f}|"
        f"REJECTED_SELL_GROSS_PIPS="
        f"{math.fsum(t.pips for t in rejected_trades):.2f}|"
        f"REJECTED_FAILED_NO_FAVORABLE={rejected_failed}|"
        f"FAILED_ALL={all_failed}|FAILED_RETAINED="
        f"{all_failed - rejected_failed}"
    )
    for scenario in (SCENARIOS[0], COST):
        _report_metrics(label, "HYBRID_BASE", baseline.trades, scenario)
        _report_metrics(label, "HYBRID_GATE", gated.trades, scenario)
        _report_metrics(label, "SELL_BASE", original_sell, scenario)
        _report_metrics(label, "SELL_GATE", retained_sell, scenario)
        base_result = _cost_metrics(baseline.trades, scenario)
        gated_result = _cost_metrics(gated.trades, scenario)
        saved_cost = (base_result.closed - gated_result.closed) * scenario.total_pips
        print(
            f"PAIRED_DELTA|PERIOD={label}|SCENARIO={scenario.name}|"
            f"NET_GATE_MINUS_BASE="
            f"{gated_result.net_pips - base_result.net_pips:.2f}|"
            f"CLOSED_TRADES_REMOVED="
            f"{base_result.closed - gated_result.closed}|"
            f"COST_SAVED_PIPS={saved_cost:.2f}"
        )
    print(
        f"REPLAY_TWICE_DETERMINISTIC={label}:OK|"
        f"T115_09_GROSS_BASELINE={label}:OK|"
        f"T115_12_ENTRY_FEATURES={label}:OK|"
        f"RETAINED_TRADES_IDENTICAL={label}:OK"
    )


def main() -> None:
    """Перевірити одне post-hoc правило, без змін production і MD7."""
    protected = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in protected}
    print("T115-13|TEST_ONLY|SELL_PRE_ENTRY_REJECTION_COST_AUDIT")
    print("ENTRY_GATE=PRIOR3_COMPLETED_M15_CLOSE_SELL_MOVE_LE_0")
    print("UNKNOWN_PRIOR3=KEEP|RULE_SELECTED_POST_HOC=True")
    print("HYBRID=BUY_ENDING_SELL_33_OR_ENDING|COSTS=HYPOTHETICAL")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {
        str(path): _fingerprint(path) for path in protected
    }, "PRODUCTION_FINGERPRINT_CHANGED"
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|TEST_ONLY=True|post_hoc_variant=True")
    print("costs_hypothetical=True|actual_bid_ask_quotes_used=False")
    print("production_changed=False|md7_changed=False")
    print("T115_13_SELL_PRE_ENTRY_REJECTION_COST_AUDIT=OK")


if __name__ == "__main__":
    main()
