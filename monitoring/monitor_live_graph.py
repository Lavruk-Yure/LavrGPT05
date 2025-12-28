# monitor_live_graph.py

import os


class LiveMonitorGraph:
    """
    Клас для відображення графіка балансу у консолі.

    Attributes:
        width (int): Ширина графіка в символах.
        height (int): Висота графіка в рядках.
        history (list[float]): Історія значень балансу.
    """

    def __init__(self, width=50, height=10):
        """
        Ініціалізує графік з заданою шириною і висотою.
        Зберігає історію значень балансу.
        """
        self.width = width
        self.height = height
        self.history = []

    def update(self, balance):
        """
        Оновлює графік останнім значенням балансу,
        нормалізує дані та виводить у вигляді ASCII-графіка.

        Args:
            balance (float): Поточний баланс для відображення.
        """
        self.history.append(balance)
        # Беремо останні width значень з історії для відображення

        data = self.history[-self.width :]  # noqa
        min_val = min(data)
        max_val = max(data)
        # Обчислюємо діапазон, уникаючи ділення на нуль
        range_val = max_val - min_val if max_val != min_val else 1.0

        # Нормалізуємо значення до висоти графіка
        normalized = [int((b - min_val) / range_val * (self.height - 1)) for b in data]

        # Створюємо сітку для виводу графіку
        grid = [[" " for _ in range(len(normalized))] for _ in range(self.height)]
        for x, val in enumerate(normalized):
            grid[self.height - 1 - val][x] = "*"

        # Очищаємо консоль (для Windows і Unix-систем)
        os.system("cls" if os.name == "nt" else "clear")

        # Виводимо графік рядок за рядком
        for row in grid:
            print("".join(row))
        # Виводимо поточний баланс та мінімальні/максимальні значення
        print(f"Balance: {balance:.2f} | Min: {min_val:.2f} Max: {max_val:.2f}")
