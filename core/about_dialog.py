# about_dialog.py
"""
core/about_dialog.py — діалог "Про програму".

- Підтягує метадані з __init__.py
- Працює з локалізацією через ключі в UI: [AboutDialog.*]
"""

from __future__ import annotations

import logging
import platform
from typing import Optional

# from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog

import __init__ as app_meta  # корінь пакета
from ui.ui_about_dialog import Ui_AboutDialog

logger = logging.getLogger(__name__)


class AboutDialog(QDialog):
    """Діалог 'Про програму'."""

    def __init__(self, parent: Optional[object] = None) -> None:
        super().__init__(parent)
        logger.debug("AboutDialog init")

        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)

        # OK закриває діалог
        self.ui.buttonBox.accepted.connect(self.accept)

        # Іконка в діалозі (беремо з вікна/апки, якщо є)
        try:
            icon = self.windowIcon()
            if not icon.isNull():
                self.ui.lblIcon.setPixmap(icon.pixmap(64, 64))
        except Exception as exc:  # noqa: BLE001
            logger.debug("AboutDialog icon set failed: %s", exc)

        self._fill_runtime_info()

    def _fill_runtime_info(self) -> None:
        """Заповнює поля з метаданих + runtime."""
        os_line = f"{platform.system()} {platform.release()} ({platform.version()})"
        py_line = platform.python_version()

        title = f"{app_meta.__product_name__} v{app_meta.__version__}"
        info = (
            f"{app_meta.__author__}\n"
            f"{app_meta.__email__}\n"
            f"{app_meta.__assistant__}, {app_meta.__year__}\n"
            f"OS: {os_line}\n"
            f"Python: {py_line}"
        )

        tested = " / ".join(app_meta.__tested_os__)
        comment = app_meta.__comment__

        # Тут ми НЕ “перекладаємо” рядки кодом.
        # Переклад робить твій lang_manager через ключі в UI.
        # Але ці runtime-рядки показуємо як контент у QLabel.
        self.ui.lblTitle.setText(title)
        self.ui.lblInfo.setText(info)
        self.ui.lblOs.setText(tested)
        self.ui.lblComment.setText(comment)
