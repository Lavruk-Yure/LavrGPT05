# core/config_trades.py
"""
Конфігураційний модуль для торгової системи LavrGPT05.

Містить параметри:
- стратегії;
- ризик-менеджменту;
- візуалізації (моніторингу);
- шаблони угод і загальні торгові налаштування.

Також реалізує клас ConfigTrades — обгортку для зручного доступу до всіх секцій.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

# --- Основна конфігурація угод ---
TRADE_CONF: Dict[str, Any] = {
    "balance": 10_000,
    "risk_per_trade": 0.01,
    "sma_fast": 3,
    "sma_slow": 5,
    "sl_coef": 0.01,
    "rr_ratio": 2.0,
    "data_file": "data.csv",
    "bars_to_close": 3,
}

# --- Шаблон угоди за замовчуванням ---
DEFAULT_TRADE_TEMPLATE: Dict[str, Any] = {
    "symbol": "TEST",
    "side": None,  # 'LONG' або 'SHORT'
    "entry_price": 0.0,
    "stop_loss": 0.0,
    "take_profit": 0.0,
    "open_index": 0,
    "balance_before": 0.0,
    "balance_after": 0.0,
    "profit": 0.0,
    "status": "OPEN",  # 'OPEN' або 'CLOSED'
}

# --- Параметри стратегії ---
STRATEGY: Dict[str, Any] = {
    "sma_fast": 3,
    "sma_slow": 5,
    "sl_coef": 0.01,
    "rr_ratio": 2.0,
}

# --- Параметри ризик-менеджера ---
RISK_MANAGER: Dict[str, Any] = {
    "balance": 10_000,
    "risk_per_trade": 0.01,
    "max_drawdown": 0.2,  # 20%
    "max_trades_per_day": 5,
}

# --- Параметри графічного монітора ---
GRAPH: Dict[str, Any] = {
    "width": 10,
    "height": 6,
    "title": "Trading Monitor",
    "update_interval": 100,  # мс між оновленнями
}

# --- Параметри торгових сесій ---
TRADES: Dict[str, Any] = {
    "risk_per_trade": 0.01,
    "balance": 10_000,
    "sma_fast": 3,
    "sma_slow": 5,
    "sl_coef": 0.01,
    "rr_ratio": 2.0,
    "close_after_bars": 3,
}


# --- Обгортка для централізованого доступу до всіх секцій ---
@dataclass
class ConfigTrades:
    """Обгортка-конфіг для торгової підсистеми (єдине джерело параметрів)."""

    trade_conf: Dict[str, Any] = field(default_factory=lambda: TRADE_CONF.copy())
    default_trade_template: Dict[str, Any] = field(
        default_factory=lambda: DEFAULT_TRADE_TEMPLATE.copy()
    )
    strategy: Dict[str, Any] = field(default_factory=lambda: STRATEGY.copy())
    risk_manager: Dict[str, Any] = field(default_factory=lambda: RISK_MANAGER.copy())
    graph: Dict[str, Any] = field(default_factory=lambda: GRAPH.copy())
    trades: Dict[str, Any] = field(default_factory=lambda: TRADES.copy())

    def summary(self) -> str:
        """Повертає короткий текстовий опис конфігурації."""
        return (
            f"Balance: {self.risk_manager['balance']}, "
            f"Risk/trade: {self.risk_manager['risk_per_trade']}, "
            f"Strategy SMA({self.strategy['sma_fast']}, {self.strategy['sma_slow']}), "
            f"RR={self.strategy['rr_ratio']}"
        )


# --- Готовий інстанс для зручного імпорту ---
DEFAULT_CONFIG = ConfigTrades()


# --- Експортовані імена ---
__all__ = [
    "TRADE_CONF",
    "DEFAULT_TRADE_TEMPLATE",
    "STRATEGY",
    "RISK_MANAGER",
    "GRAPH",
    "TRADES",
    "ConfigTrades",
    "DEFAULT_CONFIG",
]
