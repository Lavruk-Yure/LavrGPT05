from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENGINE = ROOT / "engine" / "runtime_engine.py"
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"
CTRADER_ADAPTER = ROOT / "engine" / "ctrader_adapter.py"
IB_SERVICE = ROOT / "engine" / "services" / "ib_runtime_service.py"
CTRADER_SERVICE = ROOT / "engine" / "services" / "ctrader_runtime_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    engine = _read(RUNTIME_ENGINE)
    ib_adapter = _read(IB_ADAPTER)
    ctrader_adapter = _read(CTRADER_ADAPTER)
    ib_service = _read(IB_SERVICE)
    ctrader_service = _read(CTRADER_SERVICE)

    workspace_submit_present = "def submit_workspace_execution_plan(" in engine
    workspace_reconciler_present = "def reconcile_workspace_broker_order(" in engine

    ib_submit_is_synchronous_terminal_fill = (
        "finished = self._wrapper.order_event.wait(" in ib_adapter
        and 'if status_text != "FILLED":' in ib_adapter
        and '"status": status_text' in ib_adapter
        and '"filled": float(status_row.get("filled", 0.0) or 0.0)' in ib_adapter
    )
    ib_service_returns_terminal_result_directly = (
        "return adapter.place_market_order(" in ib_service
        and "quantity=quantity" in ib_service
    )

    ctrader_waits_for_terminal_trade_event = (
        "return self._wait_for_trade_result(" in ctrader_adapter
        and "CTRADER_EXECUTION_TYPE_ORDER_FILLED" in ctrader_adapter
        and "CTRADER_EXECUTION_TYPE_ORDER_REJECTED" in ctrader_adapter
        and "self._trade_event.set()" in ctrader_adapter
    )
    ctrader_terminal_result_contains_position_evidence = (
        "self._trade_payload = payload" in ctrader_adapter
        and 'position = getattr(payload, "position", None)' in ctrader_adapter
        and 'getattr(position, "positionId", None)' in ctrader_adapter
    )
    ctrader_service_returns_terminal_result_directly = (
        "return adapter.place_market_order(" in ctrader_service
        and "lots=lots" in ctrader_service
    )

    submit_persists_broker_order_after_service_result = (
        "broker_result = service.place_market_order(" in engine
        and "broker_order_uid = self.repository.create_broker_order(" in engine
        and 'source="WORKSPACE"' in engine
    )
    submit_retains_exact_identity_after_persistence = (
        '"trade_uid": trade_uid_clean' in engine
        and '"order_plan_uid": order_plan_uid_clean' in engine
        and '"broker_order_uid": broker_order_uid' in engine
    )
    submit_calls_workspace_reconciler = (
        "self.reconcile_workspace_broker_order(" in engine.split(
            "def submit_workspace_execution_plan(", 1
        )[1].split("def reconcile_workspace_broker_order(", 1)[0]
    )
    submit_requests_post_submit_position_snapshot = (
        "get_workspace_broker_positions_snapshot(" in engine.split(
            "def submit_workspace_execution_plan(", 1
        )[1].split("def reconcile_workspace_broker_order(", 1)[0]
    )
    ib_manual_position_mapping_pattern_present = (
        "positions_after = service.get_positions()" in engine
        and "matched_position = self._find_ib_opened_manual_position(" in engine
    )
    ctrader_manual_position_mapping_pattern_present = (
        "matched_position = self._find_opened_manual_position(" in engine
        and "expected_position_id = self._extract_broker_position_id(broker_result)"
        in engine
    )
    same_call_flat_gate_precedes_workspace_submit = (
        "workspace_same_call_position_snapshot_confirms_flat(" in engine
        or "workspace_same_call_position_snapshot_confirms_flat(" in _read(
            ROOT / "core" / "algorithm_workspace_controller.py"
        )
    )

    assert workspace_submit_present
    assert workspace_reconciler_present
    assert ib_submit_is_synchronous_terminal_fill
    assert ib_service_returns_terminal_result_directly
    assert ctrader_waits_for_terminal_trade_event
    assert ctrader_terminal_result_contains_position_evidence
    assert ctrader_service_returns_terminal_result_directly
    assert submit_persists_broker_order_after_service_result
    assert submit_retains_exact_identity_after_persistence
    assert not submit_calls_workspace_reconciler
    assert not submit_requests_post_submit_position_snapshot
    assert ib_manual_position_mapping_pattern_present
    assert ctrader_manual_position_mapping_pattern_present
    assert same_call_flat_gate_precedes_workspace_submit

    print("T109-55_BROKER_CONFIRMATION_SOURCE_TO_WORKSPACE_RECONCILER_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("workspace_submit_present=True")
    print("workspace_reconciler_present=True")
    print("ib_submit_returns_only_after_terminal_fill=True")
    print("ib_terminal_result_reaches_runtime_engine_synchronously=True")
    print("ctrader_waits_for_filled_or_rejected_terminal_event=True")
    print("ctrader_terminal_result_contains_position_identity_evidence=True")
    print("ctrader_terminal_result_reaches_runtime_engine_synchronously=True")
    print("workspace_broker_order_persisted_after_terminal_result=True")
    print("workspace_trade_order_plan_broker_order_identity_available=True")
    print("same_call_flat_gate_precedes_workspace_submit=True")
    print("workspace_submit_calls_reconciler=False")
    print("workspace_submit_requests_post_submit_position_snapshot=False")
    print("manual_ib_post_submit_position_mapping_pattern_present=True")
    print("manual_ctrader_post_submit_position_mapping_pattern_present=True")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_TERMINAL_BROKER_RESULT_TO_CONFIRMED_POSITION_MAPPING"
    )
    print(
        "boundary_contract=WORKSPACE_SUBMIT_ALREADY_RECEIVES_TERMINAL_BROKER_"
        "RESULT_AND_PERSISTS_EXACT_BROKER_ORDER_IDENTITY_BUT_MUST_MAP_A_"
        "BROKER_CONFIRMED_POSITION_AND_CALL_THE_IDEMPOTENT_RECONCILER_"
        "WITHOUT_CREATING_A_SECOND_TRADE_ORDER_PLAN_OR_BROKER_ORDER"
    )
    print(
        "factual_verdict=B. TERMINAL_CONFIRMATION_SOURCE_PRESENT_BUT_"
        "WORKSPACE_CONFIRMED_POSITION_MAPPING_IS_NOT_WIRED"
    )


if __name__ == "__main__":
    main()
