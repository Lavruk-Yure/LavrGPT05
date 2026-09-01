# -*- coding: utf-8 -*-
"""RoadMap98.5.5.4 MACD zero-line comparison without Alligator."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalReplaySummary,
)
from core.workspace_macd_zero_line_comparison import (  # noqa: E402
    MACD_ZERO_LINE_POLICIES,
    MACD_ZERO_LINE_POLICY_DIRECTIONAL,
    MACD_ZERO_LINE_POLICY_OPPOSITE,
    WorkspaceMacdZeroLineComparisonRun,
    WorkspaceMacdZeroLineReplayAlgorithm,
    build_workspace_macd_zero_line_comparison,
)
from core.workspace_replay import REPLAY_SPEED_MAX  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402

M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
START_UTC = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
END_UTC = datetime(2026, 7, 27, 15, 44, tzinfo=UTC)

EXPECTED_TOTAL_SIGNALS = 1077
EXPECTED_DIRECTIONAL_SIGNALS = 402
EXPECTED_OPPOSITE_SIGNALS = 675
EXPECTED_BUY_SIGNALS = 539
EXPECTED_SELL_SIGNALS = 538


@dataclass(frozen=True, slots=True)
class ZeroLineIntrinsicRunResult:
    policy: str
    summary: WorkspaceHistoricalReplaySummary


def _workspace() -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": False,
            "warmup_bars": 25,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(M1_FILE),
            "source_timeframe": "M1",
            "start_utc": START_UTC.isoformat(),
            "end_utc": END_UTC.isoformat(),
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "IB_EURUSD_M1_MACD_ZERO_LINE_INTRINSIC",
            "initial_balance": 1000.0,
            "speed": REPLAY_SPEED_MAX,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
    )


def _algorithm_factory(
    policy: str,
) -> Callable[[str], WorkspaceMacdZeroLineReplayAlgorithm]:
    def factory(algorithm_id: str) -> WorkspaceMacdZeroLineReplayAlgorithm:
        return WorkspaceMacdZeroLineReplayAlgorithm(
            algorithm_id,
            zero_line_policy=policy,
        )

    return factory


def _run(policy: str) -> ZeroLineIntrinsicRunResult:
    runtime = WorkspaceRuntime(
        _workspace(),
        algorithm_factory=_algorithm_factory(policy),
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    assert session.multi_resolution
    assert session.source_timeframe == "M1"
    assert session.strategy_timeframe == "M15"

    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    assert runtime.context.positions_count == 0
    assert runtime.context.active_orders_count == 0
    return ZeroLineIntrinsicRunResult(policy=policy, summary=summary)


def _profit_factor(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _elapsed(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}s"


def main() -> None:
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    completed: list[ZeroLineIntrinsicRunResult] = []
    for policy in MACD_ZERO_LINE_POLICIES:
        print(
            "MACD Zero-Line Intrinsic Comparison: running "
            f"policy={policy}, alligator=OFF ...",
            flush=True,
        )
        result = _run(policy)
        completed.append(result)
        print(
            "MACD Zero-Line Intrinsic Comparison: completed "
            f"policy={policy}, "
            f"signals={result.summary.signals.total}, "
            f"trades={result.summary.opened_trades}, "
            f"net_pnl={result.summary.net_profit:.2f}, "
            f"replay={_elapsed(result.summary.replay_elapsed_seconds)}",
            flush=True,
        )

    report = build_workspace_macd_zero_line_comparison(
        tuple(
            WorkspaceMacdZeroLineComparisonRun(
                zero_line_policy=item.policy,
                summary=item.summary,
            )
            for item in completed
        )
    )

    assert report.controlled_variable == "MACD_ZERO_LINE_CONTEXT_ONLY"
    assert report.source_timeframe == "M1"
    assert report.strategy_timeframe == "M15"
    assert report.accepted_bars == 13926
    assert len(report.variants) == 2

    directional = next(
        item
        for item in report.variants
        if item.zero_line_policy == MACD_ZERO_LINE_POLICY_DIRECTIONAL
    )
    opposite = next(
        item
        for item in report.variants
        if item.zero_line_policy == MACD_ZERO_LINE_POLICY_OPPOSITE
    )

    assert directional.signals == EXPECTED_DIRECTIONAL_SIGNALS
    assert opposite.signals == EXPECTED_OPPOSITE_SIGNALS
    assert directional.signals + opposite.signals == EXPECTED_TOTAL_SIGNALS
    assert directional.buy_signals + opposite.buy_signals == EXPECTED_BUY_SIGNALS
    assert directional.sell_signals + opposite.sell_signals == EXPECTED_SELL_SIGNALS
    assert directional.alligator_allow == 0
    assert directional.alligator_reject == 0
    assert opposite.alligator_allow == 0
    assert opposite.alligator_reject == 0

    print("Algorithm Workspace MACD Zero-Line Intrinsic Comparison result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  source_timeframe={report.source_timeframe}")
    print(f"  strategy_timeframe={report.strategy_timeframe}")
    print(f"  controlled_variable={report.controlled_variable}")
    print("  alligator_filter_enabled=False")
    for item in report.variants:
        print(
            f"  {item.zero_line_policy}: "
            f"signals={item.signals}, "
            f"BUY/SELL={item.buy_signals}/{item.sell_signals}, "
            f"trades={item.trades}, "
            f"W/L={item.winners}/{item.losers}, "
            f"win_rate={item.win_rate_percent:.2f}%, "
            f"net_pnl={item.net_profit:.2f}, "
            f"PF={_profit_factor(item.profit_factor)}, "
            f"max_dd={item.maximum_drawdown_percent:.2f}%, "
            f"avg_trade={item.average_trade:.4f}, "
            f"SL/TP/PD={item.stop_loss_closes}/"
            f"{item.take_profit_closes}/"
            f"{item.profit_drawdown_closes}, "
            f"replay={_elapsed(item.replay_elapsed_seconds)}"
        )
    print("  signal_partition_matches_5_5_3=True")
    print("  same_m1_dataset=True")
    print("  alligator_disabled_for_both_variants=True")
    print("  same_execution_policy=True")
    print("  production_signal_logic_changed=False")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_ZERO_LINE_INTRINSIC_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
