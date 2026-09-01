# -*- coding: utf-8 -*-
"""Runtime check for exact WSP order and position ownership filtering."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402


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
    )
    other_workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )

    order_rows = [
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "ib",
            "account_id": "dum513747",
            "symbol": "eurusd",
            "order_id": "ORDER-1",
            "broker_order_id": "501",
            "side": "buy",
            "order_type": "limit",
            "volume": 1000,
            "price": 1.1380,
            "stop_loss": 1.1350,
            "take_profit": 1.1440,
            "status": "working",
            "created_at": "2026-07-24T08:00:00Z",
            "profit": 0.0,
        },
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "order_id": "ORDER-2",
            "broker_order_id": "502",
            "side": "SELL",
            "order_type": "MARKET",
            "volume": 1000,
            "price": 1.1400,
            "status": "FILLED",
            "created_at": "2026-07-24T08:15:00Z",
            "profit": 12.5,
        },
        {
            "workspace_uid": other_workspace.workspace_uid,
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "order_id": "OTHER-WSP-ORDER",
            "side": "BUY",
            "order_type": "MARKET",
            "volume": 2000,
            "status": "WORKING",
        },
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "GBPUSD",
            "order_id": "WRONG-SYMBOL",
            "side": "BUY",
            "order_type": "MARKET",
            "volume": 1000,
            "status": "WORKING",
        },
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "CTRADER",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "order_id": "WRONG-BROKER",
            "side": "BUY",
            "order_type": "MARKET",
            "volume": 1000,
            "status": "WORKING",
        },
        {
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "order_id": "LEGACY-NO-WSP",
            "side": "BUY",
            "order_type": "MARKET",
            "volume": 1000,
            "status": "WORKING",
        },
    ]
    position_rows = [
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "position_id": "POSITION-1",
            "broker_position_id": "IB:DUM513747:EURUSD:LEG-1",
            "side": "BUY",
            "volume": 1000,
            "entry_price": 1.1380,
            "current_price": 1.1389,
            "current_profit": 69.0,
            "peak_profit": 100.0,
            "stop_loss": 1.1350,
            "take_profit": 1.1440,
            "opened_at": "2026-07-24T08:00:00Z",
            "reconciliation_status": "RECONCILED",
        },
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "position_id": "POSITION-CLOSED",
            "side": "SELL",
            "volume": 0,
            "current_profit": 10.0,
            "peak_profit": 10.0,
            "reconciliation_status": "CLOSED",
        },
        {
            "workspace_uid": other_workspace.workspace_uid,
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "position_id": "OTHER-WSP-POSITION",
            "side": "BUY",
            "volume": 2000,
            "current_profit": 25.0,
            "peak_profit": 40.0,
            "reconciliation_status": "RECONCILED",
        },
        {
            "workspace_uid": workspace.workspace_uid,
            "broker": "IB",
            "account_id": "OTHER",
            "symbol": "EURUSD",
            "position_id": "WRONG-ACCOUNT",
            "side": "BUY",
            "volume": 1000,
            "current_profit": 5.0,
            "peak_profit": 8.0,
            "reconciliation_status": "RECONCILED",
        },
        {
            "broker": "IB",
            "account_id": "DUM513747",
            "symbol": "EURUSD",
            "position_id": "LEGACY-NO-WSP",
            "side": "BUY",
            "volume": 1000,
            "current_profit": 5.0,
            "peak_profit": 8.0,
            "reconciliation_status": "RECONCILED",
        },
    ]

    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir))
        repository.save_workspace(workspace)
        repository.save_workspace(other_workspace)
        controller = AlgorithmWorkspaceController(repository)

        owned = controller.set_workspace_owned_snapshots(
            workspace.workspace_uid,
            order_rows=order_rows,
            position_rows=position_rows,
        )
        runtime = controller.workspace_runtime(workspace.workspace_uid)
        assert runtime is not None
        assert [order.order_id for order in owned.orders] == [
            "ORDER-1",
            "ORDER-2",
        ]
        assert [position.position_id for position in owned.positions] == [
            "POSITION-1",
            "POSITION-CLOSED",
        ]
        assert len(owned.active_orders) == 1
        assert len(owned.active_positions) == 1
        assert owned.rejected_orders == 4
        assert owned.rejected_positions == 3
        assert runtime.context.active_orders_count == 1
        assert runtime.context.positions_count == 1
        assert runtime.context.current_profit == 69.0
        assert runtime.context.peak_profit == 100.0
        assert runtime.context.profit_drawdown == 31.0
        assert runtime.close_block_reason() == "active_orders=1"

        other_owned = controller.set_workspace_owned_snapshots(
            other_workspace.workspace_uid,
            order_rows=order_rows,
            position_rows=position_rows,
        )
        assert [order.order_id for order in other_owned.orders] == ["OTHER-WSP-ORDER"]
        assert [position.position_id for position in other_owned.positions] == [
            "OTHER-WSP-POSITION"
        ]

        cleared = controller.set_workspace_owned_snapshots(
            workspace.workspace_uid,
            order_rows=[],
            position_rows=[],
        )
        assert not cleared.orders
        assert not cleared.positions
        assert runtime.close_block_reason() is None
        journal_events = [entry.event for entry in runtime.journal]
        assert journal_events.count("SNAPSHOT_APPLIED") == 2

    print("Algorithm Workspace Order Filter result")
    print(f"  workspace_uid={workspace.workspace_uid}")
    print("  exact_orders=2")
    print("  exact_positions=2")
    print("  active_orders=1")
    print("  active_positions=1")
    print("  cross_workspace_blocked=True")
    print("  wrong_binding_blocked=True")
    print("  legacy_without_workspace_uid_blocked=True")
    print("  profit_drawdown=31.0%")
    print("ALGORITHM_WORKSPACE_ORDER_FILTER_CHECK=OK")


if __name__ == "__main__":
    main()
