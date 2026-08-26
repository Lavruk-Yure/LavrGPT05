# run_algorithm_workspace_macd_prominence_upper_sweep_check.py — RoadMap99_03B
# -*- coding: utf-8 -*-
"""Верхній контрольований sweep prominence для MACD Quality у RoadMap99_03B.

Модуль продовжує перший RoadMap99_03 sweep і досліджує верхню область
параметра ``macd_extremum_min_prominence`` після того, як перший прохід
показав покращення PF, net PnL і drawdown при підвищенні prominence до
0.000020. Змінюється тільки prominence; distance=0.000050, angle=45°,
Profit Drawdown=30%, risk policy, M1->M15 dataset та Replay period лишаються
незмінними. Alligator навмисно вимкнений, щоб не змішувати вплив двох
незалежних фільтрів.

Тест повторно використовує канонічний Replay harness першого prominence
sweep, тому побудова Workspace, агрегація M1->M15, missed-move policy та
метрики лишаються ідентичними. Перевіряються шість значень 0.000016..
0.000030, включно з 0.000020 як контрольним overlap-пунктом із попереднім
тестом. Вибір production-параметра не виконується автоматично: результат
призначений для ручного порівняння статистичної якості та втрати сигналів.
Broker requests і broker execution у Historical Replay повинні лишатися 0.
Версія helper API перевіряється перед Replay, щоб виключити застарілий bytecode.
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
    0.000016,
    0.000018,
    0.000020,
    0.000022,
    0.000025,
    0.000030,
)
OVERLAP_PROMINENCE = 0.000020


def main() -> None:
    """Запустити upper sweep та перевірити його controlled-variable invariants."""
    print(
        "Algorithm Workspace MACD Prominence Upper Sweep Check — RoadMap99_03B",
        flush=True,
    )
    print(
        "  Controlled variable: MACD extremum minimum prominence only. "
        "Range=0.000016..0.000030, distance=0.00005, angle=45°, "
        "Alligator=OFF, Profit Drawdown=30%, M1->M15 Replay; "
        "broker execution remains disabled.",
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
            "MACD Prominence Upper Sweep: running "
            f"{index}/{len(PROMINENCE_VALUES)} "
            f"prominence={prominence:.6f} ...",
            flush=True,
        )
        run = base_sweep.run_prominence_variant(prominence)
        completed.append(run)
        print(
            "MACD Prominence Upper Sweep: completed "
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

    overlap = next(
        variant
        for variant in report.variants
        if abs(variant.parameter_value - OVERLAP_PROMINENCE) < 1e-12
    )
    assert overlap.signals == 320
    assert overlap.buy_signals == 160
    assert overlap.sell_signals == 160
    assert overlap.quality_accept == 12
    assert overlap.quality_reject == 308
    assert overlap.trades == 12
    assert abs(overlap.net_profit - (-2.13)) < 0.01
    assert overlap.missed_moves == 118

    print("Algorithm Workspace MACD Prominence Upper Sweep result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  source_timeframe={report.source_timeframe}")
    print(f"  strategy_timeframe={report.strategy_timeframe}")
    print(f"  controlled_parameter={report.controlled_parameter}")
    print(f"  fixed_distance={report.fixed_distance:.6f}")
    print(f"  fixed_angle={report.fixed_angle:.2f}")
    print(f"  alligator_enabled={report.alligator_enabled}")
    print(f"  overlap_with_previous_sweep={OVERLAP_PROMINENCE:.6f}")
    print("  prominence_variants:")
    for variant in report.variants:
        base_sweep.print_prominence_variant(
            variant,
            baseline=(abs(variant.parameter_value - OVERLAP_PROMINENCE) < 1e-12),
        )
    print("  selection_deferred_until_manual_analysis=True")
    print("  production_signal_logic_changed=False")
    print("  distance_parameter_changed=False")
    print("  angle_parameter_changed=False")
    print("  alligator_parameters_changed=False")
    print("  profit_drawdown_policy_changed=False")
    print("  risk_policy_changed=False")
    print(f"  deterministic={report.deterministic}")
    print(f"  broker_requests={report.broker_requests}")
    print("  broker_execution_attempted=" f"{report.broker_execution_attempted}")
    print("ALGORITHM_WORKSPACE_MACD_PROMINENCE_UPPER_SWEEP_CHECK=OK")


if __name__ == "__main__":
    main()
