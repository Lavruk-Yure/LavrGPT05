# email_preview_window_logic.py
# -*- coding: utf-8 -*-
"""
email_preview_window_logic — попередній перегляд email перед SMTP.

Patch 29.2C:
- Кнопка "Редагувати" відкриває Notepad (контроль процесу).
- Якщо Notepad ще відкритий — "Надіслати" блокується.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QDialog, QMessageBox

from office.ui.ui_email_preview import Ui_EmailPreviewWindow

logger = logging.getLogger(__name__)


class EmailPreviewWindow(QDialog):
    def __init__(
        self,
        file_path: Path,
        parent=None,
        show_send_button: bool = True,
    ) -> None:
        super().__init__(parent)
        self.ui = Ui_EmailPreviewWindow()
        self.ui.setupUi(self)

        self.ui.btnSend.setVisible(show_send_button)

        self._file_path = Path(file_path)
        self._edit_proc: Optional[subprocess.Popen] = None

        self.ui.btnSend.clicked.connect(self._on_send_clicked)
        self.ui.btnCancel.clicked.connect(self.reject)
        self.ui.btnEdit.clicked.connect(self._edit_file)

        self._load_file()

    def _load_file(self) -> None:
        if not self._file_path.exists():
            QMessageBox.warning(
                self,
                "LGE Office",
                f"Файл не знайдено:\n{self._file_path}",
            )
            self.reject()
            return

        try:
            text = self._file_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.exception("Cannot read email file: %s", self._file_path)
            QMessageBox.warning(
                self,
                "LGE Office",
                f"Не можу прочитати файл:\n{self._file_path}\n\n{exc}",
            )
            self.reject()
            return

        self.ui.txtEmail.setPlainText(text)

    def _edit_file(self) -> None:
        # Відкриваємо саме Notepad, щоб можна було заблокувати "Надіслати",
        # поки редактор не закритий.
        try:
            self._edit_proc = subprocess.Popen(["notepad.exe", str(self._file_path)])
        except OSError as exc:
            QMessageBox.warning(
                self, "LGE Office", f"Не можу відкрити редактор:\n{exc}"
            )
            self._edit_proc = None

    def _on_send_clicked(self) -> None:
        # Якщо Notepad ще живий — забороняємо Send.
        if self._edit_proc is not None and self._edit_proc.poll() is None:
            QMessageBox.warning(
                self,
                "LGE Office",
                "Файл листа відкритий у редакторі.\n"
                "Закрийте редактор та натисніть “Надіслати” ще раз.",
            )
            return

        self.accept()
