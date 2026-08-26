# -*- coding: utf-8 -*-
"""Deterministic per-trade diagnostics for Historical Replay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import SupportsFloat, SupportsIndex

from core.workspace_market_event import normalize_market_timestamp


@dataclass(frozen=True, slots=True)
class WorkspaceHistoricalTradeDiagnostic:
    """Immutable diagnostic snapshot for one closed virtual Replay trade."""

    position_id: str
    order_id: str
    signal_uid: str
    signal_timestamp: datetime
    entry_timestamp: datetime
    close_timestamp: datetime
    entry_price: float
    close_price: float
    direction: str
    volume: float
    macd_state: str
    alligator_state: str
    alligator_timeframe: str
    stop_loss_distance: float
    take_profit_distance: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
    peak_profit: float
    final_profit: float
    close_reason: str
    holding_seconds: float

    def __post_init__(self) -> None:
        for field_name in ("position_id", "order_id", "signal_uid"):
            value = str(getattr(self, field_name) or "").strip()
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)

        signal_timestamp = normalize_market_timestamp(self.signal_timestamp)
        entry_timestamp = normalize_market_timestamp(self.entry_timestamp)
        close_timestamp = normalize_market_timestamp(self.close_timestamp)
        if entry_timestamp < signal_timestamp:
            raise ValueError("entry_timestamp cannot precede signal_timestamp")
        if close_timestamp < entry_timestamp:
            raise ValueError("close_timestamp cannot precede entry_timestamp")
        object.__setattr__(self, "signal_timestamp", signal_timestamp)
        object.__setattr__(self, "entry_timestamp", entry_timestamp)
        object.__setattr__(self, "close_timestamp", close_timestamp)

        direction = _required_upper(self.direction, "direction")
        if direction not in {"BUY", "SELL"}:
            raise ValueError("direction must be BUY or SELL")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(
            self,
            "macd_state",
            _required_upper(self.macd_state, "macd_state"),
        )
        object.__setattr__(
            self,
            "alligator_state",
            _required_upper(self.alligator_state, "alligator_state"),
        )
        object.__setattr__(
            self,
            "alligator_timeframe",
            _required_upper(self.alligator_timeframe, "alligator_timeframe"),
        )
        object.__setattr__(
            self,
            "close_reason",
            _required_upper(self.close_reason, "close_reason"),
        )

        for field_name in (
            "entry_price",
            "close_price",
            "volume",
            "stop_loss_distance",
            "take_profit_distance",
        ):
            value = _positive_float(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)

        for field_name in (
            "maximum_favorable_excursion",
            "maximum_adverse_excursion",
            "peak_profit",
            "final_profit",
        ):
            value = _finite_float(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)

        if self.maximum_favorable_excursion < 0.0:
            raise ValueError("maximum_favorable_excursion cannot be negative")
        if self.maximum_adverse_excursion > 0.0:
            raise ValueError("maximum_adverse_excursion cannot be positive")
        if self.peak_profit < 0.0:
            raise ValueError("peak_profit cannot be negative")

        holding_seconds = _finite_float(self.holding_seconds, "holding_seconds")
        if holding_seconds < 0.0:
            raise ValueError("holding_seconds cannot be negative")
        expected_holding = (close_timestamp - entry_timestamp).total_seconds()
        if not math.isclose(
            holding_seconds,
            expected_holding,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("holding_seconds differs from trade timestamps")
        object.__setattr__(self, "holding_seconds", holding_seconds)


def _required_upper(value: object, field_name: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _finite_float(
    value: str | SupportsFloat | SupportsIndex,
    field_name: str,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _positive_float(
    value: str | SupportsFloat | SupportsIndex,
    field_name: str,
) -> float:
    number = _finite_float(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return number
