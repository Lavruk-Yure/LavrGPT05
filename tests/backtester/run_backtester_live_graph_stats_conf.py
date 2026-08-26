# run_backtester_live_graph_stats_conf.py
"""
run_backtester_live_graph_stats_conf.py

Запуск бек-тестера з конфігурованою SMA-стратегією
та графічним монітором статистики балансу.
"""

import os
import sys

from core import config_trades as conf
from core.backtester import Backtester
from core.risk_manager import RiskManager
from monitoring.monitor_live_graph_stats import LiveMonitorGraphStats
from strategies.strategy_sma import SMAStrategy

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # noqa: E402


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")

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
        data_file=str(data_file),
        strategy=strategy,
        risk_manager=rm,
    )

    monitor = LiveMonitorGraphStats(
        width=conf.GRAPH["width"],
        height=conf.GRAPH["height"],
    )

    data = bt.load_data()
    open_orders = []

    for i, candle in enumerate(data):
        price = candle["close"]
        closed_trades = []

        # Закриття ордерів через bars_to_close
        bars_to_close = conf.TRADES.get("close_after_bars", 3)
        for order in open_orders[:]:
            if i - order.get("open_index", 0) >= bars_to_close:
                bt.execution.close_order(order["id"], exit_price=price)
                closed_trades.append(order)
                open_orders.remove(order)

        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol=(
                    conf.TRADE_CONF["symbol"] if "symbol" in conf.TRADE_CONF else "TEST"
                ),
                side=side,
                price=price,
                stop_loss=sl,
                take_profit=tp,
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)

        # Додаємо profit, якщо відсутній
        for trade in closed_trades:
            if "profit" not in trade:
                direction = 1 if trade.get("side") in ("LONG", "BUY") else -1
                exit_price = trade.get("exit_price", price)
                open_price = trade.get("price") or trade.get("open_price") or 0
                trade["profit"] = (exit_price - open_price) * direction

        monitor.update(rm.balance, closed_trades)

    print(f"Final balance: {rm.balance}")


if __name__ == "__main__":
    main()
