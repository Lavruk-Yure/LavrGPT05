# -*- coding: utf-8 -*-
"""Runtime check for WSP warm-up and continuous spread guard."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STARTING,
    AlgorithmWorkspace,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import (  # noqa: E402
    WORKSPACE_STARTUP_PHASE_LOAD_DATA,
    WORKSPACE_STARTUP_PHASE_READY,
    WORKSPACE_STARTUP_PHASE_RUNNING,
    WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
    WORKSPACE_STARTUP_PHASE_WARMUP,
    WorkspaceRuntime,
)


class GuardReplayService(WorkspaceReplayService):
    """Return a fixed spread sequence for deterministic guard testing."""

    def __init__(self, events: tuple[WorkspaceMarketEvent, ...]) -> None:
        self.events = events

    def create_synthetic_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        del broker, symbol, timeframe, replay_settings
        return WorkspaceReplaySession(
            events=self.events,
            source_name="SPREAD_GUARD_TEST",
            speed=1,
        )


def build_event(index: int, spread: float) -> WorkspaceMarketEvent:
    close = 1.17000 + index * 0.00010
    bid = close - spread / 2.0
    ask = close + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=close - 0.00005,
        high=close + 0.00015,
        low=close - 0.00015,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def main() -> None:
    events = (
        build_event(0, 0.00012),
        build_event(1, 0.00030),
        build_event(2, 0.00018),
        build_event(3, 0.00028),
        build_event(4, 0.00014),
    )
    workspace = AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode="PAPER",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={"speed": 1},
    )
    runtime = WorkspaceRuntime(
        workspace,
        replay_service=GuardReplayService(events),
    )

    runtime.begin_start()
    runtime.complete_start()
    assert runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WARMUP
    assert not runtime.can_form_signal()
    assert runtime.context.signal_block_reason == "warmup incomplete"

    runtime.advance_replay()
    assert runtime.context.warmup_bars_processed == 1
    assert not runtime.context.warmup_complete
    assert not runtime.can_form_signal()

    runtime.advance_replay()
    assert runtime.context.warmup_bars_processed == 2
    assert runtime.context.warmup_complete
    assert runtime.context.runtime_state == WORKSPACE_STATE_STARTING
    assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_WAIT_SPREAD
    assert runtime.context.current_spread is not None
    assert runtime.context.current_spread > runtime.context.spread_limit
    assert not runtime.context.spread_ok
    assert runtime.context.signal_block_reason == "spread too wide"
    assert not runtime.can_form_signal()

    runtime.advance_replay()
    assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert runtime.context.startup_phase == WORKSPACE_STARTUP_PHASE_RUNNING
    assert runtime.context.spread_ok
    assert runtime.context.signal_block_reason is None
    assert runtime.can_form_signal()

    runtime.advance_replay()
    assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
    assert not runtime.context.spread_ok
    assert runtime.context.signal_block_reason == "spread too wide"
    assert not runtime.can_form_signal()

    runtime.advance_replay()
    assert runtime.context.spread_ok
    assert runtime.context.signal_block_reason is None
    assert runtime.can_form_signal()

    startup_targets = [
        entry.details["target_phase"]
        for entry in runtime.journal
        if entry.event == "STARTUP_PHASE_CHANGED"
    ]
    assert startup_targets[:5] == [
        WORKSPACE_STARTUP_PHASE_LOAD_DATA,
        WORKSPACE_STARTUP_PHASE_WARMUP,
        WORKSPACE_STARTUP_PHASE_WAIT_SPREAD,
        WORKSPACE_STARTUP_PHASE_READY,
        WORKSPACE_STARTUP_PHASE_RUNNING,
    ]

    journal_events: list[str] = [entry.event for entry in runtime.journal]
    assert "WARMUP_PROGRESS" in journal_events
    assert "WARMUP_COMPLETED" in journal_events
    assert journal_events.count("SPREAD_BLOCKED") == 2
    assert "SPREAD_ACCEPTED" in journal_events
    assert "SIGNALS_RESUMED" in journal_events

    print("Algorithm Workspace Spread Guard result")
    print(f"  warmup_bars={runtime.context.warmup_bars_processed}")
    print(f"  warmup_complete={runtime.context.warmup_complete}")
    print(f"  spread_limit={runtime.context.spread_limit:.6f}")
    print(f"  current_spread={runtime.context.current_spread:.6f}")
    print(f"  startup_sequence={' -> '.join(startup_targets[:5])}")
    print(f"  startup_phase={runtime.context.startup_phase}")
    print(f"  runtime_state={runtime.context.runtime_state}")
    print(f"  signal_allowed={runtime.can_form_signal()}")
    print("  warmup_signal_blocked=True")
    print("  wide_spread_signal_blocked=True")
    print("  spread_recovery_resumed=True")
    print("ALGORITHM_WORKSPACE_SPREAD_GUARD_CHECK=OK")


if __name__ == "__main__":
    main()
