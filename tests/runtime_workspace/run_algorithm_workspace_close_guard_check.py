# -*- coding: utf-8 -*-
"""Runtime check for deterministic WSP close-safety blockers."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STOPPED,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_close_guard import (  # noqa: E402
    WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS,
    WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION,
    WORKSPACE_CLOSE_BLOCK_MARKET_EVENT,
    WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS,
    WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE,
    WORKSPACE_CLOSE_BLOCK_REPLAY_STEP,
    WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import WorkspaceReplaySession  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WorkspaceRuntime,
    WorkspaceRuntimeError,
)


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def _replay_session() -> WorkspaceReplaySession:
    event = WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 25, 11, 30, tzinfo=UTC),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=1.17074,
        ask=1.17086,
        spread=0.00012,
        open=1.17000,
        high=1.17120,
        low=1.16940,
        close=1.17080,
        volume=125.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )
    return WorkspaceReplaySession(
        events=(event,),
        source_name="CLOSE_GUARD_TEST",
        speed=1,
    )


def main() -> None:
    runtime = WorkspaceRuntime(_workspace())
    assert runtime.close_guard_result().allowed
    assert runtime.close_block_reason() is None

    runtime.context.runtime_state = WORKSPACE_STATE_RUNNING
    assert runtime.close_block_reason() == "runtime_state=RUNNING"

    runtime.context.runtime_state = WORKSPACE_STATE_STOPPED
    runtime.context.active_orders_count = 2
    assert runtime.close_block_reason() == "active_orders=2"

    runtime.context.active_orders_count = 0
    runtime.context.positions_count = 1
    assert runtime.close_block_reason() == "open_positions=1"

    runtime.context.positions_count = 0
    runtime.context.broker_operation_active = True
    assert runtime.close_block_reason() == "broker_operation_active"

    runtime.context.broker_operation_active = False
    runtime.context.event_processing = True
    assert runtime.close_block_reason() == "market_event_processing"

    runtime.context.event_processing = False
    runtime.replay_session = _replay_session()
    runtime.replay_session.in_step = True
    assert runtime.close_block_reason() == "replay_step_active"

    runtime.replay_session.in_step = False
    runtime.context.pending_close_decisions_count = 1
    assert runtime.close_block_reason() == "pending_close_decisions=1"

    runtime.context.runtime_state = WORKSPACE_STATE_RUNNING
    runtime.context.active_orders_count = 2
    runtime.context.positions_count = 1
    runtime.context.broker_operation_active = True
    runtime.context.event_processing = True
    runtime.replay_session.in_step = True
    combined = runtime.close_guard_result()
    blocker_codes = tuple(blocker.code for blocker in combined.blockers)
    assert blocker_codes == (
        WORKSPACE_CLOSE_BLOCK_RUNTIME_ACTIVE,
        WORKSPACE_CLOSE_BLOCK_ACTIVE_ORDERS,
        WORKSPACE_CLOSE_BLOCK_OPEN_POSITIONS,
        WORKSPACE_CLOSE_BLOCK_BROKER_OPERATION,
        WORKSPACE_CLOSE_BLOCK_MARKET_EVENT,
        WORKSPACE_CLOSE_BLOCK_REPLAY_STEP,
        WORKSPACE_CLOSE_BLOCK_PENDING_CLOSE,
    )
    assert combined.primary_reason == "runtime_state=RUNNING"

    with TemporaryDirectory() as temp_dir:
        controller = AlgorithmWorkspaceController(
            SessionRepository(Path(temp_dir))
        )
        workspace = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode="PAPER",
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        )
        managed_runtime = controller.ensure_workspace_runtime(
            workspace.workspace_uid
        )
        managed_runtime.context.active_orders_count = 1
        delete_blocked = False
        try:
            controller.delete_workspace(workspace.workspace_uid)
        except WorkspaceRuntimeError as exc:
            delete_blocked = "active_orders=1" in str(exc)
        assert delete_blocked
        assert len(controller.restore_workspaces()) == 1

        managed_runtime.context.active_orders_count = 0
        assert controller.delete_workspace(workspace.workspace_uid) is None
        assert not controller.restore_workspaces()

    print("Algorithm Workspace Close Guard result")
    print("  runtime_state_blocked=True")
    print("  active_orders_blocked=True")
    print("  open_positions_blocked=True")
    print("  broker_operation_blocked=True")
    print("  market_event_blocked=True")
    print("  replay_step_blocked=True")
    print("  pending_close_decision_blocked=True")
    print("  all_blockers_reported=True")
    print("  controller_delete_blocked=True")
    print("  delete_after_clear=True")
    print("ALGORITHM_WORKSPACE_CLOSE_GUARD_CHECK=OK")


if __name__ == "__main__":
    main()
