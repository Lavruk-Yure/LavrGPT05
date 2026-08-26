# core\execution.py
import uuid

from core.lang_manager import LangManager
from core.logger_monitor import LoggerMonitor
from core.risk_manager import RiskManager

lang = LangManager()


class ExecutionEngine:
    """
    Клас відповідає за виставлення, моделювання та закриття ордерів.
    Підтримує режими:
      - 'simulator' — для тестування логіки без реального брокера;
      - 'live' — (поки не реалізовано) для роботи з реальним середовищем.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        mode: str = "simulator",
        logger: LoggerMonitor | None = None,
    ):
        self.risk_manager = risk_manager
        self.mode = mode.lower().strip()  # нормалізація значення
        self.active_orders: dict[str, dict] = {}
        self.logger = logger

    # -----------------------------
    # Основний метод подачі ордера
    # -----------------------------
    def submit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        stop_loss: float,
        take_profit: float | None = None,
    ) -> tuple[bool, dict | str]:
        """
        Створює новий ордер у режимі 'simulator' (або готує до 'live').

        Повертає:
            (True, order_dict) — якщо ордер створено успішно
            (False, reason) — якщо ордер відхилено RiskManager'ом
        """
        # Визначаємо відстань до стоп-лоссу
        stop_loss_distance = abs(price - stop_loss)

        # --- ВАЛІДАЦІЯ через RiskManager ---
        valid, info = self.risk_manager.validate_order(stop_loss_distance, price)
        if not valid:
            # info містить причину відмови
            return False, info

        # info містить розрахований розмір позиції
        size = info
        order_id = str(uuid.uuid4())

        order = {
            "id": order_id,
            "symbol": symbol,
            "side": side.lower(),
            "price": price,
            "size": size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "OPEN",
        }

        # --- Режим симуляції ---
        if self.mode == "simulator":
            self.active_orders[order_id] = order
            if self.logger:
                self.logger.log_trade(order, self.risk_manager.balance)
            return True, order

        # --- Режим live (ще не реалізовано) ---
        if self.mode == "live":
            #  інтегрувати з реальним брокером
            return False, "Live mode not implemented yet"

        # --- Захист від неправильного режиму ---
        return False, f"Unknown mode: {self.mode}"

    # -----------------------------
    # Закриття ордера
    # -----------------------------
    def close_order(self, order_id: str, exit_price: float) -> tuple[bool, float | str]:
        """
        Закриває ордер і реєструє результат у RiskManager.
        """
        if order_id not in self.active_orders:
            return False, "Order not found"

        order = self.active_orders[order_id]

        # Розрахунок прибутку/збитку
        if order["side"] == "long":
            pnl = (exit_price - order["price"]) * order["size"]
        else:
            pnl = (order["price"] - exit_price) * order["size"]

        order["status"] = "CLOSED"
        self.risk_manager.register_trade(pnl)

        if self.logger:
            self.logger.log_trade(order, self.risk_manager.balance)

        del self.active_orders[order_id]
        return True, pnl
