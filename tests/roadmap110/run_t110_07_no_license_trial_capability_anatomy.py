# -*- coding: utf-8 -*-
"""
T110-07 — NO_LICENSE / TRIAL Capability Anatomy — TEST_ONLY.

Порівнює фактичну production capability matrix з канонічним
doc/LGE_Algorithms_01.md без зміни production.

Використовує тільки публічний LicenseManager.compute_and_update().
Тривалість trial виводиться окремо як production-факт.
"""

from __future__ import annotations

import copy
import re
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
PRODUCTION_LOGIC_CHANGED = False

CANON_PATH = PROJECT_ROOT / "doc" / "LGE_Algorithms_01.md"


def _section(text: str, heading: str, next_heading: str) -> str:
    pattern = (
        rf"(?ms)^\s*{re.escape(heading)}\s*$"
        rf"(.*?)"
        rf"^\s*{re.escape(next_heading)}\s*$"
    )
    match = re.search(pattern, text)
    if match is None:
        raise AssertionError(f"canonical_section_not_found={heading}")
    return match.group(1)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def _base_free_conf() -> dict:
    return {
        "license": {
            "edition": "free",
            "activated_at": None,
            "machine_id": LicenseManager.compute_machine_id(),
            "payload_b64": "",
            "sig_b64": "",
        }
    }


def _compute(conf: dict):
    probe = copy.deepcopy(conf)
    return LicenseManager.compute_and_update(
        probe,
        app_version="1.0.1",
    )


def main() -> int:
    canon = CANON_PATH.read_text(encoding="utf-8")
    trial_section = _section(canon, "TRIAL", "NO_TRIAL")
    no_trial_section = _section(canon, "NO_TRIAL", "PRO")

    no_license_conf = _base_free_conf()
    no_license_result = _compute(no_license_conf)

    trial_conf = _base_free_conf()
    trial_conf["license"]["activated_at"] = _iso_utc(datetime.now(UTC))
    trial_result = _compute(trial_conf)

    expired_conf = _base_free_conf()
    expired_started = datetime.now(UTC) - timedelta(days=TRIAL_DAYS + 1)
    expired_conf["license"]["activated_at"] = _iso_utc(expired_started)
    expired_result = _compute(expired_conf)

    canonical_trial_manual = "ручні ордери" in trial_section
    canonical_trial_demo = "DEMO" in trial_section
    canonical_trial_auto_forbidden = (
        "Заборонено" in trial_section and "AUTO" in trial_section
    )
    canonical_no_trial_manual = "ручні ордери" in no_trial_section

    checks = {
        "canonical_trial_manual_allowed": canonical_trial_manual,
        "canonical_trial_demo_allowed": canonical_trial_demo,
        "canonical_trial_auto_forbidden": canonical_trial_auto_forbidden,
        "canonical_no_trial_manual_allowed": canonical_no_trial_manual,
        "no_license_status_confirmed": (
            no_license_result.status == LicenseManager.ST_NO_LICENSE
        ),
        "trial_status_confirmed": (trial_result.status == LicenseManager.ST_TRIAL_OK),
        "expired_status_confirmed": (
            expired_result.status == LicenseManager.ST_TRIAL_EXPIRED
        ),
        "production_trial_manual_is_currently_false": (
            not trial_result.caps.live_manual
        ),
        "production_trial_auto_demo_is_currently_true": trial_result.caps.auto_demo,
        "production_no_license_manual_is_currently_false": (
            not no_license_result.caps.live_manual
        ),
        "production_no_license_auto_demo_is_currently_true": (
            no_license_result.caps.auto_demo
        ),
        "production_trial_expired_auto_is_blocked": (
            not expired_result.caps.auto_demo and not expired_result.caps.auto_full
        ),
        "production_trial_days_positive": TRIAL_DAYS > 0,
    }

    print("T110-07 — NO_LICENSE / TRIAL Capability Anatomy — TEST_ONLY")
    print()
    print(f"production_trial_days={TRIAL_DAYS}")
    print("canonical_trial_days=NOT_SPECIFIED_IN_LGE_ALGORITHMS_01")
    print()

    print(
        "canonical_trial="
        f"manual={canonical_trial_manual} "
        f"demo={canonical_trial_demo} "
        f"auto_forbidden={canonical_trial_auto_forbidden}"
    )
    print(
        "production_trial="
        f"status={trial_result.status} "
        f"live_manual={trial_result.caps.live_manual} "
        f"ib_connect={trial_result.caps.ib_connect} "
        f"signals_view={trial_result.caps.signals_view} "
        f"auto_demo={trial_result.caps.auto_demo} "
        f"auto_full={trial_result.caps.auto_full}"
    )
    print("canonical_no_trial=" f"manual={canonical_no_trial_manual}")
    print(
        "production_no_license="
        f"status={no_license_result.status} "
        f"live_manual={no_license_result.caps.live_manual} "
        f"ib_connect={no_license_result.caps.ib_connect} "
        f"signals_view={no_license_result.caps.signals_view} "
        f"auto_demo={no_license_result.caps.auto_demo} "
        f"auto_full={no_license_result.caps.auto_full}"
    )
    print(
        "production_trial_expired="
        f"status={expired_result.status} "
        f"auto_demo={expired_result.caps.auto_demo} "
        f"auto_full={expired_result.caps.auto_full}"
    )
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
        print("boundary=ANATOMY_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-07=RED")
        return 1

    print("trial_manual_mismatch=CANON_ALLOWED_PRODUCTION_BLOCKED")
    print("trial_auto_mismatch=CANON_BLOCKED_PRODUCTION_AUTO_DEMO_ALLOWED")
    print("no_license_manual_mismatch=CANON_ALLOWED_PRODUCTION_BLOCKED")
    print("no_license_auto_demo=PRODUCTION_ALLOWED_CANON_NOT_EXPLICITLY_ALLOWED")
    print("trial_duration_decision=UNRESOLVED_CANONICALLY")
    print("first_broken_boundary=LICENSE_CAPABILITY_MATRIX")
    print("verdict=CANONICAL_POLICY_DIFFERS_FROM_PRODUCTION_CAPS")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-07=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
