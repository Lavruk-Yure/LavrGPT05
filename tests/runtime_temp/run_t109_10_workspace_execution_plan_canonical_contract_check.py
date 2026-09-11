"""run_t109_10_workspace_execution_plan_canonical_contract_check.py.

TEST_ONLY contract harness визначає мінімальні поля й invariants майбутнього
Workspace execution plan після accepted та risk-allowed signal. Production
dataclasses, risk defaults, manual RuntimeEngine inputs, broker conversion
boundaries і SQLite schema читаються як factual sources; локальний immutable
plan лише перевіряє identity, risk, AUTO/SEMI, timestamp та reverse contracts.

Harness не створює production DTO/schema, не викликає RuntimeEngine, broker
service чи adapter, не симулює broker fill/close і не торкається Replay.
Невизначену Workspace volume unit він не підміняє припущенням: через цей
blocker жоден TEST_ONLY plan не стає executable.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_ownership import WorkspaceBinding  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_SPREAD_OK,
    WorkspaceSignalRecord,
    WorkspaceTradeIntent,
)
from engine.risk.constants import (  # noqa: E402
    DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME,
)

TEST_ID = "T109-10"
FACTUAL_VERDICT = "E. VOLUME_CONTRACT_UNRESOLVED"
FIRST_UNRESOLVED_CONTRACT = "WORKSPACE_PLAN_BROKER_NEUTRAL_VOLUME_UNIT"
BOUNDARY_CONTRACT = (
    "RISK_APPROVED_VOLUME_REQUIRES_ONE_EXPLICIT_WORKSPACE_UNIT_AND_BROKER_"
    "CONVERSION_BOUNDARY_BEFORE_PLAN_CAN_BECOME_EXECUTABLE"
)
PLAN_STATE_READY = "READY_FOR_EXECUTION"
PLAN_STATE_PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
PLAN_STATE_BLOCKED_VOLUME_UNIT = "BLOCKED_VOLUME_UNIT_UNRESOLVED"
PLAN_STATE_BLOCKED_CONFIRMED_FLAT = "BLOCKED_CONFIRMED_FLAT_REQUIRED"
VOLUME_UNIT_UNRESOLVED = "UNRESOLVED"
SIGNAL_TIME = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "ctrader_lot.py",
    PROJECT_ROOT / "core" / "workspace_ownership.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "db" / "runtime_db.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
    PROJECT_ROOT / "engine" / "runtime_repository.py",
)


@dataclass(frozen=True, slots=True)
class TestOnlyWorkspaceExecutionPlan:
    """Локальне immutable представлення прийнятого plan contract."""

    workspace_uid: str
    signal_uid: str
    broker: str
    account_id: str | None
    symbol: str
    direction: str
    requested_volume: float
    approved_volume: float
    stop_loss: float
    risk_decision: str
    risk_reason_code: str
    control_mode: str
    signal_timestamp: datetime
    plan_created_timestamp: datetime
    order_type: str
    volume_unit: str
    plan_state: str
    executable: bool


def source_text(relative_path: str) -> str:
    """Прочитати один production module як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def source_section(relative_path: str, start: str, end: str) -> str:
    """Виділити production section між двома exact anchors."""
    source = source_text(relative_path)
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def schema_columns(schema: str, table: str) -> tuple[str, ...]:
    """Повернути declared SQLite columns production table."""
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
    """Зафіксувати production sources до і після TEST_ONLY harness."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def signal_record(
    *,
    accepted: bool,
    risk_decision: str | None,
    approved_volume: float | None,
) -> WorkspaceSignalRecord:
    """Побудувати signal-side contract case без broker execution."""
    return WorkspaceSignalRecord(
        timestamp=SIGNAL_TIME,
        signal_uid="t109-10-signal",
        workspace_uid="6c18b50f-dfea-45f5-9cbd-b68d53eb1c45",
        broker="CTRADER",
        account_id="T10910-DEMO",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="BROKER",
        signal_type="CANDIDATE_F",
        direction="BUY",
        strength=1.0,
        macd_state="CROSS_UP",
        alligator_confirmation="CONFIRMED",
        spread_status=WORKSPACE_SIGNAL_SPREAD_OK,
        accepted=accepted,
        reason="T109-10 contract case",
        risk_decision=risk_decision,
        risk_reason_code=(
            ("RISK_ALLOWED" if risk_decision == "ALLOW" else "RISK_BLOCKED")
            if risk_decision is not None
            else None
        ),
        requested_volume=1000.0,
        approved_volume=approved_volume,
        risk_execution_attempted=False,
    )


def create_test_only_plan(
    signal: WorkspaceSignalRecord,
    intent: WorkspaceTradeIntent,
    binding: WorkspaceBinding,
    *,
    control_mode: str,
    confirmed: bool = False,
    opposite_direction: bool = False,
    confirmed_flat: bool = False,
) -> TestOnlyWorkspaceExecutionPlan | None:
    """Застосувати лише прийняті risk/control/reverse plan invariants."""
    if not signal.accepted:
        return None
    if signal.risk_decision != "ALLOW" or signal.approved_volume is None:
        return None
    if signal.workspace_uid != binding.workspace_uid:
        return None
    if signal.broker != binding.broker:
        return None
    if signal.account_id != binding.account_id or signal.symbol != binding.symbol:
        return None

    plan_state = PLAN_STATE_READY
    executable = True
    if control_mode == "SEMI" and not confirmed:
        plan_state = PLAN_STATE_PENDING_CONFIRMATION
        executable = False
    if opposite_direction and not confirmed_flat:
        plan_state = PLAN_STATE_BLOCKED_CONFIRMED_FLAT
        executable = False
    if VOLUME_UNIT_UNRESOLVED == "UNRESOLVED" and executable:
        plan_state = PLAN_STATE_BLOCKED_VOLUME_UNIT
        executable = False

    return TestOnlyWorkspaceExecutionPlan(
        workspace_uid=signal.workspace_uid,
        signal_uid=signal.signal_uid,
        broker=binding.broker,
        account_id=binding.account_id,
        symbol=binding.symbol,
        direction=signal.direction,
        requested_volume=intent.requested_volume,
        approved_volume=signal.approved_volume,
        stop_loss=float(intent.stop_loss or 0.0),
        risk_decision=signal.risk_decision,
        risk_reason_code=str(signal.risk_reason_code or ""),
        control_mode=control_mode,
        signal_timestamp=signal.timestamp,
        plan_created_timestamp=signal.timestamp + timedelta(microseconds=1),
        order_type="MARKET",
        volume_unit=VOLUME_UNIT_UNRESOLVED,
        plan_state=plan_state,
        executable=executable,
    )


def main() -> None:
    """Перевірити canonical plan fields та зафіксувати volume blocker."""
    hashes_before = production_hashes()
    risk_constants = source_text("engine/risk/constants.py")
    risk_model = source_text("engine/risk/risk_model.py")
    runtime_engine = source_text("engine/runtime_engine.py")
    ctrader_lot = source_text("core/ctrader_lot.py")
    schema = source_text("engine/db/runtime_db.py")
    controller = source_text("core/algorithm_workspace_controller.py")
    workspace_runtime = source_text("core/workspace_runtime.py")
    record_signal = source_section(
        "core/workspace_runtime.py",
        "    def _record_signal(",
        "    def _evaluate_signal_risk(",
    )
    manual_path = source_section(
        "engine/runtime_engine.py",
        "    def place_manual_market_order(",
        "    @staticmethod\n    def _normalize_optional_protection_price(",
    )
    ib_conversion = source_section(
        "engine/runtime_engine.py",
        "    def _ib_lots_to_fx_quantity(",
        "    @staticmethod\n    def _get_position_symbol_text(",
    )

    plan_fields = tuple(field.name for field in fields(TestOnlyWorkspaceExecutionPlan))
    identity_fields = (
        "workspace_uid",
        "signal_uid",
        "broker",
        "account_id",
        "symbol",
    )
    risk_fields = (
        "requested_volume",
        "approved_volume",
        "stop_loss",
        "risk_decision",
        "risk_reason_code",
    )
    control_fields = ("control_mode", "plan_state", "executable")
    timestamp_fields = ("signal_timestamp", "plan_created_timestamp")

    risk_volume_has_no_unit = all(
        token not in risk_model
        for token in ("volume_unit", "BASE_UNITS", "LOTS", "BROKER_NATIVE")
    )
    risk_default_is_1000 = (
        all(
            token in risk_constants
            for token in (
                "DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME = 1000.0",
                "WORKSPACE_RISK_SETTING_MAXIMUM_POSITION_VOLUME = "
                '"maximum_position_volume"',
            )
        )
        and DEFAULT_WORKSPACE_MAXIMUM_POSITION_VOLUME == 1000.0
    )
    approved_copies_requested = (
        "approved_volume = request.requested_volume" in risk_model
    )
    manual_boundary_is_lots = all(
        token in manual_path
        for token in (
            "lots: float",
            "lots=lots",
            "lots_float = float(lots)",
        )
    )
    ib_converts_lots_to_base_units = (
        all(
            token in ib_conversion
            for token in (
                "1.00 lot = 100000 units",
                "return round(lots_float * 100000.0, 2)",
            )
        )
        and "quantity_float = self._ib_lots_to_fx_quantity(lots_float)"
        in runtime_engine
    )
    ctrader_converts_lots_to_api_volume = all(
        token in ctrader_lot
        for token in (
            "API_VOLUME_PER_1_LOT_FX = 10_000_000",
            "def lots_to_api_volume(lots: float)",
        )
    ) and "api_volume = ctr_lot.lots_to_api_volume(normalized_lots)" in source_text(
        "engine/ctrader_adapter.py"
    )
    volume_contract_resolved = False

    trade_columns = schema_columns(schema, "trades")
    order_plan_columns = schema_columns(schema, "order_plans")
    existing_dto_reusable = any(
        token in workspace_runtime
        for token in ("WorkspaceExecutionPlan", "WorkspaceOrderPlan")
    )
    schema_has_identity = all(
        field_name in trade_columns or field_name in order_plan_columns
        for field_name in ("workspace_uid", "signal_uid")
    )
    controller_has_engine_and_runtime = all(
        token in controller
        for token in (
            "self._runtime_engine",
            "self._runtimes",
            "RuntimeEngineWorkspaceMarketProvider(runtime_engine)",
        )
    )
    runtime_has_engine_access = "self._runtime_engine" in source_section(
        "core/workspace_runtime.py",
        "    def __init__(",
        "    @property\n    def workspace_uid(",
    )
    risk_gate_precedes_plan_gap = all(
        token in record_signal
        for token in (
            "risk_decision = self._evaluate_signal_risk(",
            "accepted = risk_decision.allowed",
        )
    ) and all(
        token not in record_signal
        for token in ("create_order_plan(", "place_market_order(")
    )

    binding = WorkspaceBinding(
        workspace_uid="6c18b50f-dfea-45f5-9cbd-b68d53eb1c45",
        broker="CTRADER",
        account_id="T10910-DEMO",
        symbol="EURUSD",
    )
    intent = WorkspaceTradeIntent(
        requested_volume=1000.0,
        estimated_loss_at_stop=1.0,
        stop_loss=1.09,
        signal_uid="t109-10-signal",
    )
    allowed_signal = signal_record(
        accepted=True,
        risk_decision="ALLOW",
        approved_volume=1000.0,
    )
    rejected_signal = signal_record(
        accepted=False,
        risk_decision=None,
        approved_volume=None,
    )
    blocked_signal = signal_record(
        accepted=True,
        risk_decision="BLOCK",
        approved_volume=None,
    )
    missing_risk_signal = signal_record(
        accepted=True,
        risk_decision=None,
        approved_volume=None,
    )

    auto_plan = create_test_only_plan(
        allowed_signal,
        intent,
        binding,
        control_mode="AUTO",
    )
    semi_plan = create_test_only_plan(
        allowed_signal,
        intent,
        binding,
        control_mode="SEMI",
        confirmed=False,
    )
    opposite_plan = create_test_only_plan(
        allowed_signal,
        replace(intent, signal_uid=allowed_signal.signal_uid),
        binding,
        control_mode="AUTO",
        opposite_direction=True,
        confirmed_flat=False,
    )
    rejected_plan = create_test_only_plan(
        rejected_signal,
        intent,
        binding,
        control_mode="AUTO",
    )
    blocked_plan = create_test_only_plan(
        blocked_signal,
        intent,
        binding,
        control_mode="AUTO",
    )
    missing_risk_plan = create_test_only_plan(
        missing_risk_signal,
        intent,
        binding,
        control_mode="AUTO",
    )

    accepted_allowed_plan_created = auto_plan is not None
    rejected_signal_plan_created = rejected_plan is not None
    risk_blocked_plan_created = blocked_plan is not None
    missing_risk_plan_created = missing_risk_plan is not None
    identity_contract_verified = bool(
        auto_plan is not None
        and auto_plan.workspace_uid == allowed_signal.workspace_uid
        and auto_plan.signal_uid == allowed_signal.signal_uid
        and auto_plan.broker == binding.broker
        and auto_plan.account_id == binding.account_id
        and auto_plan.symbol == binding.symbol
    )
    risk_contract_verified = bool(
        accepted_allowed_plan_created
        and not rejected_signal_plan_created
        and not risk_blocked_plan_created
        and not missing_risk_plan_created
    )
    control_mode_contract_verified = bool(
        auto_plan is not None
        and semi_plan is not None
        and auto_plan.control_mode == "AUTO"
        and semi_plan.control_mode == "SEMI"
        and semi_plan.plan_state == PLAN_STATE_PENDING_CONFIRMATION
        and not semi_plan.executable
    )
    timestamp_contract_verified = bool(
        auto_plan is not None
        and auto_plan.plan_created_timestamp >= auto_plan.signal_timestamp
    )
    reverse_contract_verified = bool(
        opposite_plan is not None
        and opposite_plan.plan_state == PLAN_STATE_BLOCKED_CONFIRMED_FLAT
        and not opposite_plan.executable
    )

    assert plan_fields == (
        "workspace_uid",
        "signal_uid",
        "broker",
        "account_id",
        "symbol",
        "direction",
        "requested_volume",
        "approved_volume",
        "stop_loss",
        "risk_decision",
        "risk_reason_code",
        "control_mode",
        "signal_timestamp",
        "plan_created_timestamp",
        "order_type",
        "volume_unit",
        "plan_state",
        "executable",
    )
    assert risk_volume_has_no_unit
    assert risk_default_is_1000
    assert approved_copies_requested
    assert manual_boundary_is_lots
    assert ib_converts_lots_to_base_units
    assert ctrader_converts_lots_to_api_volume
    assert not volume_contract_resolved
    assert not existing_dto_reusable
    assert not schema_has_identity
    assert controller_has_engine_and_runtime
    assert not runtime_has_engine_access
    assert risk_gate_precedes_plan_gap
    assert accepted_allowed_plan_created
    assert not rejected_signal_plan_created
    assert not risk_blocked_plan_created
    assert not missing_risk_plan_created
    assert identity_contract_verified
    assert risk_contract_verified
    assert control_mode_contract_verified
    assert timestamp_contract_verified
    assert reverse_contract_verified
    assert auto_plan is not None and not auto_plan.executable

    broker_requests = 0
    broker_execution_attempted = False
    hashes_after = production_hashes()
    assert hashes_before == hashes_after

    print(f"test_id={TEST_ID}")
    print("canonical_plan_contract_fields=" + ",".join(plan_fields))
    print("canonical_plan_identity_fields=" + ",".join(identity_fields))
    print("canonical_plan_risk_fields=" + ",".join(risk_fields))
    print("canonical_plan_control_fields=" + ",".join(control_fields))
    print("canonical_plan_timestamp_fields=" + ",".join(timestamp_fields))
    print(
        "requested_volume_semantics=positive Workspace risk-policy value; "
        "unit is not declared in production risk contract"
    )
    print(
        "approved_volume_semantics=ALLOW copies requested_volume after risk guards; "
        "unit remains undeclared"
    )
    print(f"canonical_volume_unit={VOLUME_UNIT_UNRESOLVED}")
    print(
        "ib_volume_conversion_boundary=RuntimeEngine manual lots -> "
        "IB Forex quantity; 1 lot=100000 base units"
    )
    print(
        "ctrader_volume_conversion_boundary=CTraderAdapter lots -> Open API volume; "
        "1 lot=10000000 API volume"
    )
    print(f"volume_contract_resolved={volume_contract_resolved}")
    print(
        "auto_plan_contract=accepted+risk ALLOW creates plan candidate; executable "
        "state is blocked until volume unit contract is resolved"
    )
    print(
        "auto_plan_executable_without_confirmation="
        f"{bool(auto_plan and auto_plan.executable)}"
    )
    print(
        "semi_plan_contract=accepted+risk ALLOW creates PENDING_CONFIRMATION plan; "
        "only confirmed plan may advance toward executable eligibility"
    )
    print("semi_confirmation_required=True")
    print(f"semi_unconfirmed_executable={bool(semi_plan and semi_plan.executable)}")
    print("reverse_confirmed_flat_required=True")
    print(
        "opposite_plan_executable_without_confirmed_flat="
        f"{bool(opposite_plan and opposite_plan.executable)}"
    )
    print(f"accepted_allowed_plan_created={accepted_allowed_plan_created}")
    print(f"rejected_signal_plan_created={rejected_signal_plan_created}")
    print(f"risk_blocked_plan_created={risk_blocked_plan_created}")
    print(f"missing_risk_plan_created={missing_risk_plan_created}")
    print(f"identity_contract_verified={identity_contract_verified}")
    print(f"risk_contract_verified={risk_contract_verified}")
    print(f"control_mode_contract_verified={control_mode_contract_verified}")
    print(f"timestamp_contract_verified={timestamp_contract_verified}")
    print(f"reverse_contract_verified={reverse_contract_verified}")
    print(f"existing_dto_reusable={existing_dto_reusable}")
    print("dto_change_required=True: new immutable WorkspaceExecutionPlan DTO")
    print("schema_change_required=True: causal Workspace/signal identity persistence")
    print("production_contract_change_required=True")
    print(
        "candidate_owner_layer=AlgorithmWorkspaceController: factual holder of "
        "RuntimeEngine access and WorkspaceRuntime registry"
    )
    print(
        "candidate_execution_orchestration_boundary=controller-owned plan handoff "
        "to RuntimeEngine; production API not implemented"
    )
    print(f"first_unresolved_contract={FIRST_UNRESOLVED_CONTRACT}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_execution_wiring_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_10_WORKSPACE_EXECUTION_PLAN_CANONICAL_CONTRACT=OK")


if __name__ == "__main__":
    main()
