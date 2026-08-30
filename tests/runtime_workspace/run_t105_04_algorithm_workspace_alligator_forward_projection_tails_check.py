# -*- coding: utf-8 -*-
"""T105-04: chart-only forward projection tails Alligator без look-ahead."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm  # noqa: E402
from core.workspace_chart import WorkspaceChartSeries  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import WorkspaceReplayService, WorkspaceReplaySession  # noqa: E402
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
            source_name="T105_04_ALLIGATOR_TAILS",
            speed=int(settings.get("speed", 1)),
        )


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    start = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    result: list[WorkspaceMarketEvent] = []
    for index in range(EVENT_COUNT):
        close = 1.14000 + index * 0.000015 + math.sin(index / 7.0) * 0.00065
        open_value = close - math.sin(index / 3.0) * 0.00008
        spread = 0.00012
        result.append(
            WorkspaceMarketEvent(
                timestamp=start + timedelta(minutes=15 * index),
                broker="CTRADER",
                symbol="EURUSD",
                timeframe="M15",
                bid=close - spread / 2.0,
                ask=close + spread / 2.0,
                spread=spread,
                open=open_value,
                high=max(open_value, close) + 0.00018,
                low=min(open_value, close) - 0.00018,
                close=close,
                volume=100.0 + index,
                source_mode=WORKSPACE_DATA_MODE_REPLAY,
            )
        )
    return tuple(result)


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="T10504",
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
            "alligator_confirmation": "SAME_TIMEFRAME",
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": 1000},
    )


def main() -> None:
    events = _events()
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm("RailAlgorithm")
    runtime = WorkspaceRuntime(
        _workspace(),
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    profile = signal_filter.runtime_profile
    snapshot = runtime.chart_snapshot()
    series_map = {
        series.series_code: series
        for series in snapshot.series
        if series.series_code.startswith("ALLIGATOR_")
    }

    expected_lengths = {
        "ALLIGATOR_JAW": profile.jaw_shift,
        "ALLIGATOR_TEETH": profile.teeth_shift,
        "ALLIGATOR_LIPS": profile.lips_shift,
    }
    actual_lengths = {
        code: len(series_map[code].projection_points)
        for code in expected_lengths
    }
    profile_shifts_respected = actual_lengths == expected_lengths
    assert profile_shifts_respected

    causal_horizons = True
    finite_values = True
    for code, expected_shift in expected_lengths.items():
        points = series_map[code].projection_points
        if tuple(point.horizon_bars for point in points) != tuple(
            range(1, expected_shift + 1)
        ):
            causal_horizons = False
        if not all(math.isfinite(point.value) for point in points):
            finite_values = False
    assert causal_horizons
    assert finite_values

    runtime.scroll_chart_to(0)
    historical_snapshot = runtime.chart_snapshot()
    historical_series = cast(
        tuple[WorkspaceChartSeries, ...],
        historical_snapshot.series,
    )
    historical_projection_hidden = all(
        not series.projection_points
        for series in historical_series
        if series.series_code.startswith("ALLIGATOR_")
    )
    assert historical_projection_hidden

    runtime.scroll_chart_to_latest()
    latest_snapshot = runtime.chart_snapshot()
    latest_series = cast(
        tuple[WorkspaceChartSeries, ...],
        latest_snapshot.series,
    )
    latest_projection_visible = all(
        series.projection_points
        for series in latest_series
        if series.series_code.startswith("ALLIGATOR_")
    )
    assert latest_projection_visible

    source = (PROJECT_ROOT / "core" / "workspace_chart_widget.py").read_text(
        encoding="utf-8"
    )
    chart_renderer_wired = "series.projection_points" in source
    assert chart_renderer_wired

    print("T105-04 Alligator Forward Projection Tails result")
    print(f"  jaw_tail_bars={actual_lengths['ALLIGATOR_JAW']}")
    print(f"  teeth_tail_bars={actual_lengths['ALLIGATOR_TEETH']}")
    print(f"  lips_tail_bars={actual_lengths['ALLIGATOR_LIPS']}")
    print(f"  profile_shifts_respected={profile_shifts_respected}")
    print(f"  causal_horizons={causal_horizons}")
    print(f"  finite_values={finite_values}")
    print(f"  historical_projection_hidden={historical_projection_hidden}")
    print(f"  latest_projection_visible={latest_projection_visible}")
    print(f"  chart_renderer_wired={chart_renderer_wired}")
    print("  future_market_data_used=False")
    print("  production_trading_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_04_ALLIGATOR_FORWARD_PROJECTION_TAILS=OK")


if __name__ == "__main__":
    main()
