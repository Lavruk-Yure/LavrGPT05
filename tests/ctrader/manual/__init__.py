# __init__.py
"""Ініціалізаційний модуль пакету ctrader."""

from __future__ import annotations

# Імпортуємо модулі без падіння; частина файлів може бути в розробці.
try:
    from .run_ctrader_01_connect import *  # noqa
    from .run_ctrader_02_auth_app import *  # noqa
    from .run_ctrader_02b_list_accounts import *  # noqa
    from .run_ctrader_03_auth_account import *  # noqa
    from .run_ctrader_04_get_symbols import *  # noqa
    from .run_ctrader_05_positions import *  # noqa
    from .run_ctrader_06_place_order import *  # noqa
    from .run_ctrader_06a_place_order_login import *  # noqa
    from .run_ctrader_07_get_positions import *  # noqa
    from .run_ctrader_08_modify_position_sltp import *  # noqa
    from .run_ctrader_09_session_console import *  # noqa
except ImportError:
    pass

__all__ = [
    "run_ctrader_01_connect",
    "run_ctrader_02_auth_app",
    "run_ctrader_02b_list_accounts",
    "run_ctrader_03_auth_account",
    "run_ctrader_04_get_symbols",
    "run_ctrader_05_positions",
    "run_ctrader_06_place_order",
    "run_ctrader_06a_place_order_login",
    "run_ctrader_07_get_positions",
    "run_ctrader_08_modify_position_sltp",
    "run_ctrader_09_session_console",
]
