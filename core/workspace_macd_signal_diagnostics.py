# -*- coding: utf-8 -*-
"""Deterministic diagnostics for Historical Replay MACD crossover signals."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime

from core.workspace_macd import (
    MACD_STATE_CROSS_DOWN,
    MACD_STATE_CROSS_UP,
    WorkspaceMacdObservation,
)

MACD_STRENGTH_TINY = 0.000001
MACD_STRENGTH_VERY_WEAK = 0.000005
MACD_STRENGTH_WEAK = 0.000010

MACD_ZERO_SIDE_BUY_BELOW = "BUY_BELOW_ZERO"
MACD_ZERO_SIDE_BUY_AT_OR_ABOVE = "BUY_AT_OR_ABOVE_ZERO"
MACD_ZERO_SIDE_SELL_ABOVE = "SELL_ABOVE_ZERO"
MACD_ZERO_SIDE_SELL_AT_OR_BELOW = "SELL_AT_OR_BELOW_ZERO"


@dataclass(frozen=True, slots=True)
class WorkspaceMacdSignalDiagnostic:
    """One factual MACD crossover snapshot without trading interpretation."""

    timestamp: datetime
    direction: str
    macd_value: float
    signal_value: float
    histogram: float
    strength: float
    zero_side: str
    bars_until_opposite_cross: int | None


@dataclass(frozen=True, slots=True)
class WorkspaceMacdSignalDiagnosticsReport:
    """Canonical aggregate diagnostics for one MACD Historical Replay run."""

    total_signals: int
    buy_signals: int
    sell_signals: int
    buy_below_zero: int
    buy_at_or_above_zero: int
    sell_above_zero: int
    sell_at_or_below_zero: int
    opposite_zero_side_signals: int
    directional_zero_side_signals: int
    strength_lt_1e6: int
    strength_lt_5e6: int
    strength_lt_1e5: int
    strength_ge_1e5: int
    reversal_within_1_bar: int
    reversal_within_2_bars: int
    reversal_within_4_bars: int
    reversal_within_8_bars: int
    minimum_strength: float
    median_strength: float
    average_strength: float
    maximum_strength: float
    weakest_signals: tuple[WorkspaceMacdSignalDiagnostic, ...]
    signals: tuple[WorkspaceMacdSignalDiagnostic, ...]


def build_workspace_macd_signal_diagnostics(
    observations: tuple[WorkspaceMacdObservation, ...],
    *,
    weakest_limit: int = 10,
) -> WorkspaceMacdSignalDiagnosticsReport:
    """Classify MACD crossovers without changing signal or execution logic."""
    if weakest_limit <= 0:
        raise ValueError("weakest_limit must be positive")

    observation_indexes = {
        observation.timestamp: index
        for index, observation in enumerate(observations)
    }
    cross_observations = tuple(
        observation
        for observation in observations
        if observation.state in {
            MACD_STATE_CROSS_UP,
            MACD_STATE_CROSS_DOWN,
        }
    )

    diagnostics: list[WorkspaceMacdSignalDiagnostic] = []
    for index, observation in enumerate(cross_observations):
        direction = (
            "BUY"
            if observation.state == MACD_STATE_CROSS_UP
            else "SELL"
        )
        macd_value = _required_value(observation.macd_value, "macd_value")
        signal_value = _required_value(
            observation.signal_value,
            "signal_value",
        )
        histogram = _required_value(observation.histogram, "histogram")
        next_opposite = _next_opposite_cross(
            cross_observations,
            index,
            direction,
        )
        bars_until_opposite_cross = None
        if next_opposite is not None:
            current_bar = observation_indexes[observation.timestamp]
            next_bar = observation_indexes[next_opposite.timestamp]
            bars_until_opposite_cross = next_bar - current_bar
        diagnostics.append(
            WorkspaceMacdSignalDiagnostic(
                timestamp=observation.timestamp,
                direction=direction,
                macd_value=macd_value,
                signal_value=signal_value,
                histogram=histogram,
                strength=abs(histogram),
                zero_side=_zero_side(direction, macd_value),
                bars_until_opposite_cross=bars_until_opposite_cross,
            )
        )

    signals = tuple(diagnostics)
    strengths = tuple(item.strength for item in signals)
    zero_sides = tuple(item.zero_side for item in signals)
    buy_below_zero = zero_sides.count(MACD_ZERO_SIDE_BUY_BELOW)
    buy_at_or_above_zero = zero_sides.count(
        MACD_ZERO_SIDE_BUY_AT_OR_ABOVE
    )
    sell_above_zero = zero_sides.count(MACD_ZERO_SIDE_SELL_ABOVE)
    sell_at_or_below_zero = zero_sides.count(
        MACD_ZERO_SIDE_SELL_AT_OR_BELOW
    )
    opposite_zero_side_signals = buy_below_zero + sell_above_zero
    directional_zero_side_signals = (
        buy_at_or_above_zero + sell_at_or_below_zero
    )

    weakest_signals = tuple(
        sorted(
            signals,
            key=lambda item: (item.strength, item.timestamp),
        )[:weakest_limit]
    )

    return WorkspaceMacdSignalDiagnosticsReport(
        total_signals=len(signals),
        buy_signals=sum(item.direction == "BUY" for item in signals),
        sell_signals=sum(item.direction == "SELL" for item in signals),
        buy_below_zero=buy_below_zero,
        buy_at_or_above_zero=buy_at_or_above_zero,
        sell_above_zero=sell_above_zero,
        sell_at_or_below_zero=sell_at_or_below_zero,
        opposite_zero_side_signals=opposite_zero_side_signals,
        directional_zero_side_signals=directional_zero_side_signals,
        strength_lt_1e6=sum(
            value < MACD_STRENGTH_TINY for value in strengths
        ),
        strength_lt_5e6=sum(
            value < MACD_STRENGTH_VERY_WEAK for value in strengths
        ),
        strength_lt_1e5=sum(
            value < MACD_STRENGTH_WEAK for value in strengths
        ),
        strength_ge_1e5=sum(
            value >= MACD_STRENGTH_WEAK for value in strengths
        ),
        reversal_within_1_bar=_reversal_count(signals, 1),
        reversal_within_2_bars=_reversal_count(signals, 2),
        reversal_within_4_bars=_reversal_count(signals, 4),
        reversal_within_8_bars=_reversal_count(signals, 8),
        minimum_strength=min(strengths, default=0.0),
        median_strength=(statistics.median(strengths) if strengths else 0.0),
        average_strength=(statistics.fmean(strengths) if strengths else 0.0),
        maximum_strength=max(strengths, default=0.0),
        weakest_signals=weakest_signals,
        signals=signals,
    )


def _next_opposite_cross(
    observations: tuple[WorkspaceMacdObservation, ...],
    current_index: int,
    direction: str,
) -> WorkspaceMacdObservation | None:
    opposite_state = (
        MACD_STATE_CROSS_DOWN
        if direction == "BUY"
        else MACD_STATE_CROSS_UP
    )
    for observation in observations[current_index + 1 :]:
        if observation.state == opposite_state:
            return observation
    return None


def _zero_side(direction: str, macd_value: float) -> str:
    if direction == "BUY":
        if macd_value < 0.0:
            return MACD_ZERO_SIDE_BUY_BELOW
        return MACD_ZERO_SIDE_BUY_AT_OR_ABOVE
    if macd_value > 0.0:
        return MACD_ZERO_SIDE_SELL_ABOVE
    return MACD_ZERO_SIDE_SELL_AT_OR_BELOW


def _reversal_count(
    signals: tuple[WorkspaceMacdSignalDiagnostic, ...],
    maximum_bars: int,
) -> int:
    return sum(
        item.bars_until_opposite_cross is not None
        and item.bars_until_opposite_cross <= maximum_bars
        for item in signals
    )


def _required_value(value: float | None, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} is required for MACD crossover")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number
