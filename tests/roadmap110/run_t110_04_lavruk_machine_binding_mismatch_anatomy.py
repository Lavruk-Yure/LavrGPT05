# -*- coding: utf-8 -*-
"""
T110-04 — LAVRUK Machine Binding Mismatch Anatomy — TEST_ONLY.

Працює лише з копією реального LGE.conf.
Production-файли не змінює.
Пароль вводиться через Qt-діалог у Password mode.
Секретні значення та повні machine identifiers не друкує.
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit  # noqa: E402

import resources_rc  # noqa: E402,F401
from core.app_meta import VERSION  # noqa: E402
from core.app_paths import ROOT_CONF_PATH  # noqa: E402
from core.config_manager import ConfigManager  # noqa: E402
from core.license_manager import LicenseManager  # noqa: E402

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = False


def _short_hash(value: str | None) -> str:
    if not value:
        return "NONE"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _short_id(value: str | None) -> str:
    if not value:
        return "NONE"
    value = value.strip()
    if len(value) <= 16:
        return value
    return f"{value[:12]}...{value[-4:]}"


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
        "T110-04",
        "Пароль до LGE.conf:",
        QLineEdit.EchoMode.Password,
    )

    if owns_app:
        app.processEvents()

    if not accepted:
        return None
    return password


def main() -> int:
    print("T110-04 — LAVRUK Machine Binding Mismatch Anatomy — TEST_ONLY")
    print(f"source_conf={ROOT_CONF_PATH.name}")
    print("source_conf_mutated=False")
    print()

    if not ROOT_CONF_PATH.exists():
        print("FAIL conf_exists=False")
        print("T110-04=RED")
        return 1

    password = _ask_password()
    if password is None:
        print("input_status=CANCELLED")
        print("source_conf_mutated=False")
        print("T110-04=BLOCKED_BY_USER_CANCEL")
        return 2

    with tempfile.TemporaryDirectory(prefix="lge_t110_04_") as temp_dir:
        copied_conf = Path(temp_dir) / ROOT_CONF_PATH.name
        shutil.copy2(ROOT_CONF_PATH, copied_conf)

        manager = ConfigManager(copied_conf)
        conf, load_status = manager.load_with_status(password)

        print(f"conf_load_status={load_status}")
        if load_status != "ok" or not isinstance(conf, dict):
            print("boundary=CONF_READ_FAILED")
            print(f"TEST_ONLY={TEST_ONLY}")
            print(f"broker_requests={BROKER_REQUESTS}")
            print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
            print("source_conf_mutated=False")
            print("T110-04=RED")
            return 1

        lic = conf.get("license")
        if not isinstance(lic, dict):
            print("FAIL license_block_present=False")
            print("boundary=LICENSE_BLOCK_MISSING")
            print("source_conf_mutated=False")
            print("T110-04=RED")
            return 1

        stored_mid = lic.get("machine_id")
        if not isinstance(stored_mid, str):
            stored_mid = None

        payload_mid = _payload_machine_id(lic)

        preferred, candidates = LicenseManager.compute_machine_id_candidates()

        legacy_candidates = sorted(
            candidate for candidate in candidates if candidate != preferred
        )
        stored_matches_preferred = stored_mid == preferred
        stored_matches_candidate = stored_mid in candidates if stored_mid else False
        payload_matches_stored = bool(
            payload_mid and stored_mid and payload_mid == stored_mid
        )
        payload_matches_preferred = bool(payload_mid and payload_mid == preferred)
        payload_matches_candidate = bool(payload_mid and payload_mid in candidates)

        probe_conf = deepcopy(conf)
        probe_result = LicenseManager.compute_and_update(
            probe_conf,
            app_version=VERSION,
        )

        print(f"edition={lic.get('edition')}")
        print(f"stored_machine_id={_short_id(stored_mid)}")
        print(f"payload_machine_id={_short_id(payload_mid)}")
        print(f"current_preferred_id={_short_id(preferred)}")
        print(
            "current_legacy_ids="
            + (
                ",".join(_short_id(value) for value in legacy_candidates)
                if legacy_candidates
                else "NONE"
            )
        )
        print()

        print(f"stored_matches_preferred={stored_matches_preferred}")
        print(f"stored_matches_candidate={stored_matches_candidate}")
        print(f"payload_matches_stored={payload_matches_stored}")
        print(f"payload_matches_preferred={payload_matches_preferred}")
        print(f"payload_matches_candidate={payload_matches_candidate}")
        print(f"compute_and_update_status={probe_result.status}")
        print()

        if stored_matches_candidate:
            boundary = "STARTUP_RESULT_INCONSISTENT_WITH_MACHINE_CANDIDATES"
            verdict = "CURRENT_MACHINE_SHOULD_BE_ACCEPTED"
        elif payload_matches_candidate and not stored_matches_candidate:
            boundary = "STORED_MACHINE_ID_DIFFERS_FROM_VALID_PAYLOAD"
            verdict = "CONF_MACHINE_ID_STATE_INCONSISTENT"
        elif stored_mid and payload_mid and stored_mid == payload_mid:
            boundary = "CURRENT_MACHINE_ID_NO_LONGER_MATCHES_ISSUED_FINGERPRINT"
            verdict = "MACHINE_FINGERPRINT_DRIFT_OR_INPUT_CHANGE"
        elif stored_mid:
            boundary = "STORED_MACHINE_ID_NOT_IN_CURRENT_CANDIDATES"
            verdict = "MACHINE_BINDING_MISMATCH_CONFIRMED"
        else:
            boundary = "STORED_MACHINE_ID_MISSING"
            verdict = "MACHINE_BINDING_STATE_INCOMPLETE"

        print(f"first_broken_boundary={boundary}")
        print(f"verdict={verdict}")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("source_conf_mutated=False")
        print("T110-04=GREEN")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
