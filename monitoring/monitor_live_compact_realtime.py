# monitor_live_compact_realtime.py
import os
import time


class LiveMonitorCompactRealtime:
    def __init__(self, refresh_delay=0.1):
        self.refresh_delay = refresh_delay

    def update_bar(self, bar_index, candle, trades, balance):
        # Очистка екрану (для Windows і Linux)
        os.system("cls" if os.name == "nt" else "clear")

        line = (
            f"Bar {bar_index + 1} |"
            f" Close: {candle['close']} |"
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
        time.sleep(self.refresh_delay)
