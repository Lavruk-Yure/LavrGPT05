"""T109-32: anatomy of controller identity before Workspace submission."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_controller.py"
RUNTIME_ENGINE_PATH = PROJECT_ROOT / "engine" / "runtime_engine.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function not found: {name}")


def _call_result_assigned(function: ast.FunctionDef, call_name: str) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if isinstance(node.value.func, ast.Name):
            if node.value.func.id == call_name:
                return True
    return False


def main() -> None:
    controller_source = _source(CONTROLLER_PATH)
    runtime_engine_source = _source(RUNTIME_ENGINE_PATH)

    controller_method = _function_node(
        controller_source,
        "_persist_workspace_trade_after_risk_allow",
    )
    runtime_submit = _function_node(
        runtime_engine_source,
        "submit_workspace_execution_plan",
    )
    controller_text = ast.unparse(controller_method)

    runtime_submit_method_present = runtime_submit.name == (
        "submit_workspace_execution_plan"
    )
    controller_submit_call_present = (
        "submit_workspace_execution_plan" in controller_text
    )
    trade_uid_retained = _call_result_assigned(controller_method, "create_trade")
    new_order_plan_uid_retained = _call_result_assigned(
        controller_method,
        "create_order_plan",
    )
    existing_order_plan_uid_read = "order_plan_uid" in controller_text
    controller_returns_submission_identity = not isinstance(
        controller_method.returns,
        ast.Constant,
    )
    auto_ready_state_present = 'execution_state = "READY_FOR_SUBMISSION"' in (
        controller_source
    )
    semi_pending_state_present = 'execution_state = "PENDING_CONFIRMATION"' in (
        controller_source
    )
    runtime_reverse_gate_present = all(
        name in {arg.arg for arg in runtime_submit.args.kwonlyargs}
        for name in ("reverse_required", "confirmed_flat")
    )
    controller_reverse_gate_source_present = any(
        token in controller_text
        for token in (
            "reverse_required",
            "confirmed_flat",
            "get_active_broker_positions",
        )
    )

    assert runtime_submit_method_present
    assert not controller_submit_call_present
    assert trade_uid_retained
    assert not new_order_plan_uid_retained
    assert not existing_order_plan_uid_read
    assert not controller_returns_submission_identity
    assert auto_ready_state_present
    assert semi_pending_state_present
    assert runtime_reverse_gate_present
    assert not controller_reverse_gate_source_present

    print("T109-32_WORKSPACE_CONTROLLER_SUBMISSION_IDENTITY_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("runtime_submit_method_present=True")
    print("controller_submit_call_present=False")
    print("trade_uid_retained_in_controller=True")
    print("new_order_plan_uid_retained_in_controller=False")
    print("existing_order_plan_uid_read_in_controller=False")
    print("controller_returns_submission_identity=False")
    print("auto_ready_for_submission_state_present=True")
    print("semi_pending_confirmation_state_present=True")
    print("runtime_reverse_gate_present=True")
    print("controller_reverse_gate_source_present=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_CONTROLLER_ORDER_PLAN_IDENTITY_RETENTION"
    )
    print(
        "boundary_contract="
        "CONTROLLER_MUST_RETAIN_OR_RECOVER_EXACT_PERSISTED_ORDER_PLAN_UID_"
        "BEFORE_RUNTIME_SUBMISSION_CAN_BE_CALLED"
    )
    print(
        "factual_verdict=B. TRADE_UID_RETAINED_BUT_ORDER_PLAN_UID_NOT_RETAINED"
    )


if __name__ == "__main__":
    main()
