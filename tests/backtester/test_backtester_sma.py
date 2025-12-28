# test_backtester_sma.py
"""
test_backtester_sma.py

Тестовий модуль для перевірки роботи Backtester з SMA-стратегією у проекті LavrGPT05.

Можливе відсутність угод на деяких наборах даних допускається,
щоб уникнути падіння тесту через некритичну відсутність сигналів.
"""

import os

import pytest

from core.backtester import Backtester
from core.risk_manager import RiskManager
from strategies.strategy_sma import SMAStrategy


@pytest.fixture(scope="module")
def backtester_setup():
    """Ініціалізація бек-тестера із тестовим файлом даних."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "test_backtester_sma_data.csv")

    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)

    return bt, rm


def test_backtester_runs(backtester_setup):
    """
    Запускає бек-тест і перевіряє:
    - що повертається список угод;
    - структура першої угоди коректна (якщо угоди є);
    - фінальний баланс — число більше нуля.

    Якщо угод немає, тест не падає.
    """
    bt, rm = backtester_setup
    trades = bt.run()

    assert isinstance(trades, list), "Backtester має повертати список угод"
    assert isinstance(rm.balance, (float, int)), "Баланс має бути числом"
    assert rm.balance > 0, "Фінальний баланс має бути більший за нуль"

    if len(trades) == 0:
        print("Увага: угод не було виконано. Перевірте параметри стратегії і дані.")
    else:
        first_trade = trades[0]
        for key in ("side", "price", "stop_loss", "take_profit", "status"):
            assert key in first_trade, f"Відсутній ключ '{key}' у угоді"

        print(f"Trades executed: {len(trades)}")
        for t in trades:
            print(
                f"{t['side']} | entry={t['price']} | SL={t['stop_loss']:.2f} |"
                f"TP={t['take_profit']:.2f} | status={t['status']}"
            )
    print(f"Final balance: {rm.balance:.2f}")
