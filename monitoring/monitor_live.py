# monitoring\monitor_live.py
"""
Монітор у реальному часі для оновлення інформації по барах і відкритих позиціях.
"""
from core.lang_manager import LangManager

lang = LangManager()


class LiveMonitor:
    """Монітор у реальному часі для відображення поточних даних."""

    def __init__(self):
        self.open_positions = []

    def update_bar(self, bar_index, candle, trades, balance):
        """
        Оновлення інформації по бару.

        Аргументи:
            bar_index (int): Індекс бара.
            candle (dict): Дані свічки (час, ціна закриття тощо).
            trades (list): Список торгів з їх станом.
            balance (float): Баланс рахунку.
        """
        print(
            lang.t("bar_info").format(
                index=bar_index + 1, time=candle["time"], close=candle["close"]
            )
        )

        print(lang.t("balance_value").format(balance=f"{balance:.2f}"))

        self.open_positions = [t for t in trades if t["status"] == "OPEN"]

        if self.open_positions:
            print(lang.t("open_positions"))
            for t in self.open_positions:
                print(
                    lang.t("position_details").format(
                        symbol=t["symbol"],
                        side=t["side"],
                        price=t["price"],
                        sl=f"{t['stop_loss']:.2f}",
                        tp=f"{t['take_profit']:.2f}",
                    )
                )
        else:
            print(lang.t("no_open_positions"))
