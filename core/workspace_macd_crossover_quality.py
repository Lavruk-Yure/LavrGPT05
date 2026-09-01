# -*- coding: utf-8 -*-
"""Детермінована математика MACD crossover quality для RoadMap99.

Одна no-look-ahead реалізація використовується diagnostics і production
EXTENDED MACD. RoadMap99_04K підтримує дві явні моделі кута: стару
``LEGACY_CALIBRATED`` для сумісності з persisted WSP та нову
``ABC_REALTIME_SCALED`` з реальною UTC-часовою віссю, instrument Y-scale і
лінійно інтерпольованою точкою перетину C. Немає прихованого перерахунку
45° у ABC-поріг; кожна модель має власне persisted значення.

Жодна модель не читає chart pixels, zoom, DPI чи geometry і не використовує
майбутні observations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, SupportsFloat, SupportsIndex

from core.workspace_macd_cross_angle_abc import (
    WorkspaceMacdCrossAngleAbcConfig,
    evaluate_workspace_macd_cross_angle_abc,
)
from engine.runtime_constants import (
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC,
    WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY,
    WORKSPACE_MACD_CROSS_ANGLE_MODELS,
)

MACD_STATE_CROSS_UP = "MACD_CROSS_UP"
MACD_STATE_CROSS_DOWN = "MACD_CROSS_DOWN"

MACD_EXTREMUM_MIN_PROMINENCE = 0.00001
MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE = 0.00005
MACD_CROSS_MIN_ANGLE_DEGREES = 45.0
MACD_CROSS_45_Y_PER_M15_BAR = 0.0000535
MACD_CROSS_ANGLE_REFERENCE_MINUTES = 15
MACD_EXTREMUM_SEARCH_WINDOWS = (3, 5, 7)

MACD_EXTREMUM_MINIMUM = "MINIMUM"
MACD_EXTREMUM_MAXIMUM = "MAXIMUM"
MACD_EXTREMUM_NONE = "NONE"

MACD_QUALITY_REASON_ACCEPTED = "MACD_CROSS_ACCEPTED"
MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND = "MACD_EXTREMUM_NOT_FOUND"
MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK = "MACD_EXTREMUM_TOO_WEAK"
MACD_QUALITY_REASON_DISTANCE_TOO_SMALL = "MACD_EXTREMUM_DISTANCE_TOO_SMALL"
MACD_QUALITY_REASON_CROSS_TOO_FLAT = "MACD_CROSS_TOO_FLAT"


class WorkspaceMacdQualityObservation(Protocol):
    """Structural MACD observation contract used without circular imports."""

    timestamp: datetime
    macd_value: float | None
    signal_value: float | None
    histogram: float | None
    state: str


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCrossoverQualityConfig:
    """Пороги quality та явна legacy/ABC модель кута crossover."""

    angle_reference_y_per_minute: float | None = None
    strategy_bar_minutes: int = 15
    extremum_min_prominence: float = MACD_EXTREMUM_MIN_PROMINENCE
    extremum_to_cross_min_distance: float = MACD_EXTREMUM_TO_CROSS_MIN_DISTANCE
    cross_min_angle_degrees: float = MACD_CROSS_MIN_ANGLE_DEGREES
    angle_model: str = WORKSPACE_MACD_CROSS_ANGLE_MODEL_LEGACY
    abc_indicator_value_scale: float | None = None
    abc_time_unit_seconds: float = 60.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.strategy_bar_minutes, bool)
            or not isinstance(self.strategy_bar_minutes, int)
            or self.strategy_bar_minutes <= 0
        ):
            raise ValueError("strategy_bar_minutes must be positive integer")
        _non_negative_finite(
            self.extremum_min_prominence,
            "extremum_min_prominence",
        )
        _non_negative_finite(
            self.extremum_to_cross_min_distance,
            "extremum_to_cross_min_distance",
        )
        angle = _non_negative_finite(
            self.cross_min_angle_degrees,
            "cross_min_angle_degrees",
        )
        if angle > 180.0:
            raise ValueError("cross_min_angle_degrees cannot exceed 180")
        normalized_model = str(self.angle_model or "").strip().upper()
        if normalized_model not in WORKSPACE_MACD_CROSS_ANGLE_MODELS:
            raise ValueError("unsupported MACD crossover angle model")
        object.__setattr__(self, "angle_model", normalized_model)
        _positive_finite(self.abc_time_unit_seconds, "abc_time_unit_seconds")
        if normalized_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC:
            if self.abc_indicator_value_scale is None:
                raise ValueError("ABC MACD angle requires abc_indicator_value_scale")
            _positive_finite(
                self.abc_indicator_value_scale,
                "abc_indicator_value_scale",
            )
            return
        if self.angle_reference_y_per_minute is None:
            raise ValueError("Legacy MACD angle requires angle_reference_y_per_minute")
        _positive_finite(
            self.angle_reference_y_per_minute,
            "angle_reference_y_per_minute",
        )

    @property
    def angle_reference_y_per_bar(self) -> float:
        """Повернути legacy Y45 за один strategy bar."""
        reference = self.angle_reference_y_per_minute
        if reference is None:
            raise ValueError("ABC MACD angle has no legacy Y45 reference")
        return reference * self.strategy_bar_minutes


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCrossoverQualityDiagnostic:
    """One factual crossover quality snapshot without trading effects."""

    timestamp: datetime
    direction: str
    macd_value: float
    signal_value: float
    histogram_before: float
    histogram_after: float
    extremum_timestamp: datetime | None
    extremum_value: float | None
    extremum_type: str
    search_window: int | None
    extremum_prominence: float | None
    extremum_to_cross_distance: float | None
    crossover_steepness: float
    crossover_steepness_per_minute: float
    macd_slope_per_minute: float
    signal_slope_per_minute: float
    effective_angle_degrees: float
    extremum_found: bool
    criterion_extremum_pass: bool
    criterion_prominence_pass: bool
    criterion_distance_pass: bool
    criterion_angle_pass: bool
    final_quality_pass: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCrossoverQualityReport:
    """Aggregate RoadMap99 quality diagnostics for one observation stream."""

    total_crosses: int
    buy_crosses: int
    sell_crosses: int
    window_3: int
    window_5: int
    window_7: int
    extremum_not_found: int
    prominence_pass: int
    distance_pass: int
    angle_pass: int
    final_quality_pass: int
    final_quality_reject: int
    rejected_extremum_not_found: int
    rejected_extremum_too_weak: int
    rejected_distance_too_small: int
    rejected_cross_too_flat: int
    signals: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...]


def chart_45_degree_reference_y_per_minute(
    *,
    value_low: float,
    value_high: float,
    plot_width_px: float,
    plot_height_px: float,
    visible_bars: int,
    strategy_bar_minutes: int,
) -> float:
    """Convert one chart viewport's visual 45 degrees into numeric Y/minute.

    This is a calibration helper only. Once the numeric reference is fixed,
    Historical Replay diagnostics use the fixed value and are independent of
    chart size, zoom, DPI, or window geometry.
    """
    low = _finite(value_low, "value_low")
    high = _finite(value_high, "value_high")
    if high <= low:
        raise ValueError("value_high must exceed value_low")
    width = _positive_finite(plot_width_px, "plot_width_px")
    height = _positive_finite(plot_height_px, "plot_height_px")
    if isinstance(visible_bars, bool) or not isinstance(visible_bars, int):
        raise ValueError("visible_bars must be positive integer")
    if visible_bars <= 0:
        raise ValueError("visible_bars must be positive integer")
    if (
        isinstance(strategy_bar_minutes, bool)
        or not isinstance(strategy_bar_minutes, int)
        or strategy_bar_minutes <= 0
    ):
        raise ValueError("strategy_bar_minutes must be positive integer")

    x_pixels_per_bar = width / visible_bars
    y_value_per_pixel = (high - low) / height
    y_value_per_bar = x_pixels_per_bar * y_value_per_pixel
    return y_value_per_bar / strategy_bar_minutes


def calibrated_macd_cross_angle_reference_y_per_minute() -> float:
    """Return the fixed RoadMap99 manual 45-degree calibration."""
    return MACD_CROSS_45_Y_PER_M15_BAR / MACD_CROSS_ANGLE_REFERENCE_MINUTES


def evaluate_workspace_macd_crossover_quality(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
    *,
    config: WorkspaceMacdCrossoverQualityConfig,
) -> WorkspaceMacdCrossoverQualityDiagnostic | None:
    """Evaluate only the newest observation when it is a classic crossover."""
    _validate_observation_order(observations)
    if not observations:
        return None
    cross_index = len(observations) - 1
    observation = observations[cross_index]
    if observation.state not in {MACD_STATE_CROSS_UP, MACD_STATE_CROSS_DOWN}:
        return None
    if cross_index <= 0:
        raise ValueError("MACD crossover requires a previous observation")
    return _build_crossover_diagnostic(
        observations,
        cross_index=cross_index,
        config=config,
    )


def build_workspace_macd_crossover_quality_diagnostics(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
    *,
    config: WorkspaceMacdCrossoverQualityConfig,
) -> WorkspaceMacdCrossoverQualityReport:
    """Analyze current classic crossovers without filtering any proposal."""
    _validate_observation_order(observations)
    diagnostics: list[WorkspaceMacdCrossoverQualityDiagnostic] = []

    for cross_index, observation in enumerate(observations):
        if observation.state not in {MACD_STATE_CROSS_UP, MACD_STATE_CROSS_DOWN}:
            continue
        diagnostics.append(
            _build_crossover_diagnostic(
                observations,
                cross_index=cross_index,
                config=config,
            )
        )

    signals = tuple(diagnostics)
    return WorkspaceMacdCrossoverQualityReport(
        total_crosses=len(signals),
        buy_crosses=sum(item.direction == "BUY" for item in signals),
        sell_crosses=sum(item.direction == "SELL" for item in signals),
        window_3=sum(item.search_window == 3 for item in signals),
        window_5=sum(item.search_window == 5 for item in signals),
        window_7=sum(item.search_window == 7 for item in signals),
        extremum_not_found=sum(not item.extremum_found for item in signals),
        prominence_pass=sum(item.criterion_prominence_pass for item in signals),
        distance_pass=sum(item.criterion_distance_pass for item in signals),
        angle_pass=sum(item.criterion_angle_pass for item in signals),
        final_quality_pass=sum(item.final_quality_pass for item in signals),
        final_quality_reject=sum(not item.final_quality_pass for item in signals),
        rejected_extremum_not_found=_reason_count(
            signals,
            MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND,
        ),
        rejected_extremum_too_weak=_reason_count(
            signals,
            MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
        ),
        rejected_distance_too_small=_reason_count(
            signals,
            MACD_QUALITY_REASON_DISTANCE_TOO_SMALL,
        ),
        rejected_cross_too_flat=_reason_count(
            signals,
            MACD_QUALITY_REASON_CROSS_TOO_FLAT,
        ),
        signals=signals,
    )


def _build_crossover_diagnostic(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
    *,
    cross_index: int,
    config: WorkspaceMacdCrossoverQualityConfig,
) -> WorkspaceMacdCrossoverQualityDiagnostic:
    if cross_index <= 0:
        raise ValueError("MACD crossover requires a previous observation")
    observation = observations[cross_index]
    previous = observations[cross_index - 1]
    if observation.state not in {MACD_STATE_CROSS_UP, MACD_STATE_CROSS_DOWN}:
        raise ValueError("Newest MACD observation is not a crossover")

    direction = "BUY" if observation.state == MACD_STATE_CROSS_UP else "SELL"
    histogram_before = _required_value(previous.histogram, "histogram_before")
    histogram_after = _required_value(observation.histogram, "histogram_after")
    _validate_cross(direction, histogram_before, histogram_after)

    macd_before = _required_value(previous.macd_value, "macd_before")
    macd_after = _required_value(observation.macd_value, "macd_after")
    signal_before = _required_value(previous.signal_value, "signal_before")
    signal_after = _required_value(observation.signal_value, "signal_after")

    extremum = _find_previous_extremum(
        observations,
        cross_index=cross_index,
        direction=direction,
    )
    extremum_timestamp: datetime | None = None
    extremum_value: float | None = None
    search_window: int | None = None
    extremum_prominence: float | None = None
    extremum_distance: float | None = None
    extremum_type = (
        MACD_EXTREMUM_MINIMUM if direction == "BUY" else MACD_EXTREMUM_MAXIMUM
    )
    if extremum is not None:
        extremum_index, search_window = extremum
        extremum_observation = observations[extremum_index]
        extremum_timestamp = extremum_observation.timestamp
        extremum_value = _required_value(
            extremum_observation.histogram,
            "extremum_value",
        )
        extremum_prominence = _extremum_prominence(
            observations,
            extremum_index=extremum_index,
            direction=direction,
        )
        extremum_distance = abs(extremum_value)
    else:
        extremum_type = MACD_EXTREMUM_NONE

    bar_minutes = float(config.strategy_bar_minutes)
    histogram_delta = histogram_after - histogram_before
    crossover_steepness = abs(histogram_delta)
    crossover_steepness_per_minute = crossover_steepness / bar_minutes
    macd_slope_per_minute = (macd_after - macd_before) / bar_minutes
    signal_slope_per_minute = (signal_after - signal_before) / bar_minutes
    if config.angle_model == WORKSPACE_MACD_CROSS_ANGLE_MODEL_ABC:
        abc_scale = config.abc_indicator_value_scale
        if abc_scale is None:
            raise ValueError("ABC MACD angle requires indicator value scale")
        abc = evaluate_workspace_macd_cross_angle_abc(
            previous,
            observation,
            config=WorkspaceMacdCrossAngleAbcConfig(
                indicator_value_scale=abc_scale,
                time_unit_seconds=config.abc_time_unit_seconds,
            ),
        )
        effective_angle = abc.angle_degrees or 0.0
    else:
        legacy_reference = config.angle_reference_y_per_minute
        if legacy_reference is None:
            raise ValueError("Legacy MACD angle requires Y45 reference")
        effective_angle = _effective_cross_angle_degrees(
            macd_slope_per_minute=macd_slope_per_minute,
            signal_slope_per_minute=signal_slope_per_minute,
            reference_y_per_minute=legacy_reference,
        )

    extremum_found = extremum is not None
    criterion_prominence_pass = bool(
        extremum_prominence is not None
        and extremum_prominence >= config.extremum_min_prominence
    )
    criterion_distance_pass = bool(
        extremum_distance is not None
        and extremum_distance >= config.extremum_to_cross_min_distance
    )
    criterion_angle_pass = effective_angle >= config.cross_min_angle_degrees
    final_quality_pass = bool(
        extremum_found
        and criterion_prominence_pass
        and criterion_distance_pass
        and criterion_angle_pass
    )
    reason_code = _quality_reason_code(
        extremum_found=extremum_found,
        prominence_pass=criterion_prominence_pass,
        distance_pass=criterion_distance_pass,
        angle_pass=criterion_angle_pass,
    )
    return WorkspaceMacdCrossoverQualityDiagnostic(
        timestamp=observation.timestamp,
        direction=direction,
        macd_value=macd_after,
        signal_value=signal_after,
        histogram_before=histogram_before,
        histogram_after=histogram_after,
        extremum_timestamp=extremum_timestamp,
        extremum_value=extremum_value,
        extremum_type=extremum_type,
        search_window=search_window,
        extremum_prominence=extremum_prominence,
        extremum_to_cross_distance=extremum_distance,
        crossover_steepness=crossover_steepness,
        crossover_steepness_per_minute=crossover_steepness_per_minute,
        macd_slope_per_minute=macd_slope_per_minute,
        signal_slope_per_minute=signal_slope_per_minute,
        effective_angle_degrees=effective_angle,
        extremum_found=extremum_found,
        criterion_extremum_pass=extremum_found,
        criterion_prominence_pass=criterion_prominence_pass,
        criterion_distance_pass=criterion_distance_pass,
        criterion_angle_pass=criterion_angle_pass,
        final_quality_pass=final_quality_pass,
        reason_code=reason_code,
    )


def _find_previous_extremum(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
    *,
    cross_index: int,
    direction: str,
) -> tuple[int, int] | None:
    for window in MACD_EXTREMUM_SEARCH_WINDOWS:
        start = max(0, cross_index - window + 1)
        for index in range(cross_index - 1, start, -1):
            if _is_local_extremum(
                observations,
                index=index,
                direction=direction,
            ):
                return index, window
    return None


def _is_local_extremum(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
    *,
    index: int,
    direction: str,
) -> bool:
    if index <= 0 or index >= len(observations) - 1:
        return False
    previous = observations[index - 1].histogram
    current = observations[index].histogram
    following = observations[index + 1].histogram
    if previous is None or current is None or following is None:
        return False
    previous_value = _finite(previous, "extremum_previous")
    current_value = _finite(current, "extremum_current")
    following_value = _finite(following, "extremum_following")
    if direction == "BUY":
        return current_value < previous_value and current_value <= following_value
    return current_value > previous_value and current_value >= following_value


def _extremum_prominence(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
    *,
    extremum_index: int,
    direction: str,
) -> float:
    previous = _required_value(
        observations[extremum_index - 1].histogram,
        "extremum_previous",
    )
    current = _required_value(
        observations[extremum_index].histogram,
        "extremum_current",
    )
    following = _required_value(
        observations[extremum_index + 1].histogram,
        "extremum_following",
    )
    if direction == "BUY":
        return min(previous - current, following - current)
    return min(current - previous, current - following)


def _effective_cross_angle_degrees(
    *,
    macd_slope_per_minute: float,
    signal_slope_per_minute: float,
    reference_y_per_minute: float,
) -> float:
    reference = _positive_finite(
        reference_y_per_minute,
        "reference_y_per_minute",
    )
    macd_angle = math.degrees(math.atan(macd_slope_per_minute / reference))
    signal_angle = math.degrees(math.atan(signal_slope_per_minute / reference))
    return abs(macd_angle - signal_angle)


def _quality_reason_code(
    *,
    extremum_found: bool,
    prominence_pass: bool,
    distance_pass: bool,
    angle_pass: bool,
) -> str:
    if not extremum_found:
        return MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND
    if not prominence_pass:
        return MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK
    if not distance_pass:
        return MACD_QUALITY_REASON_DISTANCE_TOO_SMALL
    if not angle_pass:
        return MACD_QUALITY_REASON_CROSS_TOO_FLAT
    return MACD_QUALITY_REASON_ACCEPTED


def _validate_observation_order(
    observations: tuple[WorkspaceMacdQualityObservation, ...],
) -> None:
    previous_timestamp: datetime | None = None
    for observation in observations:
        if previous_timestamp is not None:
            if observation.timestamp <= previous_timestamp:
                raise ValueError(
                    "MACD observations must be strictly ordered and unique"
                )
        previous_timestamp = observation.timestamp


def _validate_cross(
    direction: str,
    histogram_before: float,
    histogram_after: float,
) -> None:
    if direction == "BUY":
        if not histogram_before <= 0.0 < histogram_after:
            raise ValueError("BUY crossover violates classic MACD contract")
        return
    if not histogram_before >= 0.0 > histogram_after:
        raise ValueError("SELL crossover violates classic MACD contract")


def _reason_count(
    signals: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    reason_code: str,
) -> int:
    return sum(item.reason_code == reason_code for item in signals)


def _required_value(value: float | None, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} is required")
    return _finite(value, field_name)


def _finite(
    value: str | SupportsFloat | SupportsIndex,
    field_name: str,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _positive_finite(
    value: str | SupportsFloat | SupportsIndex,
    field_name: str,
) -> float:
    number = _finite(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _non_negative_finite(
    value: str | SupportsFloat | SupportsIndex,
    field_name: str,
) -> float:
    number = _finite(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return number
