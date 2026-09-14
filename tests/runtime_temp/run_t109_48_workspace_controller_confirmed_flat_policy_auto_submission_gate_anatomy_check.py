"""T109-48 — anatomy confirmed-flat policy -> AUTO submission gate."""

from __future__ import annotations

import importlib
import inspect
import sys
from datetime import timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

controller_module = importlib.import_module("core.algorithm_workspace_controller")
broker_position_module = importlib.import_module("engine.broker_position")
runtime_engine_module = importlib.import_module("engine.runtime_engine")
policy_module = importlib.import_module("engine.runtime_execution_safety_policy")

AlgorithmWorkspaceController = controller_module.AlgorithmWorkspaceController
RuntimeEngine = runtime_engine_module.RuntimeEngine
RuntimeExecutionSafetyPolicy = policy_module.RuntimeExecutionSafetyPolicy


def main() -> None:
    """Перевірити factual readiness controller-side AUTO gate без submit."""

    controller_source = inspect.getsource(AlgorithmWorkspaceController)
    runtime_source = inspect.getsource(RuntimeEngine)
    evaluator_source = inspect.getsource(
        broker_position_module.broker_position_snapshot_confirms_flat
    )

    runtime_named_snapshot_api_present = (
        "def get_workspace_broker_positions_snapshot(" in runtime_source
    )
    runtime_policy_resolution_api_present = (
        "def get_workspace_position_snapshot_max_age(" in runtime_source
    )
    production_confirmed_flat_evaluator_present = (
        "def broker_position_snapshot_confirms_flat(" in evaluator_source
    )
    controller_retained_identity_present = (
        "def _workspace_submission_identity_for_signal(" in controller_source
    )
    controller_exact_record_scope_present = all(
        token in controller_source
        for token in ("record.broker", "record.account_id", "record.symbol")
    )

    controller_named_snapshot_call_present = (
        "get_workspace_broker_positions_snapshot(" in controller_source
    )
    controller_policy_resolution_call_present = (
        "get_workspace_position_snapshot_max_age(" in controller_source
    )
    controller_evaluator_call_present = (
        "broker_position_snapshot_confirms_flat(" in controller_source
    )
    controller_submit_call_present = (
        "submit_workspace_execution_plan(" in controller_source
    )

    default_policy = RuntimeExecutionSafetyPolicy()
    default_ib_max_age = default_policy.resolve_position_snapshot_max_age("IB")
    default_ctrader_max_age = default_policy.resolve_position_snapshot_max_age(
        "CTRADER"
    )
    production_policy_values_configured_by_default = (
        default_ib_max_age is not None or default_ctrader_max_age is not None
    )

    explicit_policy = RuntimeExecutionSafetyPolicy(
        position_snapshot_max_age_by_broker={
            "IB": timedelta(seconds=3),
            "CTRADER": timedelta(seconds=4),
        }
    )
    explicit_ib_resolution_works = (
        explicit_policy.resolve_position_snapshot_max_age("IB")
        == timedelta(seconds=3)
    )
    explicit_ctrader_resolution_works = (
        explicit_policy.resolve_position_snapshot_max_age("CTRADER")
        == timedelta(seconds=4)
    )

    assert runtime_named_snapshot_api_present
    assert runtime_policy_resolution_api_present
    assert production_confirmed_flat_evaluator_present
    assert controller_retained_identity_present
    assert controller_exact_record_scope_present
    assert not controller_named_snapshot_call_present
    assert not controller_policy_resolution_call_present
    assert not controller_evaluator_call_present
    assert not controller_submit_call_present
    assert not production_policy_values_configured_by_default
    assert explicit_ib_resolution_works
    assert explicit_ctrader_resolution_works

    print(
        "T109-48_WORKSPACE_CONTROLLER_CONFIRMED_FLAT_POLICY_AUTO_"
        "SUBMISSION_GATE_ANATOMY=OK"
    )
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("runtime_named_snapshot_api_present=True")
    print("runtime_policy_resolution_api_present=True")
    print("production_confirmed_flat_evaluator_present=True")
    print("controller_retained_identity_present=True")
    print("controller_exact_record_scope_present=True")
    print("controller_named_snapshot_call_present=False")
    print("controller_policy_resolution_call_present=False")
    print("controller_evaluator_call_present=False")
    print("controller_submit_call_present=False")
    print("production_policy_values_configured_by_default=False")
    print("explicit_ib_policy_resolution_works=True")
    print("explicit_ctrader_policy_resolution_works=True")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_POSITION_SNAPSHOT_MAX_AGE_PRODUCTION_VALUES"
    )
    print(
        "boundary_contract=CONTROLLER_AUTO_GATE_REQUIRES_EXPLICIT_PRODUCTION_"
        "MAX_AGE_FOR_EXACT_BROKER_BEFORE_FRESHNESS_EVALUATION_AND_SUBMISSION"
    )
    print(
        "factual_verdict=C. POLICY_SOURCE_EXISTS_BUT_PRODUCTION_MAX_AGE_"
        "VALUES_ARE_UNRESOLVED"
    )


if __name__ == "__main__":
    main()
