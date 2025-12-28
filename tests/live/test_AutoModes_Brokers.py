# test_AutoModes_Brokers.py
# 25.10.2025
# Pytest для AUTO-режимів OrderManager із моками
# брокерських адаптерів (IB, cTrader, Dummy).

import asyncio
import socket
from unittest.mock import MagicMock

import pytest

from brokers.ctrader_adapter import CTraderAdapter
from brokers.ib_adapter import IBAdapter
from core.logger_monitor import setup_logger
from core.order_manager import OrderManager, OrderMode


class DummyBroker:
    """Заглушка брокера для тестів без мережі."""

    def __init__(self, logger_obj=None):
        self.logger = logger_obj

    def send_order(self, symbol, side, volume, price=None, sl=None, tp=None, **_):
        """Імітація відправлення ордера."""
        if self.logger:
            self.logger.info(
                f"Dummy ордер: {symbol} {side} {volume} @ {price}, SL={sl}, TP={tp}"
            )
        return f"DUMMY-{symbol}-{side}-{volume}"


@pytest.fixture(scope="module")
def logger():
    """Фікстура для створення логера."""
    return setup_logger("LavrGPT05_Test", log_file="pytest_auto_modes.log")


def is_port_open(host: str, port: int) -> bool:
    """Перевіряє, чи відкритий TCP порт."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.parametrize(
    "adapter_class, symbol, side, volume, price, sl, tp",
    [
        (IBAdapter, "EURUSD", "BUY", 1.0, 1.12, 1.10, 1.15),
        (CTraderAdapter, "EURUSD", "SELL", 2.0, 1.11, 1.09, 1.14),
        (DummyBroker, "EURUSD", "BUY", 0.5, 1.13, 1.11, 1.16),
    ],
)
def test_order_manager_auto_modes(
    adapter_class, symbol, side, volume, price, sl, tp, logger
):
    """Перевіряє OrderManager в AUTO-режимі з різними брокерськими адаптерами."""

    if adapter_class is DummyBroker:
        broker = DummyBroker(logger_obj=logger)

    elif adapter_class is CTraderAdapter:
        broker = CTraderAdapter(api_token="TEST_TOKEN", logger=logger)
        broker.send_order = MagicMock(return_value="ORDER-CT-MOCK")

    else:  # IBAdapter
        try:
            broker = IBAdapter(logger=logger)
            broker.send_order = MagicMock(return_value="ORDER-IB-MOCK")
        except (asyncio.TimeoutError, TimeoutError, OSError) as e:
            pytest.skip(f"⏭ Пропущено: не вдалося підключитись до IB Gateway ({e})")

    om = OrderManager(mode=OrderMode.AUTO, broker=broker, logger=logger)
    order_id = om.place_order(symbol, side, volume, price=price, sl=sl, tp=tp)

    assert order_id is not None, "OrderManager не повернув order_id"
    assert isinstance(order_id, str), "Order ID повинен бути рядком"

    if hasattr(broker.send_order, "assert_called_once"):
        broker.send_order.assert_called_once()
