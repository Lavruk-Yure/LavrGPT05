# settings_page_license.py
# -*- coding: utf-8 -*-
"""
SettingsPageLicense — сторінка ліцензії (RoadMap19 / Patch 19.4)

UI: ui/license_page.ui -> ui/ui_settings_page_license.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from core import session_state
from core.app_meta import TRIAL_DAYS, VERSION
from core.app_paths import BASE_DIR, ROOT_CONF_PATH
from core.config_manager import ConfigCollection, ConfigManager
from core.license_manager import LicenseManager
from core.license_request_dialog import LicenseRequestDialog
from ui.ui_settings_page_license import Ui_pageLicense

_STATUS_I18N = {
    "TRIAL_OK": "SettingsPageLicense.statusTrialOk",
    "TRIAL_EXPIRED": "SettingsPageLicense.statusTrialExpired",
    "PRO_OK": "SettingsPageLicense.statusProOk",
    "UPDATE_REQUIRED": "SettingsPageLicense.statusUpdateRequired",
    "EXPIRED": "SettingsPageLicense.statusExpired",
    "OTHER_MACHINE": "SettingsPageLicense.statusOtherMachine",
    "TAMPERED": "SettingsPageLicense.statusTampered",
}

DEBUG_LICENSE_PAGE = False

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


_COMMERCIAL_ACTIVATION_EDITIONS = frozenset({"pro", "pro_plus"})


def license_activation_requires_restart(activated_edition: object) -> bool:
    """Return whether a successful activation must restart LGE."""
    edition = str(activated_edition or "").strip().lower()
    if edition == "pro+":
        edition = "pro_plus"
    return edition in _COMMERCIAL_ACTIVATION_EDITIONS


def log_lp(name: str, **kw: Any) -> None:
    if not DEBUG_LICENSE_PAGE:
        return
    msg = f"[LICENSE_PAGE:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


class SettingsPageLicense(QWidget):
    def __init__(
        self,
        parent: QWidget | None,
        lang_mgr,  # noqa: ANN001
        on_license_changed=None,  # noqa: ANN001
        on_license_restart_requested=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._lang_mgr = lang_mgr
        self._on_license_changed = on_license_changed
        self._on_license_restart_requested = on_license_restart_requested

        self.ui = Ui_pageLicense()
        self.ui.setupUi(self)
        self._setup_license_key_editor()

        # UI повідомлення
        self.ui.lblActivationInfo.setWordWrap(True)
        self.ui.lblActivationInfo.setStyleSheet("color: lightgray;")
        self._set_info("", kind="info")
        self._set_info_neutral_if_needed()

        self.ui.btnActivate.clicked.connect(self._on_activate)
        self.ui.btnCopyDiag.clicked.connect(self._on_copy_diag)
        self.ui.btnCancel.clicked.connect(self._on_cancel)
        self.ui.btnEnableTrial.clicked.connect(self._on_enable_trial)
        self.ui.btnGetLicense.clicked.connect(self._on_get_license)

        # старт: ховаємо, покажемо в refresh() якщо треба
        self.ui.btnEnableTrial.setVisible(False)

        self.refresh()

        # один раз після побудови — щоб статусбар підтягнувся
        if callable(self._on_license_changed):
            self._on_license_changed()

    def _setup_license_key_editor(self) -> None:
        """Налаштувати поле LICENSE_KEY / .lic файла."""
        self.ui.editLicenseKey.setFont(QFont("Consolas", 10))
        self.ui.editLicenseKey.setPlaceholderText(
            self._lang_mgr.tr(
                "SettingsPageLicense.editLicenseKey.placeholder",
                "Paste LICENSE_KEY or .lic file name",
            )
        )

    def _update_action_buttons_state(self, status: str) -> None:
        """
        Вимкнути кнопки отримання / активації, якщо ліцензія вже активна.
        """
        is_active = status == "PRO_OK"

        self.ui.btnGetLicense.setEnabled(not is_active)
        self.ui.btnActivate.setEnabled(not is_active)

        # trial лишаємо доступним, якщо потрібно
        # self.ui.btnEnableTrial.setEnabled(not is_active)

    def refresh(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            self._set_values("-", "-", "-", "-", "-", "-")
            self._set_info_neutral_if_needed("NO_LICENSE")
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        lic = conf.get("license", {}) if isinstance(conf, dict) else {}

        app_version = str(conf.get("version") or "0.0.0")
        res = LicenseManager.compute_and_update(conf, app_version=app_version)

        status_raw = str(res.status)
        edition_raw = str(res.edition)

        is_max_edition = edition_raw == "pro_plus"

        can_enter_key = not is_max_edition
        can_get_license = not is_max_edition

        self.ui.editLicenseKey.setEnabled(can_enter_key)
        self.ui.btnActivate.setEnabled(can_enter_key)
        self.ui.btnGetLicense.setEnabled(can_get_license)

        # PRO ще дозволяє вставити ключ для upgrade на PRO+.
        # PRO+ — фінальна редакція, вводити ключ уже не потрібно.
        can_enter_key = not is_max_edition

        self.ui.editLicenseKey.setEnabled(can_enter_key)
        self.ui.btnActivate.setEnabled(can_enter_key)

        # чистити поле тільки коли вводити не можна
        if not can_enter_key:
            self.ui.editLicenseKey.setPlainText("")

        is_no_license = status_raw == "NO_LICENSE"
        self.ui.btnEnableTrial.setVisible(is_no_license)
        self.ui.btnEnableTrial.setEnabled(is_no_license)

        status_ui = self._status_text(status_raw)
        edition_ui = edition_raw
        days_used = str(res.days_used)

        machine_id = str(lic.get("machine_id") or "")
        machine_short = self._short_machine(machine_id)

        source = str(lic.get("source") or "-")
        activated_at = str(lic.get("activated_at") or "-")

        self._set_values(
            status_ui, edition_ui, days_used, machine_short, source, activated_at
        )

        # нижній рядок — тільки за статусом, або нейтральне
        if status_raw == "NO_LICENSE":
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgTrialInfo",
                    f"Trial mode: {TRIAL_DAYS} days of nearly full functionality"
                    " (demo accounts only).",
                ),
                kind="info",
            )
        elif status_raw == "PRO_OK":
            self._set_info(
                self._lang_mgr.tr("SettingsPageLicense.msgActivated", "Activated."),
                kind="ok",
            )
        elif status_raw == "UPDATE_REQUIRED":
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.statusUpdateRequired", "Update required"
                ),
                kind="err",
            )
        elif status_raw == "TRIAL_EXPIRED":
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.statusTrialExpired", "Trial expired"
                ),
                kind="err",
            )
        elif status_raw == "OTHER_MACHINE":
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.statusOtherMachine", "Other machine"
                ),
                kind="err",
            )
        elif status_raw in ("TAMPERED", "CLOCK_ROLLBACK"):
            self._set_info(status_raw, kind="err")
        else:
            self._set_info_neutral_if_needed(status_raw)

    def _set_values(
        self,
        status: str,
        edition: str,
        days: str,
        machine: str,
        source: str,
        activated: str,
    ) -> None:
        self.ui.lblStatusValue.setText(status)
        self.ui.lblEditionValue.setText(edition)
        self.ui.lblDaysValue.setText(days)
        self.ui.lblMachineValue.setText(machine)
        self.ui.lblSourceValue.setText(source)
        self.ui.lblActivatedValue.setText(activated)

    @staticmethod
    def _short_machine(machine_id: str) -> str:
        if not machine_id:
            return "-"
        s = machine_id.strip()
        if len(s) <= 16:
            return s
        return f"{s[:10]}...{s[-6:]}"

    def _on_activate(self) -> None:
        if (
            session_state.CURRENT_CONFIG is None
            or session_state.CURRENT_PASSWORD is None
        ):
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgNotLoggedIn", "Not logged in."
                ),
                kind="err",
            )
            return

        raw_key = self.ui.editLicenseKey.toPlainText().strip()
        if not raw_key:
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgEmptyKey", "Empty license key."
                ),
                kind="err",
            )
            return

        key = self._resolve_license_key_input(raw_key)
        if not key:
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        app_version = str(conf.get("version") or "0.0.0")

        ok, msg = LicenseManager.activate_key(
            conf, license_key=key, app_version=app_version
        )
        if not ok:
            msg_s = str(msg)

            msg_key_map = {
                "Update required": "SettingsPageLicense.statusUpdateRequired",
                "Invalid license key format": "SettingsPageLicense.msgInvalidKeyFormat",
                "Invalid signature": "SettingsPageLicense.msgInvalidSignature",
                "Invalid product": "SettingsPageLicense.msgInvalidProduct",
                "Invalid edition": "SettingsPageLicense.msgInvalidEdition",
                "License expired": "SettingsPageLicense.statusTrialExpired",
            }

            key_i18n = msg_key_map.get(msg_s)
            if key_i18n:
                self._set_info(self._lang_mgr.tr(key_i18n, msg_s), kind="err")
            else:
                self._set_info(msg_s, kind="err")
            return

        res = LicenseManager.compute_and_update(conf, app_version=app_version)
        if res.fatal:
            self._set_info(f"Fatal: {res.fatal_reason}", kind="err")
            QApplication.instance().quit()
            return

        try:
            ConfigManager(ROOT_CONF_PATH).save(conf, session_state.CURRENT_PASSWORD)
            loaded = ConfigManager(ROOT_CONF_PATH).load(session_state.CURRENT_PASSWORD)
            session_state.CURRENT_CONFIG = ConfigCollection(loaded)
            self._sync_trial_button_visibility(loaded)
        except Exception:  # noqa
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgSaveFailed",
                    "Activated, but failed to save config.",
                ),
                kind="err",
            )
            return

        self.ui.editLicenseKey.setPlainText("")
        self._set_info(
            self._lang_mgr.tr("SettingsPageLicense.msgActivated", "Activated."),
            kind="ok",
        )

        self._notify_license_changed()
        self.refresh()
        if license_activation_requires_restart(res.edition):
            QTimer.singleShot(0, self._request_restart_after_activation)

    def _request_restart_after_activation(self) -> None:
        callback = self._on_license_restart_requested
        if callable(callback):
            callback()

    def _resolve_license_key_input(self, text: str) -> str:
        """
        Приймає:
        - повний LICENSE_KEY;
        - назву .lic файла з BASE_DIR/licenses;
        - повний шлях до .lic файла.

        Повертає нормалізований LICENSE_KEY або порожній рядок.
        """
        raw = (text or "").strip()
        if not raw:
            return ""

        if raw.lower().endswith(".lic"):
            path = Path(raw)

            if not path.is_absolute():
                path = BASE_DIR / "licenses" / raw

            if not path.exists() or not path.is_file():
                self._set_info(
                    self._lang_mgr.tr(
                        "SettingsPageLicense.msgLicenseFileNotFound",
                        "License file not found.",
                    ),
                    kind="err",
                )
                return ""

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa
                self._set_info(
                    self._lang_mgr.tr(
                        "SettingsPageLicense.msgLicenseFileReadFailed",
                        "Failed to read license file.",
                    ),
                    kind="err",
                )
                return ""

            payload_b64 = str(data.get("payload_b64") or "").strip()
            signature_b64 = str(data.get("signature_b64") or "").strip()

            if not payload_b64 or not signature_b64:
                self._set_info(
                    self._lang_mgr.tr(
                        "SettingsPageLicense.msgInvalidLicenseFile",
                        "Invalid license file.",
                    ),
                    kind="err",
                )
                return ""

            return f"{payload_b64}.{signature_b64}"

        return "".join(raw.split())

    def _on_get_license(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            self._set_info("NO_LICENSE", kind="warn")
            return

        dlg = LicenseRequestDialog(
            parent=self,
            lang_mgr=self._lang_mgr,
        )
        dlg.exec()

        # Тут нічого не “оновлюємо” автоматом.
        # Якщо колись зробиш автозавантаження ліцензії — тоді refresh().

    def _on_copy_diag(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgNotLoggedIn", "Not logged in."
                ),
                kind="err",
            )
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        lic = conf.get("license", {})
        payload = {
            "app": conf.get("app"),
            "version": conf.get("version"),
            "email": conf.get("email"),
            "license": {
                "edition": lic.get("edition"),
                "status": lic.get("status"),
                "machine_id": lic.get("machine_id"),
                "source": lic.get("source"),
                "activated_at": lic.get("activated_at"),
                "issued_at": lic.get("issued_at"),
                "expires_at": lic.get("expires_at"),
                "version_min": lic.get("version_min"),
            },
        }

        text = json.dumps(payload, ensure_ascii=False, indent=2)
        QApplication.clipboard().setText(text)
        self._set_info(
            self._lang_mgr.tr(
                "SettingsPageLicense.msgDiagCopied", "Diagnostics copied to clipboard."
            ),
            kind="ok",
        )

    @staticmethod
    def _read_app_version() -> str:
        """Повертає версію застосунку з app_meta."""
        return VERSION

    def _set_info(self, text: str, *, kind: str = "info") -> None:
        if kind == "ok":
            self.ui.lblActivationInfo.setStyleSheet("color: lightgreen;")
        elif kind == "err":
            self.ui.lblActivationInfo.setStyleSheet("color: salmon;")
        else:
            self.ui.lblActivationInfo.setStyleSheet("color: lightgray;")

        s = (text or "").strip()
        if s.startswith("[") and s.endswith("]") and len(s) > 2:
            key = s[1:-1].strip()
            text = self._lang_mgr.tr(key, text)

        self.ui.lblActivationInfo.setText(text)

    def _on_cancel(self) -> None:
        self.ui.editLicenseKey.setPlainText("")
        self._set_info("")
        self.window().close()

    def _status_text(self, status_raw: str) -> str:
        key = _STATUS_I18N.get(status_raw)
        if not key:
            return status_raw
        return self._lang_mgr.tr(key, status_raw)

    def _set_info_neutral_if_needed(self, status_raw: str | None = None) -> None:
        # якщо вже щось показано — не ліземо
        current = (self.ui.lblActivationInfo.text() or "").strip()
        if current:
            return

        # нейтральний hint потрібен лише коли реально можна вводити ключ
        if status_raw is not None and status_raw not in (
            "NO_LICENSE",
            "TRIAL_OK",
            "TRIAL_EXPIRED",
        ):
            return

        key_text = (self.ui.editLicenseKey.toPlainText() or "").strip()
        if key_text:
            return

        self._set_info(
            self._lang_mgr.tr(
                "SettingsPageLicense.msgHintPasteAndActivate",
                "Paste the key and click Activate",
            ),
            kind="info",
        )

    def _notify_license_changed(self) -> None:
        # викликаємо колбек SettingsCenter, якщо дали
        if callable(self._on_license_changed):
            try:
                self._on_license_changed()
                return
            except Exception:  # noqa
                pass

        # fallback: шукаємо публічний метод update_statusbar на parent
        w = self.window()
        parent = w.parent() if w is not None else None
        cb = getattr(parent, "update_statusbar", None)
        if callable(cb):
            cb()

    def _on_enable_trial(self) -> None:
        if (
            session_state.CURRENT_CONFIG is None
            or session_state.CURRENT_PASSWORD is None
        ):
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgNotLoggedIn", "Not logged in."
                ),
                kind="err",
            )
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        app_version = str(conf.get("version") or "0.0.0")

        try:
            LicenseManager.enable_trial(conf, app_version=app_version)

            ConfigManager(ROOT_CONF_PATH).save(conf, session_state.CURRENT_PASSWORD)
            loaded = ConfigManager(ROOT_CONF_PATH).load(session_state.CURRENT_PASSWORD)
            session_state.CURRENT_CONFIG = ConfigCollection(loaded)

        except RuntimeError as e:
            if str(e) == LicenseManager.ST_TRIAL_ALREADY_USED:
                self._set_info(
                    self._lang_mgr.tr(
                        "SettingsPageLicense.msgTrialAlreadyUsed",
                        "The trial period for this device has already been used. "
                        "Trial cannot be started again.",
                    ),
                    kind="err",
                )
                self._sync_trial_button_visibility(conf)
                return

            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgTrialSaveFailed",
                    "Failed to save config after enabling TRIAL.",
                ),
                kind="err",
            )
            return

        except Exception:  # noqa
            self._set_info(
                self._lang_mgr.tr(
                    "SettingsPageLicense.msgTrialSaveFailed",
                    "Failed to save config after enabling TRIAL.",
                ),
                kind="err",
            )
            return

        self._set_info(
            self._lang_mgr.tr("SettingsPageLicense.msgTrialEnabled", "TRIAL enabled."),
            kind="ok",
        )
        self._notify_license_changed()
        self.refresh()

    def _sync_trial_button_visibility(self, conf: dict[str, Any]) -> None:
        """
        Показати або сховати кнопку Trial.

        Якщо trial уже був використаний, кнопку ховаємо.
        Інші кнопки не чіпаємо: ліцензію все одно можна отримати/активувати.
        """
        btn = getattr(self.ui, "btnEnableTrial", None)
        if btn is None:
            return

        try:
            already_used = LicenseManager.is_trial_already_used(conf)
        except Exception:  # noqa
            already_used = False

        btn.setVisible(not already_used)
