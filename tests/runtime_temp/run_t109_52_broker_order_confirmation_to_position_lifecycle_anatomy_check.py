from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_project_root() / relative_path).read_text(encoding="utf-8")


def _method_body(source: str, method_name: str) -> str:
    marker = f"    def {method_name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"Method not found: {method_name}")

    next_start = source.find("\n    def ", start + len(marker))
    if next_start < 0:
        return source[start:]
    return source[start:next_start]


def main() -> None:
    runtime_engine = _read("engine/runtime_engine.py")
    repository = _read("engine/runtime_repository.py")
    ib_adapter = _read("engine/ib_adapter.py")
    ctrader_adapter = _read("engine/ctrader_adapter.py")

    workspace_submit = _method_body(
        runtime_engine,
        "submit_workspace_execution_plan",
    )
    ib_place = _method_body(ib_adapter, "place_market_order")

    ctrader_execution = _method_body(ctrader_adapter, "_on_execution_event")
    ctrader_wait = _method_body(ctrader_adapter, "_wait_for_trade_result")
    manual_ib = _method_body(runtime_engine, "_place_manual_market_order_ib")
    manual_ctrader = _method_body(runtime_engine, "place_manual_market_order")

    workspace_broker_order_identity_preserved = all(
        token in workspace_submit
        for token in (
            "trade_uid=trade_uid_clean",
            "order_plan_uid=order_plan_uid_clean",
            'source="WORKSPACE"',
        )
    )
    workspace_position_created_after_submit = "create_position(" in workspace_submit
    workspace_submit_declares_deferred_position = (
        "Position створюється\n        окремо після broker confirmation/reconciliation."
        in workspace_submit
    )

    ib_waits_for_terminal_fill = all(
        token in ib_place
        for token in (
            'status_text != "FILLED"',
            "IBMarketOrderTimeoutError",
            'raise RuntimeError(f"IB MARKET order was not filled: {status_text}")',
        )
    )
    ib_fill_result_has_identity_evidence = all(
        token in ib_place
        for token in (
            '"broker_order_id": str(parent_order_id)',
            '"filled": float(status_row.get("filled", 0.0) or 0.0)',
            '"avg_fill_price": float(status_row.get("avg_fill_price", 0.0) or 0.0)',
        )
    )

    ctrader_waits_for_filled_or_error = (
        all(
            token in ctrader_execution
            for token in (
                "CTRADER_EXECUTION_TYPE_ORDER_ACCEPTED",
                "CTRADER_EXECUTION_TYPE_ORDER_FILLED",
                "CTRADER_EXECUTION_TYPE_ORDER_REJECTED",
                "self._trade_event.set()",
            )
        )
        and "return self._trade_payload" in ctrader_wait
    )

    manual_ib_persists_position_after_confirmation = all(
        token in manual_ib
        for token in (
            "positions_before = service.get_positions()",
            "positions_after = service.get_positions()",
            "self.repository.create_position(",
        )
    )
    manual_ctrader_persists_position_after_confirmation = all(
        token in manual_ctrader
        for token in (
            "positions_before = service.get_positions()",
            "positions_after = service.get_positions()",
            "self.repository.create_position(",
        )
    )

    repository_position_links_trade_and_broker_order = all(
        token in repository
        for token in (
            "def create_position(",
            "trade_uid: str",
            "broker_order_uid: str",
            "INSERT INTO positions",
        )
    )
    repository_can_update_broker_order_status = (
        "def update_broker_order_execution_status(" in repository
    )

    workspace_specific_position_reconciliation_present = any(
        token in runtime_engine
        for token in (
            "reconcile_workspace_broker_order",
            "recover_workspace_broker_order",
            "persist_workspace_position_after_confirmation",
            "confirm_workspace_broker_order_position",
        )
    )

    partial_fill_state_persisted_for_workspace = (
        "PARTIAL" in workspace_submit or "PARTIALLY_FILLED" in workspace_submit
    )
    reject_cancel_state_persisted_for_workspace = any(
        token in workspace_submit
        for token in (
            '"REJECTED"',
            '"CANCELLED"',
            '"CANCELED"',
        )
    )

    assert workspace_broker_order_identity_preserved
    assert not workspace_position_created_after_submit
    assert workspace_submit_declares_deferred_position
    assert ib_waits_for_terminal_fill
    assert ib_fill_result_has_identity_evidence
    assert ctrader_waits_for_filled_or_error
    assert manual_ib_persists_position_after_confirmation
    assert manual_ctrader_persists_position_after_confirmation
    assert repository_position_links_trade_and_broker_order
    assert repository_can_update_broker_order_status
    assert not workspace_specific_position_reconciliation_present
    assert not partial_fill_state_persisted_for_workspace
    assert not reject_cancel_state_persisted_for_workspace

    print("T109-52_BROKER_ORDER_CONFIRMATION_TO_POSITION_LIFECYCLE_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("workspace_broker_order_identity_preserved=True")
    print("workspace_position_created_after_submit=False")
    print("workspace_submit_declares_deferred_position=True")
    print("ib_waits_for_terminal_fill=True")
    print("ib_fill_result_has_identity_evidence=True")
    print("ctrader_waits_for_filled_or_error=True")
    print("manual_ib_persists_position_after_confirmation=True")
    print("manual_ctrader_persists_position_after_confirmation=True")
    print("repository_position_links_trade_and_broker_order=True")
    print("repository_can_update_broker_order_status=True")
    print("workspace_specific_position_reconciliation_present=False")
    print("workspace_partial_fill_state_persisted=False")
    print("workspace_reject_cancel_state_persisted=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_SUBMITTED_BROKER_ORDER_TO_PERSISTED_POSITION_RECONCILIATION"
    )
    print(
        "boundary_contract=WORKSPACE_BROKER_ORDER_MUST_REUSE_PERSISTED_"
        "TRADE_ORDER_PLAN_BROKER_ORDER_IDENTITY_AND_CREATE_OR_REUSE_POSITION_"
        "ONLY_FROM_BROKER_CONFIRMED_FILL_OR_RECONCILIATION"
    )
    print(
        "factual_verdict=B. BROKER_CONFIRMATION_EXISTS_BUT_WORKSPACE_POSITION_"
        "RECONCILIATION_IS_NOT_WIRED"
    )


if __name__ == "__main__":
    main()
