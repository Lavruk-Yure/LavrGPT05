# broker_account.py
"""
Канонічна модель broker account для LGE runtime.

Модуль не залежить від:
- Qt
- SQLite
- конкретного broker API
"""

from dataclasses import dataclass


@dataclass(slots=True)
class BrokerAccount:
    """
    Нормалізована інформація про broker account.
    """

    broker: str
    account_id: str
    account_mode: str
    currency: str = ""
    balance: float = 0.0
    equity: float = 0.0
    margin_used: float = 0.0
    margin_free: float = 0.0
    raw_payload: dict | None = None

    def to_dict(self) -> dict:
        """
        Перетворити BrokerAccount у dict.
        """

        return {
            "broker": self.broker,
            "account_id": self.account_id,
            "account_mode": self.account_mode,
            "currency": self.currency,
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self.margin_used,
            "margin_free": self.margin_free,
            "raw_payload": self.raw_payload or {},
        }
