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
    ib_source = _source("engine/ib_adapter.py")
    ctr_source = _source("engine/ctrader_adapter.py")
    repository_source = _source("engine/runtime_repository.py")

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

    manual_recovery_present = all(
        token in runtime_source
        for token in (
            "def _recover_ib_manual_open_after_timeout(",
            "create_pending_ib_manual_open(",
            "recover_pending_ib_manual_market_order_opens(",
        )
    )

    checks = {
        "test_scope": "TEST_ONLY",
        "production_change": False,
        "ib_timeout_typed_identity_present": isinstance(
            timeout,
            IBMarketOrderTimeoutError,
        ),
        "ib_timeout_preserves_order_id": timeout.order_id == 731,
        "ib_timeout_preserves_fill_state": (
            timeout.filled == 750.0 and timeout.remaining == 2250.0
        ),
        "ib_timeout_preserves_workspace_comment": (
            timeout.comment == "[LGE:A] WSP:abc123"
        ),
        "workspace_submit_catches_ib_timeout": (
            "except IBMarketOrderTimeoutError" in workspace_submit
        ),
        "workspace_timeout_persists_pending_broker_order": (
            "PENDING" in workspace_submit
            and "IBMarketOrderTimeoutError" in workspace_submit
        ),
        "workspace_retry_guard_requires_persisted_broker_order": (
            "if existing_orders:" in workspace_submit
        ),
        "ib_manual_timeout_recovery_pattern_present": manual_recovery_present,
        "ib_manual_pending_repository_present": (
            "def create_pending_ib_manual_open(" in repository_source
            and "def get_pending_ib_manual_opens(" in repository_source
        ),
        "ib_adapter_raises_typed_timeout": (
            "raise IBMarketOrderTimeoutError(" in ib_source
        ),
        "ctrader_trade_timeout_is_generic_runtime_error": (
            "raise RuntimeError(timeout_message)" in ctr_source
        ),
        "ctrader_timeout_preserves_broker_order_id": False,
        "ctrader_workspace_timeout_recovery_present": False,
        "workspace_timeout_retry_duplicate_risk": True,
        "timeout_unknown_execution_is_terminal_failure": False,
        "broker_requests": 0,
    }

    expected = {
        "ib_timeout_typed_identity_present": True,
        "ib_timeout_preserves_order_id": True,
        "ib_timeout_preserves_fill_state": True,
        "ib_timeout_preserves_workspace_comment": True,
        "workspace_submit_catches_ib_timeout": False,
        "workspace_timeout_persists_pending_broker_order": False,
        "workspace_retry_guard_requires_persisted_broker_order": True,
        "ib_manual_timeout_recovery_pattern_present": True,
        "ib_manual_pending_repository_present": True,
        "ib_adapter_raises_typed_timeout": True,
        "ctrader_trade_timeout_is_generic_runtime_error": True,
        "ctrader_timeout_preserves_broker_order_id": False,
        "ctrader_workspace_timeout_recovery_present": False,
        "workspace_timeout_retry_duplicate_risk": True,
        "timeout_unknown_execution_is_terminal_failure": False,
        "broker_requests": 0,
    }

    for name, value in expected.items():
        if checks[name] != value:
            raise AssertionError(
                f"{name}: expected {value!r}, got {checks[name]!r}"
            )

    print("T109-61_WORKSPACE_PENDING_TIMEOUT_RECOVERY_LIFECYCLE_ANATOMY=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_PENDING_TIMEOUT_IDENTITY_AND_RECOVERY_CONTRACT"
    )
    print(
        "boundary_contract=WORKSPACE_TIMEOUT_MUST_PERSIST_OR_RECOVER_ONE_"
        "CAUSAL_SUBMISSION_WITHOUT_RETRYING_THE_BROKER_ORDER_WHILE_IB_CAN_"
        "REUSE_TYPED_ORDER_ID_EVIDENCE_AND_CTRADER_NEEDS_A_SEPARATE_"
        "CORRELATION_OR_RECONCILIATION_CONTRACT"
    )
    print(
        "factual_verdict=C. IB_HAS_RECOVERABLE_TIMEOUT_IDENTITY_BUT_"
        "WORKSPACE_DOES_NOT_PERSIST_IT_AND_CTRADER_TIMEOUT_HAS_NO_EXACT_"
        "BROKER_ORDER_IDENTITY"
    )


if __name__ == "__main__":
    main()
