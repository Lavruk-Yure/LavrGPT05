# datetime_utils.py
# -*- coding: utf-8 -*-
"""
Єдина нормалізація дат/часу для всієї системи LGE Office.

Формат системи:
YYYY-MM-DD HH:MM

UTC використовується скрізь.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# -----------------------------------------------------------
# Основний формат системи
# -----------------------------------------------------------

DATETIME_FORMAT = "%Y-%m-%d %H:%M"


# -----------------------------------------------------------
# Поточний UTC час
# -----------------------------------------------------------


def utc_now_str() -> str:
    """
    Поточний час UTC у форматі системи.

    Returns:
        str
    """
    return datetime.now(timezone.utc).strftime(DATETIME_FORMAT)


# -----------------------------------------------------------
# Нормалізація будь-якого datetime
# -----------------------------------------------------------


def normalize_datetime(dt: datetime) -> str:
    """
    Перетворити datetime у стандартний рядок системи.

    Args:
        dt: datetime

    Returns:
        str
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).strftime(DATETIME_FORMAT)


def normalize_datetime_text(value: str) -> str:
    """
    Нормалізувати введений користувачем текст дати/часу
    у канонічний формат системи:
    YYYY-MM-DD HH:MM

    Підтримує:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - DD.MM.YYYY
    - DD.MM.YYYY HH:MM
    """
    text = value.strip()
    if not text:
        raise ValueError("Дата/час обов’язкові.")

    formats = (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
    )

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                dt = dt.replace(hour=0, minute=0)
            return dt.strftime(DATETIME_FORMAT)
        except ValueError:
            continue

    raise ValueError(
        "Невірний формат дати/часу. " "Приклад: 2026-03-26 10:30 або 26.03.2026 10:30"
    )


# -----------------------------------------------------------
# Парсинг рядка у datetime
# -----------------------------------------------------------


def parse_datetime(value: str) -> datetime:
    """
    Перетворити рядок у datetime UTC.

    Args:
        value: str

    Returns:
        datetime
    """
    dt = datetime.strptime(value, DATETIME_FORMAT)
    return dt.replace(tzinfo=timezone.utc)


# -----------------------------------------------------------
# Перевірка валідності формату
# -----------------------------------------------------------


def is_valid_datetime(value: str) -> bool:
    """
    Перевірити, чи текст можна нормалізувати
    до канонічного формату системи.
    """
    try:
        normalize_datetime_text(value)
        return True
    except ValueError:
        return False


# -----------------------------------------------------------
# Нормалізація optional datetime
# -----------------------------------------------------------


def normalize_optional_datetime(
    dt: Optional[datetime],
) -> Optional[str]:
    """
    Безпечна нормалізація optional datetime.

    Args:
        dt: datetime | None

    Returns:
        str | None
    """
    if dt is None:
        return None

    return normalize_datetime(dt)
