# -*- coding: utf-8 -*-
"""
T111-28 — Machine ID transient read anatomy — TEST_ONLY.

Доводить, чи може тимчасова невдача читання MachineGuid/SystemUUID
дати хибний OTHER_MACHINE для вже валідного machine_id.

Production не змінюється. Broker requests = 0.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import resources_rc  # noqa: F401, E402
from core.license_manager import LicenseManager  # noqa: E402

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False


def main() -> int:
    preferred, candidates = LicenseManager.compute_machine_id_candidates()

    with patch.object(
        LicenseManager,
        "_read_system_uuid",
        return_value=None,
    ):
        _, no_uuid_candidates = LicenseManager.compute_machine_id_candidates()

    with patch.object(
        LicenseManager,
        "_read_machine_guid",
        return_value=None,
    ):
        _, no_guid_candidates = LicenseManager.compute_machine_id_candidates()

    baseline_accepted = preferred in candidates
    uuid_failure_accepts_baseline = preferred in no_uuid_candidates
    guid_failure_accepts_baseline = preferred in no_guid_candidates

    print("T111-28 TEST_ONLY")
    print(f"baseline_preferred_accepted={baseline_accepted}")
    print(
        "system_uuid_read_failure_accepts_baseline="
        f"{uuid_failure_accepts_baseline}"
    )
    print(
        "machine_guid_read_failure_accepts_baseline="
        f"{guid_failure_accepts_baseline}"
    )

    vulnerable = (
        baseline_accepted
        and not uuid_failure_accepts_baseline
        and not guid_failure_accepts_baseline
    )
    verdict = (
        "TRANSIENT_MACHINE_ID_READ_CAN_FALSE_OTHER_MACHINE"
        if vulnerable
        else "TRANSIENT_MACHINE_ID_FALSE_MISMATCH_NOT_REPRODUCED"
    )

    print(f"verdict={verdict}")
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "broker_execution_attempted="
        f"{BROKER_EXECUTION_ATTEMPTED}"
    )
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
