# run_backtester_sma.py
"""
run_backtester_sma.py

Скрипт для запуску бек-тесту з SMA-стратегією у проєкті LavrGPT05.
Виконує тестування з даними з файлу data/test_backtester_sma_data.csv,
виводить угоди та фінальний баланс у консоль.
"""

import os

from core.backtester import Backtester
from core.risk_manager import RiskManager
from strategies.strategy_sma import SMAStrategy


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "test_backtester_sma_data.csv")
    assert os.path.exists(data_file), f"Файл не знайдено: {data_file}"

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)

    trades = bt.run()

    print(f"Trades executed: {len(trades)}")
    for t in trades:
        print(
            f"{t['side']} | entry={t['price']} | SL={t['stop_loss']:.2f} |"
            f"TP={t['take_profit']:.2f} | status={t['status']}"
        )
    print(f"Final balance: {rm.balance:.2f}")


if __name__ == "__main__":
    main()
