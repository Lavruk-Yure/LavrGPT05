# -*- coding: utf-8 -*-
"""RoadMap102: diagnostic structural-reject strong trend OOS 2025.

Runner продовжує frozen price-only Trend Coverage без зміни production logic.
Він бере єдиний strong M15 trend segment, де MACD Quality і SAME_TIMEFRAME
Alligator вже дозволили aligned BUY, але Candidate F відхилив signal через
VOLATILITY_SPIKE_WITH_DETERIORATION.

Діагностика розкладає causal умову guard на окремі складові: range spike,
opening deterioration і slope deterioration. Окремо описується структура
самого signal bar та post-event price continuation. Майбутні bars не
використовуються як entry gate, counterfactual trade не створюється.
"""

from __future__ import annotations

import re
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
    COVERAGE_STRUCTURAL_REJECT,
    TrendWindow,
    coverage_for_window,
    price_only_trend_candidates,
    strongest_non_overlapping,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_UP,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    built_in_workspace_indicator_profile,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

DETAIL_PATTERN = re.compile(
    r"active_age=(?P<active_age>\d+); "
    r"opening=(?P<opening>[+-]?\d+(?:\.\d+)?); "
    r"opening_delta=(?P<opening_delta>[+-]?\d+(?:\.\d+)?); "
    r"slope=(?P<slope>[+-]?\d+(?:\.\d+)?); "
    r"slope_delta=(?P<slope_delta>[+-]?\d+(?:\.\d+)?); "
    r"range_ratio=(?P<range_ratio>[+-]?\d+(?:\.\d+)?)"
)


@dataclass(frozen=True, slots=True)
class StructuralDetail:
    """Causal numeric evidence одного Candidate F structural reject."""

    active_age: int
    opening: float
    opening_delta: float
    slope: float
    slope_delta: float
    range_ratio: float


def _parse_structural_detail(record: WorkspaceSignalRecord) -> StructuralDetail:
    """Витягнути numeric evidence з canonical Candidate F reason."""
    match = DETAIL_PATTERN.search(record.reason)
    assert match is not None, record.reason
    return StructuralDetail(
        active_age=int(match.group("active_age")),
        opening=float(match.group("opening")),
        opening_delta=float(match.group("opening_delta")),
        slope=float(match.group("slope")),
        slope_delta=float(match.group("slope_delta")),
        range_ratio=float(match.group("range_ratio")),
    )


def _profile_float(parameters: dict[str, object], key: str) -> float:
    """Повернути numeric float parameter без неявного cast з object."""
    value = parameters[key]
    assert isinstance(value, (int, float))
    assert not isinstance(value, bool)
    return float(value)


def _profile_int(parameters: dict[str, object], key: str) -> int:
    """Повернути integer parameter без неявного cast з object."""
    value = parameters[key]
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _progress_at_price(
    window: TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
    price: float,
) -> float:
    """Повернути directional частку endpoint move для довільної ціни."""
    sign = _direction_sign(window.direction)
    start_close = events[window.start_index].close
    end_close = events[window.end_index].close
    net_move = abs(end_close - start_close)
    assert net_move > 0.0
    return sign * (price - start_close) / net_move


def _aligned_structural_record(
    records: tuple[WorkspaceSignalRecord, ...],
    window: TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
) -> WorkspaceSignalRecord:
    start = events[window.start_index].timestamp
    end = events[window.end_index].timestamp
    matches = tuple(
        record
        for record in records
        if start <= record.timestamp <= end
        and record.direction == window.direction
        and record.source_reason_code == "MACD_CROSS_ACCEPTED"
        and record.filter_reason_code == ALLIGATOR_REASON_VOLATILITY_SPIKE
    )
    assert len(matches) == 1
    return matches[0]


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

    execution = runtime.replay_execution
    assert execution is not None
    records = runtime.historical_signal_records_for_test()
    trades = execution.trade_diagnostics()
    coverage = tuple(
        coverage_for_window(window, events, records, trades)
        for window in strong_windows
    )
    structural = tuple(
        item for item in coverage if item.coverage == COVERAGE_STRUCTURAL_REJECT
    )
    assert len(structural) == 1
    item = structural[0]
    window = item.window
    assert window.direction == "BUY"

    start_event = events[window.start_index]
    end_event = events[window.end_index]
    signal = _aligned_structural_record(records, window, events)
    assert signal.alligator_confirmation == "SAME_TIMEFRAME_BULLISH"
    context = signal.filter_context
    assert context is not None
    assert context.regime == ALLIGATOR_REGIME_TREND_UP
    assert context.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    assert context.active_age is not None
    assert context.normalized_slope is not None
    assert context.normalized_opening is not None
    assert len(context.diagnostic_observations) == 3

    detail = _parse_structural_detail(signal)
    assert detail.active_age == context.active_age
    assert abs(detail.slope - context.normalized_slope) < 1e-6
    assert abs(detail.opening - context.normalized_opening) < 1e-6

    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    parameters = profile.parameters
    range_threshold = _profile_float(parameters, "spike_min_range_ratio")
    opening_delta_threshold = _profile_float(
        parameters,
        "spike_max_opening_delta",
    )
    slope_delta_threshold = _profile_float(parameters, "spike_max_slope_delta")
    volatility_lookback = _profile_int(parameters, "volatility_lookback_bars")

    range_trigger = detail.range_ratio >= range_threshold
    opening_deterioration = detail.opening_delta < opening_delta_threshold
    slope_deterioration = detail.slope_delta < slope_delta_threshold
    assert range_trigger
    assert not opening_deterioration
    assert slope_deterioration

    event_index_by_timestamp = {
        event.timestamp: index for index, event in enumerate(events)
    }
    signal_index = event_index_by_timestamp[signal.timestamp]
    assert window.start_index <= signal_index <= window.end_index
    signal_event = events[signal_index]
    prior_events = events[signal_index - volatility_lookback : signal_index]  # noqa
    assert len(prior_events) == volatility_lookback
    prior_mean_range = sum(event.high - event.low for event in prior_events) / float(
        volatility_lookback
    )
    signal_range = signal_event.high - signal_event.low
    assert prior_mean_range > 0.0
    computed_range_ratio = signal_range / prior_mean_range
    assert abs(computed_range_ratio - detail.range_ratio) < 0.001

    body = signal_event.close - signal_event.open
    body_fraction = abs(body) / signal_range
    close_location = (signal_event.close - signal_event.low) / signal_range
    aligned_impulse_bar = body > 0.0 and close_location > 0.9
    assert aligned_impulse_bar

    open_progress = _progress_at_price(window, events, signal_event.open)
    close_progress = _progress_at_price(window, events, signal_event.close)
    endpoint_remaining = 1.0 - close_progress
    bar_contribution = close_progress - open_progress
    assert open_progress < 0.10
    assert close_progress > 0.50
    assert endpoint_remaining > 0.30
    assert bar_contribution > 0.50

    continuation_progress: list[tuple[int, datetime, float]] = []
    for bars_after in (1, 2, 3):
        index = signal_index + bars_after
        assert index <= window.end_index
        event = events[index]
        continuation = (
            _direction_sign(window.direction)
            * (event.close - signal_event.close)
            / abs(end_event.close - start_event.close)
        )
        continuation_progress.append((bars_after, event.timestamp, continuation))
    assert all(value > 0.0 for _, _, value in continuation_progress)

    aligned_trades = tuple(
        trade
        for trade in trades
        if start_event.timestamp <= trade.signal_timestamp <= end_event.timestamp
        and trade.direction == window.direction
    )
    assert not aligned_trades

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Trend Structural Reject 2025 result")
    print("  source_detector=PRICE_ONLY_M15_STRONG_WINDOW_V1")
    print("  structural_reject_segments=1")
    print(
        "  segment="
        f"{start_event.timestamp.isoformat()} -> {end_event.timestamp.isoformat()} "
        f"{window.direction} move:{window.normalized_move:.2f}TR "
        f"eff:{window.path_efficiency:.3f}"
    )
    print(
        "  rejected_quality_signal="
        f"{signal.timestamp.isoformat()} {signal.direction} "
        f"reason:{signal.filter_reason_code}"
    )
    print(
        "  signal_alligator="
        f"state:{signal.alligator_confirmation} regime:{context.regime} "
        f"phase:{context.regime_phase} active_age:{context.active_age} "
        f"slope:{context.normalized_slope:.6f} "
        f"opening:{context.normalized_opening:.6f}"
    )
    print(
        "  structural_guard="
        f"range_ratio:{detail.range_ratio:.3f}/{range_threshold:.3f} "
        f"opening_delta:{detail.opening_delta:+.6f}/{opening_delta_threshold:+.3f} "
        f"slope_delta:{detail.slope_delta:+.6f}/{slope_delta_threshold:+.3f}"
    )
    print(
        "  trigger_components="
        f"range_spike:{range_trigger},"
        f"opening_deterioration:{opening_deterioration},"
        f"slope_deterioration:{slope_deterioration}"
    )
    print(
        "  signal_bar_structure="
        f"range:{signal_range:.6f} prior_mean_range:{prior_mean_range:.6f} "
        f"body_fraction:{body_fraction:.3f} close_location:{close_location:.3f} "
        f"aligned_impulse:{aligned_impulse_bar}"
    )
    print(
        "  signal_position_in_segment="
        f"bars_from_start:{signal_index - window.start_index} "
        f"open_progress:{open_progress:.3f} close_progress:{close_progress:.3f} "
        f"signal_bar_contribution:{bar_contribution:.3f} "
        f"endpoint_remaining:{endpoint_remaining:.3f}"
    )
    print("  post_signal_close_continuation:")
    for bars_after, timestamp, continuation in continuation_progress:
        print(
            f"    +{bars_after} bar: {timestamp.isoformat()} "
            f"continuation:{continuation:+.3f}"
        )
    print("  aligned_trade_created=False")
    print("  causal_structural_reject_at_signal_time=True")
    print("  signal_bar_is_aligned_large_impulse=True")
    print("  future_continuation_used_as_entry_gate=False")
    print("  counterfactual_trades_created=False")
    print("  candidate_f_thresholds_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TREND_STRUCTURAL_REJECT_2025_CHECK=OK")


if __name__ == "__main__":
    main()
