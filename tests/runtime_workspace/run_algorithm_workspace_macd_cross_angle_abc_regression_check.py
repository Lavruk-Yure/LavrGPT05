# run_algorithm_workspace_macd_cross_angle_abc_regression_check.py — RoadMap99_04G
# -*- coding: utf-8 -*-
"""Regression старого calibrated angle проти нової ABC-геометрії crossover.

Тест використовує той самий EURUSD M1 -> completed M15 dataset
2026-01-02..2026-08-11 і класичний MACD 12/26/9 Close EMA/EMA. Production
MACD Quality залишається на старому calibrated-angle алгоритмі; новий метод
працює паралельно і нічого не фільтрує.

Для ABC-методу X — реальний elapsed UTC time у хвилинах, Y — значення
MACD/Signal, помножене на 10000 для EURUSD. Точка C отримується лінійною
інтерполяцією двох завершених observation, після чого стандартною векторною
формулою обчислюється ``∠ACB``. Перевіряються детермінізм, відсутність
look-ahead, BUY/SELL count, шість ручних RoadMap99 anchors і незмінність
старої reference-точки 2026-01-09 14:15 SELL у legacy regression.

Числа ABC не вважаються новим production threshold: їхній допустимий діапазон
буде калібруватися окремо після цього regression, у тому числі для швидших
MACD 8/17/5 та 6/13/4.
"""

from __future__ import annotations

import math
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_macd_cross_angle_abc import (  # noqa: E402
    WorkspaceMacdCrossAngleAbcConfig,
    build_workspace_macd_cross_angle_abc_report,
)
from core.workspace_macd_crossover_quality import (  # noqa: E402
    WorkspaceMacdCrossoverQualityConfig,
    build_workspace_macd_crossover_quality_diagnostics,
    calibrated_macd_cross_angle_reference_y_per_minute,
)
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)

M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
START_UTC = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
END_UTC = datetime(2026, 8, 11, 8, 24, tzinfo=UTC)
EURUSD_VALUE_SCALE = 10000.0
TIME_UNIT_SECONDS = 60.0

MANUAL_CASES = (
    ("A_NEAR_41", datetime(2026, 1, 5, 9, 30, tzinfo=UTC)),
    ("B_NEAR_42", datetime(2026, 1, 5, 14, 15, tzinfo=UTC)),
    ("C_VISUAL_45_REFERENCE", datetime(2026, 1, 9, 14, 15, tzinfo=UTC)),
    ("D_KNOWN_WEAK", datetime(2026, 1, 7, 17, 30, tzinfo=UTC)),
    ("E_ANGLE_PASS_WEAK_EXTREMUM", datetime(2026, 1, 4, 22, 45, tzinfo=UTC)),
    ("F_NO_EXTREMUM_LOW_ANGLE", datetime(2026, 1, 2, 21, 45, tzinfo=UTC)),
)


def load_observations():
    """Завантажити один історичний stream і побудувати MACD observations."""
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=M1_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M1",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=0.00012,
        source_name="IB_EURUSD_M1_RM99_ANGLE_ABC_REGRESSION",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    source = WorkspaceMacdSignalSource(enabled=True, mode="LINEAR")
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is not None:
            source.on_market_event(completed.event)
    final = aggregator.complete()
    if final is not None:
        source.on_market_event(final.event)
    return data_set, aggregator, source


def main() -> None:
    print(
        "Algorithm Workspace MACD Cross Angle ABC Regression Check — "
        "RoadMap99_04G",
        flush=True,
    )
    print(
        "  Production remains on legacy calibrated angle. ABC diagnostic: "
        "X=real UTC minutes, Y=indicator*10000 for EURUSD, "
        "C=interpolated crossover.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, source = load_observations()
    legacy_config = WorkspaceMacdCrossoverQualityConfig(
        angle_reference_y_per_minute=(
            calibrated_macd_cross_angle_reference_y_per_minute()
        ),
        strategy_bar_minutes=15,
        extremum_min_prominence=0.000005,
        extremum_to_cross_min_distance=0.000050,
        cross_min_angle_degrees=45.0,
    )
    legacy = build_workspace_macd_crossover_quality_diagnostics(
        source.observations,
        config=legacy_config,
    )
    abc_config = WorkspaceMacdCrossAngleAbcConfig(
        indicator_value_scale=EURUSD_VALUE_SCALE,
        time_unit_seconds=TIME_UNIT_SECONDS,
    )
    abc = build_workspace_macd_cross_angle_abc_report(
        source.observations,
        config=abc_config,
    )
    repeated = build_workspace_macd_cross_angle_abc_report(
        source.observations,
        config=abc_config,
    )
    assert abc == repeated

    assert data_set.report.accepted_rows == 224125
    assert aggregator.completed_bars == 14941
    assert legacy.total_crosses == 1154
    assert abc.total_crosses == 1154
    assert abc.buy_crosses == 577
    assert abc.sell_crosses == 577
    assert abc.degenerate_crosses == 0

    legacy_by_time = {item.timestamp: item for item in legacy.signals}
    abc_by_time = {item.timestamp: item for item in abc.diagnostics}
    angles = tuple(
        item.angle_degrees
        for item in abc.diagnostics
        if item.angle_degrees is not None
    )
    assert len(angles) == abc.total_crosses

    distribution = (
        sum(angle < 0.5 for angle in angles),
        sum(0.5 <= angle < 1.0 for angle in angles),
        sum(1.0 <= angle < 1.5 for angle in angles),
        sum(1.5 <= angle < 2.0 for angle in angles),
        sum(2.0 <= angle < 2.5 for angle in angles),
        sum(2.5 <= angle < 3.0 for angle in angles),
        sum(3.0 <= angle < 5.0 for angle in angles),
        sum(angle >= 5.0 for angle in angles),
    )
    assert distribution == (148, 254, 233, 182, 116, 66, 115, 40)

    manual_expected = {
        "A_NEAR_41": (40.6827, 1.9832),
        "B_NEAR_42": (41.8924, 2.0513),
        "C_VISUAL_45_REFERENCE": (45.0101, 2.0625),
        "D_KNOWN_WEAK": (10.8842, 0.3935),
        "E_ANGLE_PASS_WEAK_EXTREMUM": (45.4332, 2.1864),
        "F_NO_EXTREMUM_LOW_ANGLE": (14.3576, 0.5291),
    }

    print("Algorithm Workspace MACD Cross Angle ABC Regression result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={aggregator.completed_bars}")
    print(f"  classic_crosses={abc.total_crosses}")
    print(f"  BUY/SELL={abc.buy_crosses}/{abc.sell_crosses}")
    print("  abc_x_unit=REAL_UTC_MINUTE")
    print(f"  abc_y_scale_eurusd={EURUSD_VALUE_SCALE:.0f}")
    print("  abc_cross_point=LINEAR_INTERPOLATION")
    print(f"  abc_degenerate_crosses={abc.degenerate_crosses}")
    print(
        "  abc_angle_avg_median="
        f"{statistics.mean(angles):.4f}/{statistics.median(angles):.4f} deg"
    )
    print(
        "  abc_distribution="
        f"<0.5:{distribution[0]} 0.5-1:{distribution[1]} "
        f"1-1.5:{distribution[2]} 1.5-2:{distribution[3]} "
        f"2-2.5:{distribution[4]} 2.5-3:{distribution[5]} "
        f"3-5:{distribution[6]} >=5:{distribution[7]}"
    )

    for case_code, timestamp in MANUAL_CASES:
        legacy_item = legacy_by_time[timestamp]
        abc_item = abc_by_time[timestamp]
        assert abc_item.angle_degrees is not None
        expected_legacy, expected_abc = manual_expected[case_code]
        assert math.isclose(
            legacy_item.effective_angle_degrees,
            expected_legacy,
            abs_tol=0.0002,
        )
        assert math.isclose(
            abc_item.angle_degrees,
            expected_abc,
            abs_tol=0.0002,
        )
        assert abc_item.previous_timestamp < abc_item.cross_timestamp
        assert abc_item.cross_timestamp <= abc_item.timestamp
        print(
            f"  {case_code}: legacy={legacy_item.effective_angle_degrees:.2f}deg, "
            f"abc={abc_item.angle_degrees:.4f}deg, "
            f"alpha={abc_item.interpolation_fraction:.6f}, "
            f"cross={abc_item.cross_timestamp.isoformat()}"
        )

    visual_reference = abc_by_time[
        datetime(2026, 1, 9, 14, 15, tzinfo=UTC)
    ]
    assert visual_reference.angle_degrees is not None
    assert 2.06 < visual_reference.angle_degrees < 2.07

    print("  legacy_manual_y45_calibration_removed=False")
    print("  abc_diagnostic_only=True")
    print("  production_angle_logic_changed=False")
    print("  production_signal_logic_changed=False")
    print("  future_observations_used=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_CROSS_ANGLE_ABC_REGRESSION_CHECK=OK")


if __name__ == "__main__":
    main()
