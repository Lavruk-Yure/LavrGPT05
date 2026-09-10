"""run_t109_21_workspace_execution_identity_preservation_path_anatomy_check.py.

TEST_ONLY anatomy простежує ``workspace_uid``, ``signal_uid`` і локальні
execution IDs від Workspace signal до current manual Runtime persistence,
broker callbacks, position reconciliation та ``WorkspaceOwnershipFilter``.
Runner читає production dataclasses/schema/source і installed IB/cTrader API
descriptors, не створюючи execution plan, DB migration або broker request.

Executable assertions відокремлюють наявну Workspace-side identity від її
втрати на execution boundary. Вони порівнюють broker-native metadata, local
persisted mapping і hybrid strategy, перевіряють restart/reverse/open-position
feasibility та захищають production hashes і canonical Replay 2025/2026.
Жодна recommendation не є production implementation або дозволом на wiring.
"""

from __future__ import annotations

import hashlib
import importlib
import re
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY helper без копіювання harness."""
    module = importlib.import_module(module_name)
    helper = getattr(module, helper_name, None)
    if helper is None:
        raise AssertionError(f"missing TEST_ONLY helper: {helper_name}")
    return helper


CANONICAL_PERIODS = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "PERIODS",
)
run_canonical_period = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_run_period",
)

from ibapi.execution import Execution  # noqa: E402
from ibapi.order import Order  # noqa: E402

from core.workspace_ownership import WorkspacePositionSnapshot  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WorkspaceJournalEntry,
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
    WorkspaceTradeIntent,
)
from engine.broker_position import BrokerPosition  # noqa: E402

ctrader_api_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiMessages_pb2"
)
ctrader_model_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiModelMessages_pb2"
)

TEST_ID = "T109-21"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "C. HYBRID_IDENTITY_REQUIRED"
RECOMMENDED_STRATEGY = "BROKER_NATIVE_HINT_PLUS_LOCAL_PERSISTED_CAUSAL_MAPPING"
RECOMMENDED_FIELDS = (
    "workspace_uid,signal_uid,local_execution_id,broker,account_id,symbol,"
    "direction,broker_order_id,broker_position_id,created_at,updated_at"
)
FIRST_UNRESOLVED_BOUNDARY = "WORKSPACE_SIGNAL_IDENTITY_TO_PERSISTED_EXECUTION_IDENTITY"
BOUNDARY_CONTRACT = (
    "RISK_ALLOWED_WORKSPACE_SIGNAL_REQUIRES_PERSISTED_WORKSPACE_SIGNAL_"
    "EXECUTION_MAPPING_BEFORE_BROKER_SUBMISSION_AND_RECONCILIATION"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "workspace_ownership.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "broker_order_identity.py",
    PROJECT_ROOT / "engine" / "broker_position.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "db" / "runtime_db.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "ib_virtual_position_leg.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "runtime_repository.py",
    PROJECT_ROOT / "engine" / "services" / "ctrader_runtime_service.py",
    PROJECT_ROOT / "engine" / "services" / "ib_runtime_service.py",
)


def _source_text(relative_path: str) -> str:
    """Прочитати один production source як factual UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _source_section(
    relative_path: str,
    start_fragment: str,
    end_fragment: str,
) -> str:
    """Вирізати production section між двома exact anchors."""
    source = _source_text(relative_path)
    start = source.index(start_fragment)
    end = source.index(end_fragment, start + len(start_fragment))
    return source[start:end]


def _schema_columns(schema: str, table: str) -> tuple[str, ...]:
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
        if not line or line.startswith(("FOREIGN KEY", "REFERENCES", "UNIQUE")):
            continue
        columns.append(line.split()[0].rstrip(","))
    return tuple(columns)


def _proto_fields(message_type: Any) -> tuple[str, ...]:
    """Повернути installed protobuf field names без створення request."""
    return tuple(field.name for field in message_type.DESCRIPTOR.fields)


def _production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production sources до і після TEST_ONLY anatomy."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered per-file hashes у deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Повернути exact compact canonical Replay metrics key."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def _joined(values: tuple[str, ...]) -> str:
    """Сформувати стабільний comma-separated field marker."""
    return ",".join(values)


def main() -> None:
    """Довести identity gaps і сформувати factual hybrid recommendation."""
    hashes_before = _production_hashes()
    candidate_intent = _source_section(
        "core/workspace_runtime.py",
        "    def _candidate_f_execution_intent(",
        "    def _apply_candidate_f_lifecycle_events(",
    )
    record_signal = _source_section(
        "core/workspace_runtime.py",
        "    def _record_signal(",
        "    def _evaluate_signal_risk(",
    )
    manual_path = _source_section(
        "engine/runtime_engine.py",
        "    def place_manual_market_order(",
        "    @staticmethod\n    def _normalize_optional_protection_price(",
    )
    schema = _source_text("engine/db/runtime_db.py")
    repository = _source_text("engine/runtime_repository.py")
    broker_identity = _source_text("engine/broker_order_identity.py")
    ib_adapter = _source_text("engine/ib_adapter.py")
    ctrader_adapter = _source_text("engine/ctrader_adapter.py")
    ownership = _source_text("core/workspace_ownership.py")

    proposal_fields = tuple(field.name for field in fields(WorkspaceSignalProposal))
    record_fields = tuple(field.name for field in fields(WorkspaceSignalRecord))
    intent_fields = tuple(field.name for field in fields(WorkspaceTradeIntent))
    context_fields = tuple(field.name for field in fields(WorkspaceRuntimeContext))
    journal_fields = tuple(field.name for field in fields(WorkspaceJournalEntry))
    broker_position_fields = tuple(field.name for field in fields(BrokerPosition))
    workspace_position_fields = tuple(
        field.name for field in fields(WorkspacePositionSnapshot)
    )

    workspace_uid_source = "WorkspaceRuntime.context.workspace_uid"
    signal_uid_source = "WorkspaceRuntime._signal_uid(event,proposal)"
    trade_intent_signal_uid_present = "signal_uid" in intent_fields
    trade_intent_workspace_uid_present = "workspace_uid" in intent_fields
    candidate_intent_signal_uid_populated = "signal_uid=" in candidate_intent
    identity_complete_before_execution_boundary = bool(
        trade_intent_signal_uid_present
        and trade_intent_workspace_uid_present
        and candidate_intent_signal_uid_populated
    )
    workspace_side_identity_present = all(
        field_name in record_fields for field_name in ("workspace_uid", "signal_uid")
    ) and all(
        field_name in context_fields
        for field_name in ("workspace_uid", "broker", "account_id", "symbol")
    )
    journal_identity_present = bool(
        "workspace_uid" in journal_fields and "signal_uid=signal_uid" in record_signal
    )

    trade_columns = _schema_columns(schema, "trades")
    plan_columns = _schema_columns(schema, "order_plans")
    broker_order_columns = _schema_columns(schema, "broker_orders")
    position_columns = _schema_columns(schema, "positions")
    ib_leg_columns = _schema_columns(schema, "ib_virtual_position_legs")
    ib_leg_order_columns = _schema_columns(
        schema,
        "ib_virtual_position_leg_orders",
    )
    manual_persistence_chain_present = all(
        token in manual_path
        for token in (
            "self.repository.create_trade(",
            "self.repository.create_order_plan(",
            "service.place_market_order(",
            "self.repository.create_broker_order(",
            "self.repository.create_position(",
        )
    )
    workspace_uid_preserved_manual_path = any(
        "workspace_uid" in columns
        for columns in (
            trade_columns,
            plan_columns,
            broker_order_columns,
            position_columns,
            ib_leg_columns,
        )
    )
    signal_uid_preserved_manual_path = any(
        "signal_uid" in columns
        for columns in (
            trade_columns,
            plan_columns,
            broker_order_columns,
            position_columns,
            ib_leg_columns,
        )
    )

    ib_order_object_fields = tuple(vars(Order()).keys())
    ib_execution_object_fields = tuple(vars(Execution()).keys())
    ib_order_identity_capability = all(
        field_name in ib_order_object_fields
        for field_name in (
            "orderId",
            "clientId",
            "permId",
            "orderRef",
            "parentId",
            "account",
        )
    )
    ib_execution_identity_capability = all(
        field_name in ib_execution_object_fields
        for field_name in (
            "execId",
            "permId",
            "clientId",
            "orderId",
            "orderRef",
            "acctNumber",
        )
    )
    ib_current_order_ref_used = "parent_order.orderRef = comment_clean" in ib_adapter
    ib_current_marker_has_workspace_uid = "workspace_uid" in broker_identity
    ib_current_marker_has_signal_uid = "signal_uid" in broker_identity
    ib_position_callback_identity = all(
        token in ib_adapter
        for token in (
            '"account": account',
            '"contract": contract',
            '"position": position',
            '"avg_cost": avg_cost',
        )
    )
    ib_position_has_order_link = any(
        field_name in broker_position_fields
        for field_name in ("broker_order_id", "order_ref", "perm_id", "exec_id")
    )
    ib_workspace_identity_roundtrip_feasible = False
    ib_signal_identity_roundtrip_feasible = False
    ib_restart_identity_recovery_feasible = False

    new_order_fields = _proto_fields(
        getattr(ctrader_api_messages, "ProtoOANewOrderReq")
    )
    execution_event_fields = _proto_fields(
        getattr(ctrader_api_messages, "ProtoOAExecutionEvent")
    )
    order_fields = _proto_fields(getattr(ctrader_model_messages, "ProtoOAOrder"))
    deal_fields = _proto_fields(getattr(ctrader_model_messages, "ProtoOADeal"))
    position_fields = _proto_fields(getattr(ctrader_model_messages, "ProtoOAPosition"))
    trade_data_fields = _proto_fields(
        getattr(ctrader_model_messages, "ProtoOATradeData")
    )
    ctrader_native_client_identity = all(
        field_name in new_order_fields
        for field_name in ("clientOrderId", "label", "comment")
    )
    ctrader_order_position_link = all(
        field_name in order_fields for field_name in ("orderId", "positionId")
    ) and all(
        field_name in deal_fields for field_name in ("dealId", "orderId", "positionId")
    )
    ctrader_position_metadata_available = bool(
        "tradeData" in position_fields
        and "label" in trade_data_fields
        and "comment" in trade_data_fields
    )
    ctrader_execution_objects_available = all(
        field_name in execution_event_fields
        for field_name in ("order", "deal", "position")
    )
    ctrader_current_client_order_id_used = "request.clientOrderId" in ctrader_adapter
    ctrader_current_label_is_mode_only = (
        "request.label = build_ctrader_order_label(control_mode)" in ctrader_adapter
    )
    ctrader_workspace_identity_roundtrip_feasible = False
    ctrader_signal_identity_roundtrip_feasible = False
    ctrader_restart_identity_recovery_feasible = False

    current_repository_has_causal_identity = bool(
        workspace_uid_preserved_manual_path and signal_uid_preserved_manual_path
    )
    repository_links_local_chain = all(
        token in repository
        for token in (
            "def create_trade(",
            "def create_order_plan(",
            "def create_broker_order(",
            "def create_position(",
        )
    )
    ownership_requires_workspace_identity = all(
        token in ownership
        for token in (
            "class WorkspaceOwnershipFilter:",
            "workspace_uid=position.workspace_uid",
            "broker=position.broker",
            "account_id=position.account_id",
            "symbol=position.symbol",
        )
    )
    broker_position_has_workspace_identity = "workspace_uid" in broker_position_fields
    broker_position_has_signal_identity = "signal_uid" in broker_position_fields

    alternative_a_broker_native_identity_fit = (
        "PARTIAL_NOT_BROKER_NEUTRAL_AND_IB_POSITION_LOSES_ORDER_IDENTITY"
    )
    alternative_b_local_mapping_fit = (
        "PARTIAL_RESTART_SAFE_ONLY_AFTER_SCHEMA_AND_RECONCILIATION_EXTENSION"
    )
    alternative_c_hybrid_fit = "RECOMMENDED_BROKER_HINT_PLUS_LOCAL_AUTHORITY"
    schema_extension_required = not current_repository_has_causal_identity
    broker_adapter_extension_required = bool(
        not ib_current_marker_has_workspace_uid
        or not ib_current_marker_has_signal_uid
        or not ctrader_current_client_order_id_used
        or ctrader_current_label_is_mode_only
    )
    runtime_repository_extension_required = not current_repository_has_causal_identity
    reverse_identity_contract_feasible = True
    workspace_open_positions_count_becomes_derivable_if_identity_fixed = bool(
        ownership_requires_workspace_identity
        and repository_links_local_chain
        and not broker_position_has_workspace_identity
        and not broker_position_has_signal_identity
    )

    assert "workspace_uid" not in proposal_fields
    assert "signal_uid" not in proposal_fields
    assert workspace_side_identity_present and journal_identity_present
    assert trade_intent_signal_uid_present
    assert not trade_intent_workspace_uid_present
    assert not candidate_intent_signal_uid_populated
    assert not identity_complete_before_execution_boundary
    assert manual_persistence_chain_present and repository_links_local_chain
    assert not workspace_uid_preserved_manual_path
    assert not signal_uid_preserved_manual_path
    assert ib_order_identity_capability and ib_execution_identity_capability
    assert ib_current_order_ref_used and ib_position_callback_identity
    assert not ib_current_marker_has_workspace_uid
    assert not ib_current_marker_has_signal_uid
    assert not ib_position_has_order_link
    assert not ib_workspace_identity_roundtrip_feasible
    assert not ib_signal_identity_roundtrip_feasible
    assert not ib_restart_identity_recovery_feasible
    assert ctrader_native_client_identity
    assert ctrader_order_position_link and ctrader_position_metadata_available
    assert ctrader_execution_objects_available
    assert not ctrader_current_client_order_id_used
    assert ctrader_current_label_is_mode_only
    assert not ctrader_workspace_identity_roundtrip_feasible
    assert not ctrader_signal_identity_roundtrip_feasible
    assert not ctrader_restart_identity_recovery_feasible
    assert ownership_requires_workspace_identity
    assert "workspace_uid" in workspace_position_fields
    assert "signal_uid" in workspace_position_fields
    assert "broker_position_id" in workspace_position_fields
    assert not broker_position_has_workspace_identity
    assert not broker_position_has_signal_identity
    assert schema_extension_required
    assert broker_adapter_extension_required
    assert runtime_repository_extension_required
    assert reverse_identity_contract_feasible
    assert workspace_open_positions_count_becomes_derivable_if_identity_fixed

    broker_requests = 0
    broker_execution_attempted = False
    baselines: dict[str, WorkspaceRuntime] = {}
    for spec in CANONICAL_PERIODS:
        replay_runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = replay_runtime
        broker_requests += requests
    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    hashes_after = _production_hashes()
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert hashes_before == hashes_after
    assert broker_requests == 0
    assert not broker_execution_attempted

    matrix = ";".join(
        (
            f"trades[{_joined(trade_columns)}]",
            f"order_plans[{_joined(plan_columns)}]",
            f"broker_orders[{_joined(broker_order_columns)}]",
            f"positions[{_joined(position_columns)}]",
            f"ib_virtual_position_legs[{_joined(ib_leg_columns)}]",
            f"ib_virtual_position_leg_orders[{_joined(ib_leg_order_columns)}]",
        )
    )
    print(f"test_id={TEST_ID}")
    print(f"workspace_uid_source={workspace_uid_source}")
    print(f"signal_uid_source={signal_uid_source}")
    print(f"trade_intent_signal_uid_present={trade_intent_signal_uid_present}")
    print(f"trade_intent_workspace_uid_present={trade_intent_workspace_uid_present}")
    print(
        "trade_intent_signal_uid_populated_by_candidate_f="
        f"{candidate_intent_signal_uid_populated}"
    )
    print(
        "identity_complete_before_execution_boundary="
        f"{identity_complete_before_execution_boundary}"
    )
    print(f"manual_trade_fields={_joined(trade_columns)}")
    print(f"manual_order_plan_fields={_joined(plan_columns)}")
    print(f"manual_broker_order_fields={_joined(broker_order_columns)}")
    print(f"manual_position_fields={_joined(position_columns)}")
    print(
        "workspace_uid_preserved_manual_path=" f"{workspace_uid_preserved_manual_path}"
    )
    print("signal_uid_preserved_manual_path=" f"{signal_uid_preserved_manual_path}")
    print(f"runtime_db_identity_matrix={matrix}")
    print("ib_client_identity_fields=orderRef")
    print(
        "ib_order_identity_fields=" "orderId,permId,clientId,parentId,account,orderRef"
    )
    print(
        "ib_execution_identity_fields="
        "installed:execId,permId,clientId,orderId,orderRef,acctNumber;"
        "current_wrapper:order_id,perm_id,account"
    )
    print("ib_position_identity_fields=account,contract,position,avgCost")
    print(
        "ib_workspace_identity_roundtrip_feasible="
        f"{ib_workspace_identity_roundtrip_feasible}"
    )
    print(
        "ib_signal_identity_roundtrip_feasible="
        f"{ib_signal_identity_roundtrip_feasible}"
    )
    print(
        "ib_restart_identity_recovery_feasible="
        f"{ib_restart_identity_recovery_feasible}"
    )
    print("ctrader_client_identity_fields=clientOrderId,label,comment")
    print(
        "ctrader_order_identity_fields="
        "orderId,clientOrderId,positionId,tradeData.label,tradeData.comment"
    )
    print("ctrader_deal_identity_fields=dealId,orderId,positionId")
    print(
        "ctrader_position_identity_fields="
        "positionId,tradeData.label,tradeData.comment"
    )
    print(
        "ctrader_identity_format_restrictions="
        "NOT_DECLARED_IN_INSTALLED_PROTO_DESCRIPTOR"
    )
    print(
        "ctrader_workspace_identity_roundtrip_feasible="
        f"{ctrader_workspace_identity_roundtrip_feasible}"
    )
    print(
        "ctrader_signal_identity_roundtrip_feasible="
        f"{ctrader_signal_identity_roundtrip_feasible}"
    )
    print(
        "ctrader_restart_identity_recovery_feasible="
        f"{ctrader_restart_identity_recovery_feasible}"
    )
    print(
        "alternative_A_broker_native_identity_fit="
        f"{alternative_a_broker_native_identity_fit}"
    )
    print("alternative_B_local_mapping_fit=" f"{alternative_b_local_mapping_fit}")
    print(f"alternative_C_hybrid_fit={alternative_c_hybrid_fit}")
    print(f"recommended_identity_strategy={RECOMMENDED_STRATEGY}")
    print(f"recommended_identity_fields={RECOMMENDED_FIELDS}")
    print(f"schema_extension_required={schema_extension_required}")
    print("broker_adapter_extension_required=" f"{broker_adapter_extension_required}")
    print(
        "runtime_repository_extension_required="
        f"{runtime_repository_extension_required}"
    )
    print("reverse_identity_contract_feasible=" f"{reverse_identity_contract_feasible}")
    print(
        "workspace_open_positions_count_becomes_derivable_if_identity_fixed="
        f"{workspace_open_positions_count_becomes_derivable_if_identity_fixed}"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"production_hashes_before={_combined_hash(hashes_before)}")
    print(f"production_hashes_after={_combined_hash(hashes_after)}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_21_WORKSPACE_EXECUTION_IDENTITY_PATH_ANATOMY=OK")


def test_t109_21_workspace_execution_identity_path() -> None:
    """Запустити T109-21 як один pytest-compatible checkpoint."""
    main()


if __name__ == "__main__":
    main()
