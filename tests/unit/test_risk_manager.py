# tests/unit/test_risk_manager.py
"""
RiskManager — клас для управління ризиками торгівлі.

Основні можливості:
- контроль максимального ризику на одну угоду,
- розрахунок розміру позиції,
- облік максимальної просадки,
- обмеження кількості угод на день,
- обчислення тейк-профіту за співвідношенням ризик/прибуток.

Цей клас призначений для забезпечення безпеки капіталу та допомоги трейдеру
дотримуватись заданих параметрів управління ризиками.
"""

import pytest

from core.risk_manager import RiskManager


@pytest.fixture(scope="module")
def risk_manager():
    """
    Ініціалізує RiskManager для одного торгового дня.

    Баланс: 10 000
    Ризик: 1% на угоду
    Макс. просадка: 20%
    Макс. кількість угод на день: 3
    """
    return RiskManager(
        balance=10_000,
        risk_per_trade=0.01,
        max_drawdown=0.2,
        max_trades_per_day=3,
    )


def test_trade_1(risk_manager):
    """
    Перша угода (long) — стоп 50$, ціна 1000$.
    Перевіряє дозвіл, тейк-профіт і оновлення балансу після прибутку +120$.
    """
    valid, info = risk_manager.validate_order(stop_loss_distance=50, price=1000)
    assert valid, f"Trade 1 should be allowed but blocked: {info}"

    tp = risk_manager.calc_take_profit(
        entry_price=1000,
        stop_loss_price=950,
        rr_ratio=2,
    )
    assert tp == 1100, f"Take profit calculation mismatch for Trade 1: got {tp}"

    risk_manager.register_trade(profit_loss=120)
    assert risk_manager.balance == 10120, "Balance not updated correctly after Trade 1"


def test_trade_2(risk_manager):
    """
    Друга угода (short) — стоп 25$, ціна 500$.
    Перевіряє дозвіл, тейк-профіт і оновлення балансу після збитку -80$.
    """
    valid, info = risk_manager.validate_order(stop_loss_distance=25, price=500)
    assert valid, f"Trade 2 should be allowed but blocked: {info}"

    tp = risk_manager.calc_take_profit(
        entry_price=500,
        stop_loss_price=525,
        rr_ratio=3,
    )
    assert tp == 425, f"Take profit calculation mismatch for Trade 2: got {tp}"

    risk_manager.register_trade(profit_loss=-80)
    expected_balance = 10120 - 80
    assert (
        risk_manager.balance == expected_balance
    ), f"Balance not updated correctly after Trade 2: got {risk_manager.balance}"


def test_trade_3(risk_manager):
    """
    Третя угода (long) — стоп 100$, ціна 2000$.
    Перевіряє дозвіл і оновлення балансу після збитку -200$.
    """
    valid, info = risk_manager.validate_order(stop_loss_distance=100, price=2000)
    assert valid, f"Trade 3 should be allowed but blocked: {info}"

    risk_manager.register_trade(profit_loss=-200)
    expected_balance = 10120 - 80 - 200
    assert (
        risk_manager.balance == expected_balance
    ), f"Balance not updated correctly after Trade 3: got {risk_manager.balance}"


def test_trade_4_blocked_due_to_max_trades(risk_manager):
    """
    Четверта угода має бути заблокована через перевищення ліміту угод за день.
    """
    valid, info = risk_manager.validate_order(stop_loss_distance=10, price=100)
    assert not valid, "Trade 4 should be blocked due to max trades per day"
    assert (
        "max trades" in info.lower()
    ), f"Block reason should mention max trades: {info}"
