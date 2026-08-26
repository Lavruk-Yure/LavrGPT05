# run_backtester_live_graph_stats_matplotlib.py
"""
run_backtester_live_graph_stats_matplotlib.py

Запуск бек-тестера з SMA-стратегією та графічним монітором з matplotlib,
показує графік статистики балансу.
"""

# import os
from pathlib import Path

# import matplotlib
import matplotlib.pyplot as plt

from core import config_trades as conf
from core.backtester import Backtester
from core.config_trades import GRAPH, TRADES
from core.risk_manager import RiskManager
from monitoring.monitor_live_graph_matplotlib import LiveMonitorGraphMatplotlib
from strategies.strategy_sma import SMAStrategy

# Встановлюємо backend для безголового рендерингу
# matplotlib.use("Agg")


def main():
    base_dir = (
        Path(__file__).resolve().parent.parent.parent
    )  # один рівень вище кореня tests
    data_file = base_dir / "data" / "data.csv"

    rm = RiskManager(balance=TRADES["balance"], risk_per_trade=TRADES["risk_per_trade"])

    strategy = SMAStrategy(
        sma_fast=TRADES["sma_fast"],
        sma_slow=TRADES["sma_slow"],
        sl_coef=TRADES["sl_coef"],
        rr_ratio=TRADES["rr_ratio"],
    )

    bt = Backtester(data_file=str(data_file), strategy=strategy, risk_manager=rm)
    monitor = LiveMonitorGraphMatplotlib(**GRAPH)

    data = bt.load_data()
    open_orders = []

    #    plt.ioff()  # Вимикаємо інтерактивний режим

    for i, candle in enumerate(data):
        price = candle["close"]
        closed_trades = []

        # Закриття ордерів через задану кількість барів
        for order in open_orders[:]:
            if i - order.get("open_index", 0) >= TRADES["close_after_bars"]:
                bt.execution.close_order(order["id"], exit_price=price)
                if "profit" not in order:
                    direction = 1 if order.get("side") == "LONG" else -1
                    order["profit"] = (
                        price - order.get("open_price", price)
                    ) * direction
                closed_trades.append(order)
                open_orders.remove(order)

        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol=(
                    str(conf.TRADE_CONF["symbol"])
                    if "symbol" in conf.TRADE_CONF
                    else "TEST"
                ),
                side=side,
                price=price,
                stop_loss=sl,
                take_profit=tp,
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)

        monitor.update(rm.balance)

    print(f"Фінальний баланс: {rm.balance}")
    plt.show()
    # Зберігаємо графік у файл
    monitor.fig.savefig("backtest_live_graph.png")
    plt.close(monitor.fig)


if __name__ == "__main__":
    main()
