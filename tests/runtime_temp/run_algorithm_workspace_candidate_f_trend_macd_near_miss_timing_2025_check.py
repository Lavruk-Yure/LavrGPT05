# -*- coding: utf-8 -*-
"""RoadMap102: timing diagnostic single-criterion MACD near-miss у OOS 2025.

Runner продовжує frozen Trend Coverage та MACD Quality diagnostics без зміни
жодного production threshold. Він бере лише rejected MACD crosses усередині
price-only strong M15 trend segments, для яких провалений рівно один quality
criterion, і вимірює їх положення всередині вже frozen 32-bar trend window.

Це post-event research diagnostic, а не entry gate. Для кожного near-miss
показуються: bars/time progress від початку trend segment, частка directional
price move, що вже відбулася на signal bar, залишок руху до endpoint window,
максимальний favorable/adverse excursion до кінця window і відношення
фактичного quality value до frozen threshold. Counterfactual trades не
створюються; MACD/Alligator/Candidate F та execution не змінюються.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen  # noqa: E402
from run_algorithm_workspace_candidate_f_trend_coverage_2025_check import (  # noqa
    COVERAGE_MACD_QUALITY_REJECT,
    TrendWindow,
    coverage_for_window,
    price_only_trend_candidates,
    strongest_non_overlapping,
)
from run_algorithm_workspace_candidate_f_trend_macd_quality_2025_check import (  # noqa
    QualityRejectDetail,
    failed_criteria,
    quality_reject_detail,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

MACD_PROMINENCE_THRESHOLD = 0.000015
MACD_DISTANCE_THRESHOLD = 0.000050
MACD_ANGLE_THRESHOLD = 2.25


@dataclass(frozen=True, slots=True)
class NearMissTiming:
    """Timing та post-event price potential одного single-criterion near-miss."""

    timestamp: datetime
    direction: str
    criterion: str
    actual_value: float
    threshold: float
    threshold_ratio: float
    bars_from_start: int
    bars_to_end: int
    time_progress: float
    move_progress: float
    endpoint_remaining: float
    favorable_remaining: float
    adverse_remaining: float
    segment_move_tr: float
    segment_efficiency: float


def _criterion_value_and_threshold(
    detail: QualityRejectDetail,
    criterion: str,
) -> tuple[float, float]:
    """Повернути observed value та frozen threshold єдиного failed criterion."""
    if criterion == "prominence":
        assert detail.prominence is not None
        return detail.prominence, MACD_PROMINENCE_THRESHOLD
    if criterion == "distance":
        assert detail.distance is not None
        return detail.distance, MACD_DISTANCE_THRESHOLD
    if criterion == "angle":
        assert detail.angle is not None
        return detail.angle, MACD_ANGLE_THRESHOLD
    raise AssertionError(f"Unsupported single criterion: {criterion}")


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _future_excursions(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    end_index: int,
    direction: str,
    segment_abs_net_move: float,
) -> tuple[float, float]:
    """Повернути MFE/MAE після signal у частках net move trend window."""
    signal_close = events[signal_index].close
    future = events[signal_index : end_index + 1]  # noqa
    assert future
    if direction == "BUY":
        favorable = max(event.high for event in future) - signal_close
        adverse = signal_close - min(event.low for event in future)
    else:
        favorable = signal_close - min(event.low for event in future)
        adverse = max(event.high for event in future) - signal_close
    return (
        max(0.0, favorable) / segment_abs_net_move,
        max(0.0, adverse) / segment_abs_net_move,
    )


def _timing_for_record(
    record: WorkspaceSignalRecord,
    window: TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
    event_index_by_timestamp: dict[datetime, int],
) -> NearMissTiming:
    """Побудувати timing evidence для одного single-criterion rejected cross."""
    detail = quality_reject_detail(record)
    failed = failed_criteria(detail)
    assert len(failed) == 1
    criterion = failed[0]
    assert criterion != "extremum"
    actual_value, threshold = _criterion_value_and_threshold(detail, criterion)

    signal_index = event_index_by_timestamp[record.timestamp]
    assert window.start_index <= signal_index <= window.end_index
    bars_from_start = signal_index - window.start_index
    bars_to_end = window.end_index - signal_index
    span_bars = window.end_index - window.start_index
    assert span_bars > 0

    sign = _direction_sign(window.direction)
    start_close = events[window.start_index].close
    signal_close = events[signal_index].close
    end_close = events[window.end_index].close
    segment_abs_net_move = abs(end_close - start_close)
    assert segment_abs_net_move > 0.0

    move_progress = sign * (signal_close - start_close) / segment_abs_net_move
    endpoint_remaining = sign * (end_close - signal_close) / segment_abs_net_move
    favorable, adverse = _future_excursions(
        events,
        signal_index,
        window.end_index,
        window.direction,
        segment_abs_net_move,
    )
    return NearMissTiming(
        timestamp=record.timestamp,
        direction=record.direction,
        criterion=criterion,
        actual_value=actual_value,
        threshold=threshold,
        threshold_ratio=actual_value / threshold,
        bars_from_start=bars_from_start,
        bars_to_end=bars_to_end,
        time_progress=bars_from_start / span_bars,
        move_progress=move_progress,
        endpoint_remaining=endpoint_remaining,
        favorable_remaining=favorable,
        adverse_remaining=adverse,
        segment_move_tr=window.normalized_move,
        segment_efficiency=window.path_efficiency,
    )


def _criterion_count(items: tuple[NearMissTiming, ...], criterion: str) -> int:
    return sum(item.criterion == criterion for item in items)


def main() -> None:
    frozen.assert_frozen_oos_snapshot()

    runtime = frozen.FrozenOosRuntime(
        frozen.frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    events = session.events
    assert events
    event_index_by_timestamp = {
        event.timestamp: index for index, event in enumerate(events)
    }

    candidates = price_only_trend_candidates(events)
    strong_windows = strongest_non_overlapping(candidates)

    while not session.completed:
        runtime.advance_replay()

    execution = runtime.replay_execution
    assert execution is not None
    records = runtime.historical_signal_records_for_test()
    trades = execution.trade_diagnostics()
    coverage = tuple(
        coverage_for_window(window, events, records, trades)
        for window in strong_windows
    )
    quality_windows = tuple(
        item.window
        for item in coverage
        if item.coverage == COVERAGE_MACD_QUALITY_REJECT
    )
    assert len(quality_windows) == 12

    near_misses: list[NearMissTiming] = []
    for window in quality_windows:
        start = events[window.start_index].timestamp
        end = events[window.end_index].timestamp
        aligned = tuple(
            record
            for record in records
            if start <= record.timestamp <= end and record.direction == window.direction
        )
        for record in aligned:
            detail = quality_reject_detail(record)
            if len(failed_criteria(detail)) != 1:
                continue
            near_misses.append(
                _timing_for_record(
                    record,
                    window,
                    events,
                    event_index_by_timestamp,
                )
            )

    items = tuple(sorted(near_misses, key=lambda item: item.timestamp))
    assert len(items) == 8
    assert all(item.direction in {"BUY", "SELL"} for item in items)
    assert all(0.0 <= item.time_progress <= 1.0 for item in items)

    first_half = sum(item.time_progress <= 0.5 for item in items)
    second_half = len(items) - first_half
    endpoint_remaining_positive = sum(item.endpoint_remaining > 0.0 for item in items)
    favorable_remaining_positive = sum(item.favorable_remaining > 0.0 for item in items)
    average_time_progress = sum(item.time_progress for item in items) / len(items)
    average_move_progress = sum(item.move_progress for item in items) / len(items)
    average_endpoint_remaining = sum(item.endpoint_remaining for item in items) / len(
        items
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Trend MACD Near-Miss Timing 2025 result")
    print("  source_detector=PRICE_ONLY_M15_STRONG_WINDOW_V1")
    print("  source_quality_diagnostic=SINGLE_CRITERION_ONLY")
    print(f"  single_criterion_near_misses={len(items)}")
    print(
        "  criterion_counts="
        f"prominence:{_criterion_count(items, 'prominence')},"
        f"distance:{_criterion_count(items, 'distance')},"
        f"angle:{_criterion_count(items, 'angle')}"
    )
    print(
        "  frozen_thresholds="
        f"prominence:{MACD_PROMINENCE_THRESHOLD:.6f},"
        f"distance:{MACD_DISTANCE_THRESHOLD:.6f},"
        f"angle:{MACD_ANGLE_THRESHOLD:.2f}"
    )
    print("  timing_half_counts=" f"first_half:{first_half},second_half:{second_half}")
    print(
        "  remaining_directional_move="
        f"endpoint_positive:{endpoint_remaining_positive}/{len(items)},"
        f"future_favorable_positive:{favorable_remaining_positive}/{len(items)}"
    )
    print(f"  average_time_progress={average_time_progress:.3f}")
    print(f"  average_move_progress={average_move_progress:.3f}")
    print(f"  average_endpoint_remaining={average_endpoint_remaining:.3f}")
    print("  chronological_near_misses:")
    for index, item in enumerate(items, start=1):
        print(
            f"    {index:02d}. {item.timestamp.isoformat()} {item.direction} "
            f"criterion:{item.criterion} "
            f"value:{item.actual_value:.8f} threshold:{item.threshold:.8f} "
            f"ratio:{item.threshold_ratio:.3f} "
            f"bars_from_start:{item.bars_from_start} "
            f"bars_to_end:{item.bars_to_end} "
            f"time_progress:{item.time_progress:.3f} "
            f"move_progress:{item.move_progress:.3f} "
            f"endpoint_remaining:{item.endpoint_remaining:.3f} "
            f"mfe_remaining:{item.favorable_remaining:.3f} "
            f"mae_remaining:{item.adverse_remaining:.3f} "
            f"segment:{item.segment_move_tr:.2f}TR/"
            f"eff:{item.segment_efficiency:.3f}"
        )
    print("  counterfactual_trades_created=False")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TREND_MACD_NEAR_MISS_TIMING_2025_CHECK=OK")


if __name__ == "__main__":
    main()
