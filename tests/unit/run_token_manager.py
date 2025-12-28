# run_token_manager.py
"""
run_token_manager.py

Приклад запуску базових операцій TokenManager:
- Збереження токенів у файл
- Завантаження токенів з файлу
- Спроба оновлення токенів (refresh_if_needed)
"""

import time

from core.token_manager import load_tokens, refresh_if_needed, save_tokens


def main():
    tokens = {
        "access_token": "example_access",
        "refresh_token": "example_refresh",
        "expires_in": 3600,
        "expires_at": int(time.time()) + 3600,
    }

    print("Збереження токенів у файл...")
    save_tokens(tokens)

    print("Завантаження токенів...")
    loaded = load_tokens()
    print("Завантажено токени:", loaded)

    print("Спроба оновлення токенів (refresh_if_needed)...")
    refreshed = refresh_if_needed()
    print("Результат оновлення:", refreshed)


if __name__ == "__main__":
    main()
