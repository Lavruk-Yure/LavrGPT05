# monitor_live_graph_stats_compact.py
"""
monitor_live_graph_stats_compact.py

Модуль містить клас LiveMonitorGraphStatsCompact для компактного відображення
графіка балансу та статистики прибутку по закритих угодах у консолі.
"""

__all__ = ["LiveMonitorGraphStatsCompact"]


class LiveMonitorGraphStatsCompact:
    """
    Клас для моніторингу балансу з виводом компактного графіка в консолі.

    Атрибути:
        width (int): ширина графіка в символах.
        height (int): висота графіка в символах.
        history (list[float]): історія значень балансу.
    """

    def __init__(self, width=50, height=10):
        """
        Ініціалізує монітор з параметрами розміру.

        Args:
            width (int): максимальна ширина графіка (довжина історії).
            height (int): висота графіка (кількість рівнів).
        """
        self.width = width
        self.height = height
        self.history = []

    def update(self, balance, closed_trades):
        """
        Оновлює історію балансу, обчислює прибуток і виводить графік та статистику.

        Args:
            balance (float): поточний баланс.
            closed_trades (list[dict]): список закритих угод,
            кожна з яких містить ключ 'profit'.
        """
        profit = sum(t.get("profit", 0) for t in closed_trades)
        self.history.append(balance)

        if len(self.history) > self.width:
            self.history.pop(0)

        min_val = min(self.history)
        max_val = max(self.history)
        span = max_val - min_val if max_val != min_val else 1

        graph_lines = []
        for level in range(self.height, 0, -1):
            threshold = min_val + span * level / self.height
            line = "".join("*" if val >= threshold else " " for val in self.history)
            graph_lines.append(line)

        print("\033c", end="")  # Очищення консолі

        for line in graph_lines:
            print(line)

        print(
            f"Balance: {balance:.2f} | Profit: {profit:.2f} |"
            f" Trades: {len(closed_trades)}"
        )
