# -*- coding: utf-8 -*-
"""RoadMap98 Replay NEXT_BAR_OPEN gap-expiry contract check."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
    REPLAY_ORDER_STATUS_PENDING_NEXT_BAR_OPEN,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

WORKSPACE_UID = "00000000-0000-4000-8000-000000000098"


def _market_event(
    timestamp: datetime,
    *,
    timeframe: str = "M15",
    price: float = 1.1000,
) -> WorkspaceMarketEvent:
    spread = 0.00012
    bid = price - spread / 2.0
    ask = price + spread / 2.0
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe=timeframe,
        bid=bid,
        ask=ask,
        spread=spread,
        open=price,
        high=price + 0.00020,
        low=price - 0.00020,
        close=price,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _signal(timestamp: datetime, suffix: str) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid=f"signal-next-bar-gap-{suffix}",
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.0002,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="DISABLED",
        spread_status="OK",
        accepted=True,
        reason="deterministic next-bar gap check",
    )


def _engine() -> WorkspaceReplayExecutionEngine:
    return WorkspaceReplayExecutionEngine(
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=1000.0,
            maximum_open_positions=1,
        ),
    )


def main() -> None:
    signal_time = datetime(2026, 1, 2, 21, 45, tzinfo=UTC)
    expected_fill_at = signal_time + timedelta(minutes=15)
    first_after_gap = datetime(2026, 1, 4, 22, 15, tzinfo=UTC)

    gap_engine = _engine()
    created = gap_engine.queue_signal(
        _signal(signal_time, "gap"),
        _market_event(signal_time),
    )
    assert len(created) == 1
    assert created[0].details["expected_fill_at"] == expected_fill_at.isoformat()
    assert gap_engine.pending_orders_count == 1
    assert (
        gap_engine.snapshot().orders[0].status
        == REPLAY_ORDER_STATUS_PENDING_NEXT_BAR_OPEN
    )

    before_expected = gap_engine.on_market_event(
        _market_event(
            signal_time + timedelta(minutes=5),
            timeframe="M1",
        )
    )
    assert before_expected == ()
    assert gap_engine.pending_orders_count == 1
    assert not gap_engine.snapshot().positions

    expired = gap_engine.on_market_event(_market_event(first_after_gap))
    assert len(expired) == 1
    assert expired[0].event == "VIRTUAL_ORDER_EXPIRED_NEXT_BAR_GAP"
    assert expired[0].details["expected_fill_at"] == expected_fill_at.isoformat()
    assert expired[0].details["first_available_at"] == first_after_gap.isoformat()
    assert expired[0].details["broker_execution_attempted"] is False
    gap_snapshot = gap_engine.snapshot()
    assert gap_engine.pending_orders_count == 0
    assert gap_engine.active_positions_count == 0
    assert not gap_snapshot.positions
    assert (
        gap_snapshot.orders[0].status
        == REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP
    )
    assert not gap_snapshot.orders[0].active

    exact_engine = _engine()
    exact_engine.queue_signal(
        _signal(signal_time, "exact"),
        _market_event(signal_time),
    )
    exact_fill = exact_engine.on_market_event(
        _market_event(expected_fill_at, price=1.1005)
    )
    assert len(exact_fill) == 1
    assert exact_fill[0].event == "VIRTUAL_POSITION_OPENED"
    assert exact_engine.pending_orders_count == 0
    assert exact_engine.active_positions_count == 1
    assert exact_engine.snapshot().orders[0].status == "FILLED"

    capacity_engine = _engine()
    capacity_engine.queue_signal(
        _signal(signal_time, "capacity-old"),
        _market_event(signal_time),
    )
    capacity_engine.on_market_event(_market_event(first_after_gap))
    next_signal_time = first_after_gap
    next_created = capacity_engine.queue_signal(
        _signal(next_signal_time, "capacity-new"),
        _market_event(next_signal_time),
    )
    assert len(next_created) == 1
    assert next_created[0].event == "VIRTUAL_ORDER_CREATED"
    assert capacity_engine.pending_orders_count == 1

    print("Algorithm Workspace Replay NEXT_BAR Gap result")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  expected_next_m15_bar_required=True")
    print("  pre_expected_execution_event_does_not_fill=True")
    print("  missing_expected_bar_expires_order=True")
    print("  weekend_gap_not_carried_forward=True")
    print("  exact_next_bar_still_fills=True")
    print("  expired_order_releases_capacity=True")
    print("  expired_status=EXPIRED_NEXT_BAR_GAP")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_NEXT_BAR_GAP_CHECK=OK")


if __name__ == "__main__":
    main()
