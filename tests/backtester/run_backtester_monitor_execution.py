# run_backtester_monitor_execution.py
"""
Модуль run_backtester_monitor_execution.py

Цей скрипт виконує запуск бек-тестера торгової стратегії з використанням
ExecutionEngine для моделювання торгів у режимі симулятора, а також
ведення журналу операцій і управління ризиками.

Основні кроки:
1. Ініціалізує RiskManager з початковим балансом та ризиком на угоду.
2. Ініціалізує LoggerMonitor для логування торгів.
3. Створює екземпляр SMAStrategy з параметрами швидких та повільних SMA,
   коефіцієнтом SL та співвідношенням ризик/винагорода.
4. Ініціалізує Backtester з файлом історичних даних, стратегією та менеджером ризиків.
5. Встановлює ExecutionEngine у бек-тестер у режимі "simulator" з логером і
   менеджером ризиків.
6. Запускає бек-тест для отримання списку торгів.
7. Виводить підсумок по балансу через LoggerMonitor.
"""

from core.backtester import Backtester
from core.execution import ExecutionEngine
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from strategies.strategy_sma import SMAStrategy

rm = RiskManager(balance=10_000, risk_per_trade=0.01)
logger = LoggerMonitor()
strategy = SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)

bt = Backtester(data_file="data.csv", strategy=strategy, risk_manager=rm)
bt.execution = ExecutionEngine(risk_manager=rm, mode="simulator", logger=logger)

trades = bt.run()
logger.print_summary(rm.balance)
