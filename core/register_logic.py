# core/register_logic.py
"""
RegisterWindow — вікно реєстрації LGE05 (Patch 14.2, глобальний LANG)

Функції:
    • вибір мови інтерфейсу (оновлює LANG)
    • введення e-mail і паролів
    • валідація
    • шифрування AES та створення LGE05.conf
    • застосування перекладу через UITranslator

Особливості:
    • повна підтримка LANG — глобального менеджера мов
    • збереження lang_active у strings.json
    • валідація з перекладеними текстами
"""

from __future__ import annotations

import hashlib
from typing import Any

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QLineEdit,
    QMainWindow,
    QMessageBox,
)

from core.app_paths import ROOT_CONF_PATH
from core.config_manager import ConfigManager, make_machine_stub
from core.lang_manager import LANG  # <-- Глобальний менеджер
from core.ui_translator import UITranslator
from ui.ui_register import Ui_RegistrationWindow as UiRegister

APP_NAME = "LGE05"
PASSWORD_SPECIALS = r"!@#$%^&*()_+\-=\[\]{};':\",.<>/?\\|`~"

DEBUG_REGISTER = False


def log_cp(name: str, **kw: Any) -> None:
    if not DEBUG_REGISTER:
        return
    msg = f"[REGISTER_CP:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


# ======================================================================
# RegisterWindow
# ======================================================================
class RegisterWindow(QMainWindow):
    """Вікно реєстрації користувача LGE05."""

    def __init__(self) -> None:
        super().__init__()

        # --- UI ---
        self.ui = UiRegister()
        self.ui.setupUi(self)

        # --- Мова / переклад ---
        self._lang_mgr = LANG  # <-- Головне
        self._translator = UITranslator(self._lang_mgr)

        # --- Мови ---
        self._init_languages()

        # --- Сигнали ---
        self._connect_signals()

        # --- Початковий переклад ---
        self._apply_translations()

        # --- Обмеження ---
        self._current_max_len = 64
        self.ui.editPassword.setMaxLength(64)
        self.ui.editPasswordConfirm.setMaxLength(64)

        self.ui.lblError.setVisible(False)
        self.ui.btnRegister.setEnabled(False)

        self.ui.editEmail.textChanged.connect(self._validate_form)
        self.ui.editPassword.textChanged.connect(self._validate_form)
        self.ui.editPasswordConfirm.textChanged.connect(self._validate_form)

        self.ui.btnRegister.clicked.connect(self._do_register)
        self.ui.btnExit.clicked.connect(self.close)

        self._add_password_toggle(self.ui.editPassword)
        self._add_password_toggle(self.ui.editPasswordConfirm)

        log_cp("init_done", lang=self._lang_mgr.current_language)

    # ------------------------------------------------------------------
    def _t(self, key: str) -> str:
        return self._lang_mgr.resolve(key) or key

    # ------------------------------------------------------------------
    # Валідація
    # ------------------------------------------------------------------
    @staticmethod
    def _is_valid_email(text: str) -> bool:
        import re

        pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
        return re.match(pattern, text) is not None

    def _passwords_ok(self) -> tuple[bool, str]:
        p1 = self.ui.editPassword.text()
        p2 = self.ui.editPasswordConfirm.text()

        if len(p1) < 8:
            return False, self._t("RegistrationWindow.error.pw_short")
        if not any(c.islower() for c in p1):
            return False, self._t("RegistrationWindow.error.pw_lower")
        if not any(c.isupper() for c in p1):
            return False, self._t("RegistrationWindow.error.pw_upper")
        if not any(c.isdigit() for c in p1):
            return False, self._t("RegistrationWindow.error.pw_digit")
        if not any(c in PASSWORD_SPECIALS for c in p1):
            return False, self._t("RegistrationWindow.error.pw_special")
        if p1 != p2:
            return False, self._t("RegistrationWindow.error.pw_mismatch")

        return True, ""

    def _validate_form(self) -> None:
        email = self.ui.editEmail.text().strip()
        self._update_password_maxlen(email)

        if not self._is_valid_email(email):
            self._show_error(self._t("RegistrationWindow.error.email_invalid"))
            self.ui.btnRegister.setEnabled(False)
            return

        ok, msg = self._passwords_ok()
        if not ok:
            self._show_error(msg)
            self.ui.btnRegister.setEnabled(False)
            return

        self._show_error("")
        self.ui.btnRegister.setEnabled(True)

    def _show_error(self, msg: str) -> None:
        if msg:
            self.ui.lblError.setText(msg)
            self.ui.lblError.setVisible(True)
        else:
            self.ui.lblError.clear()
            self.ui.lblError.setVisible(False)

    # ------------------------------------------------------------------
    # Око
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
    # Збереження конфігу
    # ------------------------------------------------------------------
    def _do_register(self) -> None:
        email = self.ui.editEmail.text().strip()
        lang_code = self.ui.comboLanguage.currentData() or "uk"
        pwd = self.ui.editPassword.text()

        pwd_hash = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
        machine_stub = make_machine_stub()

        cfg_mgr = ConfigManager(ROOT_CONF_PATH)
        data = cfg_mgr.create_default(email, lang_code, pwd_hash, machine_stub)

        try:
            cfg_mgr.save(data, pwd)

            msg = (
                self._lang_mgr.resolve("RegistrationWindow.registerSuccess")
                or "Registration successful.\nThe file has been created:\n{path}"
            )
            msg = msg.replace("{path}", str(ROOT_CONF_PATH))

            title = (
                self._lang_mgr.resolve("RegistrationWindow.windowTitle")
                or f"{APP_NAME} — Registration"
            )

            QMessageBox.information(self, title, msg)
            self.close()

        except Exception as ex:
            QMessageBox.critical(
                self,
                f"{APP_NAME} — Error",
                f"Failed to create config:\n{ex!r}",
            )

    # ------------------------------------------------------------------
    def _update_password_maxlen(self, email: str) -> None:
        target = max(8, min(len(email), 64))
        if target != self._current_max_len:
            self._current_max_len = target
            self.ui.editPassword.setMaxLength(target)
            self.ui.editPasswordConfirm.setMaxLength(target)

    # ------------------------------------------------------------------
    # Мови
    # ------------------------------------------------------------------
    def _init_languages(self) -> None:
        combo = self.ui.comboLanguage
        combo.blockSignals(True)
        combo.clear()

        for code, name in self._lang_mgr.languages.items():
            icon = self._lang_mgr.get_flag_icon(code)
            combo.addItem(icon, name, userData=code)

        current_code = self._lang_mgr.current_language
        index = combo.findData(current_code)
        combo.setCurrentIndex(index if index >= 0 else 0)

        combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._on_language_changed)

    def _on_language_changed(self, index: int) -> None:
        combo = self.ui.comboLanguage
        code = combo.itemData(index)
        if not code:
            return

        self._lang_mgr.set_current_language(code)
        self._apply_translations()

    def _apply_translations(self) -> None:
        self._translator.apply(self)

    def _connect_signals(self) -> None:
        pass
