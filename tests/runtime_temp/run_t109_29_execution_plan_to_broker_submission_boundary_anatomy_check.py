"""T109-29: anatomy persisted Workspace execution plan -> broker submission.

TEST_ONLY: жодних broker calls і production-змін.
"""

from __future__ import annotations

import ast
from pathlib import Path

TEST_ID = "T109-29"
FACTUAL_VERDICT = "C. EXISTING_MANUAL_SUBMISSION_PATH_NOT_REUSABLE_AS_IS"
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_EXECUTION_PLAN_TO_IDENTITY_PRESERVING_BROKER_SUBMISSION"
)
BOUNDARY_CONTRACT = (
    "PERSISTED_WORKSPACE_TRADE_AND_ORDER_PLAN_MUST_BE_REUSED_WITHOUT_"
    "DUPLICATION_AND_WITH_BROKER_SPECIFIC_VOLUME_CONVERSION_BEFORE_SUBMISSION"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _function_source(source: str, function_name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    matches: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                matches.append(node)

    if not matches:
        raise AssertionError(f"Function not found: {function_name}")

    node = matches[-1]
    end_lineno = node.end_lineno or node.lineno
    return "\n".join(lines[node.lineno - 1 : end_lineno])  # noqa


def _class_method_source(
    source: str,
    class_name: str,
    method_name: str,
) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == method_name:
                    end_lineno = item.end_lineno or item.lineno
                    return "\n".join(lines[item.lineno - 1 : end_lineno])  # noqa

    raise AssertionError(f"Method not found: {class_name}.{method_name}")


def _method_argument_names(source: str, class_name: str, method_name: str) -> set[str]:
    tree = ast.parse(source)

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == method_name:
                    return {argument.arg for argument in item.args.args}

    raise AssertionError(f"Method not found: {class_name}.{method_name}")


def main() -> None:
    controller_source = _read("core/algorithm_workspace_controller.py")
    runtime_engine_source = _read("engine/runtime_engine.py")
    ib_service_source = _read("engine/services/ib_runtime_service.py")
    ctrader_service_source = _read("engine/services/ctrader_runtime_service.py")
    ib_adapter_source = _read("engine/ib_adapter.py")
    ctrader_adapter_source = _read("engine/ctrader_adapter.py")
    identity_source = _read("engine/broker_order_identity.py")
    risk_constants_source = _read("engine/risk/constants.py")

    persistence_source = _class_method_source(
        controller_source,
        "AlgorithmWorkspaceController",
        "_persist_workspace_trade_after_risk_allow",
    )
    manual_submit_source = _class_method_source(
        runtime_engine_source,
        "RuntimeEngine",
        "place_manual_market_order",
    )
    ib_manual_source = _class_method_source(
        runtime_engine_source,
        "RuntimeEngine",
        "_place_manual_market_order_ib",
    )
    ib_service_submit = _class_method_source(
        ib_service_source,
        "IBRuntimeService",
        "place_market_order",
    )
    ctrader_service_submit = _class_method_source(
        ctrader_service_source,
        "CTraderRuntimeService",
        "place_market_order",
    )
    ib_adapter_submit = _class_method_source(
        ib_adapter_source,
        "IBAdapter",
        "place_market_order",
    )
    ctrader_adapter_submit = _class_method_source(
        ctrader_adapter_source,
        "CTraderAdapter",
        "place_market_order",
    )

    assert 'source="WORKSPACE"' in persistence_source
    assert "create_order_plan(" in persistence_source
    assert "place_market_order(" not in persistence_source
    assert "place_manual_market_order(" not in persistence_source

    manual_path_creates_trade = "create_trade(" in manual_submit_source
    manual_path_delegates_ib = "_place_manual_market_order_ib(" in manual_submit_source
    assert manual_path_creates_trade or manual_path_delegates_ib
    assert "create_trade(" in ib_manual_source
    assert "create_order_plan(" in ib_manual_source
    assert "service.place_market_order(" in ib_manual_source
    assert "create_order_plan(" in manual_submit_source
    assert "service.place_market_order(" in manual_submit_source

    runtime_tree = ast.parse(runtime_engine_source)
    runtime_method_names = {
        item.name
        for node in runtime_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeEngine"
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    workspace_submit_methods = {
        name
        for name in runtime_method_names
        if "workspace" in name.lower()
        and any(token in name.lower() for token in ("submit", "order", "execute"))
    }
    assert not workspace_submit_methods

    ib_args = _method_argument_names(
        ib_service_source,
        "IBRuntimeService",
        "place_market_order",
    )
    ctrader_args = _method_argument_names(
        ctrader_service_source,
        "CTraderRuntimeService",
        "place_market_order",
    )
    assert "quantity" in ib_args
    assert "lots" in ctrader_args

    assert "quantity=quantity" in ib_service_submit
    assert "lots=lots" in ctrader_service_submit
    assert "quantity_float = float(quantity)" in ib_adapter_submit
    assert "lots_to_api_volume" in ctrader_adapter_submit

    assert 'WORKSPACE_VOLUME_UNIT_BASE_UNITS = "BASE_UNITS"' in risk_constants_source
    assert "_ib_lots_to_fx_quantity" in ib_manual_source
    assert "lots_float" in manual_submit_source

    assert "trade_uid" not in identity_source
    assert "orderRef = comment_clean" in ib_adapter_submit
    assert "request.label = build_ctrader_order_label" in ctrader_adapter_submit
    assert "request.comment = broker_comment" in ctrader_adapter_submit
    assert "clientOrderId" not in ctrader_adapter_submit

    auto_gate_present = (
        "control_mode == WORKSPACE_CONTROL_MODE_AUTO" in persistence_source
    )
    semi_gate_present = (
        "control_mode == WORKSPACE_CONTROL_MODE_SEMI" in persistence_source
    )
    assert auto_gate_present
    assert semi_gate_present
    assert 'execution_state = "READY_FOR_SUBMISSION"' in persistence_source
    assert 'execution_state = "PENDING_CONFIRMATION"' in persistence_source

    reverse_gate_present = any(
        token in persistence_source.lower()
        for token in ("confirmed_flat", "opposite_position", "reverse")
    )
    assert not reverse_gate_present

    print(f"{TEST_ID}_EXECUTION_PLAN_TO_BROKER_SUBMISSION_BOUNDARY_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("persisted_workspace_execution_plan_present=True")
    print("workspace_controller_broker_submission_wiring=False")
    print("runtime_engine_manual_submission_entrypoint_present=True")
    print("manual_path_creates_new_trade=True")
    print("manual_path_creates_new_order_plan=True")
    print("manual_path_reuses_persisted_workspace_trade=False")
    print("manual_path_reuses_persisted_workspace_order_plan=False")
    print("workspace_specific_runtime_submit_method_present=False")
    print("canonical_workspace_volume_unit=BASE_UNITS")
    print("ib_service_volume_contract=QUANTITY_BASE_UNITS_COMPATIBLE")
    print("ctrader_service_volume_contract=LOTS")
    print("ctrader_base_units_to_lots_conversion_required=True")
    print("broker_native_trade_uid_hint_present=False")
    print("ib_broker_hint_currently=CONTROL_MODE_COMMENT_ONLY")
    print("ctrader_broker_hint_currently=CONTROL_MODE_LABEL_COMMENT_ONLY")
    print("auto_ready_for_submission_state_present=True")
    print("semi_pending_confirmation_state_present=True")
    print("semi_confirmation_submission_gate_wired=False")
    print("reverse_confirmed_flat_gate_wired=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
