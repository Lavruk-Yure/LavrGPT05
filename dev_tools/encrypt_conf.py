# dev_tools/encrypt_conf.py
"""
Шифрування LGE_plain.json → LGE.conf (у форматі pyAesCrypt AES256).
Використовується лише для розробки.
"""

import io
import json
import sys
from pathlib import Path

import pyAesCrypt  # noqa

BASE_DIR = Path(__file__).resolve().parent.parent
PLAIN_PATH = BASE_DIR / "LGE_plain.json"
CONF_PATH = BASE_DIR / "LGE.conf"
AES_BUFFER = 64 * 1024


def encrypt_conf(password: str) -> bool:
    """Шифрує LGE_plain.json → LGE.conf."""
    if not PLAIN_PATH.exists():
        print(f"[Помилка] Файл не знайдено: {PLAIN_PATH}")
        return False

    try:
        with open(PLAIN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as ex:
        print(f"[Помилка читання JSON] {ex!r}")
        return False

    src = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    dst = io.BytesIO()

    try:
        pyAesCrypt.encryptStream(src, dst, password, AES_BUFFER)
        dst.seek(0)
        with open(CONF_PATH, "wb") as fout:
            fout.write(dst.read())

        print(f"✅ Зашифровано успішно: {CONF_PATH}")
        return True

    except Exception as ex:
        print(f"[Помилка шифрування] {ex!r}")
        return False


def main():
    print("🔐 Шифрування LGE_plain.json → LGE.conf")
    print(f"Вихідний файл: {PLAIN_PATH}")

    if not PLAIN_PATH.exists():
        print("❌ Файл не знайдено. Спочатку виконай decrypt_conf.py.")
        sys.exit(1)

    password = input("Введіть пароль для шифрування: ").strip()
    if not password:
        print("❌ Порожній пароль.")
        sys.exit(2)

    if encrypt_conf(password):
        print("💾 Готово.")
    else:
        sys.exit(3)


if __name__ == "__main__":
    main()
