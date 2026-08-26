# login_window_logic.py
# -*- coding: utf-8 -*-
"""
login_window_logic — логіка входу в LGEOffice (3 спроби).

Patch 28.x:
- Кнопка показу/приховування пароля (QPushButton, checkable).
- Безпечна робота: якщо кнопки немає в UI — просто ігноруємо.
- accept() тільки після успішної перевірки пароля та відкриття/створення ключів.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QLineEdit, QMessageBox

from office.core import session_state
from office.core.key_manager import ensure_ed25519_keys
from office.core.office_config import read_config
from office.core.office_paths import get_config_path
from office.core.security import verify_password
from office.ui.ui_login_office import Ui_LoginOfficeWindow

# Реєструємо Qt resources (:/office/...)


logger = logging.getLogger(__name__)


class LoginWindow(QDialog):
    MAX_TRIES = 3

    ICON_EYE_OPEN = ":/office/icons/eye_open.svg"
    ICON_EYE_CLOSED = ":/office/icons/eye_closed.svg"

    def __init__(self) -> None:
        super().__init__()
        self.ui = Ui_LoginOfficeWindow()
        self.ui.setupUi(self)

        self._tries_left = self.MAX_TRIES

        self._init_ui()
        self._wire_ui()

        logger.debug("LoginWindow initialized")

    def _init_ui(self) -> None:
        self.ui.lblStatus.setText("")
        self.ui.edtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        # На випадок якщо Designer виставив щось дивне
        if hasattr(self.ui, "btnLogin"):
            self.ui.btnLogin.setCheckable(False)
        if hasattr(self.ui, "btnExit"):
            self.ui.btnExit.setCheckable(False)

        # Кнопка "око" (QPushButton), якщо вона є у UI
        if hasattr(self.ui, "btnTogglePassword"):
            btn = self.ui.btnTogglePassword
            btn.setCheckable(True)
            btn.setChecked(False)
            btn.setText("")
            btn.setToolTip("Показати/сховати пароль")

            # Фіксуємо розмір (якщо не зробив у Designer)
            btn.setMinimumSize(26, 26)
            btn.setMaximumSize(26, 26)

            # Іконка за замовчуванням — "закрите око"
            btn.setIcon(QIcon(self.ICON_EYE_CLOSED))

            self._apply_toggle_visual(is_visible=False)

    def _wire_ui(self) -> None:
        self.ui.btnLogin.clicked.connect(self._on_login)
        self.ui.btnExit.clicked.connect(self.reject)

        # Enter у полі пароля = "Увійти"
        self.ui.edtPassword.returnPressed.connect(self._on_login)

        # Перемикач видимості пароля
        if hasattr(self.ui, "btnTogglePassword"):
            self.ui.btnTogglePassword.toggled.connect(self._on_toggle_password)

    def _set_status(self, text: str, ok: bool) -> None:
        self.ui.lblStatus.setText(text)
        color = "#1a7f37" if ok else "#b42318"
        self.ui.lblStatus.setStyleSheet(f"color: {color};")

    def _on_toggle_password(self, checked: bool) -> None:
        # checked=True => показати пароль
        is_visible = bool(checked)

        self.ui.edtPassword.setEchoMode(
            QLineEdit.EchoMode.Normal if is_visible else QLineEdit.EchoMode.Password
        )

        if hasattr(self.ui, "btnTogglePassword"):
            icon_path = self.ICON_EYE_OPEN if is_visible else self.ICON_EYE_CLOSED
            self.ui.btnTogglePassword.setIcon(QIcon(icon_path))
            self._apply_toggle_visual(is_visible=is_visible)

        self.ui.edtPassword.setFocus()

    def _apply_toggle_visual(self, *, is_visible: bool) -> None:
        """
        Легка підсвітка кнопки при 'показано пароль'.
        Без фанатизму: тільки фон, щоб око візуально "перемикалось".
        """
        if not hasattr(self.ui, "btnTogglePassword"):
            return

        btn = self.ui.btnTogglePassword
        if is_visible:
            btn.setStyleSheet(
                "QPushButton { background-color: #eef6ff; "
                "border: 1px solid #c7ddff; border-radius: 4px; }"
                "QPushButton:hover { background-color: #e3f0ff; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background-color: transparent; "
                "border: 1px solid transparent; border-radius: 4px; }"
                "QPushButton:hover { background-color: #f2f2f2; "
                "border: 1px solid #e0e0e0; }"
            )

    def _on_login(self) -> None:
        pwd = (self.ui.edtPassword.text() or "").strip()
        if not pwd:
            self._set_status("Введіть пароль.", ok=False)
            return

        cfg = read_config(get_config_path())
        auth = cfg.get("auth", {})
        salt = auth.get("password_salt")
        pwd_hash = auth.get("password_hash")

        if not salt or not pwd_hash:
            QMessageBox.critical(self, "LGE Office", "Пошкоджена конфігурація.")
            self.reject()
            return

        if verify_password(pwd, salt, pwd_hash):
            session_state.ADMIN_PASSWORD = pwd

            try:
                ensure_ed25519_keys(
                    admin_password=session_state.ADMIN_PASSWORD,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Keys open/generate failed")
                session_state.ADMIN_PASSWORD = None
                QMessageBox.warning(self, "LGE Office", f"Ключі не відкрились: {exc}")
                self.reject()  # не пускаємо
                return

            self.accept()  # пускаємо тільки коли все ОК
            return

        self._tries_left -= 1
        if self._tries_left <= 0:
            QMessageBox.critical(
                self,
                "LGE Office",
                "Перевищено кількість спроб. Програму буде закрито.",
            )
            self.reject()
            return

        self._set_status(
            f"Невірний пароль. Залишилось спроб: {self._tries_left}.",
            ok=False,
        )
