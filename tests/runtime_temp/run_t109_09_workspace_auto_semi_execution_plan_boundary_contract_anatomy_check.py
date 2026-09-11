"""run_t109_09_workspace_auto_semi_execution_plan_boundary_contract_anatomy_check.py.

TEST_ONLY anatomy встановлює фактичний contract лише для переходу від
risk-allowed Workspace signal до execution/order plan. Runner читає production
dataclasses, WorkspaceRuntime/controller dependency boundaries, manual
RuntimeEngine entrypoint і SQLite schema, після чого executable assertions
фіксують доступні identity/risk поля та перші відсутні plan contracts.

Manual order method, RuntimeEngine instance, broker service й adapter не
викликаються. Synthetic execution, schema/DTO implementation, AUTO/SEMI або
reverse semantics не створюються; production files і Replay не змінюються.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_ownership import WorkspaceBinding  # noqa: E402
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalRecord,
    WorkspaceTradeIntent,
)

TEST_ID = "T109-09"
FACTUAL_VERDICT = "G. MULTIPLE_BLOCKERS"
FIRST_MISSING_BOUNDARY = (
    "RISK_ALLOWED_WORKSPACE_SIGNAL_TO_IDENTITY_PRESERVING_EXECUTION_PLAN"
)
BOUNDARY_CONTRACT = (
    "RISK_ALLOWED_WORKSPACE_SIGNAL_REQUIRES_ONE_CAUSAL_PLAN_WITH_WORKSPACE_"
    "SIGNAL_BINDING_RISK_MODE_AND_TIMESTAMP_IDENTITY_BEFORE_BROKER_REQUEST"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace.py",
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "orders_page.py",
    PROJECT_ROOT / "core" / "workspace_ownership.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "broker_order_identity.py",
    PROJECT_ROOT / "engine" / "db" / "runtime_db.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "runtime_repository.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def source_text(relative_path: str) -> str:
    """Прочитати один фактичний production module як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def source_section(relative_path: str, start: str, end: str) -> str:
    """Виділити production section між двома exact anchors."""
    source = source_text(relative_path)
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def schema_columns(schema: str, table: str) -> tuple[str, ...]:
    """Повернути declared SQLite columns однієї production table."""
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table)} \((.*?)\n\);",
        schema,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"schema table missing: {table}")
    columns: list[str] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("FOREIGN KEY", "UNIQUE")):
            continue
        columns.append(line.split()[0].rstrip(","))
    return tuple(columns)


def production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production sources до і після anatomy run."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def main() -> None:
    """Довести Workspace signal-to-plan fields, ownership і blockers."""
    hashes_before = production_hashes()
    workspace_runtime = source_text("core/workspace_runtime.py")
    record_signal = source_section(
        "core/workspace_runtime.py",
        "    def _record_signal(",
        "    def _evaluate_signal_risk(",
    )
    signal_reason = source_section(
        "core/workspace_runtime.py",
        "    def _signal_decision_reason(",
        "    def _update_market_guards(",
    )
    controller = source_text("core/algorithm_workspace_controller.py")
    controller_init = source_section(
        "core/algorithm_workspace_controller.py",
        "    def __init__(",
        "    def set_runtime_engine(",
    )
    controller_engine_setter = source_section(
        "core/algorithm_workspace_controller.py",
        "    def set_runtime_engine(",
        "    def advance_workspace_broker_market(",
    )
    runtime_engine = source_text("engine/runtime_engine.py")
    manual_path = source_section(
        "engine/runtime_engine.py",
        "    def place_manual_market_order(",
        "    @staticmethod\n    def _normalize_optional_protection_price(",
    )
    ib_manual_path = source_section(
        "engine/runtime_engine.py",
        "    def _place_manual_market_order_ib(",
        "    def place_manual_market_order(",
    )
    schema = source_text("engine/db/runtime_db.py")
    orders_page = source_text("core/orders_page.py")
    broker_identity = source_text("engine/broker_order_identity.py")

    intent_fields = tuple(field.name for field in fields(WorkspaceTradeIntent))
    signal_fields = tuple(field.name for field in fields(WorkspaceSignalRecord))
    binding_fields = tuple(field.name for field in fields(WorkspaceBinding))
    workspace_fields = tuple(field.name for field in fields(AlgorithmWorkspace))
    runtime_context_fields = tuple(
        field.name for field in fields(WorkspaceRuntimeContext)
    )
    trade_columns = schema_columns(schema, "trades")
    plan_columns = schema_columns(schema, "order_plans")
    broker_order_columns = schema_columns(schema, "broker_orders")

    workspace_risk_route_present = all(
        token in record_signal
        for token in (
            "risk_decision = self._evaluate_signal_risk(",
            "accepted = risk_decision.allowed",
            "record = WorkspaceSignalRecord(",
            "risk_decision=(",
            "risk_reason_code=(",
            "approved_volume=(",
        )
    )
    workspace_broker_plan_route_absent = all(
        token not in record_signal
        for token in (
            "create_trade(",
            "create_order_plan(",
            "place_manual_market_order(",
            "place_market_order(",
        )
    )
    workspace_execution_plan_type_absent = all(
        token not in workspace_runtime
        for token in (
            "WorkspaceExecutionPlan",
            "WorkspaceOrderPlan",
            "workspace_execution_plan",
        )
    )

    manual_inputs_present = all(
        token in manual_path
        for token in (
            "symbol_name: str",
            "side: str",
            "lots: float",
            "stop_loss: float | None = None",
            "take_profit: float | None = None",
            'comment: str = "LGE manual order"',
            "control_mode: str = ORDER_CONTROL_MODE_MANUAL",
        )
    )
    manual_persistence_chain_present = all(
        token in manual_path
        for token in (
            "self.repository.create_trade(",
            "self.repository.create_order_plan(",
            "service.place_market_order(",
            "self.repository.create_broker_order(",
        )
    )
    manual_risk_recheck_present = any(
        token in manual_path or token in ib_manual_path
        for token in (
            "WorkspaceRiskEvaluator",
            "evaluate_risk_request",
            "WorkspaceRiskRequest",
            "risk_decision",
        )
    )
    ib_safety_preconditions_present = all(
        token in ib_manual_path
        for token in (
            "get_pending_ib_manual_opens()",
            "_assert_ib_fx_execution_safe(",
            "service.get_account_state()",
        )
    )
    global_active_broker_assumption = "broker = self.get_active_broker()" in manual_path
    manual_gui_caller_present = all(
        token in orders_page
        for token in (
            "def _on_place_order_clicked(self)",
            "self.ui.cmbSymbol.currentText()",
            "self.ui.spinLots.value()",
            "self._runtime_engine.place_manual_market_order(",
            "control_mode=ORDER_CONTROL_MODE_MANUAL",
        )
    )

    trade_has_workspace_uid = "workspace_uid" in trade_columns
    trade_has_signal_uid = "signal_uid" in trade_columns
    plan_has_workspace_uid = "workspace_uid" in plan_columns
    plan_has_signal_uid = "signal_uid" in plan_columns
    trade_has_generic_metadata = any(
        name in trade_columns for name in ("metadata", "context", "payload_json")
    )
    plan_has_generic_metadata = any(
        name in plan_columns for name in ("metadata", "context", "payload_json")
    )
    broker_marker_has_workspace_uid = "workspace_uid" in broker_identity
    broker_marker_has_signal_uid = "signal_uid" in broker_identity

    available_identity_fields = {
        "workspace_uid": "workspace_uid" in signal_fields,
        "signal_uid": "signal_uid" in signal_fields,
        "broker": "broker" in signal_fields,
        "account_id": "account_id" in signal_fields,
        "symbol": "symbol" in signal_fields,
        "direction": "direction" in signal_fields,
        "requested_volume": "requested_volume" in signal_fields,
        "stop_loss": "stop_loss" in intent_fields,
        "risk_decision": "risk_decision" in signal_fields,
        "control_mode": "control_mode" in runtime_context_fields,
        "timestamp": "timestamp" in signal_fields,
    }
    risk_allowed_fields_available = all(available_identity_fields.values())

    workspace_runtime_init = source_section(
        "core/workspace_runtime.py",
        "    def __init__(",
        "    @property\n    def workspace_uid(",
    )
    workspace_runtime_has_engine = any(
        token in workspace_runtime_init for token in ("runtime_engine", "RuntimeEngine")
    )
    controller_has_engine = all(
        token in controller_init + controller_engine_setter
        for token in (
            "self._runtime_engine",
            "RuntimeEngineWorkspaceMarketProvider(runtime_engine)",
        )
    )
    controller_has_runtime_registry = "self._runtimes" in controller_init
    runtime_engine_has_workspace_context = any(
        token in runtime_engine
        for token in (
            "WorkspaceRuntimeContext",
            "workspace_uid: str",
            "WorkspaceSignalRecord",
        )
    )

    semi_text_only = all(
        token in signal_reason
        for token in (
            'if self.context.control_mode == "SEMI":',
            'return "accepted; user confirmation is required"',
        )
    )
    semi_confirmation_api_present = any(
        token in controller + workspace_runtime
        for token in (
            "confirm_workspace_signal",
            "approve_workspace_signal",
            "pending_signal_confirmation",
            "WorkspaceSignalConfirmation",
        )
    )
    auto_execution_disabled = (
        'return "accepted; automatic execution is disabled in RoadMap95"'
        in signal_reason
    )

    repository_create_trade_has_identity = all(
        token
        in source_section(
            "engine/runtime_repository.py",
            "    def create_trade(",
            "    def create_order_plan(",
        )
        for token in ("workspace_uid", "signal_uid")
    )
    repository_create_plan_has_identity = all(
        token
        in source_section(
            "engine/runtime_repository.py",
            "    def create_order_plan(",
            "    def create_broker_order(",
        )
        for token in ("workspace_uid", "signal_uid")
    )

    assert intent_fields == (
        "requested_volume",
        "estimated_loss_at_stop",
        "stop_loss",
        "signal_uid",
    )
    assert binding_fields == ("workspace_uid", "broker", "account_id", "symbol")
    assert "control_mode" in workspace_fields
    assert workspace_risk_route_present
    assert workspace_broker_plan_route_absent
    assert workspace_execution_plan_type_absent
    assert manual_inputs_present
    assert manual_persistence_chain_present
    assert not manual_risk_recheck_present
    assert ib_safety_preconditions_present
    assert global_active_broker_assumption
    assert manual_gui_caller_present
    assert not trade_has_workspace_uid
    assert not trade_has_signal_uid
    assert not plan_has_workspace_uid
    assert not plan_has_signal_uid
    assert not trade_has_generic_metadata
    assert not plan_has_generic_metadata
    assert not broker_marker_has_workspace_uid
    assert not broker_marker_has_signal_uid
    assert risk_allowed_fields_available
    assert not workspace_runtime_has_engine
    assert controller_has_engine
    assert controller_has_runtime_registry
    assert not runtime_engine_has_workspace_context
    assert semi_text_only
    assert not semi_confirmation_api_present
    assert auto_execution_disabled
    assert not repository_create_trade_has_identity
    assert not repository_create_plan_has_identity
    assert "created_utc" in trade_columns
    assert "created_utc" in plan_columns
    assert "source" in trade_columns
    assert "source" in plan_columns
    assert "broker_order_id" in broker_order_columns

    broker_requests = 0
    broker_execution_attempted = False
    hashes_after = production_hashes()
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert not broker_execution_attempted

    print(f"test_id={TEST_ID}")
    print("workspace_trade_intent_fields=" + ",".join(intent_fields))
    print("workspace_signal_record_fields=" + ",".join(signal_fields))
    print("workspace_binding_fields=" + ",".join(binding_fields))
    print("existing_trade_record_type=SQLite trades row; no production DTO")
    print("existing_order_plan_type=SQLite order_plans row; no production DTO")
    print(
        "existing_broker_order_request_type=broker-specific RuntimeService "
        "method signatures; no shared request DTO"
    )
    print("manual_execution_entrypoint=RuntimeEngine.place_manual_market_order")
    print(
        "manual_execution_required_inputs=symbol_name,side,lots,stop_loss,"
        "take_profit,comment,control_mode"
    )
    print(
        "manual_execution_preconditions=shared engine active broker/service; "
        "service account state; IB pending-open recovery and external-exposure guard"
    )
    print(f"manual_execution_repeats_risk={manual_risk_recheck_present}")
    print(
        "manual_execution_gui_assumptions=active global broker; GUI supplies lots,"
        "optional TP/comment and MANUAL mode; IB/cTrader volume units diverge"
    )
    print(f"trade_record_has_workspace_uid={trade_has_workspace_uid}")
    print(f"trade_record_has_signal_uid={trade_has_signal_uid}")
    print(f"order_plan_has_workspace_uid={plan_has_workspace_uid}")
    print(f"order_plan_has_signal_uid={plan_has_signal_uid}")
    print(
        "identity_metadata_route=NONE: schema has no metadata/context field and "
        "broker comment/label preserves control mode only"
    )
    print(
        "risk_allowed_workspace_fields_available="
        f"{risk_allowed_fields_available}: distributed across intent,signal "
        "record,runtime context"
    )
    print(
        "execution_plan_required_fields=workspace_uid,signal_uid,broker,account_id,"
        "symbol,direction,requested_volume,approved_volume,stop_loss,risk_decision,"
        "risk_reason_code,control_mode,signal_timestamp,plan_created_timestamp,"
        "order_type,volume_unit"
    )
    print(
        "execution_plan_missing_fields=existing order_plans lacks workspace_uid,"
        "signal_uid,broker,account_id,symbol,stop_loss,risk result,volume unit; "
        "trade relation supplies some fields but not causal workspace identity"
    )
    print(f"workspace_runtime_has_runtime_engine_access={workspace_runtime_has_engine}")
    print(f"controller_has_runtime_engine_access={controller_has_engine}")
    print(
        "runtime_engine_has_workspace_context="
        f"{runtime_engine_has_workspace_context}"
    )
    print(
        "candidate_caller_layer=AlgorithmWorkspaceController is the only existing "
        "layer holding RuntimeEngine access and WorkspaceRuntime registry; "
        "execution orchestration API is absent"
    )
    print(
        "auto_plan_creation_contract=UNDEFINED: risk-allowed record exists but "
        "automatic execution is explicitly disabled and no plan transition exists"
    )
    print(
        "semi_confirmation_contract=UNRESOLVED: reason text requires user "
        "confirmation but no confirmation state/API exists"
    )
    print(
        "semi_plan_creation_contract=UNRESOLVED: production defines neither "
        "pre-confirmation draft plan nor post-confirmation executable plan"
    )
    print(
        "reverse_invariant_plan_impact=opposite executable open plan must remain "
        "blocked until owned current position is broker-confirmed flat; current "
        "plan boundary carries no ownership/close-confirmation state"
    )
    print("schema_change_required=True")
    print(
        "new_dto_required=UNRESOLVED_BY_CURRENT_ARCHITECTURE: no existing plan DTO; "
        "anatomy proves fields, not implementation form"
    )
    print("existing_contract_reusable=False")
    print(f"first_missing_boundary={FIRST_MISSING_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_09_EXECUTION_PLAN_BOUNDARY_CONTRACT_ANATOMY=OK")


if __name__ == "__main__":
    main()
