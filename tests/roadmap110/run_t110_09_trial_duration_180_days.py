# -*- coding: utf-8 -*-
"""T110-09 — Trial Duration 180 Days."""

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
EXPECTED_TRIAL_DAYS = 180


def _base_free_conf(*, trial_days: int) -> dict:
    return {
        "license": {
            "edition": "free",
            "activated_at": None,
            "machine_id": LicenseManager.compute_machine_id(),
            "payload_b64": None,
            "signature_b64": None,
            "trial_policy": {
                "trial_days": trial_days,
                "warn_before_expiry_days": 7,
            },
        }
    }


def _compute(conf: dict, now: datetime):
    probe = copy.deepcopy(conf)
    result = LicenseManager.compute_and_update(
        probe,
        now=now,
        app_version="1.0.1",
    )
    return result, probe


def _trial_conf(started: datetime) -> dict:
    conf = _base_free_conf(trial_days=TRIAL_DAYS)
    conf["license"]["activated_at"] = started.isoformat()
    conf["license"]["expires_at"] = (
        started + timedelta(days=TRIAL_DAYS)
    ).isoformat()
    return conf


def main() -> int:
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    stale_unstarted = _base_free_conf(trial_days=90)
    no_license_result, migrated_conf = _compute(stale_unstarted, started)

    result_179, _ = _compute(
        _trial_conf(started),
        started + timedelta(days=179),
    )
    result_180, _ = _compute(
        _trial_conf(started),
        started + timedelta(days=180),
    )
    result_181, _ = _compute(
        _trial_conf(started),
        started + timedelta(days=181),
    )

    started_old_policy = _base_free_conf(trial_days=90)
    started_old_policy["license"]["activated_at"] = started.isoformat()
    started_old_policy["license"]["expires_at"] = (
        started + timedelta(days=90)
    ).isoformat()
    _, preserved_conf = _compute(
        started_old_policy,
        started + timedelta(days=1),
    )

    checks = {
        "trial_days_constant_is_180": TRIAL_DAYS == EXPECTED_TRIAL_DAYS,
        "unstarted_free_status_is_no_license": (
            no_license_result.status == LicenseManager.ST_NO_LICENSE
        ),
        "unstarted_stale_policy_migrated_to_180": (
            migrated_conf["license"]["trial_policy"]["trial_days"]
            == EXPECTED_TRIAL_DAYS
        ),
        "day_179_trial_ok": result_179.status == LicenseManager.ST_TRIAL_OK,
        "day_180_trial_ok": result_180.status == LicenseManager.ST_TRIAL_OK,
        "day_181_trial_expired": (
            result_181.status == LicenseManager.ST_TRIAL_EXPIRED
        ),
        "started_old_policy_not_rewritten": (
            preserved_conf["license"]["trial_policy"]["trial_days"] == 90
        ),
        "trial_auto_still_blocked": (
            not result_179.caps.auto_demo and not result_179.caps.auto_full
        ),
        "trial_manual_still_allowed": result_179.caps.live_manual,
    }

    print("T110-09 — Trial Duration 180 Days")
    print()
    print(f"production_trial_days={TRIAL_DAYS}")
    print("migration_scope=UNSTARTED_FREE_ONLY")
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
        print("boundary=TRIAL_DURATION_180_NOT_CONFIRMED")
        print(f"TEST_ONLY={TEST_ONLY}")
        print(f"broker_requests={BROKER_REQUESTS}")
        print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
        print("T110-09=RED")
        return 1

    print("day_179=TRIAL_OK")
    print("day_180=TRIAL_OK")
    print("day_181=TRIAL_EXPIRED")
    print("unstarted_stale_90_policy=MIGRATED_TO_180")
    print("started_trial_policy=PRESERVED")
    print("trial_duration=180_DAYS")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    print("T110-09=GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
