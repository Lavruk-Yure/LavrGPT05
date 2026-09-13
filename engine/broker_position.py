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
from datetime import UTC, datetime, timedelta

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


@dataclass(frozen=True, slots=True)
class BrokerPositionSnapshot:
    """Broker-neutral snapshot результату position request."""

    broker: str
    account_id: str
    success: bool
    observed_at_utc: datetime
    positions: tuple[BrokerPosition, ...]
    failure_reason: str = ""

    @classmethod
    def success_result(
        cls,
        broker: str,
        account_id: str,
        positions: list[BrokerPosition],
    ) -> "BrokerPositionSnapshot":
        """Побудувати успішний snapshot у момент terminal outcome."""

        return cls(
            broker=str(broker).strip().upper(),
            account_id=str(account_id).strip(),
            success=True,
            observed_at_utc=datetime.now(UTC),
            positions=tuple(positions),
        )

    @classmethod
    def failure_result(
        cls,
        broker: str,
        account_id: str,
        failure_reason: str,
    ) -> "BrokerPositionSnapshot":
        """Побудувати failure snapshot у момент terminal outcome."""

        return cls(
            broker=str(broker).strip().upper(),
            account_id=str(account_id).strip(),
            success=False,
            observed_at_utc=datetime.now(UTC),
            positions=(),
            failure_reason=str(failure_reason).strip(),
        )



def _normalize_position_symbol(value: str) -> str:
    """Нормалізувати symbol для broker-neutral position scope."""

    return str(value or "").strip().upper().replace("/", "").replace(".", "")


def broker_position_snapshot_confirms_flat(
    snapshot: BrokerPositionSnapshot,
    *,
    broker: str,
    account_id: str,
    symbol: str,
    now_utc: datetime,
    max_age: timedelta,
) -> bool:
    """Перевірити broker-confirmed flat exposure для exact account/symbol.

    Функція fail-closed: failure, stale/future snapshot, scope mismatch,
    naive timestamps або matching open exposure повертають False. Freshness
    policy передається параметром і не є універсальною production-константою.
    """

    if not snapshot.success or max_age <= timedelta(0):
        return False
    if snapshot.observed_at_utc.tzinfo is None or now_utc.tzinfo is None:
        return False

    broker_norm = str(broker or "").strip().upper()
    account_norm = str(account_id or "").strip().upper()
    symbol_norm = _normalize_position_symbol(symbol)
    if not broker_norm or not account_norm or not symbol_norm:
        return False

    if snapshot.broker.strip().upper() != broker_norm:
        return False
    if snapshot.account_id.strip().upper() != account_norm:
        return False

    age = now_utc.astimezone(UTC) - snapshot.observed_at_utc.astimezone(UTC)
    if age < timedelta(0) or age > max_age:
        return False

    for position in snapshot.positions:
        if str(position.broker).strip().upper() != broker_norm:
            continue
        if str(position.account_id).strip().upper() != account_norm:
            continue
        if _normalize_position_symbol(position.symbol_name) != symbol_norm:
            continue
        if abs(float(position.volume)) > 0.0:
            return False

    return True

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
