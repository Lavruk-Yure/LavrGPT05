"""Ініціалізаційний модуль пакету dev_tools."""

from __future__ import annotations

# Імпортуємо класи без падіння (модулі можуть бути в розробці)
try:
    from .flake8_check import *  # noqa
    from .flake8_check_all import *  # noqa
    from .init_generator import *  # noqa
except ImportError:
    pass

__all__ = ["flake8_check", "flake8_check_all", "init_generator"]
