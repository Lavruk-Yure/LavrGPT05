# office_paths.py
# -*- coding: utf-8 -*-
"""
office_paths — централізовані шляхи LGEOffice.

Єдине місце, де визначаються:
- робоча директорія LGEOffice
- config
- db
- keys
- licenses
- logs
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_office_dir() -> Path:
    """
    Робоча директорія LGEOffice.

    У dev:
    - каталог office/

    У PyInstaller onefile/onedir:
    - каталог, де лежить LGEOffice.exe
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def get_config_path() -> Path:
    return get_office_dir() / "office_config.json"


def get_db_path() -> Path:
    return get_office_dir() / "office.db"


def get_keys_dir() -> Path:
    return get_office_dir() / "keys"


def get_private_key_path() -> Path:
    return get_keys_dir() / "_private_ed25519.pem"


def get_public_key_path() -> Path:
    return get_keys_dir() / "_public_ed25519.b64"


def get_licenses_dir() -> Path:
    return get_office_dir() / "licenses"


def get_logs_dir() -> Path:
    return get_office_dir() / "logs"
