from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STATE_STILL_PENDING = "STILL_PENDING"
STATE_FILLED = "FILLED"
STATE_REJECTED = "REJECTED"
STATE_CANCELLED = "CANCELLED"
STATE_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class _RecoveryEvidence:
    reconcile_success: bool = True
    order_history_success: bool = True
    deal_history_success: bool = True
    pending_order: bool = False
    terminal_status: str = ""
    confirmed_execution: bool = False
    confirmed_exposure: bool = False


def _resolve(evidence: _RecoveryEvidence) -> tuple[str, bool]:
    """TEST_ONLY: визначити safe cTrader timeout recovery outcome."""
    if not (
        evidence.reconcile_success
        and evidence.order_history_success
        and evidence.deal_history_success
    ):
        return STATE_UNKNOWN, False

    terminal = evidence.terminal_status.strip().upper()
    positive_execution = (
        evidence.confirmed_execution or evidence.confirmed_exposure
    )

    if evidence.pending_order:
        if terminal or positive_execution:
            return STATE_UNKNOWN, False
        return STATE_STILL_PENDING, False

    if terminal == STATE_REJECTED:
        if positive_execution:
            return STATE_UNKNOWN, False
        return STATE_REJECTED, False

    if terminal == STATE_CANCELLED:
        return STATE_CANCELLED, positive_execution

    if terminal == STATE_FILLED:
        if not positive_execution:
            return STATE_UNKNOWN, False
        return STATE_FILLED, True

    if positive_execution:
        return STATE_FILLED, True

    return STATE_UNKNOWN, False


def _source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    adapter_source = _source("engine/ctrader_adapter.py")
    service_source = _source("engine/services/ctrader_runtime_service.py")
    runtime_source = _source("engine/runtime_engine.py")

    pending = _resolve(_RecoveryEvidence(pending_order=True))
    filled = _resolve(
        _RecoveryEvidence(
            terminal_status=STATE_FILLED,
            confirmed_execution=True,
            confirmed_exposure=True,
        )
    )
    rejected = _resolve(
        _RecoveryEvidence(terminal_status=STATE_REJECTED)
    )
    cancelled_zero = _resolve(
        _RecoveryEvidence(terminal_status=STATE_CANCELLED)
    )
    cancelled_partial = _resolve(
        _RecoveryEvidence(
            terminal_status=STATE_CANCELLED,
            confirmed_execution=True,
            confirmed_exposure=True,
        )
    )
    missing_fill_evidence = _resolve(
        _RecoveryEvidence(terminal_status=STATE_FILLED)
    )
    contradiction = _resolve(
        _RecoveryEvidence(
            pending_order=True,
            terminal_status=STATE_CANCELLED,
        )
    )
    source_failure = _resolve(
        _RecoveryEvidence(order_history_success=False)
    )
    no_evidence = _resolve(_RecoveryEvidence())

    checks = {
        "test_scope": "TEST_ONLY",
        "production_change": False,
        "recovery_source_routes_present": all(
            name in adapter_source and name in service_source
            for name in (
                "get_workspace_reconcile_snapshot",
                "get_order_history",
                "get_deal_history",
                "get_workspace_timeout_recovery_sources",
            )
        ),
        "still_pending_resolution": pending == (STATE_STILL_PENDING, False),
        "filled_requires_positive_execution": (
            filled == (STATE_FILLED, True)
            and missing_fill_evidence == (STATE_UNKNOWN, False)
        ),
        "reject_zero_fill_resolution": rejected == (STATE_REJECTED, False),
        "cancel_zero_fill_resolution": (
            cancelled_zero == (STATE_CANCELLED, False)
        ),
        "cancel_partial_fill_preserves_exposure": (
            cancelled_partial == (STATE_CANCELLED, True)
        ),
        "contradictory_evidence_resolves_unknown": (
            contradiction == (STATE_UNKNOWN, False)
        ),
        "source_failure_resolves_unknown": (
            source_failure == (STATE_UNKNOWN, False)
        ),
        "no_evidence_resolves_unknown": no_evidence == (STATE_UNKNOWN, False),
        "still_pending_resubmit_allowed": False,
        "unknown_resubmit_allowed": False,
        "terminal_outcomes_are_causal_resolution": True,
        "production_lifecycle_resolver_present": (
            "resolve_ctrader_workspace_timeout" in runtime_source
            or "recover_ctrader_workspace_timeout" in runtime_source
        ),
        "broker_requests": 0,
    }

    required_true = (
        "recovery_source_routes_present",
        "still_pending_resolution",
        "filled_requires_positive_execution",
        "reject_zero_fill_resolution",
        "cancel_zero_fill_resolution",
        "cancel_partial_fill_preserves_exposure",
        "contradictory_evidence_resolves_unknown",
        "source_failure_resolves_unknown",
        "no_evidence_resolves_unknown",
        "terminal_outcomes_are_causal_resolution",
    )
    failed = [name for name in required_true if checks[name] is not True]
    if checks["still_pending_resubmit_allowed"] is not False:
        failed.append("still_pending_resubmit_allowed")
    if checks["unknown_resubmit_allowed"] is not False:
        failed.append("unknown_resubmit_allowed")
    if checks["production_lifecycle_resolver_present"] is not False:
        failed.append("production_lifecycle_resolver_present")
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-66_CTRADER_PENDING_TIMEOUT_RECOVERY_LIFECYCLE_DECISION=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "recommended_state_machine="
        "STILL_PENDING,FILLED,REJECTED,CANCELLED,UNKNOWN"
    )
    print("recommended_pending_behavior=KEEP_PENDING_AND_BLOCK_RESUBMIT")
    print("recommended_unknown_behavior=KEEP_PENDING_AND_BLOCK_RESUBMIT")
    print("recommended_filled_rule=REQUIRE_POSITIVE_EXECUTION_EVIDENCE")
    print(
        "recommended_cancel_partial_rule="
        "CANCELLED_WITH_CONFIRMED_EXPOSURE"
    )
    print(
        "first_unresolved_boundary="
        "CTRADER_PENDING_TIMEOUT_RECOVERY_LIFECYCLE_PRODUCTION_WIRING"
    )
    print(
        "boundary_contract=RUNTIME_MUST_RESOLVE_ONE_CAUSAL_CTRADER_TIMEOUT_"
        "USING_RECONCILE_ORDER_HISTORY_AND_DEAL_EVIDENCE_WITH_FAIL_CLOSED_"
        "UNKNOWN_OR_STILL_PENDING_AND_MUST_NOT_RESUBMIT_BEFORE_TERMINAL_"
        "CAUSAL_RESOLUTION"
    )
    print(
        "factual_verdict=A. CTRADER_PENDING_TIMEOUT_RECOVERY_LIFECYCLE_"
        "CONTRACT_IDENTIFIED"
    )


if __name__ == "__main__":
    main()
