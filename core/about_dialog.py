# about_dialog.py
"""
core/about_dialog.py — діалог "Про програму".

- UI містить ключі перекладу у форматі: [AboutDialog.*]
- Переклад застосовує UITranslator (НЕ .qm).
- Runtime-дані (OS/Python/Mode) показуємо у QTextBrowser (копіюється Ctrl+C).
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import Optional

from PySide6.QtWidgets import QDialog

import __init__ as app_meta
from core.lang_manager import LANG
from core.ui_translator import UITranslator
from ui.ui_about_dialog import Ui_AboutDialog

logger = logging.getLogger(__name__)

DEBUG_ABOUT = False


def log_cp(name: str, **kw: object) -> None:
    """Локальний debug-логер AboutDialog."""
    if not DEBUG_ABOUT:
        return
    logger.debug(
        "AboutDialog: %s | %s",
        name,
        ", ".join(f"{k}={v!r}" for k, v in kw.items()),
    )


class AboutDialog(QDialog):
    """Діалог 'Про програму'."""

    def __init__(self, parent: Optional[object] = None) -> None:
        super().__init__(parent)

        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)

        # 1) Прибрати ключі виду "[AboutDialog.*]" (включно з windowTitle)
        UITranslator(LANG).apply(self)

        # 2) OK закриває діалог
        self.ui.btnOk.clicked.connect(self.accept)

        # 3) Runtime-інформація
        self._fill_runtime_info()

        log_cp("init_done", window_title=self.windowTitle())

    def _fill_runtime_info(self) -> None:
        """Заповнює runtime поля, не ламаючи переклад у lblOs/lblComment."""
        os_line = f"{platform.system()} {platform.release()} ({platform.version()})"
        py_line = platform.python_version()

        # Заголовок всередині діалогу — продукт/версія (не перекладаємо)
        product = getattr(app_meta, "__product_name__", "LGE05 — ATS")
        version = getattr(app_meta, "__version__", "0.0.0")
        self.ui.lblTitle.setText(f"{product} v{version}")

        author = getattr(app_meta, "__author__", "")
        email = getattr(app_meta, "__email__", "")
        assistant = getattr(app_meta, "__assistant__", "")
        year = getattr(app_meta, "__year__", "")

        # Режим
        mode_label = LANG.resolve("AboutDialog.mode") or "Mode"
        mode_value = (
            "PyInstaller (frozen)" if getattr(sys, "frozen", False) else "dev (sources)"
        )
        mode_line = f"{mode_label}: {mode_value}"

        lines = [
            author,
            email,
            f"{assistant}, {year}".strip(", "),
            f"OS: {os_line}",
            f"Python: {py_line}",
            mode_line,
        ]
        text = "\n".join([x for x in lines if isinstance(x, str) and x.strip()])

        # QTextBrowser: копіювання Ctrl+C працює
        self.ui.textInfo.setPlainText(text)
