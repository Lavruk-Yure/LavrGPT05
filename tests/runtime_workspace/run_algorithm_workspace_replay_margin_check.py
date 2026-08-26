# -*- coding: utf-8 -*-
"""RoadMap98.2 Historical Replay execution and margin mathematics check."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import WORKSPACE_DATA_MODE_REPLAY  # noqa: E402
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceProfitDrawdownGuard,
    WorkspaceProfitProtectionPolicy,
)
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_replay_margin import (  # noqa: E402
    HISTORICAL_REPLAY_LEVERAGE,
    replay_required_margin,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

WORKSPACE_UID = "00000000-0000-4000-8000-000000000098"
START = datetime(2026, 8, 10, 6, 0, tzinfo=UTC)


def _event(
    timestamp: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    spread: float = 0.0002,
) -> WorkspaceMarketEvent:
    half_spread = spread / 2.0
    bid = close - half_spread
    ask = close + half_spread
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=bid,
        ask=ask,
        spread=spread,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _signal(timestamp: datetime, direction: str, suffix: str) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid=f"signal-margin-{suffix}",
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
        signal_type="MACD_CROSS",
        direction=direction,
        strength=0.0002,
        macd_state=f"MACD_CROSS_{direction}",
        alligator_confirmation="SAME_TIMEFRAME_ALLOW",
        spread_status="OK",
        accepted=True,
        reason="deterministic margin mathematics check",
    )


def _engine(
    *,
    volume: float = 1000.0,
    initial_balance: float = 1000.0,
    leverage: float = HISTORICAL_REPLAY_LEVERAGE,
) -> WorkspaceReplayExecutionEngine:
    return WorkspaceReplayExecutionEngine(
        workspace_uid=WORKSPACE_UID,
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=volume,
            maximum_open_positions=2,
        ),
        initial_balance=initial_balance,
        leverage=leverage,
    )


def _open_position(
    engine: WorkspaceReplayExecutionEngine,
    *,
    direction: str,
    suffix: str,
    spread: float = 0.0002,
) -> None:
    signal_event = _event(
        START,
        open_price=1.0000,
        high=1.0200,
        low=0.9800,
        close=1.0000,
        spread=spread,
    )
    engine.queue_signal(_signal(START, direction, suffix), signal_event)
    fill_event = _event(
        START + timedelta(minutes=15),
        open_price=1.1000,
        high=1.1005,
        low=1.0995,
        close=1.1000,
        spread=spread,
    )
    engine.on_market_event(fill_event)


def _session_end_profit(*, leverage: float) -> float:
    engine = _engine(leverage=leverage)
    _open_position(engine, direction="BUY", suffix=f"lev-{leverage:g}")
    close_event = _event(
        START + timedelta(minutes=30),
        open_price=1.1010,
        high=1.1015,
        low=1.1005,
        close=1.1011,
    )
    engine.on_market_event(close_event)
    engine.complete(close_event)
    position = engine.snapshot().positions[0]
    assert position.close_reason == REPLAY_CLOSE_SESSION_END
    return position.current_profit


def _protection_profit(close_reason: str) -> float:
    engine = _engine()
    signal_event = _event(
        START,
        open_price=1.0000,
        high=1.0010,
        low=0.9990,
        close=1.0000,
    )
    engine.queue_signal(_signal(START, "BUY", close_reason), signal_event)
    fill_event = _event(
        START + timedelta(minutes=15),
        open_price=1.0000,
        high=1.0005,
        low=0.9995,
        close=1.0000,
    )
    engine.on_market_event(fill_event)
    position = engine.snapshot().positions[0]
    if close_reason == REPLAY_CLOSE_STOP_LOSS:
        trigger = _event(
            START + timedelta(minutes=30),
            open_price=1.0000,
            high=1.0005,
            low=position.stop_loss - 0.0001,
            close=0.9990,
        )
    else:
        trigger = _event(
            START + timedelta(minutes=30),
            open_price=1.0010,
            high=position.take_profit + 0.0001,
            low=1.0005,
            close=1.0030,
        )
    engine.on_market_event(trigger)
    closed = engine.snapshot().positions[0]
    assert closed.close_reason == close_reason
    return closed.current_profit


def main() -> None:
    assert HISTORICAL_REPLAY_LEVERAGE == 500.0
    required = replay_required_margin(volume=1000.0, price=1.1001)
    assert math.isclose(required, 2.2002, rel_tol=0.0, abs_tol=1e-12)

    buy_engine = _engine()
    _open_position(buy_engine, direction="BUY", suffix="buy")
    opened_buy = buy_engine.snapshot().positions[0]
    assert math.isclose(opened_buy.entry_price, 1.1001, abs_tol=1e-12)
    opened_margin = buy_engine.margin_snapshot()
    assert math.isclose(opened_margin.used_margin, 2.2002, abs_tol=1e-12)
    assert math.isclose(opened_margin.equity, 999.80, abs_tol=1e-12)
    assert math.isclose(
        opened_margin.free_margin,
        997.5998,
        abs_tol=1e-12,
    )

    buy_mark = _event(
        START + timedelta(minutes=30),
        open_price=1.1010,
        high=1.1015,
        low=1.1005,
        close=1.1011,
    )
    buy_engine.on_market_event(buy_mark)
    buy_live = buy_engine.snapshot().positions[0]
    assert math.isclose(buy_live.current_profit, 0.90, abs_tol=1e-12)
    live_margin = buy_engine.margin_snapshot()
    assert math.isclose(live_margin.balance, 1000.00, abs_tol=1e-12)
    assert math.isclose(live_margin.equity, 1000.90, abs_tol=1e-12)

    buy_engine.complete(buy_mark)
    closed_margin = buy_engine.margin_snapshot()
    assert math.isclose(closed_margin.balance, 1000.90, abs_tol=1e-12)
    assert math.isclose(closed_margin.equity, 1000.90, abs_tol=1e-12)
    assert math.isclose(closed_margin.used_margin, 0.0, abs_tol=1e-12)
    assert math.isclose(closed_margin.free_margin, 1000.90, abs_tol=1e-12)

    sell_engine = _engine()
    _open_position(sell_engine, direction="SELL", suffix="sell")
    opened_sell = sell_engine.snapshot().positions[0]
    assert math.isclose(opened_sell.entry_price, 1.0999, abs_tol=1e-12)
    sell_mark = _event(
        START + timedelta(minutes=30),
        open_price=1.0990,
        high=1.0995,
        low=1.0985,
        close=1.0989,
    )
    sell_engine.on_market_event(sell_mark)
    assert math.isclose(
        sell_engine.snapshot().positions[0].current_profit,
        0.90,
        abs_tol=1e-12,
    )

    stop_profit = _protection_profit(REPLAY_CLOSE_STOP_LOSS)
    take_profit = _protection_profit(REPLAY_CLOSE_TAKE_PROFIT)
    assert math.isclose(stop_profit, -2.0, abs_tol=1e-9)
    assert math.isclose(take_profit, 4.0, abs_tol=1e-9)

    drawdown_engine = _engine()
    _open_position(drawdown_engine, direction="BUY", suffix="drawdown")
    peak_event = _event(
        START + timedelta(minutes=30),
        open_price=1.1020,
        high=1.1025,
        low=1.1015,
        close=1.1021,
    )
    drawdown_engine.on_market_event(peak_event)
    pullback_event = _event(
        START + timedelta(minutes=45),
        open_price=1.1015,
        high=1.1018,
        low=1.1010,
        close=1.1015,
    )
    drawdown_engine.on_market_event(pullback_event)
    position = drawdown_engine.snapshot().positions[0]
    guard = WorkspaceProfitDrawdownGuard(
        WorkspaceProfitProtectionPolicy(
            enabled=True,
            activation_mode="AFTER_SPREAD",
            max_drawdown_percent=30.0,
            minimum_profit=0.0,
        )
    )
    decision = guard.evaluate(
        position,
        timestamp=pullback_event.timestamp,
        runtime_ready=True,
        spread_guard_passed=True,
    )
    assert decision.close_requested
    drawdown_engine.close_profit_drawdown((decision,), pullback_event)
    drawdown_closed = drawdown_engine.snapshot().positions[0]
    assert drawdown_closed.close_reason == REPLAY_CLOSE_PROFIT_DRAWDOWN
    assert math.isclose(drawdown_closed.current_profit, 1.30, abs_tol=1e-12)

    pnl_500 = _session_end_profit(leverage=500.0)
    pnl_100 = _session_end_profit(leverage=100.0)
    assert math.isclose(pnl_500, pnl_100, abs_tol=1e-12)
    assert math.isclose(pnl_500, 0.90, abs_tol=1e-12)

    blocked_engine = _engine(volume=100_000.0, initial_balance=100.0)
    signal_event = _event(
        START,
        open_price=1.0000,
        high=1.0200,
        low=0.9800,
        close=1.0000,
    )
    blocked_engine.queue_signal(
        _signal(START, "BUY", "blocked-margin"),
        signal_event,
    )
    fill_event = _event(
        START + timedelta(minutes=15),
        open_price=1.1000,
        high=1.1005,
        low=1.0995,
        close=1.1000,
    )
    lifecycle = blocked_engine.on_market_event(fill_event)
    assert len(lifecycle) == 1
    assert lifecycle[0].event == "VIRTUAL_ORDER_BLOCKED_MARGIN"
    blocked_snapshot = blocked_engine.snapshot()
    assert blocked_snapshot.orders[0].status == "BLOCKED_MARGIN"
    assert blocked_snapshot.orders[0].price is None
    assert not blocked_snapshot.positions
    assert blocked_engine.margin_snapshot().used_margin == 0.0

    print("Algorithm Workspace Replay Margin result")
    print("  historical_replay_leverage=1:500")
    print("  required_margin_usd=2.2002")
    print("  buy_entry_uses_ask_half_spread=True")
    print("  sell_entry_uses_bid_half_spread=True")
    print("  buy_sell_pnl_math=True")
    print("  spread_cost_included=True")
    print("  stop_loss_pnl_math=True")
    print("  take_profit_pnl_math=True")
    print("  profit_drawdown_pnl_math=True")
    print("  balance_equity_realized_unrealized_math=True")
    print("  used_margin_released_on_close=True")
    print("  leverage_does_not_multiply_pnl=True")
    print("  insufficient_free_margin_blocks_fill=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_MARGIN_CHECK=OK")


if __name__ == "__main__":
    main()
