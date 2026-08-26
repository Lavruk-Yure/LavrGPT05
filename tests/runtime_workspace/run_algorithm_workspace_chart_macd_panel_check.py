# -*- coding: utf-8 -*-
"""Runtime check for factual MACD series in a synchronized lower chart panel."""

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
    WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM,
    WORKSPACE_CHART_ROLE_INDICATOR_LINE,
    WorkspaceChartSeries,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

EVENT_COUNT = 240
WIDGET_PATH = PROJECT_ROOT / "core" / "workspace_chart_widget.py"


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
            source_name="CHART_MACD_PANEL_TEST",
            speed=int(settings.get("speed", 1)),
        )


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    start = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    result: list[WorkspaceMarketEvent] = []
    for index in range(EVENT_COUNT):
        wave = math.sin(index / 5.0) * 0.00115
        slower_wave = math.sin(index / 19.0) * 0.00055
        close = 1.14000 + wave + slower_wave
        open_value = close - math.sin(index / 3.0) * 0.00009
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


def _workspace() -> AlgorithmWorkspace:
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
            "alligator_filter_enabled": False,
            "alligator_confirmation": "SAME_TIMEFRAME",
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


def _macd_series(runtime: WorkspaceRuntime) -> dict[str, WorkspaceChartSeries]:
    snapshot = runtime.chart_snapshot()
    return {
        series.series_code: series
        for series in snapshot.series
        if series.series_code.startswith("MACD_")
    }


def main() -> None:
    events = _events()
    runtime, algorithm = _run(_workspace(), events)
    snapshot = runtime.chart_snapshot()
    series = _macd_series(runtime)

    expected_codes = {"MACD_VALUE", "MACD_SIGNAL", "MACD_HISTOGRAM"}
    factual_three_series = set(series) == expected_codes
    assert factual_three_series
    assert series["MACD_VALUE"].role == WORKSPACE_CHART_ROLE_INDICATOR_LINE
    assert series["MACD_SIGNAL"].role == WORKSPACE_CHART_ROLE_INDICATOR_LINE
    assert (
        series["MACD_HISTOGRAM"].role
        == WORKSPACE_CHART_ROLE_INDICATOR_HISTOGRAM
    )

    source = algorithm.source
    assert source is not None
    observations = {item.timestamp: item for item in source.observations}
    field_by_code = {
        "MACD_VALUE": "macd_value",
        "MACD_SIGNAL": "signal_value",
        "MACD_HISTOGRAM": "histogram",
    }
    factual_values = True
    for code, chart_series in series.items():
        field_name = field_by_code[code]
        for point in chart_series.points:
            observation = observations.get(point.timestamp)
            if observation is None:
                factual_values = False
                break
            expected = getattr(observation, field_name)
            if expected is None or point.value != float(expected):
                factual_values = False
                break
            if point.source_timestamp != observation.timestamp:
                factual_values = False
                break
            if point.available_at != observation.timestamp:
                factual_values = False
                break
        if not factual_values:
            break
    assert factual_values

    viewport_bounded = True
    visible_timestamps = {event.timestamp for event in snapshot.visible_events}
    synchronized_viewport = True
    for chart_series in series.values():
        if len(chart_series.points) > len(snapshot.visible_events):
            viewport_bounded = False
        for point in chart_series.points:
            if point.timestamp not in visible_timestamps:
                synchronized_viewport = False
                break
    assert viewport_bounded
    assert synchronized_viewport

    profile_metadata = True
    for chart_series in series.values():
        if (
            chart_series.timeframe != "M15"
            or chart_series.profile_uid != source.profile_uid
            or chart_series.profile_revision != source.profile_revision
        ):
            profile_metadata = False
            break
    assert profile_metadata

    histogram_values = [
        point.value for point in series["MACD_HISTOGRAM"].points
    ]
    histogram_both_sides = (
        any(value > 0.0 for value in histogram_values)
        and any(value < 0.0 for value in histogram_values)
    )
    assert histogram_both_sides

    runtime.scroll_chart_to(0)
    first_snapshot = runtime.chart_snapshot()
    first_macd = _macd_series(runtime)
    first_visible_timestamps = {
        event.timestamp for event in first_snapshot.visible_events
    }
    full_history_navigation_preserved = first_snapshot.visible_start == 0
    for chart_series in first_macd.values():
        for point in chart_series.points:
            if point.timestamp not in first_visible_timestamps:
                full_history_navigation_preserved = False
                break
    assert full_history_navigation_preserved

    runtime.scroll_chart_to_latest()
    before_stop = runtime.chart_snapshot()
    before_stop_macd = _macd_series(runtime)
    runtime.stop("MACD panel persistence check.")
    after_stop = runtime.chart_snapshot()
    after_stop_macd = _macd_series(runtime)
    stopped_panel_preserved = (
        before_stop.visible_events == after_stop.visible_events
        and bool(after_stop_macd)
        and before_stop_macd == after_stop_macd
    )
    assert stopped_panel_preserved

    runtime.begin_start()
    new_run_clears_stale_panel = not _macd_series(runtime)
    assert new_run_clears_stale_panel

    disabled_parameters = dict(_workspace().parameters)
    disabled_parameters["macd_signal_enabled"] = False
    disabled_workspace = replace(
        _workspace(),
        parameters=disabled_parameters,
    )
    disabled_runtime, _disabled_algorithm = _run(
        disabled_workspace,
        events,
    )
    disabled_source_hidden = not _macd_series(disabled_runtime)
    assert disabled_source_hidden

    widget_source = WIDGET_PATH.read_text(encoding="utf-8")
    widget_panel_contract = all(
        token in widget_source
        for token in (
            "class WorkspaceMacdCanvas",
            'self.macd_canvas.setObjectName("wspMacdCanvas")',
            'self.splitter.setObjectName("splitChartMacd")',
            "self.splitter.addWidget(self.macd_panel)",
            'self.macd_vertical_scrollbar.setObjectName("scrollMacdVertical")',
            "self.macd_canvas.has_macd_series(snapshot)",
        )
    )
    assert widget_panel_contract

    macd_four_color_legend = all(
        token in widget_source
        for token in (
            'f"{histogram_label} +"',
            'f"{histogram_label} −"',
            "QColor(38, 166, 154)",
            "QColor(239, 83, 80)",
        )
    )
    assert macd_four_color_legend

    print("Algorithm Workspace Chart MACD Panel result")
    print(f"  factual_three_series={factual_three_series}")
    print(f"  factual_values={factual_values}")
    print(f"  viewport_bounded={viewport_bounded}")
    print(f"  synchronized_viewport={synchronized_viewport}")
    print(f"  profile_metadata={profile_metadata}")
    print(f"  histogram_both_sides={histogram_both_sides}")
    print(
        "  full_history_navigation_preserved="
        f"{full_history_navigation_preserved}"
    )
    print(f"  stopped_panel_preserved={bool(stopped_panel_preserved)}")
    print(f"  new_run_clears_stale_panel={new_run_clears_stale_panel}")
    print(f"  disabled_source_hidden={disabled_source_hidden}")
    print(f"  widget_panel_contract={widget_panel_contract}")
    print(f"  macd_four_color_legend={macd_four_color_legend}")
    print("ALGORITHM_WORKSPACE_CHART_MACD_PANEL_CHECK=OK")


if __name__ == "__main__":
    main()
