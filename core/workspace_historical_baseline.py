# -*- coding: utf-8 -*-
"""Deterministic baseline metrics for completed Historical Replay trades."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass


class WorkspaceHistoricalBaselineError(ValueError):
    """Invalid Historical Replay baseline trade sequence."""


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalClosedTrade:
    """Minimal immutable input required by baseline statistics."""

    trade_uid: str
    realized_profit: float
    close_reason: str

    def __post_init__(self) -> None:
        trade_uid = str(self.trade_uid or "").strip()
        close_reason = str(self.close_reason or "").strip().upper()
        try:
            realized_profit = float(self.realized_profit)
        except (TypeError, ValueError) as exc:
            raise WorkspaceHistoricalBaselineError(
                "realized_profit must be finite"
            ) from exc
        if not trade_uid:
            raise WorkspaceHistoricalBaselineError("trade_uid is required")
        if not math.isfinite(realized_profit):
            raise WorkspaceHistoricalBaselineError("realized_profit must be finite")
        if not close_reason:
            raise WorkspaceHistoricalBaselineError("close_reason is required")
        object.__setattr__(self, "trade_uid", trade_uid)
        object.__setattr__(self, "realized_profit", realized_profit)
        object.__setattr__(self, "close_reason", close_reason)


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalCloseReasonCount:
    """Deterministic count for one normalized close reason."""

    close_reason: str
    trades: int


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalBaselineMetrics:
    """Canonical first-stage statistics for one completed Replay run."""

    trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    win_rate_percent: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    average_trade: float
    profit_factor: float | None
    maximum_drawdown: float
    close_reasons: tuple[WorkspaceHistoricalCloseReasonCount, ...]

    def close_reason_count(self, close_reason: str) -> int:
        normalized = str(close_reason or "").strip().upper()
        for item in self.close_reasons:
            if item.close_reason == normalized:
                return item.trades
        return 0


def build_workspace_historical_baseline_metrics(
    trades: tuple[WorkspaceHistoricalClosedTrade, ...],
) -> WorkspaceHistoricalBaselineMetrics:
    """Build deterministic metrics in the supplied trade-close order."""
    trade_uids = tuple(trade.trade_uid for trade in trades)
    if len(set(trade_uids)) != len(trade_uids):
        raise WorkspaceHistoricalBaselineError("duplicate trade_uid")

    tolerance = 1e-12
    winning_trades = sum(trade.realized_profit > tolerance for trade in trades)
    losing_trades = sum(trade.realized_profit < -tolerance for trade in trades)
    break_even_trades = len(trades) - winning_trades - losing_trades
    gross_profit = math.fsum(
        trade.realized_profit for trade in trades if trade.realized_profit > tolerance
    )
    gross_loss = math.fsum(
        trade.realized_profit for trade in trades if trade.realized_profit < -tolerance
    )
    net_profit = math.fsum(trade.realized_profit for trade in trades)
    trade_count = len(trades)
    win_rate_percent = winning_trades / trade_count * 100.0 if trade_count else 0.0
    average_trade = net_profit / trade_count if trade_count else 0.0
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < -tolerance else None
    close_reason_counts = Counter(trade.close_reason for trade in trades)
    close_reasons = tuple(
        WorkspaceHistoricalCloseReasonCount(
            close_reason=close_reason,
            trades=close_reason_counts[close_reason],
        )
        for close_reason in sorted(close_reason_counts)
    )
    return WorkspaceHistoricalBaselineMetrics(
        trades=trade_count,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        break_even_trades=break_even_trades,
        win_rate_percent=win_rate_percent,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        average_trade=average_trade,
        profit_factor=profit_factor,
        maximum_drawdown=_maximum_drawdown(trades),
        close_reasons=close_reasons,
    )


def _maximum_drawdown(
    trades: tuple[WorkspaceHistoricalClosedTrade, ...],
) -> float:
    cumulative_profit = 0.0
    peak_profit = 0.0
    maximum_drawdown = 0.0
    for trade in trades:
        cumulative_profit += trade.realized_profit
        peak_profit = max(peak_profit, cumulative_profit)
        maximum_drawdown = max(
            maximum_drawdown,
            peak_profit - cumulative_profit,
        )
    return maximum_drawdown
