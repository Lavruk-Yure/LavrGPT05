# -*- coding: utf-8 -*-
"""RoadMap102: causal diagnostic єдиного Alligator-reject strong trend OOS 2025.

Runner продовжує frozen price-only Trend Coverage без зміни production logic.
Він бере єдиний strong M15 trend segment, де MACD Quality уже PASS, але
SAME_TIMEFRAME Alligator відхилив aligned signal, і вимірює причинний lag
Alligator від старого режиму до нового напрямку тренду.

Post-event price metrics потрібні лише для research: скільки strong-window move
вже пройшло на signal bar, скільки залишалося, коли Alligator став NEUTRAL,
BEARISH, TREND_DOWN STARTING та TREND_DOWN ACTIVE. Ці майбутні дані не
потрапляють у trade gate, counterfactual trade не створюється.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
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
    COVERAGE_ALLIGATOR_REJECT,
    TrendWindow,
    coverage_for_window,
    price_only_trend_candidates,
    strongest_non_overlapping,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_NEUTRAL,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402


@dataclass(frozen=True, slots=True)
class AlligatorMilestone:
    """Одна causal зміна Alligator після rejected MACD signal."""

    name: str
    timestamp: datetime
    bars_after_signal: int
    move_progress: float
    endpoint_remaining: float
    state: str
    regime: str
    phase: str
    normalized_slope: float | None
    normalized_opening: float | None


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _move_progress(
    window: TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
    event_index: int,
) -> tuple[float, float]:
    """Повернути частку move до event та залишок до endpoint strong window."""
    sign = _direction_sign(window.direction)
    start_close = events[window.start_index].close
    end_close = events[window.end_index].close
    event_close = events[event_index].close
    absolute_net_move = abs(end_close - start_close)
    assert absolute_net_move > 0.0
    progress = sign * (event_close - start_close) / absolute_net_move
    remaining = sign * (end_close - event_close) / absolute_net_move
    return progress, remaining


def _milestone(
    name: str,
    observation: WorkspaceAlligatorObservation,
    *,
    signal_index: int,
    event_index_by_timestamp: dict[datetime, int],
    window: TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
) -> AlligatorMilestone:
    event_index = event_index_by_timestamp[observation.timestamp]
    progress, remaining = _move_progress(window, events, event_index)
    return AlligatorMilestone(
        name=name,
        timestamp=observation.timestamp,
        bars_after_signal=event_index - signal_index,
        move_progress=progress,
        endpoint_remaining=remaining,
        state=observation.state,
        regime=observation.regime,
        phase=observation.regime_phase,
        normalized_slope=observation.normalized_slope,
        normalized_opening=observation.normalized_opening,
    )


def _first_observation(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    *,
    after: datetime,
    predicate: Callable[[WorkspaceAlligatorObservation], bool],
) -> WorkspaceAlligatorObservation:
    """Повернути перше causal observation після signal, що відповідає умові."""
    for observation in observations:
        if observation.timestamp < after:
            continue
        if predicate(observation):
            return observation
    raise AssertionError("Expected Alligator milestone was not found")


def _fmt_optional(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.6f}"


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

    candidates = price_only_trend_candidates(events)
    strong_windows = strongest_non_overlapping(candidates)

    while not session.completed:
        runtime.advance_replay()

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    observations = signal_filter.observations
    assert observations

    execution = runtime.replay_execution
    assert execution is not None
    records = runtime.historical_signal_records_for_test()
    trades = execution.trade_diagnostics()
    coverage = tuple(
        coverage_for_window(window, events, records, trades)
        for window in strong_windows
    )
    rejected = tuple(
        item for item in coverage if item.coverage == COVERAGE_ALLIGATOR_REJECT
    )
    assert len(rejected) == 1
    item = rejected[0]
    window = item.window
    assert window.direction == "SELL"

    start = events[window.start_index].timestamp
    end = events[window.end_index].timestamp
    aligned_quality_pass = tuple(
        record
        for record in records
        if start <= record.timestamp <= end
        and record.direction == window.direction
        and record.source_reason_code == "MACD_CROSS_ACCEPTED"
    )
    assert len(aligned_quality_pass) == 1
    signal: WorkspaceSignalRecord = aligned_quality_pass[0]
    assert signal.filter_reason_code == "ALLIGATOR_SAME_TIMEFRAME_SELL_REJECT"
    context = signal.filter_context
    assert context is not None
    assert context.regime == ALLIGATOR_REGIME_TREND_UP
    assert context.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    assert signal.alligator_confirmation == "SAME_TIMEFRAME_BULLISH"

    event_index_by_timestamp = {
        event.timestamp: index for index, event in enumerate(events)
    }
    signal_index = event_index_by_timestamp[signal.timestamp]
    assert window.start_index <= signal_index <= window.end_index
    signal_progress, signal_remaining = _move_progress(
        window,
        events,
        signal_index,
    )

    after_signal = tuple(
        observation
        for observation in observations
        if signal.timestamp <= observation.timestamp <= end
    )
    neutral_ending = _first_observation(
        after_signal,
        after=signal.timestamp,
        predicate=lambda observation: (
            observation.state == ALLIGATOR_STATE_NEUTRAL
            and observation.regime == ALLIGATOR_REGIME_TREND_UP
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING
        ),
    )
    bearish_state = _first_observation(
        after_signal,
        after=signal.timestamp,
        predicate=lambda observation: observation.state == ALLIGATOR_STATE_BEARISH,
    )
    down_starting = _first_observation(
        after_signal,
        after=signal.timestamp,
        predicate=lambda observation: (
            observation.state == ALLIGATOR_STATE_BEARISH
            and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_STARTING
        ),
    )
    down_active = _first_observation(
        after_signal,
        after=signal.timestamp,
        predicate=lambda observation: (
            observation.state == ALLIGATOR_STATE_BEARISH
            and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        ),
    )

    milestones = (
        _milestone(
            "NEUTRAL_ENDING_OLD_UPTREND",
            neutral_ending,
            signal_index=signal_index,
            event_index_by_timestamp=event_index_by_timestamp,
            window=window,
            events=events,
        ),
        _milestone(
            "BEARISH_STATE",
            bearish_state,
            signal_index=signal_index,
            event_index_by_timestamp=event_index_by_timestamp,
            window=window,
            events=events,
        ),
        _milestone(
            "TREND_DOWN_STARTING",
            down_starting,
            signal_index=signal_index,
            event_index_by_timestamp=event_index_by_timestamp,
            window=window,
            events=events,
        ),
        _milestone(
            "TREND_DOWN_ACTIVE",
            down_active,
            signal_index=signal_index,
            event_index_by_timestamp=event_index_by_timestamp,
            window=window,
            events=events,
        ),
    )

    signal_close = events[signal_index].close
    future = events[signal_index : window.end_index + 1]  # noqa
    favorable = signal_close - min(event.low for event in future)
    adverse = max(event.high for event in future) - signal_close
    segment_abs_net_move = abs(
        events[window.end_index].close - events[window.start_index].close
    )
    favorable_ratio = favorable / segment_abs_net_move
    adverse_ratio = adverse / segment_abs_net_move

    assert signal_progress < 0.25
    assert signal_remaining > 0.75
    assert favorable_ratio > 0.0
    assert milestones[-1].bars_after_signal > 0
    assert milestones[-1].move_progress > signal_progress
    assert milestones[-1].endpoint_remaining > 0.0

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Trend Alligator Reject 2025 result")
    print("  source_detector=PRICE_ONLY_M15_STRONG_WINDOW_V1")
    print("  alligator_reject_segments=1")
    print(
        "  segment="
        f"{start.isoformat()} -> {end.isoformat()} {window.direction} "
        f"move:{window.normalized_move:.2f}TR eff:{window.path_efficiency:.3f}"
    )
    print(
        "  rejected_quality_signal="
        f"{signal.timestamp.isoformat()} {signal.direction} "
        f"reason:{signal.filter_reason_code}"
    )
    print(
        "  signal_alligator="
        f"state:{signal.alligator_confirmation} "
        f"regime:{context.regime} phase:{context.regime_phase} "
        f"slope:{_fmt_optional(context.normalized_slope)} "
        f"opening:{_fmt_optional(context.normalized_opening)}"
    )
    print(
        "  signal_position_in_segment="
        f"bars_from_start:{signal_index - window.start_index} "
        f"move_progress:{signal_progress:.3f} "
        f"endpoint_remaining:{signal_remaining:.3f}"
    )
    print(
        "  post_signal_price_potential="
        f"mfe_remaining:{favorable_ratio:.3f} "
        f"mae_remaining:{adverse_ratio:.3f}"
    )
    print("  alligator_transition_milestones:")
    for milestone in milestones:
        print(
            f"    {milestone.name}: {milestone.timestamp.isoformat()} "
            f"delay_bars:{milestone.bars_after_signal} "
            f"move_progress:{milestone.move_progress:.3f} "
            f"endpoint_remaining:{milestone.endpoint_remaining:.3f} "
            f"state:{milestone.state} regime:{milestone.regime} "
            f"phase:{milestone.phase} "
            f"slope:{_fmt_optional(milestone.normalized_slope)} "
            f"opening:{_fmt_optional(milestone.normalized_opening)}"
        )
    print("  causal_reject_at_signal_time=True")
    print("  old_trend_state_lag_observed=True")
    print("  counterfactual_trades_created=False")
    print("  alligator_thresholds_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TREND_ALLIGATOR_REJECT_2025_CHECK=OK")


if __name__ == "__main__":
    main()
