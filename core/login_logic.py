"""
LoginWindow — вікно входу LGE05 (Patch 14.1)

Функції:
    - AES-дешифровка LGE05.conf
    - перевірка password_sha256
    - перевірка machine_stub
    - ліміти спроб
    - відкриття MainAppWindow після успіху
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QMainWindow,
)

from core import session_state
from core.app_paths import ROOT_CONF_PATH
from core.config_manager import (
    USER_PASSWORD,
    ConfigCollection,
    ConfigManager,
    make_machine_stub,
)
from core.lang_manager import LANG  # <-- глобальний
from core.main_logic import MainAppWindow  # <-- окремий модуль
from core.ui_translator import UITranslator
from ui.ui_login import Ui_LoginWindow

AES_BUFFER = 64 * 1024  # 64 KiB

DEBUG_LOGIN = False


def log_cp(name: str, **kw: Any) -> None:
    if not DEBUG_LOGIN:
        return
    msg = f"[LOGIN_CP:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


# ======================================================================
# LoginWindow
# ======================================================================
class LoginWindow(QMainWindow):
    """Вікно входу LGE05."""

    def __init__(self) -> None:
        super().__init__()

        # --- UI ---
        self.ui = Ui_LoginWindow()
        self.ui.setupUi(self)

        # --- Lang / Translator ---
        self._lang_mgr = LANG  # <-- тепер глобальний
        self._ui_translator = UITranslator(self._lang_mgr)
        self._ui_translator.apply(self)

        log_cp("init_translator_applied", lang=self._lang_mgr.current_language)

        # --- Attempts ---
        self._login_attempts = 0
        self._max_attempts = 3

        # --- Buttons / Focus ---
        self.ui.lineEdit.setFocus()
        self.ui.btnLogin.clicked.connect(self._do_login)
        self.ui.btnExit.clicked.connect(self._exit_app)
        self._add_password_toggle(self.ui.lineEdit)

        self._main_window: MainAppWindow | None = None

        self.result: str | None = None

    # ------------------------------------------------------------------
    def _exit_app(self) -> None:
        log_cp("exit_clicked")
        self.close()

    # ------------------------------------------------------------------
    def _add_password_toggle(self, edit: QLineEdit) -> None:  # noqa
        act = QAction(edit)
        act.setCheckable(True)
        act.setIcon(QIcon(":/icons/eye_closed.svg"))

        def toggle() -> None:
            if act.isChecked():
                edit.setEchoMode(QLineEdit.EchoMode.Normal)
                act.setIcon(QIcon(":/icons/eye_open.svg"))
            else:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                act.setIcon(QIcon(":/icons/eye_closed.svg"))

        act.triggered.connect(toggle)
        edit.addAction(act, QLineEdit.ActionPosition.TrailingPosition)

    # ------------------------------------------------------------------
    def _set_error_and_lock(self, message: str) -> None:
        self.ui.lblError.setText(message)
        self.ui.btnLogin.setEnabled(False)
        self.ui.lineEdit.setEnabled(False)

    # ------------------------------------------------------------------
    def _do_login(self) -> None:
        pwd = self.ui.lineEdit.text().strip()
        log_cp("do_login_called", pwd_len=len(pwd))

        # --- 1. Too many attempts ---
        if self._login_attempts >= self._max_attempts:
            msg = (
                self._lang_mgr.resolve("LoginWindow.errorTooMany")
                or "Too many invalid attempts. Access denied."
            )
            self.ui.lblError.setText(msg)
            QApplication.instance().quit()
            return

        # --- 2. Load config ---
        cfg_mgr = ConfigManager(ROOT_CONF_PATH)
        raw_data, status = cfg_mgr.load_with_status(pwd)
        ok = status == "ok"
        log_cp("config_loaded", ok=ok, status=status)

        # --- 2.1 Corrupted config (do NOT count as wrong password) ---
        if status in ("corrupted", "json_error"):
            self.result = "bad_conf"
            self.close()
            return

        # --- 3. Wrong password ---
        if not ok:
            self._login_attempts += 1
            left = self._max_attempts - self._login_attempts

            msg = self._lang_mgr.resolve("LoginWindow.errorInvalidPassword")
            if msg:
                msg = msg.replace("{left}", str(left))
            else:
                msg = f"Invalid password. Attempts left: {left}"

            self.ui.lblError.setText(msg)

            if left <= 0:
                msg2 = (
                    self._lang_mgr.resolve("LoginWindow.errorTooMany")
                    or "Too many invalid attempts. Access denied."
                )
                self._set_error_and_lock(msg2)

            return

        # --- 4. Check machine stub ---
        current_machine = make_machine_stub()
        stored_machine = raw_data.get("machine", {})

        for key in ("username", "platform", "node", "mac"):
            if str(stored_machine.get(key)) != str(current_machine.get(key)):
                msg = (
                    self._lang_mgr.resolve("LoginWindow.errorMachineMismatch")
                    or "This LGE05.conf was created on another device.\nAccess denied."
                )
                self._set_error_and_lock(msg)
                return

        # --- 5. Login OK ---
        session_state.CURRENT_CONFIG = ConfigCollection(raw_data)
        session_state.CURRENT_PASSWORD = pwd
        USER_PASSWORD.value = pwd

        self.ui.lblError.setText("")
        self._open_main_window()

    # ------------------------------------------------------------------
    def _open_main_window(self) -> None:
        self._main_window = MainAppWindow()
        self._main_window.show()
        self.close()

    # ------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._do_login()
        else:
            super().keyPressEvent(event)
