# -*- coding: utf-8 -*-
"""Deterministic margin mathematics for Historical Replay virtual trading."""

from __future__ import annotations

import math
from dataclasses import dataclass

HISTORICAL_REPLAY_LEVERAGE = 500.0


@dataclass(frozen=True, slots=True)
class WorkspaceReplayMarginSnapshot:
    """One synthetic Replay margin state in account-currency units."""

    leverage: float
    balance: float
    equity: float
    used_margin: float
    free_margin: float

    def __post_init__(self) -> None:
        leverage = _positive_float(self.leverage, "leverage")
        balance = _finite_float(self.balance, "balance")
        equity = _finite_float(self.equity, "equity")
        used_margin = _non_negative_float(self.used_margin, "used_margin")
        free_margin = _finite_float(self.free_margin, "free_margin")
        expected_free_margin = equity - used_margin
        if not math.isclose(
            free_margin,
            expected_free_margin,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("free_margin must equal equity - used_margin")
        object.__setattr__(self, "leverage", leverage)
        object.__setattr__(self, "balance", balance)
        object.__setattr__(self, "equity", equity)
        object.__setattr__(self, "used_margin", used_margin)
        object.__setattr__(self, "free_margin", free_margin)


def replay_required_margin(
    *,
    volume: float,
    price: float,
    leverage: float = HISTORICAL_REPLAY_LEVERAGE,
) -> float:
    """Return notional margin; leverage never multiplies trading PnL."""
    normalized_volume = _positive_float(volume, "volume")
    normalized_price = _positive_float(price, "price")
    normalized_leverage = _positive_float(leverage, "leverage")
    return normalized_volume * normalized_price / normalized_leverage


def _finite_float(value: object, field_name: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _positive_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _non_negative_float(value: object, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} cannot be negative")
    return number
