# -*- coding: utf-8 -*-
"""Controlled Historical Replay comparison for MACD zero-line context."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
from core.workspace_historical_summary import WorkspaceHistoricalReplaySummary
from core.workspace_macd import (
    WorkspaceMacdRuntimeProfile,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_signal import WorkspaceSignalProposal

if TYPE_CHECKING:
    from core.workspace_runtime import WorkspaceRuntimeContext

MACD_ZERO_LINE_POLICY_DIRECTIONAL = "DIRECTIONAL_SIDE"
MACD_ZERO_LINE_POLICY_OPPOSITE = "OPPOSITE_SIDE"
MACD_ZERO_LINE_POLICIES = (
    MACD_ZERO_LINE_POLICY_DIRECTIONAL,
    MACD_ZERO_LINE_POLICY_OPPOSITE,
)
MACD_ZERO_LINE_CONTROLLED_VARIABLE = "MACD_ZERO_LINE_CONTEXT_ONLY"


class WorkspaceMacdZeroLineComparisonError(ValueError):
    """Invalid input for a controlled MACD zero-line comparison."""


class WorkspaceMacdZeroLineSignalSource(WorkspaceMacdSignalSource):
    """Experiment-only MACD source that filters crosses by zero-line side."""

    def __init__(
        self,
        *,
        enabled: bool,
        mode: str,
        zero_line_policy: str,
        runtime_profile: WorkspaceMacdRuntimeProfile | None = None,
    ) -> None:
        super().__init__(
            enabled=enabled,
            mode=mode,
            runtime_profile=runtime_profile,
        )
        self.zero_line_policy = _normalized_policy(zero_line_policy)

    @classmethod
    def from_experiment_runtime_context(
        cls,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
        *,
        zero_line_policy: str,
    ) -> WorkspaceMacdZeroLineSignalSource:
        """Build the experiment source from the production profile snapshot."""
        baseline = WorkspaceMacdSignalSource.from_runtime_context(
            context,
            parameters,
        )
        return cls(
            enabled=baseline.enabled,
            mode=baseline.mode,
            zero_line_policy=zero_line_policy,
            runtime_profile=baseline.runtime_profile,
        )

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        proposal = super().on_market_event(event)
        if proposal is None:
            return None
        observation = self.observations[-1]
        macd_value = observation.macd_value
        if macd_value is None or not math.isfinite(macd_value):
            raise WorkspaceMacdZeroLineComparisonError(
                "MACD value is required for zero-line comparison"
            )
        if _zero_line_allows(
            self.zero_line_policy,
            proposal.direction,
            macd_value,
        ):
            return proposal
        return None


class WorkspaceMacdZeroLineReplayAlgorithm(
    WorkspaceMacdAlligatorReplayAlgorithm
):
    """Production RailAlgorithm behavior with one experiment-only filter."""

    def __init__(
        self,
        algorithm_id: str,
        *,
        zero_line_policy: str,
    ) -> None:
        super().__init__(algorithm_id)
        self.zero_line_policy = _normalized_policy(zero_line_policy)

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        super().configure(context, parameters)
        self.source = WorkspaceMacdZeroLineSignalSource.from_experiment_runtime_context(
            context,
            parameters,
            zero_line_policy=self.zero_line_policy,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceMacdZeroLineComparisonRun:
    """One completed Historical Replay bound to one zero-line policy."""

    zero_line_policy: str
    summary: WorkspaceHistoricalReplaySummary


@dataclass(frozen=True, slots=True)
class WorkspaceMacdZeroLineComparisonVariant:
    """Metrics for one controlled zero-line policy."""

    zero_line_policy: str
    signals: int
    buy_signals: int
    sell_signals: int
    alligator_allow: int
    alligator_reject: int
    trades: int
    winners: int
    losers: int
    win_rate_percent: float
    net_profit: float
    profit_factor: float | None
    maximum_drawdown_percent: float
    average_trade: float
    stop_loss_closes: int
    take_profit_closes: int
    profit_drawdown_closes: int
    replay_elapsed_seconds: float | None


@dataclass(frozen=True, slots=True)
class WorkspaceMacdZeroLineComparisonReport:
    """Canonical comparison while only MACD zero-line context changes."""

    symbol: str
    strategy_timeframe: str
    source_timeframe: str
    period_start: datetime
    period_end: datetime
    accepted_bars: int
    spread: float
    initial_balance: float
    controlled_variable: str
    variants: tuple[WorkspaceMacdZeroLineComparisonVariant, ...]
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


def build_workspace_macd_zero_line_comparison(
    runs: tuple[WorkspaceMacdZeroLineComparisonRun, ...],
) -> WorkspaceMacdZeroLineComparisonReport:
    """Build one immutable comparison from completed Replay summaries."""
    if not runs:
        raise WorkspaceMacdZeroLineComparisonError(
            "at least one MACD zero-line run is required"
        )

    policies = tuple(_normalized_policy(run.zero_line_policy) for run in runs)
    if len(set(policies)) != len(policies):
        raise WorkspaceMacdZeroLineComparisonError(
            "MACD zero-line policies must be unique"
        )

    baseline = runs[0].summary
    binding = _summary_binding(baseline)
    variants: list[WorkspaceMacdZeroLineComparisonVariant] = []

    for run, policy in zip(runs, policies):
        summary = run.summary
        if _summary_binding(summary) != binding:
            raise WorkspaceMacdZeroLineComparisonError(
                "Historical Replay inputs differ between zero-line variants"
            )
        variants.append(
            WorkspaceMacdZeroLineComparisonVariant(
                zero_line_policy=policy,
                signals=summary.signals.total,
                buy_signals=summary.signals.buy,
                sell_signals=summary.signals.sell,
                alligator_allow=summary.signals.alligator_allow,
                alligator_reject=summary.signals.alligator_reject,
                trades=summary.opened_trades,
                winners=summary.winning_trades,
                losers=summary.losing_trades,
                win_rate_percent=summary.win_rate_percent,
                net_profit=summary.net_profit,
                profit_factor=summary.profit_factor,
                maximum_drawdown_percent=(
                    summary.maximum_drawdown_percent
                ),
                average_trade=summary.average_trade,
                stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
                take_profit_closes=summary.close_reason_count(
                    "TAKE_PROFIT"
                ),
                profit_drawdown_closes=summary.close_reason_count(
                    "PROFIT_DRAWDOWN"
                ),
                replay_elapsed_seconds=summary.replay_elapsed_seconds,
            )
        )

    return WorkspaceMacdZeroLineComparisonReport(
        symbol=baseline.symbol,
        strategy_timeframe=baseline.timeframe,
        source_timeframe=baseline.source_timeframe,
        period_start=baseline.period_start,
        period_end=baseline.period_end,
        accepted_bars=baseline.accepted_bars,
        spread=baseline.spread,
        initial_balance=baseline.initial_balance,
        controlled_variable=MACD_ZERO_LINE_CONTROLLED_VARIABLE,
        variants=tuple(variants),
    )


def _normalized_policy(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in MACD_ZERO_LINE_POLICIES:
        raise WorkspaceMacdZeroLineComparisonError(
            f"Unsupported MACD zero-line policy: {value}"
        )
    return normalized


def _zero_line_allows(
    policy: str,
    direction: str,
    macd_value: float,
) -> bool:
    normalized_policy = _normalized_policy(policy)
    normalized_direction = str(direction or "").strip().upper()
    if normalized_direction not in {"BUY", "SELL"}:
        raise WorkspaceMacdZeroLineComparisonError(
            f"Unsupported signal direction: {direction}"
        )
    if normalized_policy == MACD_ZERO_LINE_POLICY_DIRECTIONAL:
        if normalized_direction == "BUY":
            return macd_value >= 0.0
        return macd_value <= 0.0
    if normalized_direction == "BUY":
        return macd_value < 0.0
    return macd_value > 0.0


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
