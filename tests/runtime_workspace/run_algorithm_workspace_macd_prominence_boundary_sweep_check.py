# run_algorithm_workspace_macd_prominence_boundary_sweep_check.py — RoadMap99_03C
# -*- coding: utf-8 -*-
"""Граничний sweep робочого діапазону prominence для RoadMap99_03C.

Модуль завершує серію контрольованих досліджень параметра
``macd_extremum_min_prominence`` після широкого та верхнього sweep. Мета —
не оголосити одне значення універсальною константою, а точно дослідити
локальну межу 0.000022..0.000026 на EURUSD M15 у зафіксованому Historical
Replay 2026-01-02..2026-02-28. Параметри можуть залежати від інструмента,
timeframe, волатильності та ринкового режиму, тому результат цього тесту є
лише кандидатом на робочий діапазон для поточного набору даних.

Змінюється тільки prominence. Extremum-to-cross distance=0.000050,
angle=45°, Alligator=OFF, Profit Drawdown=30%, risk policy, M1->M15 source,
Replay period і execution policy лишаються незмінними. Перевіряються п'ять
значень із кроком 0.000001: 0.000022, 0.000023, 0.000024, 0.000025 і
0.000026. Тест повторно використовує публічний helper API базового prominence
sweep, щоб не дублювати Replay-логіку.

Звіт показує MACD Quality accept/reject, причини відхилення, trades, W/L,
win rate, net PnL, Profit Factor, drawdown, average trade, причини закриття та
missed moves. Автоматичного вибору production-значення немає. Broker requests
і broker execution у Historical Replay повинні лишатися нульовими.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_macd_quality_parameter_sweep import (  # noqa: E402
    MACD_QUALITY_SWEEP_PARAMETER_PROMINENCE,
    WorkspaceMacdQualityParameterSweepRun,
    build_workspace_macd_quality_prominence_sweep,
)
from tests.runtime_workspace import (  # noqa: E402
    run_algorithm_workspace_macd_prominence_sweep_check as base_sweep,
)

PROMINENCE_VALUES = (
    0.000022,
    0.000023,
    0.000024,
    0.000025,
    0.000026,
)
LOWER_OVERLAP_PROMINENCE = 0.000022
UPPER_OVERLAP_PROMINENCE = 0.000025


def main() -> None:
    """Запустити boundary sweep і перевірити controlled-variable invariants."""
    print(
        "Algorithm Workspace MACD Prominence Boundary Sweep Check — " "RoadMap99_03C",
        flush=True,
    )
    print(
        "  Controlled variable: MACD extremum minimum prominence only. "
        "Range=0.000022..0.000026 step=0.000001, distance=0.00005, "
        "angle=45°, Alligator=OFF, Profit Drawdown=30%, M1->M15 Replay; "
        "broker execution remains disabled.",
        flush=True,
    )
    print(
        "  Interpretation: local admissible-range calibration for this "
        "EURUSD period, not a universal market constant.",
        flush=True,
    )
    assert base_sweep.PROMINENCE_SWEEP_HELPER_API_VERSION == "RoadMap99_03E"
    print(
        "  helper_api=" f"{base_sweep.PROMINENCE_SWEEP_HELPER_API_VERSION}",
        flush=True,
    )
    if not base_sweep.M1_FILE.is_file():
        raise FileNotFoundError(
            "Real EURUSD M1 history is required: " + str(base_sweep.M1_FILE)
        )

    events = base_sweep.build_strategy_events()
    completed = []
    for index, prominence in enumerate(PROMINENCE_VALUES, start=1):
        print(
            "MACD Prominence Boundary Sweep: running "
            f"{index}/{len(PROMINENCE_VALUES)} "
            f"prominence={prominence:.6f} ...",
            flush=True,
        )
        run = base_sweep.run_prominence_variant(prominence)
        completed.append(run)
        print(
            "MACD Prominence Boundary Sweep: completed "
            f"prominence={prominence:.6f}, "
            f"quality={run.summary.signals.macd_quality_accept}/"
            f"{run.summary.signals.macd_quality_reject}, "
            f"trades={run.summary.opened_trades}, "
            f"net_pnl={run.summary.net_profit:.2f}, "
            f"PF={base_sweep.format_profit_factor_text(run.summary.profit_factor)}",
            flush=True,
        )

    sweep_runs = tuple(
        WorkspaceMacdQualityParameterSweepRun(
            parameter_value=run.prominence,
            summary=run.summary,
            expired_next_bar_gap_orders=run.expired_next_bar_gap_orders,
            missed_moves=base_sweep.count_missed_moves(run.records, events),
        )
        for run in completed
    )
    report = build_workspace_macd_quality_prominence_sweep(
        sweep_runs,
        fixed_distance=base_sweep.FIXED_DISTANCE,
        fixed_angle=base_sweep.FIXED_ANGLE,
    )

    assert report.controlled_parameter == MACD_QUALITY_SWEEP_PARAMETER_PROMINENCE
    assert report.source_timeframe == "M1"
    assert report.strategy_timeframe == "M15"
    assert report.accepted_bars == 3888
    assert report.fixed_distance == base_sweep.FIXED_DISTANCE
    assert report.fixed_angle == base_sweep.FIXED_ANGLE
    assert not report.alligator_enabled
    assert len(report.variants) == len(PROMINENCE_VALUES)
    assert tuple(variant.parameter_value for variant in report.variants) == (
        PROMINENCE_VALUES
    )

    lower_overlap = next(
        variant
        for variant in report.variants
        if abs(variant.parameter_value - LOWER_OVERLAP_PROMINENCE) < 1e-12
    )
    assert lower_overlap.signals == 320
    assert lower_overlap.quality_accept == 11
    assert lower_overlap.quality_reject == 309
    assert lower_overlap.trades == 11
    assert abs(lower_overlap.net_profit - (-2.16)) < 0.01
    assert lower_overlap.missed_moves == 119

    upper_overlap = next(
        variant
        for variant in report.variants
        if abs(variant.parameter_value - UPPER_OVERLAP_PROMINENCE) < 1e-12
    )
    assert upper_overlap.signals == 320
    assert upper_overlap.quality_accept == 7
    assert upper_overlap.quality_reject == 313
    assert upper_overlap.trades == 7
    assert abs(upper_overlap.net_profit - 0.88) < 0.01
    assert upper_overlap.missed_moves == 122

    print("Algorithm Workspace MACD Prominence Boundary Sweep result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  source_timeframe={report.source_timeframe}")
    print(f"  strategy_timeframe={report.strategy_timeframe}")
    print(f"  controlled_parameter={report.controlled_parameter}")
    print(f"  fixed_distance={report.fixed_distance:.6f}")
    print(f"  fixed_angle={report.fixed_angle:.2f}")
    print(f"  alligator_enabled={report.alligator_enabled}")
    print("  parameter_model=ADMISSIBLE_RANGE_NOT_UNIVERSAL_CONSTANT")
    print("  symbol_regime_specific=True")
    print("  production_selection_deferred=True")
    print("  prominence_variants:")
    for variant in report.variants:
        base_sweep.print_prominence_variant(
            variant,
            baseline=(abs(variant.parameter_value - UPPER_OVERLAP_PROMINENCE) < 1e-12),
        )
    print("  production_signal_logic_changed=False")
    print("  distance_parameter_changed=False")
    print("  angle_parameter_changed=False")
    print("  alligator_parameters_changed=False")
    print("  profit_drawdown_policy_changed=False")
    print("  risk_policy_changed=False")
    print(f"  deterministic={report.deterministic}")
    print(f"  broker_requests={report.broker_requests}")
    print("  broker_execution_attempted=" f"{report.broker_execution_attempted}")
    print("ALGORITHM_WORKSPACE_MACD_PROMINENCE_BOUNDARY_SWEEP_CHECK=OK")


if __name__ == "__main__":
    main()
