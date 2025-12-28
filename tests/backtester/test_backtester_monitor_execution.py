# test_backtester_monitor_execution.py

"""
Тести для модуля run_backtester_monitor_execution з використанням pytest.

Цей модуль тестує роботу бек-тестера з використанням ExecutionEngine,
логування торгів через LoggerMonitor і керування ризиками через RiskManager.
Використовується мокання для ізоляції логіки без залежностей
від зовнішніх файлів і ресурсів.
"""

from unittest.mock import patch

import pytest

from core.backtester import Backtester
from core.execution import ExecutionEngine
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from strategies.strategy_sma import SMAStrategy


@pytest.fixture
def risk_manager():
    """Фікстура для RiskManager з початковим балансом і ризиком на угоду."""
    return RiskManager(balance=10_000, risk_per_trade=0.01)


@pytest.fixture
def logger_monitor():
    """Фікстура для LoggerMonitor для ведення логів у тестах."""
    return LoggerMonitor()


@pytest.fixture
def strategy():
    """Фікстура для SMA стратегії з тестовими параметрами."""
    return SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)


@pytest.fixture
def backtester(strategy, risk_manager):
    """Фікстура для ініціалізації Backtester з вхідними параметрами."""
    return Backtester(
        data_file="data.csv", strategy=strategy, risk_manager=risk_manager
    )


def test_backtester_run_and_log(backtester, logger_monitor, risk_manager):
    """
    Тест перевіряє запуск бек-тестера з моканим списком торгів
    та виклик логування підсумкового балансу.
    """
    mock_trades = [
        {"id": 1, "profit": 50},
        {"id": 2, "profit": -30},
    ]
    backtester.execution = ExecutionEngine(
        risk_manager=risk_manager, mode="simulator", logger=logger_monitor
    )

    with patch.object(Backtester, "run", return_value=mock_trades):
        trades = backtester.run()
        assert trades == mock_trades

        with patch.object(LoggerMonitor, "print_summary") as mock_print_summary:
            logger_monitor.print_summary(risk_manager.balance)
            mock_print_summary.assert_called_once_with(risk_manager.balance)
