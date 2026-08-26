"""Qt check for one-shot WSP external-exposure safety alerts."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    WORKSPACE_STATE_STOPPED,
)
from core.algorithm_workspace_area import AlgorithmWorkspaceArea  # noqa: E402
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_IDLE,
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE,
    WorkspaceRuntime,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402


class AlertTestArea(AlgorithmWorkspaceArea):
    def __init__(self, controller: AlgorithmWorkspaceController) -> None:
        self.alert_count = 0
        super().__init__(controller=controller)

    def _play_external_exposure_alert(self) -> None:
        self.alert_count += 1

    def sync_runtime_for_check(self, workspace_uid: str) -> None:
        self._sync_workspace_runtime(workspace_uid)


class FakeIbRuntimeService:
    @staticmethod
    def get_managed_accounts() -> list[str]:
        return ["DUM513747"]

    @staticmethod
    def get_account_state() -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id="DUM513747",
            broker_name="IB",
            currency="USD",
            balance=125000.50,
        )


def _set_hold(runtime: WorkspaceRuntime, *, active: bool, revision: int) -> None:
    context = runtime.context
    context.safety_hold_active = active
    context.safety_hold_revision = revision
    context.safety_hold_message = (
        "External IB FX exposure blocks exact account and symbol"
        if active
        else None
    )
    context.safety_hold_signed_volume = 1000.0 if active else 0.0
    context.safety_hold_evidence_status = "CONFIRMED" if active else None
    context.safety_hold_confirmation_required = False
    context.runtime_state = (
        WORKSPACE_STATE_STARTING if active else WORKSPACE_STATE_RUNNING
    )
    context.startup_phase = (
        WORKSPACE_STARTUP_PHASE_SAFETY_HOLD_EXTERNAL_EXPOSURE
        if active
        else WORKSPACE_STARTUP_PHASE_RUNNING
    )


def main() -> int:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository)
        area = AlertTestArea(controller=controller)
        area.set_runtime_engine(
            SimpleNamespace(
                ib_runtime_service=FakeIbRuntimeService(),
                ctrader_runtime_service=None,
            )
        )
        workspace = area.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="GBPUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
            parameters={
                "warmup_bars": 0,
                "spread_limit": 0.00020,
            },
        )
        runtime = controller.workspace_runtime(workspace.workspace_uid)
        if runtime is None:
            raise AssertionError("Workspace runtime was not created")

        notifications: list[tuple[str, str, str]] = []
        area.external_exposure_resolution_requested.connect(
            lambda display_name, account_id, symbol: notifications.append(
                (display_name, account_id, symbol)
            )
        )
        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count or notifications:
            raise AssertionError("Inactive hold emitted an alert")

        _set_hold(runtime, active=True, revision=1)
        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count != 1 or len(notifications) != 1:
            raise AssertionError("First safety hold did not alert exactly once")

        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count != 1 or len(notifications) != 1:
            raise AssertionError("Repeated sync duplicated the safety alert")

        runtime.context.safety_hold_revision = 2
        runtime.context.safety_hold_message = "Updated current IB evidence"
        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count != 1 or len(notifications) != 1:
            raise AssertionError("Safety hold update duplicated the alert")

        _set_hold(runtime, active=False, revision=3)
        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count != 1 or len(notifications) != 1:
            raise AssertionError("Safety hold clear emitted an alert")

        _set_hold(runtime, active=True, revision=4)
        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count != 2 or len(notifications) != 2:
            raise AssertionError("Cleared safety hold did not re-arm the alert")

        area.sync_runtime_for_check(workspace.workspace_uid)
        if area.alert_count != 2 or len(notifications) != 2:
            raise AssertionError("Second hold duplicated its one-shot alert")

        if notifications[0][1:] != ("DUM513747", "GBPUSD"):
            raise AssertionError("First recovery signal scope differs")
        if notifications[1][1:] != ("DUM513747", "GBPUSD"):
            raise AssertionError("Second recovery signal scope differs")

        runtime.context.safety_hold_active = False
        runtime.context.runtime_state = WORKSPACE_STATE_STOPPED
        runtime.context.startup_phase = WORKSPACE_STARTUP_PHASE_IDLE
        area.hide()
        area.deleteLater()
        app.processEvents()

    print("Algorithm Workspace external exposure alert result")
    print("  first_hold_beep_once=True")
    print("  repeated_sync_silent=True")
    print("  hold_update_silent=True")
    print("  clear_silent=True")
    print("  clear_rearms_alert=True")
    print("  popup_signal_once_per_hold=True")
    print("  exact_scope=DUM513747,GBPUSD")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_EXTERNAL_EXPOSURE_ALERT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
