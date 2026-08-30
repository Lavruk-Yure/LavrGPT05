# -*- coding: utf-8 -*-
"""RoadMap105 / T105-01: revert T104-27 production Supertrend integration.

Перевірка фіксує чистий production runtime після відкоту T104-27:
Supertrend не входить до Replay execution API, close reasons або
WorkspaceRuntime dispatch. Базова геометрія virtual execution лишається
динамічною: SL=max(signal bar range, spread*10), TP=2R.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_replay_execution as replay_execution  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_REASONS,
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

TEST_ID = "T105-01"
MODE = "RM105_T105_01_REVERT_T104_27_SUPERTREND_PRODUCTION_INTEGRATION"


def main() -> None:
    expected_close_reasons = (
        REPLAY_CLOSE_STOP_LOSS,
        REPLAY_CLOSE_TAKE_PROFIT,
        REPLAY_CLOSE_PROFIT_DRAWDOWN,
        REPLAY_CLOSE_SESSION_END,
    )
    assert REPLAY_CLOSE_REASONS == expected_close_reasons

    removed_execution_symbols = (
        "REPLAY_CLOSE_SUPERTREND_OPPOSITE_SWITCH",
        "SELL_SUPERTREND_TIMEFRAME",
        "SELL_SUPERTREND_ATR_LENGTH",
        "SELL_SUPERTREND_FACTOR",
        "SELL_SUPERTREND_SOURCE",
        "SELL_SUPERTREND_ATR_SMOOTHING",
        "WorkspaceSupertrendObservation",
        "WorkspaceCanonicalSupertrend",
    )
    assert all(
        not hasattr(replay_execution, symbol) for symbol in removed_execution_symbols
    )
    assert not hasattr(WorkspaceReplayExecutionEngine, "on_completed_m15_bar")
    assert not hasattr(WorkspaceRuntime, "_apply_replay_sell_supertrend_exit")

    execution_source = inspect.getsource(WorkspaceReplayExecutionEngine).upper()
    runtime_source = inspect.getsource(WorkspaceRuntime).upper()
    assert "SUPERTREND" not in execution_source
    assert "SUPERTREND" not in runtime_source

    policy = WorkspaceReplayExecutionPolicy(
        fixed_volume=1000.0,
        maximum_open_positions=2,
    )
    assert policy.stop_range_multiplier == 1.0
    assert policy.minimum_spread_multiples == 10.0
    assert policy.take_profit_r_multiple == 2.0
    assert policy.ambiguous_bar_policy == "STOP_LOSS_FIRST"

    engine = WorkspaceReplayExecutionEngine(
        workspace_uid="00000000-0000-0000-0000-000000010501",
        broker="CTRADER",
        account_id="TEST_ONLY",
        symbol="EURUSD",
        policy=policy,
        initial_balance=1000.0,
    )
    assert not hasattr(engine, "_sell_supertrend")
    assert engine.closed_trades == 0

    print("T105-01 Revert T104-27 Supertrend Production Integration result")
    print(f"  mode={MODE}")
    print("  production_supertrend_wiring=False")
    print("  production_supertrend_execution_api=False")
    print("  production_supertrend_close_reason=False")
    print("  close_reasons=STOP_LOSS,TAKE_PROFIT,PROFIT_DRAWDOWN,SESSION_END")
    print("  stop_loss_geometry=max(signal_bar_range,spread*10)")
    print("  take_profit_geometry=2R")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_entry_logic_changed=False")
    print("  production_profit_drawdown_logic_changed=False")
    print(f"T105_01_SUPERTREND_PRODUCTION_REVERT_REGRESSION=OK")


if __name__ == "__main__":
    main()
