# monitor_live_realtime.py
import os
import time


class LiveMonitorRealtime:
    """
    Клас для реального часу виведення інформації про бари, позиції та баланс у консолі.

    Attributes:
        refresh_delay (float): Затримка оновлення екрана в секундах.
    """

    def __init__(self, refresh_delay=0.1):
        """
        Ініціалізує монітор із заданою затримкою оновлення.

        Args:
            refresh_delay (float, optional): Затримка оновлення екрана в секундах.
            За замовчуванням 0.1.
        """
        self.refresh_delay = refresh_delay

    def update_bar(self, bar_index, candle, trades, balance):
        """
        Оновлює інформацію про поточний бар, відкриті позиції та баланс.

        Args:
            bar_index (int): Індекс поточного бару.
            candle (dict): Дані свічки з ключами 'time' та 'close'.
            trades (list[dict]): Список угод з атрибутом 'status', 'symbol',
            'side', 'price', 'stop_loss', 'take_profit'.
            balance (float): Поточний баланс.
        """
        # Очищення екрана залежно від ОС
        os.system("cls" if os.name == "nt" else "clear")

        # Вивід основної інформації про бар та баланс
        print(
            f"Bar {bar_index + 1} | Time: {candle['time']} |"
            f" Close:{candle['close']} | Balance: {balance:.2f}"
        )

        # Фільтруємо відкриті угоди
        open_trades = [t for t in trades if t["status"] == "OPEN"]

        # Вивід інформації про відкриті позиції
        if open_trades:
            print("Open positions:")
            for t in open_trades:
                print(
                    f"  {t['symbol']} | {t['side'].upper()} | entry={t['price']} |"
                    f" SL={t['stop_loss']:.2f} | TP={t['take_profit']:.2f}"
                )
        else:
            print("No open positions.")

        # Затримка перед наступним оновленням
        time.sleep(self.refresh_delay)
