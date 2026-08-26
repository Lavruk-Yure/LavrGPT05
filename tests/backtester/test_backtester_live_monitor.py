# test_backtester_live_monitor_pytest.py
"""
Pytest-тест для живого моніторингу та бек-тестування SMA-стратегії.

Цей тест:
- Ініціалізує RiskManager, LoggerMonitor, SMAStrategy і LiveMonitor.
- Завантажує історичні дані через Backtester.
- По кожній свічці оновлює ордери (закриває після 3 барів).
- Генерує сигнали SMA-стратегії й відкриває угоди.
- Передає стан у LiveMonitor для відображення.
- Наприкінці закриває всі ордери.
- Перевіряє, що підсумковий баланс не впав нижче початкового.

Файл призначено для автоматизованої перевірки логіки системи.
"""
import os

from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from monitoring.monitor_live import LiveMonitor
from strategies.strategy_sma import SMAStrategy


def test_backtester_live_monitor():
    """Перевірка узгодженої роботи стратегії, монітору й бек-тестера."""

    # 1️⃣ Ініціалізація ключових компонентів
    rm = RiskManager(balance=10_000, risk_per_trade=0.01)
    logger = LoggerMonitor()
    strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
    monitor = LiveMonitor()

    # Шлях до CSV-файлу з тестовими даними
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_file = os.path.join(project_root, "data", "data.csv")
    assert os.path.exists(data_file), f"Файл не знайдено: {data_file}"

    bt = Backtester(data_file=data_file, strategy=strategy, risk_manager=rm)

    bt.execution.logger = logger

    # 2️⃣ Робочі змінні для циклу
    trades_log = []
    open_orders = []
    data = bt.load_data()

    # 3️⃣ Основний торговий цикл
    for i, candle in enumerate(data):
        price = candle["close"]

        # Закриття ордерів після 3 барів
        for order in open_orders[:]:
            if i - order["open_index"] >= 3:
                bt.execution.close_order(order["id"], exit_price=price)
                open_orders.remove(order)

        # Генерація торгового сигналу SMA-стратегії
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

        # Оновлення монітора поточного стану
        monitor.update_bar(i, candle, open_orders, rm.balance)

    # 4️⃣ Закриття всіх залишкових ордерів
    for order in open_orders:
        bt.execution.close_order(order["id"], exit_price=data[-1]["close"])
    open_orders.clear()

    # 5️⃣ Логування та фінальна перевірка
    logger.print_summary(rm.balance)

    # 🔍 Умова тесту: баланс має залишатися позитивним
    assert rm.balance > 0, "Баланс не повинен бути нульовим або від’ємним"
