# main_window_logic.py
# -*- coding: utf-8 -*-
"""
main_window_logic — головне вікно LGEOffice (мінімальний каркас).
"""

from __future__ import annotations

import logging
import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QMainWindow, QMessageBox

from office.core.db_grid_window_logic import DbGridWindow
from office.core.db_report_service import export_db_report
from office.core.init_window_logic import InitWindow
from office.core.office_paths import get_db_path
from office.core.payment_add_window_logic import PaymentAddWindow
from office.core.quick_issue_dialog import QuickIssueDialog
from office.ui.ui_main_office import Ui_MainOfficeWindow

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.ui = Ui_MainOfficeWindow()
        self.ui.setupUi(self)
        self.setWindowIcon(QIcon(":/icons/LGEOffice.ico"))

        # Ліве меню
        self.ui.btnExit.clicked.connect(self.close)
        self.ui.btnInit.clicked.connect(self._open_init)

        self.ui.btnPayments.clicked.connect(self._open_payments)
        self.ui.btnDbGrid.clicked.connect(self._open_db_grid)
        self.ui.btnDbReport.clicked.connect(self._on_db_report)
        self.ui.btnQuickIssue.clicked.connect(self._open_quick_issue)

        # Верхнє меню
        self.ui.actExit.triggered.connect(self.close)
        self.ui.actInit.triggered.connect(self._open_init)

        self.ui.actPayments.triggered.connect(self._open_payments)
        self.ui.actDbGrid.triggered.connect(self._open_db_grid)
        self.ui.actDbReport.triggered.connect(self._on_db_report)
        self.ui.actQuickIssue.triggered.connect(self._open_quick_issue)

    def _open_init(self) -> None:  # noqa
        w = InitWindow()
        result = w.exec()

        if result == QDialog.DialogCode.Accepted:
            return

    def _open_payments(self) -> None:  # noqa
        """Відкрити діалог Введення невизначеної оплати."""
        logger.debug("Opening PaymentAddWindow.")
        w = PaymentAddWindow(self)
        w.exec()

    def _open_quick_issue(self) -> None:
        """Відкрити діалог швидкої видачі ліцензії."""
        logger.debug("Opening QuickIssueDialog.")
        dlg = QuickIssueDialog(self)
        dlg.exec()

    def _open_db_grid(self) -> None:  # noqa
        try:
            db_path = str(get_db_path())
            w = DbGridWindow(db_path=db_path, parent=self)
            w.exec()

            self.showNormal()
            self.raise_()
            self.activateWindow()
        except Exception as e:  # noqa: BLE001
            logger.exception("Open DbGrid failed")
            QMessageBox.critical(self, "LGE Office", f"Редактор не відкрився:\n{e}")

    def _on_db_report(self) -> None:
        """Сформувати TXT-звіт по БД."""
        try:
            report_path = export_db_report(get_db_path())
        except Exception as exc:
            logger.exception("DB report export failed: %s", exc)
            QMessageBox.warning(
                self,
                "LGE Office",
                f"Не вдалося сформувати звіт по БД.\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "LGE Office",
            f"Файл /reports/{report_path.name} сформований.",
        )

        try:
            os.startfile(report_path)
        except Exception as exc:
            logger.exception("Cannot open DB report: %s", exc)
            QMessageBox.warning(
                self,
                "LGE Office",
                f"Файл сформований, але не вдалося відкрити його автоматично.\n\n{exc}",
            )
