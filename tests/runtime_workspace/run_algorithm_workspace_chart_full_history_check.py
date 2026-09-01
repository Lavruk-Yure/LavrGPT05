# -*- coding: utf-8 -*-
"""Runtime check for full-history Replay chart navigation."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_replay import REPLAY_SPEED_MAX  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_CHART_MAX_EVENTS,
    DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS,
)

HISTORY_EVENTS = 2600


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        workspace = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
            parameters={
                "warmup_bars": 2,
                "spread_limit": 0.00020,
            },
            replay_settings={
                "source_type": "SYNTHETIC",
                "start_utc": "2026-01-02T08:00:00Z",
                "event_count": HISTORY_EVENTS,
                "base_price": 1.14000,
                "spread": 0.00012,
                "speed": REPLAY_SPEED_MAX,
                "source": "FULL_HISTORY_CHART_TEST",
            },
        )

        runtime = controller.ensure_workspace_runtime(workspace.workspace_uid)
        controller.begin_workspace_runtime_start(workspace.workspace_uid)
        controller.complete_workspace_runtime_start(workspace.workspace_uid)
        session = runtime.replay_session
        assert session is not None
        assert len(session.events) == HISTORY_EVENTS

        before_advance = runtime.chart_snapshot()
        future_events_hidden = (
            before_advance.total_events == 0
            and not before_advance.visible_events
            and not before_advance.events
        )
        assert future_events_hidden

        emitted = controller.advance_workspace_replay(workspace.workspace_uid)
        assert len(emitted) == HISTORY_EVENTS
        assert session.completed

        latest = runtime.chart_snapshot()
        retained_buffer_bounded = (
            len(latest.events) == DEFAULT_WORKSPACE_CHART_MAX_EVENTS
            and latest.events[0]
            == session.events[HISTORY_EVENTS - DEFAULT_WORKSPACE_CHART_MAX_EVENTS]
        )
        renderer_viewport_bounded = (
            len(latest.visible_events) == DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS
        )
        assert latest.total_events == HISTORY_EVENTS
        assert retained_buffer_bounded
        assert renderer_viewport_bounded
        assert latest.visible_events[-1] == session.events[-1]

        controller.scroll_workspace_chart_to(workspace.workspace_uid, 0)
        first = runtime.chart_snapshot()
        home_reaches_first = (
            first.visible_start == 0 and first.visible_events[0] == session.events[0]
        )
        assert home_reaches_first

        middle_start = HISTORY_EVENTS // 2
        controller.scroll_workspace_chart_to(
            workspace.workspace_uid,
            middle_start,
        )
        middle = runtime.chart_snapshot()
        middle_history_accessible = (
            middle.visible_start == middle_start
            and middle.visible_events[0] == session.events[middle_start]
        )
        assert middle_history_accessible

        controller.scroll_workspace_chart_to_latest(workspace.workspace_uid)
        end = runtime.chart_snapshot()
        expected_last_start = HISTORY_EVENTS - DEFAULT_WORKSPACE_CHART_VISIBLE_EVENTS
        end_reaches_last = (
            end.visible_start == expected_last_start
            and end.visible_events[-1] == session.events[-1]
            and end.at_latest
        )
        assert end_reaches_last

        full_scroll_range = end.total_events - end.visible_count == expected_last_start
        assert full_scroll_range

        print("Algorithm Workspace Chart Full History result")
        print(f"  history_events={HISTORY_EVENTS}")
        print(f"  retained_events={len(latest.events)}")
        print(f"  visible_events={len(latest.visible_events)}")
        print(f"  future_events_hidden={future_events_hidden}")
        print(f"  retained_buffer_bounded={retained_buffer_bounded}")
        print(f"  renderer_viewport_bounded={renderer_viewport_bounded}")
        print(f"  home_reaches_first={home_reaches_first}")
        print(f"  middle_history_accessible={middle_history_accessible}")
        print(f"  end_reaches_last={end_reaches_last}")
        print(f"  full_scroll_range={full_scroll_range}")
        print("ALGORITHM_WORKSPACE_CHART_FULL_HISTORY_CHECK=OK")


if __name__ == "__main__":
    main()
