# tests\live\run_AutoModes_Brokers.py
# 18.09.2025 / оновлено 16.10.2025
# Демонстраційний запуск AUTO-режимів для різних брокерів (IB, cTrader, Dummy).
# Призначення:
#   • Інтеграційна перевірка OrderManager у режимі AUTO.
#   • Логування реальних або мокованих ордерів для IB / cTrader / Dummy.
#   • Не є pytest-тестом — запускається вручну.
#
# Запуск:
#   python tests/run_AutoModes_Brokers.py
#
# Логи:
#   створюються у файлі Test_AutoModes_Brokers.log у корені LavrGPT05.
#
# Примітка:
#   Якщо треба виконувати тільки локально (без мережі) —
#   залишай моковану версію cTrader (рядки з CT-DEMO-MOCK).
#   Для реального API використовуй дійсний access_token.


from brokers.ctrader_adapter import CTraderAdapter
from brokers.ib_adapter import IBAdapter
from core.lang_manager import LangManager
from core.logger_monitor import setup_logger
from core.order_manager import OrderManager, OrderMode

lang = LangManager()


class DummyBroker:
    """Проста заглушка брокера для тестів без мережі."""

    def __init__(self, logger_obj=None):
        self.logger = logger_obj

    def send_order(self, symbol, side, volume, price=None, sl=None, tp=None, **_):
        """Мокає відправку ордера (повна сигнатура OrderManager)."""
        msg = lang.t("dummy_order_info").format(
            symbol=symbol, side=side, volume=volume, price=price, sl=sl, tp=tp
        )
        if self.logger:
            self.logger.info(msg)
        return lang.t("dummy_order_id").format(symbol=symbol, side=side, volume=volume)

    @staticmethod
    def get_balance():
        """Повертає фіктивний баланс для тестів."""
        return 100000.0


if __name__ == "__main__":
    log = setup_logger("Test_AutoModes_Brokers", log_file="Test_AutoModes_Brokers.log")
    log.info("=== Початок тесту AUTO-режимів брокерів ===")

    # --- IB Adapter ---
    ib_adapter = IBAdapter(logger=log)
    om_ib = OrderManager(mode=OrderMode.AUTO, broker=ib_adapter, logger=log)
    ib_order_id = om_ib.place_order("EURUSD", "BUY", 20000)
    log.info(f"IB ордер ID: {ib_order_id}")
    log.info("✅ Ордер выполнен (IB)")

    # # --- cTrader Adapter ---
    # ctrader_adapter = CTraderAdapter(api_token="DEMO_TOKEN", logger=log)
    # om_ct = OrderManager(mode=OrderMode.AUTO, broker=ctrader_adapter, logger=log)
    # ct_order_id = om_ct.place_order("EURUSD", "SELL", 20000)

    # --- cTrader Adapter (мок) ---
    ctrader_adapter = CTraderAdapter(api_token="DEMO_TOKEN", logger=log)
    ctrader_adapter.send_order = lambda *args, **kwargs: "CT-DEMO-MOCK"
    om_ct = OrderManager(mode=OrderMode.AUTO, broker=ctrader_adapter, logger=log)
    ct_order_id = om_ct.place_order("EURUSD", "SELL", 20000)

    log.info(f"cTrader ордер ID: {ct_order_id}")
    log.info("✅ Ордер выполнен (cTrader)")

    # --- Dummy Broker ---
    dummy = DummyBroker(logger_obj=log)
    om_dummy = OrderManager(mode=OrderMode.AUTO, broker=dummy, logger=log)
    dummy_order_id = om_dummy.place_order("EURUSD", "BUY", 1000)
    log.info(f"Dummy ордер ID: {dummy_order_id}")
    log.info("✅ Ордер выполнен (Dummy)")

    log.info("=== Тест AUTO-режимів завершено успішно ===")
