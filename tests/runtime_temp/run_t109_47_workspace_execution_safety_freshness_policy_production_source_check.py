"""T109-47: production source runtime execution safety freshness policy."""

from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

policy_module = importlib.import_module("engine.runtime_execution_safety_policy")
runtime_engine_module = importlib.import_module("engine.runtime_engine")

RuntimeExecutionSafetyPolicy = policy_module.RuntimeExecutionSafetyPolicy
RuntimeEngine = runtime_engine_module.RuntimeEngine


def main() -> None:
    """Перевірити production source без broker requests."""

    default_policy = RuntimeExecutionSafetyPolicy()
    ib_test_age = timedelta(seconds=7)
    ctrader_test_age = timedelta(seconds=11)
    configured_policy = RuntimeExecutionSafetyPolicy(
        position_snapshot_max_age_by_broker={
            "ib": ib_test_age,
            "ctrader": ctrader_test_age,
            "unknown": timedelta(0),
        }
    )

    engine = RuntimeEngine(
        db_path=":memory:",
        execution_safety_policy=configured_policy,
    )
    try:
        default_missing_blocks = (
            default_policy.resolve_position_snapshot_max_age("IB") is None
        )
        ib_exact_resolution = (
            engine.get_workspace_position_snapshot_max_age("IB") == ib_test_age
        )
        ctrader_exact_resolution = (
            engine.get_workspace_position_snapshot_max_age("ctrader")
            == ctrader_test_age
        )
        unknown_broker_blocks = (
            engine.get_workspace_position_snapshot_max_age("OTHER") is None
        )
        non_positive_policy_blocks = (
            engine.get_workspace_position_snapshot_max_age("UNKNOWN") is None
        )
        normalized_broker_lookup = (
            engine.get_workspace_position_snapshot_max_age("  ib  ")
            == ib_test_age
        )

        assert default_missing_blocks
        assert ib_exact_resolution
        assert ctrader_exact_resolution
        assert unknown_broker_blocks
        assert non_positive_policy_blocks
        assert normalized_broker_lookup

        print("T109-47_WORKSPACE_EXECUTION_SAFETY_FRESHNESS_POLICY_SOURCE=OK")
        print("production_change=True")
        print("runtime_execution_safety_policy_present=True")
        print("runtime_engine_policy_source_present=True")
        print("exact_broker_resolution_present=True")
        print(f"default_missing_policy_blocks={default_missing_blocks}")
        print(f"ib_exact_resolution={ib_exact_resolution}")
        print(f"ctrader_exact_resolution={ctrader_exact_resolution}")
        print(f"unknown_broker_blocks={unknown_broker_blocks}")
        print(f"non_positive_policy_blocks={non_positive_policy_blocks}")
        print(f"normalized_broker_lookup={normalized_broker_lookup}")
        print("workspace_user_setting=False")
        print("production_ttl_values_decided=False")
        print("workspace_controller_submission_wiring=False")
        print("broker_requests=0")
        print(
            "first_unresolved_boundary="
            "WORKSPACE_CONTROLLER_CONFIRMED_FLAT_POLICY_TO_AUTO_SUBMISSION_GATE"
        )
        print(
            "boundary_contract=CONTROLLER_MUST_RESOLVE_EXACT_BROKER_"
            "POSITION_SNAPSHOT_MAX_AGE_FROM_RUNTIME_EXECUTION_SAFETY_POLICY_"
            "BEFORE_CONFIRMED_FLAT_CAN_GATE_AUTO_SUBMISSION"
        )
        print(
            "factual_verdict=A. WORKSPACE_EXECUTION_SAFETY_FRESHNESS_"
            "POLICY_PRODUCTION_SOURCE_GREEN"
        )
    finally:
        engine.connection.close()


if __name__ == "__main__":
    main()
