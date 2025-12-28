# core\risk_manager.py
# --- Python 3.13, LavrGPT05 ---

import datetime


class RiskManager:
    """Керує ризиками торгівлі: розмір позиції, просадка, ліміти на день."""

    def __init__(
        self,
        balance: float,
        risk_per_trade: float = 0.01,  # 1% ризику на угоду
        max_drawdown: float = 0.2,  # 20% максимальної просадки
        max_trades_per_day: int = 5,  # ліміт угод за день
    ):
        self.start_balance = balance
        self.balance = balance
        self.risk_per_trade = risk_per_trade
        self.max_drawdown = max_drawdown
        self.max_trades_per_day = max_trades_per_day

        # облік кількості угод
        self.trades_today = 0
        self.last_trade_date = None

    # --- допоміжне ---
    def _reset_daily_counter(self) -> None:
        """Скидає лічильник угод, якщо настав новий день."""
        today = datetime.date.today()
        if self.last_trade_date != today:
            self.trades_today = 0
            self.last_trade_date = today

    # --- контроль просадки ---
    def check_drawdown(self) -> bool:
        """
        True — якщо торгувати ще можна.
        False — якщо перевищено ліміт просадки.
        """
        return self.balance >= self.start_balance * (1 - self.max_drawdown)

    # --- розрахунок розміру позиції ---
    def calc_position_size(self, stop_loss_distance: float, price: float) -> float:
        """
        Обчислює допустимий розмір позиції.
        stop_loss_distance — відстань від входу до стоп-а у тих же одиницях, що й ціна.
        price — поточна ціна інструменту.
        """
        if stop_loss_distance <= 0 or price <= 0:
            return 0.0

        risk_amount = self.balance * self.risk_per_trade
        size = risk_amount / stop_loss_distance
        return round(size, 6)

    # --- перевірка ордера ---
    def validate_order(self, stop_loss_distance: float, price: float) -> tuple:
        """
        Перевіряє, чи можна відкрити угоду.
        Повертає (True/False, size або повідомлення).
        """
        """Перевірка чи дозволено відкрити нову угоду."""
        if self.trades_today >= self.max_trades_per_day:
            return False, "Max trades per day reached"

        self._reset_daily_counter()

        if not self.check_drawdown():
            return False, "❌ Max drawdown exceeded"

        if self.trades_today >= self.max_trades_per_day:
            return False, "❌ Max trades per day exceeded"

        size = self.calc_position_size(stop_loss_distance, price)
        if size <= 0:
            return False, "❌ Invalid position size"

        return True, size

    # --- реєстрація угоди ---
    def register_trade(self, profit_loss: float) -> None:
        """
        Оновлює баланс після закриття угоди.
        profit_loss — прибуток або збиток у валюті рахунку.
        """
        self.balance += profit_loss
        self.trades_today += 1

        # --- розрахунок тейк-профіту ---

    @staticmethod
    def calc_take_profit(entry_price, stop_loss_price, rr_ratio):
        """
        Розрахунок тейк-профіту за співвідношенням ризик/прибуток.
        Працює для long і short позицій.
        """
        if entry_price > stop_loss_price:
            # LONG позиція
            return entry_price + abs(entry_price - stop_loss_price) * rr_ratio
        else:
            # SHORT позиція
            return entry_price - abs(entry_price - stop_loss_price) * rr_ratio
