# -*- coding: utf-8 -*-
"""T110-08 — License Capability Matrix Fix."""

from __future__ import annotations

import copy
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import resources_rc  # noqa: E402,F401

from core.app_meta import TRIAL_DAYS  # noqa: E402
from core.license_manager import LicenseManager  # noqa: E402

TEST_ONLY = True
BROKER_REQUESTS = 0
PRODUCTION_LOGIC_CHANGED = True


def _base_free_conf() -> dict:
    return {
        "license": {
            "edition": "free",
            "activated_at": None,
            "machine_id": LicenseManager.compute_machine_id(),
            "payload_b64": None,
            "signature_b64": None,
        }
    }


def _compute(conf: dict, now: datetime):
    probe = copy.deepcopy(conf)
    return LicenseManager.compute_and_update(
        probe,
        now=now,
        app_version="1.0.1",
    )


def main() -> int:
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)

    no_license = _base_free_conf()
    no_license_result = _compute(no_license, now)

    trial = _base_free_conf()
    trial["license"]["activated_at"] = now.isoformat()
    trial["license"]["expires_at"] = (
        now + timedelta(days=TRIAL_DAYS)
    ).isoformat()
    trial_result = _compute(trial, now)

    expired = _base_free_conf()
    expired_started = now - timedelta(days=TRIAL_DAYS + 1)
    expired["license"]["activated_at"] = expired_started.isoformat()
    expired["license"]["expires_at"] = (
        expired_started + timedelta(days=TRIAL_DAYS)
    ).isoformat()
    expired_result = _compute(expired, now)

    manager_source = (
        PROJECT_ROOT / "core" / "license_manager.py"
    ).read_text(encoding="utf-8")

    checks = {
        "no_license_status": (
            no_license_result.status == LicenseManager.ST_NO_LICENSE
        ),
        "no_license_ib_connect": no_license_result.caps.ib_connect,
        "no_license_signals_view": no_license_result.caps.signals_view,
        "no_license_manual_allowed": no_license_result.caps.live_manual,
        "no_license_semi_blocked": not no_license_result.caps.live_semi,
        "no_license_auto_demo_blocked": not no_license_result.caps.auto_demo,
        "no_license_auto_full_blocked": not no_license_result.caps.auto_full,
        "trial_status": trial_result.status == LicenseManager.ST_TRIAL_OK,
        "trial_ib_connect": trial_result.caps.ib_connect,
        "trial_signals_view": trial_result.caps.signals_view,
        "trial_manual_allowed": trial_result.caps.live_manual,
        "trial_semi_blocked": not trial_result.caps.live_semi,
        "trial_auto_demo_blocked": not trial_result.caps.auto_demo,
        "trial_auto_full_blocked": not trial_result.caps.auto_full,
        "expired_auto_demo_blocked": not expired_result.caps.auto_demo,
        "expired_auto_full_blocked": not expired_result.caps.auto_full,
        "pro_branch_manual_preserved": (
            "elif status == cls.ST_PRO_OK:" in manager_source
            and "live_manual = True" in manager_source
            and "live_semi = True" in manager_source
        ),
        "pro_branch_auto_full_preserved": (
            'if edition == "pro_plus":' in manager_source
            and 'elif edition == "pro":' in manager_source
            and "auto_full = True" in manager_source
        ),
    }

    print("T110-08 — License Capability Matrix Fix")
    print()

    failed = 0
    for name, passed in checks.items():
        state = "PASS" if passed else "FAIL"
        print(f"{state} {name}={passed}")
        failed += 0 if passed else 1

    print()
    print(f"checks={len(checks)}")
    print(f"passed={len(checks) - failed}")
    print(f"failed={failed}")

    if failed:
        print("boundary=LICENSE_CAPABILITY_MATRIX_NOT_REPAIRED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-08=RED")
        return 1

    print("NO_LICENSE=MANUAL_ALLOWED_AUTO_BLOCKED")
    print("TRIAL_OK=MANUAL_ALLOWED_AUTO_BLOCKED")
    print("TRIAL_EXPIRED=AUTO_BLOCKED")
    print("PRO_PRO_PLUS=SOURCE_BRANCH_PRESERVED")
    print("first_repaired_boundary=LICENSE_CAPABILITY_MATRIX")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-08=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
