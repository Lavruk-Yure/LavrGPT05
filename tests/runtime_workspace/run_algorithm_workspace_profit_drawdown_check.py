# -*- coding: utf-8 -*-
"""Runtime check for WSP profit drawdown CLOSE decision foundation."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RUNNING,
    AlgorithmWorkspace,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WORKSPACE_PROFIT_ACTION_CLOSE,
    WORKSPACE_PROFIT_ACTION_HOLD,
)
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402


class FixedReplayService(WorkspaceReplayService):
    def __init__(
        self,
        events: tuple[WorkspaceMarketEvent, ...],
    ) -> None:
        super().__init__()
        self.events = events

    def create_synthetic_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        _ = broker, symbol, timeframe, replay_settings
        return WorkspaceReplaySession(
            events=self.events,
            source_name="PROFIT_DRAWDOWN_TEST",
            speed=1,
        )


def _event(index: int, spread: float) -> WorkspaceMarketEvent:
    close = 1.1400 + index * 0.0001
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 25, 10, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=close - 0.00005,
        high=close + 0.00010,
        low=close - 0.00010,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _position(
    workspace: AlgorithmWorkspace,
    *,
    current_profit: float,
    peak_profit: float,
    current_price: float | None = 1.1390,
    workspace_uid: str | None = None,
) -> dict[str, object]:
    return {
        "workspace_uid": workspace_uid or workspace.workspace_uid,
        "broker": workspace.broker,
        "account_id": workspace.account_id,
        "symbol": workspace.symbol,
        "position_id": "position-1",
        "broker_position_id": "IB:DUM513747:EURUSD:LEG1",
        "side": "BUY",
        "volume": 1000.0,
        "entry_price": 1.1380,
        "current_price": current_price,
        "current_profit": current_profit,
        "peak_profit": peak_profit,
        "stop_loss": 1.1360,
        "take_profit": 1.1440,
        "opened_at": "2026-07-25T09:00:00Z",
        "reconciliation_status": "RECONCILED",
        "active": True,
    }


def main() -> None:
    events = (
        _event(0, 0.00012),
        _event(1, 0.00030),
        _event(2, 0.00012),
    )
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "warmup_bars": 0,
            "spread_limit": 0.00020,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 10.0,
        },
    )
    runtime = WorkspaceRuntime(
        workspace,
        replay_service=FixedReplayService(events),
    )

    runtime.begin_start()
    runtime.complete_start()
    assert len(runtime.advance_replay()) == 1
    assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert runtime.context.signal_allowed

    wrong_workspace_uid = str(uuid4())
    selection = runtime.apply_owned_snapshots(
        [],
        [
            _position(
                workspace,
                current_profit=20.0,
                peak_profit=100.0,
                workspace_uid=wrong_workspace_uid,
            ),
            _position(
                workspace,
                current_profit=69.0,
                peak_profit=100.0,
            ),
        ],
    )
    assert selection.rejected_positions == 1
    decisions = runtime.profit_protection_decisions()
    assert len(decisions) == 1
    close_decision = decisions[0]
    assert close_decision.action == WORKSPACE_PROFIT_ACTION_CLOSE
    assert close_decision.close_requested
    assert abs(close_decision.drawdown_percent - 31.0) < 1e-12
    assert close_decision.ownership_verified
    assert close_decision.current_price_verified
    assert close_decision.spread_guard_passed
    assert close_decision.runtime_ready
    assert not close_decision.execution_attempted
    assert runtime.context.pending_close_decisions_count == 1

    runtime.apply_owned_snapshots(
        [],
        [_position(workspace, current_profit=70.0, peak_profit=100.0)],
    )
    exact_limit_decision = runtime.profit_protection_decisions()[0]
    assert exact_limit_decision.action == WORKSPACE_PROFIT_ACTION_HOLD
    assert exact_limit_decision.reason == "profit drawdown is within limit"

    runtime.apply_owned_snapshots(
        [],
        [_position(workspace, current_profit=5.0, peak_profit=9.0)],
    )
    minimum_profit_decision = runtime.profit_protection_decisions()[0]
    assert minimum_profit_decision.action == WORKSPACE_PROFIT_ACTION_HOLD
    assert minimum_profit_decision.reason == "minimum profit is not reached"

    runtime.apply_owned_snapshots(
        [],
        [
            _position(
                workspace,
                current_profit=60.0,
                peak_profit=100.0,
                current_price=None,
            )
        ],
    )
    price_decision = runtime.profit_protection_decisions()[0]
    assert price_decision.action == WORKSPACE_PROFIT_ACTION_HOLD
    assert price_decision.reason == "current price is unavailable"
    assert not price_decision.current_price_verified

    runtime.apply_owned_snapshots(
        [],
        [_position(workspace, current_profit=69.0, peak_profit=100.0)],
    )
    assert runtime.pending_close_decisions()[0].close_requested

    assert len(runtime.advance_replay()) == 1
    spread_decision = runtime.profit_protection_decisions()[0]
    assert spread_decision.action == WORKSPACE_PROFIT_ACTION_HOLD
    assert spread_decision.reason == "spread guard is not passed"
    assert not spread_decision.spread_guard_passed
    assert runtime.context.pending_close_decisions_count == 0

    assert len(runtime.advance_replay()) == 1
    recovery_decision = runtime.profit_protection_decisions()[0]
    assert recovery_decision.action == WORKSPACE_PROFIT_ACTION_CLOSE
    assert recovery_decision.spread_guard_passed
    assert runtime.context.pending_close_decisions_count == 1

    wrong_only = runtime.apply_owned_snapshots(
        [],
        [
            _position(
                workspace,
                current_profit=69.0,
                peak_profit=100.0,
                workspace_uid=wrong_workspace_uid,
            )
        ],
    )
    assert wrong_only.rejected_positions == 1
    assert not runtime.profit_protection_decisions()
    assert runtime.context.pending_close_decisions_count == 0

    journal_events: list[str] = [entry.event for entry in runtime.journal]
    assert journal_events.count("CLOSE_DECISION_CREATED") >= 2
    assert "CLOSE_DECISION_CLEARED" in journal_events
    assert all(entry.category != "BROKER" for entry in runtime.journal)

    print("Algorithm Workspace Profit Drawdown result")
    print("  peak_profit=100.00")
    print("  current_profit=69.00")
    print("  drawdown_percent=31.0%")
    print("  drawdown_limit=30.0%")
    print("  close_decision_created=True")
    print("  exact_limit_not_triggered=True")
    print("  minimum_profit_guard=True")
    print("  current_price_guard=True")
    print("  ownership_guard=True")
    print("  spread_guard=True")
    print("  spread_recovery_close_decision=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PROFIT_DRAWDOWN_CHECK=OK")


if __name__ == "__main__":
    main()
