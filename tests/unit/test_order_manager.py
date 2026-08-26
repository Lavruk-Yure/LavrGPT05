# test_order_manager.py
"""
test_order_manager.py

Тестування OrderManager у режимах MANUAL, SEMI_AUTO, AUTO.
Перевіряємо коректність роботи place_order у кожному режимі.
Для режиму SEMI_AUTO мокамо input() для підтвердження.
"""

import pytest

from core.logger_monitor import setup_logger
from core.order_manager import OrderManager, OrderMode


@pytest.fixture(scope="module")
def logger():
    """Фікстура для налаштування логгера."""
    return setup_logger("OrderManagerTest", log_file="order_manager_test.log")


@pytest.fixture
def dummy_broker(logger):
    class DummyBroker:
        @staticmethod
        def send_order(symbol, side, volume, price, sl, tp):
            msg = (
                f"Відправлено ордер: {symbol} {side} {volume} "
                f"@ {price}, SL={sl}, TP={tp}"
            )
            logger.info(msg)
            return f"ORDER-{symbol}-{side}-{volume}"

    return DummyBroker()


@pytest.fixture
def dummy_analyzer(logger):
    class DummyAnalyzer:
        @staticmethod
        def analyze(symbol, side):
            analysis = f"Сигнал {side} по {symbol} базується на SMA."
            logger.info(f"Аналіз: {analysis}")
            return analysis

    return DummyAnalyzer()


@pytest.mark.parametrize(
    "mode, symbol, side, volume, price, sl, tp",
    [
        (OrderMode.MANUAL, "EURUSD", "BUY", 1.0, 1.12, 1.10, 1.15),
        (OrderMode.SEMI_AUTO, "EURUSD", "SELL", 2.0, 1.11, 1.09, 1.14),
        (OrderMode.AUTO, "EURUSD", "BUY", 0.5, 1.13, 1.11, 1.16),
    ],
)
def test_order_manager_modes(
    mode,
    symbol,
    side,
    volume,
    price,
    sl,
    tp,
    dummy_broker,
    dummy_analyzer,
    logger,
    monkeypatch,
):
    """Тестуємо place_order у різних режимах роботи OrderManager."""
    om = OrderManager(
        mode=mode, broker=dummy_broker, analyzer=dummy_analyzer, logger=logger
    )
    if mode == OrderMode.SEMI_AUTO:
        monkeypatch.setattr("builtins.input", lambda _: "y")
        result = om.place_order(symbol, side, volume, price=price, sl=sl, tp=tp)
    else:
        result = om.place_order(symbol, side, volume, price=price, sl=sl, tp=tp)

    if mode == OrderMode.MANUAL:
        assert result is None  # manual mode повертає None свідомо
    else:
        assert result is not None
