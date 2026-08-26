# -*- coding: utf-8 -*-
"""Runtime check for bounded WSP chart history and viewport controls."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_chart import (  # noqa: E402
    WorkspaceChartError,
    WorkspaceChartModel,
)
from core.workspace_replay import WorkspaceReplayService  # noqa: E402


def main() -> None:
    service = WorkspaceReplayService()
    session = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "start_utc": "2026-07-01T08:00:00Z",
            "event_count": 30,
            "base_price": 1.14500,
            "spread": 0.00014,
            "speed": 1,
            "source": "SYNTHETIC_CHART_TEST",
        },
    )

    model = WorkspaceChartModel(max_events=20, visible_count=12)
    model.extend(tuple(session.events))
    snapshot = model.snapshot()

    assert snapshot.total_events == 20
    assert snapshot.events == tuple(session.events[-20:])
    assert len(snapshot.visible_events) == 12
    assert snapshot.visible_start == 8
    assert snapshot.visible_end == 20
    assert snapshot.at_latest
    assert snapshot.cursor_index == 19
    assert snapshot.cursor_timestamp == session.events[-1].timestamp
    assert snapshot.current_close == session.events[-1].close
    assert snapshot.current_bid == session.events[-1].bid
    assert snapshot.current_ask == session.events[-1].ask
    assert snapshot.current_spread == session.events[-1].spread

    model.scroll_to(2)
    scrolled = model.snapshot()
    assert scrolled.visible_start == 2
    assert not scrolled.at_latest
    assert scrolled.visible_events[0] == session.events[-18]

    model.zoom_out()
    zoomed_out = model.snapshot()
    assert zoomed_out.visible_count == 15
    assert zoomed_out.visible_start == 0
    assert zoomed_out.visible_end == 15

    model.zoom_in()
    zoomed_in = model.snapshot()
    assert zoomed_in.visible_count == 12
    assert zoomed_in.visible_start == 3
    assert zoomed_in.visible_end == zoomed_out.visible_end

    model.scroll_to_latest()
    latest = model.snapshot()
    assert latest.at_latest
    assert latest.visible_end == latest.total_events

    replacement = session.events[-1]
    model.append(replacement)
    replaced = model.snapshot()
    assert replaced.total_events == 20
    assert replaced.events[-1] == replacement

    chronology_blocked = False
    try:
        model.append(session.events[0])
    except WorkspaceChartError:
        chronology_blocked = True
    assert chronology_blocked

    model.clear()
    cleared = model.snapshot()
    assert cleared.total_events == 0
    assert not cleared.visible_events
    assert cleared.cursor_timestamp is None

    print("Algorithm Workspace Chart result")
    print("  source=SYNTHETIC_CHART_TEST")
    print("  input_events=30")
    print(f"  bounded_events={snapshot.total_events}")
    print(f"  visible_events={len(snapshot.visible_events)}")
    print(f"  visible_range={snapshot.visible_start}:{snapshot.visible_end}")
    print(f"  replay_cursor={snapshot.cursor_timestamp.isoformat()}")
    print("  zoom_in_out=True")
    print("  horizontal_scroll=True")
    print("  follow_latest=True")
    print(f"  chronology_blocked={chronology_blocked}")
    print("  clear_on_new_run=True")
    print("ALGORITHM_WORKSPACE_CHART_CHECK=OK")


if __name__ == "__main__":
    main()
