# -*- coding: utf-8 -*-
"""RoadMap99_01 short M1 -> M15 MACD crossover quality diagnostics."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_macd_crossover_quality import (  # noqa: E402
    WorkspaceMacdCrossoverQualityConfig,
    build_workspace_macd_crossover_quality_diagnostics,
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
END_UTC = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)
STRATEGY_BAR_MINUTES = 15

# RoadMap99 manual chart calibration. The 2026-01-09 14:15 UTC SELL
# crossover is the visual 45-degree reference selected during manual
# acceptance. Replay uses this fixed numeric scale, not chart pixels.
MANUAL_CALIBRATED_45_Y_PER_M15_BAR = 0.0000535


def _observations():
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
        source_name="IB_EURUSD_M1_RM99_DEV",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    source = WorkspaceMacdSignalSource(enabled=True, mode="LINEAR")
    proposals = 0
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is None:
            continue
        if source.on_market_event(completed.event) is not None:
            proposals += 1
    final = aggregator.complete()
    if final is not None:
        if source.on_market_event(final.event) is not None:
            proposals += 1
    return data_set, aggregator, source, proposals


def _format_signal(item) -> str:
    extremum_time = (
        "NONE"
        if item.extremum_timestamp is None
        else item.extremum_timestamp.isoformat()
    )
    distance = (
        "NONE"
        if item.extremum_to_cross_distance is None
        else f"{item.extremum_to_cross_distance:.8f}"
    )
    prominence = (
        "NONE"
        if item.extremum_prominence is None
        else f"{item.extremum_prominence:.8f}"
    )
    return (
        f"{item.timestamp.isoformat()} {item.direction} "
        f"window={item.search_window or 'NONE'} "
        f"extremum={extremum_time} "
        f"prominence={prominence} distance={distance} "
        f"angle={item.effective_angle_degrees:.2f} "
        f"pass={item.final_quality_pass} reason={item.reason_code}"
    )


def main() -> None:
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, source, proposals = _observations()
    config = WorkspaceMacdCrossoverQualityConfig(
        angle_reference_y_per_minute=(
            MANUAL_CALIBRATED_45_Y_PER_M15_BAR / STRATEGY_BAR_MINUTES
        ),
        strategy_bar_minutes=STRATEGY_BAR_MINUTES,
        extremum_min_prominence=0.00001,
        extremum_to_cross_min_distance=0.00005,
        cross_min_angle_degrees=45.0,
    )
    report = build_workspace_macd_crossover_quality_diagnostics(
        source.observations,
        config=config,
    )
    repeated = build_workspace_macd_crossover_quality_diagnostics(
        source.observations,
        config=config,
    )

    assert report == repeated
    assert proposals == report.total_crosses
    assert report.buy_crosses + report.sell_crosses == report.total_crosses
    assert (
        report.final_quality_pass + report.final_quality_reject
        == report.total_crosses
    )
    assert (
        report.window_3
        + report.window_5
        + report.window_7
        + report.extremum_not_found
        == report.total_crosses
    )
    assert data_set.report.accepted_rows == 58320
    assert aggregator.completed_bars == 3888
    assert report.total_crosses == 320
    assert report.buy_crosses == 160
    assert report.sell_crosses == 160
    assert report.window_3 == 58
    assert report.window_5 == 102
    assert report.window_7 == 86
    assert report.extremum_not_found == 74
    assert report.prominence_pass == 113
    assert report.distance_pass == 132
    assert report.angle_pass == 46
    assert report.final_quality_pass == 23
    assert report.final_quality_reject == 297
    assert report.rejected_extremum_not_found == 74
    assert report.rejected_extremum_too_weak == 133
    assert report.rejected_distance_too_small == 49
    assert report.rejected_cross_too_flat == 41

    by_timestamp = {item.timestamp: item for item in report.signals}
    weekend = by_timestamp[datetime(2026, 1, 2, 21, 45, tzinfo=UTC)]
    assert weekend.direction == "BUY"
    assert not weekend.extremum_found
    assert not weekend.criterion_angle_pass
    assert not weekend.final_quality_pass

    ordinary_sell = by_timestamp[datetime(2026, 1, 5, 9, 30, tzinfo=UTC)]
    assert ordinary_sell.direction == "SELL"
    assert ordinary_sell.search_window == 7
    assert not ordinary_sell.final_quality_pass
    assert not ordinary_sell.criterion_angle_pass
    assert 40.0 < ordinary_sell.effective_angle_degrees < 41.0

    visual_45_reference = by_timestamp[
        datetime(2026, 1, 9, 14, 15, tzinfo=UTC)
    ]
    assert visual_45_reference.direction == "SELL"
    assert visual_45_reference.final_quality_pass
    assert 45.0 <= visual_45_reference.effective_angle_degrees < 45.1

    weak_buy = by_timestamp[datetime(2026, 1, 7, 17, 30, tzinfo=UTC)]
    assert weak_buy.direction == "BUY"
    assert weak_buy.criterion_prominence_pass
    assert not weak_buy.criterion_distance_pass
    assert not weak_buy.criterion_angle_pass
    assert not weak_buy.final_quality_pass

    angle_bands = {
        "lt_10": sum(item.effective_angle_degrees < 10.0 for item in report.signals),
        "10_20": sum(
            10.0 <= item.effective_angle_degrees < 20.0
            for item in report.signals
        ),
        "20_30": sum(
            20.0 <= item.effective_angle_degrees < 30.0
            for item in report.signals
        ),
        "30_40": sum(
            30.0 <= item.effective_angle_degrees < 40.0
            for item in report.signals
        ),
        "40_45": sum(
            40.0 <= item.effective_angle_degrees < 45.0
            for item in report.signals
        ),
        "45_50": sum(
            45.0 <= item.effective_angle_degrees < 50.0
            for item in report.signals
        ),
        "50_60": sum(
            50.0 <= item.effective_angle_degrees < 60.0
            for item in report.signals
        ),
        "ge_60": sum(item.effective_angle_degrees >= 60.0 for item in report.signals),
    }
    assert angle_bands == {
        "lt_10": 10,
        "10_20": 67,
        "20_30": 65,
        "30_40": 86,
        "40_45": 46,
        "45_50": 18,
        "50_60": 23,
        "ge_60": 5,
    }
    structurally_qualified = tuple(
        item
        for item in report.signals
        if item.criterion_extremum_pass
        and item.criterion_prominence_pass
        and item.criterion_distance_pass
    )
    assert len(structurally_qualified) == 64
    assert sum(item.criterion_angle_pass for item in structurally_qualified) == 23

    accepted = tuple(
        item for item in report.signals if item.final_quality_pass
    )
    rejected = tuple(
        item for item in report.signals if not item.final_quality_pass
    )

    print("Algorithm Workspace MACD Crossover Quality Historical result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={aggregator.completed_bars}")
    print(
        "  dropped_incomplete_m15_buckets="
        f"{aggregator.dropped_incomplete_buckets}"
    )
    print(f"  classic_crosses={report.total_crosses}")
    print(f"  BUY/SELL={report.buy_crosses}/{report.sell_crosses}")
    print(
        "  search_windows="
        f"3:{report.window_3} 5:{report.window_5} 7:{report.window_7} "
        f"NONE:{report.extremum_not_found}"
    )
    print(
        "  criteria_pass="
        f"prominence:{report.prominence_pass} "
        f"distance:{report.distance_pass} angle:{report.angle_pass}"
    )
    print(
        "  quality_pass_reject="
        f"{report.final_quality_pass}/{report.final_quality_reject}"
    )
    print(
        "  reject_reasons="
        f"not_found:{report.rejected_extremum_not_found} "
        f"weak:{report.rejected_extremum_too_weak} "
        f"distance:{report.rejected_distance_too_small} "
        f"flat:{report.rejected_cross_too_flat}"
    )
    print(
        "  manual_calibrated_45_y_per_m15_bar="
        f"{MANUAL_CALIBRATED_45_Y_PER_M15_BAR:.8f}"
    )
    print(
        "  angle_distribution="
        f"<10:{angle_bands['lt_10']} "
        f"10-20:{angle_bands['10_20']} "
        f"20-30:{angle_bands['20_30']} "
        f"30-40:{angle_bands['30_40']} "
        f"40-45:{angle_bands['40_45']} "
        f"45-50:{angle_bands['45_50']} "
        f"50-60:{angle_bands['50_60']} "
        f">=60:{angle_bands['ge_60']}"
    )
    print(
        "  structurally_qualified_angle_pass="
        f"{len(structurally_qualified)}/"
        f"{sum(item.criterion_angle_pass for item in structurally_qualified)}"
    )
    for index, item in enumerate(accepted[:5], start=1):
        print(f"  accepted_{index}={_format_signal(item)}")
    for index, item in enumerate(rejected[:5], start=1):
        print(f"  rejected_{index}={_format_signal(item)}")
    print("  production_signal_logic_changed=False")
    print("  alligator_logic_changed=False")
    print("  risk_logic_changed=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_CROSSOVER_QUALITY_HISTORICAL_CHECK=OK")


if __name__ == "__main__":
    main()
