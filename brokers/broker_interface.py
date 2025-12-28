# interfaces/broker_interface.py
"""Інтерфейс BrokerInterface визначає контракт для взаємодії
з будь-яким брокером (cTrader, IBKR, тестовим тощо).

Кожен конкретний адаптер брокера повинен реалізовувати ці методи.
"""

from abc import ABC, abstractmethod
from typing import Any


class BrokerInterface(ABC):
    """Базовий інтерфейс для брокерських адаптерів."""

    @abstractmethod
    def send_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Any:
        """Відправити торговий ордер."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: Any) -> None:
        """Скасувати ордер за його ідентифікатором."""
        raise NotImplementedError

    @abstractmethod
    def get_balance(self) -> float:
        """Отримати баланс рахунку."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Отримати список відкритих позицій."""
        raise NotImplementedError
