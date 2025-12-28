# brokers/broker_adapter.py
"""Базовий клас BrokerAdapter для реалізації адаптерів брокерів
(наприклад, Interactive Brokers, cTrader тощо).
Усі похідні класи повинні реалізовувати однаковий інтерфейс.
"""

from abc import ABC, abstractmethod
from typing import Any


class BrokerAdapter(ABC):
    """Абстрактний базовий клас для брокерських адаптерів."""

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
        """Відправлення торгового ордера."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: Any) -> None:
        """Скасування торгового ордера."""
        raise NotImplementedError

    @abstractmethod
    def get_balance(self) -> float:
        """Отримати баланс торгового рахунку."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Отримати список відкритих позицій."""
        raise NotImplementedError
