"""Main-window external exposure popup post-OK refresh routing check."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMainWindow,
    QMessageBox,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.main_logic import MainAppWindow  # noqa: E402


class FakeRuntimeEngine:
    """Track broker activation without any broker execution."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.execution_attempts = 0

    def unlock_active_broker(self) -> None:
        self.events.append("unlock_active_broker")

    def set_active_broker(self, broker: str) -> None:
        self.events.append(f"set_active_broker:{broker}")


class FakeOrdersPage:
    """Track deferred setup and post-dialog refresh calls."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.prepare_calls: list[dict[str, object]] = []

    def prepare_external_exposure_resolution(
        self,
        *,
        account_id: str,
        symbol_name: str,
        refresh: bool = True,
    ) -> bool:
        self.prepare_calls.append(
            {
                "account_id": account_id,
                "symbol_name": symbol_name,
                "refresh": refresh,
            }
        )
        self.events.append(f"prepare_external:{refresh}")
        return True


class FakeLangManager:
    """Fallback-only translation source."""

    @staticmethod
    def tr(_key: str, fallback: str) -> str:
        return fallback


class MainWindowHarness(MainAppWindow):
    """Minimal initialized QMainWindow for the external recovery route."""

    def __init__(self) -> None:
        QMainWindow.__init__(self)
        self.events: list[str] = []
        self.runtime_engine: Any = FakeRuntimeEngine(self.events)
        self.page_orders: Any = FakeOrdersPage(self.events)
        self._lang_mgr: Any = FakeLangManager()

    def _switch_page(self, page_widget: QWidget) -> None:
        if page_widget is not self.page_orders:
            raise AssertionError("External exposure route selected wrong page")
        self.events.append("switch_orders")

    def request_external_exposure_resolution(
        self,
        workspace_display_name: str,
        account_id: str,
        symbol_name: str,
    ) -> None:
        self._on_external_exposure_resolution_requested(
            workspace_display_name,
            account_id,
            symbol_name,
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    harness = MainWindowHarness()
    warning_calls: list[tuple[str, str]] = []

    def capture_warning(_parent, title, text, *_args, **_kwargs):
        warning_calls.append((str(title), str(text)))
        harness.events.append("warning_closed")
        return QMessageBox.StandardButton.Ok

    try:
        with patch.object(QMessageBox, "warning", capture_warning):
            harness.request_external_exposure_resolution(
                "IB GBPUSD M15 — RailAlgorithm",
                "DUM513747",
                "GBPUSD",
            )

        expected_events = [
            "unlock_active_broker",
            "set_active_broker:IB",
            "switch_orders",
            "prepare_external:False",
            "warning_closed",
            "prepare_external:True",
        ]
        if harness.events != expected_events:
            raise AssertionError(
                "External exposure popup refresh order differs: " f"{harness.events!r}"
            )

        if len(warning_calls) != 1:
            raise AssertionError("External exposure warning was not shown exactly once")

        prepare_calls = harness.page_orders.prepare_calls
        refresh_calls = [call for call in prepare_calls if call["refresh"]]
        if len(refresh_calls) != 1:
            raise AssertionError("Post-popup refresh was not requested exactly once")

        deferred_calls = [call for call in prepare_calls if not call["refresh"]]
        if len(deferred_calls) != 1:
            raise AssertionError("Pre-popup setup was not deferred exactly once")

        runtime_engine: Any = harness.runtime_engine
        if runtime_engine.execution_attempts != 0:
            raise AssertionError("Popup refresh route attempted broker execution")

    finally:
        # The harness intentionally bypasses MainAppWindow.__init__().
        # Do not call close(), because that would enter the production
        # controlled-shutdown path with uninitialized application state.
        harness.hide()
        harness.deleteLater()
        app.processEvents()

    print("Main external exposure popup auto-refresh result")
    print("  popup_closed=True")
    print("  deferred_setup_before_popup=True")
    print("  refresh_called_once_after_popup=True")
    print("  broker_execution_attempted=False")
    print("MAIN_EXTERNAL_EXPOSURE_POPUP_AUTO_REFRESH_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
