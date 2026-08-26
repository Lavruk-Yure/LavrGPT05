# workspace_macd_quality_parameter_sweep.py — RoadMap99_03
# -*- coding: utf-8 -*-
"""workspace_macd_quality_parameter_sweep — RoadMap99_03 sweep report model.

The module defines the immutable comparison model used for sequential MACD
Quality parameter experiments in Historical Replay. RoadMap99 requires that
only one MACD Quality parameter changes per iteration while the M1 source,
M15 strategy timeframe, Replay period, spread, initial balance, risk policy,
Profit Drawdown, SL/TP policy, and the other MACD Quality thresholds remain
fixed.

The first production use is the prominence sweep. Alligator is intentionally
disabled during this sweep so that the measured differences belong only to
MACD Quality. The selected prominence can later be validated with the existing
SAME_TIMEFRAME Alligator as a separate pipeline stage. The report carries
quality decisions, trade metrics, close reasons, NEXT_BAR_GAP expirations, and
missed-move diagnostics. It never performs broker I/O or broker execution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary

MACD_QUALITY_SWEEP_PARAMETER_PROMINENCE = "MACD_EXTREMUM_MIN_PROMINENCE"


class WorkspaceMacdQualityParameterSweepError(ValueError):
    """Invalid input for a controlled MACD Quality parameter sweep."""


@dataclass(frozen=True, slots=True)
class WorkspaceMacdQualityParameterSweepRun:
    """One completed Replay bound to one value of the controlled parameter."""

    parameter_value: float
    summary: WorkspaceHistoricalReplaySummary
    expired_next_bar_gap_orders: int = 0
    missed_moves: int = 0


@dataclass(frozen=True, slots=True)
class WorkspaceMacdQualityParameterSweepVariant:
    """Normalized metrics for one value of the controlled MACD parameter."""

    parameter_value: float
    signals: int
    buy_signals: int
    sell_signals: int
    quality_accept: int
    quality_reject: int
    extremum_not_found: int
    extremum_too_weak: int
    distance_too_small: int
    cross_too_flat: int
    trades: int
    winners: int
    losers: int
    win_rate_percent: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float | None
    maximum_drawdown: float
    maximum_drawdown_percent: float
    average_trade: float
    stop_loss_closes: int
    take_profit_closes: int
    profit_drawdown_closes: int
    session_end_closes: int
    expired_next_bar_gap_orders: int
    missed_moves: int
    replay_elapsed_seconds: float | None


@dataclass(frozen=True, slots=True)
class WorkspaceMacdQualityParameterSweepReport:
    """Immutable controlled-variable report for one MACD Quality parameter."""

    symbol: str
    strategy_timeframe: str
    source_timeframe: str
    period_start: datetime
    period_end: datetime
    accepted_bars: int
    skipped_bars: int
    gaps: int
    spread: float
    initial_balance: float
    controlled_parameter: str
    fixed_distance: float
    fixed_angle: float
    alligator_enabled: bool
    variants: tuple[WorkspaceMacdQualityParameterSweepVariant, ...]
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


def build_workspace_macd_quality_prominence_sweep(
    runs: tuple[WorkspaceMacdQualityParameterSweepRun, ...],
    *,
    fixed_distance: float,
    fixed_angle: float,
) -> WorkspaceMacdQualityParameterSweepReport:
    """Build and validate a prominence-only RoadMap99 Historical Replay sweep."""
    if len(runs) < 2:
        raise WorkspaceMacdQualityParameterSweepError(
            "at least two prominence variants are required"
        )

    distance = _positive_finite(fixed_distance, "fixed_distance")
    angle = _positive_finite(fixed_angle, "fixed_angle")
    normalized = tuple(_normalize_run(run) for run in runs)
    parameter_values = tuple(run.parameter_value for run in normalized)
    if parameter_values != tuple(sorted(parameter_values)):
        raise WorkspaceMacdQualityParameterSweepError(
            "prominence variants must be ordered from low to high"
        )
    if len(set(parameter_values)) != len(parameter_values):
        raise WorkspaceMacdQualityParameterSweepError(
            "prominence variants must be unique"
        )

    baseline = normalized[0].summary
    binding = _summary_binding(baseline)
    variants: list[WorkspaceMacdQualityParameterSweepVariant] = []
    for run in normalized:
        if _summary_binding(run.summary) != binding:
            raise WorkspaceMacdQualityParameterSweepError(
                "Historical Replay inputs differ between prominence variants"
            )
        variants.append(_build_variant(run))

    result = tuple(variants)
    _validate_prominence_semantics(result)
    return WorkspaceMacdQualityParameterSweepReport(
        symbol=baseline.symbol,
        strategy_timeframe=baseline.timeframe,
        source_timeframe=baseline.source_timeframe,
        period_start=baseline.period_start,
        period_end=baseline.period_end,
        accepted_bars=baseline.accepted_bars,
        skipped_bars=baseline.skipped_bars,
        gaps=baseline.gaps,
        spread=baseline.spread,
        initial_balance=baseline.initial_balance,
        controlled_parameter=MACD_QUALITY_SWEEP_PARAMETER_PROMINENCE,
        fixed_distance=distance,
        fixed_angle=angle,
        alligator_enabled=False,
        variants=result,
    )


def _normalize_run(
    run: WorkspaceMacdQualityParameterSweepRun,
) -> WorkspaceMacdQualityParameterSweepRun:
    value = _positive_finite(run.parameter_value, "parameter_value")
    expired = _non_negative_int(
        run.expired_next_bar_gap_orders,
        "expired_next_bar_gap_orders",
    )
    missed = _non_negative_int(run.missed_moves, "missed_moves")
    return WorkspaceMacdQualityParameterSweepRun(
        parameter_value=value,
        summary=run.summary,
        expired_next_bar_gap_orders=expired,
        missed_moves=missed,
    )


def _build_variant(
    run: WorkspaceMacdQualityParameterSweepRun,
) -> WorkspaceMacdQualityParameterSweepVariant:
    summary = run.summary
    signals = summary.signals
    return WorkspaceMacdQualityParameterSweepVariant(
        parameter_value=run.parameter_value,
        signals=signals.total,
        buy_signals=signals.buy,
        sell_signals=signals.sell,
        quality_accept=signals.macd_quality_accept,
        quality_reject=signals.macd_quality_reject,
        extremum_not_found=signals.macd_extremum_not_found,
        extremum_too_weak=signals.macd_extremum_too_weak,
        distance_too_small=signals.macd_distance_too_small,
        cross_too_flat=signals.macd_cross_too_flat,
        trades=summary.opened_trades,
        winners=summary.winning_trades,
        losers=summary.losing_trades,
        win_rate_percent=summary.win_rate_percent,
        gross_profit=summary.gross_profit,
        gross_loss=summary.gross_loss,
        net_profit=summary.net_profit,
        profit_factor=summary.profit_factor,
        maximum_drawdown=summary.maximum_drawdown,
        maximum_drawdown_percent=summary.maximum_drawdown_percent,
        average_trade=summary.average_trade,
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        session_end_closes=summary.close_reason_count("SESSION_END"),
        expired_next_bar_gap_orders=run.expired_next_bar_gap_orders,
        missed_moves=run.missed_moves,
        replay_elapsed_seconds=summary.replay_elapsed_seconds,
    )


def _validate_prominence_semantics(
    variants: tuple[WorkspaceMacdQualityParameterSweepVariant, ...],
) -> None:
    first = variants[0]
    for variant in variants:
        if variant.signals != first.signals:
            raise WorkspaceMacdQualityParameterSweepError(
                "classic MACD crossover count changed during prominence sweep"
            )
        if variant.buy_signals != first.buy_signals:
            raise WorkspaceMacdQualityParameterSweepError(
                "BUY crossover count changed during prominence sweep"
            )
        if variant.sell_signals != first.sell_signals:
            raise WorkspaceMacdQualityParameterSweepError(
                "SELL crossover count changed during prominence sweep"
            )
        if variant.quality_accept + variant.quality_reject != variant.signals:
            raise WorkspaceMacdQualityParameterSweepError(
                "MACD Quality accept/reject counts do not cover all crossovers"
            )
        reason_total = (
            variant.extremum_not_found
            + variant.extremum_too_weak
            + variant.distance_too_small
            + variant.cross_too_flat
        )
        if reason_total != variant.quality_reject:
            raise WorkspaceMacdQualityParameterSweepError(
                "MACD Quality reject reason counts do not match total rejects"
            )
        if variant.extremum_not_found != first.extremum_not_found:
            raise WorkspaceMacdQualityParameterSweepError(
                "extremum search changed while only prominence varied"
            )

    accepts = tuple(variant.quality_accept for variant in variants)
    if any(current > previous for previous, current in zip(accepts, accepts[1:])):
        raise WorkspaceMacdQualityParameterSweepError(
            "quality accepts increased when prominence became stricter"
        )
    missed = tuple(variant.missed_moves for variant in variants)
    if any(current < previous for previous, current in zip(missed, missed[1:])):
        raise WorkspaceMacdQualityParameterSweepError(
            "missed moves decreased when prominence became stricter"
        )


def _summary_binding(
    summary: WorkspaceHistoricalReplaySummary,
) -> tuple[object, ...]:
    return (
        summary.symbol,
        summary.timeframe,
        summary.source_timeframe,
        summary.period_start,
        summary.period_end,
        summary.accepted_bars,
        summary.skipped_bars,
        summary.gaps,
        round(summary.spread, 12),
        round(summary.initial_balance, 8),
    )


def _positive_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkspaceMacdQualityParameterSweepError(
            f"{field_name} must be a positive finite number"
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise WorkspaceMacdQualityParameterSweepError(
            f"{field_name} must be a positive finite number"
        )
    return number


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkspaceMacdQualityParameterSweepError(
            f"{field_name} must be a non-negative integer"
        )
    if value < 0:
        raise WorkspaceMacdQualityParameterSweepError(
            f"{field_name} must be a non-negative integer"
        )
    return value
