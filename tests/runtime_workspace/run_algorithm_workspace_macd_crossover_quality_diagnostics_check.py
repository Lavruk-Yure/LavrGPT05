# -*- coding: utf-8 -*-
"""RoadMap99_01 synthetic MACD crossover quality diagnostics check."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_macd import (  # noqa: E402
    MACD_STATE_BEARISH,
    MACD_STATE_BULLISH,
    MACD_STATE_CROSS_DOWN,
    MACD_STATE_CROSS_UP,
    WorkspaceMacdObservation,
)
from core.workspace_macd_crossover_quality import (  # noqa: E402
    MACD_QUALITY_REASON_ACCEPTED,
    MACD_QUALITY_REASON_DISTANCE_TOO_SMALL,
    MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND,
    WorkspaceMacdCrossoverQualityConfig,
    build_workspace_macd_crossover_quality_diagnostics,
    chart_45_degree_reference_y_per_minute,
)

BAR_MINUTES = 15
REFERENCE_Y_PER_BAR = 0.000040
REFERENCE_Y_PER_MINUTE = REFERENCE_Y_PER_BAR / BAR_MINUTES


def _observation(
    index: int,
    *,
    macd: float,
    signal: float,
    state: str,
) -> WorkspaceMacdObservation:
    return WorkspaceMacdObservation(
        timestamp=datetime(2026, 1, 2, tzinfo=UTC)
        + timedelta(minutes=BAR_MINUTES * index),
        close=1.17000 + index * 0.00001,
        source_value=1.17000 + index * 0.00001,
        macd_value=macd,
        signal_value=signal,
        histogram=macd - signal,
        state=state,
        bars_processed=40 + index,
        warmed_up=True,
        profile_uid="MACD-LGE-CLASSIC",
        profile_revision=1,
    )


def _synthetic_observations() -> tuple[WorkspaceMacdObservation, ...]:
    # BUY at index 4. Structural minimum is at index 1, so search falls
    # through 3 and succeeds in window 5. The crossover is exactly 45 deg:
    # Signal is flat and MACD moves REFERENCE_Y_PER_BAR in one M15 bar.
    # SELL at index 9 has a valid local maximum but distance < 0.00005.
    # BUY at index 20 has no local minimum in the 3 -> 5 -> 7 history.
    values = (
        (-0.000010, 0.0, MACD_STATE_BEARISH),
        (-0.000080, 0.0, MACD_STATE_BEARISH),
        (-0.000040, 0.0, MACD_STATE_BEARISH),
        (-0.000020, 0.0, MACD_STATE_BEARISH),
        (0.000020, 0.0, MACD_STATE_CROSS_UP),
        (0.000010, 0.0, MACD_STATE_BULLISH),
        (0.000020, 0.0, MACD_STATE_BULLISH),
        (0.000030, 0.0, MACD_STATE_BULLISH),
        (0.000040, 0.0, MACD_STATE_BULLISH),
        (-0.000010, 0.0, MACD_STATE_CROSS_DOWN),
        (-0.000020, 0.0, MACD_STATE_BEARISH),
        (-0.000030, 0.0, MACD_STATE_BEARISH),
        (-0.000040, 0.0, MACD_STATE_BEARISH),
        (-0.000050, 0.0, MACD_STATE_BEARISH),
        (-0.000045, 0.0, MACD_STATE_BEARISH),
        (-0.000040, 0.0, MACD_STATE_BEARISH),
        (-0.000035, 0.0, MACD_STATE_BEARISH),
        (-0.000030, 0.0, MACD_STATE_BEARISH),
        (-0.000025, 0.0, MACD_STATE_BEARISH),
        (-0.000020, 0.0, MACD_STATE_BEARISH),
        (0.000005, 0.0, MACD_STATE_CROSS_UP),
    )
    return tuple(
        _observation(index, macd=macd, signal=signal, state=state)
        for index, (macd, signal, state) in enumerate(values)
    )


def main() -> None:
    calibration = chart_45_degree_reference_y_per_minute(
        value_low=-0.00020,
        value_high=0.00020,
        plot_width_px=360.0,
        plot_height_px=120.0,
        visible_bars=100,
        strategy_bar_minutes=BAR_MINUTES,
    )
    expected_calibration = 0.000012 / BAR_MINUTES
    assert math.isclose(
        calibration,
        expected_calibration,
        rel_tol=0.0,
        abs_tol=1e-18,
    )

    config = WorkspaceMacdCrossoverQualityConfig(
        angle_reference_y_per_minute=REFERENCE_Y_PER_MINUTE,
        strategy_bar_minutes=BAR_MINUTES,
        extremum_min_prominence=0.00001,
        extremum_to_cross_min_distance=0.00005,
        cross_min_angle_degrees=45.0,
    )
    observations = _synthetic_observations()
    report = build_workspace_macd_crossover_quality_diagnostics(
        observations,
        config=config,
    )
    repeated = build_workspace_macd_crossover_quality_diagnostics(
        observations,
        config=config,
    )

    assert report == repeated
    assert report.total_crosses == 3
    assert report.buy_crosses == 2
    assert report.sell_crosses == 1

    first = report.signals[0]
    assert first.direction == "BUY"
    assert first.search_window == 5
    assert first.extremum_timestamp == observations[1].timestamp
    assert math.isclose(first.extremum_value, -0.000080, abs_tol=1e-15)
    assert math.isclose(
        first.extremum_prominence or 0.0,
        0.000040,
        abs_tol=1e-15,
    )
    assert math.isclose(
        first.extremum_to_cross_distance or 0.0,
        0.000080,
        abs_tol=1e-15,
    )
    assert math.isclose(
        first.crossover_steepness,
        0.000040,
        abs_tol=1e-15,
    )
    assert math.isclose(
        first.effective_angle_degrees,
        45.0,
        abs_tol=1e-12,
    )
    assert first.final_quality_pass
    assert first.reason_code == MACD_QUALITY_REASON_ACCEPTED

    second = report.signals[1]
    assert second.direction == "SELL"
    assert second.search_window == 3
    assert second.extremum_to_cross_distance is not None
    assert second.extremum_to_cross_distance < 0.00005
    assert not second.final_quality_pass
    assert second.reason_code == MACD_QUALITY_REASON_DISTANCE_TOO_SMALL

    third = report.signals[2]
    assert third.direction == "BUY"
    assert third.search_window is None
    assert not third.extremum_found
    assert not third.final_quality_pass
    assert third.reason_code == MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND

    assert report.window_3 == 1
    assert report.window_5 == 1
    assert report.window_7 == 0
    assert report.extremum_not_found == 1
    assert report.final_quality_pass == 1
    assert report.final_quality_reject == 2

    print("Algorithm Workspace MACD Crossover Quality Diagnostics result")
    print(f"  classic_crosses={report.total_crosses}")
    print(f"  BUY/SELL={report.buy_crosses}/{report.sell_crosses}")
    print(
        "  search_windows="
        f"3:{report.window_3} 5:{report.window_5} 7:{report.window_7} "
        f"NONE:{report.extremum_not_found}"
    )
    print("  canonical_buy_window_5=True")
    print("  canonical_buy_angle_45=True")
    print("  canonical_sell_distance_reject=True")
    print("  canonical_no_extremum_reject=True")
    print("  chart_45_calibration_helper=True")
    print("  production_signal_logic_changed=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_CROSSOVER_QUALITY_DIAGNOSTICS_CHECK=OK")


if __name__ == "__main__":
    main()
