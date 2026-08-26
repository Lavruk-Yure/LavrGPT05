# -*- coding: utf-8 -*-
"""Runtime check for WorkspaceAlgorithm signals and WSP guard decisions."""

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
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STOPPED,
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
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_SPREAD_BLOCKED,
    WORKSPACE_SIGNAL_SPREAD_OK,
    WorkspaceSignalProposal,
)


class SignalProbeAlgorithm(WorkspaceAlgorithm):
    def __init__(self) -> None:
        self.context: WorkspaceRuntimeContext | None = None
        self.parameters: dict[str, Any] = {}
        self.started = False
        self.stopped = False
        self.market_events = 0
        self.order_events = 0

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        self.context = context
        self.parameters = dict(parameters)

    def start(self) -> None:
        assert self.context is not None
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        assert self.started
        self.market_events += 1
        direction = "BUY" if event.close >= event.open else "SELL"
        return WorkspaceSignalProposal(
            signal_type="RAIL_ENTRY",
            direction=direction,
            strength=0.75,
            macd_state="LINEAR_UP",
            alligator_confirmation="SAME_TIMEFRAME",
        )

    def on_order_event(self, event: object) -> None:
        assert self.started
        assert event == {"status": "FILLED"}
        self.order_events += 1

    def stop(self) -> None:
        self.started = False
        self.stopped = True


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
            source_name="SIGNAL_TEST",
            speed=1,
        )


def _event(index: int, spread: float) -> WorkspaceMarketEvent:
    close = 1.1400 + index * 0.0001
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 25, 8, 0, tzinfo=UTC)
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


def main() -> None:
    events = (
        _event(0, 0.00012),
        _event(1, 0.00030),
        _event(2, 0.00012),
        _event(3, 0.00030),
        _event(4, 0.00012),
    )
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="SignalProbeAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
    )
    probe = SignalProbeAlgorithm()
    runtime = WorkspaceRuntime(
        workspace,
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: probe,
    )

    runtime.begin_start()
    runtime.complete_start()
    assert probe.started
    assert probe.parameters["warmup_bars"] == 2

    for expected_count in range(1, len(events) + 1):
        emitted = runtime.advance_replay()
        assert len(emitted) == 1
        assert len(runtime.signal_records()) == expected_count

    signals = runtime.signal_records()
    assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
    assert runtime.context.signals_count == 5
    assert runtime.context.accepted_signals_count == 2
    assert runtime.context.rejected_signals_count == 3

    assert not signals[0].accepted
    assert signals[0].reason == "warmup incomplete"
    assert signals[0].spread_status == WORKSPACE_SIGNAL_SPREAD_OK
    assert not signals[1].accepted
    assert signals[1].reason == "spread too wide"
    assert signals[1].spread_status == WORKSPACE_SIGNAL_SPREAD_BLOCKED
    assert signals[2].accepted
    assert signals[2].reason == "accepted for signal display only"
    assert signals[2].spread_status == WORKSPACE_SIGNAL_SPREAD_OK
    assert not signals[3].accepted
    assert signals[3].reason == "spread too wide"
    assert signals[4].accepted

    assert all(signal.workspace_uid == workspace.workspace_uid for signal in signals)
    assert all(signal.account_id == "DUM513747" for signal in signals)
    assert all(signal.symbol == "EURUSD" for signal in signals)

    runtime.handle_order_event({"status": "FILLED"})
    assert probe.order_events == 1
    runtime.stop()
    assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
    assert probe.stopped
    assert probe.market_events == 5

    journal_events: list[str] = [entry.event for entry in runtime.journal]
    assert journal_events.count("SIGNAL_ACCEPTED") == 2
    assert journal_events.count("SIGNAL_REJECTED") == 3
    assert "ORDER_EVENT_PROCESSED" in journal_events

    print("Algorithm Workspace Signal result")
    print(f"  signals={runtime.context.signals_count}")
    print(f"  accepted={runtime.context.accepted_signals_count}")
    print(f"  rejected={runtime.context.rejected_signals_count}")
    print("  warmup_rejected=True")
    print("  spread_rejected=True")
    print("  spread_recovery_accepted=True")
    print("  order_event_forwarded=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_CHECK=OK")


if __name__ == "__main__":
    main()
