"""Controlled full-shutdown regression for all Algorithm Workspaces."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

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
    WORKSPACE_STATE_STOPPED,
    WORKSPACE_STATE_STOPPING,
)
from core.algorithm_workspace_area import AlgorithmWorkspaceArea  # noqa: E402
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])

    with TemporaryDirectory(prefix="lge_wsp_shutdown_") as temp_dir:
        repository = SessionRepository(Path(temp_dir) / "Session")
        controller = AlgorithmWorkspaceController(repository=repository)
        area = AlgorithmWorkspaceArea(controller=controller)
        area.show()

        first = area.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        )
        second = area.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="GBPUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        )
        app.processEvents()

        first_runtime = controller.workspace_runtime(first.workspace_uid)
        second_runtime = controller.workspace_runtime(second.workspace_uid)
        assert first_runtime is not None
        assert second_runtime is not None
        first_runtime.context.runtime_state = WORKSPACE_STATE_RUNNING
        second_runtime.context.runtime_state = WORKSPACE_STATE_STOPPING

        first_subwindow = area.workspace_subwindow(first.workspace_uid)
        second_subwindow = area.workspace_subwindow(second.workspace_uid)
        assert first_subwindow is not None
        assert second_subwindow is not None

        area.shutdown_all_workspaces()
        area.shutdown_all_workspaces()
        app.processEvents()

        first_stopped = first_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        second_stopped = second_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        windows_closed = (
            not first_subwindow.isVisible() and not second_subwindow.isVisible()
        )
        shutdown_diagnostics = area.shutdown_diagnostics()
        timers_stopped = shutdown_diagnostics["timers_stopped"]
        runtime_engine_detached = shutdown_diagnostics["runtime_engine_detached"]

        print("Algorithm workspace controlled shutdown result")
        print(f"  workspaces=2")
        print(f"  first_runtime_stopped={first_stopped}")
        print(f"  second_runtime_stopped={second_stopped}")
        print(f"  mdi_windows_closed={windows_closed}")
        print(f"  timers_stopped={timers_stopped}")
        print(f"  runtime_engine_detached={runtime_engine_detached}")
        print("  duplicate_shutdown_safe=True")

        checks = [
            first_stopped,
            second_stopped,
            windows_closed,
            timers_stopped,
            runtime_engine_detached,
        ]
        area.close()

        if all(checks):
            print("ALGORITHM_WORKSPACE_CONTROLLED_SHUTDOWN_CHECK=OK")
            return 0

        print("ALGORITHM_WORKSPACE_CONTROLLED_SHUTDOWN_CHECK=FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
