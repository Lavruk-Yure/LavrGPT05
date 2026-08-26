# init_actions.py
# -*- coding: utf-8 -*-
"""
init_actions — дії ініціалізації LGEOffice.

Patch 29.4 Fix:
1) Створюємо потрібні директорії office/ (мінімум: keys, licenses, logs).
2) Створюємо office_config.json (initialized=false) з salt+hash.
3) Створюємо Ed25519 keys (private PEM зашифрований паролем адміністратора).
4) БД створюється окремо (office.core.db.init_db), а initialized=true ставиться
   лише після повної перевірки (config + db + keys) у InitWindow.
"""

from __future__ import annotations

import logging
from pathlib import Path

from office.core.key_manager import ensure_ed25519_keys
from office.core.office_config import OfficeConfig, write_config
from office.core.office_paths import get_config_path, get_office_dir
from office.core.security import hash_password, make_salt

logger = logging.getLogger(__name__)


def ensure_dirs(office_dir: Path) -> None:
    """
    1) Створює базові директорії LGEOffice (мінімум потрібного).
    """
    for name in ("keys", "licenses", "logs"):
        (office_dir / name).mkdir(parents=True, exist_ok=True)


def initialize_office(admin_password: str) -> None:
    """
    1) Створити директорії.
    2) Створити office_config.json (initialized=false) з salt+hash.
    3) Створити/відновити Ed25519 keys (private PEM зашифрований паролем).
    """
    office_dir = get_office_dir()
    cfg_path = get_config_path()

    # 1) dirs
    ensure_dirs(office_dir)

    # 2) config (initialized=false)
    salt = make_salt()
    pwd_hash = hash_password(admin_password, salt)

    cfg = OfficeConfig(
        initialized=False,
        password_salt=salt,
        password_hash=pwd_hash,
    )
    write_config(cfg_path, cfg)

    # 3) keys (критично для першого запуску)
    ensure_ed25519_keys(admin_password=admin_password)
    logger.info("Ed25519 keys ensured (first init).")

    logger.info("Ініціалізація завершена: %s", cfg_path)
