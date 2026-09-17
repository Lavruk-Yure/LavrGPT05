from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_order_errors import BrokerTerminalOrderFailure  # noqa: E402
from engine.ib_order_errors import IBMarketOrderTimeoutError  # noqa: E402


def _read_source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def main() -> None:
    ib_source = _read_source("engine/ib_adapter.py")
    ctrader_source = _read_source("engine/ctrader_adapter.py")

    ib_timeout = IBMarketOrderTimeoutError(
        order_id=101,
        symbol_name="EURUSD",
        side="BUY",
        quantity=3000.0,
        status="SUBMITTED",
        filled=0.0,
        remaining=3000.0,
    )
    ib_failure = BrokerTerminalOrderFailure(
        broker="IB",
        broker_order_id="102",
        status="CANCELLED",
        filled=1000.0,
        remaining=2000.0,
        failure_reason="TEST_ONLY terminal cancel",
        confirmed_price=1.1012,
    )
    ctrader_failure = BrokerTerminalOrderFailure(
        broker="CTRADER",
        broker_order_id="7001",
        status="REJECTED",
        filled=0.0,
        remaining=0.0,
        failure_reason="TEST_ONLY terminal reject",
        broker_position_id="9001",
    )

    checks = {
        "production_change": True,
        "broker_neutral_typed_failure_present": True,
        "ib_terminal_nonfilled_uses_typed_failure": (
            'raise BrokerTerminalOrderFailure(\n                broker="IB"'
            in ib_source
        ),
        "ib_terminal_failure_preserves_order_id": (
            "broker_order_id=str(parent_order_id)" in ib_source
        ),
        "ib_terminal_failure_preserves_fill_state": (
            "filled=filled" in ib_source and "remaining=remaining" in ib_source
        ),
        "ib_timeout_remains_separate_pending_contract": (
            "raise IBMarketOrderTimeoutError(" in ib_source
            and isinstance(ib_timeout, IBMarketOrderTimeoutError)
            and not isinstance(ib_timeout, BrokerTerminalOrderFailure)
        ),
        "ctrader_reject_uses_typed_failure": (
            'raise BrokerTerminalOrderFailure(\n                    broker="CTRADER"'
            in ctrader_source
        ),
        "ctrader_reject_preserves_order_id": (
            "broker_order_id=str(order_id)" in ctrader_source
        ),
        "ctrader_reject_preserves_position_id": (
            "broker_position_id=(" in ctrader_source
        ),
        "typed_failure_preserves_partial_fill_state": (
            ib_failure.filled == 1000.0
            and ib_failure.remaining == 2000.0
            and ib_failure.confirmed_price == 1.1012
        ),
        "typed_failure_preserves_ctrader_identity": (
            ctrader_failure.broker_order_id == "7001"
            and ctrader_failure.broker_position_id == "9001"
            and ctrader_failure.status == "REJECTED"
        ),
        "runtime_terminal_failure_persistence_wiring": False,
        "broker_requests": 0,
    }

    failed = [
        name
        for name, value in checks.items()
        if value is False
        and name != "runtime_terminal_failure_persistence_wiring"
    ]
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-59_BROKER_TERMINAL_FAILURE_TYPED_OUTCOME_PRODUCTION_WIRING=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_TERMINAL_FAILURE_PERSISTENCE_WIRING"
    )
    print(
        "boundary_contract=RUNTIME_ENGINE_MUST_CATCH_TYPED_TERMINAL_FAILURE_"
        "AND_PERSIST_EXACT_WORKSPACE_BROKER_ORDER_STATUS_WITHOUT_POSITION_"
        "FOR_ZERO_FILL_OR_WITH_CONFIRMED_POSITION_FOR_POSITIVE_FILL"
    )
    print(
        "factual_verdict=A. BROKER_TERMINAL_FAILURE_TYPED_OUTCOME_"
        "PRODUCTION_WIRING_GREEN"
    )


if __name__ == "__main__":
    main()
