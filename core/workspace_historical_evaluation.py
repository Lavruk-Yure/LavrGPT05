# -*- coding: utf-8 -*-
"""Deterministic hypothetical PnL for completed Historical Replay signals.

The evaluator is broker-neutral and does not create orders. Every allowed
signal is treated as an independent fixed-horizon hypothetical trade. The
model uses only already loaded Replay bars and an explicit immutable policy.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalRecord,
)


class WorkspaceHistoricalEvaluationError(ValueError):
    """Invalid historical evaluation policy, binding, or signal stream."""


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalEvaluationPolicy:
    """Explicit execution assumptions for hypothetical signal trades."""

    horizon_bars: int
    fixed_volume: float
    pnl_currency: str
    commission_per_trade: float = 0.0
    slippage_per_side: float = 0.0

    def __post_init__(self) -> None:
        try:
            horizon_bars = int(self.horizon_bars)
        except (TypeError, ValueError) as exc:
            raise WorkspaceHistoricalEvaluationError(
                "horizon_bars must be a positive integer"
            ) from exc
        fixed_volume = _positive_finite(self.fixed_volume, "fixed_volume")
        commission = _non_negative_finite(
            self.commission_per_trade,
            "commission_per_trade",
        )
        slippage = _non_negative_finite(
            self.slippage_per_side,
            "slippage_per_side",
        )
        pnl_currency = str(self.pnl_currency or "").strip().upper()
        if horizon_bars <= 0:
            raise WorkspaceHistoricalEvaluationError(
                "horizon_bars must be a positive integer"
            )
        if not pnl_currency:
            raise WorkspaceHistoricalEvaluationError(
                "pnl_currency is required"
            )
        object.__setattr__(self, "horizon_bars", horizon_bars)
        object.__setattr__(self, "fixed_volume", fixed_volume)
        object.__setattr__(self, "pnl_currency", pnl_currency)
        object.__setattr__(self, "commission_per_trade", commission)
        object.__setattr__(self, "slippage_per_side", slippage)


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalTradeResult:
    """One completed independent hypothetical trade."""

    signal_uid: str
    direction: str
    signal_timestamp: datetime
    entry_timestamp: datetime
    exit_timestamp: datetime
    volume: float
    entry_mid_price: float
    exit_mid_price: float
    entry_execution_price: float
    exit_execution_price: float
    gross_profit: float
    spread_cost: float
    commission_cost: float
    slippage_cost: float
    net_profit: float


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalVariantEvaluation:
    """Historical PnL summary for one mode/profile snapshot."""

    mode: str
    profile_uid: str
    profile_revision: int
    alligator_timeframe: str
    broker: str
    symbol: str
    base_timeframe: str
    source_mode: str
    pnl_currency: str
    signals: int
    allowed: int
    rejected: int
    evaluated_trades: int
    skipped_incomplete_horizon: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    gross_profit: float
    spread_cost: float
    commission_cost: float
    slippage_cost: float
    net_profit: float
    maximum_drawdown: float
    trades: tuple[WorkspaceHistoricalTradeResult, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalEvaluationReport:
    """Comparable Historical Replay PnL for unique Alligator variants."""

    policy: WorkspaceHistoricalEvaluationPolicy
    historical_bars: int
    variants: tuple[WorkspaceHistoricalVariantEvaluation, ...]
    proposal_signatures_identical: bool
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


def build_workspace_historical_variant_evaluation(
    records: tuple[WorkspaceSignalRecord, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    policy: WorkspaceHistoricalEvaluationPolicy,
) -> WorkspaceHistoricalVariantEvaluation:
    """Evaluate one complete mode/profile signal stream."""
    if not records:
        raise WorkspaceHistoricalEvaluationError("signal records are required")
    event_index = _validate_events(events)
    _validate_unique_signal_uids(records)
    first = records[0]
    context = _required_filter_context(first)
    variant_key = _variant_key(context)
    binding = _record_binding(first)
    if not first.symbol.endswith(policy.pnl_currency):
        raise WorkspaceHistoricalEvaluationError(
            "symbol quote currency does not match pnl_currency"
        )

    allowed = 0
    rejected = 0
    skipped = 0
    trades: list[WorkspaceHistoricalTradeResult] = []
    for record in records:
        record_context = _required_filter_context(record)
        if _variant_key(record_context) != variant_key:
            raise WorkspaceHistoricalEvaluationError(
                "signal records mix mode/profile variants"
            )
        if _record_binding(record) != binding:
            raise WorkspaceHistoricalEvaluationError(
                "signal record binding changed inside one variant"
            )
        index = event_index.get(record.timestamp)
        if index is None:
            raise WorkspaceHistoricalEvaluationError(
                "signal timestamp is absent from the event stream"
            )
        event = events[index]
        event_binding = (
            event.broker,
            event.symbol,
            event.timeframe,
            event.source_mode,
        )
        if event_binding != binding:
            raise WorkspaceHistoricalEvaluationError(
                "signal and market-event bindings do not match"
            )
        if (
            record_context.available_at is not None
            and record_context.available_at > record.timestamp
        ):
            raise WorkspaceHistoricalEvaluationError(
                "filter context uses future information"
            )
        if record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT:
            rejected += 1
            continue
        if record.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
            raise WorkspaceHistoricalEvaluationError(
                "unsupported filter decision in signal records"
            )
        allowed += 1
        trade = _build_trade(record, events, index, policy)
        if trade is None:
            skipped += 1
        else:
            trades.append(trade)

    tolerance = 1e-12
    winning = sum(trade.net_profit > tolerance for trade in trades)
    losing = sum(trade.net_profit < -tolerance for trade in trades)
    break_even = len(trades) - winning - losing
    return WorkspaceHistoricalVariantEvaluation(
        mode=context.mode,
        profile_uid=context.profile_uid,
        profile_revision=context.profile_revision,
        alligator_timeframe=context.timeframe,
        broker=first.broker,
        symbol=first.symbol,
        base_timeframe=first.timeframe,
        source_mode=first.source_mode,
        pnl_currency=policy.pnl_currency,
        signals=len(records),
        allowed=allowed,
        rejected=rejected,
        evaluated_trades=len(trades),
        skipped_incomplete_horizon=skipped,
        winning_trades=winning,
        losing_trades=losing,
        break_even_trades=break_even,
        gross_profit=sum(trade.gross_profit for trade in trades),
        spread_cost=sum(trade.spread_cost for trade in trades),
        commission_cost=sum(trade.commission_cost for trade in trades),
        slippage_cost=sum(trade.slippage_cost for trade in trades),
        net_profit=sum(trade.net_profit for trade in trades),
        maximum_drawdown=_maximum_drawdown(tuple(trades)),
        trades=tuple(trades),
    )


def build_workspace_historical_evaluation(
    variants: tuple[tuple[WorkspaceSignalRecord, ...], ...],
    events: tuple[WorkspaceMarketEvent, ...],
    policy: WorkspaceHistoricalEvaluationPolicy,
) -> WorkspaceHistoricalEvaluationReport:
    """Compare complete mode/profile streams on one historical event set."""
    if not variants:
        raise WorkspaceHistoricalEvaluationError(
            "historical evaluation variants are required"
        )
    summaries: list[WorkspaceHistoricalVariantEvaluation] = []
    keys: set[tuple[str, str, int, str]] = set()
    signatures: tuple[tuple[object, ...], ...] | None = None
    for records in variants:
        summary = build_workspace_historical_variant_evaluation(
            records,
            events,
            policy,
        )
        key = (
            summary.mode,
            summary.profile_uid,
            summary.profile_revision,
            summary.alligator_timeframe,
        )
        if key in keys:
            raise WorkspaceHistoricalEvaluationError(
                "duplicate mode/profile evaluation variant"
            )
        keys.add(key)
        current_signatures = _proposal_signatures(records)
        if signatures is None:
            signatures = current_signatures
        elif current_signatures != signatures:
            raise WorkspaceHistoricalEvaluationError(
                "evaluation variants do not contain identical proposals"
            )
        summaries.append(summary)
    return WorkspaceHistoricalEvaluationReport(
        policy=policy,
        historical_bars=len(events),
        variants=tuple(summaries),
        proposal_signatures_identical=True,
    )


def _build_trade(
    record: WorkspaceSignalRecord,
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    policy: WorkspaceHistoricalEvaluationPolicy,
) -> WorkspaceHistoricalTradeResult | None:
    entry_index = signal_index + 1
    exit_index = signal_index + policy.horizon_bars
    if entry_index >= len(events) or exit_index >= len(events):
        return None
    entry_event = events[entry_index]
    exit_event = events[exit_index]
    entry_mid = float(entry_event.open)
    exit_mid = float(exit_event.close)
    entry_half_spread = float(entry_event.spread) / 2.0
    exit_half_spread = float(exit_event.spread) / 2.0
    slippage = policy.slippage_per_side
    volume = policy.fixed_volume

    if record.direction == "BUY":
        entry_execution = entry_mid + entry_half_spread + slippage
        exit_execution = exit_mid - exit_half_spread - slippage
        gross_profit = (exit_mid - entry_mid) * volume
        execution_profit = (exit_execution - entry_execution) * volume
    elif record.direction == "SELL":
        entry_execution = entry_mid - entry_half_spread - slippage
        exit_execution = exit_mid + exit_half_spread + slippage
        gross_profit = (entry_mid - exit_mid) * volume
        execution_profit = (entry_execution - exit_execution) * volume
    else:
        raise WorkspaceHistoricalEvaluationError(
            f"unsupported signal direction: {record.direction}"
        )

    spread_cost = (entry_half_spread + exit_half_spread) * volume
    slippage_cost = 2.0 * slippage * volume
    commission_cost = policy.commission_per_trade
    net_profit = execution_profit - commission_cost
    expected_net = (
        gross_profit
        - spread_cost
        - slippage_cost
        - commission_cost
    )
    if not math.isclose(net_profit, expected_net, rel_tol=0.0, abs_tol=1e-9):
        raise WorkspaceHistoricalEvaluationError(
            "hypothetical execution cost decomposition is inconsistent"
        )
    return WorkspaceHistoricalTradeResult(
        signal_uid=record.signal_uid,
        direction=record.direction,
        signal_timestamp=record.timestamp,
        entry_timestamp=entry_event.timestamp,
        exit_timestamp=exit_event.timestamp,
        volume=volume,
        entry_mid_price=entry_mid,
        exit_mid_price=exit_mid,
        entry_execution_price=entry_execution,
        exit_execution_price=exit_execution,
        gross_profit=gross_profit,
        spread_cost=spread_cost,
        commission_cost=commission_cost,
        slippage_cost=slippage_cost,
        net_profit=net_profit,
    )


def _maximum_drawdown(
    trades: tuple[WorkspaceHistoricalTradeResult, ...],
) -> float:
    pnl_by_exit: dict[datetime, float] = defaultdict(float)
    for trade in trades:
        pnl_by_exit[trade.exit_timestamp] += trade.net_profit
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for exit_timestamp in sorted(pnl_by_exit):
        cumulative += pnl_by_exit[exit_timestamp]
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def _validate_events(
    events: tuple[WorkspaceMarketEvent, ...],
) -> dict[datetime, int]:
    if not events:
        raise WorkspaceHistoricalEvaluationError("market events are required")
    result: dict[datetime, int] = {}
    binding: tuple[str, str, str, str] | None = None
    previous_timestamp: datetime | None = None
    for index, event in enumerate(events):
        if previous_timestamp is not None and event.timestamp <= previous_timestamp:
            raise WorkspaceHistoricalEvaluationError(
                "market events must be strictly ordered and unique"
            )
        current_binding = (
            event.broker,
            event.symbol,
            event.timeframe,
            event.source_mode,
        )
        if binding is None:
            binding = current_binding
        elif current_binding != binding:
            raise WorkspaceHistoricalEvaluationError(
                "market-event binding changed inside evaluation stream"
            )
        result[event.timestamp] = index
        previous_timestamp = event.timestamp
    return result


def _validate_unique_signal_uids(
    records: tuple[WorkspaceSignalRecord, ...],
) -> None:
    signal_uids = tuple(record.signal_uid for record in records)
    if len(set(signal_uids)) != len(signal_uids):
        raise WorkspaceHistoricalEvaluationError("duplicate signal_uid")


def _required_filter_context(
    record: WorkspaceSignalRecord,
) -> WorkspaceSignalFilterContext:
    context = record.filter_context
    if context is None:
        raise WorkspaceHistoricalEvaluationError(
            "structured filter context is required for evaluation"
        )
    return context


def _variant_key(
    context: WorkspaceSignalFilterContext,
) -> tuple[str, str, int, str]:
    return (
        context.mode,
        context.profile_uid,
        context.profile_revision,
        context.timeframe,
    )


def _record_binding(
    record: WorkspaceSignalRecord,
) -> tuple[str, str, str, str]:
    return (
        record.broker,
        record.symbol,
        record.timeframe,
        record.source_mode,
    )


def _proposal_signatures(
    records: tuple[WorkspaceSignalRecord, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            record.timestamp,
            record.signal_type,
            record.direction,
            record.macd_state,
            record.strength,
        )
        for record in records
    )


def _positive_finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise WorkspaceHistoricalEvaluationError(
            f"{field_name} must be positive and finite"
        )
    return number


def _non_negative_finite(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise WorkspaceHistoricalEvaluationError(
            f"{field_name} must be non-negative and finite"
        )
    return number
