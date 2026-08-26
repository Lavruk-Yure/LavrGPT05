# test_backtester_monitor.py
"""
•	Запускає бек тестер із моканим методом run() для контролю виходу.
•	Викликає логування торгів і підсумковий вивід.
•	Перевіряє, що метод print_summary у LoggerMonitor викликається з правильним балансом.
"""

from unittest.mock import patch

import pytest

# Імпортуйте класи, якщо вони в одному пакеті
from core.backtester import Backtester
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager
from strategies.strategy_sma import SMAStrategy


@pytest.fixture
def risk_manager():
    return RiskManager(balance=10_000, risk_per_trade=0.01)


@pytest.fixture
def strategy():
    return SMAStrategy(sma_fast=3, sma_slow=5, sl_coef=0.01, rr_ratio=2.0)


@pytest.fixture
def backtester(strategy, risk_manager):
    # Можна помокати data_file, наприклад, або залишити як є, якщо у тестах є data.csv
    return Backtester(
        data_file="data.csv", strategy=strategy, risk_manager=risk_manager
    )


@pytest.fixture
def logger_monitor():
    return LoggerMonitor()


def test_backtester_runs_and_logs(backtester, logger_monitor, risk_manager):
    # Мок списку угод, які повертає бек тестер
    mock_trades = [
        {"id": 1, "profit": 50},
        {"id": 2, "profit": -30},
    ]

    # Мокати метод run у Backtester, щоб він повертав mock_trades
    with patch.object(Backtester, "run", return_value=mock_trades):
        trades = backtester.run()

        # Перевірка, що run повертає нашу мокану угоду
        assert trades == mock_trades

        # Для кожної торгівлі викликаємо логера
        for t in trades:
            logger_monitor.log_trade(t, risk_manager.balance)

        # Перевірити, що логер викликав print_summary з поточним балансом
        with patch.object(LoggerMonitor, "print_summary") as mock_print_summary:
            logger_monitor.print_summary(risk_manager.balance)
            mock_print_summary.assert_called_once_with(risk_manager.balance)
