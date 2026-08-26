# -*- coding: utf-8 -*-
"""RoadMap98.3 Historical Replay per-trade diagnostics check."""

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
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalFilterContext,
    WorkspaceSignalRecord,
)

WORKSPACE_UID = "00000000-0000-4000-8000-000000000983"
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
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=close - half_spread,
        ask=close + half_spread,
        spread=spread,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _signal(
    timestamp: datetime,
    direction: str,
    suffix: str,
) -> WorkspaceSignalRecord:
    return WorkspaceSignalRecord(
        timestamp=timestamp,
        signal_uid=f"diagnostic-signal-{suffix}",
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
        alligator_confirmation="HIGHER_1_ALLOW",
        spread_status="OK",
        accepted=True,
        reason="deterministic historical trade diagnostic",
        filter_context=WorkspaceSignalFilterContext(
            mode="HIGHER_1",
            timeframe="H1",
            profile_uid="builtin-alligator-default",
            profile_revision=1,
            observation_timestamp=timestamp - timedelta(hours=1),
            available_at=timestamp,
        ),
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
        initial_balance=1000.0,
    )


def _run_buy_session_end(engine: WorkspaceReplayExecutionEngine) -> None:
    signal_event = _event(
        START,
        open_price=1.0000,
        high=1.0010,
        low=0.9990,
        close=1.0000,
    )
    engine.queue_signal(_signal(START, "BUY", "buy"), signal_event)
    engine.on_market_event(
        _event(
            START + timedelta(minutes=15),
            open_price=1.1000,
            high=1.1008,
            low=1.0994,
            close=1.1000,
        )
    )
    engine.on_market_event(
        _event(
            START + timedelta(minutes=30),
            open_price=1.1010,
            high=1.1030,
            low=1.1000,
            close=1.1025,
        )
    )
    final_event = _event(
        START + timedelta(minutes=45),
        open_price=1.1020,
        high=1.1035,
        low=1.1015,
        close=1.1020,
    )
    engine.on_market_event(final_event)
    engine.complete(final_event)


def _run_sell_stop_loss(engine: WorkspaceReplayExecutionEngine) -> None:
    signal_time = START + timedelta(hours=1)
    signal_event = _event(
        signal_time,
        open_price=1.2000,
        high=1.2010,
        low=1.1990,
        close=1.2000,
    )
    engine.queue_signal(_signal(signal_time, "SELL", "sell"), signal_event)
    engine.on_market_event(
        _event(
            signal_time + timedelta(minutes=15),
            open_price=1.2000,
            high=1.2005,
            low=1.1995,
            close=1.2000,
        )
    )
    engine.on_market_event(
        _event(
            signal_time + timedelta(minutes=30),
            open_price=1.2010,
            high=1.2022,
            low=1.1980,
            close=1.2015,
        )
    )


def main() -> None:
    engine = _engine()
    _run_buy_session_end(engine)
    _run_sell_stop_loss(engine)

    diagnostics = engine.trade_diagnostics()
    assert len(diagnostics) == 2

    buy = diagnostics[0]
    assert buy.signal_uid == "diagnostic-signal-buy"
    assert buy.signal_timestamp == START
    assert buy.entry_timestamp == START + timedelta(minutes=15)
    assert buy.close_timestamp == START + timedelta(minutes=45)
    assert buy.direction == "BUY"
    assert buy.macd_state == "MACD_CROSS_BUY"
    assert buy.alligator_state == "HIGHER_1_ALLOW"
    assert buy.alligator_timeframe == "H1"
    assert math.isclose(buy.entry_price, 1.1001, abs_tol=1e-12)
    assert math.isclose(buy.close_price, 1.1019, abs_tol=1e-12)
    assert math.isclose(buy.stop_loss_distance, 0.0020, abs_tol=1e-12)
    assert math.isclose(buy.take_profit_distance, 0.0040, abs_tol=1e-12)
    assert math.isclose(
        buy.maximum_favorable_excursion,
        3.4,
        abs_tol=1e-9,
    )
    assert math.isclose(
        buy.maximum_adverse_excursion,
        -0.7,
        abs_tol=1e-9,
    )
    assert math.isclose(buy.peak_profit, 2.3, abs_tol=1e-9)
    assert math.isclose(buy.final_profit, 1.8, abs_tol=1e-9)
    assert buy.close_reason == REPLAY_CLOSE_SESSION_END
    assert buy.holding_seconds == 1800.0

    sell = diagnostics[1]
    assert sell.signal_uid == "diagnostic-signal-sell"
    assert sell.direction == "SELL"
    assert sell.alligator_timeframe == "H1"
    assert sell.close_reason == REPLAY_CLOSE_STOP_LOSS
    assert math.isclose(
        sell.maximum_favorable_excursion,
        0.4,
        abs_tol=1e-9,
    )
    assert math.isclose(
        sell.maximum_adverse_excursion,
        -2.0,
        abs_tol=1e-9,
    )
    assert math.isclose(sell.final_profit, -2.0, abs_tol=1e-9)
    assert sell.holding_seconds == 900.0

    repeated = engine.trade_diagnostics()
    assert repeated == diagnostics
    engine.reset()
    assert engine.trade_diagnostics() == ()

    print("Algorithm Workspace Historical Trade Diagnostics result")
    print(f"  closed_trades={len(diagnostics)}")
    print("  signal_timestamp_preserved=True")
    print("  entry_timestamp_preserved=True")
    print("  direction_and_indicator_state_preserved=True")
    print("  alligator_timeframe_preserved=True")
    print("  sl_tp_distance_preserved=True")
    print("  mfe_mae_deterministic=True")
    print("  peak_profit_separate_from_mfe=True")
    print("  final_profit_and_close_reason_preserved=True")
    print("  holding_time_deterministic=True")
    print("  protection_bar_intrabar_order_not_assumed=True")
    print("  reset_clears_diagnostics=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_HISTORICAL_TRADE_DIAGNOSTICS_CHECK=OK")


if __name__ == "__main__":
    main()
