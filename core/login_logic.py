# login_logic.py
# -*- coding: utf-8 -*-
"""
LoginLogic — логіка вікна входу (тільки пароль).

Patch 24.12:
- 3 спроби пароля:
  • 1–2: тільки lblError (без діалогу)
  • 3: lblError + CommonErrorDialog
- wrong_password_or_corrupted: стабільний статус (pyAesCrypt не гарантує типи винятків)
- bad_conf: result="bad_conf" + close (LGE.py показує повідомлення і робить .bad)
- LicenseManager.compute_and_update якщо впав -> bad_conf
- Enter працює (returnPressed)
- DEBUG_LOGIN керує traceback у консоль
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QMainWindow

from core import session_state
from core.app_meta import (
    APP_NAME,
    TRIAL_DAYS,
    TRIAL_WARN_BEFORE_EXPIRY_DAYS,
    VERSION,
)
from core.app_paths import ROOT_CONF_PATH
from core.common_dialogs import CommonErrorDialog
from core.config_manager import (
    USER_PASSWORD,
    ConfigCollection,
    ConfigManager,
    make_machine_stub,
)
from core.lang_manager import LangManager
from core.license_manager import LicenseManager
from core.main_logic import MainAppWindow
from core.ui_translator import UITranslator
from ui.ui_login import Ui_LoginWindow

logger = logging.getLogger(__name__)

DEBUG_LOGIN = False  # True -> traceback у консоль


class LoginWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.ui = Ui_LoginWindow()
        self.ui.setupUi(self)

        # password edit
        self._edit_password: Optional[QLineEdit] = getattr(
            self.ui, "editPassword", None
        ) or getattr(self.ui, "lineEdit", None)

        if not isinstance(self._edit_password, QLineEdit):
            raise RuntimeError("Login UI: password QLineEdit not found")

        self._edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        # X (clear)
        self._edit_password.setClearButtonEnabled(True)

        # eye icons from resources (must exist in .qrc)
        icon_eye_open = QIcon(":/icons/eye_open.svg")
        icon_eye_closed = QIcon(":/icons/eye_closed.svg")

        eye_action = QAction(self)
        eye_action.setCheckable(True)
        eye_action.setChecked(False)
        eye_action.setIcon(icon_eye_closed)

        def _toggle_password_visible(checked: bool) -> None:
            self._edit_password.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
            eye_action.setIcon(icon_eye_open if checked else icon_eye_closed)

        eye_action.toggled.connect(_toggle_password_visible)

        self._edit_password.addAction(
            eye_action,
            QLineEdit.ActionPosition.TrailingPosition,
        )

        # language manager
        self._lang_mgr = LangManager()

        # UI translation
        self._translator = UITranslator(self._lang_mgr)
        self._translator.apply(self)

        # attempts policy
        self._failed_attempts = 0
        self._max_attempts = 3

        # lblError
        self._lbl_error: Optional[QLabel] = getattr(self.ui, "lblError", None)
        if isinstance(self._lbl_error, QLabel):
            self._lbl_error.setText("")
            self._lbl_error.setVisible(False)
        else:
            self._lbl_error = None

        # Enter -> login
        self._edit_password.returnPressed.connect(self._on_login_clicked)
        self.ui.btnLogin.setDefault(True)
        self.ui.btnLogin.setAutoDefault(True)

        self.ui.btnLogin.clicked.connect(self._on_login_clicked)
        self.ui.btnExit.clicked.connect(self.close)

    def _set_error(self, text_key_or_text: str) -> None:
        if self._lbl_error is None:
            return
        msg = self._lang_mgr.resolve(text_key_or_text)
        if msg == text_key_or_text:
            msg = text_key_or_text
        self._lbl_error.setText(msg)
        self._lbl_error.setVisible(True)

    def _clear_error(self) -> None:
        if self._lbl_error is None:
            return
        self._lbl_error.setText("")
        self._lbl_error.setVisible(False)

    def _bump_attempts_and_maybe_dialog(self, details_key: str) -> bool:
        """
        Returns True if handled (and should return from caller).
        1–2: lblError only
        3: lblError + dialog, then reset attempts
        """
        self._failed_attempts += 1

        if self._failed_attempts < self._max_attempts:
            self._set_error(details_key)
            self._edit_password.selectAll()
            self._edit_password.setFocus()
            return True

        # 3rd attempt -> dialog
        self._failed_attempts = 0
        self._set_error(details_key)
        CommonErrorDialog.show_dialog(
            parent=self,
            lang_mgr=self._lang_mgr,
            title="CommonErrorDialog.windowTitle",
            header="CommonErrorDialog.lblHeader",
            details=details_key,
        )
        self._edit_password.selectAll()
        self._edit_password.setFocus()
        return True

    def _on_login_clicked(self) -> None:
        password = (self._edit_password.text() or "").strip()
        if not password:
            return

        self._clear_error()

        try:
            cfg_mgr = ConfigManager(ROOT_CONF_PATH)

            # --- first run ---
            if not ROOT_CONF_PATH.exists():
                now_iso = datetime.now(UTC).isoformat()

                conf = {
                    "app": APP_NAME,
                    "version": VERSION,
                    "email": "",
                    "language": "en",
                    "password_sha256": USER_PASSWORD.hash(password),
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "multi_language": False,
                    "translator": {
                        "provider": "off",
                        "deepl_key_1": "",
                        "deepl_key_2": "",
                    },
                    "machine": make_machine_stub(),
                    "license": {
                        "edition": "free",
                        "status": "NO_LICENSE",
                        "machine_id": None,
                        "payload_b64": None,
                        "signature_b64": None,
                        "activated_at": None,
                        "issued_at": None,
                        "expires_at": None,
                        "version_min": None,
                        "last_check_at": None,
                        "last_run_at": None,
                        "source": None,
                        "note": None,
                        "trial_policy": {
                            "trial_days": TRIAL_DAYS,
                            "warn_before_expiry_days": TRIAL_WARN_BEFORE_EXPIRY_DAYS,
                        },
                    },
                }
                cfg_mgr.save(conf, password)

            # --- load ---
            data, status = cfg_mgr.load_with_status(password)

            # Wrong password (clear)
            if status == "wrong_password":
                if self._bump_attempts_and_maybe_dialog(
                    "LoginWindow.errorWrongPassword"
                ):
                    return

            # Wrong password or corrupted (merged)
            if status == "wrong_password_or_corrupted":
                if self._bump_attempts_and_maybe_dialog(
                    "LoginWindow.errorWrongPasswordOrCorrupted"
                ):
                    return

            # Bad conf / other errors -> let LGE.py handle .bad and messaging
            if status != "ok" or not isinstance(data, dict):
                self.result = "bad_conf"
                self.close()
                return

            # success: reset attempts
            self._failed_attempts = 0
            self._clear_error()

            conf = ConfigCollection(data)

            session_state.CURRENT_CONFIG = conf
            session_state.CURRENT_PASSWORD = password

            # Не ліземо в ConfigCollection.get(...), бо сигнатура/обгортка у нього інша.
            # Беремо версію напряму з app_meta як канонічне джерело.
            app_version = VERSION

            # If compute/update fails -> treat as bad conf
            try:
                LicenseManager.compute_and_update(
                    conf.to_dict(),
                    now=datetime.now(UTC),
                    app_version=app_version,
                )
            except Exception:  # noqa
                self.result = "bad_conf"
                self.close()
                return

            self._open_main()

        except Exception as e:
            if DEBUG_LOGIN:
                logger.exception("Login failed")

            CommonErrorDialog.show_dialog(
                parent=self,
                lang_mgr=self._lang_mgr,
                title="CommonErrorDialog.windowTitle",
                header="CommonErrorDialog.lblHeader",
                details=str(e) if DEBUG_LOGIN else "LoginWindow.errorUnknown",
            )

    def _open_main(self) -> None:
        self.hide()
        self._main = MainAppWindow()
        self._main.show()
        self.close()


def run_login() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    w = LoginWindow()
    w.setWindowModality(Qt.WindowModality.ApplicationModal)
    w.show()

    app.exec()
