# -*- coding: utf-8 -*-
"""RoadMap98 deterministic Historical Replay baseline metrics check."""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_historical_baseline import (  # noqa: E402
    WorkspaceHistoricalBaselineError,
    WorkspaceHistoricalClosedTrade,
    build_workspace_historical_baseline_metrics,
)
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_SESSION_END,
    REPLAY_CLOSE_STOP_LOSS,
    REPLAY_CLOSE_TAKE_PROFIT,
)


def _trade(
    index: int,
    realized_profit: float,
    close_reason: str,
) -> WorkspaceHistoricalClosedTrade:
    return WorkspaceHistoricalClosedTrade(
        trade_uid=f"RPL-POS-{index:06d}",
        realized_profit=realized_profit,
        close_reason=close_reason,
    )


def main() -> None:
    trades = (
        _trade(1, 100.0, REPLAY_CLOSE_TAKE_PROFIT),
        _trade(2, -40.0, REPLAY_CLOSE_STOP_LOSS),
        _trade(3, -60.0, REPLAY_CLOSE_STOP_LOSS),
        _trade(4, 30.0, REPLAY_CLOSE_PROFIT_DRAWDOWN),
        _trade(5, -20.0, REPLAY_CLOSE_SESSION_END),
        _trade(6, 50.0, REPLAY_CLOSE_TAKE_PROFIT),
    )

    metrics = build_workspace_historical_baseline_metrics(trades)
    repeated = build_workspace_historical_baseline_metrics(trades)

    assert metrics == repeated
    assert metrics.trades == 6
    assert metrics.winning_trades == 3
    assert metrics.losing_trades == 3
    assert metrics.break_even_trades == 0
    assert math.isclose(metrics.win_rate_percent, 50.0)
    assert math.isclose(metrics.gross_profit, 180.0)
    assert math.isclose(metrics.gross_loss, -120.0)
    assert math.isclose(metrics.net_profit, 60.0)
    assert math.isclose(metrics.average_trade, 10.0)
    assert metrics.profit_factor is not None
    assert math.isclose(metrics.profit_factor, 1.5)
    assert math.isclose(metrics.maximum_drawdown, 100.0)
    assert metrics.close_reason_count(REPLAY_CLOSE_STOP_LOSS) == 2
    assert metrics.close_reason_count(REPLAY_CLOSE_TAKE_PROFIT) == 2
    assert metrics.close_reason_count(REPLAY_CLOSE_PROFIT_DRAWDOWN) == 1
    assert metrics.close_reason_count(REPLAY_CLOSE_SESSION_END) == 1
    assert metrics.close_reason_count("UNKNOWN") == 0

    empty = build_workspace_historical_baseline_metrics(())
    assert empty.trades == 0
    assert empty.win_rate_percent == 0.0
    assert empty.net_profit == 0.0
    assert empty.average_trade == 0.0
    assert empty.profit_factor is None
    assert empty.maximum_drawdown == 0.0
    assert empty.close_reasons == ()

    try:
        build_workspace_historical_baseline_metrics((trades[0], trades[0]))
    except WorkspaceHistoricalBaselineError as exc:
        assert str(exc) == "duplicate trade_uid"
    else:
        raise AssertionError("duplicate trade_uid must be rejected")

    print("Algorithm Workspace Historical Baseline Report result")
    print(f"  trades={metrics.trades}")
    print(f"  winners={metrics.winning_trades}")
    print(f"  losers={metrics.losing_trades}")
    print(f"  win_rate_percent={metrics.win_rate_percent:.2f}")
    print(f"  gross_profit={metrics.gross_profit:.2f}")
    print(f"  gross_loss={metrics.gross_loss:.2f}")
    print(f"  net_profit={metrics.net_profit:.2f}")
    print(f"  average_trade={metrics.average_trade:.2f}")
    print(f"  profit_factor={metrics.profit_factor:.2f}")
    print(f"  maximum_drawdown={metrics.maximum_drawdown:.2f}")
    print("  close_reasons_deterministic=True")
    print("  empty_report_supported=True")
    print("  duplicate_trade_uid_blocked=True")
    print("ALGORITHM_WORKSPACE_HISTORICAL_BASELINE_REPORT_CHECK=OK")


if __name__ == "__main__":
    main()
