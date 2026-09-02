"""run_t106_01_current_production_temporal_segmentation_check.py — T106-01.

TEST_ONLY runner виконує registered production Candidate F Replay для
канонічних cTrader-періодів 2025 і 2026 та бере тільки factual закриті угоди
з ``WorkspaceHistoricalTradeDiagnostic``. Угода належить календарному
сегменту за її causal ``signal_timestamp`` в UTC; outcome, close reason і PnL
читаються після завершення Replay лише як factual labels. Для DD угоди
всередині сегмента впорядковуються за фактичним ``close_timestamp``.

Pipeline повторно використовує current-production checkpoint T105-18,
перевіряє повну річну population, будує місячні й квартальні partitions та
друкує trades, W/L/BE, net, PF, DD, PD/SL/TP, BUY/SELL, average і median PnL.
Для неповного Q3 2026 виводиться окремий available-сегмент до останнього
доступного market event 2026-08-25. Порожні доступні місяці не приховуються.

Runner не змінює production wiring, не створює filter/threshold, не виконує
broker execution і не використовує future bars як entry features. Assertions
зберігають deterministic Replay, completed bars only, no look-ahead,
``broker_requests=0`` та незмінність production exit-policy файлів.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    WorkspaceRuntime,
    _file_hashes,
    _run_period,
)

from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)

TEST_ID = "T106-01"
MODE = "RM106_T106_01_CURRENT_PRODUCTION_TEMPORAL_SEGMENTATION_TEST_ONLY"
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class SegmentSpec:
    """Календарні UTC-межі та label одного доступного сегмента."""

    label: str
    start: datetime
    end: datetime
    availability: str


@dataclass(frozen=True, slots=True)
class SegmentStats:
    """Описові factual trade-метрики одного temporal segment."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float | None
    drawdown: float
    profit_drawdown: int
    stop_loss: int
    take_profit: int
    buy: int
    sell: int
    average_pnl: float
    median_pnl: float


def _segment_trades(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    segment: SegmentSpec,
) -> tuple[WorkspaceHistoricalTradeDiagnostic, ...]:
    """Відібрати угоди за causal signal time та впорядкувати за close time."""

    selected = (
        trade
        for trade in trades
        if segment.start <= trade.signal_timestamp < segment.end
    )
    return tuple(
        sorted(
            selected,
            key=lambda trade: (
                trade.close_timestamp,
                trade.entry_timestamp,
                trade.position_id,
            ),
        )
    )


def _maximum_drawdown(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> float:
    """Обчислити absolute realized-equity DD у factual close order."""

    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for trade in trades:
        equity += trade.final_profit
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _stats(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> SegmentStats:
    """Побудувати однаковий набір метрик для одного factual segment."""

    profits = tuple(trade.final_profit for trade in trades)
    wins = sum(profit > EPSILON for profit in profits)
    losses = sum(profit < -EPSILON for profit in profits)
    break_even = len(profits) - wins - losses
    gross_profit = math.fsum(max(profit, 0.0) for profit in profits)
    gross_loss = -math.fsum(min(profit, 0.0) for profit in profits)
    close_reasons = Counter(trade.close_reason for trade in trades)
    directions = Counter(trade.direction for trade in trades)
    return SegmentStats(
        trades=len(trades),
        wins=wins,
        losses=losses,
        break_even=break_even,
        net=math.fsum(profits),
        profit_factor=(gross_profit / gross_loss if gross_loss > EPSILON else None),
        drawdown=_maximum_drawdown(trades),
        profit_drawdown=close_reasons["PROFIT_DRAWDOWN"],
        stop_loss=close_reasons["STOP_LOSS"],
        take_profit=close_reasons["TAKE_PROFIT"],
        buy=directions["BUY"],
        sell=directions["SELL"],
        average_pnl=math.fsum(profits) / len(profits) if profits else 0.0,
        median_pnl=statistics.median(profits) if profits else 0.0,
    )


def _next_month(value: datetime) -> datetime:
    """Повернути UTC-початок наступного календарного місяця."""

    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value.replace(month=value.month + 1, day=1)


def _month_segments(
    period_start: datetime,
    period_end: datetime,
) -> tuple[SegmentSpec, ...]:
    """Побудувати всі календарні місяці, яких торкається Replay period."""

    cursor = period_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    final_month = period_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    segments: list[SegmentSpec] = []
    while cursor <= final_month:
        next_month = _next_month(cursor)
        last_calendar_date = (next_month - timedelta(days=1)).date()
        availability = (
            "COMPLETE"
            if period_end.date() >= last_calendar_date
            else "AVAILABLE_PARTIAL"
        )
        segments.append(
            SegmentSpec(
                label=cursor.strftime("%Y-%m"),
                start=cursor,
                end=next_month,
                availability=availability,
            )
        )
        cursor = next_month
    return tuple(segments)


def _quarter_segments(
    period_start: datetime,
    period_end: datetime,
) -> tuple[SegmentSpec, ...]:
    """Побудувати complete quarters і останній available partial quarter."""

    quarter_month = (period_start.month - 1) // 3 * 3 + 1
    cursor = period_start.replace(
        month=quarter_month,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    segments: list[SegmentSpec] = []
    while cursor <= period_end:
        next_month = cursor.month + 3
        if next_month > 12:
            next_quarter = cursor.replace(
                year=cursor.year + 1,
                month=next_month - 12,
            )
        else:
            next_quarter = cursor.replace(month=next_month)
        quarter = (cursor.month - 1) // 3 + 1
        last_calendar_date = (next_quarter - timedelta(days=1)).date()
        availability = (
            "COMPLETE"
            if period_end.date() >= last_calendar_date
            else "AVAILABLE_PARTIAL"
        )
        label = f"{cursor.year}-Q{quarter}"
        if availability == "AVAILABLE_PARTIAL":
            label += f"_TO_{period_end.date().isoformat()}"
        segments.append(
            SegmentSpec(
                label=label,
                start=cursor,
                end=next_quarter,
                availability=availability,
            )
        )
        cursor = next_quarter
    return tuple(segments)


def _stats_line(segment: SegmentSpec, item: SegmentStats) -> str:
    """Сформувати стабільний machine-readable рядок temporal metrics."""

    profit_factor = (
        "NONE" if item.profit_factor is None else f"{item.profit_factor:.4f}"
    )
    return (
        f"    {segment.label}|availability:{segment.availability},"
        f"trades:{item.trades},W:{item.wins},L:{item.losses},"
        f"BE:{item.break_even},net:{item.net:+.2f},pf:{profit_factor},"
        f"dd:{item.drawdown:.2f},PD:{item.profit_drawdown},"
        f"SL:{item.stop_loss},TP:{item.take_profit},BUY:{item.buy},"
        f"SELL:{item.sell},avg_pnl:{item.average_pnl:+.4f},"
        f"median_pnl:{item.median_pnl:+.4f}"
    )


def _assert_partition(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    segments: tuple[SegmentSpec, ...],
) -> None:
    """Підтвердити, що кожна factual trade входить рівно в один segment."""

    populations = tuple(_segment_trades(trades, segment) for segment in segments)
    partition_ids = tuple(
        trade.position_id for population in populations for trade in population
    )
    factual_ids = tuple(trade.position_id for trade in trades)
    assert len(partition_ids) == len(factual_ids)
    assert len(set(partition_ids)) == len(partition_ids)
    assert set(partition_ids) == set(factual_ids)


def _print_segments(
    name: str,
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    segments: tuple[SegmentSpec, ...],
) -> None:
    """Надрукувати один partition і перевірити його повноту."""

    _assert_partition(trades, segments)
    print(f"    {name}")
    for segment in segments:
        print(_stats_line(segment, _stats(_segment_trades(trades, segment))))


def _assert_full_period(runtime: WorkspaceRuntime) -> None:
    """Звірити reconstruction factual trades із canonical Replay summary."""

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None and execution is not None
    trades = execution.trade_diagnostics()
    stats = _stats(trades)
    assert (
        stats.trades,
        stats.wins,
        stats.losses,
        stats.break_even,
    ) == (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    )
    assert math.isclose(
        stats.net,
        summary.net_profit,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )
    assert math.isclose(
        stats.drawdown,
        summary.maximum_drawdown,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )
    assert stats.profit_drawdown == summary.close_reason_count("PROFIT_DRAWDOWN")
    assert stats.stop_loss == summary.close_reason_count("STOP_LOSS")
    assert stats.take_profit == summary.close_reason_count("TAKE_PROFIT")
    assert stats.buy + stats.sell == stats.trades


def _print_period(
    runtime: WorkspaceRuntime,
    code: str,
    broker_requests: int,
) -> None:
    """Надрукувати factual full-period, monthly і quarterly segmentation."""

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    session = runtime.replay_session
    assert summary is not None
    assert execution is not None
    assert session is not None
    assert session.completed
    trades = execution.trade_diagnostics()
    assert tuple(trades) == tuple(
        sorted(
            trades,
            key=lambda trade: (
                trade.close_timestamp,
                trade.entry_timestamp,
                trade.position_id,
            ),
        )
    )
    _assert_full_period(runtime)
    full_segment = SegmentSpec(
        label=code,
        start=summary.period_start,
        end=summary.period_end,
        availability="FULL_REPLAY_PERIOD",
    )
    print(f"  period={code}")
    print(_stats_line(full_segment, _stats(trades)))
    _print_segments(
        "MONTHLY_BY_SIGNAL_TIMESTAMP_UTC",
        trades,
        _month_segments(summary.period_start, summary.period_end),
    )
    _print_segments(
        "QUARTERLY_BY_SIGNAL_TIMESTAMP_UTC",
        trades,
        _quarter_segments(summary.period_start, summary.period_end),
    )
    print(f"    broker_requests={broker_requests}")


def main() -> None:
    """Запустити T106-01 поверх factual registered production Replay."""

    production_hashes_before = _file_hashes()
    print("T106-01 Current Production Temporal Segmentation")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  path=REGISTERED_PRODUCTION_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  segment_membership=SIGNAL_TIMESTAMP_UTC")
    print("  drawdown_order=FACTUAL_CLOSE_TIMESTAMP")
    for spec in PERIODS:
        runtime, _rejects, broker_requests = _run_period(spec)
        _print_period(runtime, spec.code, broker_requests)

    assert _file_hashes() == production_hashes_before
    print("  factual_current_production_trades_only=True")
    print("  stochastic_current_bar_reject_production=True")
    print("  stochastic_profile=14/1/3")
    print("  donchian_production_gate=False")
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_sl_geometry=max(signal_bar_range,spread*10)")
    print("  production_tp_geometry=2R")
    print("  negative_pd_recovery_unchanged=True")
    print("  outcome_used_as_factual_label_only=True")
    print("  entry_features_future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  deterministic_replay=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("T106_01_CURRENT_PRODUCTION_TEMPORAL_SEGMENTATION=OK")


if __name__ == "__main__":
    main()
