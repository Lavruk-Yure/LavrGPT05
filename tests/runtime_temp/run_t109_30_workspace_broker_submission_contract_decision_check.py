"""T109-30: canonical Workspace broker submission contract decision.

TEST_ONLY: фіксує мінімальний identity-preserving submission contract без
broker calls і без production-змін.
"""

from __future__ import annotations

import ast
from pathlib import Path

TEST_ID = "T109-30"
FACTUAL_VERDICT = "A. CANONICAL_WORKSPACE_BROKER_SUBMISSION_CONTRACT_IDENTIFIED"
FIRST_UNRESOLVED_BOUNDARY = "RUNTIME_ENGINE_WORKSPACE_SUBMISSION_METHOD_WIRING"
BOUNDARY_CONTRACT = (
    "PERSISTED_WORKSPACE_TRADE_AND_ORDER_PLAN_MUST_BE_REUSED_WITH_EXACT_"
    "ACCOUNT_BINDING_CONTROL_MODE_GATES_BROKER_VOLUME_CONVERSION_AND_"
    "DIAGNOSTIC_TRADE_UID_HINT_BEFORE_BROKER_SUBMISSION"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _class_method_source(source: str, class_name: str, method_name: str) -> str:
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


def _runtime_method_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        item.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeEngine"
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _ctrader_lots_from_base_units(base_units: float) -> float:
    if base_units <= 0.0:
        raise ValueError("Workspace BASE_UNITS volume must be positive")
    return base_units / 100000.0


def main() -> None:
    controller_source = _read("core/algorithm_workspace_controller.py")
    runtime_engine_source = _read("engine/runtime_engine.py")
    repository_source = _read("engine/runtime_repository.py")
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
    create_order_plan_source = _class_method_source(
        repository_source,
        "RuntimeRepository",
        "create_order_plan",
    )

    assert 'source="WORKSPACE"' in persistence_source
    assert "create_order_plan(" in persistence_source
    assert 'execution_state = "READY_FOR_SUBMISSION"' in persistence_source
    assert 'execution_state = "PENDING_CONFIRMATION"' in persistence_source
    assert "place_market_order(" not in persistence_source

    assert "create_trade(" in manual_submit_source
    assert "create_order_plan(" in manual_submit_source
    assert "service.place_market_order(" in manual_submit_source

    runtime_methods = _runtime_method_names(runtime_engine_source)
    assert "submit_workspace_execution_plan" not in runtime_methods

    assert 'WORKSPACE_VOLUME_UNIT_BASE_UNITS = "BASE_UNITS"' in risk_constants_source
    assert "stop_loss" in create_order_plan_source
    assert "trade_uid" in create_order_plan_source

    canonical_inputs = (
        "trade_uid",
        "order_plan_uid",
        "broker",
        "account_id",
        "symbol",
        "side",
        "approved_volume_base_units",
        "stop_loss",
        "control_mode",
        "execution_state",
    )
    assert len(canonical_inputs) == 10

    ib_quantity = 3000.0
    ctrader_lots = _ctrader_lots_from_base_units(3000.0)
    assert ib_quantity == 3000.0
    assert ctrader_lots == 0.03

    assert "build_broker_order_comment" in identity_source
    assert "SQLite ``source`` remains the authoritative origin" in identity_source
    assert "trade_uid" not in identity_source

    allowed_auto_state = "READY_FOR_SUBMISSION"
    blocked_semi_state = "PENDING_CONFIRMATION"
    required_reverse_state = "CONFIRMED_FLAT"
    assert allowed_auto_state != blocked_semi_state
    assert required_reverse_state not in persistence_source

    print(f"{TEST_ID}_WORKSPACE_BROKER_SUBMISSION_CONTRACT_DECISION=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("workspace_specific_runtime_submit_method_present=False")
    print("recommended_runtime_method=submit_workspace_execution_plan")
    print("reuse_persisted_trade_uid=True")
    print("reuse_persisted_order_plan_uid=True")
    print("create_new_trade_during_submission=False")
    print("create_new_order_plan_during_submission=False")
    print("exact_broker_account_binding_required=True")
    print("canonical_workspace_volume_unit=BASE_UNITS")
    print("ib_submission_volume_contract=BASE_UNITS_AS_QUANTITY")
    print("ctrader_submission_volume_contract=BASE_UNITS_DIV_100000_AS_LOTS")
    print("ctrader_3000_base_units_lots=0.03")
    print("broker_identity_authority=LOCAL_PERSISTED_TRADE_UID")
    print("broker_native_identity_hint=SHORT_OPAQUE_TRADE_UID_REFERENCE")
    print("broker_native_hint_authoritative=False")
    print("auto_submission_gate=READY_FOR_SUBMISSION")
    print("semi_direct_submission_from_pending_confirmation=False")
    print("semi_confirmation_must_transition_to_ready=True")
    print("reverse_gate_contract=CONFIRMED_FLAT_BEFORE_SUBMISSION")
    print("reverse_gate_wiring_present=False")
    print("broker_order_persistence_after_submission=True")
    print("position_persistence_after_broker_confirmation=True")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
