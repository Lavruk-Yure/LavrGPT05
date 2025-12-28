# core\backtester.py

"""
Модуль Backtester реалізує клас для симуляції торгової стратегії на історичних даних.

Backtester:
- Завантажує цінові дані з CSV файлу.
- Виконує поетапний прогін даних, генерує торгові сигнали за допомогою
  переданої стратегії.
- Симулює відкриття і закриття ордерів через ExecutionEngine.
- Підраховує журнал усіх угод.
"""

import csv
from pathlib import Path

from core.execution import ExecutionEngine
from core.lang_manager import LangManager
from core.risk_manager import RiskManager

lang = LangManager()


class Backtester:
    def __init__(self, data_file: str, strategy, risk_manager: RiskManager):
        base_dir = Path(__file__).parent.resolve()
        self.data_file = base_dir.parent / "data" / data_file
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.execution = ExecutionEngine(risk_manager, mode="simulator")
        self.trades_log = []

    def load_data(self):
        """
        Завантаження історичних даних цін з CSV файлу.

        Повертає список словників з ключами:
        'time', 'open', 'high', 'low', 'close'
        """
        data = []
        with open(self.data_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(
                    {
                        "time": row["time"],
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    }
                )
        return data

    def run(self):
        """
        Запуск бек-тестування стратегії на завантажених даних.

        Логіка:
        - Ітерується по кожному бару (свічці).
        - Закриває відкриті ордери, якщо з моменту відкриття пройшло 3 бари.
        - Генерує торговий сигнал зі стратегії.
        - Відправляє ордер на виконання через ExecutionEngine.
        - Зберігає всі угоди в журналі.
        - В кінці закриває всі залишені відкриті ордери.

        Повертає список усіх угод (трейдів).
        """
        data = self.load_data()
        open_orders = []

        for i in range(len(data)):
            price = data[i]["close"]

            # Закриття ордерів через 3 бари після відкриття
            for order in open_orders[:]:
                if i - order["open_index"] >= 3:
                    self.execution.close_order(order["id"], exit_price=price)
                    open_orders.remove(order)

            # Генерація сигнала від стратегії
            signal = self.strategy.generate_signal(data[: i + 1])
            if signal:
                side, stop_loss, take_profit = signal

                # Посилання ордера на виконання
                ok, order = self.execution.submit_order(
                    symbol="TEST",
                    side=side,
                    price=price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
                if ok:
                    order["open_index"] = i  # зберігаємо індекс бару відкриття
                    open_orders.append(order)
                    self.trades_log.append(order)

        # Закриття всіх відкритих ордерів у кінці тесту
        for order in open_orders:
            self.execution.close_order(order["id"], exit_price=data[-1]["close"])
        open_orders.clear()

        return self.trades_log
