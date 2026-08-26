"""Ініціалізаційний модуль пакету dev_tools."""

from __future__ import annotations

# Імпортуємо класи без падіння (модулі можуть бути в розробці)
try:
    from .build_all import *  # noqa
    from .ed25519_keypair import *  # noqa
    from .init_db import *  # noqa
    from .license_keygen import *  # noqa
    from .test_repo import *  # noqa
except ImportError:
    pass

__all__ = ["build_all", "ed25519_keypair", "init_db", "license_keygen", "test_repo"]
