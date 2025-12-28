"""Ініціалізаційний модуль пакету ui."""

from __future__ import annotations

# Імпортуємо класи без падіння (модулі можуть бути в розробці)
try:
    from .register_lang import *  # noqa
    from .ui_login import *  # noqa
    from .ui_main_app import *  # noqa
    from .ui_register import *  # noqa
    from .ui_settings_dialog import *  # noqa
    from .ui_splash import *  # noqa
    from .ui_test_styles import *  # noqa
except ImportError:
    pass

__all__ = [
    "register_lang", "ui_login", "ui_main_app", "ui_register", "ui_settings_dialog",
    "ui_splash", "ui_test_styles"
]
