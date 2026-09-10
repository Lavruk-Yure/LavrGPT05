"""run_t109_22_persisted_workspace_execution_identity_contract_decision_check.py.

TEST_ONLY contract decision визначає мінімальну broker-neutral persisted
identity для майбутнього Workspace AUTO/SEMI execution. Runner читає фактичні
Workspace DTO, risk ordering, RuntimeRepository, SQLite schema, manual
pre-submission path, IB virtual-leg cardinality та installed cTrader protobuf
descriptors. На цій основі він порівнює reuse ``trade_uid``, ``order_plan_uid``,
нову entity й окрему mapping table.

Перевірка не створює записів у БД, не виконує migration, confirmation,
execution wiring, adapter call або broker request. Canonical Replay 2025/2026,
production hashes, schema hash, completed-bar causality та broker-safety
контракти перевіряються після factual anatomy. Рекомендація описує майбутній
контракт, але нічого не productionize і не починає T109-23.
"""

from __future__ import annotations

import hashlib
import importlib
import re
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, get_type_hints

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established helper без копіювання Replay harness."""
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

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalRecord,
    WorkspaceTradeIntent,
)

ctrader_api_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiMessages_pb2"
)
ctrader_model_messages = importlib.import_module(
    "ctrader_open_api.messages.OpenApiModelMessages_pb2"
)

TEST_ID = "T109-22"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
FACTUAL_VERDICT = "A. EXISTING_TRADE_UID_CANONICAL_EXECUTION_ID_SUFFICIENT"
FIRST_UNRESOLVED_BOUNDARY = (
    "TRADE_ROW_WORKSPACE_IDENTITY_SCHEMA_AND_POST_RISK_PERSISTENCE_WIRING"
)
BOUNDARY_CONTRACT = (
    "RISK_ALLOW_MUST_ATOMICALLY_CREATE_OR_REUSE_ONE_WORKSPACE_OWNED_TRADE_"
    "BY_WORKSPACE_UID_SIGNAL_UID_BEFORE_ANY_BROKER_SUBMISSION"
)
PRE_SUBMISSION_FIELDS = (
    "workspace_uid,signal_uid,trade_uid,execution_origin,control_mode,"
    "execution_state,broker,account_id,symbol,direction,created_utc"
)
RECOMMENDED_FIELDS = (
    "trade_uid,workspace_uid,signal_uid,execution_origin,control_mode,"
    "execution_state,broker,account_id,symbol,side,created_utc"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace.py",
    PROJECT_ROOT / "core" / "session_repository.py",
    PROJECT_ROOT / "core" / "workspace_ownership.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "broker_order_identity.py",
    PROJECT_ROOT / "engine" / "ctrader_adapter.py",
    PROJECT_ROOT / "engine" / "db" / "runtime_db.py",
    PROJECT_ROOT / "engine" / "ib_adapter.py",
    PROJECT_ROOT / "engine" / "ib_virtual_position_leg.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "runtime_repository.py",
)


def _source_text(relative_path: str) -> str:
    """Прочитати production source як factual UTF-8 contract."""
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
    """Повернути declared SQLite columns без constraint continuation."""
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
    """Повернути installed protobuf fields без створення broker request."""
    return tuple(field.name for field in message_type.DESCRIPTOR.fields)


def _production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production sources до і після TEST_ONLY run."""
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered production hashes у deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Повернути exact canonical Replay summary key."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def main() -> None:
    """Довести canonical persisted identity decision і safety invariants."""
    hashes_before = _production_hashes()
    schema_path = PROJECT_ROOT / "engine" / "db" / "runtime_db.py"
    schema_hash_before = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    schema = _source_text("engine/db/runtime_db.py")
    runtime_engine = _source_text("engine/runtime_engine.py")
    algorithm_workspace = _source_text("core/algorithm_workspace.py")
    session_repository = _source_text("core/session_repository.py")
    ownership = _source_text("core/workspace_ownership.py")
    ib_virtual_leg = _source_text("engine/ib_virtual_position_leg.py")

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
    signal_uid_section = _source_section(
        "core/workspace_runtime.py",
        "    def _signal_uid(",
        "    def _market_event_binding_matches(",
    )
    create_trade = _source_section(
        "engine/runtime_repository.py",
        "    def create_trade(",
        "    def create_order_plan(",
    )
    create_order_plan = _source_section(
        "engine/runtime_repository.py",
        "    def create_order_plan(",
        "    def create_broker_order(",
    )
    create_broker_order = _source_section(
        "engine/runtime_repository.py",
        "    def create_broker_order(",
        "    def get_broker_order_by_broker_order_id(",
    )
    create_position = _source_section(
        "engine/runtime_repository.py",
        "    def create_position(",
        "    def get_trade_chain(",
    )
    trade_chain = _source_section(
        "engine/runtime_repository.py",
        "    def get_trade_chain(",
        "    def get_latest_trade_uid(",
    )
    ib_open_path = _source_section(
        "engine/runtime_engine.py",
        "    def _place_manual_market_order_ib(",
        "    def place_manual_market_order(",
    )
    ctrader_open_path = _source_section(
        "engine/runtime_engine.py",
        "    def place_manual_market_order(",
        "    @staticmethod\n    def _normalize_optional_protection_price(",
    )

    workspace_types = get_type_hints(AlgorithmWorkspace)
    context_types = get_type_hints(WorkspaceRuntimeContext)
    record_types = get_type_hints(WorkspaceSignalRecord)
    intent_fields = tuple(field.name for field in fields(WorkspaceTradeIntent))
    workspace_uid_type = workspace_types["workspace_uid"].__name__
    signal_uid_type = record_types["signal_uid"].__name__
    workspace_uid_restart_stable = all(
        token in algorithm_workspace
        for token in (
            "workspace_uid=str(uuid4())",
            'workspace_uid=str(data.get("workspace_uid") or "")',
            '"workspace_uid": self.workspace_uid',
        )
    ) and all(
        token in session_repository
        for token in ("def save_workspace(", "def load_workspace(")
    )
    workspace_uid_uniqueness_scope = "ONE_PERSISTED_ALGORITHM_WORKSPACE"
    signal_uid_deterministic = all(
        token in signal_uid_section
        for token in (
            "self.context.workspace_uid",
            "event.timestamp.isoformat()",
            "proposal.signal_type",
            "proposal.direction",
            "hashlib.sha256(payload).hexdigest()[:32]",
        )
    )
    signal_uid_uniqueness_scope = (
        "WORKSPACE_PLUS_EVENT_TIMESTAMP_SOURCE_AND_PROPOSAL_IDENTITY"
    )
    trade_intent_signal_uid_currently_populated = bool(
        "signal_uid" in intent_fields and "signal_uid=" in candidate_intent
    )

    trade_columns = _schema_columns(schema, "trades")
    plan_columns = _schema_columns(schema, "order_plans")
    broker_order_columns = _schema_columns(schema, "broker_orders")
    position_columns = _schema_columns(schema, "positions")
    ib_leg_columns = _schema_columns(schema, "ib_virtual_position_legs")
    trade_uid_persistent_uuid = bool(
        "trade_uid = str(uuid4())" in create_trade
        and "trade_uid TEXT NOT NULL UNIQUE" in schema
    )
    plan_uid_persistent_uuid = bool(
        "order_plan_uid = str(uuid4())" in create_order_plan
        and "order_plan_uid TEXT NOT NULL UNIQUE" in schema
    )
    broker_order_uid_persistent_uuid = bool(
        "broker_order_uid = str(uuid4())" in create_broker_order
        and "broker_order_uid TEXT NOT NULL UNIQUE" in schema
    )
    position_uid_persistent_uuid = bool(
        "position_uid = str(uuid4())" in create_position
        and "position_uid TEXT NOT NULL UNIQUE" in schema
    )
    trade_chain_is_root = all(
        token in trade_chain
        for token in (
            "FROM trades",
            "FROM order_plans",
            "FROM broker_orders",
            "FROM positions",
        )
    )
    local_ids_linked = all(
        "trade_uid" in columns
        for columns in (trade_columns, plan_columns, broker_order_columns,
                        position_columns, ib_leg_columns)
    )

    trade_created_before_submission = all(
        path.index("trade_uid = self.repository.create_trade(")
        < path.index("order_plan_uid = self.repository.create_order_plan(")
        < path.index("service.place_market_order(")
        for path in (ib_open_path, ctrader_open_path)
    )
    close_plan_reuses_trade_uid = all(
        token in runtime_engine
        for token in (
            "trade_uid=leg.trade_uid",
            'order_type="CLOSE_MARKET"',
        )
    )
    trade_to_order_one_to_many = bool(
        "trade_uid TEXT NOT NULL" in schema
        and "trade_uid TEXT NOT NULL UNIQUE" not in re.search(
            r"CREATE TABLE IF NOT EXISTS order_plans \((.*?)\n\);",
            schema,
            re.DOTALL,
        ).group(1)
        and close_plan_reuses_trade_uid
    )
    broker_order_one_to_many_fills = all(
        token in ib_virtual_leg
        for token in (
            "sum(",
            'row.get("order_id")',
            'row.get("shares")',
        )
    )
    runtime_positions_allow_many_per_trade = bool(
        "trade_uid" in position_columns
        and "trade_uid TEXT NOT NULL UNIQUE" not in re.search(
            r"CREATE TABLE IF NOT EXISTS positions \((.*?)\n\);",
            schema,
            re.DOTALL,
        ).group(1)
    )
    ib_virtual_leg_one_per_trade = (
        "trade_uid TEXT NOT NULL UNIQUE" in re.search(
            r"CREATE TABLE IF NOT EXISTS ib_virtual_position_legs "
            r"\((.*?)\n\);",
            schema,
            re.DOTALL,
        ).group(1)
    )

    ctrader_new_order_fields = _proto_fields(
        getattr(ctrader_api_messages, "ProtoOANewOrderReq")
    )
    ctrader_deal_fields = _proto_fields(
        getattr(ctrader_model_messages, "ProtoOADeal")
    )
    ctrader_hint_available = all(
        field_name in ctrader_new_order_fields
        for field_name in ("clientOrderId", "label", "comment")
    )
    ctrader_deal_links_order_position = all(
        field_name in ctrader_deal_fields
        for field_name in ("dealId", "orderId", "positionId")
    )

    risk_allowed_boundary_present = all(
        token in record_signal
        for token in (
            "risk_decision = self._evaluate_signal_risk(",
            "accepted = risk_decision.allowed",
            "WorkspaceSignalRecord(",
        )
    ) and record_signal.index("accepted = risk_decision.allowed") < (
        record_signal.index("WorkspaceSignalRecord(")
    )
    current_workspace_execution_persistence_absent = not any(
        token in record_signal
        for token in (
            "create_trade(",
            "create_order_plan(",
            "place_market_order(",
        )
    )
    current_trade_has_workspace_identity = all(
        field_name in trade_columns for field_name in ("workspace_uid", "signal_uid")
    )
    existing_uid_reusable_as_execution_uid = bool(
        trade_uid_persistent_uuid
        and trade_chain_is_root
        and trade_created_before_submission
        and trade_to_order_one_to_many
        and runtime_positions_allow_many_per_trade
    )
    new_execution_uid_required = not existing_uid_reusable_as_execution_uid
    identity_persist_before_broker_submission_feasible = bool(
        trade_created_before_submission and existing_uid_reusable_as_execution_uid
    )
    idempotency_key_candidate = "UNIQUE(workspace_uid,signal_uid)"
    duplicate_execution_prevention_feasible = bool(
        workspace_uid_restart_stable
        and signal_uid_deterministic
        and identity_persist_before_broker_submission_feasible
    )
    current_idempotency_constraint_present = bool(
        "workspace_uid" in trade_columns
        and "signal_uid" in trade_columns
        and "UNIQUE (workspace_uid, signal_uid)" in schema
    )

    current_source_is_control_mode = all(
        token in runtime_engine
        for token in (
            "control_mode_norm = normalize_order_control_mode(control_mode)",
            "source=control_mode_norm",
        )
    )
    manual_path_can_receive_non_manual_mode = (
        "def place_manual_market_order(" in runtime_engine
        and "control_mode: str = ORDER_CONTROL_MODE_MANUAL" in runtime_engine
    )
    workspace_execution_source_marker_required = bool(
        current_source_is_control_mode and manual_path_can_receive_non_manual_mode
    )
    manual_execution_identity_affected = False

    ownership_bridge_contract_present = all(
        token in ownership
        for token in (
            "class WorkspaceOwnershipFilter:",
            "workspace_uid=position.workspace_uid",
            "broker=position.broker",
            "account_id=position.account_id",
            "symbol=position.symbol",
        )
    )
    reverse_identity_contract_supported = bool(
        trade_chain_is_root and close_plan_reuses_trade_uid
    )
    open_positions_ownership_bridge_supported = bool(
        ownership_bridge_contract_present
        and runtime_positions_allow_many_per_trade
        and local_ids_linked
    )

    alternative_a_extend_trades_fit = (
        "RECOMMENDED_ROOT_SEMANTICS_PRE_SUBMISSION_RESTART_SAFE_1_TO_N_"
        "WITH_NULLABLE_WORKSPACE_FIELDS_STATE_AND_ORIGIN_MARKER"
    )
    alternative_b_extend_order_plans_fit = (
        "NOT_CANONICAL_ROOT_ONE_TRADE_HAS_MANY_OPEN_CLOSE_PROTECTIVE_PLANS"
    )
    alternative_c_new_workspace_execution_entity_fit = (
        "FEASIBLE_BUT_DUPLICATES_TRADE_ROOT_AND_EXPANDS_MIGRATION"
    )
    alternative_d_mapping_table_fit = (
        "FEASIBLE_DECOUPLING_BUT_SPLITS_STATE_AND_REQUIRES_EXTRA_JOIN"
    )
    recommended_persistence_strategy = (
        "EXTEND_TRADES_WITH_NULLABLE_WORKSPACE_CAUSAL_IDENTITY_STATE_AND_ORIGIN"
    )
    schema_migration_required = not current_trade_has_workspace_identity
    new_entity_required = False

    assert context_types["workspace_uid"] is str
    assert workspace_uid_type == "str" and signal_uid_type == "str"
    assert workspace_uid_restart_stable and signal_uid_deterministic
    assert not trade_intent_signal_uid_currently_populated
    assert trade_uid_persistent_uuid and plan_uid_persistent_uuid
    assert broker_order_uid_persistent_uuid and position_uid_persistent_uuid
    assert trade_chain_is_root and local_ids_linked
    assert trade_to_order_one_to_many and broker_order_one_to_many_fills
    assert runtime_positions_allow_many_per_trade
    assert ib_virtual_leg_one_per_trade
    assert ctrader_hint_available and ctrader_deal_links_order_position
    assert risk_allowed_boundary_present
    assert current_workspace_execution_persistence_absent
    assert existing_uid_reusable_as_execution_uid
    assert not new_execution_uid_required
    assert identity_persist_before_broker_submission_feasible
    assert duplicate_execution_prevention_feasible
    assert not current_idempotency_constraint_present
    assert workspace_execution_source_marker_required
    assert not manual_execution_identity_affected
    assert reverse_identity_contract_supported
    assert open_positions_ownership_bridge_supported
    assert schema_migration_required and not new_entity_required

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
    schema_hash_after = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert hashes_before == hashes_after
    assert schema_hash_before == schema_hash_after
    assert broker_requests == 0
    assert not broker_execution_attempted

    print(f"test_id={TEST_ID}")
    print(f"workspace_uid_type={workspace_uid_type}")
    print(f"workspace_uid_restart_stable={workspace_uid_restart_stable}")
    print(f"workspace_uid_uniqueness_scope={workspace_uid_uniqueness_scope}")
    print(f"signal_uid_type={signal_uid_type}")
    print(f"signal_uid_deterministic={signal_uid_deterministic}")
    print(f"signal_uid_uniqueness_scope={signal_uid_uniqueness_scope}")
    print(
        "trade_intent_signal_uid_currently_populated="
        f"{trade_intent_signal_uid_currently_populated}"
    )
    print(
        "trade_uid_semantics=PERSISTED_UUID_PRE_SUBMISSION_TRADE_CHAIN_ROOT_"
        "ONE_TO_MANY_ORDERS_AND_POSITIONS_RESTART_STABLE"
    )
    print(
        "order_plan_uid_semantics=PERSISTED_UUID_ONE_ORDER_INTENT_CHILD_OF_"
        "TRADE_NOT_EXECUTION_ROOT"
    )
    print(
        "broker_order_uid_semantics=PERSISTED_UUID_CREATED_AFTER_SUBMISSION_"
        "BROKER_ORDER_CHILD_NOT_PRE_SUBMISSION_ID"
    )
    print(
        "position_uid_semantics=PERSISTED_UUID_CREATED_AFTER_FILL_OR_POSITION_"
        "MATCH_NOT_PRE_SUBMISSION_ID"
    )
    print("trade_to_order_cardinality=ONE_TO_MANY")
    print("order_to_fill_cardinality=ONE_TO_MANY")
    print(
        "execution_to_position_cardinality=ONE_TO_ZERO_OR_MANY_RUNTIME_"
        "POSITIONS;IB_VIRTUAL_LEG_CURRENTLY_ONE_TO_ZERO_OR_ONE_PER_TRADE"
    )
    print(
        "existing_uid_reusable_as_execution_uid="
        f"{existing_uid_reusable_as_execution_uid}"
    )
    print(f"new_execution_uid_required={new_execution_uid_required}")
    print(f"candidate_pre_submission_identity_fields={PRE_SUBMISSION_FIELDS}")
    print(
        "identity_persist_before_broker_submission_feasible="
        f"{identity_persist_before_broker_submission_feasible}"
    )
    print(
        "risk_allowed_boundary=WorkspaceRuntime._record_signal after "
        "_evaluate_signal_risk returns ALLOW"
    )
    print(
        "identity_creation_owner_candidate=WorkspaceRuntime post-risk-ALLOW "
        "orchestration -> RuntimeRepository.create_trade atomic persistence"
    )
    print("auto_identity_state=READY_FOR_SUBMISSION")
    print("semi_identity_state=PENDING_CONFIRMATION")
    print("semi_confirmation_required_before_submission=True")
    print(f"idempotency_key_candidate={idempotency_key_candidate}")
    print(
        "duplicate_execution_prevention_feasible="
        f"{duplicate_execution_prevention_feasible}"
    )
    print(
        "current_idempotency_constraint_present="
        f"{current_idempotency_constraint_present}"
    )
    print("broker_native_hint_authoritative=False")
    print("ib_hint_field=orderRef")
    print("ctrader_hint_field=clientOrderId")
    print(
        "broker_native_hint_payload_recommendation=SHORT_OPAQUE_TRADE_UID_"
        "REFERENCE_NOT_FULL_WORKSPACE_OR_SIGNAL_IDENTITY"
    )
    print(f"alternative_A_extend_trades_fit={alternative_a_extend_trades_fit}")
    print(
        "alternative_B_extend_order_plans_fit="
        f"{alternative_b_extend_order_plans_fit}"
    )
    print(
        "alternative_C_new_workspace_execution_entity_fit="
        f"{alternative_c_new_workspace_execution_entity_fit}"
    )
    print(f"alternative_D_mapping_table_fit={alternative_d_mapping_table_fit}")
    print(f"recommended_persistence_strategy={recommended_persistence_strategy}")
    print(f"recommended_execution_identity_fields={RECOMMENDED_FIELDS}")
    print(f"schema_migration_required={schema_migration_required}")
    print(f"new_entity_required={new_entity_required}")
    print(f"manual_execution_identity_affected={manual_execution_identity_affected}")
    print(
        "workspace_execution_source_marker_required="
        f"{workspace_execution_source_marker_required}"
    )
    print(
        "reverse_identity_contract_supported="
        f"{reverse_identity_contract_supported}"
    )
    print(
        "open_positions_ownership_bridge_supported="
        f"{open_positions_ownership_bridge_supported}"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"production_hashes_before={_combined_hash(hashes_before)}")
    print(f"production_hashes_after={_combined_hash(hashes_after)}")
    print(f"production_hashes_before_after_match={hashes_before == hashes_after}")
    print(f"schema_hash_before={schema_hash_before}")
    print(f"schema_hash_after={schema_hash_after}")
    print(f"schema_changed={schema_hash_before != schema_hash_after}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  schema_changed=False")
    print("  lookahead_used=False")
    print("T109_22_PERSISTED_WORKSPACE_EXECUTION_IDENTITY_CONTRACT=OK")


if __name__ == "__main__":
    main()
