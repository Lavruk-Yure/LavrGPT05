# -*- coding: utf-8 -*-
"""Runtime check for causal Alligator price-overlay chart series."""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_chart import (  # noqa: E402
    WORKSPACE_CHART_ROLE_PRICE_OVERLAY,
    WorkspaceChartSeries,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

EVENT_COUNT = 180


class FixedReplayService(WorkspaceReplayService):
    def __init__(self, events: tuple[WorkspaceMarketEvent, ...]) -> None:
        super().__init__()
        self.events = events

    def create_synthetic_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        _ = broker, symbol, timeframe
        settings = dict(replay_settings or {})
        return WorkspaceReplaySession(
            events=self.events,
            source_name="CHART_ALLIGATOR_OVERLAY_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    start = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    result: list[WorkspaceMarketEvent] = []
    for index in range(EVENT_COUNT):
        trend = index * 0.000015
        wave = math.sin(index / 7.0) * 0.00065
        close = 1.14000 + trend + wave
        open_value = close - math.sin(index / 3.0) * 0.00008
        high = max(open_value, close) + 0.00018
        low = min(open_value, close) - 0.00018
        spread = 0.00012
        result.append(
            WorkspaceMarketEvent(
                timestamp=start + timedelta(minutes=15 * index),
                broker="IB",
                symbol="EURUSD",
                timeframe="M15",
                bid=close - spread / 2.0,
                ask=close + spread / 2.0,
                spread=spread,
                open=open_value,
                high=high,
                low=low,
                close=close,
                volume=100.0 + index,
                source_mode=WORKSPACE_DATA_MODE_REPLAY,
            )
        )
    return tuple(result)


def _workspace(mode: str) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": True,
            "alligator_confirmation": mode,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": 1000},
    )


def _run(
    workspace: AlgorithmWorkspace,
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceRuntime, WorkspaceMacdAlligatorReplayAlgorithm]:
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm(workspace.algorithm)
    runtime = WorkspaceRuntime(
        workspace,
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    return runtime, algorithm


def _alligator_series_map(
    runtime: WorkspaceRuntime,
) -> dict[str, WorkspaceChartSeries]:
    snapshot = runtime.chart_snapshot()
    return {
        series.series_code: series
        for series in snapshot.series
        if series.series_code.startswith("ALLIGATOR_")
    }


def main() -> None:
    events = _events()

    same_runtime, same_algorithm = _run(
        _workspace("SAME_TIMEFRAME"),
        events,
    )
    same_snapshot = same_runtime.chart_snapshot()
    same_series = _alligator_series_map(same_runtime)
    expected_codes = {
        "ALLIGATOR_JAW",
        "ALLIGATOR_TEETH",
        "ALLIGATOR_LIPS",
    }
    factual_three_lines = set(same_series) == expected_codes
    assert factual_three_lines
    for chart_series in same_series.values():
        assert chart_series.role == WORKSPACE_CHART_ROLE_PRICE_OVERLAY
    viewport_bounded = True
    for chart_series in same_series.values():
        if len(chart_series.points) > len(same_snapshot.visible_events):
            viewport_bounded = False
            break
    assert viewport_bounded

    same_filter = same_algorithm.signal_filter
    assert same_filter is not None
    profile_metadata = True
    for chart_series in same_series.values():
        if (
            chart_series.timeframe != "M15"
            or chart_series.profile_uid != same_filter.profile_uid
            or chart_series.profile_revision != same_filter.profile_revision
        ):
            profile_metadata = False
            break
    assert profile_metadata

    same_runtime.scroll_chart_to(0)
    first_snapshot = same_runtime.chart_snapshot()
    full_history_navigation_preserved = (
        first_snapshot.visible_start == 0
        and first_snapshot.visible_events[0] == events[0]
    )
    assert full_history_navigation_preserved

    same_runtime.scroll_chart_to_latest()
    before_stop = same_runtime.chart_snapshot()
    same_runtime.stop("Chart overlay persistence check.")
    after_stop = same_runtime.chart_snapshot()
    stopped_overlay_preserved = (
        before_stop.visible_events == after_stop.visible_events
        and before_stop.series == after_stop.series
        and bool(after_stop.series)
    )
    assert stopped_overlay_preserved

    same_runtime.begin_start()
    new_run_clears_stale_overlay = not same_runtime.chart_snapshot().series
    assert new_run_clears_stale_overlay

    higher_runtime, higher_algorithm = _run(
        _workspace("HIGHER_1"),
        events,
    )
    higher_filter = higher_algorithm.signal_filter
    assert higher_filter is not None
    observations = higher_filter.observations
    assert len(observations) > 8
    target = observations[len(observations) // 2]
    target_index = observations.index(target)
    previous = observations[target_index - 1]
    boundary_timestamp: datetime = target.available_at
    before_timestamp: datetime = boundary_timestamp - timedelta(minutes=15)
    causal_timestamps: tuple[datetime, ...] = (
        before_timestamp,
        boundary_timestamp,
    )
    causal_series = higher_algorithm.chart_series(causal_timestamps)
    jaw = next(
        series for series in causal_series if series.series_code == "ALLIGATOR_JAW"
    )
    assert len(jaw.points) == 2
    higher_available_at_causal = (
        jaw.points[0].source_timestamp == previous.timestamp
        and jaw.points[0].available_at == previous.available_at
        and jaw.points[1].source_timestamp == target.timestamp
        and jaw.points[1].available_at == target.available_at
        and jaw.points[0].available_at <= jaw.points[0].timestamp
        and jaw.points[1].available_at <= jaw.points[1].timestamp
    )
    assert higher_available_at_causal

    higher_series_map = _alligator_series_map(higher_runtime)
    higher_series = (
        higher_series_map["ALLIGATOR_JAW"],
        higher_series_map["ALLIGATOR_TEETH"],
        higher_series_map["ALLIGATOR_LIPS"],
    )
    higher_timeframe_visible = True
    for chart_series in higher_series:
        if chart_series.timeframe != "H1":
            higher_timeframe_visible = False
            break
    assert higher_timeframe_visible

    no_look_ahead = True
    for chart_series in higher_series:
        for point in chart_series.points:
            if point.available_at is not None and point.available_at > point.timestamp:
                no_look_ahead = False
                break
        if not no_look_ahead:
            break
    assert no_look_ahead

    disabled_parameters = dict(_workspace("SAME_TIMEFRAME").parameters)
    disabled_parameters["alligator_filter_enabled"] = False
    disabled_workspace = replace(
        _workspace("SAME_TIMEFRAME"),
        parameters=disabled_parameters,
    )
    disabled_runtime, _disabled_algorithm = _run(
        disabled_workspace,
        events,
    )
    disabled_filter_hidden = not _alligator_series_map(disabled_runtime)
    assert disabled_filter_hidden

    print("Algorithm Workspace Chart Alligator Overlay result")
    print(f"  factual_three_lines={factual_three_lines}")
    print(f"  viewport_bounded={viewport_bounded}")
    print(f"  profile_metadata={profile_metadata}")
    print("  full_history_navigation_preserved=" f"{full_history_navigation_preserved}")
    print(f"  higher_available_at_causal={higher_available_at_causal}")
    print(f"  higher_timeframe_visible={higher_timeframe_visible}")
    print(f"  no_look_ahead={no_look_ahead}")
    print(f"  disabled_filter_hidden={disabled_filter_hidden}")
    print(f"  stopped_overlay_preserved={stopped_overlay_preserved}")
    print(f"  new_run_clears_stale_overlay={new_run_clears_stale_overlay}")
    print("ALGORITHM_WORKSPACE_CHART_ALLIGATOR_OVERLAY_CHECK=OK")


if __name__ == "__main__":
    main()
