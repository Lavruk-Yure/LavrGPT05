# core/conf_guard.py
"""
ПАТЧ 3.4 — Перевірка LGE05.conf на цілісність без розшифрування.

Логіка:
- JSON → json_error
- Порожній / підозріло малий → corrupted
- Бінарний AES → ok
- Немає → missing
- Помилка → unknown_error
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

ConfState = Literal[
    "ok",
    "missing",
    "json_error",
    "corrupted",
    "unknown_error",
]


def check_conf_state(path: Path) -> ConfState:
    """Перевіряє базову цілісність AES-файлу без спроби дешифрування."""

    if not path.exists():
        return "missing"

    try:
        data = path.open("rb").read(64)
    except Exception:  # noqa
        return "unknown_error"

    # Порожній або явно малий файл
    if not data or len(data) < 16:
        return "corrupted"

    # Текстовий JSON → файл зламаний
    if data.startswith(b"{") or data.startswith(b"["):
        return "json_error"

    # Якщо файл не схожий на JSON → нехай буде OK
    # AES не можна перевірити без пароля, але хоча б виключимо явні проблеми
    return "ok"


def backup_bad_conf(path: Path) -> Path:
    """Переміщує пошкоджений конфіг у *.conf.bad."""
    bad_path = path.with_suffix(".conf.bad")
    try:
        if bad_path.exists():
            bad_path.unlink()
        path.replace(bad_path)
        return bad_path
    except Exception:  # noqa
        return bad_path
