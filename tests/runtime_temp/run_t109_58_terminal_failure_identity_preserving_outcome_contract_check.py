from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IB_ADAPTER = PROJECT_ROOT / "engine" / "ib_adapter.py"
IB_ERRORS = PROJECT_ROOT / "engine" / "ib_order_errors.py"
CTRADER_ADAPTER = PROJECT_ROOT / "engine" / "ctrader_adapter.py"
RUNTIME_ENGINE = PROJECT_ROOT / "engine" / "runtime_engine.py"


@dataclass(frozen=True)
class _TerminalFailureOutcomeContract:
    broker: str
    broker_order_id: str
    status: str
    filled: float
    remaining: float
    confirmed_price: float | None
    broker_position_id: str | None
    failure_reason: str

    def is_terminal_failure(self) -> bool:
        return bool(self.broker_order_id and self.status and self.failure_reason)

    def has_confirmed_exposure(self) -> bool:
        return self.filled > 0.0


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    ib_adapter = _read(IB_ADAPTER)
    ib_errors = _read(IB_ERRORS)
    ctrader_adapter = _read(CTRADER_ADAPTER)
    runtime_engine = _read(RUNTIME_ENGINE)

    ib_terminal_statuses_present = all(
        token in ib_adapter
        for token in (
            '"FILLED"',
            '"CANCELLED"',
            '"API CANCELLED"',
            '"INACTIVE"',
        )
    )
    ib_terminal_row_has_identity = all(
        token in ib_adapter
        for token in (
            '"order_id": int(order_id)',
            '"status": str(status or "")',
            '"filled": float(filled or 0.0)',
            '"remaining": float(remaining or 0.0)',
            '"avg_fill_price": float(avg_fill_price or 0.0)',
        )
    )
    ib_timeout_is_nonterminal_pending_contract = (
        "class IBMarketOrderTimeoutError" in ib_errors
        and "execution state is " in ib_errors
        and "unknown. Do not repeat the order. " in ib_errors
    )
    ib_nonfilled_terminal_raises_generic_runtime_error = (
        'raise RuntimeError(f"IB MARKET order was not filled: {status_text}")'
        in ib_adapter
    )

    ctrader_reject_keeps_payload_before_error = (
        "if execution_type == CTRADER_EXECUTION_TYPE_ORDER_REJECTED:" in ctrader_adapter
        and "self._trade_payload = payload" in ctrader_adapter
        and 'self._trade_error_text = "cTrader order rejected by execution event."'
        in ctrader_adapter
    )
    ctrader_wait_discards_payload_on_error = (
        "if self._trade_error_text:" in ctrader_adapter
        and "raise RuntimeError(self._trade_error_text)" in ctrader_adapter
        and "return self._trade_payload" in ctrader_adapter
    )

    workspace_terminal_failure_handler_present = (
        "BrokerTerminalOrderFailure" in runtime_engine
        or "TerminalOrderFailure" in runtime_engine
    )

    reject_zero = _TerminalFailureOutcomeContract(
        broker="CTRADER",
        broker_order_id="7001",
        status="REJECTED",
        filled=0.0,
        remaining=3000.0,
        confirmed_price=None,
        broker_position_id=None,
        failure_reason="ORDER_REJECTED",
    )
    cancel_zero = _TerminalFailureOutcomeContract(
        broker="IB",
        broker_order_id="101",
        status="CANCELLED",
        filled=0.0,
        remaining=3000.0,
        confirmed_price=None,
        broker_position_id=None,
        failure_reason="CANCELLED",
    )
    cancel_partial = _TerminalFailureOutcomeContract(
        broker="IB",
        broker_order_id="102",
        status="CANCELLED",
        filled=1200.0,
        remaining=1800.0,
        confirmed_price=1.1012,
        broker_position_id=None,
        failure_reason="CANCELLED_AFTER_PARTIAL_FILL",
    )

    contract_fields_cover_required_identity = all(
        outcome.is_terminal_failure()
        for outcome in (reject_zero, cancel_zero, cancel_partial)
    )
    reject_zero_fill_means_no_position = not reject_zero.has_confirmed_exposure()
    cancel_zero_fill_means_no_position = not cancel_zero.has_confirmed_exposure()
    cancel_partial_fill_requires_position = cancel_partial.has_confirmed_exposure()

    checks = {
        "test_scope": "TEST_ONLY",
        "production_change": False,
        "ib_terminal_status_set_present": ib_terminal_statuses_present,
        "ib_terminal_callback_preserves_order_fill_state": ib_terminal_row_has_identity,
        "ib_timeout_is_separate_nonterminal_pending_contract": (
            ib_timeout_is_nonterminal_pending_contract
        ),
        "ib_nonfilled_terminal_still_uses_generic_runtime_error": (
            ib_nonfilled_terminal_raises_generic_runtime_error
        ),
        "ctrader_reject_payload_preserved_before_raise": (
            ctrader_reject_keeps_payload_before_error
        ),
        "ctrader_wait_discards_typed_identity_on_error": (
            ctrader_wait_discards_payload_on_error
        ),
        "workspace_typed_terminal_failure_handler_present": (
            workspace_terminal_failure_handler_present
        ),
        "contract_fields_cover_required_identity": (
            contract_fields_cover_required_identity
        ),
        "recommended_transport": "BROKER_NEUTRAL_TYPED_EXCEPTION",
        "recommended_type": "BrokerTerminalOrderFailure",
        "recommended_required_fields": (
            "broker,broker_order_id,status,filled,remaining,failure_reason"
        ),
        "recommended_optional_fields": "confirmed_price,broker_position_id",
        "timeout_unknown_execution_uses_terminal_failure_contract": False,
        "reject_zero_fill_creates_position": not reject_zero_fill_means_no_position,
        "cancel_zero_fill_creates_position": not cancel_zero_fill_means_no_position,
        "cancel_partial_fill_requires_confirmed_position": (
            cancel_partial_fill_requires_position
        ),
        "runtime_catch_must_persist_broker_order_identity": True,
        "runtime_catch_must_reconcile_positive_confirmed_exposure": True,
        "generic_runtime_error_after_terminal_event_canonical": False,
        "broker_requests": 0,
    }

    required_true = (
        "ib_terminal_status_set_present",
        "ib_terminal_callback_preserves_order_fill_state",
        "ib_timeout_is_separate_nonterminal_pending_contract",
        "ib_nonfilled_terminal_still_uses_generic_runtime_error",
        "ctrader_reject_payload_preserved_before_raise",
        "ctrader_wait_discards_typed_identity_on_error",
        "contract_fields_cover_required_identity",
        "cancel_partial_fill_requires_confirmed_position",
        "runtime_catch_must_persist_broker_order_identity",
        "runtime_catch_must_reconcile_positive_confirmed_exposure",
    )
    failed = [name for name in required_true if checks[name] is not True]

    if checks["workspace_typed_terminal_failure_handler_present"] is not False:
        failed.append("workspace_typed_terminal_failure_handler_present")
    if checks["reject_zero_fill_creates_position"] is not False:
        failed.append("reject_zero_fill_creates_position")
    if checks["cancel_zero_fill_creates_position"] is not False:
        failed.append("cancel_zero_fill_creates_position")
    if checks["generic_runtime_error_after_terminal_event_canonical"] is not False:
        failed.append("generic_runtime_error_after_terminal_event_canonical")

    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-58_TERMINAL_FAILURE_IDENTITY_PRESERVING_OUTCOME_CONTRACT=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "BROKER_TERMINAL_FAILURE_TYPED_OUTCOME_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=IB_AND_CTRADER_TERMINAL_REJECT_CANCEL_EVENTS_MUST_"
        "RAISE_ONE_BROKER_NEUTRAL_TYPED_FAILURE_THAT_PRESERVES_EXACT_ORDER_"
        "IDENTITY_AND_CONFIRMED_FILL_STATE_WHILE_TIMEOUT_UNKNOWN_REMAINS_A_"
        "SEPARATE_NONTERMINAL_PENDING_CONTRACT"
    )
    print(
        "factual_verdict=A. BROKER_TERMINAL_FAILURE_IDENTITY_PRESERVING_"
        "OUTCOME_CONTRACT_IDENTIFIED"
    )


if __name__ == "__main__":
    main()
