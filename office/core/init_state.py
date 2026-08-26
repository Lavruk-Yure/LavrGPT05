# init_state.py
# -*- coding: utf-8 -*-
"""
init_state — перевірка стану готовності LGEOffice.

Важливо:
- office_config.json може мати initialized=false під час першого проходу ініціалізації.
- Готовність (ready) визначається наявністю БД (schema_version) і ключів.
- initialized=true — це вже фінальний прапорець,
  який ставить InitWindow після успішної готовності.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from office.core.db import is_db_ready
from office.core.office_paths import (
    get_office_dir,
    get_private_key_path,
    get_public_key_path,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InitState:
    initialized: bool
    reason: str


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не вдалося прочитати JSON: %s | %s", path, exc)
        return {}


def check_initialized(config_path: Path) -> InitState:
    """
    Повертає initialized=True, якщо система ГОТОВА (db + keys).
    Поле config["initialized"] тут не є блокуючим, бо воно виставляється в кінці.
    """
    if not config_path.exists():
        return InitState(False, "office_config.json відсутній")

    office_dir = get_office_dir()

    if not is_db_ready(office_dir):
        return InitState(False, "БД відсутня або schema_version не співпадає")

    private_key = get_private_key_path()
    public_key = get_public_key_path()

    if not private_key.exists():
        return InitState(False, "Відсутній приватний ключ: keys/_private_ed25519.pem")

    if not public_key.exists():
        return InitState(False, "Відсутній публічний ключ: keys/_public_ed25519.b64")

    return InitState(True, "db + keys OK")
