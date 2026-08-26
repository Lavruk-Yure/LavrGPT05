# -*- coding: utf-8 -*-
"""Deterministic check for the broker-neutral WSP risk model."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.risk.constants import (  # noqa: E402
    RISK_REASON_ACCOUNT_BINDING_MISMATCH,
    RISK_REASON_ACCOUNT_SNAPSHOT_MISSING,
    RISK_REASON_APPROVED,
    RISK_REASON_DAILY_LOSS_LIMIT_REACHED,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
    RISK_REASON_INVALID_LOSS_AT_STOP,
    RISK_REASON_MARKET_INVALID,
    RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
    RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
    RISK_REASON_RISK_PERCENT_EXCEEDED,
    RISK_REASON_RUNTIME_NOT_READY,
    RISK_REASON_SPREAD_BLOCKED,
    RISK_REASON_STOP_LOSS_REQUIRED,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)


def main() -> None:
    policy = WorkspaceRiskPolicy(
        max_risk_percent=0.5,
        maximum_position_volume=3000.0,
        maximum_open_positions=2,
        max_daily_loss_percent=2.0,
        require_stop_loss=True,
    )
    request = WorkspaceRiskRequest(
        timestamp=datetime(2026, 7, 30, 5, 30, tzinfo=UTC),
        workspace_uid="risk-workspace-1",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        side="BUY",
        source_mode="REPLAY",
        requested_volume=1000.0,
        equity=100_000.0,
        estimated_loss_at_stop=500.0,
        stop_loss=1.1350,
        open_positions_count=1,
        daily_realized_pnl=-250.0,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
        signal_uid="signal-1",
    )
    evaluator = WorkspaceRiskEvaluator(policy)

    approved = evaluator.evaluate(request)
    approved_repeat = evaluator.evaluate(request)
    assert approved == approved_repeat
    assert approved.allowed
    assert approved.reason_code == RISK_REASON_APPROVED
    assert approved.approved_volume == 1000.0
    assert abs(approved.calculated_risk_percent - 0.5) < 1e-12
    assert abs(approved.daily_loss_percent - 0.25) < 1e-12
    assert not approved.execution_attempted

    blocked_cases = {
        RISK_REASON_RUNTIME_NOT_READY: replace(request, runtime_ready=False),
        RISK_REASON_ACCOUNT_BINDING_MISMATCH: replace(
            request,
            binding_verified=False,
        ),
        RISK_REASON_ACCOUNT_SNAPSHOT_MISSING: replace(request, equity=0.0),
        RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING: replace(
            request,
            daily_realized_pnl=None,
        ),
        RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING: replace(
            request,
            open_positions_count=None,
        ),
        RISK_REASON_MARKET_INVALID: replace(request, market_valid=False),
        RISK_REASON_SPREAD_BLOCKED: replace(
            request,
            spread_guard_passed=False,
        ),
        RISK_REASON_STOP_LOSS_REQUIRED: replace(request, stop_loss=None),
        RISK_REASON_INVALID_LOSS_AT_STOP: replace(
            request,
            estimated_loss_at_stop=0.0,
        ),
        RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED: replace(
            request,
            requested_volume=3000.01,
        ),
        RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED: replace(
            request,
            open_positions_count=2,
        ),
        RISK_REASON_DAILY_LOSS_LIMIT_REACHED: replace(
            request,
            daily_realized_pnl=-2000.0,
        ),
        RISK_REASON_RISK_PERCENT_EXCEEDED: replace(
            request,
            estimated_loss_at_stop=500.01,
        ),
    }

    for reason_code, blocked_request in blocked_cases.items():
        decision = evaluator.evaluate(blocked_request)
        assert decision.blocked
        assert decision.reason_code == reason_code
        assert decision.approved_volume is None
        assert not decision.execution_attempted

    print("Algorithm Workspace Risk Model result")
    print("  max_risk_percent=0.5000%")
    print("  exact_risk_limit_allowed=True")
    print("  maximum_position_volume=3000.00")
    print("  maximum_open_positions=2")
    print("  max_daily_loss_percent=2.0000%")
    print("  stop_loss_required=True")
    print(f"  blocked_reason_codes={len(blocked_cases)}")
    print("  deterministic=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_RISK_MODEL_CHECK=OK")


if __name__ == "__main__":
    main()
