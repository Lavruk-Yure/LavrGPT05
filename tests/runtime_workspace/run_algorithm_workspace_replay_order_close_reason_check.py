# -*- coding: utf-8 -*-
"""RoadMap97 Replay virtual order close-reason contract check."""

from __future__ import annotations

import ast
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_STOP_LOSS,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"


def _market_event(
    timestamp: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> WorkspaceMarketEvent:
    bid = close - 0.0001
    ask = close + 0.0001
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=ask - bid,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _signal(timestamp: datetime) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid="signal-order-close-1",
        workspace_uid="00000000-0000-4000-8000-000000000097",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.0002,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="SAME_TIMEFRAME_BULLISH",
        spread_status="OK",
        accepted=True,
        reason="accepted for signal display only",
    )


def _order_columns() -> tuple[tuple[str, str], ...]:
    source = AREA_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "ORDER_TABLE_COLUMNS":
            value = ast.literal_eval(node.value)
            assert isinstance(value, tuple)
            return value
    raise AssertionError("ORDER_TABLE_COLUMNS not found")


def main() -> None:
    start = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)
    engine = WorkspaceReplayExecutionEngine(
        workspace_uid="00000000-0000-4000-8000-000000000097",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=1000.0,
            maximum_open_positions=1,
        ),
    )

    signal_event = _market_event(
        start,
        open_price=1.1000,
        high=1.1010,
        low=1.0990,
        close=1.1000,
    )
    queued = engine.queue_signal(_signal(start), signal_event)
    assert len(queued) == 1

    pending_order = engine.snapshot().orders[0]
    assert pending_order.order_type == "VIRTUAL_MARKET"
    assert pending_order.broker_order_id is None
    assert pending_order.side == "BUY"
    assert pending_order.volume == 1000.0
    assert pending_order.price is None
    assert pending_order.status == "PENDING_NEXT_BAR_OPEN"
    assert pending_order.close_reason is None

    fill_event = _market_event(
        start + timedelta(minutes=15),
        open_price=1.1005,
        high=1.1010,
        low=1.1000,
        close=1.1006,
    )
    engine.on_market_event(fill_event)
    filled_snapshot = engine.snapshot()
    filled_order = filled_snapshot.orders[0]
    position = filled_snapshot.positions[0]
    assert filled_order.status == "FILLED"
    assert filled_order.price == position.entry_price
    assert filled_order.stop_loss == position.stop_loss
    assert filled_order.take_profit == position.take_profit
    assert filled_order.close_reason is None

    close_event = _market_event(
        start + timedelta(minutes=30),
        open_price=1.1000,
        high=1.1005,
        low=1.0980,
        close=1.0985,
    )
    engine.on_market_event(close_event)
    closed_snapshot = engine.snapshot()
    closed_order = closed_snapshot.orders[0]
    closed_position = closed_snapshot.positions[0]

    assert closed_order.status == "FILLED"
    assert closed_order.close_reason == REPLAY_CLOSE_STOP_LOSS
    assert closed_position.reconciliation_status.endswith(REPLAY_CLOSE_STOP_LOSS)
    assert math.isclose(
        closed_order.profit,
        closed_position.current_profit,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert closed_order.broker_order_id is None

    columns = _order_columns()
    assert len(columns) == 12
    assert columns[9][0] == "AlgorithmWorkspaceWindow.colCloseReason"
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colCloseReason",
            "uk",
        )
        == "Причина закриття"
    )

    area_source = AREA_PATH.read_text(encoding="utf-8")
    assert "self._display_text(order.close_reason)" in area_source
    assert "table.setColumnHidden(1" in area_source

    print("Algorithm Workspace Replay order close reason result")
    print("  virtual_market_order=True")
    print("  side_volume_entry_sl_tp_visible=True")
    print("  fill_status_preserved=True")
    print("  close_reason_propagated=True")
    print("  realized_profit_propagated=True")
    print("  replay_broker_order_id_absent=True")
    print("  close_reason_ui_column=True")
    print("  close_reason_ukrainian_header=True")
    print("ALGORITHM_WORKSPACE_REPLAY_ORDER_CLOSE_REASON_CHECK=OK")


if __name__ == "__main__":
    main()
