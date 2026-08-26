# -*- coding: utf-8 -*-
"""Deterministic comparison of broker M15 and M1-derived M15 histories."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from core.workspace_macd import (
    MACD_STATE_CROSS_DOWN,
    MACD_STATE_CROSS_UP,
    WorkspaceMacdObservation,
)
from core.workspace_market_event import WorkspaceMarketEvent


@dataclass(frozen=True, slots=True)
class WorkspaceFieldDifference:
    """Difference statistics for one OHLC field."""

    field_name: str
    differing_bars: int
    average_absolute_difference: float
    maximum_absolute_difference: float
    maximum_difference_timestamp: datetime | None


@dataclass(frozen=True, slots=True)
class WorkspaceSignalSignature:
    """Minimal deterministic MACD crossover identity."""

    timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalSourceComparison:
    """Canonical broker-M15 versus M1-derived-M15 comparison report."""

    broker_bars: int
    derived_bars: int
    common_timestamps: int
    broker_only_timestamps: tuple[datetime, ...]
    derived_only_timestamps: tuple[datetime, ...]
    exact_ohlc_bars: int
    differing_ohlc_bars: int
    open_difference: WorkspaceFieldDifference
    high_difference: WorkspaceFieldDifference
    low_difference: WorkspaceFieldDifference
    close_difference: WorkspaceFieldDifference
    first_ohlc_difference: datetime | None
    broker_signals: int
    derived_signals: int
    common_signals: int
    broker_only_signals: tuple[WorkspaceSignalSignature, ...]
    derived_only_signals: tuple[WorkspaceSignalSignature, ...]
    direction_changed_timestamps: tuple[datetime, ...]
    first_signal_difference: datetime | None
    signal_differences_without_prior_close_difference: int


def build_workspace_historical_source_comparison(
    broker_events: tuple[WorkspaceMarketEvent, ...],
    derived_events: tuple[WorkspaceMarketEvent, ...],
    broker_observations: tuple[WorkspaceMacdObservation, ...],
    derived_observations: tuple[WorkspaceMacdObservation, ...],
) -> WorkspaceHistoricalSourceComparison:
    """Compare strategy bars and MACD crossovers without changing logic."""
    broker_by_time = {event.timestamp: event for event in broker_events}
    derived_by_time = {event.timestamp: event for event in derived_events}
    broker_times = set(broker_by_time)
    derived_times = set(derived_by_time)
    common_times = tuple(sorted(broker_times & derived_times))

    field_reports = {
        field_name: _field_difference(
            field_name,
            common_times,
            broker_by_time,
            derived_by_time,
        )
        for field_name in ("open", "high", "low", "close")
    }
    differing_ohlc_times = tuple(
        timestamp
        for timestamp in common_times
        if any(
            getattr(broker_by_time[timestamp], field_name)
            != getattr(derived_by_time[timestamp], field_name)
            for field_name in ("open", "high", "low", "close")
        )
    )

    broker_signals = _signal_map(broker_observations)
    derived_signals = _signal_map(derived_observations)
    common_signal_times = set(broker_signals) & set(derived_signals)
    direction_changed = tuple(
        sorted(
            timestamp
            for timestamp in common_signal_times
            if broker_signals[timestamp] != derived_signals[timestamp]
        )
    )
    common_same_direction = sum(
        broker_signals[timestamp] == derived_signals[timestamp]
        for timestamp in common_signal_times
    )
    broker_only = tuple(
        WorkspaceSignalSignature(timestamp, broker_signals[timestamp])
        for timestamp in sorted(set(broker_signals) - set(derived_signals))
    )
    derived_only = tuple(
        WorkspaceSignalSignature(timestamp, derived_signals[timestamp])
        for timestamp in sorted(set(derived_signals) - set(broker_signals))
    )
    signal_difference_times = tuple(
        sorted(
            {item.timestamp for item in broker_only}
            | {item.timestamp for item in derived_only}
            | set(direction_changed)
        )
    )
    close_difference_times = tuple(
        timestamp
        for timestamp in common_times
        if broker_by_time[timestamp].close != derived_by_time[timestamp].close
    )
    signal_differences_without_prior_close_difference = sum(
        not any(close_time <= signal_time for close_time in close_difference_times)
        for signal_time in signal_difference_times
    )

    return WorkspaceHistoricalSourceComparison(
        broker_bars=len(broker_events),
        derived_bars=len(derived_events),
        common_timestamps=len(common_times),
        broker_only_timestamps=tuple(sorted(broker_times - derived_times)),
        derived_only_timestamps=tuple(sorted(derived_times - broker_times)),
        exact_ohlc_bars=len(common_times) - len(differing_ohlc_times),
        differing_ohlc_bars=len(differing_ohlc_times),
        open_difference=field_reports["open"],
        high_difference=field_reports["high"],
        low_difference=field_reports["low"],
        close_difference=field_reports["close"],
        first_ohlc_difference=(
            differing_ohlc_times[0] if differing_ohlc_times else None
        ),
        broker_signals=len(broker_signals),
        derived_signals=len(derived_signals),
        common_signals=common_same_direction,
        broker_only_signals=broker_only,
        derived_only_signals=derived_only,
        direction_changed_timestamps=direction_changed,
        first_signal_difference=(
            signal_difference_times[0] if signal_difference_times else None
        ),
        signal_differences_without_prior_close_difference=(
            signal_differences_without_prior_close_difference
        ),
    )


def _field_difference(
    field_name: str,
    timestamps: tuple[datetime, ...],
    broker_by_time: dict[datetime, WorkspaceMarketEvent],
    derived_by_time: dict[datetime, WorkspaceMarketEvent],
) -> WorkspaceFieldDifference:
    differences = tuple(
        (
            timestamp,
            abs(
                float(getattr(broker_by_time[timestamp], field_name))
                - float(getattr(derived_by_time[timestamp], field_name))
            ),
        )
        for timestamp in timestamps
    )
    non_zero = tuple(item for item in differences if item[1] != 0.0)
    if not non_zero:
        return WorkspaceFieldDifference(field_name, 0, 0.0, 0.0, None)
    maximum_timestamp, maximum_difference = max(
        non_zero,
        key=lambda item: (item[1], item[0]),
    )
    return WorkspaceFieldDifference(
        field_name=field_name,
        differing_bars=len(non_zero),
        average_absolute_difference=statistics.fmean(
            difference for _, difference in non_zero
        ),
        maximum_absolute_difference=maximum_difference,
        maximum_difference_timestamp=maximum_timestamp,
    )


def _signal_map(
    observations: tuple[WorkspaceMacdObservation, ...],
) -> dict[datetime, str]:
    result: dict[datetime, str] = {}
    for observation in observations:
        if observation.state == MACD_STATE_CROSS_UP:
            result[observation.timestamp] = "BUY"
        elif observation.state == MACD_STATE_CROSS_DOWN:
            result[observation.timestamp] = "SELL"
    return result
