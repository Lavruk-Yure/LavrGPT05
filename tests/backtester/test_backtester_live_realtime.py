# test_backtester_live_realtime.py
"""
test_backtester_live_realtime.py

Тест бек-тестера з SMA-стратегією і монітором у режимі реального часу.
Перевіряє логіку відкриття/закриття ордерів, оновлення монітора і вивід статистики.
"""

import os

import pytest

from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from monitoring.monitor_live_realtime import LiveMonitorRealtime
from strategies.strategy_sma import SMAStrategy


@pytest.fixture(scope="module")
def backtester_setup():
    """
    Ініціалізація RiskManager, LoggerMonitor, SMAStrategy, LiveMonitorRealtime та
    Backtester.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")
    assert os.path.exists(data_file), f"Файл не знайдено: {data_file}"

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    logger = LoggerMonitor()
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    monitor = LiveMonitorRealtime(refresh_delay=0.3)
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    bt.execution.logger = logger

    return bt, rm, logger, monitor, strategy


def test_live_realtime_backtester(backtester_setup):
    """
    Запускає бек-тестер зі SMA стратегією,
    імітує торгівлю з генерацією сигналів,
    закриває ордери через 3 бари,
    оновлює монітор у реальному часі,
    підсумовує результати через логер і виконує базові перевірки.
    """
    bt, rm, logger, monitor, strategy = backtester_setup
    data = bt.load_data()
    open_orders = []

    for i, candle in enumerate(data):
        price = candle["close"]

        # Закриття ордерів через 3 бари
        for order in open_orders[:]:
            if i - order["open_index"] >= 3:
                bt.execution.close_order(order["id"], exit_price=price)
                open_orders.remove(order)

        # Генерація торгового сигналу SMA стратегії
        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol="TEST", side=side, price=price, stop_loss=sl, take_profit=tp
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)

        # Оновлення монітора в режимі реального часу
        monitor.update_bar(i, candle, open_orders, rm.balance)

    # Закриття всіх відкритих ордерів в кінці сесії
    for order in open_orders:
        bt.execution.close_order(order["id"], exit_price=data[-1]["close"])
    open_orders.clear()

    logger.print_summary(rm.balance)

    # Базові перевірки
    assert isinstance(rm.balance, (float, int)), "Баланс має бути числом"
    assert rm.balance > 0, "Фінальний баланс має бути більшим за 0"
