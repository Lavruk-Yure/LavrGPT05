# monitor_live_graph_stats_orders.py
"""
monitor_live_graph_stats_orders.py

Модуль містить клас LiveMonitorGraphOrders для моніторингу балансу,
відображення відкритих і закритих ордерів у вигляді графіка в консолі.
"""


class LiveMonitorGraphOrders:
    """
    Клас для відображення балансу та ордерів на графіку у консолі.

    Атрибути:
        width (int): ширина графіка.
        height (int): висота графіка.
        max_balance (float): максимальне значення балансу для масштабування.
        min_balance (float): мінімальне значення балансу для масштабування.
    """

    def __init__(self, width=50, height=10, title="Trading Monitor"):
        """
        Ініціалізує параметри відображення графіка.

        Args:
            width (int): ширина графіка по горизонталі.
            height (int): висота графіка по вертикалі.
            title (str): заголовок
        """
        self.width = width
        self.height = height
        self.title = title
        self.max_balance = 0
        self.min_balance = float("inf")
        self.last_balance = 0

    def update(self, balance, closed_trades, open_orders):
        """
        Оновлює межі графіка, відображає баланс, відкриті та закриті ордери.

        Args:
            balance (float): поточний баланс.
            closed_trades (list[dict]): список закритих угод,
                кожен з ключами 'balance_after' та 'profit'.
            open_orders (list[dict]): список відкритих ордерів,
                кожен з ключами 'price' та 'side' (buy/sell).
        """
        # Усі баланси для визначення меж відображення
        all_balances = [balance] + [
            t.get("balance_after", balance) for t in closed_trades
        ]
        self.max_balance = max(all_balances + [self.max_balance])
        self.min_balance = min(all_balances + [self.min_balance])

        scale = max(1e-6, self.max_balance - self.min_balance)

        # Ініціалізація сітки символів для графіка
        grid = [[" " for _ in range(self.width)] for _ in range(self.height)]

        # Позначення відкритих ордерів на першому стовпчику
        for order in open_orders:
            order_price = order.get("price", balance)
            order_pos = int(
                (order_price - self.min_balance) / scale * (self.height - 1)
            )
            order_pos = max(0, min(self.height - 1, order_pos))
            grid[self.height - 1 - order_pos][0] = (
                "+" if order.get("side") == "buy" else "-"
            )

        # Позначення закритих ордерів на другому стовпчику
        for t in closed_trades:
            balance_after = t.get("balance_after", balance)
            t_pos = int((balance_after - self.min_balance) / scale * (self.height - 1))
            t_pos = max(0, min(self.height - 1, t_pos))
            symbol = "*" if t.get("profit", 0) > 0 else "x"
            grid[self.height - 1 - t_pos][1] = symbol

        # Вивід графіка в консоль
        for row in grid:
            print("".join(row))

        # Вивід поточної статистики
        print(
            f"Balance: {balance:.2f} |"
            f" Trades: {len(closed_trades) + len(open_orders)} |"
            f" Open Orders: {len(open_orders)}"
        )
