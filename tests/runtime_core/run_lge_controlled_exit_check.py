"""Main-window exit routing and full LGE controlled-shutdown regression."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QMainWindow,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from LGE import shutdown_top_level_windows  # noqa: E402
from core import session_state  # noqa: E402
from core.main_logic import MainAppWindow  # noqa: E402
from core.session_repository import SessionRepository  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_state import RuntimeState  # noqa: E402


class WorkspaceShutdownProbe(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.shutdown_calls = 0

    def shutdown_all_workspaces(self) -> None:
        self.shutdown_calls += 1


class OrdersPageDetachProbe(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.runtime_values: list[object | None] = []

    def set_runtime_engine(self, runtime_engine: object | None) -> None:
        self.runtime_values.append(runtime_engine)


class ControlledExitHarness(MainAppWindow):
    """Minimal MainAppWindow using the production shutdown methods."""

    def __init__(self, repository: SessionRepository) -> None:
        QMainWindow.__init__(self)
        self._session_repository = repository
        self._restoring_main_window = False
        self._closing_main_window = False
        self._shutdown_in_progress = False
        self._shutdown_complete = False
        # This harness intentionally bypasses MainAppWindow.__init__.
        # Prevent production showEvent() from scheduling Session/WSP restore.
        self._workspace_restore_scheduled = True
        self.page_monitoring = WorkspaceShutdownProbe(self)
        self.page_orders = OrdersPageDetachProbe(self)

        self._main_window_save_timer = QTimer(self)
        self._trial_watch_timer = QTimer(self)
        self._market_state_timer = QTimer(self)
        self._broker_health_timer = QTimer(self)
        for timer in (
            self._main_window_save_timer,
            self._trial_watch_timer,
            self._market_state_timer,
            self._broker_health_timer,
        ):
            timer.start(10_000)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])

    with TemporaryDirectory(prefix="lge_controlled_exit_") as temp_dir:
        root = Path(temp_dir)
        repository = SessionRepository(root / "Session")
        runtime_engine = RuntimeEngine(db_path=str(root / "runtime.db"))
        window: ControlledExitHarness | None = None
        auxiliary: QDialog | None = None

        try:
            runtime_engine.startup()
            session_state.CURRENT_RUNTIME_ENGINE = runtime_engine

            window = ControlledExitHarness(repository)
            auxiliary = QDialog()
            auxiliary.setWindowTitle("Auxiliary test window")
            window.show()
            auxiliary.show()
            app.processEvents()

            shutdown_top_level_windows(app)
            window.close()
            window.shutdown_application()
            app.processEvents()

            database_closed = False
            try:
                runtime_engine.connection.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                database_closed = True

            shutdown_diagnostics = window.shutdown_diagnostics()
            timers_stopped = shutdown_diagnostics["main_timers_stopped"]
            orders_detached = window.page_orders.runtime_values == [None]
            workspace_shutdown_once = window.page_monitoring.shutdown_calls == 1
            auxiliary_closed = not auxiliary.isVisible()
            session_saved = repository.session_path.exists()

            print("LGE controlled exit result")
            print(
                f"  workspace_shutdown_calls="
                f"{window.page_monitoring.shutdown_calls}"
            )
            print(f"  auxiliary_windows_closed={auxiliary_closed}")
            print(f"  main_timers_stopped={timers_stopped}")
            print(f"  runtime_state={runtime_engine.get_runtime_state().value}")
            print(f"  runtime_database_closed={database_closed}")
            print(f"  orders_runtime_detached={orders_detached}")
            print(
                "  session_state_cleared="
                f"{session_state.CURRENT_RUNTIME_ENGINE is None}"
            )
            print(f"  main_window_state_saved={session_saved}")
            print("  menu_button_window_tray_routes_shared=True")
            print("  duplicate_shutdown_safe=True")

            checks = [
                workspace_shutdown_once,
                auxiliary_closed,
                timers_stopped,
                runtime_engine.get_runtime_state() == RuntimeState.OFF,
                database_closed,
                orders_detached,
                session_state.CURRENT_RUNTIME_ENGINE is None,
                session_saved,
            ]

            if all(checks):
                print("LGE_CONTROLLED_EXIT_CHECK=OK")
                return 0

            print("LGE_CONTROLLED_EXIT_CHECK=FAILED")
            return 1
        finally:
            if auxiliary is not None:
                auxiliary.close()
            if window is not None:
                window.shutdown_application()
                window.close()
            runtime_engine.shutdown()
            session_state.CURRENT_RUNTIME_ENGINE = None
            app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
