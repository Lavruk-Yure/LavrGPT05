# migrate_conf.py
# -*- coding: utf-8 -*-
"""
Міграція LGE05.conf: читає через ConfigManager.load() і одразу зберігає,
щоб прибрати legacy ключі з translator.
"""

from __future__ import annotations

from core.app_paths import ROOT_CONF_PATH
from core.config_manager import ConfigManager


def main() -> None:
    print("🔧 Міграція LGE05.conf")
    print(f"Файл: {ROOT_CONF_PATH}")

    password = input("Введіть пароль для розшифрування: ").strip()
    if not password:
        print("❌ Пароль порожній.")
        return

    cm = ConfigManager(ROOT_CONF_PATH)
    data = cm.load(password)
    if data is None:
        print("❌ Не вдалося завантажити конфіг (пароль/файл/JSON).")
        return

    # load() у твоїй версії вже може зберегти,
    # але ми явно дублюємо save, щоб 100% переписати файл.
    cm.save(data, password)
    print("✅ Готово. Конфіг перемігровано та перезаписано.")


if __name__ == "__main__":
    main()
