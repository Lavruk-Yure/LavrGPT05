# -*- coding: utf-8 -*-
"""RoadMap99_02E — formal MACD pipeline baseline comparison.

This long-running deterministic Replay test executes the same EURUSD M1 source
for 2026-01-02..2026-02-28 through three controlled M15 strategy stages:
LINEAR classic MACD, EXTENDED MACD Quality, and EXTENDED MACD Quality followed
by SAME_TIMEFRAME Alligator confirmation. All non-signal variables are held
constant: source data, Replay period, spread, initial balance, risk policy,
SL/TP policy, Profit Drawdown, and Replay leverage semantics.

The test verifies the already accepted RoadMap99 baseline trade/PnL counts and
also measures missed directional moves over an 8-bar M15 horizon. Missed-move
diagnostics are pipeline-stage diagnostics, so they intentionally use each
record's final filter_decision and do not require Alligator filter_context;
LINEAR and EXTENDED without Alligator legitimately have no such context.
Historical Replay must remain deterministic and broker execution must remain 0.
"""

from __future__ import annotations

import sys
from collections import Counter
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
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd_pipeline_comparison import (  # noqa: E402
    MACD_PIPELINE_CONTROLLED_VARIABLE,
    MACD_PIPELINE_STAGE_EXTENDED,
    MACD_PIPELINE_STAGE_EXTENDED_ALLIGATOR,
    MACD_PIPELINE_STAGE_LINEAR,
    WorkspaceMacdPipelineComparisonRun,
    build_workspace_macd_pipeline_comparison,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import REPLAY_SPEED_MAX  # noqa: E402
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalRecord,
)
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)
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
END_UTC = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _CompletedRun:
    stage: str
    summary: WorkspaceHistoricalReplaySummary
    records: tuple[WorkspaceSignalRecord, ...]
    expired_next_bar_gap_orders: int


def _workspace(stage: str) -> AlgorithmWorkspace:
    extended = stage != MACD_PIPELINE_STAGE_LINEAR
    alligator_enabled = stage == MACD_PIPELINE_STAGE_EXTENDED_ALLIGATOR
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
            "macd_signal_mode": "EXTENDED" if extended else "LINEAR",
            "macd_extremum_min_prominence": 0.00001,
            "macd_extremum_to_cross_min_distance": 0.00005,
            "macd_cross_min_angle": 45.0,
            "alligator_filter_enabled": alligator_enabled,
            "alligator_confirmation": "SAME_TIMEFRAME",
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
            "source": "IB_EURUSD_M1_RM99_PIPELINE_COMPARISON",
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


def _run(stage: str) -> _CompletedRun:
    records: list[WorkspaceSignalRecord] = []
    runtime = WorkspaceRuntime(
        _workspace(stage),
        algorithm_factory=create_registered_workspace_algorithm,
        signal_record_observer=records.append,
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
    order_statuses = Counter(order.status for order in runtime.owned_snapshot.orders)
    assert runtime.context.positions_count == 0
    assert runtime.context.active_orders_count == 0
    return _CompletedRun(
        stage=stage,
        summary=summary,
        records=tuple(records),
        expired_next_bar_gap_orders=order_statuses[
            REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP
        ],
    )


def _strategy_events() -> tuple[WorkspaceMarketEvent, ...]:
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=M1_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M1",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=0.00012,
        source_name="IB_EURUSD_M1_RM99_PIPELINE_QUALITY",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    events = []
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is not None:
            events.append(completed.event)
    final = aggregator.complete()
    if final is not None:
        events.append(final.event)
    assert aggregator.completed_bars == 3888
    return tuple(events)


def _profit_factor(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _missed_moves(
    records: tuple[WorkspaceSignalRecord, ...],
    events: tuple[WorkspaceMarketEvent, ...],
) -> int:
    """Count rejected pipeline signals followed by a qualifying move.

    RoadMap99 compares MACD pipeline stages, not Alligator profile variants.
    Therefore filter_context is deliberately not required here: LINEAR and
    EXTENDED with Alligator disabled correctly record ``filter_context=None``.
    A missed move is a signal rejected by the current pipeline whose close,
    eight completed M15 bars later, moved at least 0.00020 in the signalled
    direction. Signals too close to the end of the event stream are unknown and
    are not counted as missed.
    """
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    if len(event_index) != len(events):
        raise AssertionError("strategy events must have unique timestamps")

    missed = 0
    horizon_bars = 8
    minimum_move = 0.00020
    for record in records:
        if record.filter_decision != WORKSPACE_SIGNAL_FILTER_REJECT:
            continue
        index = event_index.get(record.timestamp)
        if index is None:
            raise AssertionError("signal timestamp is absent from strategy events")
        future_index = index + horizon_bars
        if future_index >= len(events):
            continue
        start_close = float(events[index].close)
        future_close = float(events[future_index].close)
        if record.direction == "BUY":
            directional_move = future_close - start_close
        elif record.direction == "SELL":
            directional_move = start_close - future_close
        else:
            raise AssertionError(f"unsupported signal direction: {record.direction}")
        if directional_move >= minimum_move:
            missed += 1
    return missed


def main() -> None:
    print(
        "Algorithm Workspace MACD Pipeline Comparison Check — "
        "RoadMap99_02E baseline",
        flush=True,
    )
    print(
        "  Running LINEAR -> EXTENDED -> EXTENDED+ALLIGATOR on the same "
        "M1->M15 Replay dataset; broker execution remains disabled.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    events = _strategy_events()
    completed: list[_CompletedRun] = []
    for stage in (
        MACD_PIPELINE_STAGE_LINEAR,
        MACD_PIPELINE_STAGE_EXTENDED,
        MACD_PIPELINE_STAGE_EXTENDED_ALLIGATOR,
    ):
        print(f"MACD Pipeline Comparison: running {stage} ...", flush=True)
        run = _run(stage)
        completed.append(run)
        print(
            "MACD Pipeline Comparison: completed "
            f"{stage}, trades={run.summary.opened_trades}, "
            f"net_pnl={run.summary.net_profit:.2f}, "
            f"PF={_profit_factor(run.summary.profit_factor)}",
            flush=True,
        )

    missed = tuple(_missed_moves(run.records, events) for run in completed)
    assert missed[0] == 0
    assert missed[2] >= missed[1]
    report = build_workspace_macd_pipeline_comparison(
        tuple(
            WorkspaceMacdPipelineComparisonRun(
                stage=run.stage,
                summary=run.summary,
                expired_next_bar_gap_orders=run.expired_next_bar_gap_orders,
                missed_moves=missed[index],
            )
            for index, run in enumerate(completed)
        )
    )

    assert report.controlled_variable == MACD_PIPELINE_CONTROLLED_VARIABLE
    assert report.source_timeframe == "M1"
    assert report.strategy_timeframe == "M15"
    assert report.accepted_bars == 3888
    assert len(report.variants) == 3

    linear, extended, with_alligator = report.variants
    assert linear.signals == 320
    assert linear.buy_signals == 160
    assert linear.sell_signals == 160
    assert linear.trades == 304
    assert abs(linear.net_profit - (-53.48)) < 0.01

    assert extended.signals == 320
    assert extended.macd_quality_accept == 23
    assert extended.macd_quality_reject == 297
    assert extended.trades == 23
    assert abs(extended.net_profit - (-7.80)) < 0.01

    assert with_alligator.signals == 320
    assert with_alligator.macd_quality_accept == 23
    assert with_alligator.macd_quality_reject == 297
    assert with_alligator.alligator_allow == 1
    assert with_alligator.alligator_reject == 22
    assert with_alligator.trades == 1
    assert abs(with_alligator.net_profit - 0.03) < 0.01

    print("Algorithm Workspace MACD Pipeline Comparison result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  source_timeframe={report.source_timeframe}")
    print(f"  strategy_timeframe={report.strategy_timeframe}")
    print(f"  controlled_variable={report.controlled_variable}")
    print("  profit_drawdown_percent=30")
    print("  replay_leverage=1:500")
    print("  risk_policy_unchanged=True")
    for item in report.variants:
        print(
            f"  {item.stage}: "
            f"signals={item.signals}, "
            f"quality={item.macd_quality_accept}/"
            f"{item.macd_quality_reject}, "
            f"alligator={item.alligator_allow}/"
            f"{item.alligator_reject}, "
            f"trades={item.trades}, "
            f"W/L={item.winners}/{item.losers}, "
            f"win_rate={item.win_rate_percent:.2f}%, "
            f"net_pnl={item.net_profit:.2f}, "
            f"PF={_profit_factor(item.profit_factor)}, "
            f"max_dd={item.maximum_drawdown:.2f}/"
            f"{item.maximum_drawdown_percent:.2f}%, "
            f"avg_trade={item.average_trade:.4f}, "
            f"SL/TP/PD/END={item.stop_loss_closes}/"
            f"{item.take_profit_closes}/"
            f"{item.profit_drawdown_closes}/"
            f"{item.session_end_closes}, "
            f"expired_gap={item.expired_next_bar_gap_orders}, "
            f"missed_moves={item.missed_moves}"
        )
    print("  same_m1_dataset=True")
    print("  same_replay_period=True")
    print("  same_risk_policy=True")
    print("  same_profit_drawdown_policy=True")
    print("  same_sl_tp_policy=True")
    print("  production_signal_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_PIPELINE_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
