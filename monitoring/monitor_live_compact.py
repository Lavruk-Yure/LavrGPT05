# monitor_live_compact.py
"""
monitor_live_compact.py

Модуль містить клас LiveMonitorCompact
для компактного відображення даних моніторингу торгів у консолі.
"""


class LiveMonitorCompact:
    """
    Клас для компактного відображення барів, відкритих ордерів та балансу.

    Метод update_bar виводить інформацію по бару у вигляді рядка з даними
    про ціну закриття, баланс і відкриті позиції.
    """

    def update_bar(self, bar_index, candle, trades, balance):  # noqa
        """
        Оновлює рядок моніторингу для поточного бару.

        Args:
            bar_index (int): номер бару (індекс).
            candle (dict): словник зі свічкою, має містити ключ 'close'.
            trades (list[dict]): список угод, кожна з ключем 'status' (OPEN, CLOSED).
            balance (float): поточний баланс.
        """
        line = (
            f"Bar {bar_index + 1} |"
            f" Close: {candle['close']} |"
            f" Balance: {balance:.2f}"
        )
        open_trades = [t for t in trades if t["status"] == "OPEN"]
        if open_trades:
            positions = " | ".join(
                f"{t['side'].upper()}@{t['price']}"
                f" SL:{t['stop_loss']:.2f} TP:{t['take_profit']:.2f}"
                for t in open_trades
            )
            line += f" | Open: {positions}"
        print(line)
