# -*- coding: utf-8 -*-
"""engine.ib_history

Broker-neutral value objects and validation for IB historical bars.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable


IBHistoryProgressCallback = Callable[[int, int, datetime | None], None]


@dataclass(frozen=True, slots=True)
class IBHistoricalBar:
    """One normalized IB OHLC bar in UTC."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class IBHistoryDownloadResult:
    """Result returned by the IB historical-data request chain."""

    broker: str
    symbol: str
    timeframe: str
    requested_start_utc: datetime
    requested_end_utc: datetime
    bars: tuple[IBHistoricalBar, ...]
    request_count: int

    @property
    def first_timestamp(self) -> datetime | None:
        return self.bars[0].timestamp if self.bars else None

    @property
    def last_timestamp(self) -> datetime | None:
        return self.bars[-1].timestamp if self.bars else None


def is_ib_historical_no_data_error(error_text: str) -> bool:
    """Return True only for IB HMDS code 162 explicit no-data replies."""
    normalized = str(error_text or "").strip().lower()
    return (
        "ib historical data error 162" in normalized
        and "hmds query returned no data" in normalized
    )


def format_ib_historical_end_datetime(value: datetime) -> str:
    """Return the canonical UTC endDateTime accepted by TWS API."""
    if not isinstance(value, datetime):
        raise TypeError("IB historical end datetime must be datetime")
    if value.tzinfo is None:
        raise ValueError("IB historical end datetime must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y%m%d %H:%M:%S UTC")


def decode_ib_historical_bar(bar: object) -> IBHistoricalBar:
    """Decode and validate one IB API BarData-compatible object."""
    timestamp = _parse_ib_bar_timestamp(getattr(bar, "date", ""))
    open_price = _finite_float(getattr(bar, "open", 0.0), "open")
    high = _finite_float(getattr(bar, "high", 0.0), "high")
    low = _finite_float(getattr(bar, "low", 0.0), "low")
    close = _finite_float(getattr(bar, "close", 0.0), "close")
    volume = _volume_float(getattr(bar, "volume", 0.0))

    if high < max(open_price, close, low):
        raise RuntimeError("IB historical bar has invalid high price")
    if low > min(open_price, close, high):
        raise RuntimeError("IB historical bar has invalid low price")

    return IBHistoricalBar(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _parse_ib_bar_timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError("IB historical bar timestamp is empty")

    try:
        epoch_seconds = int(text)
    except ValueError:
        epoch_seconds = 0

    if epoch_seconds > 0:
        return datetime.fromtimestamp(epoch_seconds, tz=UTC)

    normalized = text.replace("  ", " ").strip()
    for pattern in (
        "%Y%m%d %H:%M:%S",
        "%Y%m%d-%H:%M:%S",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(normalized, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"Unsupported IB historical timestamp: {text}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _finite_float(value: object, field_name: str) -> float:
    try:
        normalized = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"IB historical {field_name} is not numeric") from exc
    if not math.isfinite(normalized):
        raise RuntimeError(f"IB historical {field_name} is not finite")
    return normalized


def _volume_float(value: object) -> float:
    try:
        normalized = float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(normalized) or normalized < 0.0:
        return 0.0
    return normalized
