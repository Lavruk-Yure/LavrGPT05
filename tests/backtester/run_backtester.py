# run_backtester.py
"""
run_backtester_2.py

Скрипт для запуску бек-тесту з Dummy-стратегією у LavrGPT05.
Виконує тестування з даними data/data.csv,
виводить кількість угод і фінальний баланс у консоль.
"""

import os

from core.backtester import Backtester
from core.risk_manager import RiskManager
from strategies.strategy_dummy import DummyStrategy


def main():
    # base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # data_file = os.path.join(base_dir, "data", "data.csv")
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    data_file = os.path.join(project_root, "data", "data.csv")

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    strategy = DummyStrategy()
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)

    trades = bt.run()

    print(f"Trades executed: {len(trades)}")
    print(f"Final balance: {rm.balance:.2f}")


if __name__ == "__main__":
    main()
