# core\logger_monitor.py
# --- LavrGPT05, Python 3.13, стиль flake8 + black ---

import csv
import logging
from datetime import datetime
from pathlib import Path

from core.lang_manager import LangManager

lang = LangManager()


def setup_logger(name: str, log_file: str | None = None, level=logging.INFO):
    """Створює або повертає наявний логер для підсистеми LavrGPT05."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Якщо хендлери вже існують — не дублюємо
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Консольний лог
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Файловий лог (якщо задано)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class LoggerMonitor:
    """Веде журнал угод у пам'яті та CSV."""

    def __init__(self, logfile: str = "trades_log.csv"):
        self.trades: list[list[str | float]] = []
        self.logfile = Path(logfile)

        # Якщо файл не існує — створюємо з заголовком
        if not self.logfile.exists():
            with open(self.logfile, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "symbol",
                        "side",
                        "entry",
                        "size",
                        "SL",
                        "TP",
                        "status",
                        "balance",
                    ]
                )

    def log_trade(self, order: dict, balance: float) -> None:
        """Додає угоду у пам'ять і записує в CSV."""
        entry = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            order.get("symbol", "N/A"),
            order.get("side", "N/A"),
            order.get("price", 0.0),
            order.get("size", 0.0),
            order.get("stop_loss", 0.0),
            order.get("take_profit", 0.0),
            order.get("status", "N/A"),
            round(balance, 2),
        ]
        self.trades.append(entry)
        with open(self.logfile, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(entry)

    def print_summary(self, balance: float) -> None:
        """Виводить короткий підсумок усіх угод у консоль."""
        print("\n===== MONITOR =====")
        print(f"Trades executed: {len(self.trades)}")
        print(f"Current balance: {balance:.2f}")
        print("===================\n")

        for t in self.trades:
            print(
                f"{t[1]} | {t[2]} | entry={t[3]} | "
                f"SL={t[5]:.2f} | TP={t[6]:.2f} | "
                f"status={t[7]} | balance={t[8]:.2f}"
            )
