# decrypt_conf.py
# -*- coding: utf-8 -*-
"""
Розшифровка LGE.conf у пам'яті або в тимчасовий JSON.
Використовується лише для розробки.

ВАЖЛИВО:
- використовує ConfigManager (єдине місце, де мають жити правила конфігу),
- виводить статуси так, щоб "битий конфіг" не виглядав як просто "не той пароль".
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _add_project_root_to_syspath(base_dir: Path) -> None:
    base = str(base_dir)
    if base not in sys.path:
        sys.path.insert(0, base)


def _dump_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _read_password() -> str:
    """
    В PyCharm `getpass()` інколи не показує prompt / ламається.
    Тому використовуємо звичайний input().
    """
    try:
        return input("Введіть пароль для розшифрування: ").strip()
    except EOFError:
        return ""


def main() -> int:
    base_dir = _project_root()
    _add_project_root_to_syspath(base_dir)

    # Імпорт після sys.path
    from core.config_manager import ConfigManager  # noqa: WPS433

    conf_path = base_dir / "LGE.conf"
    out_path = base_dir / "LGE_plain.json"

    print("🔐 Розшифровка LGE.conf")
    print(f"Файл: {conf_path}")

    if not conf_path.exists():
        print("❌ Файл конфігу не знайдено.")
        return 1

    password = _read_password()
    if not password:
        print("❌ Пароль не введено.")
        return 2

    mgr = ConfigManager(conf_path)

    try:
        data, status = mgr.load_with_status(password)
    except Exception as e:  # noqa
        print("❌ Внутрішня помилка під час load_with_status().")
        print(f"   {type(e).__name__}: {e}")
        traceback.print_exc()
        return 3

    if status == "ok" and isinstance(data, dict):
        print("\n✅ Успішно розшифровано:\n")
        print(_dump_json(data))

        out_path.write_text(_dump_json(data), encoding="utf-8")
        print(f"\n💾 Збережено у: {out_path}\n")
        return 0

    if status == "missing":
        print("❌ Файл конфігу відсутній.")
        return 2

    if status == "corrupted":
        print("❌ Файл пошкоджений або не є валідним AES Crypt/pyAesCrypt.")
        return 2

    if status == "json_error":
        print("❌ Конфіг розшифровано, але JSON пошкоджений (json_error).")
        return 2

    if status == "wrong_password":
        print("❌ Невірний пароль (або файл пошкоджений).")
        return 2

    if status == "hash_mismatch":
        print(
            "❌ Пароль розшифрував файл, але password_sha256 не збігається "
            "(hash_mismatch)."
        )
        return 2

    print(f"❌ Невідома помилка (status={status!r}).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
