from __future__ import annotations

from pathlib import Path


TEST_ID = "T109-46"
FACTUAL_VERDICT = "A. RUNTIME_EXECUTION_SAFETY_FRESHNESS_POLICY_CONTRACT_IDENTIFIED"
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_EXECUTION_SAFETY_FRESHNESS_POLICY_PRODUCTION_SOURCE"
)
BOUNDARY_CONTRACT = (
    "CONTROLLER_MUST_RECEIVE_BROKER_NEUTRAL_EXECUTION_SAFETY_POLICY_THAT_"
    "RESOLVES_POSITION_SNAPSHOT_MAX_AGE_FOR_EXACT_BROKER_BEFORE_CONFIRMED_"
    "FLAT_EVALUATION_CAN_GATE_AUTO_SUBMISSION"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROKER_MARKET = PROJECT_ROOT / "core" / "workspace_broker_market.py"
BROKER_POSITION = PROJECT_ROOT / "engine" / "broker_position.py"
CONTROLLER = PROJECT_ROOT / "core" / "algorithm_workspace_controller.py"
WORKSPACE_PARAMETERS = PROJECT_ROOT / "core" / "workspace_parameters.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    broker_market_source = _read(BROKER_MARKET)
    broker_position_source = _read(BROKER_POSITION)
    controller_source = _read(CONTROLLER)
    workspace_parameters_source = _read(WORKSPACE_PARAMETERS)

    existing_refresh_cadence_present = (
        "WORKSPACE_EXECUTION_SAFETY_REFRESH_SECONDS = 10.0"
        in broker_market_source
    )
    existing_refresh_cadence_is_ib_external_guard = all(
        token in broker_market_source
        for token in (
            'if binding.broker != "IB":',
            "refresh_ib_fx_external_exposure_guard",
            "WORKSPACE_EXECUTION_SAFETY_REFRESH_SECONDS",
        )
    )
    evaluator_requires_explicit_max_age = "max_age: timedelta" in broker_position_source
    evaluator_has_embedded_ttl = any(
        token in broker_position_source
        for token in (
            "POSITION_SNAPSHOT_MAX_AGE",
            "CONFIRMED_FLAT_MAX_AGE",
        )
    )
    controller_policy_source_present = any(
        token in controller_source
        for token in (
            "position_snapshot_max_age",
            "confirmed_flat_max_age",
            "execution_safety_policy",
        )
    )
    workspace_user_setting_present = any(
        token in workspace_parameters_source
        for token in (
            "position_snapshot_max_age",
            "confirmed_flat_max_age",
        )
    )

    assert existing_refresh_cadence_present
    assert existing_refresh_cadence_is_ib_external_guard
    assert evaluator_requires_explicit_max_age
    assert not evaluator_has_embedded_ttl
    assert not controller_policy_source_present
    assert not workspace_user_setting_present

    print(f"{TEST_ID}_RUNTIME_EXECUTION_SAFETY_FRESHNESS_POLICY_CONTRACT_DECISION=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print(
        "existing_execution_safety_refresh_seconds_present="
        f"{existing_refresh_cadence_present}"
    )
    print("existing_refresh_cadence_scope=IB_EXTERNAL_EXPOSURE_CACHE_ONLY")
    print(
        "existing_refresh_cadence_reusable_as_position_snapshot_freshness=False"
    )
    print(
        "production_evaluator_requires_explicit_max_age="
        f"{evaluator_requires_explicit_max_age}"
    )
    print(f"production_evaluator_has_embedded_ttl={evaluator_has_embedded_ttl}")
    print(f"controller_policy_source_present={controller_policy_source_present}")
    print(f"workspace_user_setting_present={workspace_user_setting_present}")
    print("recommended_policy_owner=RUNTIME_EXECUTION_SAFETY_POLICY")
    print("recommended_policy_scope=BROKER_NEUTRAL_RUNTIME_EXECUTION")
    print("recommended_policy_field=position_snapshot_max_age")
    print("recommended_policy_resolution=EXACT_BROKER_TO_MAX_AGE")
    print("missing_policy_behavior=BLOCK")
    print("recommended_workspace_user_setting=False")
    print("single_cross_broker_ttl_value_decided=False")
    print("broker_specific_ttl_values_decided=False")
    print("workspace_controller_submission_wiring=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
