# workspace_macd_cross_angle_abc.py — геометрія кута перетину MACD/Signal
# -*- coding: utf-8 -*-
"""ABC-геометрія production/diagnostic кута перетину MACD та Signal.

RoadMap99_04K переводить EXTENDED MACD на версійовану модель кута без
прихованої зміни старих WSP. Для ABC-моделі A — попереднє значення MACD,
B — попереднє значення Signal, C — лінійно інтерпольована точка перетину
між попереднім і поточним завершеними observations. Кут визначається як
звичайний геометричний ``∠ACB``.

Горизонтальна координата походить лише з реального UTC elapsed time;
канонічна одиниця — хвилина. Вертикальна координата масштабується через
цінову convention інструмента. Для підтриманих Forex symbols resolver
повертає 10000 для звичайних quote currencies та 100 для JPY quote;
невідомі/non-Forex symbols відхиляються fail-closed замість вгадування.

Інтерпольована C не переносить signal timestamp назад у часі: Runtime
підтверджує crossover тільки після поточного завершеного bar. Модуль не
використовує майбутні observations, chart pixels, zoom, DPI чи geometry.
Legacy calibrated-angle лишається окремою сумісною моделлю.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

MACD_STATE_CROSS_UP = "MACD_CROSS_UP"
MACD_STATE_CROSS_DOWN = "MACD_CROSS_DOWN"

_FOREX_CURRENCY_CODES = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CNH",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "JPY",
        "MXN",
        "NOK",
        "NZD",
        "PLN",
        "SEK",
        "SGD",
        "TRY",
        "USD",
        "ZAR",
    }
)


class WorkspaceMacdCrossAngleObservation(Protocol):
    """Мінімальний структурний контракт завершеного MACD observation."""

    timestamp: datetime
    macd_value: float | None
    signal_value: float | None
    histogram: float | None
    state: str


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCrossAngleAbcConfig:
    """Явні одиниці координат для ABC-геометрії без прихованої калібровки."""

    indicator_value_scale: float
    time_unit_seconds: float = 60.0

    def __post_init__(self) -> None:
        _positive_finite(self.indicator_value_scale, "indicator_value_scale")
        _positive_finite(self.time_unit_seconds, "time_unit_seconds")


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCrossAngleAbcDiagnostic:
    """Один crossover із точкою C та геометричним кутом ``∠ACB``."""

    timestamp: datetime
    direction: str
    previous_timestamp: datetime
    cross_timestamp: datetime
    interpolation_fraction: float
    elapsed_to_cross_units: float
    macd_before: float
    signal_before: float
    macd_after: float
    signal_after: float
    cross_value: float
    point_a_x: float
    point_a_y: float
    point_b_x: float
    point_b_y: float
    point_c_x: float
    point_c_y: float
    angle_degrees: float | None
    degenerate: bool


@dataclass(frozen=True, slots=True)
class WorkspaceMacdCrossAngleAbcReport:
    """Детермінований набір ABC-кутів для одного observation stream."""

    total_crosses: int
    buy_crosses: int
    sell_crosses: int
    degenerate_crosses: int
    diagnostics: tuple[WorkspaceMacdCrossAngleAbcDiagnostic, ...]


def resolve_workspace_macd_cross_angle_value_scale(symbol: str) -> float:
    """Повернути Forex Y-scale для ABC або відмовити для невідомого symbol."""
    normalized = str(symbol or "").strip().upper()
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError("ABC MACD angle requires canonical 6-letter Forex symbol")
    base = normalized[:3]
    quote = normalized[3:]
    if base not in _FOREX_CURRENCY_CODES or quote not in _FOREX_CURRENCY_CODES:
        raise ValueError("ABC MACD angle supports verified Forex symbols only")
    return 100.0 if quote == "JPY" else 10000.0


def evaluate_workspace_macd_cross_angle_abc(
    previous: WorkspaceMacdCrossAngleObservation,
    current: WorkspaceMacdCrossAngleObservation,
    *,
    config: WorkspaceMacdCrossAngleAbcConfig,
) -> WorkspaceMacdCrossAngleAbcDiagnostic:
    """Обчислити один ABC crossover лише з двох завершених observations."""
    if current.timestamp <= previous.timestamp:
        raise ValueError("MACD observations must have increasing timestamps")
    if current.state not in {MACD_STATE_CROSS_UP, MACD_STATE_CROSS_DOWN}:
        raise ValueError("Current MACD observation is not a crossover")
    return _build_abc_diagnostic(previous, current, config=config)


def build_workspace_macd_cross_angle_abc_report(
    observations: tuple[WorkspaceMacdCrossAngleObservation, ...],
    *,
    config: WorkspaceMacdCrossAngleAbcConfig,
) -> WorkspaceMacdCrossAngleAbcReport:
    """Побудувати ABC-кут для кожного classic crossover без look-ahead."""
    _validate_observation_order(observations)
    diagnostics: list[WorkspaceMacdCrossAngleAbcDiagnostic] = []
    for index, observation in enumerate(observations):
        if observation.state not in {MACD_STATE_CROSS_UP, MACD_STATE_CROSS_DOWN}:
            continue
        if index <= 0:
            raise ValueError("MACD crossover requires a previous observation")
        diagnostics.append(
            evaluate_workspace_macd_cross_angle_abc(
                observations[index - 1],
                observation,
                config=config,
            )
        )
    result = tuple(diagnostics)
    return WorkspaceMacdCrossAngleAbcReport(
        total_crosses=len(result),
        buy_crosses=sum(item.direction == "BUY" for item in result),
        sell_crosses=sum(item.direction == "SELL" for item in result),
        degenerate_crosses=sum(item.degenerate for item in result),
        diagnostics=result,
    )


def _build_abc_diagnostic(
    previous: WorkspaceMacdCrossAngleObservation,
    current: WorkspaceMacdCrossAngleObservation,
    *,
    config: WorkspaceMacdCrossAngleAbcConfig,
) -> WorkspaceMacdCrossAngleAbcDiagnostic:
    direction = "BUY" if current.state == MACD_STATE_CROSS_UP else "SELL"
    macd_before = _required_value(previous.macd_value, "macd_before")
    signal_before = _required_value(previous.signal_value, "signal_before")
    macd_after = _required_value(current.macd_value, "macd_after")
    signal_after = _required_value(current.signal_value, "signal_after")
    histogram_before = _required_value(previous.histogram, "histogram_before")
    histogram_after = _required_value(current.histogram, "histogram_after")
    _validate_cross(direction, histogram_before, histogram_after)

    elapsed_seconds = (current.timestamp - previous.timestamp).total_seconds()
    if elapsed_seconds <= 0.0:
        raise ValueError("MACD observations must have increasing timestamps")
    denominator = histogram_after - histogram_before
    if denominator == 0.0:
        raise ValueError("MACD crossover histogram delta cannot be zero")
    fraction = -histogram_before / denominator
    if fraction < -1e-12 or fraction > 1.0 + 1e-12:
        raise ValueError("Interpolated MACD crossover falls outside bar interval")
    fraction = min(1.0, max(0.0, fraction))

    cross_value_macd = macd_before + fraction * (macd_after - macd_before)
    cross_value_signal = signal_before + fraction * (
        signal_after - signal_before
    )
    cross_value = (cross_value_macd + cross_value_signal) / 2.0
    cross_timestamp = previous.timestamp + timedelta(
        seconds=elapsed_seconds * fraction
    )
    elapsed_units = elapsed_seconds * fraction / config.time_unit_seconds
    scale = config.indicator_value_scale

    point_a = (0.0, macd_before * scale)
    point_b = (0.0, signal_before * scale)
    point_c = (elapsed_units, cross_value * scale)
    angle, degenerate = _angle_at_c(point_a, point_b, point_c)

    return WorkspaceMacdCrossAngleAbcDiagnostic(
        timestamp=current.timestamp,
        direction=direction,
        previous_timestamp=previous.timestamp,
        cross_timestamp=cross_timestamp,
        interpolation_fraction=fraction,
        elapsed_to_cross_units=elapsed_units,
        macd_before=macd_before,
        signal_before=signal_before,
        macd_after=macd_after,
        signal_after=signal_after,
        cross_value=cross_value,
        point_a_x=point_a[0],
        point_a_y=point_a[1],
        point_b_x=point_b[0],
        point_b_y=point_b[1],
        point_c_x=point_c[0],
        point_c_y=point_c[1],
        angle_degrees=angle,
        degenerate=degenerate,
    )


def _angle_at_c(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    point_c: tuple[float, float],
) -> tuple[float | None, bool]:
    ca = (point_a[0] - point_c[0], point_a[1] - point_c[1])
    cb = (point_b[0] - point_c[0], point_b[1] - point_c[1])
    length_ca = math.hypot(*ca)
    length_cb = math.hypot(*cb)
    if length_ca == 0.0 or length_cb == 0.0:
        return None, True
    cosine = (ca[0] * cb[0] + ca[1] * cb[1]) / (length_ca * length_cb)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine)), False


def _validate_observation_order(
    observations: tuple[WorkspaceMacdCrossAngleObservation, ...],
) -> None:
    previous_timestamp: datetime | None = None
    for observation in observations:
        if (
            previous_timestamp is not None
            and observation.timestamp <= previous_timestamp
        ):
            raise ValueError("MACD observations must be strictly chronological")
        previous_timestamp = observation.timestamp


def _validate_cross(
    direction: str,
    histogram_before: float,
    histogram_after: float,
) -> None:
    if direction == "BUY":
        if not (histogram_before <= 0.0 < histogram_after):
            raise ValueError("BUY crossover histogram signs are inconsistent")
        return
    if not (histogram_before >= 0.0 > histogram_after):
        raise ValueError("SELL crossover histogram signs are inconsistent")


def _required_value(value: float | None, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required")
    return _finite(value, name)


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_finite(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result
