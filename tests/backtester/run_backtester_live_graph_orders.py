# run_backtester_live_graph_orders_pytest.py
"""
run_backtester_live_graph_orders.py

Запуск бек-тесту з SMA-стратегією та графічним монітором ордерів.
Виводить фінальний баланс та оновлює графік під час торгівлі.
"""

import os
import sys

from core import config_trades as conf
from core.backtester import Backtester
from core.risk_manager import RiskManager
from monitoring.monitor_live_graph_stats_orders import LiveMonitorGraphOrders
from strategies.strategy_sma import SMAStrategy

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # noqa: E402


def main():
    rm = RiskManager(
        balance=conf.RISK_MANAGER["balance"],
        risk_per_trade=conf.RISK_MANAGER["risk_per_trade"],
    )
    strategy = SMAStrategy(
        sma_fast=conf.STRATEGY["sma_fast"],
        sma_slow=conf.STRATEGY["sma_slow"],
        sl_coef=conf.STRATEGY["sl_coef"],
        rr_ratio=conf.STRATEGY["rr_ratio"],
    )

    bt = Backtester(
        data_file=conf.TRADE_CONF["data_file"],
        strategy=strategy,
        risk_manager=rm,
    )

    monitor = LiveMonitorGraphOrders(
        width=conf.GRAPH["width"],
        height=conf.GRAPH["height"],
    )

    data = bt.load_data()
    open_orders = []

    for i, candle in enumerate(data):
        price = candle["close"]
        closed_trades = []

        bars_to_close = conf.TRADES.get("close_after_bars", 3)

        for order in open_orders[:]:
            if i - order["open_index"] >= bars_to_close:
                bt.execution.close_order(order["id"], exit_price=price)

                # Обчислюємо прибуток, якщо можливо
                profit = 0.0
                if "profit" in order:
                    profit = order["profit"]
                elif "open_price" in order:
                    direction = 1 if order.get("side") == "BUY" else -1
                    profit = (price - order["open_price"]) * direction

                order["profit"] = profit
                closed_trades.append(order)
                open_orders.remove(order)

        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol="TEST",
                side=side,
                price=price,
                stop_loss=sl,
                take_profit=tp,
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)

        monitor.update(rm.balance, closed_trades, open_orders)

    # Вивід фінального балансу
    print(f"=== FINAL BALANCE: {rm.balance} ===")

    assert rm.balance > 0, "Баланс не повинен бути нульовим або від’ємним"


if __name__ == "__main__":
    main()
