from __future__ import annotations

from pathlib import Path


TEST_ID = "T109-45"
FACTUAL_VERDICT = "B. NO_EXISTING_CONTROLLER_FRESHNESS_POLICY_SOURCE"
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_EXECUTION_POSITION_SNAPSHOT_FRESHNESS_POLICY_CONTRACT"
)
BOUNDARY_CONTRACT = (
    "CONTROLLER_MUST_RECEIVE_AN_EXPLICIT_EXECUTION_SAFETY_FRESHNESS_POLICY_"
    "BEFORE_CONFIRMED_FLAT_EVALUATION_CAN_GATE_AUTO_SUBMISSION"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = PROJECT_ROOT / "core" / "algorithm_workspace_controller.py"
WORKSPACE_PARAMETERS = PROJECT_ROOT / "core" / "workspace_parameters.py"
RUNTIME_CONSTANTS = PROJECT_ROOT / "engine" / "runtime_constants.py"
BROKER_POSITION = PROJECT_ROOT / "engine" / "broker_position.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    controller_source = _read(CONTROLLER)
    workspace_parameters_source = _read(WORKSPACE_PARAMETERS)
    runtime_constants_source = _read(RUNTIME_CONSTANTS)
    broker_position_source = _read(BROKER_POSITION)

    controller_freshness_source_present = any(
        token in controller_source
        for token in (
            "freshness_max_age",
            "position_snapshot_max_age",
            "confirmed_flat_max_age",
        )
    )
    workspace_freshness_setting_present = any(
        token in workspace_parameters_source
        for token in (
            "freshness_max_age",
            "position_snapshot_max_age",
            "confirmed_flat_max_age",
        )
    )
    runtime_freshness_policy_constant_present = any(
        token in runtime_constants_source
        for token in (
            "WORKSPACE_POSITION_SNAPSHOT_MAX_AGE",
            "WORKSPACE_CONFIRMED_FLAT_MAX_AGE",
        )
    )
    broker_request_timeout_constants_present = all(
        token in runtime_constants_source
        for token in (
            "IB_POSITIONS_TIMEOUT_SECONDS",
            "CTRADER_POSITIONS_TIMEOUT_SECONDS",
        )
    )
    evaluator_requires_max_age = "max_age: timedelta" in broker_position_source
    evaluator_policy_is_parameterized = (
        "policy передається параметром" in broker_position_source
    )

    assert not controller_freshness_source_present
    assert not workspace_freshness_setting_present
    assert not runtime_freshness_policy_constant_present
    assert broker_request_timeout_constants_present
    assert evaluator_requires_max_age
    assert evaluator_policy_is_parameterized

    print(f"{TEST_ID}_WORKSPACE_CONTROLLER_FRESHNESS_POLICY_SOURCE_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print(
        "controller_freshness_policy_source_present="
        f"{controller_freshness_source_present}"
    )
    print(
        "workspace_freshness_setting_present="
        f"{workspace_freshness_setting_present}"
    )
    print(
        "runtime_freshness_policy_constant_present="
        f"{runtime_freshness_policy_constant_present}"
    )
    print(
        "broker_request_timeout_constants_present="
        f"{broker_request_timeout_constants_present}"
    )
    print("broker_request_timeouts_are_freshness_policy=False")
    print(f"production_evaluator_requires_max_age={evaluator_requires_max_age}")
    print(
        "production_evaluator_policy_is_parameterized="
        f"{evaluator_policy_is_parameterized}"
    )
    print("recommended_policy_owner=RUNTIME_EXECUTION_SAFETY_POLICY")
    print("recommended_workspace_user_setting=False")
    print("production_freshness_ttl_value_decided=False")
    print("workspace_controller_submission_wiring=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
