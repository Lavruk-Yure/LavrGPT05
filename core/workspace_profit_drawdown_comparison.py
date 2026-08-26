# -*- coding: utf-8 -*-
"""Controlled Historical Replay comparison for Profit Drawdown exit policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary

PROFIT_DRAWDOWN_CONTROLLED_VARIABLE = "PROFIT_DRAWDOWN_POLICY_ONLY"


class WorkspaceProfitDrawdownComparisonError(ValueError):
    """Invalid input for a controlled Profit Drawdown comparison."""


@dataclass(frozen=True, slots=True)
class WorkspaceProfitDrawdownComparisonRun:
    """One completed Replay bound to one Profit Drawdown setting."""

    enabled: bool
    drawdown_percent: float | None
    summary: WorkspaceHistoricalReplaySummary


@dataclass(frozen=True, slots=True)
class WorkspaceProfitDrawdownComparisonVariant:
    """Metrics for one controlled Profit Drawdown setting."""

    enabled: bool
    drawdown_percent: float | None
    signals: int
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
    maximum_drawdown_percent: float
    average_trade: float
    average_winner: float
    average_loser: float
    stop_loss_closes: int
    take_profit_closes: int
    profit_drawdown_closes: int
    session_end_closes: int
    replay_elapsed_seconds: float | None

    @property
    def label(self) -> str:
        """Return a stable console label for this setting."""
        if not self.enabled:
            return "OFF"
        assert self.drawdown_percent is not None
        return f"{self.drawdown_percent:g}%"


@dataclass(frozen=True, slots=True)
class WorkspaceProfitDrawdownComparisonReport:
    """Canonical comparison while only Profit Drawdown policy changes."""

    symbol: str
    strategy_timeframe: str
    source_timeframe: str
    period_start: datetime
    period_end: datetime
    accepted_bars: int
    spread: float
    initial_balance: float
    controlled_variable: str
    variants: tuple[WorkspaceProfitDrawdownComparisonVariant, ...]
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


def build_workspace_profit_drawdown_comparison(
    runs: tuple[WorkspaceProfitDrawdownComparisonRun, ...],
) -> WorkspaceProfitDrawdownComparisonReport:
    """Build one immutable controlled comparison from Replay summaries."""
    if not runs:
        raise WorkspaceProfitDrawdownComparisonError(
            "at least one Profit Drawdown run is required"
        )

    normalized = tuple(_normalized_run(run) for run in runs)
    keys = tuple(_variant_key(run) for run in normalized)
    if len(set(keys)) != len(keys):
        raise WorkspaceProfitDrawdownComparisonError(
            "Profit Drawdown settings must be unique"
        )

    baseline = normalized[0].summary
    binding = _summary_binding(baseline)
    signal_binding = _signal_binding(baseline)
    variants: list[WorkspaceProfitDrawdownComparisonVariant] = []

    for run in normalized:
        summary = run.summary
        if _summary_binding(summary) != binding:
            raise WorkspaceProfitDrawdownComparisonError(
                "Historical Replay inputs differ between drawdown variants"
            )
        if _signal_binding(summary) != signal_binding:
            raise WorkspaceProfitDrawdownComparisonError(
                "signal stream differs between drawdown variants"
            )
        variants.append(
            WorkspaceProfitDrawdownComparisonVariant(
                enabled=run.enabled,
                drawdown_percent=run.drawdown_percent,
                signals=summary.signals.total,
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
                maximum_drawdown_percent=summary.maximum_drawdown_percent,
                average_trade=summary.average_trade,
                average_winner=summary.average_winner,
                average_loser=summary.average_loser,
                stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
                take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
                profit_drawdown_closes=summary.close_reason_count(
                    "PROFIT_DRAWDOWN"
                ),
                session_end_closes=summary.close_reason_count("SESSION_END"),
                replay_elapsed_seconds=summary.replay_elapsed_seconds,
            )
        )

    return WorkspaceProfitDrawdownComparisonReport(
        symbol=baseline.symbol,
        strategy_timeframe=baseline.timeframe,
        source_timeframe=baseline.source_timeframe,
        period_start=baseline.period_start,
        period_end=baseline.period_end,
        accepted_bars=baseline.accepted_bars,
        spread=baseline.spread,
        initial_balance=baseline.initial_balance,
        controlled_variable=PROFIT_DRAWDOWN_CONTROLLED_VARIABLE,
        variants=tuple(variants),
    )


def _normalized_run(
    run: WorkspaceProfitDrawdownComparisonRun,
) -> WorkspaceProfitDrawdownComparisonRun:
    enabled = bool(run.enabled)
    if not enabled:
        if run.drawdown_percent is not None:
            raise WorkspaceProfitDrawdownComparisonError(
                "disabled Profit Drawdown must not define a threshold"
            )
        return WorkspaceProfitDrawdownComparisonRun(
            enabled=False,
            drawdown_percent=None,
            summary=run.summary,
        )

    threshold = _finite_float(run.drawdown_percent, "drawdown_percent")
    if not 0.0 < threshold < 100.0:
        raise WorkspaceProfitDrawdownComparisonError(
            "drawdown_percent must be between 0 and 100"
        )
    return WorkspaceProfitDrawdownComparisonRun(
        enabled=True,
        drawdown_percent=threshold,
        summary=run.summary,
    )


def _variant_key(
    run: WorkspaceProfitDrawdownComparisonRun,
) -> tuple[object, ...]:
    return run.enabled, run.drawdown_percent


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


def _signal_binding(
    summary: WorkspaceHistoricalReplaySummary,
) -> tuple[object, ...]:
    return (
        summary.signals.total,
        summary.signals.buy,
        summary.signals.sell,
        summary.signals.alligator_allow,
        summary.signals.alligator_reject,
        summary.signals.warmup_rejects,
        summary.signals.risk_rejects,
    )


def _finite_float(value: object, field_name: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise WorkspaceProfitDrawdownComparisonError(
            f"{field_name} must be numeric"
        ) from exc
    if not math.isfinite(number):
        raise WorkspaceProfitDrawdownComparisonError(
            f"{field_name} must be finite"
        )
    return number
