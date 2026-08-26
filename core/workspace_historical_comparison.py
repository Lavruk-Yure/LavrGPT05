# -*- coding: utf-8 -*-
"""Canonical comparison of completed Historical Replay Alligator variants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary
from core.workspace_signal_statistics import WorkspaceSignalComparisonReport
from engine.runtime_constants import (
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

HISTORICAL_COMPARISON_MODES = (
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_1,
    WORKSPACE_ALLIGATOR_CONFIRMATION_HIGHER_2,
)


class WorkspaceHistoricalComparisonError(ValueError):
    """Invalid or non-comparable Historical Replay variant input."""


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalComparisonRun:
    """One completed Replay summary explicitly bound to an Alligator mode."""

    mode: str
    summary: WorkspaceHistoricalReplaySummary


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalComparisonVariant:
    """Metrics shown for one controlled Alligator experiment variant."""

    mode: str
    alligator_timeframe: str | None
    signals: int
    allowed_signals: int
    rejected_signals: int
    missed_profitable_moves: int
    average_confirmation_delay_seconds: float | None
    trades: int
    win_rate_percent: float
    net_profit: float
    profit_factor: float | None
    maximum_drawdown: float
    maximum_drawdown_percent: float
    average_trade: float


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalComparisonReport:
    """Four-way controlled comparison on one identical Historical dataset."""

    symbol: str
    timeframe: str
    period_start: datetime
    period_end: datetime
    accepted_bars: int
    skipped_bars: int
    gaps: int
    spread: float
    initial_balance: float
    quality_horizon_bars: int
    quality_minimum_directional_move: float
    variants: tuple[WorkspaceHistoricalComparisonVariant, ...]
    proposal_signatures_identical: bool
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


def build_workspace_historical_mode_comparison(
    runs: tuple[WorkspaceHistoricalComparisonRun, ...],
    signal_report: WorkspaceSignalComparisonReport,
) -> WorkspaceHistoricalComparisonReport:
    """Build the canonical MACD/SAME/HIGHER_1/HIGHER_2 comparison."""
    if len(runs) != len(HISTORICAL_COMPARISON_MODES):
        raise WorkspaceHistoricalComparisonError(
            "comparison requires exactly four Alligator variants"
        )

    run_by_mode: dict[str, WorkspaceHistoricalReplaySummary] = {}
    for run in runs:
        mode = str(run.mode or "").strip().upper()
        if mode not in HISTORICAL_COMPARISON_MODES:
            raise WorkspaceHistoricalComparisonError(
                f"unsupported comparison mode: {mode}"
            )
        if mode in run_by_mode:
            raise WorkspaceHistoricalComparisonError(
                f"duplicate comparison mode: {mode}"
            )
        run_by_mode[mode] = run.summary

    if tuple(run_by_mode) != HISTORICAL_COMPARISON_MODES:
        missing = tuple(
            mode
            for mode in HISTORICAL_COMPARISON_MODES
            if mode not in run_by_mode
        )
        if missing:
            raise WorkspaceHistoricalComparisonError(
                f"comparison modes are incomplete: {missing}"
            )

    quality_by_mode = {item.mode: item for item in signal_report.variants}
    if set(quality_by_mode) != set(HISTORICAL_COMPARISON_MODES):
        raise WorkspaceHistoricalComparisonError(
            "signal comparison modes do not match Replay runs"
        )
    if not signal_report.proposal_signatures_identical:
        raise WorkspaceHistoricalComparisonError(
            "MACD proposal signatures differ between variants"
        )

    baseline = run_by_mode[HISTORICAL_COMPARISON_MODES[0]]
    baseline_binding = _summary_binding(baseline)
    result: list[WorkspaceHistoricalComparisonVariant] = []

    for mode in HISTORICAL_COMPARISON_MODES:
        summary = run_by_mode[mode]
        if _summary_binding(summary) != baseline_binding:
            raise WorkspaceHistoricalComparisonError(
                "Historical Replay inputs differ between variants"
            )
        quality = quality_by_mode[mode]
        if quality.signals != summary.signals.total:
            raise WorkspaceHistoricalComparisonError(
                f"signal count mismatch for mode {mode}"
            )
        if quality.rejected != summary.signals.alligator_reject:
            if mode != WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED:
                raise WorkspaceHistoricalComparisonError(
                    f"Alligator reject count mismatch for mode {mode}"
                )
        result.append(
            WorkspaceHistoricalComparisonVariant(
                mode=mode,
                alligator_timeframe=(
                    None
                    if mode == WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
                    else quality.alligator_timeframe
                ),
                signals=quality.signals,
                allowed_signals=quality.allowed,
                rejected_signals=quality.rejected,
                missed_profitable_moves=quality.missed_signals,
                average_confirmation_delay_seconds=(
                    None
                    if mode == WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
                    else quality.confirmation_delay_average_seconds
                ),
                trades=summary.opened_trades,
                win_rate_percent=summary.win_rate_percent,
                net_profit=summary.net_profit,
                profit_factor=summary.profit_factor,
                maximum_drawdown=summary.maximum_drawdown,
                maximum_drawdown_percent=summary.maximum_drawdown_percent,
                average_trade=summary.average_trade,
            )
        )

    return WorkspaceHistoricalComparisonReport(
        symbol=baseline.symbol,
        timeframe=baseline.timeframe,
        period_start=baseline.period_start,
        period_end=baseline.period_end,
        accepted_bars=baseline.accepted_bars,
        skipped_bars=baseline.skipped_bars,
        gaps=baseline.gaps,
        spread=baseline.spread,
        initial_balance=baseline.initial_balance,
        quality_horizon_bars=signal_report.policy.horizon_bars,
        quality_minimum_directional_move=(
            signal_report.policy.minimum_directional_move
        ),
        variants=tuple(result),
        proposal_signatures_identical=True,
    )


def _summary_binding(
    summary: WorkspaceHistoricalReplaySummary,
) -> tuple[object, ...]:
    return (
        summary.symbol,
        summary.timeframe,
        summary.period_start,
        summary.period_end,
        summary.accepted_bars,
        summary.skipped_bars,
        summary.gaps,
        summary.spread,
        summary.initial_balance,
    )
