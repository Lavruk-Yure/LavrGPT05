"""Ініціалізаційний модуль пакету strategies."""

from __future__ import annotations

# Імпортуємо класи без падіння (модулі можуть бути в розробці)
try:
    from .strategy_dummy import *  # noqa
    from .strategy_sma import *  # noqa
except ImportError:
    pass

__all__ = ["strategy_dummy", "strategy_sma"]
