# broker_position.py
"""
Канонічна модель broker position для LGE runtime.

Модуль не залежить від:
- Qt;
- SQLite;
- конкретного broker API.

RoadMap68:
- foundation для IB positions;
- foundation для cTrader positions;
- єдина broker-independent модель позиції.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

POSITION_SIDE_BUY = "BUY"
POSITION_SIDE_SELL = "SELL"
POSITION_SIDE_UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class BrokerPosition:
    """
    Нормалізована інформація про відкриту broker position.
    """

    broker: str
    account_id: str
    account_mode: str
    position_id: str
    symbol_name: str
    side: str = POSITION_SIDE_UNKNOWN
    volume: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float = 0.0
    currency: str = ""
    opened_utc: str = ""
    raw_payload: dict | None = None

    def to_dict(self) -> dict:
        """
        Перетворити BrokerPosition у dict.
        """

        return {
            "broker": self.broker,
            "account_id": self.account_id,
            "account_mode": self.account_mode,
            "position_id": self.position_id,
            "symbol_name": self.symbol_name,
            "side": self.side,
            "volume": self.volume,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "unrealized_pnl": self.unrealized_pnl,
            "currency": self.currency,
            "opened_utc": self.opened_utc,
            "raw_payload": self.raw_payload or {},
        }


def normalize_position_side(value: str | int | None) -> str:
    """
    Нормалізувати broker-specific direction у BUY/SELL/UNKNOWN.
    """

    text = str(value or "").strip().upper()

    if text in {"BUY", "LONG", "1"}:
        return POSITION_SIDE_BUY

    if text in {"SELL", "SHORT", "2"}:
        return POSITION_SIDE_SELL

    logger.debug("Unknown position side: %r", value)
    return POSITION_SIDE_UNKNOWN
