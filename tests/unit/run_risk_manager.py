"""
run_risk_manager.py

Запуск RiskManager з прикладами угод,
демонстрація розрахунку розміру позиції, тейк-профіту, та оновлення балансу.
"""

from core.risk_manager import RiskManager


def main():
    rm = RiskManager(
        balance=10_000, risk_per_trade=0.01, max_drawdown=0.2, max_trades_per_day=3
    )
    print(f"Start balance: {rm.balance}\n")

    # 1 угода (long), стоп 50$, ціна 1000$
    valid, info = rm.validate_order(stop_loss_distance=50, price=1000)
    if valid:
        size = info
        print(f"[TRADE 1] Order allowed. Position size = {size}")
        tp = rm.calc_take_profit(entry_price=1000, stop_loss_price=950, rr_ratio=2)
        print(f"   Take Profit set at {tp}")
        rm.register_trade(profit_loss=120)
    else:
        print(f"[TRADE 1] Blocked: {info}")

    print(f"Balance after trade 1: {rm.balance}\n")

    # 2 угода (short), стоп 25$, ціна 500$
    valid, info = rm.validate_order(stop_loss_distance=25, price=500)
    if valid:
        size = info
        print(f"[TRADE 2] Order allowed. Position size = {size}")
        tp = rm.calc_take_profit(entry_price=500, stop_loss_price=525, rr_ratio=3)
        print(f"   Take Profit set at {tp}")
        rm.register_trade(profit_loss=-80)
    else:
        print(f"[TRADE 2] Blocked: {info}")

    print(f"Balance after trade 2: {rm.balance}\n")

    # 3 угода (long), стоп 100$, ціна 2000$
    valid, info = rm.validate_order(stop_loss_distance=100, price=2000)
    if valid:
        size = info
        print(f"[TRADE 3] Order allowed. Position size = {size}")
        rm.register_trade(profit_loss=-200)
    else:
        print(f"[TRADE 3] Blocked: {info}")

    print(f"Balance after trade 3: {rm.balance}\n")

    # 4 угода (має бути заблокована, max_trades_per_day=3)
    valid, info = rm.validate_order(stop_loss_distance=10, price=100)
    if valid:
        print("[TRADE 4] Allowed, ERROR!")
    else:
        print(f"[TRADE 4] Blocked: {info}")


if __name__ == "__main__":
    main()
