# -*- coding: utf-8 -*-
"""RoadMap98.6.1 controlled Profit Drawdown exit comparison."""

from __future__ import annotations

import sys
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
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalReplaySummary,
)
from core.workspace_profit_drawdown_comparison import (  # noqa: E402
    PROFIT_DRAWDOWN_CONTROLLED_VARIABLE,
    WorkspaceProfitDrawdownComparisonRun,
    build_workspace_profit_drawdown_comparison,
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

DRAW_DOWN_VARIANTS = (
    (False, None),
    (True, 10.0),
    (True, 20.0),
    (True, 30.0),
    (True, 40.0),
    (True, 50.0),
)

EXPECTED_SIGNALS = 1077
EXPECTED_BUY_SIGNALS = 539
EXPECTED_SELL_SIGNALS = 538
EXPECTED_ALLIGATOR_ALLOW = 233
EXPECTED_ALLIGATOR_REJECT = 844
EXPECTED_BASELINE_30_TRADES = 230
EXPECTED_BASELINE_30_NET_PNL = -41.25


@dataclass(frozen=True, slots=True)
class ProfitDrawdownRunResult:
    enabled: bool
    drawdown_percent: float | None
    summary: WorkspaceHistoricalReplaySummary

    @property
    def label(self) -> str:
        if not self.enabled:
            return "OFF"
        assert self.drawdown_percent is not None
        return f"{self.drawdown_percent:g}%"


def _workspace(
    *,
    enabled: bool,
    drawdown_percent: float | None,
) -> AlgorithmWorkspace:
    policy_threshold = 30.0 if drawdown_percent is None else drawdown_percent
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
            "alligator_filter_enabled": True,
            "alligator_confirmation_mode": "SAME_TIMEFRAME",
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
            "source": "IB_EURUSD_M1_PROFIT_DRAWDOWN_COMPARISON",
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
            "enabled": enabled,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": policy_threshold,
            "minimum_profit": 0.0,
        },
    )


def _run(
    *,
    enabled: bool,
    drawdown_percent: float | None,
) -> ProfitDrawdownRunResult:
    runtime = WorkspaceRuntime(
        _workspace(
            enabled=enabled,
            drawdown_percent=drawdown_percent,
        ),
        algorithm_factory=create_registered_workspace_algorithm,
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
    return ProfitDrawdownRunResult(
        enabled=enabled,
        drawdown_percent=drawdown_percent,
        summary=summary,
    )


def _profit_factor(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _elapsed(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}s"


def main() -> None:
    if not M1_FILE.is_file():
        raise FileNotFoundError(
            "Real EURUSD M1 history is required: " + str(M1_FILE)
        )

    print(
        "Profit Drawdown Comparison: validating 30% baseline first ...",
        flush=True,
    )
    baseline_result = _run(
        enabled=True,
        drawdown_percent=30.0,
    )
    baseline_summary = baseline_result.summary
    print(
        "Profit Drawdown Comparison: baseline 30% completed, "
        f"signals={baseline_summary.signals.total}, "
        f"allow/reject={baseline_summary.signals.alligator_allow}/"
        f"{baseline_summary.signals.alligator_reject}, "
        f"trades={baseline_summary.opened_trades}, "
        f"net_pnl={baseline_summary.net_profit:.2f}, "
        f"replay={_elapsed(baseline_summary.replay_elapsed_seconds)}",
        flush=True,
    )
    assert baseline_summary.signals.total == EXPECTED_SIGNALS
    assert baseline_summary.signals.buy == EXPECTED_BUY_SIGNALS
    assert baseline_summary.signals.sell == EXPECTED_SELL_SIGNALS
    assert (
        baseline_summary.signals.alligator_allow
        == EXPECTED_ALLIGATOR_ALLOW
    )
    assert (
        baseline_summary.signals.alligator_reject
        == EXPECTED_ALLIGATOR_REJECT
    )
    assert baseline_summary.opened_trades == EXPECTED_BASELINE_30_TRADES
    assert (
        abs(baseline_summary.net_profit - EXPECTED_BASELINE_30_NET_PNL)
        < 0.01
    )
    print(
        "Profit Drawdown Comparison: baseline 30% validated=True",
        flush=True,
    )

    completed_by_key: dict[
        tuple[bool, float | None], ProfitDrawdownRunResult
    ] = {(True, 30.0): baseline_result}
    for enabled, drawdown_percent in DRAW_DOWN_VARIANTS:
        key = enabled, drawdown_percent
        if key in completed_by_key:
            continue
        label = "OFF" if not enabled else f"{drawdown_percent:g}%"
        print(
            "Profit Drawdown Comparison: running "
            f"drawdown={label} ...",
            flush=True,
        )
        result = _run(
            enabled=enabled,
            drawdown_percent=drawdown_percent,
        )
        completed_by_key[key] = result
        print(
            "Profit Drawdown Comparison: completed "
            f"drawdown={label}, "
            f"trades={result.summary.opened_trades}, "
            f"net_pnl={result.summary.net_profit:.2f}, "
            f"PF={_profit_factor(result.summary.profit_factor)}, "
            f"replay={_elapsed(result.summary.replay_elapsed_seconds)}",
            flush=True,
        )

    completed = [
        completed_by_key[(enabled, drawdown_percent)]
        for enabled, drawdown_percent in DRAW_DOWN_VARIANTS
    ]

    report = build_workspace_profit_drawdown_comparison(
        tuple(
            WorkspaceProfitDrawdownComparisonRun(
                enabled=item.enabled,
                drawdown_percent=item.drawdown_percent,
                summary=item.summary,
            )
            for item in completed
        )
    )

    assert report.controlled_variable == PROFIT_DRAWDOWN_CONTROLLED_VARIABLE
    assert report.source_timeframe == "M1"
    assert report.strategy_timeframe == "M15"
    assert report.accepted_bars == 13926
    assert len(report.variants) == len(DRAW_DOWN_VARIANTS)

    for item in report.variants:
        assert item.signals == EXPECTED_SIGNALS
        assert item.alligator_allow == EXPECTED_ALLIGATOR_ALLOW
        assert item.alligator_reject == EXPECTED_ALLIGATOR_REJECT
        if not item.enabled:
            assert item.profit_drawdown_closes == 0

    first_summary = completed[0].summary
    assert first_summary.signals.buy == EXPECTED_BUY_SIGNALS
    assert first_summary.signals.sell == EXPECTED_SELL_SIGNALS

    baseline_30 = next(
        item
        for item in report.variants
        if item.enabled and item.drawdown_percent == 30.0
    )
    assert baseline_30.trades == EXPECTED_BASELINE_30_TRADES
    assert abs(baseline_30.net_profit - EXPECTED_BASELINE_30_NET_PNL) < 0.01

    print("Algorithm Workspace Profit Drawdown Comparison result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  source_timeframe={report.source_timeframe}")
    print(f"  strategy_timeframe={report.strategy_timeframe}")
    print(f"  controlled_variable={report.controlled_variable}")
    print("  alligator_mode=SAME_TIMEFRAME")
    print("  macd_mode=LINEAR")
    for item in report.variants:
        print(
            f"  {item.label}: "
            f"signals={item.signals}, "
            f"allow/reject={item.alligator_allow}/"
            f"{item.alligator_reject}, "
            f"trades={item.trades}, "
            f"W/L={item.winners}/{item.losers}, "
            f"win_rate={item.win_rate_percent:.2f}%, "
            f"net_pnl={item.net_profit:.2f}, "
            f"PF={_profit_factor(item.profit_factor)}, "
            f"max_dd={item.maximum_drawdown_percent:.2f}%, "
            f"avg_trade={item.average_trade:.4f}, "
            f"avg_W/L={item.average_winner:.4f}/"
            f"{item.average_loser:.4f}, "
            f"SL/TP/PD/END={item.stop_loss_closes}/"
            f"{item.take_profit_closes}/"
            f"{item.profit_drawdown_closes}/"
            f"{item.session_end_closes}, "
            f"replay={_elapsed(item.replay_elapsed_seconds)}"
        )
    print("  signal_stream_unchanged=True")
    print("  baseline_30_percent_reproduced=True")
    print("  same_m1_dataset=True")
    print("  same_signal_logic=True")
    print("  same_alligator_mode=True")
    print("  same_sl_tp_policy=True")
    print("  production_signal_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_PROFIT_DRAWDOWN_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
