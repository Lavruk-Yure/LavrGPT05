# run_backtester_live_monitor.py
"""
Скрипт для живого моніторингу та бек-тестування SMA-стратегії.

Призначення:
- Ініціалізує RiskManager, LoggerMonitor, SMAStrategy і LiveMonitor.
- Завантажує історичні дані через Backtester.
- По кожній свічці оновлює ордери (закриває після 3 барів).
- Генерує сигнали SMA-стратегії та відкриває угоди.
- Передає стан у LiveMonitor для відображення.
- Наприкінці закриває всі ордери.
- Виводить фінальний баланс через LoggerMonitor.

Цей файл виконується напряму через Python (не pytest).
"""

import os

from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from monitoring.monitor_live import LiveMonitor
from strategies.strategy_sma import SMAStrategy

# import sys


# # Додаємо корінь проєкту до системного шляху
# sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def main():
    """Основна логіка запуску бек-тесту."""

    # 1️⃣ Ініціалізація компонентів
    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    logger = LoggerMonitor()
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    monitor = LiveMonitor()

    # Шлях до CSV із тестовими даними
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")

    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)
    bt.execution.logger = logger

    trades_log = []
    open_orders = []
    data = bt.load_data()

    # 2️⃣ Основний цикл по свічках
    for i, candle in enumerate(data):
        price = candle["close"]

        # Закриваємо ордери через 3 бари після відкриття
        for order in open_orders[:]:
            if i - order["open_index"] >= 3:
                bt.execution.close_order(order["id"], exit_price=price)
                open_orders.remove(order)

        # Генеруємо сигнал SMA
        signal = strategy.generate_signal(data[: i + 1])
        if signal:
            side, sl, tp = signal
            ok, order = bt.execution.submit_order(
                symbol="TEST", side=side, price=price, stop_loss=sl, take_profit=tp
            )
            if ok:
                order["open_index"] = i
                open_orders.append(order)
                trades_log.append(order)

        # Оновлюємо монітор
        monitor.update_bar(i, candle, open_orders, rm.balance)

    # 3️⃣ Закриваємо решту ордерів наприкінці
    for order in open_orders:
        bt.execution.close_order(order["id"], exit_price=data[-1]["close"])
    open_orders.clear()

    # 4️⃣ Фінальний звіт
    logger.print_summary(rm.balance)


if __name__ == "__main__":
    main()
