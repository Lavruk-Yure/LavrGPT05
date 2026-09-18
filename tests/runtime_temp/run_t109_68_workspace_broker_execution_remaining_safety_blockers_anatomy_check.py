from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.risk.constants import (  # noqa: E402
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)


def _risk_request(
    *,
    daily_realized_pnl: float | None,
    open_positions_count: int | None,
) -> WorkspaceRiskRequest:
    return WorkspaceRiskRequest(
        timestamp=datetime(2026, 9, 18, 11, 0, tzinfo=UTC),
        workspace_uid="T109-68-WSP",
        broker="CTRADER",
        account_id="12345",
        symbol="EURUSD",
        side="BUY",
        source_mode="BROKER",
        requested_volume=1000.0,
        equity=10_000.0,
        estimated_loss_at_stop=10.0,
        stop_loss=1.1000,
        open_positions_count=open_positions_count,
        daily_realized_pnl=daily_realized_pnl,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
        signal_uid="T109-68-SIGNAL",
    )


def main() -> None:
    controller_source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_controller.py"
    ).read_text(encoding="utf-8")
    runtime_engine_source = (
        PROJECT_ROOT / "engine" / "runtime_engine.py"
    ).read_text(encoding="utf-8")

    evaluator = WorkspaceRiskEvaluator(
        WorkspaceRiskPolicy(
            max_risk_percent=0.5,
            maximum_position_volume=3000.0,
            maximum_open_positions=2,
            max_daily_loss_percent=2.0,
            require_stop_loss=True,
        )
    )

    missing_daily = evaluator.evaluate(
        _risk_request(
            daily_realized_pnl=None,
            open_positions_count=None,
        )
    )
    daily_present_positions_missing = evaluator.evaluate(
        _risk_request(
            daily_realized_pnl=0.0,
            open_positions_count=None,
        )
    )

    checks = {
        "test_scope": "TEST_ONLY",
        "production_change": False,
        "cached_account_equity_wired": (
            'equity=getattr(account_state, "equity", None)' in controller_source
        ),
        "cached_account_currency_wired": (
            'currency=getattr(account_state, "currency", None)'
            in controller_source
        ),
        "daily_realized_pnl_still_unwired": (
            "daily_realized_pnl=None" in controller_source
        ),
        "open_positions_count_still_unwired": (
            "open_positions_count=None" in controller_source
        ),
        "first_risk_blocker_is_daily_pnl": (
            missing_daily.reason_code
            == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
        ),
        "next_risk_blocker_after_daily_pnl_is_positions": (
            daily_present_positions_missing.reason_code
            == RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
        ),
        "semi_persists_pending_confirmation": (
            'execution_state = "PENDING_CONFIRMATION"' in controller_source
        ),
        "auto_requires_same_call_confirmed_flat": (
            "workspace_same_call_position_snapshot_confirms_flat" in controller_source
            and "_submit_workspace_auto_after_same_call_flat" in controller_source
        ),
        "reverse_submission_requires_confirmed_flat": (
            "Workspace reverse submission requires confirmed flat exposure"
            in runtime_engine_source
        ),
        "ctrader_pending_timeout_blocks_resubmit": (
            'existing_status == "PENDING_CONFIRMATION"' in runtime_engine_source
            and '"resubmit_allowed": False' in runtime_engine_source
        ),
        "broker_requests": 0,
    }

    failed = [
        name
        for name, value in checks.items()
        if name not in {"test_scope", "production_change", "broker_requests"}
        and value is not True
    ]
    if checks["production_change"] is not False:
        failed.append("production_change")
    if checks["broker_requests"] != 0:
        failed.append("broker_requests")
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-68_WORKSPACE_BROKER_EXECUTION_REMAINING_SAFETY_BLOCKERS_ANATOMY=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print("risk_blocker_with_current_broker_snapshot=DAILY_PNL_SNAPSHOT_MISSING")
    print("next_blocker_if_daily_pnl_resolved=OPEN_POSITIONS_SNAPSHOT_MISSING")
    print("semi_submission_status=PENDING_CONFIRMATION_NO_AUTO_SUBMIT")
    print("reverse_guard_status=CONFIRMED_FLAT_REQUIRED")
    print("timeout_recovery_status=FAIL_CLOSED_NO_RESUBMIT")
    print("first_unresolved_boundary=BROKER_DAILY_REALIZED_PNL_CANONICAL_SOURCE")
    print(
        "boundary_contract=BROKER_RISK_ALLOW_REQUIRES_AUTHORITATIVE_ACCOUNT_DAY_"
        "REALIZED_PNL_BEFORE_OPEN_POSITIONS_COUNT_CAN_BECOME_THE_NEXT_RUNTIME_BLOCKER"
    )
    print(
        "factual_verdict=A. DAILY_REALIZED_PNL_REMAINS_THE_FIRST_CAUSAL_"
        "BROKER_EXECUTION_SAFETY_BLOCKER"
    )


if __name__ == "__main__":
    main()
