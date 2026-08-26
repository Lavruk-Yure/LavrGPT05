# -*- coding: utf-8 -*-
"""Deterministic comparative statistics for WSP Replay signals.

The module evaluates already recorded signal proposals. It does not select a
"best" mode and never performs broker requests or execution. Signal quality is
measured only against an explicit, immutable forward-horizon policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalRecord,
)


class WorkspaceSignalStatisticsError(ValueError):
    """Invalid comparison input, binding, policy, or duplicate data."""


@dataclass(frozen=True, slots=True)
class WorkspaceSignalQualityPolicy:
    """Explicit causal policy used to evaluate directional signal outcomes."""

    horizon_bars: int
    minimum_directional_move: float

    def __post_init__(self) -> None:
        try:
            horizon_bars = int(self.horizon_bars)
        except (TypeError, ValueError) as exc:
            raise WorkspaceSignalStatisticsError(
                "horizon_bars must be a positive integer"
            ) from exc
        try:
            minimum_move = float(self.minimum_directional_move)
        except (TypeError, ValueError) as exc:
            raise WorkspaceSignalStatisticsError(
                "minimum_directional_move must be positive and finite"
            ) from exc
        if horizon_bars <= 0:
            raise WorkspaceSignalStatisticsError(
                "horizon_bars must be a positive integer"
            )
        if not math.isfinite(minimum_move) or minimum_move <= 0.0:
            raise WorkspaceSignalStatisticsError(
                "minimum_directional_move must be positive and finite"
            )
        object.__setattr__(self, "horizon_bars", horizon_bars)
        object.__setattr__(
            self,
            "minimum_directional_move",
            minimum_move,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceSignalVariantStatistics:
    """Statistics for one Alligator mode/profile snapshot."""

    mode: str
    profile_uid: str
    profile_revision: int
    alligator_timeframe: str
    broker: str
    symbol: str
    base_timeframe: str
    source_mode: str
    signals: int
    allowed: int
    rejected: int
    evaluated_signals: int
    outcome_wins: int
    outcome_losses: int
    outcome_unknown: int
    allowed_evaluated: int
    allowed_wins: int
    allowed_losses: int
    allowed_unknown: int
    rejected_evaluated: int
    rejected_wins: int
    rejected_losses: int
    rejected_unknown: int
    missed_signals: int
    confirmation_delay_samples: int
    confirmation_delay_min_seconds: float | None
    confirmation_delay_average_seconds: float | None
    confirmation_delay_max_seconds: float | None

    @property
    def allow_rate(self) -> float | None:
        return _safe_ratio(self.allowed, self.signals)

    @property
    def quality_before_filter(self) -> float | None:
        return _safe_ratio(self.outcome_wins, self.evaluated_signals)

    @property
    def quality_after_filter(self) -> float | None:
        return _safe_ratio(self.allowed_wins, self.allowed_evaluated)


@dataclass(frozen=True, slots=True)
class WorkspaceSignalComparisonReport:
    """Comparable statistics for unique mode/profile variants."""

    policy: WorkspaceSignalQualityPolicy
    variants: tuple[WorkspaceSignalVariantStatistics, ...]
    proposal_signatures_identical: bool
    deterministic: bool = True
    broker_requests: int = 0
    broker_execution_attempted: bool = False


@dataclass(frozen=True, slots=True)
class _OutcomeCounts:
    evaluated: int
    wins: int
    losses: int
    unknown: int


def build_workspace_signal_variant_statistics(
    records: tuple[WorkspaceSignalRecord, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    policy: WorkspaceSignalQualityPolicy,
) -> WorkspaceSignalVariantStatistics:
    """Build deterministic metrics for one Replay mode/profile snapshot."""
    if not records:
        raise WorkspaceSignalStatisticsError("signal records are required")
    event_index = _validate_events(events)
    _validate_unique_signal_uids(records)
    first = records[0]
    variant_context = _required_filter_context(first)
    binding = (
        first.broker,
        first.symbol,
        first.timeframe,
        first.source_mode,
    )
    variant_key = _variant_key(variant_context)

    allowed_records: list[WorkspaceSignalRecord] = []
    rejected_records: list[WorkspaceSignalRecord] = []
    delays: list[float] = []
    outcomes: dict[str, bool | None] = {}

    for record in records:
        context = _required_filter_context(record)
        if _variant_key(context) != variant_key:
            raise WorkspaceSignalStatisticsError(
                "signal records mix mode/profile variants"
            )
        record_binding = (
            record.broker,
            record.symbol,
            record.timeframe,
            record.source_mode,
        )
        if record_binding != binding:
            raise WorkspaceSignalStatisticsError(
                "signal record binding changed inside one variant"
            )
        index = event_index.get(record.timestamp)
        if index is None:
            raise WorkspaceSignalStatisticsError(
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
            raise WorkspaceSignalStatisticsError(
                "signal and market-event bindings do not match"
            )
        if context.available_at is not None:
            if context.available_at > record.timestamp:
                raise WorkspaceSignalStatisticsError(
                    "filter context uses future information"
                )
            assert context.observation_timestamp is not None
            delays.append(
                (context.available_at - context.observation_timestamp)
                .total_seconds()
            )
        outcomes[record.signal_uid] = _directional_outcome(
            record,
            events,
            index,
            policy,
        )
        if record.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW:
            allowed_records.append(record)
        elif record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT:
            rejected_records.append(record)
        else:
            raise WorkspaceSignalStatisticsError(
                "unsupported filter decision in signal records"
            )

    all_counts = _count_outcomes(records, outcomes)
    allowed_counts = _count_outcomes(tuple(allowed_records), outcomes)
    rejected_counts = _count_outcomes(tuple(rejected_records), outcomes)
    delay_min = min(delays) if delays else None
    delay_average = fmean(delays) if delays else None
    delay_max = max(delays) if delays else None
    return WorkspaceSignalVariantStatistics(
        mode=variant_context.mode,
        profile_uid=variant_context.profile_uid,
        profile_revision=variant_context.profile_revision,
        alligator_timeframe=variant_context.timeframe,
        broker=first.broker,
        symbol=first.symbol,
        base_timeframe=first.timeframe,
        source_mode=first.source_mode,
        signals=len(records),
        allowed=len(allowed_records),
        rejected=len(rejected_records),
        evaluated_signals=all_counts.evaluated,
        outcome_wins=all_counts.wins,
        outcome_losses=all_counts.losses,
        outcome_unknown=all_counts.unknown,
        allowed_evaluated=allowed_counts.evaluated,
        allowed_wins=allowed_counts.wins,
        allowed_losses=allowed_counts.losses,
        allowed_unknown=allowed_counts.unknown,
        rejected_evaluated=rejected_counts.evaluated,
        rejected_wins=rejected_counts.wins,
        rejected_losses=rejected_counts.losses,
        rejected_unknown=rejected_counts.unknown,
        missed_signals=rejected_counts.wins,
        confirmation_delay_samples=len(delays),
        confirmation_delay_min_seconds=delay_min,
        confirmation_delay_average_seconds=delay_average,
        confirmation_delay_max_seconds=delay_max,
    )


def build_workspace_signal_comparison(
    variants: tuple[tuple[WorkspaceSignalRecord, ...], ...],
    events: tuple[WorkspaceMarketEvent, ...],
    policy: WorkspaceSignalQualityPolicy,
) -> WorkspaceSignalComparisonReport:
    """Compare unique mode/profile snapshots on one identical event stream."""
    if not variants:
        raise WorkspaceSignalStatisticsError("comparison variants are required")
    summaries: list[WorkspaceSignalVariantStatistics] = []
    keys: set[tuple[str, str, int, str]] = set()
    signatures: tuple[tuple[object, ...], ...] | None = None
    for records in variants:
        summary = build_workspace_signal_variant_statistics(
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
            raise WorkspaceSignalStatisticsError(
                "duplicate mode/profile comparison variant"
            )
        keys.add(key)
        current_signatures = _proposal_signatures(records)
        if signatures is None:
            signatures = current_signatures
        elif current_signatures != signatures:
            raise WorkspaceSignalStatisticsError(
                "comparison variants do not contain identical proposals"
            )
        summaries.append(summary)
    return WorkspaceSignalComparisonReport(
        policy=policy,
        variants=tuple(summaries),
        proposal_signatures_identical=True,
    )


def _validate_events(
    events: tuple[WorkspaceMarketEvent, ...],
) -> dict[object, int]:
    if not events:
        raise WorkspaceSignalStatisticsError("market events are required")
    result: dict[object, int] = {}
    binding: tuple[str, str, str, str] | None = None
    previous_timestamp = None
    for index, event in enumerate(events):
        if previous_timestamp is not None and event.timestamp <= previous_timestamp:
            raise WorkspaceSignalStatisticsError(
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
            raise WorkspaceSignalStatisticsError(
                "market-event binding changed inside comparison stream"
            )
        result[event.timestamp] = index
        previous_timestamp = event.timestamp
    return result


def _validate_unique_signal_uids(
    records: tuple[WorkspaceSignalRecord, ...],
) -> None:
    signal_uids = tuple(record.signal_uid for record in records)
    if len(set(signal_uids)) != len(signal_uids):
        raise WorkspaceSignalStatisticsError("duplicate signal_uid")


def _required_filter_context(
    record: WorkspaceSignalRecord,
) -> WorkspaceSignalFilterContext:
    context = record.filter_context
    if context is None:
        raise WorkspaceSignalStatisticsError(
            "structured filter context is required for statistics"
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


def _directional_outcome(
    record: WorkspaceSignalRecord,
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    policy: WorkspaceSignalQualityPolicy,
) -> bool | None:
    future_index = index + policy.horizon_bars
    if future_index >= len(events):
        return None
    start_close = float(events[index].close)
    future_close = float(events[future_index].close)
    if record.direction == "BUY":
        directional_move = future_close - start_close
    elif record.direction == "SELL":
        directional_move = start_close - future_close
    else:
        raise WorkspaceSignalStatisticsError(
            f"unsupported signal direction: {record.direction}"
        )
    return directional_move >= policy.minimum_directional_move


def _count_outcomes(
    records: tuple[WorkspaceSignalRecord, ...],
    outcomes: dict[str, bool | None],
) -> _OutcomeCounts:
    wins = 0
    losses = 0
    unknown = 0
    for record in records:
        outcome = outcomes[record.signal_uid]
        if outcome is None:
            unknown += 1
        elif outcome:
            wins += 1
        else:
            losses += 1
    return _OutcomeCounts(
        evaluated=wins + losses,
        wins=wins,
        losses=losses,
        unknown=unknown,
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


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
