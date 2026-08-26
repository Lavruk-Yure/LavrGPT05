"""Synthetic check для RoadMap92 AlgorithmWorkspace + SessionRepository."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from core.algorithm_workspace import (
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_DATA_MODE_BROKER,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_STOPPED,
    AlgorithmWorkspace,
    AlgorithmWorkspaceError,
)
from core.algorithm_workspace_controller import (
    AlgorithmWorkspaceController,
    WorkspaceLayoutLockedError,
)
from core.session_repository import SessionRepository


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "Session"
        repository = SessionRepository(session_dir)
        controller = AlgorithmWorkspaceController(repository)

        workspace = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            parameters={"rail_min_points": 12},
            risk_settings={"risk_percent": 0.5},
            ui_state={"panel_parameters": True},
        )

        UUID(workspace.workspace_uid)
        assert workspace.runtime_state == WORKSPACE_STATE_STOPPED
        assert workspace.display_name == "IB EURUSD M15 — RailAlgorithm"
        assert workspace.data_mode == WORKSPACE_DATA_MODE_BROKER
        assert workspace.account_mode == WORKSPACE_ACCOUNT_MODE_PAPER

        workspace_path = repository.workspace_path(workspace.workspace_uid)
        assert workspace_path.exists()
        assert repository.session_path.exists()

        stored_payload = json.loads(workspace_path.read_text(encoding="utf-8"))
        assert stored_payload["workspace_uid"] == workspace.workspace_uid
        assert stored_payload["schema_version"] == 5
        assert stored_payload["data_mode"] == WORKSPACE_DATA_MODE_BROKER
        assert stored_payload["account_mode"] == WORKSPACE_ACCOUNT_MODE_PAPER
        assert "runtime_state" not in stored_payload
        assert set(stored_payload["indicator_profile_bindings"]) == {
            "MACD",
            "ALLIGATOR",
        }
        assert "broker_order_id" not in stored_payload
        assert "position_id" not in stored_payload
        assert "pnl" not in stored_payload

        legacy_workspace = AlgorithmWorkspace.from_storage_dict(
            {
                **stored_payload,
                "schema_version": 2,
                "data_mode": "PAPER",
                "account_mode": None,
            }
        )
        assert legacy_workspace.data_mode == WORKSPACE_DATA_MODE_BROKER
        assert legacy_workspace.account_mode == WORKSPACE_ACCOUNT_MODE_PAPER

        renamed = controller.rename_workspace(
            workspace.workspace_uid,
            "EURUSD Rails M15",
        )
        assert renamed.display_name == "EURUSD Rails M15"

        restored = controller.restore_workspaces()
        assert len(restored) == 1
        assert restored[0].runtime_state == WORKSPACE_STATE_RESTORED
        assert restored[0].display_name == "EURUSD Rails M15"

        controller.mark_workspace_started_once(workspace.workspace_uid)
        try:
            controller.rename_workspace(workspace.workspace_uid, "New Name")
        except AlgorithmWorkspaceError:
            rename_after_start_blocked = True
        else:
            rename_after_start_blocked = False
        assert rename_after_start_blocked

        controller.set_layout_locked(True)
        assert controller.is_layout_locked()

        try:
            controller.create_workspace(
                broker="CTRADER",
                account_id="123456",
                account_mode="DEMO",
                symbol="GBPUSD",
                timeframe="H1",
                algorithm="SMAAlgorithm",
            )
        except WorkspaceLayoutLockedError:
            create_while_locked_blocked = True
        else:
            create_while_locked_blocked = False
        assert create_while_locked_blocked

        repository.save_main_window_state(
            {
                "geometry": {
                    "x": 120,
                    "y": 80,
                    "width": 1280,
                    "height": 900,
                },
                "window_state": "MAXIMIZED",
            }
        )

        manifest = repository.load_manifest()
        assert manifest["schema_version"] == 2
        assert manifest["layout_locked"] is True
        assert manifest["active_workspace_uid"] == workspace.workspace_uid
        assert manifest["workspace_order"] == [workspace.workspace_uid]
        assert manifest["main_window"]["window_state"] == "MAXIMIZED"
        assert manifest["main_window"]["geometry"]["width"] == 1280

        legacy_session_dir = Path(temp_dir) / "LegacySession"
        legacy_repository = SessionRepository(legacy_session_dir)
        legacy_repository.ensure_storage()
        legacy_repository.session_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "layout_locked": False,
                    "active_workspace_uid": None,
                    "workspace_order": [],
                }
            ),
            encoding="utf-8",
        )
        legacy_manifest = legacy_repository.load_manifest()
        assert legacy_manifest["schema_version"] == 2
        assert legacy_manifest["main_window"]["geometry"] is None
        assert legacy_manifest["main_window"]["window_state"] == "NORMAL"

        print("Algorithm Workspace Session result")
        print(f"  workspace_uid={workspace.workspace_uid}")
        print(f"  display_name={renamed.display_name}")
        print(f"  data_mode={workspace.data_mode}")
        print(f"  account_mode={workspace.account_mode}")
        print(f"  legacy_data_mode={legacy_workspace.data_mode}")
        print(f"  restored_state={restored[0].runtime_state}")
        print(f"  rename_after_start_blocked={rename_after_start_blocked}")
        print(f"  layout_locked={manifest['layout_locked']}")
        print(f"  main_window_state={manifest['main_window']['window_state']}")
        print(f"  legacy_session_schema={legacy_manifest['schema_version']}")
        print(f"  create_while_locked_blocked={create_while_locked_blocked}")
        print("ALGORITHM_WORKSPACE_SESSION_CHECK=OK")


if __name__ == "__main__":
    main()
