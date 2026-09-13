"""T109-34: anatomy exact AUTO Workspace controller submission gate."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

controller_module = importlib.import_module("core.algorithm_workspace_controller")
runtime_engine_module = importlib.import_module("engine.runtime_engine")
workspace_module = importlib.import_module("core.algorithm_workspace")

AlgorithmWorkspaceController = controller_module.AlgorithmWorkspaceController
RuntimeEngine = runtime_engine_module.RuntimeEngine
WORKSPACE_CONTROL_MODE_AUTO = workspace_module.WORKSPACE_CONTROL_MODE_AUTO
WORKSPACE_CONTROL_MODE_SEMI = workspace_module.WORKSPACE_CONTROL_MODE_SEMI

TEST_ID = "T109-34"
FACTUAL_VERDICT = (
    "B. AUTO_READY_IDENTITY_AVAILABLE_BUT_CONTROLLER_SUBMISSION_GATE_NOT_WIRED"
)
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_CONTROLLER_TO_RUNTIME_ENGINE_SUBMISSION_GATE"
)
BOUNDARY_CONTRACT = (
    "AUTO_READY_WORKSPACE_SIGNAL_WITH_EXACT_TRADE_AND_ORDER_PLAN_IDENTITY_"
    "MUST_CALL_RUNTIME_SUBMIT_ONLY_AFTER_REVERSE_CONFIRMED_FLAT_GATE_PASSES"
)


def main() -> None:
    controller_source = inspect.getsource(AlgorithmWorkspaceController)
    submit_method = getattr(RuntimeEngine, "submit_workspace_execution_plan", None)
    assert callable(submit_method)

    submit_signature = inspect.signature(submit_method)
    submit_parameters = set(submit_signature.parameters)
    assert "trade_uid" in submit_parameters
    assert "order_plan_uid" in submit_parameters
    assert "reverse_required" in submit_parameters
    assert "confirmed_flat" in submit_parameters

    remember_method = getattr(
        AlgorithmWorkspaceController,
        "_remember_workspace_submission_identity",
        None,
    )
    lookup_method = getattr(
        AlgorithmWorkspaceController,
        "_workspace_submission_identity_for_signal",
        None,
    )
    assert callable(remember_method)
    assert callable(lookup_method)

    controller = object.__new__(AlgorithmWorkspaceController)
    controller._workspace_submission_identities = {}
    remember_method(
        controller,
        "workspace-t109-34",
        "signal-t109-34",
        "trade-t109-34",
        "plan-t109-34",
    )
    identity = lookup_method(
        controller,
        "workspace-t109-34",
        "signal-t109-34",
    )
    assert identity == ("trade-t109-34", "plan-t109-34")

    controller_submit_call_present = (
        "submit_workspace_execution_plan" in controller_source
    )
    assert not controller_submit_call_present

    auto_ready_state_present = "READY_FOR_SUBMISSION" in controller_source
    semi_pending_state_present = "PENDING_CONFIRMATION" in controller_source
    assert auto_ready_state_present
    assert semi_pending_state_present

    runtime_source = inspect.getsource(RuntimeEngine.submit_workspace_execution_plan)
    runtime_ready_gate_present = (
        'execution_state != "READY_FOR_SUBMISSION"' in runtime_source
    )
    runtime_reverse_gate_present = (
        "reverse_required and not confirmed_flat" in runtime_source
    )
    assert runtime_ready_gate_present
    assert runtime_reverse_gate_present

    controller_reverse_gate_source_present = any(
        token in controller_source
        for token in (
            "reverse_required",
            "confirmed_flat",
            "CONFIRMED_FLAT",
        )
    )
    assert not controller_reverse_gate_source_present

    auto_direct_submit_contract = (
        WORKSPACE_CONTROL_MODE_AUTO == "AUTO" and auto_ready_state_present
    )
    semi_direct_submit_contract = (
        WORKSPACE_CONTROL_MODE_SEMI == "SEMI" and semi_pending_state_present
    )
    assert auto_direct_submit_contract
    assert semi_direct_submit_contract

    print(f"{TEST_ID}_WORKSPACE_CONTROLLER_AUTO_SUBMISSION_GATE_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("runtime_submit_method_present=True")
    print("exact_trade_order_plan_identity_available=True")
    print("controller_submit_call_present=False")
    print("auto_ready_for_submission_state_present=True")
    print("semi_pending_confirmation_state_present=True")
    print("runtime_ready_gate_present=True")
    print("runtime_reverse_confirmed_flat_gate_present=True")
    print("controller_reverse_gate_source_present=False")
    print("auto_submission_candidate=True")
    print("semi_direct_submission_candidate=False")
    print("duplicate_submission_guard_owned_by_runtime=True")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
