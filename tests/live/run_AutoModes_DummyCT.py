# run_AutoModes_DummyCT.py
"""
Запускає тестову сесію для адаптера Dummy cTrader.

Виконує наступні дії:
- Ініціалізує екземпляр DummyCTrader.
- Збирає та логірує баланс рахунку перед створенням ордера.
- Відправляє ринковий ордер на купівлю EURUSD об'ємом 1 лот.
- Логірує ID відправленого ордера.
- Отримує та логірує список відкритих ордерів.
- Отримує та логірує поточні позиції на ринку.
- Збирає та логірує баланс рахунку після операцій.

Примітка:
Ця функція призначена для ручного запуску і демонстрації роботи DummyCTrader.
Для автоматизованого тестування радимо використовувати pytest з assert-перевірками.
"""


import logging

from brokers.ctrader_dummy import DummyCTrader

# --- Логування ---
logger = logging.getLogger("Test_AutoModes_DummyCT")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


def main():
    """Примітка:
    Ця функція призначена для ручного запуску і демонстрації роботи DummyCTrader.
    Для автоматизованого тестування радимо використовувати pytest з assert-перевірками.
    """
    logger.info("=== TEST: Dummy cTrader Adapter ===")

    broker = DummyCTrader()

    # Баланс перед ордером
    balance_before = broker.get_account_info()["balance"]
    logger.info(f"Баланс перед ордером: {balance_before}")

    # Відправка ринкового ордера
    order_id = broker.place_order("EURUSD", 1, "BUY", order_type="market")
    logger.info(f"Ордер відправлено, ID={order_id}")

    # Відкриті ордери
    open_orders = broker.get_open_orders()
    logger.info(f"Відкриті ордери: {open_orders}")

    # Позиції
    positions = broker.get_positions()
    logger.info(f"Позиції: {positions}")

    # Баланс після ордеру
    balance_after = broker.get_account_info()["balance"]
    logger.info(f"Баланс після ордерів: {balance_after}")


if __name__ == "__main__":
    main()
