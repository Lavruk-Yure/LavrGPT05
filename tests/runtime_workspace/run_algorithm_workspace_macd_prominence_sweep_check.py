# run_algorithm_workspace_macd_prominence_sweep_check.py — RoadMap99_03
# -*- coding: utf-8 -*-
"""Перший контрольований sweep prominence для MACD Quality у RoadMap99_03.

Модуль виконує довгий детермінований Historical Replay після MD6 baseline
RoadMap99 і змінює тільки параметр ``macd_extremum_min_prominence``. Відстань
extremum->cross лишається 0.000050, калібрований кут перетину — 45°, risk і
Profit Drawdown не змінюються, а Alligator навмисно вимкнений, щоб результат
належав тільки MACD Quality.

Той самий EURUSD M1 source агрегується у завершені M15 strategy bars за період
2026-01-02..2026-02-28. Шість prominence-варіантів виконуються як повні
virtual Replay runs. Звіт містить рішення MACD Quality, торгові метрики,
причини закриття, NEXT_BAR_GAP expirations і missed directional moves за вісім
M15 bars. Production-переможець автоматично не вибирається: тест лише формує
порівнювані дані для ручного аналізу. Broker requests і broker execution у
Historical Replay мають лишатися нульовими.

Функції побудови strategy events, запуску одного prominence-варіанта,
підрахунку missed moves і форматування рядка варіанта є публічним test-harness
API. RoadMap99_03B використовує їх повторно, щоб не дублювати Replay-логіку і
не звертатися до protected members іншого модуля. Версія helper API явно
фіксується, щоб після PATCH не допустити виконання застарілого ``.pyc``.
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
from core.workspace_macd_quality_parameter_sweep import (  # noqa: E402
    MACD_QUALITY_SWEEP_PARAMETER_PROMINENCE,
    WorkspaceMacdQualityParameterSweepRun,
    WorkspaceMacdQualityParameterSweepVariant,
    build_workspace_macd_quality_prominence_sweep,
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
FIXED_DISTANCE = 0.00005
FIXED_ANGLE = 45.0
BASELINE_PROMINENCE = 0.000010
PROMINENCE_SWEEP_HELPER_API_VERSION = "RoadMap99_03E"


PROMINENCE_VALUES = (
    0.000005,
    0.000008,
    BASELINE_PROMINENCE,
    0.000012,
    0.000015,
    0.000020,
)


@dataclass(frozen=True, slots=True)
class _CompletedRun:
    prominence: float
    records: tuple[WorkspaceSignalRecord, ...]
    summary: WorkspaceHistoricalReplaySummary
    expired_next_bar_gap_orders: int


def _workspace(prominence: float) -> AlgorithmWorkspace:
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
            "macd_signal_mode": "EXTENDED",
            "macd_extremum_min_prominence": prominence,
            "macd_extremum_to_cross_min_distance": FIXED_DISTANCE,
            "macd_cross_min_angle": FIXED_ANGLE,
            "alligator_filter_enabled": False,
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
            "source": "IB_EURUSD_M1_RM99_PROMINENCE_SWEEP",
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


def run_prominence_variant(prominence: float) -> _CompletedRun:
    """Виконати один повний Replay для заданого prominence."""
    records: list[WorkspaceSignalRecord] = []
    runtime = WorkspaceRuntime(
        _workspace(prominence),
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
        prominence=prominence,
        records=tuple(records),
        summary=summary,
        expired_next_bar_gap_orders=order_statuses[
            REPLAY_ORDER_STATUS_EXPIRED_NEXT_BAR_GAP
        ],
    )


def build_strategy_events() -> tuple[WorkspaceMarketEvent, ...]:
    """Побудувати канонічну послідовність завершених M15 strategy events."""
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
        source_name="IB_EURUSD_M1_RM99_PROMINENCE_SWEEP",
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    events: list[WorkspaceMarketEvent] = []
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is not None:
            events.append(completed.event)
    final = aggregator.complete()
    if final is not None:
        events.append(final.event)
    assert aggregator.completed_bars == 3888
    return tuple(events)


def count_missed_moves(
    records: tuple[WorkspaceSignalRecord, ...],
    events: tuple[WorkspaceMarketEvent, ...],
) -> int:
    """Порахувати відхилені MACD Quality сигнали з подальшим рухом."""
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


def format_profit_factor_text(value: float | None) -> str:
    """Подати Profit Factor у стабільному текстовому форматі."""
    return "N/A" if value is None else f"{value:.2f}"


def print_prominence_variant(
    variant: WorkspaceMacdQualityParameterSweepVariant,
    *,
    baseline: bool,
) -> None:
    """Надрукувати один рядок метрик prominence-варіанта."""
    prefix = "BASELINE" if baseline else "variant"
    print(
        f"  {prefix} prominence={variant.parameter_value:.6f}: "
        f"quality={variant.quality_accept}/{variant.quality_reject}, "
        f"reasons=N{variant.extremum_not_found}/W{variant.extremum_too_weak}/"
        f"D{variant.distance_too_small}/F{variant.cross_too_flat}, "
        f"trades={variant.trades}, W/L={variant.winners}/{variant.losers}, "
        f"win_rate={variant.win_rate_percent:.2f}%, "
        f"net_pnl={variant.net_profit:.2f}, "
        f"PF={format_profit_factor_text(variant.profit_factor)}, "
        f"DD={variant.maximum_drawdown:.2f}/"
        f"{variant.maximum_drawdown_percent:.2f}%, "
        f"avg={variant.average_trade:.4f}, "
        f"SL/TP/PD/END={variant.stop_loss_closes}/"
        f"{variant.take_profit_closes}/"
        f"{variant.profit_drawdown_closes}/"
        f"{variant.session_end_closes}, "
        f"expired_gap={variant.expired_next_bar_gap_orders}, "
        f"missed_moves={variant.missed_moves}"
    )


def main() -> None:
    print(
        "Algorithm Workspace MACD Prominence Sweep Check — RoadMap99_03",
        flush=True,
    )
    print(
        "  Controlled variable: MACD extremum minimum prominence only. "
        "Distance=0.00005, angle=45°, Alligator=OFF, Profit Drawdown=30%, "
        "M1->M15 Replay; broker execution remains disabled.",
        flush=True,
    )
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    events = build_strategy_events()
    completed: list[_CompletedRun] = []
    for index, prominence in enumerate(PROMINENCE_VALUES, start=1):
        print(
            "MACD Prominence Sweep: running "
            f"{index}/{len(PROMINENCE_VALUES)} prominence={prominence:.6f} ...",
            flush=True,
        )
        run = run_prominence_variant(prominence)
        completed.append(run)
        print(
            "MACD Prominence Sweep: completed "
            f"prominence={prominence:.6f}, "
            f"quality={run.summary.signals.macd_quality_accept}/"
            f"{run.summary.signals.macd_quality_reject}, "
            f"trades={run.summary.opened_trades}, "
            f"net_pnl={run.summary.net_profit:.2f}, "
            f"PF={format_profit_factor_text(run.summary.profit_factor)}",
            flush=True,
        )

    sweep_runs = tuple(
        WorkspaceMacdQualityParameterSweepRun(
            parameter_value=run.prominence,
            summary=run.summary,
            expired_next_bar_gap_orders=run.expired_next_bar_gap_orders,
            missed_moves=count_missed_moves(run.records, events),
        )
        for run in completed
    )
    report = build_workspace_macd_quality_prominence_sweep(
        sweep_runs,
        fixed_distance=FIXED_DISTANCE,
        fixed_angle=FIXED_ANGLE,
    )

    assert report.controlled_parameter == MACD_QUALITY_SWEEP_PARAMETER_PROMINENCE
    assert report.source_timeframe == "M1"
    assert report.strategy_timeframe == "M15"
    assert report.accepted_bars == 3888
    assert report.fixed_distance == FIXED_DISTANCE
    assert report.fixed_angle == FIXED_ANGLE
    assert not report.alligator_enabled
    assert len(report.variants) == len(PROMINENCE_VALUES)
    assert tuple(variant.parameter_value for variant in report.variants) == (
        PROMINENCE_VALUES
    )

    baseline = next(
        variant
        for variant in report.variants
        if abs(variant.parameter_value - BASELINE_PROMINENCE) < 1e-12
    )
    assert baseline.signals == 320
    assert baseline.buy_signals == 160
    assert baseline.sell_signals == 160
    assert baseline.quality_accept == 23
    assert baseline.quality_reject == 297
    assert baseline.trades == 23
    assert abs(baseline.net_profit - (-7.80)) < 0.01

    print("Algorithm Workspace MACD Prominence Sweep result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  source_timeframe={report.source_timeframe}")
    print(f"  strategy_timeframe={report.strategy_timeframe}")
    print(f"  controlled_parameter={report.controlled_parameter}")
    print(f"  fixed_distance={report.fixed_distance:.6f}")
    print(f"  fixed_angle={report.fixed_angle:.2f}")
    print(f"  alligator_enabled={report.alligator_enabled}")
    print("  prominence_variants:")
    for variant in report.variants:
        print_prominence_variant(
            variant,
            baseline=abs(variant.parameter_value - BASELINE_PROMINENCE) < 1e-12,
        )
    print("  selection_deferred_until_manual_analysis=True")
    print("  production_signal_logic_changed=False")
    print("  distance_parameter_changed=False")
    print("  angle_parameter_changed=False")
    print("  alligator_parameters_changed=False")
    print("  profit_drawdown_policy_changed=False")
    print("  risk_policy_changed=False")
    print(f"  deterministic={report.deterministic}")
    print(f"  broker_requests={report.broker_requests}")
    print("  broker_execution_attempted=" f"{report.broker_execution_attempted}")
    print("ALGORITHM_WORKSPACE_MACD_PROMINENCE_SWEEP_CHECK=OK")


if __name__ == "__main__":
    main()
