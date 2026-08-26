# -*- coding: utf-8 -*-
"""Runtime check for signal-to-risk integration without broker execution."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithm,
    WorkspaceSignalOutput,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import (  # noqa: E402
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceTradeIntent,
)
from engine.risk.constants import (  # noqa: E402
    RISK_DECISION_ALLOW,
    RISK_DECISION_BLOCK,
    RISK_REASON_APPROVED,
    RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED,
    RISK_REASON_STOP_LOSS_REQUIRED,
    REPLAY_RISK_SETTING_EQUITY,
)


class RiskSignalProbeAlgorithm(WorkspaceAlgorithm):
    """Emit deterministic trade intents with allow and block outcomes."""

    def __init__(self) -> None:
        self.context: WorkspaceRuntimeContext | None = None
        self.started = False
        self.market_events = 0

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        _ = parameters
        self.context = context

    def start(self) -> None:
        assert self.context is not None
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        assert self.started
        index = self.market_events
        self.market_events += 1
        stop_loss = event.close - 0.0010
        requested_volume = 500.0
        if index == 2:
            stop_loss = None
        if index == 3:
            requested_volume = 1500.0
        return WorkspaceSignalProposal(
            signal_type="RISK_ENTRY",
            direction="BUY",
            strength=0.80,
            macd_state="LINEAR_UP",
            alligator_confirmation="SAME_TIMEFRAME",
            trade_intent=WorkspaceTradeIntent(
                requested_volume=requested_volume,
                estimated_loss_at_stop=400.0,
                stop_loss=stop_loss,
            ),
        )

    def on_order_event(self, event: object) -> None:
        _ = event

    def stop(self) -> None:
        self.started = False


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
            source_name="SIGNAL_RISK_TEST",
            speed=1,
        )


def _event(index: int) -> WorkspaceMarketEvent:
    close = 1.1400 + index * 0.0001
    spread = 0.00012
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 30, 7, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=close - spread / 2.0,
        ask=close + spread / 2.0,
        spread=spread,
        open=close - 0.00005,
        high=close + 0.00010,
        low=close - 0.00010,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _run(
    workspace: AlgorithmWorkspace,
    events: tuple[WorkspaceMarketEvent, ...],
) -> WorkspaceRuntime:
    runtime = WorkspaceRuntime(
        workspace,
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: RiskSignalProbeAlgorithm(),
    )
    runtime.begin_start()
    runtime.complete_start()
    for _event_item in events:
        emitted = runtime.advance_replay()
        assert len(emitted) == 1
    return runtime


def main() -> None:
    events = tuple(_event(index) for index in range(4))
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RiskSignalProbeAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={REPLAY_RISK_SETTING_EQUITY: 100_000.0},
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
    )

    first_runtime = _run(workspace, events)
    second_runtime = _run(workspace, events)
    first_snapshot = first_runtime.risk_account_snapshot
    second_snapshot = second_runtime.risk_account_snapshot
    records = first_runtime.signal_records()
    repeated_records = second_runtime.signal_records()

    assert records == repeated_records
    assert first_snapshot == second_snapshot
    assert first_snapshot is not None
    assert first_snapshot.synthetic
    assert first_snapshot.equity == 100_000.0
    assert first_snapshot.daily_realized_pnl == 0.0
    assert first_snapshot.open_positions_count == 0
    assert len(records) == 4
    assert first_runtime.context.accepted_signals_count == 1
    assert first_runtime.context.rejected_signals_count == 3

    assert not records[0].accepted
    assert records[0].reason == "warmup incomplete"
    assert records[0].risk_decision is None
    assert records[0].risk_reason_code is None

    assert records[1].accepted
    assert records[1].risk_decision == RISK_DECISION_ALLOW
    assert records[1].risk_reason_code == RISK_REASON_APPROVED
    assert records[1].requested_volume == 500.0
    assert records[1].approved_volume == 500.0

    assert not records[2].accepted
    assert records[2].risk_decision == RISK_DECISION_BLOCK
    assert records[2].risk_reason_code == RISK_REASON_STOP_LOSS_REQUIRED
    assert records[2].approved_volume is None

    assert not records[3].accepted
    assert records[3].risk_decision == RISK_DECISION_BLOCK
    assert records[3].risk_reason_code == RISK_REASON_MAXIMUM_POSITION_VOLUME_EXCEEDED
    assert records[3].approved_volume is None

    signal_uids = {record.signal_uid for record in records}
    assert len(signal_uids) == len(records)
    assert all(not record.risk_execution_attempted for record in records)

    journal_events = [entry.event for entry in first_runtime.journal]
    assert journal_events.count("RISK_ALLOWED") == 1
    assert journal_events.count("RISK_BLOCKED") == 2
    assert journal_events.count("SIGNAL_ACCEPTED") == 1
    assert journal_events.count("SIGNAL_REJECTED") == 3

    print("Algorithm Workspace Signal Risk result")
    print(f"  signals={len(records)}")
    print("  runtime_guard_rejected=1")
    print("  risk_allowed=1")
    print("  risk_blocked=2")
    print("  stop_loss_required_blocked=True")
    print("  maximum_position_volume_blocked=True")
    print("  signal_uid_deterministic=True")
    print("  risk_account_snapshot_connected=True")
    print("  replay_snapshot_automatic=True")
    print("  signal_record_risk_reason=True")
    print("  risk_journal_connected=True")
    print("  deterministic=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_RISK_CHECK=OK")


if __name__ == "__main__":
    main()
