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

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from core import session_state
from core.app_paths import ROOT_CONF_PATH, ROOT_INIT_PATH
from core.config_manager import ConfigManager
from core.license_manager import LicenseManager

# from core.session_state import CURRENT_CONFIG, CURRENT_PASSWORD
from ui.ui_settings_page_license import Ui_pageLicense

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

        self.ui.btnActivate.clicked.connect(self._on_activate)
        self.ui.btnCopyDiag.clicked.connect(self._on_copy_diag)

        self.refresh()

    def refresh(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            self._set_values("-", "-", "-", "-", "-", "-")
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        lic = conf.get("license", {}) if isinstance(conf, dict) else {}

        app_version = self._read_app_version()

        res = LicenseManager.compute_and_update(conf, app_version=app_version)

        status = str(res.status)
        edition = str(res.edition)
        days_used = str(res.days_used)

        machine_id = str(lic.get("machine_id") or "")
        machine_short = self._short_machine(machine_id)

        source = str(lic.get("source") or "-")
        activated_at = str(lic.get("activated_at") or "-")

        self._set_values(
            status, edition, days_used, machine_short, source, activated_at
        )

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
            QMessageBox.warning(self, "LGE05 — License", "Not logged in.")
            return

        key = self.ui.editLicenseKey.toPlainText().strip()
        key = "".join(key.split())

        if not key:
            QMessageBox.warning(self, "LGE05 — License", "Empty license key.")
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        app_version = self._read_app_version()

        ok, msg = LicenseManager.activate_key(
            conf, license_key=key, app_version=app_version
        )
        if not ok:
            QMessageBox.warning(self, "LGE05 — License", msg)
            return

        res = LicenseManager.compute_and_update(conf, app_version=app_version)
        if res.fatal:
            QMessageBox.critical(self, "LGE05 — License", f"Fatal: {res.fatal_reason}")
            QApplication.instance().quit()
            return

        try:
            cfg_mgr = ConfigManager(ROOT_CONF_PATH)
            cfg_mgr.save(conf, session_state.CURRENT_PASSWORD)
        except Exception as e:  # noqa
            logger.exception("Failed to save config after activation: %s", e)
            QMessageBox.warning(
                self, "LGE05 — License", "Activated, but failed to save config."
            )
            return

        self.ui.editLicenseKey.setPlainText("")

        QMessageBox.information(self, "LGE05 — License", "Activated.")
        self.refresh()

    def _on_copy_diag(self) -> None:
        if session_state.CURRENT_CONFIG is None:
            return

        conf = session_state.CURRENT_CONFIG.to_dict()
        lic = conf.get("license", {})
        payload = {
            "app": conf.get("app"),
            "version": self._read_app_version(),
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
        QMessageBox.information(
            self, "LGE05 — License", "Diagnostics copied to clipboard."
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
