# ctrader_symbols.py
"""
Таблиця cTrader SYMBOL_ID для поточного demo-рахунку.

Джерело:
- run_ctrader_04_get_symbols.py
- symbolCategoryId == 1 (Forex)

Увага:
1) Це НЕ універсальні значення.
2) Вони прив'язані до поточного брокера/рахунку.
3) Для іншого рахунку таблицю треба перевіряти повторно.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CTraderSymbol:
    symbol_id: int
    symbol_name: str
    enabled: bool


CTRADER_FOREX_SYMBOLS: tuple[CTraderSymbol, ...] = (
    CTraderSymbol(1, "EURUSD", True),
    CTraderSymbol(2, "GBPUSD", True),
    CTraderSymbol(4, "USDJPY", True),
    CTraderSymbol(5, "AUDUSD", True),
    CTraderSymbol(8, "USDCAD", True),
    CTraderSymbol(6, "USDCHF", True),
    CTraderSymbol(18, "AUDCAD", True),
    CTraderSymbol(23, "AUDCHF", True),
    CTraderSymbol(38, "AUDDKK", False),
    CTraderSymbol(11, "AUDJPY", True),
    CTraderSymbol(20, "AUDNZD", True),
    CTraderSymbol(1001, "AUDSGD", True),
    CTraderSymbol(15, "CADJPY", True),
    CTraderSymbol(27, "CADCHF", True),
    CTraderSymbol(13, "CHFJPY", True),
    CTraderSymbol(1002, "CHFSGD", True),
    CTraderSymbol(14, "EURAUD", True),
    CTraderSymbol(17, "EURCAD", True),
    CTraderSymbol(10, "EURCHF", True),
    CTraderSymbol(1024, "EURCZK", False),
    CTraderSymbol(1003, "EURDKK", True),
    CTraderSymbol(1004, "EURHKD", True),
    CTraderSymbol(34, "EURHUF", False),
    CTraderSymbol(9, "EURGBP", True),
    CTraderSymbol(3, "EURJPY", True),
    CTraderSymbol(1022, "EURMXN", False),
    CTraderSymbol(33, "EURNOK", True),
    CTraderSymbol(26, "EURNZD", True),
    CTraderSymbol(1005, "EURPLN", True),
    CTraderSymbol(1023, "EURRUB", False),
    CTraderSymbol(31, "EURSEK", True),
    CTraderSymbol(1006, "EURSGD", True),
    CTraderSymbol(1007, "EURTRY", True),
    CTraderSymbol(1008, "EURZAR", True),
    CTraderSymbol(16, "GBPAUD", True),
    CTraderSymbol(19, "GBPCAD", True),
    CTraderSymbol(40, "GBPCHF", True),
    CTraderSymbol(7, "GBPJPY", True),
    CTraderSymbol(37, "GBPNOK", True),
    CTraderSymbol(25, "GBPNZD", True),
    CTraderSymbol(32, "GBPSGD", True),
    CTraderSymbol(1021, "GBPZAR", False),
    CTraderSymbol(1009, "GBPDKK", True),
    CTraderSymbol(1010, "GBPSEK", True),
    CTraderSymbol(1014, "NOKJPY", True),
    CTraderSymbol(1011, "NOKSEK", True),
    CTraderSymbol(30, "NZDCAD", True),
    CTraderSymbol(39, "NZDCHF", True),
    CTraderSymbol(21, "NZDJPY", True),
    CTraderSymbol(1025, "NZDSGD", False),
    CTraderSymbol(12, "NZDUSD", True),
    CTraderSymbol(1015, "SEKJPY", True),
    CTraderSymbol(1016, "SGDJPY", True),
    CTraderSymbol(1020, "USDCNH", True),
    CTraderSymbol(1018, "USDCZK", True),
    CTraderSymbol(36, "USDDKK", True),
    CTraderSymbol(1000, "USDHKD", True),
    CTraderSymbol(1017, "USDHUF", True),
    CTraderSymbol(24, "USDMXN", True),
    CTraderSymbol(22, "USDNOK", True),
    CTraderSymbol(35, "USDPLN", True),
    CTraderSymbol(1019, "USDRUB", False),
    CTraderSymbol(29, "USDSEK", True),
    CTraderSymbol(28, "USDSGD", True),
    CTraderSymbol(1026, "USDTHB", True),
    CTraderSymbol(1012, "USDTRY", True),
    CTraderSymbol(1013, "USDZAR", True),
    CTraderSymbol(10031, "GBPTRY", True),
    CTraderSymbol(10023, "EURUSDt", False),
)

CTRADER_FOREX_BY_NAME: dict[str, CTraderSymbol] = {
    item.symbol_name.upper(): item for item in CTRADER_FOREX_SYMBOLS
}

CTRADER_FOREX_ID_BY_NAME: dict[str, int] = {
    item.symbol_name.upper(): item.symbol_id for item in CTRADER_FOREX_SYMBOLS
}

CTRADER_FOREX_NAME_BY_ID: dict[int, str] = {
    item.symbol_id: item.symbol_name for item in CTRADER_FOREX_SYMBOLS
}


def get_symbol_id(symbol_name: str) -> int:
    """Повернути SYMBOL_ID за назвою інструмента."""
    key = symbol_name.strip().upper()
    if key not in CTRADER_FOREX_BY_NAME:
        raise KeyError(f"Невідомий Forex symbol: {symbol_name}")
    item = CTRADER_FOREX_BY_NAME[key]
    return item.symbol_id


def get_symbol_name(symbol_id: int) -> str:
    """Повернути назву інструмента за SYMBOL_ID."""
    item = CTRADER_FOREX_NAME_BY_ID.get(symbol_id)
    if item is None:
        raise KeyError(f"Невідомий Forex symbol_id: {symbol_id}")
    return item


def is_symbol_enabled(symbol_name: str) -> bool:
    """Перевірити, чи symbol увімкнений на поточному рахунку."""
    key = symbol_name.strip().upper()
    if key not in CTRADER_FOREX_BY_NAME:
        raise KeyError(f"Невідомий Forex symbol: {symbol_name}")
    return CTRADER_FOREX_BY_NAME[key].enabled


def get_enabled_symbol_id(symbol_name: str) -> int:
    """Повернути SYMBOL_ID тільки для активного symbol."""
    key = symbol_name.strip().upper()
    if key not in CTRADER_FOREX_BY_NAME:
        raise KeyError(f"Невідомий Forex symbol: {symbol_name}")

    item = CTRADER_FOREX_BY_NAME[key]
    if not item.enabled:
        raise ValueError(
            f"Symbol '{item.symbol_name}' присутній у таблиці, але зараз disabled."
        )

    return item.symbol_id


def list_enabled_symbols() -> list[str]:
    """Список увімкнених Forex symbols."""
    return [item.symbol_name for item in CTRADER_FOREX_SYMBOLS if item.enabled]


logger.debug(
    "cTrader Forex symbols loaded: total=%s enabled=%s",
    len(CTRADER_FOREX_SYMBOLS),
    len(list_enabled_symbols()),
)
