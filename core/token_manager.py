# token_manager.py
"""
core/token_manager.py

Модуль для управління токенами доступу:
- Збереження токенів у файл (з коментарем)
- Завантаження токенів із файлу
- Перевірка та оновлення токенів при потребі
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from core.lang_manager import LangManager

logger = logging.getLogger(__name__)

lang = LangManager()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKENS_PATH = PROJECT_ROOT / "tokens" / "tokens.json"

INVALID_TOKEN_PLACEHOLDERS = {
    "",
    "new_access_token",
    "new_refresh_token",
    "access_token",
    "refresh_token",
}


def get_tokens_path() -> Path:
    """Повертає шлях до файлу токенів (env або project_root/tokens/tokens.json)."""
    try:
        import os

        env_path = os.getenv("TOKENS_PATH", "").strip()
    except (OSError, RuntimeError):
        env_path = ""
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_TOKENS_PATH


def save_tokens(tokens: dict) -> None:
    """Зберігає токени у JSON-файл із коментарем."""
    tokens["_comment"] = (
        "Автоматично згенерований tokens.json. Не зберігати в репозиторії."
    )
    path = get_tokens_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)
    print(lang.t("tokens_saved").format(path=str(path)))


def load_tokens() -> dict | None:
    """Завантажує токени з файлу, якщо він існує."""
    path = get_tokens_path()
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_access_token_valid(tokens: dict | None) -> bool:
    """Перевіряє, чи є придатний access_token у tokens.json."""
    if not tokens:
        return False

    access_token = str(tokens.get("access_token", "")).strip()
    refresh_token = str(tokens.get("refresh_token", "")).strip()
    if access_token in INVALID_TOKEN_PLACEHOLDERS:
        return False
    if refresh_token in INVALID_TOKEN_PLACEHOLDERS:
        return False

    try:
        expires_at = int(tokens.get("expires_at", 0))
    except (TypeError, ValueError):
        expires_at = 0

    if expires_at <= 0:
        return False

    return int(time.time()) < expires_at


def refresh_if_needed() -> dict | None:
    """
    Повертає чинні токени або None.

    Важливо: ця функція більше не створює фейкові токени.
    Реальне оновлення/отримання токенів виконується manual auth flow.
    """
    path = get_tokens_path()
    if not path.exists():
        return None

    tokens = load_tokens()
    if not tokens:
        return None

    if not is_access_token_valid(tokens):
        logger.debug("cTrader access token is expired or invalid.")
        return None

    logger.debug("cTrader access token is still valid.")
    return tokens
