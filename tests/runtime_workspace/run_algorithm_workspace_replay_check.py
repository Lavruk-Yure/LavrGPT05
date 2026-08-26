# -*- coding: utf-8 -*-
"""Runtime check for deterministic WSP synthetic Replay sessions."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_replay import (  # noqa: E402
    REPLAY_SPEED_MAX,
    REPLAY_SPEEDS,
    REPLAY_STATE_COMPLETED,
    REPLAY_STATE_PAUSED,
    REPLAY_STATE_RUNNING,
    WorkspaceReplayError,
    WorkspaceReplayService,
)


def main() -> None:
    service = WorkspaceReplayService()
    settings = {
        "start_utc": "2026-07-01T08:00:00Z",
        "event_count": 18,
        "base_price": 1.14500,
        "spread": 0.00014,
        "speed": 2,
        "source": "SYNTHETIC_TEST",
    }
    first = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings=settings,
    )
    second = service.create_synthetic_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings=settings,
    )

    assert first.events == second.events
    assert first.speed == 2
    assert first.source_name == "SYNTHETIC_TEST"

    first.start()
    assert first.state == REPLAY_STATE_RUNNING
    first_batch = first.advance()
    assert len(first_batch) == 2
    assert first.index == 2

    first.pause()
    assert first.state == REPLAY_STATE_PAUSED
    assert first.advance() == []
    stepped_event = first.step()
    assert stepped_event == first.events[2]
    assert first.index == 3
    assert first.state == REPLAY_STATE_PAUSED

    for supported_speed in REPLAY_SPEEDS:
        first.set_speed(supported_speed)
        assert first.speed == supported_speed
    first.set_speed(5)
    invalid_speed_blocked = False
    try:
        first.set_speed(3)
    except WorkspaceReplayError:
        invalid_speed_blocked = True
    assert invalid_speed_blocked
    first.resume()
    assert len(first.advance()) == 5
    assert first.index == 8

    while not first.completed:
        first.advance()
    assert first.state == REPLAY_STATE_COMPLETED
    assert first.index == len(first.events)
    assert first.current_event == first.events[-1]

    print("Algorithm Workspace Replay result")
    print(f"  source={first.source_name}")
    print(f"  events={len(first.events)}")
    print(f"  first_timestamp={first.events[0].timestamp.isoformat()}")
    print(f"  last_timestamp={first.events[-1].timestamp.isoformat()}")
    print("  deterministic=True")
    print("  pause_step=True")
    assert REPLAY_SPEED_MAX == 0
    print("  supported_speeds=1x,2x,5x,10x,100x,1000x,MAX")
    print(f"  invalid_speed_blocked={invalid_speed_blocked}")
    print(f"  completed_state={first.state}")
    print("ALGORITHM_WORKSPACE_REPLAY_CHECK=OK")


if __name__ == "__main__":
    main()
