# runtime_account_state.py
"""
Runtime account state.

Це тимчасовий runtime-знімок торгового рахунку.
Не зберігається в LGE.conf.
Після reconnect може перебудовуватись заново.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RuntimeAccountState:
    """
    Runtime-знімок стану broker account.
    """

    account_id: str | None = None
    trader_login: str | None = None
    broker_name: str = ""

    currency: str = ""
    balance: Optional[float] = None
    equity: Optional[float] = None
    margin: Optional[float] = None
    free_margin: Optional[float] = None

    leverage: Optional[float] = None

    snapshot_utc: str = ""

    def is_loaded(self) -> bool:
        """
        Перевірити, чи account state має основний account_id.
        """
        return self.account_id is not None

    def clear(self) -> None:
        """
        Очистити runtime-знімок account state.
        """
        self.account_id = None
        self.trader_login = None
        self.broker_name = ""

        self.currency = ""
        self.balance = None
        self.equity = None
        self.margin = None
        self.free_margin = None

        self.leverage = None

        self.snapshot_utc = ""
