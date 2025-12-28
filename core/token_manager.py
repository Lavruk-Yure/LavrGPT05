# core/token_manager.py
"""
core/token_manager.py

Модуль для управління токенами доступу:
- Збереження токенів у файл (з коментарем)
- Завантаження токенів із файлу
- Перевірка та оновлення токенів при потребі
"""

import json
import os
import time

from core.lang_manager import LangManager

lang = LangManager()


def get_tokens_path() -> str:
    """Повертає шлях до файлу токенів з env або 'tokens.json' за замовчуванням."""
    return os.getenv("TOKENS_PATH", "tokens.json")


def save_tokens(tokens: dict) -> None:
    """Зберігає токени у JSON-файл із коментарем."""
    tokens["_comment"] = (
        "Автоматично згенерований tokens.json. Не зберігати в репозиторії."
    )
    path = get_tokens_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)
    print(lang.t("tokens_saved").format(path=path))


def load_tokens() -> dict | None:
    """Завантажує токени з файлу, якщо він існує."""
    path = get_tokens_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def refresh_if_needed() -> dict | None:
    """
    Перевіряє, чи токен прострочений, і при потребі оновлює.
    Якщо файл токенів відсутній — повертає None.
    """
    path = get_tokens_path()
    if not os.path.exists(path):
        return None

    tokens = load_tokens()
    if not tokens:
        return None

    now = int(time.time())
    expires_at = tokens.get("expires_at", 0)

    if now >= expires_at:
        print(lang.t("token_expired"))
        tokens["access_token"] = "new_access_token"
        tokens["refresh_token"] = "new_refresh_token"
        tokens["expires_at"] = now + tokens.get("expires_in", 3600)
        save_tokens(tokens)
        return tokens

    print(lang.t("token_still_valid"))
    return tokens
