# -*- coding: utf-8 -*-
"""Runtime check for WSP lifecycle, Replay control and local journal."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_ERROR,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
    WORKSPACE_STATE_STOPPING,
    AlgorithmWorkspace,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_WARMUP,
    WorkspaceRuntime,
    WorkspaceRuntimeError,
)


def main() -> None:
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "start_utc": "2026-07-01T08:00:00Z",
            "event_count": 12,
            "speed": 2,
        },
    )
    runtime = WorkspaceRuntime(workspace)
    assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
    assert runtime.context.workspace_uid == workspace.workspace_uid
    assert runtime.context.algorithm_id == "RailAlgorithm"
    assert runtime.context.warmup_bars_required == 2
    assert runtime.context.spread_limit == 0.00020

    runtime.begin_start()
    assert runtime.context.runtime_state == WORKSPACE_STATE_STARTING

    repeated_start_blocked = False
    try:
        runtime.begin_start()
    except WorkspaceRuntimeError:
        repeated_start_blocked = True
    assert repeated_start_blocked

    runtime.complete_start()
    assert runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WARMUP
    assert runtime.replay_session is not None
    assert runtime.replay_session.speed == 2
    assert not runtime.can_form_signal()

    first_events = runtime.advance_replay()
    assert len(first_events) == 2
    assert runtime.context.market_event_count == 2
    assert runtime.context.current_market_event == first_events[-1]
    assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
    assert runtime.can_form_signal()
    startup_phase_before_stop = runtime.context.startup_phase

    assert runtime.toggle_replay_pause()
    stepped = runtime.step_replay()
    assert stepped is not None
    assert runtime.context.market_event_count == 3
    assert not runtime.toggle_replay_pause()

    runtime.set_replay_speed(5)
    next_events = runtime.advance_replay()
    assert len(next_events) == 5
    assert runtime.context.market_event_count == 8

    runtime.context.set_runtime_snapshot(
        active_orders_count=0,
        positions_count=1,
        current_profit=69.0,
        peak_profit=100.0,
    )
    assert runtime.context.profit_drawdown == 31.0
    profit_drawdown = runtime.context.profit_drawdown
    assert runtime.close_block_reason() == "runtime_state=RUNNING"

    runtime.begin_stop()
    assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPING
    runtime.complete_stop()
    assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
    assert not runtime.can_form_signal()
    assert runtime.close_block_reason() == "open_positions=1"

    runtime.context.set_runtime_snapshot()
    assert runtime.close_block_reason() is None

    journal_events = [entry.event for entry in runtime.journal]
    assert journal_events.count("STATE_CHANGED") == 4
    assert "SESSION_STARTED" in journal_events
    assert "DATA_LOADED" in journal_events
    assert "WARMUP_COMPLETED" in journal_events
    assert "SPREAD_ACCEPTED" in journal_events
    assert "PAUSED" in journal_events
    assert "RESUMED" in journal_events
    assert "SPEED_CHANGED" in journal_events
    assert "EVENT_ACCEPTED" in journal_events

    broker_workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="GBPUSD",
        timeframe="H1",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
    )
    broker_runtime = WorkspaceRuntime(broker_workspace)
    unsupported_broker_mode_blocked = False
    try:
        broker_runtime.start()
    except WorkspaceRuntimeError:
        unsupported_broker_mode_blocked = True
    assert unsupported_broker_mode_blocked
    assert broker_runtime.context.runtime_state == WORKSPACE_STATE_ERROR

    print("Algorithm Workspace Runtime State result")
    print(f"  workspace_uid={workspace.workspace_uid}")
    print(f"  final_state={runtime.context.runtime_state}")
    print(f"  market_events={runtime.context.market_event_count}")
    print(f"  journal_entries={len(runtime.journal)}")
    print(f"  repeated_start_blocked={repeated_start_blocked}")
    print(f"  startup_phase={startup_phase_before_stop}")
    print("  warmup_bars=2")
    print(f"  profit_drawdown={profit_drawdown:.1f}%")
    print(
        f"  unsupported_broker_mode_blocked={unsupported_broker_mode_blocked}"
    )
    print(f"  broker_error_state={broker_runtime.context.runtime_state}")
    print("ALGORITHM_WORKSPACE_RUNTIME_STATE_CHECK=OK")


if __name__ == "__main__":
    main()
