# -*- coding: utf-8 -*-
"""Моделі та допоміжні функції історичних cTrader trend bars.

Модуль декодує OHLC, керує backward pagination і задає callback прогресу
для довгих завантажень без залежності engine від Qt/UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

CTraderHistoryProgressCallback = Callable[[int, int, datetime | None], None]


@dataclass(frozen=True, slots=True)
class CTraderHistoricalBar:
    """One decoded cTrader OHLC trend bar in UTC."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class CTraderHistoryDownloadResult:
    """Result returned by the cTrader history request chain."""

    broker: str
    symbol: str
    timeframe: str
    requested_start_utc: datetime
    requested_end_utc: datetime
    bars: tuple[CTraderHistoricalBar, ...]
    request_count: int

    @property
    def first_timestamp(self) -> datetime | None:
        return self.bars[0].timestamp if self.bars else None

    @property
    def last_timestamp(self) -> datetime | None:
        return self.bars[-1].timestamp if self.bars else None


def next_ctrader_history_chunk_end(
    bars: list[CTraderHistoricalBar],
    requested_start_utc: datetime,
) -> int | None:
    """Return the next backward page boundary in Unix milliseconds."""
    if not bars:
        return None
    if requested_start_utc.tzinfo is None:
        raise ValueError("requested_start_utc must be timezone-aware")

    requested_start = requested_start_utc.astimezone(UTC)
    earliest = min(bar.timestamp.astimezone(UTC) for bar in bars)
    if earliest <= requested_start:
        return None
    return int(earliest.timestamp() * 1000) - 1


def decode_ctrader_trendbars(payload: object) -> list[CTraderHistoricalBar]:
    """Decode ProtoOATrendbar values without importing the SDK module."""
    result: list[CTraderHistoricalBar] = []
    for trendbar in list(getattr(payload, "trendbar", [])):
        timestamp_minutes = int(getattr(trendbar, "utcTimestampInMinutes", 0) or 0)
        low_raw = int(getattr(trendbar, "low", 0) or 0)
        if timestamp_minutes <= 0:
            raise RuntimeError("cTrader trendbar timestamp is invalid")
        if low_raw <= 0:
            raise RuntimeError("cTrader trendbar low price is invalid")

        open_raw = low_raw + int(getattr(trendbar, "deltaOpen", 0) or 0)
        close_raw = low_raw + int(getattr(trendbar, "deltaClose", 0) or 0)
        high_raw = low_raw + int(getattr(trendbar, "deltaHigh", 0) or 0)
        low = low_raw / 100000.0
        open_price = open_raw / 100000.0
        close = close_raw / 100000.0
        high = high_raw / 100000.0
        if high < max(open_price, close, low):
            raise RuntimeError("cTrader trendbar has invalid high price")
        if low > min(open_price, close, high):
            raise RuntimeError("cTrader trendbar has invalid low price")

        result.append(
            CTraderHistoricalBar(
                timestamp=datetime.fromtimestamp(
                    timestamp_minutes * 60,
                    tz=UTC,
                ),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=float(getattr(trendbar, "volume", 0) or 0),
            )
        )
    result.sort(key=lambda item: item.timestamp)
    return result
