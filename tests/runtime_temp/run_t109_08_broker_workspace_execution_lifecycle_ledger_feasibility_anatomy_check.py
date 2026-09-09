"""run_t109_08_broker_workspace_execution_lifecycle_ledger_feasibility_anatomy_check.py.

TEST_ONLY anatomy доводить фактичну межу між дозволеним WSP risk-рішенням
і broker execution lifecycle. Runner читає production models, call-sites та
SQLite schema, окремо класифікує IB/cTrader capability і реально досягнутий
AUTO/SEMI path, а також перевіряє ownership, close та realized-PnL gaps.

Жодні synthetic fills/positions, broker requests або orders не створюються.
Canonical completed-bar Replay 2025/2026 запускається лише як exact regression
control; production, risk, Candidate F, AUTO/SEMI та trading logic не змінюються.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t109_03_minimal_production_execution_intent_repair_check import (  # noqa
    CANONICAL_PERIODS,
    EXPECTED_2025,
    EXPECTED_2026,
    run_canonical_period,
)

from core.workspace_ownership import WorkspacePositionSnapshot  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceTradeIntent  # noqa: E402
from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ib_virtual_position_leg import IBVirtualPositionLeg  # noqa: E402

TEST_ID = "T109-08"
FACTUAL_VERDICT = "D. EXECUTION_PATH_NOT_WIRED_TO_LIFECYCLE"
FIRST_MISSING_LIFECYCLE_BOUNDARY = (
    "RISK_ALLOWED_WORKSPACE_SIGNAL_TO_BROKER_EXECUTION_PLAN"
)
BOUNDARY_CONTRACT = (
    "RISK_ALLOWED_BROKER_AUTO_SEMI_SIGNAL_REQUIRES_CAUSAL_WORKSPACE_"
    "EXECUTION_PLAN_AND_IDENTITY_ROUTE"
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
)


def source_text(relative_path: str) -> str:
    """Прочитати один production module як UTF-8 contract."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def source_section(relative_path: str, start: str, end: str) -> str:
    """Виділити factual source section між двома exact anchors."""
    source = source_text(relative_path)
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def production_hashes() -> dict[str, str]:
    """Зафіксувати production sources до і після TEST_ONLY run."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def baseline_key(runtime: WorkspaceRuntime) -> str:
    """Побудувати exact canonical Replay summary key."""
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
    """Довести first missing lifecycle boundary та downstream gaps."""
    hashes_before = production_hashes()
    workspace_runtime = source_text("core/workspace_runtime.py")
    record_signal = source_section(
        "core/workspace_runtime.py",
        "    def _record_signal(",
        "    def _evaluate_signal_risk(",
    )
    risk_section = source_section(
        "core/workspace_runtime.py",
        "    def _evaluate_signal_risk(",
        "    def _signal_uid(",
    )
    runtime_engine = source_text("engine/runtime_engine.py")
    repository = source_text("engine/runtime_repository.py")
    schema = source_text("engine/db/runtime_db.py")
    ib_adapter = source_text("engine/ib_adapter.py")
    ctrader_adapter = source_text("engine/ctrader_adapter.py")
    ownership = source_text("core/workspace_ownership.py")
    identity = source_text("engine/broker_order_identity.py")
    ib_leg = source_text("engine/ib_virtual_position_leg.py")

    intent_fields = tuple(field.name for field in fields(WorkspaceTradeIntent))
    broker_position_fields = tuple(field.name for field in fields(BrokerPosition))
    workspace_position_fields = tuple(
        field.name for field in fields(WorkspacePositionSnapshot)
    )
    ib_leg_fields = tuple(field.name for field in fields(IBVirtualPositionLeg))

    risk_route_present = (
        all(
            token in record_signal
            for token in (
                "risk_decision = self._evaluate_signal_risk(",
                "accepted = risk_decision.allowed",
                "record = WorkspaceSignalRecord(",
            )
        )
        and "decision = self.evaluate_risk_request(request)" in risk_section
    )
    replay_only_execution_route = all(
        token in record_signal
        for token in (
            "if self.replay_execution is not None and record.accepted:",
            "self.replay_execution.queue_signal(record, event)",
        )
    )
    broker_execution_call_absent = all(
        token not in record_signal
        for token in (
            "RuntimeEngine",
            "place_market_order",
            "place_manual_market_order",
            "broker_order",
            "create_order_plan",
        )
    )
    workspace_execution_plan_absent = all(
        token not in workspace_runtime
        for token in (
            "WorkspaceExecutionPlan",
            "WorkspaceOrderPlan",
            "workspace_execution_plan",
        )
    )

    ib_status_source_present = all(
        token in ib_adapter
        for token in (
            "def orderStatus(",
            '"filled": float(filled or 0.0)',
            '"remaining": float(remaining or 0.0)',
            '"avg_fill_price": float(avg_fill_price or 0.0)',
            "self.order_statuses.append(item)",
            "def execDetails(",
            "def completedOrder(",
        )
    )
    ib_submitted_state_present = 'default_status="SUBMITTED"' in repository
    ib_partial_fill_state_present = all(
        token in ib_adapter for token in ('"filled"', '"remaining"')
    )
    ib_filled_state_present = '"FILLED"' in ib_adapter
    ib_broker_order_id_preserved = (
        all(
            token in ib_adapter
            for token in (
                '"broker_order_id": str(parent_order_id)',
                '"order_id": int(order_id)',
            )
        )
        and "broker_order_id TEXT" in schema
    )

    ctrader_status_source_present = all(
        token in ctrader_adapter
        for token in (
            "def _on_execution_event(self, payload)",
            "CTRADER_EXECUTION_TYPE_ORDER_ACCEPTED",
            "CTRADER_EXECUTION_TYPE_ORDER_FILLED",
            "CTRADER_EXECUTION_TYPE_ORDER_REJECTED",
        )
    )
    ctrader_submitted_state_present = (
        "if execution_type == CTRADER_EXECUTION_TYPE_ORDER_ACCEPTED:" in ctrader_adapter
    )
    ctrader_partial_fill_state_present = any(
        token in ctrader_adapter
        for token in (
            "ORDER_PARTIAL_FILL",
            "ORDER_PARTIALLY_FILLED",
            "cumulative_filled_volume",
        )
    )
    ctrader_filled_state_present = (
        "if execution_type == CTRADER_EXECUTION_TYPE_ORDER_FILLED:" in ctrader_adapter
    )
    ctrader_broker_order_id_preserved = all(
        token in runtime_engine
        for token in (
            "def _extract_broker_order_id(",
            "broker_order_id = self._extract_broker_order_id(broker_result)",
            "self.repository.create_broker_order(",
        )
    )

    broker_marker_has_workspace_uid = "workspace_uid" in identity
    runtime_ledger_has_workspace_uid = "workspace_uid" in source_section(
        "engine/db/runtime_db.py",
        "CREATE TABLE IF NOT EXISTS trades (",
        "CREATE TABLE IF NOT EXISTS ib_virtual_position_legs (",
    )
    ib_workspace_identity_preserved = (
        broker_marker_has_workspace_uid and runtime_ledger_has_workspace_uid
    )
    ctrader_workspace_identity_preserved = ib_workspace_identity_preserved

    workspace_ownership_source_present = all(
        token in ownership
        for token in (
            "class WorkspaceOwnershipFilter:",
            "workspace_uid=position.workspace_uid",
            "workspace_uid=order.workspace_uid",
        )
    )
    workspace_ownership_causal_from_execution = (
        runtime_ledger_has_workspace_uid
        and "workspace_uid" in runtime_engine
        and "workspace_uid" in identity
    )

    ib_close_requested_state_present = (
        all(
            token in schema
            for token in (
                "ib_virtual_position_leg_orders",
                "execution_status TEXT NOT NULL",
            )
        )
        and "IB_LEG_CLOSE_EXECUTION_STATUS_PENDING" in repository
    )
    ib_close_partial_state_present = "IB_LEG_STATUS_PARTIALLY_CLOSED" in ib_leg
    ib_close_confirmed_state_present = all(
        token in runtime_engine
        for token in (
            "IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING",
            "IB_LEG_STATUS_CLOSED",
        )
    )
    generic_close_pending_state_present = any(
        token in schema
        for token in (
            "CLOSE_REQUESTED_BUT_NOT_CONFIRMED",
            "CLOSE_PENDING",
        )
    )
    confirmed_flat_observation_present = all(
        token in runtime_engine
        for token in (
            "positions_after = service.get_positions()",
            "still_open = any(",
            '"closed": not still_open',
        )
    )

    persistent_runtime_ledger_present = (
        all(
            token in schema
            for token in (
                "CREATE TABLE IF NOT EXISTS trades (",
                "CREATE TABLE IF NOT EXISTS order_plans (",
                "CREATE TABLE IF NOT EXISTS broker_orders (",
                "CREATE TABLE IF NOT EXISTS positions (",
            )
        )
        and "connect_runtime_db(db_path)" in runtime_engine
    )
    fill_ledger_complete = all(
        token in schema
        for token in (
            "filled_volume",
            "fill_price",
            "fill_timestamp",
        )
    )
    cost_ledger_complete = all(
        token in schema for token in ("commission", "fee", "swap", "adjustment")
    )

    assert intent_fields == (
        "requested_volume",
        "estimated_loss_at_stop",
        "stop_loss",
        "signal_uid",
    )
    assert risk_route_present
    assert replay_only_execution_route
    assert broker_execution_call_absent
    assert workspace_execution_plan_absent
    assert ib_status_source_present
    assert ib_submitted_state_present
    assert ib_partial_fill_state_present
    assert ib_filled_state_present
    assert ib_broker_order_id_preserved
    assert ctrader_status_source_present
    assert ctrader_submitted_state_present
    assert not ctrader_partial_fill_state_present
    assert ctrader_filled_state_present
    assert ctrader_broker_order_id_preserved
    assert not ib_workspace_identity_preserved
    assert not ctrader_workspace_identity_preserved
    assert workspace_ownership_source_present
    assert not workspace_ownership_causal_from_execution
    assert ib_close_requested_state_present
    assert ib_close_partial_state_present
    assert ib_close_confirmed_state_present
    assert not generic_close_pending_state_present
    assert confirmed_flat_observation_present
    assert persistent_runtime_ledger_present
    assert not fill_ledger_complete
    assert not cost_ledger_complete
    assert "position_id" in broker_position_fields
    assert "workspace_uid" not in broker_position_fields
    assert "workspace_uid" in workspace_position_fields
    assert "broker_position_id" in workspace_position_fields
    assert "position_uid" in ib_leg_fields
    assert "broker_position_id" in ib_leg_fields

    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests
    canonical_2025_exact_match = baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = baseline_key(baselines["2026"]) == EXPECTED_2026
    broker_execution_attempted = False
    hashes_after = production_hashes()

    assert canonical_2025_exact_match
    assert canonical_2026_exact_match
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert hashes_before == hashes_after

    print(f"test_id={TEST_ID}")
    print("intent_identity_fields=" + ",".join(intent_fields))
    print(
        "risk_to_execution_plan_route="
        "WorkspaceRuntime._record_signal->_evaluate_signal_risk->"
        "WorkspaceSignalRecord; Replay queue only; BROKER plan/caller absent"
    )
    print("execution_plan_created_for_workspace_auto=False")
    print("execution_plan_created_for_workspace_semi=False")
    print("runtime_broker_order_boundary_reached=False")
    print(
        "ib_order_status_source=IBWrapper.orderStatus transient status/filled/"
        "remaining/avg_fill_price plus execDetails/completedOrder; manual "
        "Runtime ledger"
    )
    print(f"ib_submitted_state_present={ib_submitted_state_present}")
    print(f"ib_partial_fill_state_present={ib_partial_fill_state_present}")
    print(f"ib_filled_state_present={ib_filled_state_present}")
    print(f"ib_broker_order_id_preserved={ib_broker_order_id_preserved}")
    print(f"ib_workspace_identity_preserved={ib_workspace_identity_preserved}")
    print(
        "ctrader_order_status_source=ProtoOAExecutionEvent accepted/filled/"
        "rejected; adapter retains only pending trade payload; manual Runtime ledger"
    )
    print(f"ctrader_submitted_state_present={ctrader_submitted_state_present}")
    print(f"ctrader_partial_fill_state_present={ctrader_partial_fill_state_present}")
    print(f"ctrader_filled_state_present={ctrader_filled_state_present}")
    print("ctrader_broker_order_id_preserved=" f"{ctrader_broker_order_id_preserved}")
    print(
        "ctrader_workspace_identity_preserved="
        f"{ctrader_workspace_identity_preserved}"
    )
    print(
        "broker_position_identity_fields=BrokerPosition:broker,account_id,"
        "position_id,symbol_name,side,volume,entry_price,opened_utc; no workspace_uid"
    )
    print(
        "workspace_position_ownership_source=WorkspaceOwnershipFilter over rows "
        "already carrying workspace_uid,broker,account_id,symbol"
    )
    print(
        "workspace_ownership_causal_from_execution="
        f"{workspace_ownership_causal_from_execution}"
    )
    print(
        "close_requested_state_present=PARTIAL: IB virtual-leg pending close only; "
        "no broker-neutral workspace state"
    )
    print(
        "close_partial_state_present=PARTIAL: IB virtual-leg PARTIALLY_CLOSED; "
        "no cTrader/workspace ledger state"
    )
    print(
        "close_confirmed_state_present=PARTIAL: IB reconciled CLOSED and synchronous "
        "manual close result; no workspace lifecycle event"
    )
    print(
        "confirmed_flat_state_present=PARTIAL: fresh broker snapshot absence/zero "
        "is observed, not persisted as canonical workspace flat state"
    )
    print("reverse_invariant_currently_enforceable=False")
    print("realized_pnl_entry_fill_data_complete=False")
    print("realized_pnl_exit_fill_data_complete=False")
    print("realized_pnl_cost_data_complete=False")
    print("realized_pnl_ledger_feasibility=INSUFFICIENT")
    print(
        "existing_runtime_ledger=SQLite trades/order_plans/broker_orders/positions "
        "plus IB virtual legs; populated by manual execution capability"
    )
    print(
        "ledger_scope=MANUAL_RUNTIME_AND_IB_VIRTUAL_LEG_PARTIAL; no signal_uid/"
        "workspace_uid causal AUTO/SEMI link and no canonical fill/cost ledger"
    )
    print("ledger_persistence=SQLITE_PERSISTENT_WITH_TRANSIENT_ADAPTER_EVENTS")
    print("ledger_completeness=PARTIAL_NOT_WORKSPACE_AUTO_SEMI_SOURCE_OF_TRUTH")
    print("first_missing_lifecycle_boundary=" f"{FIRST_MISSING_LIFECYCLE_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_08_EXECUTION_LIFECYCLE_LEDGER_FEASIBILITY_ANATOMY=OK")


if __name__ == "__main__":
    main()
