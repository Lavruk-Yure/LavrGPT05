#  run_execution.py
"""
run_execution.py

Приклад запуску ExecutionEngine з RiskManager.
Виконує відкриття і закриття ордера, виводить результати.
"""

from core.execution import ExecutionEngine
from core.risk_manager import RiskManager


def main():
    rm = RiskManager(
        balance=10_000, risk_per_trade=0.01, max_drawdown=0.2, max_trades_per_day=3
    )
    engine = ExecutionEngine(risk_manager=rm, mode="simulator")

    ok, order = engine.submit_order(
        symbol="BTCUSDT", side="long", price=1000, stop_loss=950, take_profit=1100
    )
    print("Submit Order:", ok, order)

    if ok:
        order_id = order["id"]
        ok, pnl = engine.close_order(order_id, exit_price=1050)
        print("Close Order:", ok, pnl)
        print("Balance:", rm.balance)


if __name__ == "__main__":
    main()
