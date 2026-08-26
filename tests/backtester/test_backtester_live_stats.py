# test_backtester_live_stats.py
"""
test_backtester_live_stats.py

Тест бек-тестера з SMA-стратегією та статистичним монітором.
Перевіряє закриття ордерів, генерацію сигналів,
оновлення статистики та вивід підсумків.
"""

import os

import pytest

from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from monitoring.monitor_live_stats import LiveMonitorStats
from strategies.strategy_sma import SMAStrategy


@pytest.fixture(scope="module")
def backtester_setup():
    """
    Ініціалізація RiskManager, LoggerMonitor, SMA-стратегії, LiveMonitorStats та
    Backtester.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")
    assert os.path.exists(data_file), f"Файл не знайдено: {data_file}"

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    logger = LoggerMonitor()
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    monitor = LiveMonitorStats(refresh_delay=0.3)
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    bt.execution.logger = logger

    return bt, rm, logger, monitor, strategy


def test_live_stats_backtester(backtester_setup):
    """
    Запускає бек-тестер з SMA стратегією,
    контролює відкриття і закриття ордерів,
    оновлює статистичний монітор,
    завершує сесію закриттям угод,
    підсумовує і перевіряє результати.
    """
    bt, rm, logger, monitor, strategy = backtester_setup
    data = bt.load_data()
    open_orders = []
    closed_trades = []

    for i, candle in enumerate(data):
        price = candle["close"]

        # Закриття ордерів через 3 бари
        for order in open_orders[:]:
            if i - order["open_index"] >= 3:
                bt.execution.close_order(order["id"], exit_price=price)
                order["exit_price"] = price
                closed_trades.append(order)
                open_orders.remove(order)

        # Генерація торгового сигналу
        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol="TEST", side=side, price=price, stop_loss=sl, take_profit=tp
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)

        # Оновлення статистичного монітора
        monitor.update_bar(i, candle, open_orders, rm.balance, closed_trades)

    # Закриття усіх відкритих ордерів наприкінці сесії
    for order in open_orders:
        bt.execution.close_order(order["id"], exit_price=data[-1]["close"])
        order["exit_price"] = data[-1]["close"]
        closed_trades.append(order)
    open_orders.clear()

    logger.print_summary(rm.balance)

    # Базові перевірки
    assert isinstance(rm.balance, (float, int)), "Баланс має бути числом"
    assert rm.balance > 0, "Фінальний баланс має бути більшим за 0"
