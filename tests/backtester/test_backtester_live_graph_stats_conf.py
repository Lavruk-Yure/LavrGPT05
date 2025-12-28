# test_backtester_live_graph_stats_conf.py
"""
test_backtester_live_graph_stats.py

Pytest-тест для перевірки бек-тестера з SMA-стратегією
та графічним монітором статистики балансу.
"""

import os

import pytest

from core.backtester import Backtester
from core.risk_manager import RiskManager
from monitoring.monitor_live_graph_stats import LiveMonitorGraphStats
from strategies.strategy_sma import SMAStrategy


@pytest.fixture(scope="module")
def backtester_setup():
    """
    Ініціалізація RiskManager, SMA-стратегії, Backtester і монітора.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")
    assert os.path.exists(data_file), f"Файл не знайдено: {data_file}"

    rm = RiskManager(balance=10000, risk_per_trade=0.01)
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    monitor = LiveMonitorGraphStats(width=50, height=10)

    return bt, rm, monitor, strategy


def test_live_graph_stats_backtester(backtester_setup):
    """
    Тест імітує торгівлю з відкриттям і закриттям ордерів,
    оновлює графічний монітор статистики,
    перевіряє коректність фінального балансу.
    """
    bt, rm, monitor, strategy = backtester_setup
    data = bt.load_data()
    open_orders = []

    for i, candle in enumerate(data):
        price = candle["close"]
        closed_trades = []

        # Закриття ордерів через 3 бари
        for order in open_orders[:]:
            if i - order.get("open_index", 0) >= 3:
                bt.execution.close_order(order["id"], exit_price=price)
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

        # Запевняємось, що у кожної закритої угоди є profit для монітора
        for trade in closed_trades:
            if "profit" not in trade:
                direction = 1 if trade.get("side") in ("LONG", "BUY") else -1
                exit_price = trade.get("exit_price", price)
                open_price = trade.get("price") or trade.get("open_price") or 0
                trade["profit"] = (exit_price - open_price) * direction

        monitor.update(rm.balance, closed_trades)

    # Перевірка фінального балансу, має бути додатним числом
    assert isinstance(rm.balance, (float, int)), "Баланс повинен бути числом"
    assert rm.balance > 0, "Фінальний баланс має бути більшим за 0"
