# core/session_state.py
# -*- coding: utf-8 -*-
"""
Глобальний стан сесії LGE05.

Зберігає:
- поточну колекцію конфігу
- поточний пароль (робочий ключ для збереження)
"""

from __future__ import annotations

from typing import Optional

from core.config_manager import ConfigCollection

CURRENT_CONFIG: Optional[ConfigCollection] = None
CURRENT_PASSWORD: Optional[str] = None
