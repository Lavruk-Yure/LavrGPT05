# -*- coding: utf-8 -*-
"""Canonical completed-run summary for Historical Replay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.workspace_historical_baseline import (
    WorkspaceHistoricalClosedTrade,
    build_workspace_historical_baseline_metrics,
)
from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import normalize_market_timestamp
from core.workspace_macd_crossover_quality import (
    MACD_QUALITY_REASON_ACCEPTED,
    MACD_QUALITY_REASON_CROSS_TOO_FLAT,
    MACD_QUALITY_REASON_DISTANCE_TOO_SMALL,
    MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND,
    MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
)
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalRecord,
)
from engine.risk.constants import RISK_DECISION_BLOCK
from engine.runtime_constants import WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalSignalMetrics:
    """Full-run signal counters independent of the bounded WSP table."""

    total: int = 0
    buy: int = 0
    sell: int = 0
    alligator_allow: int = 0
    alligator_reject: int = 0
    warmup_rejects: int = 0
    risk_rejects: int = 0
    macd_quality_accept: int = 0
    macd_quality_reject: int = 0
    macd_extremum_not_found: int = 0
    macd_extremum_too_weak: int = 0
    macd_distance_too_small: int = 0
    macd_cross_too_flat: int = 0


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalReplaySummary:
    """Canonical facts for one completed Historical Replay run."""

    symbol: str
    timeframe: str
    period_start: datetime
    period_end: datetime
    accepted_bars: int
    skipped_bars: int
    gaps: int
    spread: float
    initial_balance: float
    final_balance: float
    signals: WorkspaceHistoricalSignalMetrics
    opened_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    win_rate_percent: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    average_trade: float
    average_winner: float
    average_loser: float
    maximum_winner: float
    maximum_loser: float
    profit_factor: float | None
    maximum_drawdown: float
    maximum_drawdown_percent: float
    maximum_consecutive_losses: int
    maximum_consecutive_wins: int
    peak_balance: float
    minimum_balance: float
    close_reasons: tuple[tuple[str, int], ...]
    source_timeframe: str = ""
    csv_selection_elapsed_seconds: float | None = None
    replay_elapsed_seconds: float | None = None

    def close_reason_count(self, close_reason: str) -> int:
        normalized = str(close_reason or "").strip().upper()
        for reason, count in self.close_reasons:
            if reason == normalized:
                return count
        return 0


def build_workspace_historical_signal_metrics(
    records: tuple[WorkspaceSignalRecord, ...],
) -> WorkspaceHistoricalSignalMetrics:
    """Count signal outcomes in deterministic record order."""
    buy = 0
    sell = 0
    alligator_allow = 0
    alligator_reject = 0
    warmup_rejects = 0
    risk_rejects = 0
    macd_quality_accept = 0
    macd_extremum_not_found = 0
    macd_extremum_too_weak = 0
    macd_distance_too_small = 0
    macd_cross_too_flat = 0

    for record in records:
        if record.direction == "BUY":
            buy += 1
        elif record.direction == "SELL":
            sell += 1

        alligator_active = (
            record.alligator_confirmation
            != WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
        )
        if alligator_active:
            if record.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW:
                alligator_allow += 1
            elif record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT:
                alligator_reject += 1

        if (
            record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
            and "WARMUP" in record.alligator_confirmation
        ):
            warmup_rejects += 1
        if record.risk_decision == RISK_DECISION_BLOCK:
            risk_rejects += 1

        source_reason = str(record.source_reason_code or "").strip().upper()
        if source_reason == MACD_QUALITY_REASON_ACCEPTED:
            macd_quality_accept += 1
        elif source_reason == MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND:
            macd_extremum_not_found += 1
        elif source_reason == MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK:
            macd_extremum_too_weak += 1
        elif source_reason == MACD_QUALITY_REASON_DISTANCE_TOO_SMALL:
            macd_distance_too_small += 1
        elif source_reason == MACD_QUALITY_REASON_CROSS_TOO_FLAT:
            macd_cross_too_flat += 1

    macd_quality_reject = (
        macd_extremum_not_found
        + macd_extremum_too_weak
        + macd_distance_too_small
        + macd_cross_too_flat
    )
    return WorkspaceHistoricalSignalMetrics(
        total=len(records),
        buy=buy,
        sell=sell,
        alligator_allow=alligator_allow,
        alligator_reject=alligator_reject,
        warmup_rejects=warmup_rejects,
        risk_rejects=risk_rejects,
        macd_quality_accept=macd_quality_accept,
        macd_quality_reject=macd_quality_reject,
        macd_extremum_not_found=macd_extremum_not_found,
        macd_extremum_too_weak=macd_extremum_too_weak,
        macd_distance_too_small=macd_distance_too_small,
        macd_cross_too_flat=macd_cross_too_flat,
    )


def build_workspace_historical_replay_summary(
    *,
    symbol: str,
    timeframe: str,
    period_start: datetime,
    period_end: datetime,
    accepted_bars: int,
    skipped_bars: int,
    gaps: int,
    spread: float,
    initial_balance: float,
    signals: WorkspaceHistoricalSignalMetrics,
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    source_timeframe: str | None = None,
    csv_selection_elapsed_seconds: float | None = None,
    replay_elapsed_seconds: float | None = None,
) -> WorkspaceHistoricalReplaySummary:
    """Build one immutable completed-run summary from factual Replay data."""
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_timeframe = str(timeframe or "").strip().upper()
    normalized_source_timeframe = (
        str(source_timeframe or normalized_timeframe).strip().upper()
    )
    if not normalized_symbol:
        raise ValueError("symbol is required")
    if not normalized_timeframe:
        raise ValueError("timeframe is required")
    if not normalized_source_timeframe:
        raise ValueError("source_timeframe is required")

    normalized_start = normalize_market_timestamp(period_start)
    normalized_end = normalize_market_timestamp(period_end)
    if normalized_end < normalized_start:
        raise ValueError("period_end cannot be before period_start")

    accepted = _non_negative_int(accepted_bars, "accepted_bars")
    skipped = _non_negative_int(skipped_bars, "skipped_bars")
    gap_count = _non_negative_int(gaps, "gaps")
    normalized_spread = _non_negative_float(spread, "spread")
    starting_balance = _positive_float(initial_balance, "initial_balance")
    selection_elapsed = _optional_non_negative_float(
        csv_selection_elapsed_seconds,
        "csv_selection_elapsed_seconds",
    )
    replay_elapsed = _optional_non_negative_float(
        replay_elapsed_seconds,
        "replay_elapsed_seconds",
    )

    closed_trades = tuple(
        WorkspaceHistoricalClosedTrade(
            trade_uid=trade.position_id,
            realized_profit=trade.final_profit,
            close_reason=trade.close_reason,
        )
        for trade in trades
    )
    baseline = build_workspace_historical_baseline_metrics(closed_trades)
    profits = tuple(trade.final_profit for trade in trades)
    winning = tuple(value for value in profits if value > 1e-12)
    losing = tuple(value for value in profits if value < -1e-12)

    peak_balance = starting_balance
    minimum_balance = starting_balance
    current_balance = starting_balance
    maximum_drawdown = 0.0
    maximum_drawdown_percent = 0.0
    consecutive_wins = 0
    consecutive_losses = 0
    maximum_consecutive_wins = 0
    maximum_consecutive_losses = 0

    for profit in profits:
        current_balance += profit
        if current_balance > peak_balance:
            peak_balance = current_balance
        minimum_balance = min(minimum_balance, current_balance)
        drawdown = peak_balance - current_balance
        maximum_drawdown = max(maximum_drawdown, drawdown)
        if peak_balance > 0.0:
            maximum_drawdown_percent = max(
                maximum_drawdown_percent,
                drawdown / peak_balance * 100.0,
            )

        if profit > 1e-12:
            consecutive_wins += 1
            consecutive_losses = 0
            maximum_consecutive_wins = max(
                maximum_consecutive_wins,
                consecutive_wins,
            )
        elif profit < -1e-12:
            consecutive_losses += 1
            consecutive_wins = 0
            maximum_consecutive_losses = max(
                maximum_consecutive_losses,
                consecutive_losses,
            )
        else:
            consecutive_wins = 0
            consecutive_losses = 0

    close_reasons = tuple(
        (item.close_reason, item.trades) for item in baseline.close_reasons
    )
    return WorkspaceHistoricalReplaySummary(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        period_start=normalized_start,
        period_end=normalized_end,
        accepted_bars=accepted,
        skipped_bars=skipped,
        gaps=gap_count,
        spread=normalized_spread,
        initial_balance=starting_balance,
        final_balance=starting_balance + baseline.net_profit,
        signals=signals,
        opened_trades=baseline.trades,
        winning_trades=baseline.winning_trades,
        losing_trades=baseline.losing_trades,
        break_even_trades=baseline.break_even_trades,
        win_rate_percent=baseline.win_rate_percent,
        gross_profit=baseline.gross_profit,
        gross_loss=baseline.gross_loss,
        net_profit=baseline.net_profit,
        average_trade=baseline.average_trade,
        average_winner=(math.fsum(winning) / len(winning) if winning else 0.0),
        average_loser=(math.fsum(losing) / len(losing) if losing else 0.0),
        maximum_winner=max(winning, default=0.0),
        maximum_loser=min(losing, default=0.0),
        profit_factor=baseline.profit_factor,
        maximum_drawdown=maximum_drawdown,
        maximum_drawdown_percent=maximum_drawdown_percent,
        maximum_consecutive_losses=maximum_consecutive_losses,
        maximum_consecutive_wins=maximum_consecutive_wins,
        peak_balance=peak_balance,
        minimum_balance=minimum_balance,
        close_reasons=close_reasons,
        source_timeframe=normalized_source_timeframe,
        csv_selection_elapsed_seconds=selection_elapsed,
        replay_elapsed_seconds=replay_elapsed,
    )


def _optional_non_negative_float(
    value: float | None,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _non_negative_float(value, field_name)


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        number = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return number


def _non_negative_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} cannot be negative")
    return number


def _positive_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _finite_float(value: object, field_name: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number
