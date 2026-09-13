from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

TEST_ID = "T109-43"
FACTUAL_VERDICT = (
    "C. CONTROLLER_HAS_EVALUATOR_BUT_EXACT_WORKSPACE_SNAPSHOT_SOURCE_IS_MISSING"
)
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_NAMED_BROKER_ACCOUNT_POSITION_SNAPSHOT_ROUTING"
)
BOUNDARY_CONTRACT = (
    "CONTROLLER_MUST_OBTAIN_POSITION_SNAPSHOT_FOR_EXACT_WORKSPACE_BROKER_ACCOUNT_"
    "BEFORE_FRESHNESS_EVALUATION_AND_AUTO_SUBMISSION_GATE_CAN_RUN"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

controller_module = importlib.import_module("core.algorithm_workspace_controller")
broker_position_module = importlib.import_module("engine.broker_position")
runtime_engine_module = importlib.import_module("engine.runtime_engine")

AlgorithmWorkspaceController = controller_module.AlgorithmWorkspaceController
broker_position_snapshot_confirms_flat = (
    broker_position_module.broker_position_snapshot_confirms_flat
)
RuntimeEngine = runtime_engine_module.RuntimeEngine


def main() -> None:
    controller_source = inspect.getsource(AlgorithmWorkspaceController)
    engine_source = inspect.getsource(RuntimeEngine)
    evaluator_source = inspect.getsource(broker_position_snapshot_confirms_flat)

    runtime_snapshot_api_present = (
        "def get_active_broker_positions_snapshot(" in engine_source
    )
    runtime_named_snapshot_api_present = (
        "def get_workspace_broker_positions_snapshot(" in engine_source
        or "def get_broker_positions_snapshot(" in engine_source
    )
    runtime_submit_method_present = (
        "def submit_workspace_execution_plan(" in engine_source
    )
    controller_submit_call_present = (
        ".submit_workspace_execution_plan(" in controller_source
    )
    controller_evaluator_call_present = (
        "broker_position_snapshot_confirms_flat(" in controller_source
    )
    controller_runtime_engine_present = "self._runtime_engine" in controller_source
    retained_identity_present = (
        "_workspace_submission_identity_for_signal" in controller_source
    )
    exact_record_scope_present = all(
        token in controller_source
        for token in (
            "record.broker",
            "record.account_id",
            "record.symbol",
        )
    )
    evaluator_requires_freshness_parameter = "max_age:" in evaluator_source
    controller_freshness_policy_source_present = (
        "confirmed_flat_max_age" in controller_source
        or "position_snapshot_max_age" in controller_source
        or "snapshot_freshness" in controller_source
    )
    active_snapshot_is_active_broker_scoped = (
        "broker = self.get_active_broker()" in inspect.getsource(
            RuntimeEngine.get_active_broker_positions_snapshot
        )
    )

    assert runtime_snapshot_api_present
    assert runtime_submit_method_present
    assert controller_runtime_engine_present
    assert retained_identity_present
    assert exact_record_scope_present
    assert evaluator_requires_freshness_parameter
    assert active_snapshot_is_active_broker_scoped
    assert not runtime_named_snapshot_api_present
    assert not controller_submit_call_present
    assert not controller_evaluator_call_present
    assert not controller_freshness_policy_source_present

    print(
        f"{TEST_ID}_WORKSPACE_CONTROLLER_CONFIRMED_FLAT_SOURCE_"
        "AUTO_SUBMISSION_GATE_ANATOMY=OK"
    )
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("runtime_snapshot_api_present=True")
    print("runtime_snapshot_api_scope=ACTIVE_BROKER_ONLY")
    print("runtime_named_workspace_snapshot_api_present=False")
    print("runtime_submit_method_present=True")
    print("controller_runtime_engine_present=True")
    print("controller_retained_trade_order_plan_identity_present=True")
    print("controller_exact_record_broker_account_symbol_scope_present=True")
    print("production_confirmed_flat_evaluator_present=True")
    print("production_evaluator_requires_freshness_parameter=True")
    print("controller_freshness_policy_source_present=False")
    print("controller_evaluator_call_present=False")
    print("controller_submit_call_present=False")
    print("active_broker_snapshot_cannot_guarantee_workspace_named_broker=True")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
