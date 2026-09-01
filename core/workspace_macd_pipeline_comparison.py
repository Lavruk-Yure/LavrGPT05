# -*- coding: utf-8 -*-
"""RoadMap99 canonical comparison model for staged MACD Replay experiments.

The module receives completed Historical Replay summaries for three strictly
ordered stages: LINEAR classic MACD, EXTENDED MACD Quality, and EXTENDED MACD
Quality followed by Alligator confirmation. It normalizes those runs, rejects
input drift between stages, enforces the intended pipeline semantics, and
produces one immutable report suitable for regression tests and MD6 baseline
documentation.

Only the MACD pipeline stage is allowed to vary. Symbol, M1/M15 binding, Replay
period, accepted/skipped bars, gaps, spread, initial balance, risk policy and
exit policy are expected to come from identical runs. The model carries trade
metrics, close reasons, NEXT_BAR_GAP expirations and externally calculated
missed-move diagnostics; it never sends broker requests and never performs
broker execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary

MACD_PIPELINE_CONTROLLED_VARIABLE = "MACD_SIGNAL_PIPELINE_STAGE"
MACD_PIPELINE_STAGE_LINEAR = "LINEAR"
MACD_PIPELINE_STAGE_EXTENDED = "EXTENDED"
MACD_PIPELINE_STAGE_EXTENDED_ALLIGATOR = "EXTENDED+ALLIGATOR"
MACD_PIPELINE_STAGES = (
    MACD_PIPELINE_STAGE_LINEAR,
    MACD_PIPELINE_STAGE_EXTENDED,
    MACD_PIPELINE_STAGE_EXTENDED_ALLIGATOR,
)


class WorkspaceMacdPipelineComparisonError(ValueError):
    """Invalid input for a staged MACD pipeline comparison."""


@dataclass(frozen=True, slots=True)
class WorkspaceMacdPipelineComparisonRun:
    """One completed Replay bound to one canonical MACD pipeline stage."""

    stage: str
    summary: WorkspaceHistoricalReplaySummary
    expired_next_bar_gap_orders: int = 0
    missed_moves: int | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceMacdPipelineComparisonVariant:
    """Comparable metrics for one canonical MACD pipeline stage."""

    stage: str
    signals: int
    buy_signals: int
    sell_signals: int
    macd_quality_accept: int
    macd_quality_reject: int
    alligator_allow: int
    alligator_reject: int
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
    missed_moves: int | None
    replay_elapsed_seconds: float | None


@dataclass(frozen=True, slots=True)
class WorkspaceMacdPipelineComparisonReport:
    """Immutable LINEAR -> EXTENDED -> EXTENDED+Alligator comparison."""

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
    controlled_variable: str
    variants: tuple[WorkspaceMacdPipelineComparisonVariant, ...]
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


def build_workspace_macd_pipeline_comparison(
    runs: tuple[WorkspaceMacdPipelineComparisonRun, ...],
) -> WorkspaceMacdPipelineComparisonReport:
    """Build the canonical RoadMap99 staged comparison from Replay summaries."""
    if len(runs) != len(MACD_PIPELINE_STAGES):
        raise WorkspaceMacdPipelineComparisonError(
            "exactly three canonical MACD pipeline runs are required"
        )

    normalized = tuple(_normalize_run(run) for run in runs)
    stages = tuple(run.stage for run in normalized)
    if stages != MACD_PIPELINE_STAGES:
        raise WorkspaceMacdPipelineComparisonError(
            "MACD pipeline runs must be ordered LINEAR, EXTENDED, " "EXTENDED+ALLIGATOR"
        )

    baseline = normalized[0].summary
    binding = _summary_binding(baseline)
    variants: list[WorkspaceMacdPipelineComparisonVariant] = []
    for run in normalized:
        summary = run.summary
        if _summary_binding(summary) != binding:
            raise WorkspaceMacdPipelineComparisonError(
                "Historical Replay inputs differ between MACD pipeline stages"
            )
        variants.append(_build_variant(run))

    _validate_stage_semantics(tuple(variants))
    return WorkspaceMacdPipelineComparisonReport(
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
        controlled_variable=MACD_PIPELINE_CONTROLLED_VARIABLE,
        variants=tuple(variants),
    )


def _normalize_run(
    run: WorkspaceMacdPipelineComparisonRun,
) -> WorkspaceMacdPipelineComparisonRun:
    stage = str(run.stage or "").strip().upper()
    if stage not in MACD_PIPELINE_STAGES:
        raise WorkspaceMacdPipelineComparisonError(
            f"unsupported MACD pipeline stage: {stage or '<empty>'}"
        )
    expired = _non_negative_int(
        run.expired_next_bar_gap_orders,
        "expired_next_bar_gap_orders",
    )
    missed = run.missed_moves
    if missed is not None:
        missed = _non_negative_int(missed, "missed_moves")
    return WorkspaceMacdPipelineComparisonRun(
        stage=stage,
        summary=run.summary,
        expired_next_bar_gap_orders=expired,
        missed_moves=missed,
    )


def _build_variant(
    run: WorkspaceMacdPipelineComparisonRun,
) -> WorkspaceMacdPipelineComparisonVariant:
    summary = run.summary
    return WorkspaceMacdPipelineComparisonVariant(
        stage=run.stage,
        signals=summary.signals.total,
        buy_signals=summary.signals.buy,
        sell_signals=summary.signals.sell,
        macd_quality_accept=summary.signals.macd_quality_accept,
        macd_quality_reject=summary.signals.macd_quality_reject,
        alligator_allow=summary.signals.alligator_allow,
        alligator_reject=summary.signals.alligator_reject,
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


def _validate_stage_semantics(
    variants: tuple[WorkspaceMacdPipelineComparisonVariant, ...],
) -> None:
    linear, extended, with_alligator = variants
    if linear.signals != extended.signals or linear.signals != with_alligator.signals:
        raise WorkspaceMacdPipelineComparisonError(
            "classic MACD crossover count differs between pipeline stages"
        )
    if linear.buy_signals != extended.buy_signals:
        raise WorkspaceMacdPipelineComparisonError(
            "BUY crossover count differs between LINEAR and EXTENDED"
        )
    if linear.sell_signals != extended.sell_signals:
        raise WorkspaceMacdPipelineComparisonError(
            "SELL crossover count differs between LINEAR and EXTENDED"
        )
    if linear.macd_quality_accept or linear.macd_quality_reject:
        raise WorkspaceMacdPipelineComparisonError(
            "LINEAR stage must not apply MACD Quality"
        )
    if linear.alligator_allow or linear.alligator_reject:
        raise WorkspaceMacdPipelineComparisonError(
            "LINEAR stage must not apply Alligator"
        )
    if extended.alligator_allow or extended.alligator_reject:
        raise WorkspaceMacdPipelineComparisonError(
            "EXTENDED stage must isolate MACD Quality without Alligator"
        )
    if (
        extended.macd_quality_accept != with_alligator.macd_quality_accept
        or extended.macd_quality_reject != with_alligator.macd_quality_reject
    ):
        raise WorkspaceMacdPipelineComparisonError(
            "MACD Quality decisions changed when Alligator was enabled"
        )
    alligator_total = with_alligator.alligator_allow + with_alligator.alligator_reject
    if alligator_total != with_alligator.macd_quality_accept:
        raise WorkspaceMacdPipelineComparisonError(
            "Alligator must evaluate exactly the accepted MACD Quality candidates"
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
        summary.spread,
        summary.initial_balance,
    )


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise WorkspaceMacdPipelineComparisonError(
            f"{field_name} must be a non-negative integer"
        )
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError as exc:
            raise WorkspaceMacdPipelineComparisonError(
                f"{field_name} must be a non-negative integer"
            ) from exc
    else:
        raise WorkspaceMacdPipelineComparisonError(
            f"{field_name} must be a non-negative integer"
        )
    if number < 0:
        raise WorkspaceMacdPipelineComparisonError(
            f"{field_name} must be a non-negative integer"
        )
    return number
