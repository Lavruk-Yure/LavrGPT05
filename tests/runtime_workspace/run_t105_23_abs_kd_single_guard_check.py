"""run_t105_23_abs_kd_single_guard_check.py — модуль T105-23.

Runner виконує один контрольований TEST_ONLY hypothesis test для заздалегідь
зафіксованого порогу ``abs_KD >= 20.0``. Він повторно використовує factual
production Replay і causal Donchian-rejected population із T105-21/T105-22:
production Candidate F, чинний Stochastic 14/1/3 CURRENT_BAR gate, а потім
TEST_ONLY Donchian N20 classification лише за completed M15 bars.

Для кожного періоду runner порівнює повну Donchian-rejected population із
counterfactual survivors ``abs_KD < 20.0`` та removed group
``abs_KD >= 20.0``. Factual outcome і PnL використовуються тільки як labels
відомих production trades; окрема execution model не запускається.

Runner перевіряє counts, canonical T105-22 medians, loss capture, winner damage
та removed PnL, але не виконує threshold sweep, не створює production filter і
не змінює Candidate F, Stochastic, Donchian wiring, PD, SL/TP або exit stack.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from run_t105_22_donchian_rejected_discriminator_check import (
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    PERIODS,
    RejectedSurvivorRow,
    _production_hashes,
    _run_period,
)

TEST_ID = "T105-23"
MODE = "RM105_T105_23_ABS_KD_SINGLE_GUARD_TEST_ONLY"
ABS_KD_THRESHOLD = 20.0
EXPECTED_BASELINE = {
    "2025": (22, 16, 6, 0, -0.62),
    "2026": (11, 9, 2, 0, 2.57),
}
EXPECTED_MEDIANS = {
    "2025": {OUTCOME_WIN: 14.6492, OUTCOME_LOSS: 19.7562},
    "2026": {OUTCOME_WIN: 14.5775, OUTCOME_LOSS: 24.6291},
}


@dataclass(frozen=True, slots=True)
class ScenarioStats:
    """Описові метрики однієї factual або counterfactual trade group."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float | None


@dataclass(frozen=True, slots=True)
class PeriodSelection:
    """Підсумок single-threshold selection diagnostic одного періоду."""

    loss_capture_rate: float
    winner_damage_rate: float
    removed_net: float


def _stats(rows: tuple[RejectedSurvivorRow, ...]) -> ScenarioStats:
    """Обчислити однакові descriptive metrics для заданої групи trades."""

    counts = Counter(row.outcome for row in rows)
    gross_profit = math.fsum(max(row.trade.final_profit, 0.0) for row in rows)
    gross_loss = -math.fsum(min(row.trade.final_profit, 0.0) for row in rows)
    return ScenarioStats(
        trades=len(rows),
        wins=counts[OUTCOME_WIN],
        losses=counts[OUTCOME_LOSS],
        break_even=counts[OUTCOME_BREAK_EVEN],
        net=math.fsum(row.trade.final_profit for row in rows),
        profit_factor=None if gross_loss == 0.0 else gross_profit / gross_loss,
    )


def _stats_line(name: str, item: ScenarioStats) -> str:
    """Сформувати стабільний console-рядок метрик сценарію."""

    profit_factor = (
        "NONE" if item.profit_factor is None else f"{item.profit_factor:.4f}"
    )
    return (
        f"    {name}=trades:{item.trades},W:{item.wins},L:{item.losses},"
        f"BE:{item.break_even},net:{item.net:+.2f},pf:{profit_factor}"
    )


def _median_abs_kd(
    rows: tuple[RejectedSurvivorRow, ...],
    outcome: str,
) -> float:
    """Повернути медіану готового causal abs_KD для outcome group."""

    values = sorted(abs(row.signed_kd) for row in rows if row.outcome == outcome)
    assert values
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def _assert_population(
    period: str,
    rows: tuple[RejectedSurvivorRow, ...],
) -> ScenarioStats:
    """Зупинити тест, якщо factual population або T105-22 medians змінилися."""

    baseline = _stats(rows)
    expected = EXPECTED_BASELINE[period]
    assert (
        baseline.trades,
        baseline.wins,
        baseline.losses,
        baseline.break_even,
    ) == expected[:4]
    assert math.isclose(baseline.net, expected[4], rel_tol=0.0, abs_tol=0.005)
    for outcome in (OUTCOME_WIN, OUTCOME_LOSS):
        actual_median = _median_abs_kd(rows, outcome)
        assert math.isclose(
            actual_median,
            EXPECTED_MEDIANS[period][outcome],
            rel_tol=0.0,
            abs_tol=0.00005,
        )
    return baseline


def _row_line(row: RejectedSurvivorRow) -> str:
    """Сформувати factual row для trade, видаленого single guard."""

    return (
        f"      {row.trade.signal_timestamp.isoformat()}|{row.trade.direction}|"
        f"{row.outcome}|{row.trade.final_profit:+.2f}|"
        f"{abs(row.signed_kd):.4f}|{row.percent_k:.4f}|{row.percent_d:.4f}|"
        f"{row.trade.close_reason}"
    )


def _print_period(
    period: str,
    rows: tuple[RejectedSurvivorRow, ...],
) -> PeriodSelection:
    """Надрукувати baseline, selection groups, rates та removed factual rows."""

    baseline = _assert_population(period, rows)
    survivors = tuple(
        row for row in rows if abs(row.signed_kd) < ABS_KD_THRESHOLD
    )
    removed = tuple(
        row for row in rows if abs(row.signed_kd) >= ABS_KD_THRESHOLD
    )
    survivor_stats = _stats(survivors)
    removed_stats = _stats(removed)
    assert baseline.trades == survivor_stats.trades + removed_stats.trades
    assert baseline.wins == survivor_stats.wins + removed_stats.wins
    assert baseline.losses == survivor_stats.losses + removed_stats.losses
    assert baseline.break_even == survivor_stats.break_even + removed_stats.break_even

    loss_capture_rate = removed_stats.losses / baseline.losses
    winner_damage_rate = removed_stats.wins / baseline.wins
    removed_loss_pnl = math.fsum(
        row.trade.final_profit for row in removed if row.outcome == OUTCOME_LOSS
    )
    removed_win_pnl = math.fsum(
        row.trade.final_profit for row in removed if row.outcome == OUTCOME_WIN
    )
    print(f"  period={period}")
    print(
        "    hypothesis_medians="
        f"WIN:{_median_abs_kd(rows, OUTCOME_WIN):.4f},"
        f"LOSS:{_median_abs_kd(rows, OUTCOME_LOSS):.4f},WIN_LT_LOSS=True"
    )
    print(_stats_line("BASELINE_REJECTED", baseline))
    print(_stats_line("ABS_KD_LT_20_SURVIVORS", survivor_stats))
    print(_stats_line("ABS_KD_GE_20_REJECTED", removed_stats))
    print(
        "    DELTA_SELECTION="
        f"removed_trades:{removed_stats.trades},removed_wins:{removed_stats.wins},"
        f"removed_losses:{removed_stats.losses},removed_net:{removed_stats.net:+.2f}"
    )
    print(
        "    capture_damage="
        f"loss_capture_rate:{loss_capture_rate:.4f},"
        f"winner_damage_rate:{winner_damage_rate:.4f},"
        f"removed_loss_pnl:{removed_loss_pnl:+.2f},"
        f"removed_win_pnl:{removed_win_pnl:+.2f}"
    )
    print("    ABS_KD_GE_20_ROWS")
    print("      timestamp|side|outcome|pnl|abs_KD|K|D|close_reason")
    for row in removed:
        print(_row_line(row))
    return PeriodSelection(
        loss_capture_rate=loss_capture_rate,
        winner_damage_rate=winner_damage_rate,
        removed_net=removed_stats.net,
    )


def main() -> None:
    """Запустити T105-23 без sweep, execution simulation і production decision."""

    production_before = _production_hashes()
    print("T105-23 abs_KD Single Guard Check")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print(f"  threshold={ABS_KD_THRESHOLD:.1f}")
    print("  rule=ABS_KD_GE_20_GUARD_REJECT__ABS_KD_LT_20_GUARD_ALLOW")
    print("  execution_model_run=False")
    selections = {
        spec.code: _print_period(spec.code, _run_period(spec)) for spec in PERIODS
    }
    print("  CROSS_PERIOD_ACCEPTANCE_DIAGNOSTIC")
    for period in ("2025", "2026"):
        item = selections[period]
        print(
            f"    {period}=loss_capture_rate:{item.loss_capture_rate:.4f},"
            f"winner_damage_rate:{item.winner_damage_rate:.4f},"
            f"net_removed:{item.removed_net:+.2f}"
        )

    assert _production_hashes() == production_before
    print("  threshold_sweep_performed=False")
    print("  single_threshold_predeclared=True")
    print(f"  threshold={ABS_KD_THRESHOLD:.1f}")
    print("  outcome_used_as_label_only=True")
    print("  entry_feature_abs_KD_causal=True")
    print("  entry_features_future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  production_stochastic_gate_active=True")
    print("  donchian_gate_test_only=True")
    print("  abs_kd_guard_test_only=True")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_23_ABS_KD_SINGLE_GUARD=OK")


if __name__ == "__main__":
    main()
