from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENGINE = ROOT / "engine" / "runtime_engine.py"
RUNTIME_REPOSITORY = ROOT / "engine" / "runtime_repository.py"
RUNTIME_DB = ROOT / "engine" / "db" / "runtime_db.py"
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"
CTRADER_ADAPTER = ROOT / "engine" / "ctrader_adapter.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    engine = _read(RUNTIME_ENGINE)
    repository = _read(RUNTIME_REPOSITORY)
    runtime_db = _read(RUNTIME_DB)
    ib_adapter = _read(IB_ADAPTER)
    ctrader_adapter = _read(CTRADER_ADAPTER)

    workspace_submit_declares_deferred_position = (
        "Position створюється\n        окремо після broker confirmation/reconciliation."
        in engine
    )
    workspace_submit_persists_broker_order = (
        "def submit_workspace_execution_plan(" in engine
        and 'source="WORKSPACE"' in engine
        and "broker_order_uid = self.repository.create_broker_order(" in engine
    )
    repository_position_links_trade_and_broker_order = (
        "def create_position(" in repository
        and "trade_uid: str" in repository
        and "broker_order_uid: str" in repository
        and "FOREIGN KEY (trade_uid) REFERENCES trades (trade_uid)" in runtime_db
        and "REFERENCES broker_orders (broker_order_uid)" in runtime_db
    )
    repository_position_lookup_by_trade_present = (
        "def get_position_by_trade_uid(" in repository
    )
    ib_manual_recovery_is_idempotent = (
        "position_row = self.repository.get_position_by_trade_uid(trade_uid)" in engine
        and "if position_row is None:" in engine
        and "self.repository.update_broker_order_execution_status(" in engine
    )
    ib_submit_requires_terminal_fill = (
        'if status_text != "FILLED":' in ib_adapter
        and 'raise RuntimeError(f"IB MARKET order was not filled: {status_text}")'
        in ib_adapter
    )
    ctrader_waits_for_fill_or_reject = (
        "CTRADER_EXECUTION_TYPE_ORDER_FILLED" in ctrader_adapter
        and "CTRADER_EXECUTION_TYPE_ORDER_REJECTED" in ctrader_adapter
        and "cTrader order filled" in ctrader_adapter
        and "cTrader order rejected" in ctrader_adapter
    )
    manual_ib_creates_position_from_confirmed_broker_state = (
        "matched_position = self._find_ib_opened_manual_position(" in engine
        and 'broker="IB"' in engine
        and 'state="OPEN"' in engine
    )
    manual_ctrader_creates_position_from_confirmed_broker_state = (
        "matched_position = self._find_opened_manual_position(" in engine
        and "broker_position_id=matched_position.position_id" in engine
        and "volume=matched_position.volume" in engine
    )
    workspace_reconciler_present = (
        "reconcile_workspace" in engine
        or "recover_workspace" in engine
        or "workspace_position_reconciliation" in engine
    )
    positions_have_unique_trade_guard = (
        "trade_uid TEXT NOT NULL UNIQUE" in runtime_db.split(
            "CREATE TABLE IF NOT EXISTS positions", 1
        )[1].split(
            "CREATE TABLE IF NOT EXISTS ib_virtual_position_legs", 1
        )[0]
    )
    positions_have_unique_broker_order_guard = (
        "broker_order_uid TEXT NOT NULL UNIQUE" in runtime_db.split(
            "CREATE TABLE IF NOT EXISTS positions", 1
        )[1].split(
            "CREATE TABLE IF NOT EXISTS ib_virtual_position_legs", 1
        )[0]
    )

    assert workspace_submit_declares_deferred_position
    assert workspace_submit_persists_broker_order
    assert repository_position_links_trade_and_broker_order
    assert repository_position_lookup_by_trade_present
    assert ib_manual_recovery_is_idempotent
    assert ib_submit_requires_terminal_fill
    assert ctrader_waits_for_fill_or_reject
    assert manual_ib_creates_position_from_confirmed_broker_state
    assert manual_ctrader_creates_position_from_confirmed_broker_state
    assert not workspace_reconciler_present
    assert not positions_have_unique_trade_guard
    assert not positions_have_unique_broker_order_guard

    print("T109-53_WORKSPACE_POSITION_RECONCILIATION_CONTRACT=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("workspace_submit_declares_deferred_position=True")
    print("workspace_submit_persists_broker_order_identity=True")
    print("repository_position_links_trade_and_broker_order=True")
    print("repository_position_lookup_by_trade_present=True")
    print("ib_terminal_fill_required_before_success=True")
    print("ctrader_terminal_fill_or_reject_event_present=True")
    print("manual_ib_confirmed_position_mapping_present=True")
    print("manual_ctrader_confirmed_position_mapping_present=True")
    print("existing_ib_recovery_idempotency_pattern_present=True")
    print("workspace_position_reconciler_present=False")
    print("position_db_unique_trade_guard_present=False")
    print("position_db_unique_broker_order_guard_present=False")
    print("recommended_position_creation_trigger=BROKER_CONFIRMED_POSITIVE_EXPOSURE")
    print("recommended_identity_root=TRADE_UID_ORDER_PLAN_UID_BROKER_ORDER_UID")
    print("recommended_full_fill_behavior=CREATE_OR_REUSE_OPEN_POSITION")
    print(
        "recommended_partial_fill_behavior="
        "CREATE_OR_UPDATE_ACTUAL_CONFIRMED_EXPOSURE"
    )
    print("recommended_reject_behavior=UPDATE_BROKER_ORDER_REJECTED_NO_POSITION")
    print(
        "recommended_cancel_zero_fill_behavior="
        "UPDATE_BROKER_ORDER_CANCELLED_NO_POSITION"
    )
    print(
        "recommended_cancel_partial_fill_behavior="
        "PERSIST_CONFIRMED_EXPOSURE_AND_TERMINAL_ORDER_STATUS"
    )
    print("recommended_duplicate_guard=LOOKUP_BY_TRADE_UID_BEFORE_CREATE")
    print(
        "recommended_reconciliation_authority="
        "BROKER_CONFIRMED_FILL_OR_POSITION_SNAPSHOT"
    )
    print("broker_requests=0")
    print("first_unresolved_boundary=WORKSPACE_POSITION_RECONCILER_PRODUCTION_WIRING")
    print(
        "boundary_contract=WORKSPACE_RECONCILER_MUST_REUSE_PERSISTED_IDENTITY_"
        "AND_CREATE_OR_UPDATE_POSITION_ONLY_FROM_CONFIRMED_BROKER_EXPOSURE_"
        "WHILE_REJECT_OR_ZERO_FILL_CANCEL_MUST_NOT_CREATE_POSITION"
    )
    print(
        "factual_verdict=A. WORKSPACE_POSITION_RECONCILIATION_CONTRACT_IDENTIFIED"
    )


if __name__ == "__main__":
    main()
