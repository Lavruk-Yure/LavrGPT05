# workspace_macd_signal_latency.py — RoadMap99_04D MACD Signal Latency
# -*- coding: utf-8 -*-
"""Детермінована діагностика затримки price turn -> MACD signal -> entry.

Модуль не намагається оголосити точний «момент початку руху» ринку, бо така
точка залежить від способу інтерпретації price structure. Для порівнюваного
RoadMap99-експерименту використовується явний proxy: для BUY береться
найближчий у часі мінімум Low у попередньому вікні завершених strategy bars,
для SELL — найближчий максимум High. Вікно задається параметром і тому може
перевірятися як діапазон, а не як універсальна константа.

Для кожного MACD crossover фіксуються три часові точки: directional price
extremum, signal bar і очікуваний NEXT_BAR_OPEN entry bar. У розрахунок
екстремуму потрапляють тільки bars з timestamp <= signal timestamp, тому
діагностика не має look-ahead. Якщо наступного очікуваного strategy bar немає,
entry позначається недоступним замість перенесення через gap.

Модуль не змінює MACD, MACD Quality, Alligator, risk або virtual execution.
Його мета — дати стабільну метрику latency, яку пізніше можна однаково
застосувати до різних MACD profile snapshots і порівнювати швидкість сигналу
окремо від торгового PnL. Broker execution тут відсутній.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from core.workspace_macd_crossover_quality import (
    WorkspaceMacdCrossoverQualityDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent


@dataclass(frozen=True, slots=True)
class WorkspaceMacdSignalLatencySample:
    """Одна причинна часово-просторова оцінка MACD crossover."""

    signal_timestamp: datetime
    direction: str
    price_extremum_timestamp: datetime
    price_extremum_value: float
    price_to_signal_bars: int
    expected_entry_timestamp: datetime
    signal_to_entry_bars: int | None
    price_to_entry_bars: int | None


@dataclass(frozen=True, slots=True)
class WorkspaceMacdSignalLatencyReport:
    """Агреговані latency-метрики для одного lookback-вікна."""

    lookback_bars: int
    strategy_bar_minutes: int
    total_signals: int
    buy_signals: int
    sell_signals: int
    entry_eligible_signals: int
    entry_gap_signals: int
    average_price_to_signal_bars: float
    median_price_to_signal_bars: float
    average_price_to_entry_bars: float | None
    median_price_to_entry_bars: float | None
    buy_average_price_to_signal_bars: float
    sell_average_price_to_signal_bars: float
    lag_0: int
    lag_1: int
    lag_2: int
    lag_3: int
    lag_4: int
    lag_5_plus: int
    lag_le_1: int
    lag_le_2: int
    lag_le_3: int
    samples: tuple[WorkspaceMacdSignalLatencySample, ...]

    @property
    def average_price_to_signal_minutes(self) -> float:
        """Середній proxy-lag від price extremum до signal у хвилинах."""
        return self.average_price_to_signal_bars * self.strategy_bar_minutes

    @property
    def average_price_to_entry_minutes(self) -> float | None:
        """Середній proxy-lag від price extremum до entry у хвилинах."""
        if self.average_price_to_entry_bars is None:
            return None
        return self.average_price_to_entry_bars * self.strategy_bar_minutes


def build_workspace_macd_signal_latency_report(
    events: tuple[WorkspaceMarketEvent, ...],
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    *,
    lookback_bars: int,
    strategy_bar_minutes: int,
    quality_only: bool = True,
) -> WorkspaceMacdSignalLatencyReport:
    """Побудувати latency report без використання майбутніх price bars."""
    _positive_integer(lookback_bars, "lookback_bars")
    _positive_integer(strategy_bar_minutes, "strategy_bar_minutes")
    _validate_events(events)

    event_index = {event.timestamp: index for index, event in enumerate(events)}
    selected = tuple(
        item for item in diagnostics if item.final_quality_pass or not quality_only
    )
    samples = tuple(
        _build_sample(
            events,
            event_index,
            diagnostic,
            lookback_bars=lookback_bars,
            strategy_bar_minutes=strategy_bar_minutes,
        )
        for diagnostic in selected
    )
    if not samples:
        raise ValueError("MACD latency report requires at least one signal")

    signal_lags = tuple(item.price_to_signal_bars for item in samples)
    entry_lags = tuple(
        item.price_to_entry_bars
        for item in samples
        if item.price_to_entry_bars is not None
    )
    buy_lags = tuple(
        item.price_to_signal_bars for item in samples if item.direction == "BUY"
    )
    sell_lags = tuple(
        item.price_to_signal_bars for item in samples if item.direction == "SELL"
    )
    if not buy_lags or not sell_lags:
        raise ValueError("MACD latency report requires BUY and SELL samples")

    return WorkspaceMacdSignalLatencyReport(
        lookback_bars=lookback_bars,
        strategy_bar_minutes=strategy_bar_minutes,
        total_signals=len(samples),
        buy_signals=len(buy_lags),
        sell_signals=len(sell_lags),
        entry_eligible_signals=len(entry_lags),
        entry_gap_signals=len(samples) - len(entry_lags),
        average_price_to_signal_bars=_average(signal_lags),
        median_price_to_signal_bars=float(median(signal_lags)),
        average_price_to_entry_bars=(_average(entry_lags) if entry_lags else None),
        median_price_to_entry_bars=(float(median(entry_lags)) if entry_lags else None),
        buy_average_price_to_signal_bars=_average(buy_lags),
        sell_average_price_to_signal_bars=_average(sell_lags),
        lag_0=sum(value == 0 for value in signal_lags),
        lag_1=sum(value == 1 for value in signal_lags),
        lag_2=sum(value == 2 for value in signal_lags),
        lag_3=sum(value == 3 for value in signal_lags),
        lag_4=sum(value == 4 for value in signal_lags),
        lag_5_plus=sum(value >= 5 for value in signal_lags),
        lag_le_1=sum(value <= 1 for value in signal_lags),
        lag_le_2=sum(value <= 2 for value in signal_lags),
        lag_le_3=sum(value <= 3 for value in signal_lags),
        samples=samples,
    )


def _build_sample(
    events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
    diagnostic: WorkspaceMacdCrossoverQualityDiagnostic,
    *,
    lookback_bars: int,
    strategy_bar_minutes: int,
) -> WorkspaceMacdSignalLatencySample:
    signal_index = event_index.get(diagnostic.timestamp)
    if signal_index is None:
        raise ValueError("MACD signal timestamp is absent from strategy events")

    first_index = max(0, signal_index - lookback_bars + 1)
    window = events[first_index : signal_index + 1]  # noqa
    if diagnostic.direction == "BUY":
        extremum_value = min(float(event.low) for event in window)
        relative_index = max(
            index
            for index, event in enumerate(window)
            if float(event.low) == extremum_value
        )
    elif diagnostic.direction == "SELL":
        extremum_value = max(float(event.high) for event in window)
        relative_index = max(
            index
            for index, event in enumerate(window)
            if float(event.high) == extremum_value
        )
    else:
        raise ValueError(f"Unsupported MACD direction: {diagnostic.direction}")

    extremum_index = first_index + relative_index
    extremum_timestamp = events[extremum_index].timestamp
    if extremum_timestamp > diagnostic.timestamp:
        raise AssertionError("MACD latency diagnostic used future price data")

    expected_entry_timestamp = diagnostic.timestamp + timedelta(
        minutes=strategy_bar_minutes
    )
    signal_to_entry_bars: int | None = None
    price_to_entry_bars: int | None = None
    next_index = signal_index + 1
    if (
        next_index < len(events)
        and events[next_index].timestamp == expected_entry_timestamp
    ):
        signal_to_entry_bars = 1
        price_to_entry_bars = signal_index - extremum_index + 1

    return WorkspaceMacdSignalLatencySample(
        signal_timestamp=diagnostic.timestamp,
        direction=diagnostic.direction,
        price_extremum_timestamp=extremum_timestamp,
        price_extremum_value=extremum_value,
        price_to_signal_bars=signal_index - extremum_index,
        expected_entry_timestamp=expected_entry_timestamp,
        signal_to_entry_bars=signal_to_entry_bars,
        price_to_entry_bars=price_to_entry_bars,
    )


def _validate_events(events: tuple[WorkspaceMarketEvent, ...]) -> None:
    if not events:
        raise ValueError("MACD latency report requires strategy events")
    previous: datetime | None = None
    timestamps: set[datetime] = set()
    for event in events:
        if event.timestamp in timestamps:
            raise ValueError("strategy event timestamps must be unique")
        if previous is not None and event.timestamp <= previous:
            raise ValueError("strategy events must be strictly ordered")
        timestamps.add(event.timestamp)
        previous = event.timestamp


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _average(values: tuple[int, ...]) -> float:
    if not values:
        raise ValueError("average requires at least one value")
    return sum(values) / len(values)
