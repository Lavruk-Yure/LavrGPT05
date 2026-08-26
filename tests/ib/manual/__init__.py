# __init__.py
"""Ініціалізаційний модуль пакету manual."""

from __future__ import annotations

# Імпортуємо модулі без падіння; частина файлів може бути в розробці.
try:
    from .run_ib_01_handshake import *  # noqa
    from .run_ib_02_account_summary import *  # noqa
    from .run_ib_03_positions import *  # noqa
    from .run_ib_04_market_data import *  # noqa
    from .run_ib_05_historical_data import *  # noqa
    from .run_ib_06_order_simulation import *  # noqa
except ImportError:
    pass

__all__ = [
    "run_ib_01_handshake", "run_ib_02_account_summary", "run_ib_03_positions",
    "run_ib_04_market_data", "run_ib_05_historical_data", "run_ib_06_order_simulation"
]
