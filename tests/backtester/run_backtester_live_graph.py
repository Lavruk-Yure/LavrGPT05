# run_backtester_live_graph.py
"""
run_backtester_live_graph.py

Скрипт для запуску бек-тесту з SMA-стратегією та графічним монітором.
Виводить графік балансу у вигляді ASCII-графіки.
"""

import os

from core.backtester import Backtester
from core.risk_manager import RiskManager
from monitoring.monitor_live_graph import LiveMonitorGraph
from strategies.strategy_sma import SMAStrategy


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")

    rm = RiskManager(balance=10000, risk_per_trade=0.01)
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    graph = LiveMonitorGraph(width=50, height=10)

    data = bt.load_data()
    open_orders = []

    for i, candle in enumerate(data):
        price = candle["close"]

        # Закриття ордерів через 3 бари
        for order in open_orders[:]:
            if i - order["open_index"] >= 3:
                bt.execution.close_order(order["id"], exit_price=price)
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

        graph.update(rm.balance)


if __name__ == "__main__":
    main()
