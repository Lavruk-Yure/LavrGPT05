# broker_interface.py
"""
Канонічний broker interface для LGE runtime.

Модуль визначає єдиний API для:
- IB
- cTrader
- future broker adapters

UI і RuntimeEngine повинні працювати
через цей interface, а не напряму
через broker-specific API.
"""

from abc import ABC, abstractmethod

from engine.broker_account import BrokerAccount
from engine.broker_position import BrokerPosition


class BrokerInterface(ABC):
    """
    Базовий broker interface.
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Підключитися до broker.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """
        Відключитися від broker.
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Перевірити стан підключення.
        """

    @abstractmethod
    def get_account_info(self) -> BrokerAccount:
        """
        Отримати інформацію про account.
        """

    def get_positions(self) -> list[BrokerPosition]:
        """
        Отримати відкриті broker positions у canonical форматі.
        """

        raise NotImplementedError
