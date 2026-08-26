# run_backtester_monitor.py
"""
Модуль run_backtester_monitor.py

Цей скрипт виконує тестування торгової стратегії з використанням
Backtester, а також моніторинг торгових операцій із веденням журналу
та керуванням ризиками.

Основні кроки:
1. Ініціалізація RiskManager з балансом та ризиком на торгівлю.
2. Ініціалізація торгової стратегії SMAStrategy з параметрами.
3. Створення Backtester з файлом даних, стратегічним об'єктом та менеджером ризиків.
4. Ініціалізація LoggerMonitor для ведення логів.
5. Запуск бек тесту для отримання торгів.
6. Логування торгів та вивід підсумкового балансу.

"""

from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from strategies.strategy_sma import SMAStrategy

rm = RiskManager(balance=10_000, risk_per_trade=0.01)
strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)
bt = Backtester(data_file="data.csv", strategy=strategy, risk_manager=rm)

logger = LoggerMonitor()

trades = bt.run()

for t in trades:
    logger.log_trade(t, rm.balance)

logger.print_summary(rm.balance)
