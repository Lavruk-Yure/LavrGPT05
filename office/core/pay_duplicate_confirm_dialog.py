# pay_duplicate_confirm_dialog.py
"""
PayDuplicateConfirmDialog — підтвердження створення дубльованого платежу.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QDialog

from office.ui.ui_payment_duplicate_confirm_dialog import (
    Ui_PayDuplicateConfirmDialog,
)

logger = logging.getLogger(__name__)


class PayDuplicateConfirmDialog(QDialog):
    """Діалог підтвердження дублю платежу."""

    def __init__(self, duplicate: dict, parent=None) -> None:
        super().__init__(parent)

        self.ui = Ui_PayDuplicateConfirmDialog()
        self.ui.setupUi(self)

        self._duplicate = duplicate

        self._setup_ui()
        self._bind()

    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Заповнення тексту деталей."""

        if not self._duplicate:
            self.ui.plainDetails.setPlainText("Дані дубля відсутні.")
            return

        details = (
            f"ID: {self._duplicate.get('id')}\n"
            f"Bank: {self._duplicate.get('provider')}\n"
            f"External Ref: {self._duplicate.get('external_ref')}\n"
            f"Amount: {self._duplicate.get('amount')} "
            f"{self._duplicate.get('currency')}\n"
        )

        note = self._duplicate.get("note")
        if note:
            details += f"Note: {note}\n"

        self.ui.plainDetails.setPlainText(details)

    # ------------------------------------------------------------------

    def _bind(self) -> None:
        """Підключення кнопок."""

        self.ui.btnAddAnyway.clicked.connect(self.accept)
        self.ui.btnCancel.clicked.connect(self.reject)
