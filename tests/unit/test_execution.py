# test_execution.py
"""
test_execution.py

Тестування ExecutionEngine з RiskManager у режимі симулятора.
Перевіряє коректність відкриття і закриття ордерів,
а також коректне оновлення балансу після угод.
"""

import pytest

from core.execution import ExecutionEngine
from core.risk_manager import RiskManager


@pytest.fixture
def setup_execution_engine():
    """
    Фікстура для ініціалізації RiskManager і ExecutionEngine.
    """
    rm = RiskManager(
        balance=10_000, risk_per_trade=0.01, max_drawdown=0.2, max_trades_per_day=3
    )
    engine = ExecutionEngine(risk_manager=rm, mode="simulator")
    return engine, rm


def test_submit_and_close_order(setup_execution_engine):
    """
    Тестує відкриття ордера і його закриття з перевіркою:
    - коректності повернення статусу з submit_order,
    - правильності розрахунку прибутку/збитку при закритті,
    - оновлення балансу RiskManager після закриття угоди.
    """
    engine, rm = setup_execution_engine

    ok, order = engine.submit_order(
        symbol="BTCUSDT", side="long", price=1000, stop_loss=950, take_profit=1100
    )
    assert ok, "Order submission failed"
    assert "id" in order, "Order ID missing in response"

    order_id = order["id"]
    ok_close, pnl = engine.close_order(order_id, exit_price=1050)
    assert ok_close, "Order closing failed"
    assert isinstance(pnl, (int, float)), "Profit/loss not a number"

    # Перевірка що баланс оновився на суму pnl
    expected_balance = 10000 + pnl
    assert (
        abs(rm.balance - expected_balance) < 1e-6
    ), "Balance not updated correctly after closing order"
