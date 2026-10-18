# -*- coding: utf-8 -*-
"""
T111-27 — Machine Binding Diagnostic — TEST_ONLY.

Без змін production і без брокерських запитів:
- читає копію LGE.conf;
- порівнює stored/payload machine_id з поточними кандидатами;
- показує лише скорочені/хешовані ідентифікатори;
- не змінює вихідний LGE.conf.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import shutil
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import resources_rc  # noqa: F401, E402
from core.app_meta import VERSION  # noqa: E402
from core.config_manager import ConfigManager  # noqa: E402
from core.license_manager import LicenseManager  # noqa: E402

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False
CONF_PATH = PROJECT_ROOT / "LGE.conf"


def _short_id(value: str | None) -> str:
    if not value:
        return "NONE"
    value = value.strip()
    if len(value) <= 16:
        return value
    return f"{value[:12]}...{value[-4:]}"


def _hash12(value: str | None) -> str:
    if not value:
        return "NONE"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _payload_machine_id(lic: dict[str, Any]) -> str | None:
    payload_b64 = lic.get("payload_b64")
    if not isinstance(payload_b64, str) or not payload_b64.strip():
        return None
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("machine_id") or payload.get("fingerprint")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _ask_password() -> str | None:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)

    password, accepted = QInputDialog.getText(
        None,
        "T111-27",
        "Пароль до LGE.conf:",
        QLineEdit.EchoMode.Password,
    )
    if owns_app:
        app.processEvents()
    if not accepted:
        return None
    return password


def main() -> int:
    print("T111-27 TEST_ONLY")
    print("source_conf=LGE.conf")
    print("source_conf_mutated=False")

    if not CONF_PATH.exists():
        print("verdict=CONF_MISSING")
        return 1

    password = _ask_password()
    if password is None:
        print("verdict=USER_CANCELLED")
        return 2

    with tempfile.TemporaryDirectory(prefix="t111_27_") as tmp:
        copied = Path(tmp) / "LGE.conf"
        shutil.copy2(CONF_PATH, copied)

        manager = ConfigManager(copied)
        conf, status = manager.load_with_status(password)
        print(f"conf_load_status={status}")
        if status != "ok" or not isinstance(conf, dict):
            print("verdict=CONF_READ_FAILED")
            return 1

        lic = conf.get("license")
        if not isinstance(lic, dict):
            print("verdict=LICENSE_BLOCK_MISSING")
            return 1

        stored_mid = lic.get("machine_id")
        if not isinstance(stored_mid, str):
            stored_mid = None

        payload_mid = _payload_machine_id(lic)
        preferred, candidates = LicenseManager.compute_machine_id_candidates()

        probe_conf = deepcopy(conf)
        probe_result = LicenseManager.compute_and_update(
            probe_conf,
            app_version=VERSION,
        )

        print(f"edition={lic.get('edition')}")
        print(f"stored_machine_id={_short_id(stored_mid)}")
        print(f"payload_machine_id={_short_id(payload_mid)}")
        print(f"current_preferred_id={_short_id(preferred)}")
        stored_matches_candidate = bool(stored_mid and stored_mid in candidates)
        payload_matches_candidate = bool(payload_mid and payload_mid in candidates)
        payload_matches_stored = bool(
            payload_mid and stored_mid and payload_mid == stored_mid
        )

        print(f"stored_matches_candidate={stored_matches_candidate}")
        print(f"payload_matches_candidate={payload_matches_candidate}")
        print(f"payload_matches_stored={payload_matches_stored}")

        print(f"compute_and_update_status={probe_result.status}")

        if stored_mid and stored_mid in candidates:
            verdict = "CURRENT_MACHINE_SHOULD_BE_ACCEPTED"
        elif payload_mid and payload_mid in candidates and stored_mid not in candidates:
            verdict = "CONF_MACHINE_ID_STATE_INCONSISTENT"
        elif stored_mid and payload_mid and stored_mid == payload_mid:
            verdict = "MACHINE_FINGERPRINT_DRIFT_OR_INPUT_CHANGE"
        elif stored_mid:
            verdict = "MACHINE_BINDING_MISMATCH_CONFIRMED"
        else:
            verdict = "STORED_MACHINE_ID_MISSING"

        print(f"verdict={verdict}")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"broker_execution_attempted={BROKER_EXECUTION_ATTEMPTED}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("source_conf_mutated=False")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
