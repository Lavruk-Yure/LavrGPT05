# settings_page_license.py
# -*- coding: utf-8 -*-
"""
SettingsPageLicense — сторінка ліцензії (RoadMap19 / Patch 19.4)

UI: ui/license_page.ui -> ui/ui_license_page.py
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from PySide6.QtWidgets import QApplication, QWidget

from core import session_state
from core.app_paths import ROOT_CONF_PATH, ROOT_INIT_PATH
from core.config_manager import ConfigManager
from core.license_manager import LicenseManager
from ui.ui_settings_page_license import Ui_pageLicense

_STATUS_I18N = {
    "TRIAL_OK": "SettingsPageLicense.statusTrialOk",
    "TRIAL_EXPIRED": "SettingsPageLicense.statusTrialExpired",
    "PRO_OK": "SettingsPageLicense.statusProOk",
    "PRO_LIMITED": "SettingsPageLicense.statusProLimited",
    "UPDATE_REQUIRED": "SettingsPageLicense.statusUpdateRequired",
    "EXPIRED": "SettingsPageLicense.statusExpired",
    "OTHER_MACHINE": "SettingsPageLicense.statusOtherMachine",
    "TAMPERED": "SettingsPageLicense.statusTampered",
}


DEBUG_LICENSE_PAGE = False

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


def log_lp(name: str, **kw: Any) -> None:
    if not DEBUG_LICENSE_PAGE:
        return
    msg = f"[LICENSE_PAGE:{name}] " + ", ".join(f"{k}={v!r}" for k, v in kw.items())
    print(msg)


class SettingsPageLicense(QWidget):
    def __init__(self, parent: QWidget | None, lang_mgr) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._lang_mgr = lang_mgr

        self.ui = Ui_pageLicense()
        self.ui.setupUi(self)

        # UI повідомлення замість QMessageBox
        self.ui.lblActivationInfo.setWordWrap(True)
        self.ui.lblActivationInfo.setStyleSheet("color: lightgray;")
        self._set_info("")

        self.ui.btnActivate.clicked.connect(self._on_activate)
        self.ui.btnCopyDiag.clicked.connect(self._on_copy_diag)
        self.ui.btnCancel.clicked.connect(self._on_cancel)

        self.refresh()

    def refresh(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            self._set_values("-", "-", "-", "-", "-", "-")
            self._set_info("")
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        lic = conf.get("license", {}) if isinstance(conf, dict) else {}

        app_version = str(conf.get("version") or "0.0.0")
        res = LicenseManager.compute_and_update(conf, app_version=app_version)

        # --- RAW для логіки ---
        status_raw = str(res.status)
        edition_raw = str(res.edition)

        # --- UI тексти (перекладені) ---
        status_ui = self._status_text(status_raw)
        edition_ui = edition_raw  # поки без перекладу
        days_used = str(res.days_used)

        machine_id = str(lic.get("machine_id") or "")
        machine_short = self._short_machine(machine_id)

        source = str(lic.get("source") or "-")
        activated_at = str(lic.get("activated_at") or "-")

        self._set_values(
            status_ui,
            edition_ui,
            days_used,
            machine_short,
            source,
            activated_at,
        )

        # Нижній рядок (lblActivationInfo) — одноманітні повідомлення
        if status_raw == "PRO_OK":
            self._set_info(
                self._tr("SettingsPageLicense.msgActivated", "Activated."),
                kind="ok",
            )
        elif status_raw == "UPDATE_REQUIRED":
            self._set_info(
                self._tr("SettingsPageLicense.statusUpdateRequired", "Update required"),
                kind="err",
            )
        elif status_raw == "TRIAL_EXPIRED":
            self._set_info(
                self._tr("SettingsPageLicense.statusTrialExpired", "Trial expired"),
                kind="err",
            )
        elif status_raw == "OTHER_MACHINE":
            self._set_info(
                self._tr("SettingsPageLicense.statusOtherMachine", "Other machine"),
                kind="err",
            )
        elif status_raw in ("TAMPERED", "CLOCK_ROLLBACK"):
            # це вже серйозно, але хоча б покажемо людині
            self._set_info(status_raw, kind="err")
        else:
            self._set_info("")

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
                self._tr("SettingsPageLicense.msgNotLoggedIn", "Not logged in."),
                kind="err",
            )
            return

        key = self.ui.editLicenseKey.toPlainText().strip()
        key = "".join(key.split())
        if not key:
            self._set_info(
                self._tr("SettingsPageLicense.msgEmptyKey", "Empty license key."),
                kind="err",
            )
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        app_version = str(conf.get("version") or "0.0.0")

        ok, msg = LicenseManager.activate_key(
            conf, license_key=key, app_version=app_version
        )
        if not ok:
            # msg зараз англійський з LicenseManager — можна лишити,
            # або потім замапити на ключі
            self._set_info(str(msg), kind="err")
            return

        res = LicenseManager.compute_and_update(conf, app_version=app_version)
        if res.fatal:
            self._set_info(f"Fatal: {res.fatal_reason}", kind="err")
            QApplication.instance().quit()
            return

        try:
            ConfigManager(ROOT_CONF_PATH).save(conf, session_state.CURRENT_PASSWORD)
        except Exception:  # noqa
            self._set_info(
                self._tr(
                    "SettingsPageLicense.msgSaveFailed",
                    "Activated, but failed to save config.",
                ),
                kind="err",
            )
            return

        self.ui.editLicenseKey.setPlainText("")
        self._set_info(
            self._tr("SettingsPageLicense.msgActivated", "Activated."), kind="ok"
        )
        self.refresh()

    def _on_copy_diag(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            self._set_info(
                self._tr("SettingsPageLicense.msgNotLoggedIn", "Not logged in."),
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
            self._tr(
                "SettingsPageLicense.msgDiagCopied", "Diagnostics copied to clipboard."
            ),
            kind="ok",
        )

    @staticmethod
    def _read_app_version() -> str:
        """
        Читає __version__ з ROOT_INIT_PATH.
        Без імпорту пакета (щоб уникнути циклічних імпортів).
        """
        try:
            text = ROOT_INIT_PATH.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa
            return "0.0.0"

        m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
        if not m:
            m = re.search(r"__version__\s*=\s*'([^']+)'", text)
        return m.group(1).strip() if m else "0.0.0"

    def _tr(self, key: str, fallback: str) -> str:
        try:
            s = self._lang_mgr.resolve(key)
        except Exception:  # noqa
            return fallback
        return s if isinstance(s, str) and s else fallback

    def _set_info(self, text: str, *, kind: str = "info") -> None:
        # kind: info / ok / err
        if kind == "ok":
            self.ui.lblActivationInfo.setStyleSheet("color: lightgreen;")
        elif kind == "err":
            self.ui.lblActivationInfo.setStyleSheet("color: salmon;")
        else:
            self.ui.lblActivationInfo.setStyleSheet("color: lightgray;")
        self.ui.lblActivationInfo.setText(text)

    def _on_cancel(self) -> None:
        self.ui.editLicenseKey.setPlainText("")
        self._set_info("")
        self.window().close()

    def _status_text(self, status_raw: str) -> str:
        key = _STATUS_I18N.get(status_raw)
        if not key:
            return status_raw
        return self._tr(key, status_raw)
