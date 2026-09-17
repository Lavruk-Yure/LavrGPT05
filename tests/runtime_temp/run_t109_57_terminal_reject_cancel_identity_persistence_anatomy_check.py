from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENGINE = ROOT / "engine" / "runtime_engine.py"
IB_ADAPTER = ROOT / "engine" / "ib_adapter.py"
IB_ERRORS = ROOT / "engine" / "ib_order_errors.py"
CTRADER_ADAPTER = ROOT / "engine" / "ctrader_adapter.py"
RUNTIME_REPOSITORY = ROOT / "engine" / "runtime_repository.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def main() -> None:
    engine = _read(RUNTIME_ENGINE)
    ib_adapter = _read(IB_ADAPTER)
    ib_errors = _read(IB_ERRORS)
    ctrader_adapter = _read(CTRADER_ADAPTER)
    repository = _read(RUNTIME_REPOSITORY)

    workspace_submit = _between(
        engine,
        "    def submit_workspace_execution_plan(",
        "    def reconcile_workspace_broker_order(",
    )
    ib_market_order = _between(
        ib_adapter,
        "    def place_market_order(",
        "    def close_position(",
    )
    ctrader_wait = _between(
        ctrader_adapter,
        "    def _wait_for_trade_result(",
        "    @staticmethod\n    def _start_reactor_if_needed",
    )
    ctrader_execution = _between(
        ctrader_adapter,
        "    def _on_execution_event(",
        "    def _on_order_error_event(",
    )

    broker_order_created_only_after_service_return = (
        "broker_result = service.place_market_order(" in workspace_submit
        and "broker_order_uid = self.repository.create_broker_order("
        in workspace_submit
        and workspace_submit.index("broker_result = service.place_market_order(")
        < workspace_submit.index(
            "broker_order_uid = self.repository.create_broker_order("
        )
    )
    workspace_failure_exception_handler_present = (
        "except IBMarketOrderTimeoutError" in workspace_submit
        or "except RuntimeError" in workspace_submit
    )

    ib_timeout_has_exact_identity = all(
        token in ib_errors
        for token in (
            "self.order_id = int(order_id)",
            "self.status = str(status or \"\").strip().upper()",
            "self.filled = float(filled or 0.0)",
            "self.remaining = float(remaining or 0.0)",
        )
    )
    ib_cancel_is_terminal_callback_status = all(
        token in ib_adapter
        for token in (
            '"CANCELLED",',
            '"API CANCELLED",',
            '"INACTIVE",',
            "self.order_event.set()",
        )
    )
    ib_timeout_raises_typed_error = (
        "raise IBMarketOrderTimeoutError(" in ib_market_order
    )
    ib_nonfilled_terminal_raises_generic_error = (
        'if status_text != "FILLED":' in ib_market_order
        and 'raise RuntimeError(f"IB MARKET order was not filled: {status_text}")'
        in ib_market_order
    )
    ib_generic_terminal_error_preserves_order_id = (
        'raise RuntimeError(f"IB MARKET order was not filled: '
        '{status_text}; order_id={parent_order_id}")' in ib_market_order
    )

    ctrader_reject_captures_payload = all(
        token in ctrader_execution
        for token in (
            "CTRADER_EXECUTION_TYPE_ORDER_REJECTED",
            "self._trade_payload = payload",
            'order_id = getattr(order, "orderId", None)',
            'position_id = (\n            getattr(position, "positionId", None)',
        )
    )
    ctrader_reject_sets_error = (
        'self._trade_error_text = "cTrader order rejected by execution event."'
        in ctrader_execution
    )
    ctrader_wait_raises_before_payload_return = (
        "if self._trade_error_text:" in ctrader_wait
        and "raise RuntimeError(self._trade_error_text)" in ctrader_wait
        and "return self._trade_payload" in ctrader_wait
        and ctrader_wait.index("raise RuntimeError(self._trade_error_text)")
        < ctrader_wait.index("return self._trade_payload")
    )
    ctrader_market_cancel_terminal_handler_present = (
        "CTRADER_EXECUTION_TYPE_ORDER_CANCEL" in ctrader_execution
        or "CTRADER_EXECUTION_TYPE_ORDER_CANCELLED" in ctrader_execution
    )

    repository_can_persist_failure_status = (
        "def create_broker_order(" in repository
        and "def update_broker_order_execution_status(" in repository
    )
    workspace_failure_broker_order_persistence_present = (
        workspace_failure_exception_handler_present
        and "create_broker_order(" in workspace_submit.split("except", 1)[-1]
    )
    workspace_failure_reconciler_call_present = (
        workspace_failure_exception_handler_present
        and "reconcile_workspace_broker_order(" in workspace_submit.split(
            "except", 1
        )[-1]
    )

    assert broker_order_created_only_after_service_return
    assert not workspace_failure_exception_handler_present
    assert ib_timeout_has_exact_identity
    assert ib_cancel_is_terminal_callback_status
    assert ib_timeout_raises_typed_error
    assert ib_nonfilled_terminal_raises_generic_error
    assert not ib_generic_terminal_error_preserves_order_id
    assert ctrader_reject_captures_payload
    assert ctrader_reject_sets_error
    assert ctrader_wait_raises_before_payload_return
    assert not ctrader_market_cancel_terminal_handler_present
    assert repository_can_persist_failure_status
    assert not workspace_failure_broker_order_persistence_present
    assert not workspace_failure_reconciler_call_present

    print("T109-57_TERMINAL_REJECT_CANCEL_IDENTITY_PERSISTENCE_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("production_change=False")
    print("workspace_broker_order_created_only_after_service_return=True")
    print("workspace_terminal_failure_handler_present=False")
    print("ib_timeout_typed_identity_present=True")
    print("ib_cancel_terminal_callback_status_present=True")
    print("ib_timeout_preserves_order_id_status_fill_state=True")
    print("ib_nonfilled_terminal_uses_generic_runtime_error=True")
    print("ib_generic_terminal_error_preserves_order_id=False")
    print("ctrader_reject_payload_captures_order_identity=True")
    print("ctrader_reject_payload_is_retained_inside_adapter=True")
    print("ctrader_wait_raises_before_returning_reject_payload=True")
    print("ctrader_reject_identity_reaches_runtime_engine=False")
    print("ctrader_market_cancel_terminal_handler_present=False")
    print("repository_can_persist_terminal_failure_status=True")
    print("workspace_terminal_failure_broker_order_persistence=False")
    print("workspace_terminal_failure_reconciler_call=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "BROKER_TERMINAL_FAILURE_IDENTITY_PRESERVING_OUTCOME_CONTRACT"
    )
    print(
        "boundary_contract=IB_AND_CTRADER_TERMINAL_FAILURES_MUST_RETURN_OR_RAISE_"
        "A_TYPED_OUTCOME_THAT_PRESERVES_BROKER_ORDER_ID_STATUS_AND_CONFIRMED_"
        "FILL_STATE_BEFORE_WORKSPACE_CAN_PERSIST_REJECT_CANCEL_WITHOUT_POSITION"
    )
    print(
        "factual_verdict=C. TERMINAL_FAILURE_EVENTS_EXIST_BUT_EXACT_IDENTITY_"
        "IS_LOST_BEFORE_WORKSPACE_PERSISTENCE"
    )


if __name__ == "__main__":
    main()
