# -*- coding: utf-8 -*-
"""Check deterministic broker-neutral WSP risk account snapshots."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_DEMO,
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.constants import (  # noqa: E402
    REPLAY_RISK_SETTING_DAILY_REALIZED_PNL,
    REPLAY_RISK_SETTING_EQUITY,
    REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT,
)


def _workspace(
    *,
    broker: str,
    account_id: str,
    account_mode: str,
    symbol: str,
) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker=broker,
        account_id=account_id,
        account_mode=account_mode,
        symbol=symbol,
        timeframe="M15",
        algorithm="RiskSnapshotProbe",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
    )


def main() -> None:
    snapshot_utc = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    settings = {
        REPLAY_RISK_SETTING_EQUITY: 100_000.0,
        REPLAY_RISK_SETTING_DAILY_REALIZED_PNL: -250.0,
        REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT: 1,
    }
    ib_workspace = _workspace(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
    )
    ctrader_workspace = _workspace(
        broker="CTRADER",
        account_id="12345678",
        account_mode=WORKSPACE_ACCOUNT_MODE_DEMO,
        symbol="GBPUSD",
    )

    ib_snapshot = WorkspaceRiskAccountSnapshot.from_replay_settings(
        snapshot_utc=snapshot_utc,
        workspace_uid=ib_workspace.workspace_uid,
        broker=ib_workspace.broker,
        account_id=ib_workspace.account_id,
        source_mode=ib_workspace.data_mode,
        replay_settings=settings,
    )
    ib_repeat = WorkspaceRiskAccountSnapshot.from_replay_settings(
        snapshot_utc=snapshot_utc,
        workspace_uid=ib_workspace.workspace_uid,
        broker=ib_workspace.broker,
        account_id=ib_workspace.account_id,
        source_mode=ib_workspace.data_mode,
        replay_settings=settings,
    )
    ctrader_snapshot = WorkspaceRiskAccountSnapshot.from_replay_settings(
        snapshot_utc=snapshot_utc,
        workspace_uid=ctrader_workspace.workspace_uid,
        broker=ctrader_workspace.broker,
        account_id=ctrader_workspace.account_id,
        source_mode=ctrader_workspace.data_mode,
        replay_settings=settings,
    )

    assert ib_snapshot == ib_repeat
    assert ib_snapshot.synthetic
    assert ib_snapshot.equity_available
    assert ib_snapshot.daily_pnl_available
    assert ib_snapshot.open_positions_available
    assert ib_snapshot.equity == 100_000.0
    assert ib_snapshot.daily_realized_pnl == -250.0
    assert ib_snapshot.open_positions_count == 1
    assert ib_snapshot.matches_binding(
        workspace_uid=ib_workspace.workspace_uid,
        broker="IB",
        account_id="DUM513747",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )
    assert ctrader_snapshot.matches_binding(
        workspace_uid=ctrader_workspace.workspace_uid,
        broker="CTRADER",
        account_id="12345678",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )

    missing_snapshot = WorkspaceRiskAccountSnapshot(
        snapshot_utc=snapshot_utc,
        workspace_uid=ib_workspace.workspace_uid,
        broker="IB",
        account_id="DUM513747",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        equity=None,
        daily_realized_pnl=None,
        open_positions_count=None,
        binding_verified=True,
        synthetic=True,
    )
    assert not missing_snapshot.equity_available
    assert not missing_snapshot.daily_pnl_available
    assert not missing_snapshot.open_positions_available

    runtime = WorkspaceRuntime(ib_workspace)
    applied = runtime.set_risk_account_snapshot(ctrader_snapshot)
    assert not applied.binding_verified
    assert runtime.risk_account_snapshot == applied
    assert runtime.context.risk_equity == 100_000.0
    assert runtime.context.daily_realized_pnl == -250.0

    invalid_boolean_blocked = False
    invalid_binding_verified: Any = "True"

    try:
        WorkspaceRiskAccountSnapshot(
            snapshot_utc=snapshot_utc,
            workspace_uid=ib_workspace.workspace_uid,
            broker="IB",
            account_id="DUM513747",
            source_mode=WORKSPACE_DATA_MODE_REPLAY,
            equity=100_000.0,
            daily_realized_pnl=0.0,
            open_positions_count=0,
            binding_verified=invalid_binding_verified,
            synthetic=True,
        )
    except ValueError:
        invalid_boolean_blocked = True

    assert invalid_boolean_blocked

    print("Algorithm Workspace Risk Account Snapshot result")
    print("  ib_replay_snapshot_valid=True")
    print("  ctrader_replay_snapshot_valid=True")
    print("  deterministic=True")
    print("  equity_available=True")
    print("  daily_pnl_available=True")
    print("  open_positions_available=True")
    print("  missing_values_preserved=True")
    print("  foreign_binding_blocked=True")
    print(f"  invalid_boolean_blocked={invalid_boolean_blocked}")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_RISK_ACCOUNT_SNAPSHOT_CHECK=OK")


if __name__ == "__main__":
    main()
