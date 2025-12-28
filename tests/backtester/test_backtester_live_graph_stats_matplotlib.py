#  test_backtester_live_graph_stats_matplotlib.py
"""
test_backtester_live_graph_stats_matplotlib.py

Pytest-тест бек-тестера з SMA-стратегією та графічним монітором,
використовує matplotlib і pytest-mpl для порівняння графіки.
"""

# import os

import matplotlib  # noqa

matplotlib.use("Agg")  # noqa


from pathlib import Path  # noqa

import matplotlib.pyplot as plt  # noqa
import pytest  # noqa

from core import config_trades as conf  # noqa
from core.backtester import Backtester  # noqa
from core.config_trades import GRAPH, TRADES  # noqa
from core.risk_manager import RiskManager  # noqa
from monitoring.monitor_live_graph_matplotlib import LiveMonitorGraphMatplotlib  # noqa
from strategies.strategy_sma import SMAStrategy  # noqa

# # Встановлюємо backend ПЕРЕД імпортом pyplot
# matplotlib.use("Agg")


# @pytest.fixture(scope="module")
# def backtester_setup():
#     """
#     Фікстура для ініціалізації бек-тестера, монітора та стратегії.
#     """


@pytest.fixture(scope="module")
def backtester_setup():
    """
    Фікстура для ініціалізації бек-тестера, монітора та стратегії
    з правильним шляхом до data.csv.
    """
    base_dir = (
        Path(__file__).resolve().parent.parent.parent
    )  # Три рівні вгору від tests/backtester
    data_file = base_dir / "data" / "data.csv"

    if not data_file.exists():
        pytest.skip(f"Вхідний файл даних не знайдено: {data_file}")

    rm = RiskManager(balance=TRADES["balance"], risk_per_trade=TRADES["risk_per_trade"])

    strategy = SMAStrategy(
        sma_fast=TRADES["sma_fast"],
        sma_slow=TRADES["sma_slow"],
        sl_coef=TRADES["sl_coef"],
        rr_ratio=TRADES["rr_ratio"],
    )

    bt = Backtester(data_file=str(data_file), strategy=strategy, risk_manager=rm)
    monitor = LiveMonitorGraphMatplotlib(**GRAPH)

    return bt, rm, strategy, monitor


def matplotlib_setup():
    matplotlib.use("Agg")
    yield


@pytest.mark.mpl_image_compare
def test_live_graph_matplotlib_with_pytest_mpl(backtester_setup):
    """
    Тестовий сценарій із matplotlib, порівняння з базовим зображенням.
    """
    bt, rm, strategy, monitor = backtester_setup
    data = bt.load_data()
    open_orders = []

    plt.ioff()  # Вимикаємо інтерактивний режим matplotlib для тестів

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

        # Генерація сигнала
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

    # Перевірка фінального балансу (має бути позитивний)
    assert rm.balance > 0, "Фінальний баланс має бути більшим за 0"

    # Повертаємо об'єкт matplotlib figure для pytest-mpl
    return monitor.fig
