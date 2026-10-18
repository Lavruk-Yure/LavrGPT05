# -*- coding: utf-8 -*-
"""T111-29 — transient machine identity guard — TEST_ONLY."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import resources_rc  # noqa: F401, E402
from core.license_manager import (  # noqa: E402
    LicenseManager,
    MachineIdentityUnavailableError,
)

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = True


def _mid(machine_guid: str, system_uuid: str) -> str:
    with (
        patch.object(
            LicenseManager,
            "_read_machine_guid",
            return_value=machine_guid,
        ),
        patch.object(
            LicenseManager,
            "_read_system_uuid",
            return_value=system_uuid,
        ),
    ):
        preferred, _candidates = LicenseManager.compute_machine_id_candidates()

    return preferred


def _conf(stored_mid: str) -> dict[str, object]:
    return {
        "license": {
            "edition": "pro",
            "machine_id": stored_mid,
        }
    }


def _raises_unavailable(
    stored_mid: str,
    *,
    machine_guid: str | None,
    system_uuid: str | None,
) -> bool:
    conf = _conf(stored_mid)
    try:
        with (
            patch.object(
                LicenseManager,
                "_read_machine_guid",
                return_value=machine_guid,
            ),
            patch.object(
                LicenseManager,
                "_read_system_uuid",
                return_value=system_uuid,
            ),
        ):
            LicenseManager.compute_and_update(conf)
    except MachineIdentityUnavailableError:
        return True
    return False


def main() -> int:
    baseline_guid = "GUID-A"
    baseline_uuid = "UUID-A"
    stored_mid = _mid(baseline_guid, baseline_uuid)

    uuid_failure_guarded = _raises_unavailable(
        stored_mid,
        machine_guid=baseline_guid,
        system_uuid=None,
    )
    guid_failure_guarded = _raises_unavailable(
        stored_mid,
        machine_guid=None,
        system_uuid=baseline_uuid,
    )

    other_machine_conf = _conf(stored_mid)
    with (
        patch.object(
            LicenseManager,
            "_read_machine_guid",
            return_value="GUID-B",
        ),
        patch.object(
            LicenseManager,
            "_read_system_uuid",
            return_value="UUID-B",
        ),
    ):
        other_machine_result = LicenseManager.compute_and_update(
            deepcopy(other_machine_conf)
        )

    login_source = (PROJECT_ROOT / "core/login_logic.py").read_text(encoding="utf-8")
    policy_source = (PROJECT_ROOT / "core/translation_policy.py").read_text(
        encoding="utf-8"
    )

    login_has_guard = "except MachineIdentityUnavailableError:" in login_source
    user_message_present = (
        "LoginWindow.errorMachineIdentityUnavailable" in policy_source
    )
    true_other_machine_preserved = (
        other_machine_result.status == LicenseManager.ST_OTHER_MACHINE
    )

    print("T111-29 TEST_ONLY")
    print(f"system_uuid_failure_guarded={uuid_failure_guarded}")
    print(f"machine_guid_failure_guarded={guid_failure_guarded}")
    print(f"true_other_machine_preserved={true_other_machine_preserved}")
    print(f"login_has_retry_guard={login_has_guard}")
    print(f"user_message_present={user_message_present}")

    green = all(
        (
            uuid_failure_guarded,
            guid_failure_guarded,
            true_other_machine_preserved,
            login_has_guard,
            user_message_present,
        )
    )
    verdict = (
        "TRANSIENT_MACHINE_ID_FALSE_MISMATCH_GUARDED"
        if green
        else "TRANSIENT_MACHINE_ID_GUARD_INCOMPLETE"
    )
    print(f"verdict={verdict}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("broker_execution_attempted=" f"{BROKER_EXECUTION_ATTEMPTED}")
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
