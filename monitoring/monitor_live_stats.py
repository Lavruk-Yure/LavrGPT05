# monitor_live_stats.py
import os
import time


class LiveMonitorStats:
    """
    Клас для моніторингу основних торгових метрик з виводом у консоль.

    Attributes:
        refresh_delay (float): час затримки оновлення в секундах.
        trades_executed (int): кількість виконаних угод.
        profit_total (float): сумарний прибуток.
        max_drawdown (float): максимальне просідання балансу.
        balance_peak (float): максимальний досягнутий баланс.
        win_trades (int): кількість виграшних угод.
    """

    def __init__(self, refresh_delay=0.1):
        """
        Ініціалізує монітор з часом затримки оновлення.

        Args:
            refresh_delay (float, optional): затримка оновлення у секундах.
            За замовчуванням 0.1.
        """
        self.refresh_delay = refresh_delay
        self.trades_executed = 0
        self.profit_total = 0.0
        self.max_drawdown = 0.0
        self.balance_peak = 0.0
        self.win_trades = 0

    def update_metrics(self, balance, closed_trades):
        """
        Оновлює показники метрик на основі поточного балансу та закритих угод.

        Args:
            balance (float): поточний баланс.
            closed_trades (list[dict]): список закритих угод з ключами
            'exit_price', 'price', 'side'.
        """
        self.balance_peak = max(self.balance_peak, balance)
        self.max_drawdown = max(self.max_drawdown, self.balance_peak - balance)

        for t in closed_trades:
            self.trades_executed += 1
            pnl = (
                (t["exit_price"] - t["price"])
                if t["side"] == "LONG"
                else (t["price"] - t["exit_price"])
            )
            self.profit_total += pnl
            if pnl > 0:
                self.win_trades += 1

    def update_bar(self, bar_index, candle, trades, balance, closed_trades=None):
        """
        Оновлює екран в консолі з інформацією по бару, позиціях і статистиці.

        Args:
            bar_index (int): індекс поточного бару.
            candle (dict): дані свічки, повинен містити ключ 'close'.
            trades (list[dict]): список всіх угод.
            balance (float): поточний баланс.
            closed_trades (list[dict], optional): список закритих угод.
            За замовчуванням None.
        """
        if closed_trades is None:
            closed_trades = []

        os.system("cls" if os.name == "nt" else "clear")

        self.update_metrics(balance, closed_trades)

        # Основний рядок для виводу
        line = (
            f"Bar {bar_index + 1} | Close: {candle['close']} |"
            f" Balance:{balance:.2f}"
        )
        open_trades = [t for t in trades if t["status"] == "OPEN"]
        if open_trades:
            positions = " | ".join(
                f"{t['side'].upper()}@{t['price']}"
                f" SL:{t['stop_loss']:.2f}TP:{t['take_profit']:.2f}"
                for t in open_trades
            )
            line += f" | Open: {positions}"
        print(line)

        # Вивід статистики
        win_percent = (
            (self.win_trades / self.trades_executed * 100)
            if self.trades_executed
            else 0
        )
        print(
            f"Trades: {self.trades_executed} | Profit: {self.profit_total:.2f} |"
            f" Max DD: {self.max_drawdown:.2f} | Win%: {win_percent:.1f}%"
        )

        time.sleep(self.refresh_delay)
