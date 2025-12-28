# core/config_collection.py
# -*- coding: utf-8 -*-
"""
ConfigCollection — робота з конфігурацією LGE05.conf у памʼяті.

Підтримує:
- get(section, key)
- set(section, key, value)
- delete(section, key)
- auto-create section on set
- created_at / updated_at (автоматично)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict


class ConfigCollection:
    """Колекція (структура) конфігу в памʼяті."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data

        # гарантовано створені метадані
        if "created_at" not in self.data:
            self.data["created_at"] = datetime.now(UTC).isoformat()

        if "updated_at" not in self.data:
            self.data["updated_at"] = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    def get(self, section: str | None, key: str) -> Any:
        """Отримати значення. Якщо немає — повернути None."""
        if not key:
            return None

        if not section:
            return self.data.get(key)

        sec = self.data.get(section)
        if not isinstance(sec, dict):
            return None

        return sec.get(key)

    # ------------------------------------------------------------------
    def set(self, section: str | None, key: str, value: Any) -> None:
        """Встановити значення. Якщо секції немає — створити."""
        if not key:
            raise ValueError("Key must not be empty")

        if not section:
            self.data[key] = value
        else:
            sec = self.data.get(section)
            if not isinstance(sec, dict):
                self.data[section] = {}
                sec = self.data[section]

            sec[key] = value

        self.data["updated_at"] = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    def delete(self, section: str | None, key: str) -> None:
        """Видалити ключ. Якщо секція не існує — нічого не робимо."""
        if not key:
            return

        if not section:
            self.data.pop(key, None)
        else:
            sec = self.data.get(section)
            if isinstance(sec, dict):
                sec.pop(key, None)

        self.data["updated_at"] = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    def raw(self) -> Dict[str, Any]:
        """Повертає внутрішній dict."""
        return self.data
