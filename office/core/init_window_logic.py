# init_window_logic.py
# -*- coding: utf-8 -*-
"""
init_window_logic — логіка вікна ініціалізації LGEOffice.

UI: office/ui/init_office.ui -> office/ui/ui_init_office.py

Patch 29.4:
1) Перший запуск: ініціалізація з новим паролем
   (папки + office_config.json + keys + db).
2) Recovery DB: якщо немає БД — відновлюємо без пароля (пароль не змінюємо).
3) Recovery keys: якщо відсутні ключі — вимагаємо поточний пароль і відновлюємо keys.
4) initialized=true ставимо тільки після повної перевірки (config + db + keys).

UI чекбокси:
- chkDirs
- chkConfig
- chkKeys
- chkReady
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QLineEdit, QMessageBox

from office.core.db import init_db, is_db_ready, is_db_write_locked
from office.core.init_actions import initialize_office
from office.core.init_state import check_initialized
from office.core.key_manager import ensure_ed25519_keys
from office.core.office_config import OfficeConfig, read_config, write_config
from office.core.office_paths import (
    get_config_path,
    get_office_dir,
    get_private_key_path,
    get_public_key_path,
)
from office.core.security import validate_password, verify_password
from office.ui.ui_init_office import Ui_InitOfficeWindow

logger = logging.getLogger(__name__)


class InitWindow(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.ui = Ui_InitOfficeWindow()
        self.ui.setupUi(self)

        # Recovery mode: config є, але система не повністю готова (db/keys)
        self._recovery_mode = False
        self._recovery_require_password = False
        self._recovery_keys_missing = False

        self.ui.edtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        for chk in (
            self.ui.chkDirs,
            self.ui.chkConfig,
            self.ui.chkKeys,
            self.ui.chkReady,
        ):
            chk.setEnabled(False)
            chk.setChecked(False)

        self.ui.lblPwStatus.setText("")
        self.ui.lblPwStatus.setWordWrap(True)

        self.ui.edtPassword.textChanged.connect(self._on_password_changed)
        self.ui.btnInit.clicked.connect(self._on_init_clicked)
        self.ui.btnExit.clicked.connect(self.reject)
        self.ui.btnContinue.setEnabled(False)
        self.ui.btnContinue.clicked.connect(self.accept)

        self._apply_existing_state()
        self._update_init_button()

        # Перевірка lock office.db раз на 500 мс, щоб кнопка “Ініціалізація”
        # автоматично активувалась після закриття DBeaver/SQLite Browser.
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(500)
        self._lock_timer.timeout.connect(self._update_init_button)
        self._lock_timer.start()

    def _apply_existing_state(self) -> None:
        """
        Визначаємо стан:
        - dirs існують?
        - config існує?
        - db ready?
        - keys ready?
        І тільки якщо все ок -> "вже ініціалізовано".
        """
        office_dir = get_office_dir()
        cfg_path = get_config_path()

        dirs_ok = all((office_dir / x).exists() for x in ("keys", "licenses", "logs"))
        cfg_exists = cfg_path.exists()
        db_ok = is_db_ready(office_dir)

        priv_key = get_private_key_path()
        pub_key = get_public_key_path()
        keys_ok = priv_key.exists() and pub_key.exists()

        # UI state
        self.ui.chkDirs.setChecked(dirs_ok)
        self.ui.chkConfig.setChecked(cfg_exists)
        self.ui.chkKeys.setChecked(keys_ok)
        self.ui.chkReady.setChecked(dirs_ok and cfg_exists and db_ok and keys_ok)

        # Нема config -> це перший запуск. Потрібен новий пароль.
        if not cfg_exists:
            self._recovery_mode = False
            self._recovery_require_password = False
            self._recovery_keys_missing = False

            self.ui.edtPassword.setEnabled(True)
            self.ui.lblPassword.setEnabled(True)
            self.ui.edtPassword.setPlaceholderText("Введіть пароль...")
            self._set_pw_status("", True)
            return

        state = check_initialized(cfg_path)

        if state.initialized:
            # Все повністю готово
            self._recovery_mode = False
            self._recovery_require_password = False
            self._recovery_keys_missing = False

            self.ui.edtPassword.setText("")
            self.ui.edtPassword.setEnabled(False)
            self.ui.lblPassword.setEnabled(False)
            self.ui.edtPassword.setPlaceholderText("")

            self.ui.btnInit.setEnabled(False)
            self._set_pw_status("Система повністю ініціалізована.", True)
            return

        # config є, але система НЕ ініціалізована.
        # Розрізняємо:
        # - немає БД -> відновлюємо без пароля
        # - немає keys -> потрібен поточний пароль
        self._recovery_mode = True
        self._recovery_keys_missing = not keys_ok
        self._recovery_require_password = self._recovery_keys_missing

        if self._recovery_require_password:
            self.ui.edtPassword.setEnabled(True)
            self.ui.lblPassword.setEnabled(True)
            self.ui.edtPassword.setPlaceholderText(
                "Введіть поточний пароль для відновлення ключів"
            )
        else:
            self.ui.edtPassword.setText("")
            self.ui.edtPassword.setEnabled(False)
            self.ui.lblPassword.setEnabled(False)
            self.ui.edtPassword.setPlaceholderText("")

        self._set_pw_status(f"Не ініціалізовано: {state.reason}", False)

    def _get_password(self) -> str:
        return (self.ui.edtPassword.text() or "").strip()

    def _set_pw_status(self, text: str, ok: bool) -> None:
        self.ui.lblPwStatus.setText(text)
        color = "#1a7f37" if ok else "#b42318"
        self.ui.lblPwStatus.setStyleSheet(f"color: {color};")

    def _update_init_button(self) -> None:

        office_dir = get_office_dir()
        db_path = office_dir / "office.db"
        if is_db_write_locked(db_path):
            self._set_pw_status(
                "office.db зайнята (закрий DBeaver/SQLite Browser) і "
                "натисни «Ініціалізація» ще раз.",
                False,
            )
            self.ui.btnInit.setEnabled(False)
            return

        # Recovery режим
        if self._recovery_mode:
            if not self._recovery_require_password:
                self.ui.btnInit.setEnabled(True)
                return

            pwd = self._get_password()
            if not pwd:
                self._set_pw_status(
                    "Потрібен поточний пароль для відновлення ключів.", False
                )
                self.ui.btnInit.setEnabled(False)
                return

            cfg_path = get_config_path()
            data = read_config(cfg_path)
            auth = data.get("auth", {})
            salt = str(auth.get("password_salt", ""))
            expected_hash = str(auth.get("password_hash", ""))

            if not salt or not expected_hash:
                self._set_pw_status("Немає даних auth у office_config.json.", False)
                self.ui.btnInit.setEnabled(False)
                return

            ok = verify_password(pwd, salt, expected_hash)
            self._set_pw_status(
                "Пароль підтверджено." if ok else "Невірний пароль.", ok
            )
            self.ui.btnInit.setEnabled(ok)
            return

        # Перший запуск: потрібен НОВИЙ пароль (валідація правил)
        pwd = self._get_password()
        if not pwd:
            self._set_pw_status("", True)
            self.ui.btnInit.setEnabled(False)
            return

        chk = validate_password(pwd)
        self._set_pw_status(chk.message if not chk.ok else "Пароль підходить.", chk.ok)
        self.ui.btnInit.setEnabled(chk.ok)

    def _on_password_changed(self) -> None:
        self._update_init_button()

    def _on_init_clicked(self) -> None:
        office_dir = get_office_dir()
        cfg_path = get_config_path()

        # 0) Локальні хелпери для оновлення UI
        def _refresh_checks() -> None:
            dirs_ok = all(
                (office_dir / x).exists() for x in ("keys", "licenses", "logs")
            )
            cfg_ok = cfg_path.exists()
            db_ok = is_db_ready(office_dir)
            priv_ok = get_private_key_path().exists()
            pub_ok = get_public_key_path().exists()
            keys_ok = priv_ok and pub_ok

            self.ui.chkDirs.setChecked(dirs_ok)
            self.ui.chkConfig.setChecked(cfg_ok)
            self.ui.chkKeys.setChecked(keys_ok)
            self.ui.chkReady.setChecked(dirs_ok and cfg_ok and db_ok and keys_ok)

        # 1) Перший запуск: створити config + keys (пароль новий)
        if not self._recovery_mode:
            pwd = self._get_password()
            chk = validate_password(pwd)
            if not chk.ok:
                QMessageBox.warning(self, "LGE Office", chk.message)
                self._update_init_button()
                return

            # initialize_office: папки + config (initialized=false) + keys
            initialize_office(pwd)

            _refresh_checks()

        # 2) Створюємо/відновлюємо БД завжди

        db_path = office_dir / "office.db"
        if is_db_write_locked(db_path):
            QMessageBox.warning(
                self,
                "LGE Office",
                "Файл office.db зараз відкритий (зайнятий іншим процесом).\n\n"
                "Закрий DBeaver / SQLite Browser / інші копії LGEOffice\n"
                "і натисни «Ініціалізація» ще раз.",
            )
            return

        try:
            init_db(office_dir)
        except PermissionError as e:
            _refresh_checks()
            QMessageBox.warning(
                self,
                "LGE Office",
                "Не можу оновити базу даних.\n\n"
                "Файл office.db зайнятий іншим процесом.\n"
                "Закрий DBeaver / SQLite Browser / інші копії LGEOffice\n"
                "і натисни «Ініціалізація» ще раз.\n\n"
                f"Деталі: {e}",
            )
            self._update_init_button()
            return
        except Exception as e:
            _refresh_checks()
            QMessageBox.critical(
                self,
                "LGE Office",
                f"Помилка ініціалізації БД:\n\n{e}",
            )
            self._update_init_button()
            return

        if not is_db_ready(office_dir):
            _refresh_checks()
            QMessageBox.critical(
                self,
                "LGE Office",
                "БД не ініціалізована або schema_version не співпадає.",
            )
            self._update_init_button()
            return

        _refresh_checks()

        # 3) Якщо recovery і немає keys — відновлюємо keys (потрібен поточний пароль)
        if self._recovery_mode and self._recovery_keys_missing:
            pwd = self._get_password()
            if not pwd:
                QMessageBox.warning(
                    self,
                    "LGE Office",
                    "Введіть поточний пароль для відновлення ключів.",
                )
                return

            data = read_config(cfg_path)
            auth = data.get("auth", {})
            salt = str(auth.get("password_salt", ""))
            expected_hash = str(auth.get("password_hash", ""))

            if not verify_password(pwd, salt, expected_hash):
                QMessageBox.warning(
                    self, "LGE Office", "Невірний пароль адміністратора."
                )
                return

            ensure_ed25519_keys(admin_password=pwd)

            _refresh_checks()

        # 4) Фінальна перевірка готовності (db + keys)
        state = check_initialized(cfg_path)
        if not state.initialized:
            _refresh_checks()
            QMessageBox.critical(
                self, "LGE Office", f"Ініціалізація не завершена:\n{state.reason}"
            )
            return

        # 5) Ставимо initialized=true (пароль/хеш не чіпаємо)
        data = read_config(cfg_path)
        auth = data.get("auth", {})

        cfg = OfficeConfig(
            initialized=True,
            password_salt=str(auth.get("password_salt", "")),
            password_hash=str(auth.get("password_hash", "")),
        )
        write_config(cfg_path, cfg)

        _refresh_checks()

        # 6) Закриваємо вікно успішно
        self._finish_ok_ui()
        return

    def _finish_ok_ui(self) -> None:
        self.ui.chkDirs.setChecked(True)
        self.ui.chkConfig.setChecked(True)
        self.ui.chkKeys.setChecked(True)
        self.ui.chkReady.setChecked(True)

        self.ui.edtPassword.setText("")
        self.ui.edtPassword.setEnabled(False)
        self.ui.lblPassword.setEnabled(False)

        self.ui.btnInit.setEnabled(False)
        self.ui.btnContinue.setEnabled(True)

        self._set_pw_status(
            "Ініціалізація завершена. Натисніть «Продовжити» або «Вихід».", True
        )
