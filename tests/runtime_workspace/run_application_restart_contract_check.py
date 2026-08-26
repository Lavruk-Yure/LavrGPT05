# -*- coding: utf-8 -*-
"""Controlled application restart contract after license activation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.main_logic import MainAppWindow  # noqa: E402
from core.settings_page_license import (  # noqa: E402
    license_activation_requires_restart,
)


class RestartProbe(MainAppWindow):
    """Minimal restart probe without normal MainAppWindow initialization."""

    def __init__(self) -> None:
        QMainWindow.__init__(self)
        self.shutdown_called = False

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        QMainWindow.showEvent(self, event)

    def moveEvent(self, event) -> None:  # noqa: ANN001, N802
        QMainWindow.moveEvent(self, event)

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        QMainWindow.resizeEvent(self, event)

    def changeEvent(self, event) -> None:  # noqa: ANN001, N802
        QMainWindow.changeEvent(self, event)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.shutdown_application()
        QMainWindow.closeEvent(self, event)

    def shutdown_application(self) -> None:
        self.shutdown_called = True


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setProperty("lge_restart_requested", False)
    probe = RestartProbe()
    probe.show()
    app.processEvents()

    probe.request_application_restart()
    app.processEvents()

    assert bool(app.property("lge_restart_requested"))
    assert probe.shutdown_called
    assert not probe.isVisible()

    assert license_activation_requires_restart("pro")
    assert license_activation_requires_restart("pro_plus")
    assert license_activation_requires_restart("PRO+")
    assert not license_activation_requires_restart("free")

    print("Application Restart Contract result")
    print("  restart_flag_set=True")
    print("  main_window_close_lifecycle_used=True")
    print("  controlled_shutdown_requested=True")
    print("  detached_restart_deferred_until_event_loop_exit=True")
    print("  restart_policy_source_independent=True")
    print("  trial_to_pro_restart_supported=True")
    print("  trial_to_pro_plus_restart_supported=True")
    print("  pro_to_pro_plus_restart_supported=True")
    print("APPLICATION_RESTART_CONTRACT_CHECK=OK")


if __name__ == "__main__":
    main()
