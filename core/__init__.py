"""Ініціалізаційний модуль пакету core."""

from __future__ import annotations

# Імпортуємо класи без падіння (модулі можуть бути в розробці)
try:
    from .ai_translator import *  # noqa
    from .app_paths import *  # noqa
    from .backtester import *  # noqa
    from .bot_skeleton import *  # noqa
    from .conf_guard import *  # noqa
    from .config_collection import *  # noqa
    from .config_manager import *  # noqa
    from .config_trades import *  # noqa
    from .data_manager import *  # noqa
    from .encryption_manager import *  # noqa
    from .execution import *  # noqa
    from .lang_manager import *  # noqa
    from .logger_monitor import *  # noqa
    from .login_logic import *  # noqa
    from .main_logic import *  # noqa
    from .order_manager import *  # noqa
    from .register_logic import *  # noqa
    from .risk_manager import *  # noqa
    from .session_state import *  # noqa
    from .settings_dialog import *  # noqa
    from .splash_runner import *  # noqa
    from .token_manager import *  # noqa
    from .ui_translator import *  # noqa
except ImportError:
    pass

__all__ = [
    "ai_translator", "app_paths", "backtester", "bot_skeleton", "conf_guard",
    "config_collection", "config_manager", "config_trades", "data_manager",
    "encryption_manager", "execution", "lang_manager", "logger_monitor", "login_logic",
    "main_logic", "order_manager", "register_logic", "risk_manager", "session_state",
    "settings_dialog", "splash_runner", "token_manager", "ui_translator"
]
