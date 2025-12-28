# monitor_live_graph_stats.py

import os


class LiveMonitorGraphStats:
    """
    Клас для відображення статистики торгів та графіка балансу у консолі.

    Attributes:
        width (int): Ширина графіка в символах.
        height (int): Висота графіка в рядках.
        balance_history (list[float]): Історія значень балансу.
        trades (int): Загальна кількість закритих угод.
        win_trades (int): Кількість виграшних угод.
        profit (float): Загальний прибуток.
        max_dd (float): Максимальне просідання (drawdown).
        peak_balance (float): Максимальний зафіксований баланс.
    """

    def __init__(self, width=50, height=10):
        """
        Ініціалізує параметри графіка та статистики.
        """
        self.width = width
        self.height = height
        self.balance_history = []
        self.trades = 0
        self.win_trades = 0
        self.profit = 0.0
        self.max_dd = 0.0
        self.peak_balance = 0.0

    def update(self, balance, closed_trades=None):
        """
        Оновлює історію балансу та статистику за закритими угодами,
        будує графік балансу та виводить статистику.

        Args:
            balance (float): Поточний баланс.
            closed_trades (list[dict], optional): Список недавно закритих угод.
        """
        if closed_trades is None:
            closed_trades = []

        self.balance_history.append(balance)
        self.peak_balance = max(self.peak_balance, balance)
        dd = self.peak_balance - balance
        if dd > self.max_dd:
            self.max_dd = dd

        # оновлення статистики по закритих угодах
        for t in closed_trades:
            self.trades += 1
            if t["profit"] > 0:
                self.win_trades += 1
            self.profit += t["profit"]

        # будуємо графік останніх width значень балансу
        data = self.balance_history[-self.width :]  # noqa
        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val if max_val != min_val else 1.0
        normalized = [int((b - min_val) / range_val * (self.height - 1)) for b in data]

        # створюємо сітку для графіка
        grid = [[" " for _ in range(len(normalized))] for _ in range(self.height)]
        for x, val in enumerate(normalized):
            grid[self.height - 1 - val][x] = "*"

        # чистимо консоль
        os.system("cls" if os.name == "nt" else "clear")

        # виводимо графік рядок за рядком
        for row in grid:
            print("".join(row))

        win_pct = (self.win_trades / self.trades * 100) if self.trades > 0 else 0.0
        # виводимо статистику балансу та угод
        print(
            f"Balance: {balance:.2f} | Profit: {self.profit:.2f} | Trades:"
            f"  {self.trades} | Win%: {win_pct:.1f}% | Max DD: {self.max_dd:.2f}"
        )
