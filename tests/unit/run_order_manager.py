# run_order_manager.py
"""
run_order_manager.py

Приклад запуску OrderManager у різних режимах,
демонстрація логування та роботи place_order.
"""

from core.logger_monitor import setup_logger
from core.order_manager import OrderManager, OrderMode


class DummyBroker:
    @staticmethod
    def send_order(symbol, side, volume, price, sl, tp):
        print(
            f"Відправлено ордер: {symbol} {side} {volume} @ {price}, SL={sl}, TP={tp}"
        )
        return f"ORDER-{symbol}-{side}-{volume}"


class DummyAnalyzer:
    @staticmethod
    def analyze(symbol, side):
        analysis = f"Сигнал {side} по {symbol} базується на SMA."
        print(f"Аналіз: {analysis}")
        return analysis


def main():
    logger = setup_logger("OrderManagerTest", log_file="order_manager_test.log")
    broker = DummyBroker()
    analyzer = DummyAnalyzer()

    for mode in [OrderMode.MANUAL, OrderMode.SEMI_AUTO, OrderMode.AUTO]:
        om = OrderManager(mode=mode, broker=broker, analyzer=analyzer, logger=logger)
        print(f"\n=== Режим: {mode.value.upper()} ===")
        if mode == OrderMode.SEMI_AUTO:
            # Симуляція підтвердження угоди
            import builtins

            builtins.input = lambda _: "y"
        res = om.place_order("EURUSD", "BUY", 1.0, price=1.12, sl=1.10, tp=1.15)
        print(f"Результат place_order: {res}")


if __name__ == "__main__":
    main()
