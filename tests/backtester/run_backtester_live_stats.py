# run_backtester_live_stats.py
"""
run_backtester_live_stats.py

Скрипт для запуску бек-тесту зі SMA стратегією та статистичним монітором.
Імітує торгівлю, збирає статистику, виводить підсумки на екран.
"""

import os

from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from monitoring.monitor_live_stats import LiveMonitorStats
from strategies.strategy_sma import SMAStrategy


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    logger = LoggerMonitor()
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    monitor = LiveMonitorStats(refresh_delay=0.3)

    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    bt.execution.logger = logger

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

        # Генерація сигналу
        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol="TEST", side=side, price=price, stop_loss=sl, take_profit=tp
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)

        monitor.update_bar(i, candle, open_orders, rm.balance, closed_trades)

    # Закриття усіх відкритих ордерів наприкінці
    for order in open_orders:
        bt.execution.close_order(order["id"], exit_price=data[-1]["close"])
        order["exit_price"] = data[-1]["close"]
        closed_trades.append(order)
    open_orders.clear()

    logger.print_summary(rm.balance)


if __name__ == "__main__":
    main()
