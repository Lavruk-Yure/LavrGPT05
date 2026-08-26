# -*- coding: utf-8 -*-
"""Canonical market-data models shared by every Algorithm Workspace mode."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from core.algorithm_workspace import WORKSPACE_DATA_MODES


def normalize_market_timestamp(value: datetime | str) -> datetime:
    """Return an aware UTC timestamp or raise ValueError."""
    if isinstance(value, datetime):
        timestamp = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp is required")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("Invalid market timestamp") from exc

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _finite_number(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass(frozen=True, slots=True)
class WorkspaceMarketBar:
    """One immutable OHLCV bar used by Replay and future history providers."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float
    ask: float

    def __post_init__(self) -> None:
        timestamp = normalize_market_timestamp(self.timestamp)
        open_price = _finite_number(self.open, "open")
        high_price = _finite_number(self.high, "high")
        low_price = _finite_number(self.low, "low")
        close_price = _finite_number(self.close, "close")
        volume = _finite_number(self.volume, "volume")
        bid = _finite_number(self.bid, "bid")
        ask = _finite_number(self.ask, "ask")

        if volume < 0.0:
            raise ValueError("volume cannot be negative")
        if high_price < max(open_price, close_price, low_price):
            raise ValueError("high is below OHLC values")
        if low_price > min(open_price, close_price, high_price):
            raise ValueError("low is above OHLC values")
        if ask < bid:
            raise ValueError("ask cannot be below bid")

        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "open", open_price)
        object.__setattr__(self, "high", high_price)
        object.__setattr__(self, "low", low_price)
        object.__setattr__(self, "close", close_price)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)


@dataclass(frozen=True, slots=True)
class WorkspaceQuote:
    """One immutable bid/ask quote for future tick-based workspace modes."""

    timestamp: datetime
    bid: float
    ask: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        timestamp = normalize_market_timestamp(self.timestamp)
        bid = _finite_number(self.bid, "bid")
        ask = _finite_number(self.ask, "ask")
        volume = _finite_number(self.volume, "volume")
        if ask < bid:
            raise ValueError("ask cannot be below bid")
        if volume < 0.0:
            raise ValueError("volume cannot be negative")
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "volume", volume)


@dataclass(frozen=True, slots=True)
class WorkspaceMarketEvent:
    """Canonical market event consumed by workspace algorithms."""

    timestamp: datetime
    broker: str
    symbol: str
    timeframe: str
    bid: float
    ask: float
    spread: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    source_mode: str

    def __post_init__(self) -> None:
        timestamp = normalize_market_timestamp(self.timestamp)
        broker = str(self.broker or "").strip().upper()
        symbol = str(self.symbol or "").strip().upper()
        timeframe = str(self.timeframe or "").strip().upper()
        source_mode = str(self.source_mode or "").strip().upper()
        if not broker:
            raise ValueError("broker is required")
        if not symbol:
            raise ValueError("symbol is required")
        if not timeframe:
            raise ValueError("timeframe is required")
        if source_mode not in WORKSPACE_DATA_MODES:
            raise ValueError("Invalid source_mode")

        bid = _finite_number(self.bid, "bid")
        ask = _finite_number(self.ask, "ask")
        spread = _finite_number(self.spread, "spread")
        open_price = _finite_number(self.open, "open")
        high_price = _finite_number(self.high, "high")
        low_price = _finite_number(self.low, "low")
        close_price = _finite_number(self.close, "close")
        volume = _finite_number(self.volume, "volume")

        if ask < bid:
            raise ValueError("ask cannot be below bid")
        expected_spread = ask - bid
        if not math.isclose(spread, expected_spread, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("spread must equal ask - bid")
        if spread < 0.0:
            raise ValueError("spread cannot be negative")
        if volume < 0.0:
            raise ValueError("volume cannot be negative")
        if high_price < max(open_price, close_price, low_price):
            raise ValueError("high is below OHLC values")
        if low_price > min(open_price, close_price, high_price):
            raise ValueError("low is above OHLC values")

        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "spread", spread)
        object.__setattr__(self, "open", open_price)
        object.__setattr__(self, "high", high_price)
        object.__setattr__(self, "low", low_price)
        object.__setattr__(self, "close", close_price)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "source_mode", source_mode)

    @classmethod
    def from_bar(
        cls,
        *,
        bar: WorkspaceMarketBar,
        broker: str,
        symbol: str,
        timeframe: str,
        source_mode: str,
    ) -> WorkspaceMarketEvent:
        """Build one canonical event from an OHLCV bar."""
        return cls(
            timestamp=bar.timestamp,
            broker=broker,
            symbol=symbol,
            timeframe=timeframe,
            bid=bar.bid,
            ask=bar.ask,
            spread=bar.ask - bar.bid,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source_mode=source_mode,
        )
