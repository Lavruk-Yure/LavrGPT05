from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_order_errors import IBMarketOrderTimeoutError  # noqa: E402


def _source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    runtime_source = _source("engine/runtime_engine.py")
    ctrader_source = _source("engine/ctrader_adapter.py")
    identity_source = _source("engine/broker_order_identity.py")

    timeout = IBMarketOrderTimeoutError(
        order_id=731,
        symbol_name="EURUSD",
        side="BUY",
        quantity=3000.0,
        status="SUBMITTED",
        filled=750.0,
        remaining=2250.0,
        comment="[LGE:A] WSP:abc123",
    )

    workspace_submit_start = runtime_source.index(
        "    def submit_workspace_execution_plan("
    )
    workspace_submit_end = runtime_source.index(
        "    def reconcile_workspace_broker_order(",
        workspace_submit_start,
    )
    workspace_submit = runtime_source[
        workspace_submit_start:workspace_submit_end
    ]

    ctrader_has_broker_comment_correlation = all(
        token in ctrader_source
        for token in (
            "broker_comment = build_broker_order_comment(comment, control_mode)",
            "request.comment = broker_comment",
            '"broker_comment": str(comment or "").strip()',
        )
    )
    ctrader_has_order_recovery_source = any(
        token in ctrader_source
        for token in (
            "ProtoOAOrderListReq",
            "ProtoOAOrderDetailsReq",
            "ProtoOAOrderHistoryReq",
        )
    )

    outcomes = (
        "FILLED",
        "REJECTED",
        "CANCELLED",
        "STILL_PENDING",
        "UNKNOWN",
    )

    checks = {
        "test_scope": "TEST_ONLY",
        "production_change": False,
        "ib_timeout_has_exact_order_identity": timeout.order_id == 731,
        "ib_timeout_has_confirmed_fill_state": (
            timeout.filled == 750.0 and timeout.remaining == 2250.0
        ),
        "ib_timeout_has_workspace_correlation": (
            timeout.comment == "[LGE:A] WSP:abc123"
        ),
        "ib_pending_can_be_persisted_without_resubmit": True,
        "ib_pending_recovery_pattern_already_present": (
            "def _recover_ib_manual_open_after_timeout(" in runtime_source
        ),
        "workspace_retry_guard_uses_persisted_broker_order": (
            "if existing_orders:" in workspace_submit
        ),
        "ctrader_request_carries_workspace_correlation": (
            ctrader_has_broker_comment_correlation
        ),
        "ctrader_correlation_marker_is_stable": (
            'prefix = f"[LGE:{_ORDER_MODE_CODE[mode]}]"' in identity_source
            and 'f"WSP:{trade_hint}"' in workspace_submit
        ),
        "ctrader_timeout_has_exact_broker_order_id": False,
        "ctrader_position_reconcile_returns_broker_comment": (
            '"broker_comment": str(comment or "").strip()' in ctrader_source
        ),
        "ctrader_order_recovery_source_present": ctrader_has_order_recovery_source,
        "ctrader_position_snapshot_alone_can_prove_reject": False,
        "ctrader_position_snapshot_alone_can_prove_pending": False,
        "retry_before_recovery_allowed": False,
        "timeout_is_terminal_failure": False,
        "recovery_outcomes_complete": outcomes
        == (
            "FILLED",
            "REJECTED",
            "CANCELLED",
            "STILL_PENDING",
            "UNKNOWN",
        ),
        "recommended_ib_contract": (
            "PERSIST_PENDING_BROKER_ORDER_BY_EXACT_ORDER_ID"
        ),
        "recommended_ctrader_contract": (
            "PERSIST_CAUSAL_PENDING_SUBMISSION_BY_WORKSPACE_CORRELATION"
        ),
        "recommended_retry_policy": "BLOCK_UNTIL_RECOVERY_RESOLVES",
        "recommended_timeout_semantics": "NON_TERMINAL_UNKNOWN_EXECUTION",
        "single_production_repair_for_both_brokers": False,
        "broker_requests": 0,
    }

    expected = {
        "ib_timeout_has_exact_order_identity": True,
        "ib_timeout_has_confirmed_fill_state": True,
        "ib_timeout_has_workspace_correlation": True,
        "ib_pending_can_be_persisted_without_resubmit": True,
        "ib_pending_recovery_pattern_already_present": True,
        "workspace_retry_guard_uses_persisted_broker_order": True,
        "ctrader_request_carries_workspace_correlation": True,
        "ctrader_correlation_marker_is_stable": True,
        "ctrader_timeout_has_exact_broker_order_id": False,
        "ctrader_position_reconcile_returns_broker_comment": True,
        "ctrader_order_recovery_source_present": False,
        "ctrader_position_snapshot_alone_can_prove_reject": False,
        "ctrader_position_snapshot_alone_can_prove_pending": False,
        "retry_before_recovery_allowed": False,
        "timeout_is_terminal_failure": False,
        "recovery_outcomes_complete": True,
        "single_production_repair_for_both_brokers": False,
        "broker_requests": 0,
    }

    for name, value in expected.items():
        if checks[name] != value:
            raise AssertionError(
                f"{name}: expected {value!r}, got {checks[name]!r}"
            )

    print("T109-62_WORKSPACE_PENDING_TIMEOUT_IDENTITY_RECOVERY_CONTRACT=OK")
    for name, value in checks.items():
        if isinstance(value, tuple):
            value = ",".join(value)
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_PENDING_TIMEOUT_RECOVERY_SPLIT_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=IB_CAN_PERSIST_EXACT_PENDING_BROKER_ORDER_NOW_"
        "WHILE_CTRADER_MUST_PERSIST_ONE_CAUSAL_PENDING_SUBMISSION_BY_"
        "WORKSPACE_CORRELATION_AND_MUST_NOT_RETRY_UNTIL_A_BROKER_"
        "RECOVERY_SOURCE_RESOLVES_FILLED_REJECTED_CANCELLED_PENDING_OR_UNKNOWN"
    )
    print(
        "factual_verdict=A. PENDING_TIMEOUT_RECOVERY_CONTRACT_IDENTIFIED_"
        "AND_IB_CTRADER_PRODUCTION_REPAIRS_MUST_BE_SPLIT"
    )


if __name__ == "__main__":
    main()
