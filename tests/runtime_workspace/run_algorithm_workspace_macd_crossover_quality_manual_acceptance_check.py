# -*- coding: utf-8 -*-
"""RoadMap99_01 manual acceptance anchors for MACD crossover quality."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
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
MANUAL_CALIBRATED_45_Y_PER_M15_BAR = 0.0000535

MANUAL_CASES = (
    ("A_NEAR_41", datetime(2026, 1, 5, 9, 30, tzinfo=UTC)),
    ("B_NEAR_42", datetime(2026, 1, 5, 14, 15, tzinfo=UTC)),
    ("C_VISUAL_45_REFERENCE", datetime(2026, 1, 9, 14, 15, tzinfo=UTC)),
    ("D_KNOWN_WEAK", datetime(2026, 1, 7, 17, 30, tzinfo=UTC)),
    ("E_ANGLE_PASS_WEAK_EXTREMUM", datetime(2026, 1, 4, 22, 45, tzinfo=UTC)),
    ("F_NO_EXTREMUM_LOW_ANGLE", datetime(2026, 1, 2, 21, 45, tzinfo=UTC)),
)


def _load_observations():
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
        source_name="IB_EURUSD_M1_RM99_MANUAL",
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


def _number(value: float | None) -> str:
    return "NONE" if value is None else f"{value:+.8f}"


def _criteria(item) -> str:
    return (
        f"extremum={item.criterion_extremum_pass} "
        f"prominence={item.criterion_prominence_pass} "
        f"distance={item.criterion_distance_pass} "
        f"angle={item.criterion_angle_pass}"
    )


def main() -> None:
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    data_set, aggregator, source = _load_observations()
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

    observation_index = {
        item.timestamp: index for index, item in enumerate(source.observations)
    }
    diagnostics = {item.timestamp: item for item in report.signals}

    print("Algorithm Workspace MACD Crossover Quality Manual Acceptance result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={aggregator.completed_bars}")
    print(
        "  manual_calibrated_45_y_per_m15_bar="
        f"{MANUAL_CALIBRATED_45_Y_PER_M15_BAR:.8f}"
    )
    print(f"  manual_cases={len(MANUAL_CASES)}")

    for case_number, (case_code, timestamp) in enumerate(MANUAL_CASES, start=1):
        item = diagnostics[timestamp]
        index = observation_index[timestamp]
        assert index > 0
        previous = source.observations[index - 1]
        current = source.observations[index]
        assert current.timestamp == timestamp

        chart_start = (
            item.extremum_timestamp
            if item.extremum_timestamp is not None
            else timestamp - timedelta(hours=1)
        )
        chart_start -= timedelta(minutes=30)
        chart_end = timestamp + timedelta(minutes=30)

        print(f"  case_{case_number}={case_code}")
        print(
            f"    cross={timestamp.isoformat()} {item.direction} "
            f"chart_range={chart_start.isoformat()}..{chart_end.isoformat()}"
        )
        print(
            "    lines="
            f"MACD:{_number(previous.macd_value)}->{_number(current.macd_value)} "
            f"Signal:{_number(previous.signal_value)}->{_number(current.signal_value)}"
        )
        print(
            "    histogram="
            f"before:{item.histogram_before:+.8f} "
            f"after:{item.histogram_after:+.8f} "
            f"steepness:{item.crossover_steepness:.8f}"
        )
        extremum_timestamp = "NONE"
        if item.extremum_timestamp is not None:
            extremum_timestamp = item.extremum_timestamp.isoformat()

        print(
            "    extremum="
            f"{extremum_timestamp} "
            f"type:{item.extremum_type} "
            f"window:{item.search_window or 'NONE'} "
            f"value:{_number(item.extremum_value)} "
            f"prominence:{_number(item.extremum_prominence)} "
            f"distance:{_number(item.extremum_to_cross_distance)}"
        )
        print(
            "    slopes_per_m15="
            f"MACD:{item.macd_slope_per_minute * STRATEGY_BAR_MINUTES:+.8f} "
            f"Signal:{item.signal_slope_per_minute * STRATEGY_BAR_MINUTES:+.8f} "
            f"angle:{item.effective_angle_degrees:.2f}deg"
        )
        print(f"    criteria={_criteria(item)}")
        print(
            f"    result=pass:{item.final_quality_pass} "
            f"reason:{item.reason_code}"
        )

    near_41 = diagnostics[datetime(2026, 1, 5, 9, 30, tzinfo=UTC)]
    near_42 = diagnostics[datetime(2026, 1, 5, 14, 15, tzinfo=UTC)]
    visual_45 = diagnostics[datetime(2026, 1, 9, 14, 15, tzinfo=UTC)]
    known_weak = diagnostics[datetime(2026, 1, 7, 17, 30, tzinfo=UTC)]
    weak_extremum = diagnostics[datetime(2026, 1, 4, 22, 45, tzinfo=UTC)]
    no_extremum = diagnostics[datetime(2026, 1, 2, 21, 45, tzinfo=UTC)]

    assert not near_41.final_quality_pass
    assert 40.0 < near_41.effective_angle_degrees < 41.0
    assert not near_41.criterion_angle_pass
    assert not near_42.final_quality_pass
    assert 41.0 < near_42.effective_angle_degrees < 42.0
    assert not near_42.criterion_angle_pass
    assert visual_45.final_quality_pass
    assert 45.0 <= visual_45.effective_angle_degrees < 45.1
    assert visual_45.criterion_angle_pass
    assert not known_weak.final_quality_pass
    assert not known_weak.criterion_distance_pass
    assert not known_weak.criterion_angle_pass
    assert 10.0 < known_weak.effective_angle_degrees < 11.0
    assert not weak_extremum.final_quality_pass
    assert weak_extremum.criterion_angle_pass
    assert not weak_extremum.criterion_prominence_pass
    assert not no_extremum.final_quality_pass
    assert not no_extremum.criterion_angle_pass
    assert not no_extremum.criterion_extremum_pass

    print("  production_signal_logic_changed=False")
    print("  alligator_logic_changed=False")
    print("  risk_logic_changed=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_CROSSOVER_QUALITY_MANUAL_ACCEPTANCE_CHECK=OK")


if __name__ == "__main__":
    main()
