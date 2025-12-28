# test_backtester.py
"""
test_backtester_2.py

Тест бек-тестера з Dummy-стратегією для LavrGPT05.

Перевіряє базове виконання бек-тесту, повернення угод
та оновлення фінального балансу.
"""

import os

import pytest

from core.backtester import Backtester
from core.risk_manager import RiskManager
from strategies.strategy_dummy import DummyStrategy


@pytest.fixture(scope="module")
def backtester_setup():
    """
    Ініціалізація RiskManager, DummyStrategy та Backtester з тестовим файлом.
    """
    # base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # data_file = os.path.join(base_dir, "data", "data.csv")
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    data_file = os.path.join(project_root, "data", "data.csv")

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    strategy = DummyStrategy()
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    return bt, rm


def test_backtester_dummy_strategy(backtester_setup):
    """
    Запускає бек-тест з Dummy стратегією,
    перевіряє, що повертається список угод і баланс оновлюється.
    """
    bt, rm = backtester_setup
    trades = bt.run()

    assert isinstance(trades, list), "Backtester повинен повертати список угод"
    assert isinstance(rm.balance, (float, int)), "Баланс повинен бути числом"
    assert rm.balance >= 0, "Баланс не повинен бути від'ємним"

    # Вивід для налагодження (опціонально)
    print(f"Trades executed: {len(trades)}")
    print(f"Final balance: {rm.balance:.2f}")
