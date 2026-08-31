"""run_t105_22_donchian_rejected_discriminator_check.py — модуль T105-22.

Runner виконує окремий фактичний ``WorkspaceRuntime`` Replay для 2025 і 2026
через зареєстрований production Candidate F із чинним Stochastic 14/1/3
CURRENT_BAR reject. Із готової причинно-часової вибірки T105-21 він аналізує
лише production Stochastic survivors, які TEST_ONLY Donchian N20 класифікує
як REJECT за попередніми 20 завершеними M15 bars без поточного signal bar.

Для WIN і LOSS порівнюються вже наявні entry-time features: K, D, signed та
absolute K-D, normalized Alligator opening, opening delta, normalized slope,
direction, regime і line order. Runner друкує descriptive quartiles,
categorical groups, напрямки медіан, IQR overlap та задані factual trade rows.
Outcome і PnL використовуються виключно як labels після завершення Replay.

POTENTIAL_DISCRIMINATORS означає лише однаковий напрямок медіан у двох
періодах. Runner не створює entry filter, не підбирає threshold, не виконує
ML/regression і не змінює production logic, PD, SL/TP, recovery або exit stack.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass

from run_algorithm_workspace_replay_virtual_execution_check import BrokerRequestProbe
from run_t105_10_pd_35_production_regression_check import PeriodSpec, _workspace
from run_t105_15_stochastic_entry_anatomy_check import (
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    _assert_geometry,
    _assert_metrics,
    _assert_policy,
    _assert_stochastic_path,
    _broker_execution_attempted,
)
from run_t105_21_donchian_rejected_anatomy_check import (
    EXPECTED_REJECTED,
    EXPECTED_SURVIVORS,
    RejectedSurvivorAnatomyRuntime,
    RejectedSurvivorRow,
    _production_hashes,
    _rejected_rows,
)

from core.workspace_algorithm import create_registered_workspace_algorithm

TEST_ID = "T105-22"
MODE = "RM105_T105_22_DONCHIAN_REJECTED_DISCRIMINATOR_TEST_ONLY"
EXPECTED_OUTCOMES = {
    "2025": {OUTCOME_WIN: 16, OUTCOME_LOSS: 6, OUTCOME_BREAK_EVEN: 0},
    "2026": {OUTCOME_WIN: 9, OUTCOME_LOSS: 2, OUTCOME_BREAK_EVEN: 0},
}
NUMERIC_FEATURES = (
    "K",
    "D",
    "signed_KD",
    "abs_KD",
    "normalized_opening",
    "opening_delta",
    "normalized_slope",
)
CATEGORICAL_FEATURES = ("direction", "regime", "line_order")


@dataclass(frozen=True, slots=True)
class FeatureStats:
    """Описова статистика однієї числової ознаки для групи результатів."""

    n: int
    median: float
    p25: float
    p75: float
    minimum: float
    maximum: float


def _numeric_value(row: RejectedSurvivorRow, feature: str) -> float:
    """Повернути готову причинно-часову ознаку без нового розрахунку сигналу."""

    values = {
        "K": row.percent_k,
        "D": row.percent_d,
        "signed_KD": row.signed_kd,
        "abs_KD": abs(row.signed_kd),
        "normalized_opening": row.normalized_opening,
        "opening_delta": row.opening_delta,
        "normalized_slope": row.normalized_slope,
    }
    return float(values[feature])


def _categorical_value(row: RejectedSurvivorRow, feature: str) -> str:
    """Повернути категоріальну ознаку фактичної відхиленої угоди."""

    values = {
        "direction": row.trade.direction,
        "regime": row.regime,
        "line_order": row.line_order,
    }
    return values[feature]


def _feature_stats(
    rows: tuple[RejectedSurvivorRow, ...],
    feature: str,
) -> FeatureStats:
    """Обчислити описові медіану, квартилі та діапазон однієї ознаки."""

    values = sorted(_numeric_value(row, feature) for row in rows)
    assert len(values) >= 2
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return FeatureStats(
        n=len(values),
        median=float(statistics.median(values)),
        p25=float(quartiles[0]),
        p75=float(quartiles[2]),
        minimum=values[0],
        maximum=values[-1],
    )


def _stats_line(outcome: str, item: FeatureStats) -> str:
    """Сформувати стабільний рядок консолі для групи результатів."""

    return (
        f"        {outcome}=n:{item.n},median:{item.median:+.6f},"
        f"p25:{item.p25:+.6f},p75:{item.p75:+.6f},"
        f"min:{item.minimum:+.6f},max:{item.maximum:+.6f}"
    )


def _run_period(spec: PeriodSpec) -> tuple[RejectedSurvivorRow, ...]:
    """Виконати фактичний production Replay і повернути вибірку T105-21."""

    broker_probe = BrokerRequestProbe()
    runtime = RejectedSurvivorAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
    )
    _assert_policy(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_metrics(spec, runtime)
    _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    rows = _rejected_rows(runtime)
    counts = Counter(row.outcome for row in rows)
    assert runtime.historical_summary is not None
    assert runtime.historical_summary.opened_trades == EXPECTED_SURVIVORS[spec.code]
    assert len(rows) == EXPECTED_REJECTED[spec.code]
    assert all(
        counts[outcome] == expected
        for outcome, expected in EXPECTED_OUTCOMES[spec.code].items()
    )
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    assert session.completed
    assert all(event.timeframe == "M15" for event in session.events)
    return rows


def _numeric_stats(
    rows_by_period: dict[str, tuple[RejectedSurvivorRow, ...]],
) -> dict[str, dict[str, dict[str, FeatureStats]]]:
    """Надрукувати числову діагностику WIN і LOSS для обох періодів."""

    result: dict[str, dict[str, dict[str, FeatureStats]]] = {}
    print("  NUMERIC_FEATURES")
    for period, rows in rows_by_period.items():
        result[period] = {}
        print(f"    period={period}")
        for feature in NUMERIC_FEATURES:
            result[period][feature] = {}
            print(f"      feature={feature}")
            for outcome in (OUTCOME_WIN, OUTCOME_LOSS):
                group = tuple(row for row in rows if row.outcome == outcome)
                item = _feature_stats(group, feature)
                result[period][feature][outcome] = item
                print(_stats_line(outcome, item))
    return result


def _categorical_stats(
    rows_by_period: dict[str, tuple[RejectedSurvivorRow, ...]],
) -> None:
    """Надрукувати описові групи напрямку, режиму та порядку ліній."""

    print("  CATEGORICAL_FEATURES")
    for period, rows in rows_by_period.items():
        print(f"    period={period}")
        for feature in CATEGORICAL_FEATURES:
            print(f"      feature={feature}")
            values = sorted(_categorical_value(row, feature) for row in rows)
            for value in sorted(set(values)):
                group = tuple(
                    row for row in rows if _categorical_value(row, feature) == value
                )
                counts = Counter(row.outcome for row in group)
                net = math.fsum(row.trade.final_profit for row in group)
                print(
                    f"        {value}=trades:{len(group)},W:{counts[OUTCOME_WIN]},"
                    f"L:{counts[OUTCOME_LOSS]},BE:{counts[OUTCOME_BREAK_EVEN]},"
                    f"net:{net:+.2f}"
                )


def _median_direction(win: FeatureStats, loss: FeatureStats) -> str:
    """Описати напрямок різниці медіан без створення порогу."""

    if win.median > loss.median:
        return "WIN_GT_LOSS"
    if win.median < loss.median:
        return "WIN_LT_LOSS"
    return "EQUAL"


def _iqr_overlap(win: FeatureStats, loss: FeatureStats) -> bool:
    """Перевірити перетин включних IQR-інтервалів WIN і LOSS."""

    return max(win.p25, loss.p25) <= min(win.p75, loss.p75)


def _separation(
    stats: dict[str, dict[str, dict[str, FeatureStats]]],
) -> None:
    """Порівняти напрямки медіан та IQR між 2025 і 2026."""

    potential: list[str] = []
    rejected: list[str] = []
    print("  CROSS_PERIOD_SEPARATION")
    for feature in NUMERIC_FEATURES:
        win_2025 = stats["2025"][feature][OUTCOME_WIN]
        loss_2025 = stats["2025"][feature][OUTCOME_LOSS]
        win_2026 = stats["2026"][feature][OUTCOME_WIN]
        loss_2026 = stats["2026"][feature][OUTCOME_LOSS]
        direction_2025 = _median_direction(win_2025, loss_2025)
        direction_2026 = _median_direction(win_2026, loss_2026)
        consistent = direction_2025 == direction_2026
        if consistent:
            potential.append(feature)
        else:
            rejected.append(feature)
        print(
            f"    {feature}=median_direction_2025:{direction_2025},"
            f"median_direction_2026:{direction_2026},"
            f"cross_period_direction_consistent:{consistent},"
            f"IQR_overlap_2025:{_iqr_overlap(win_2025, loss_2025)},"
            f"IQR_overlap_2026:{_iqr_overlap(win_2026, loss_2026)}"
        )
    print("  POTENTIAL_DISCRIMINATORS=" + (",".join(potential) or "NONE"))
    print("  REJECTED_DISCRIMINATORS=" + (",".join(rejected) or "NONE"))


def _row_line(row: RejectedSurvivorRow) -> str:
    """Сформувати компактний причинно-часовий рядок діагностики."""

    return (
        f"      {row.trade.signal_timestamp.isoformat()}|{row.trade.direction}|"
        f"{row.outcome}|{row.trade.final_profit:+.2f}|{row.percent_k:.4f}|"
        f"{row.percent_d:.4f}|{row.signed_kd:+.4f}|{abs(row.signed_kd):.4f}|"
        f"{row.normalized_opening:.6f}|{row.opening_delta:+.6f}|"
        f"{row.normalized_slope:.6f}|{row.regime}|{row.line_order}"
    )


def _row_diagnostics(
    rows_by_period: dict[str, tuple[RejectedSurvivorRow, ...]],
) -> None:
    """Надрукувати задані фактичні рядки 2025 і всі відхилені рядки 2026."""

    header = (
        "      timestamp|side|outcome|pnl|K|D|signed_KD|abs_KD|"
        "normalized_opening|opening_delta|normalized_slope|regime|line_order"
    )
    rows_2025 = rows_by_period["2025"]
    top_wins = sorted(
        (row for row in rows_2025 if row.outcome == OUTCOME_WIN),
        key=lambda row: row.trade.final_profit,
        reverse=True,
    )[:5]
    losses = sorted(
        (row for row in rows_2025 if row.outcome == OUTCOME_LOSS),
        key=lambda row: row.trade.signal_timestamp,
    )
    print("  ROWS_2025_TOP_5_WIN")
    print(header)
    for row in top_wins:
        print(_row_line(row))
    print("  ROWS_2025_ALL_LOSS")
    print(header)
    for row in losses:
        print(_row_line(row))

    print("  ROWS_2026_ALL_REJECTED")
    print(header)
    for row in rows_by_period["2026"]:
        print(_row_line(row))


def main() -> None:
    """Запустити T105-22 як суто діагностичний міжперіодний аналіз."""

    production_before = _production_hashes()
    print("T105-22 Donchian Rejected Discriminator Anatomy")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  population=PRODUCTION_STOCHASTIC_SURVIVORS__DONCHIAN_N20_REJECT")
    print("  omitted_structured_features=NONE")
    rows_by_period = {spec.code: _run_period(spec) for spec in PERIODS}
    for spec in PERIODS:
        counts = Counter(row.outcome for row in rows_by_period[spec.code])
        print(
            f"  population_{spec.code}=production_survivors:"
            f"{EXPECTED_SURVIVORS[spec.code]},donchian_rejected:"
            f"{EXPECTED_REJECTED[spec.code]},W:{counts[OUTCOME_WIN]},"
            f"L:{counts[OUTCOME_LOSS]},BE:{counts[OUTCOME_BREAK_EVEN]}"
        )

    stats = _numeric_stats(rows_by_period)
    _categorical_stats(rows_by_period)
    _separation(stats)
    _row_diagnostics(rows_by_period)
    assert _production_hashes() == production_before
    print("  outcome_used_as_label_only=True")
    print("  entry_features_future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  production_stochastic_gate_active=True")
    print("  donchian_gate_test_only=True")
    print("  donchian_production_gate=False")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  filter_rule_created=False")
    print("  threshold_optimization_performed=False")
    print("T105_22_DONCHIAN_REJECTED_DISCRIMINATOR=OK")


if __name__ == "__main__":
    main()
