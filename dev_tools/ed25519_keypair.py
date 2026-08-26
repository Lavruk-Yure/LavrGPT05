# dev_tools/ed25519_keypair.py
# -*- coding: utf-8 -*-
"""
Ed25519 keypair generator for LGE licensing (RoadMap23 / Patch 23.1).

- Generates ONE keypair.
- Saves private key as encrypted PEM (PKCS8) protected with passphrase.
- Saves public key as base64 (raw 32 bytes) for embedding into LicenseManager.

IMPORTANT:
- Never commit private key to git.
- Keep passphrase secret.

Files:
- dev_tools/_private_ed25519.pem   (encrypted)
- dev_tools/_public_ed25519.b64    (public, for copy/paste)
"""

from __future__ import annotations

import base64
import getpass
import logging
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEBUG_ED25519_KEYPAIR = False

# ВАЖЛИВО: налаштовуємо логінг ПРИМУСОВО завжди (PyCharm часто вже має хендлери)
logging.basicConfig(
    level=logging.DEBUG if DEBUG_ED25519_KEYPAIR else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    force=True,
)


logger = logging.getLogger(__name__)

PRIVATE_PEM_PATH = (Path(__file__).parent / "_private_ed25519.pem").resolve()
PUBLIC_B64_PATH = (Path(__file__).parent / "_public_ed25519.b64").resolve()


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:  # noqa
        return False


def _safe_getpass(prompt: str) -> str:
    """
    Надійне зчитування пароля.
    1) Пробуємо getpass (якщо консоль нормальна).
    2) Якщо середовище криве (PyCharm/не TTY) — fallback на input() з попередженням.
    """
    # PyCharm часто ламає getpass (prompt/echo/залипання)
    pycharm_hosted = os.environ.get("PYCHARM_HOSTED") == "1"

    # Явно друкуємо prompt і flush, щоб не "пропадав"
    print(prompt, end="", flush=True)

    if (not pycharm_hosted) and _stdin_is_tty():
        try:
            # getpass сам показує prompt, тому ми йому даємо порожній рядок
            # (prompt вже вивели print'ом вище)
            value = getpass.getpass("").strip()
            return value
        except Exception:  # noqa
            # звалюємось у fallback нижче
            pass

    # Fallback: звичайний input (пароль буде видно)
    print(
        "\n[Увага] Консоль не підтримує прихований ввід. Пароль буде видно на екрані."
    )
    return input(">>> ").strip()


def _ask_passphrase() -> bytes:
    p1 = _safe_getpass("Введіть пароль: ")
    if not p1:
        raise SystemExit("Порожній пароль заборонено.")

    p2 = _safe_getpass("Введіть підтвердження пароля: ")
    if p1 != p2:
        raise SystemExit("Паролі не співпадають.")

    return p1.encode("utf-8")


def main() -> int:
    logger.debug("Script: %s", Path(__file__).resolve())
    logger.debug("Python: %s", sys.executable)
    logger.debug("CWD: %s", Path.cwd())
    logger.debug("Private PEM path: %s", PRIVATE_PEM_PATH)
    logger.debug("Public B64 path: %s", PUBLIC_B64_PATH)

    # Захист від випадкового перезапису
    if PRIVATE_PEM_PATH.exists():
        logger.error("Private key already exists: %s", PRIVATE_PEM_PATH)
        logger.error("Aborting to avoid overwrite.")
        print(f"STOP: ключ вже існує: {PRIVATE_PEM_PATH}")
        return 2

    passphrase = _ask_passphrase()

    try:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
        )

        pub_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        pub_b64 = base64.b64encode(pub_raw).decode("ascii")

        # Запис файлів
        PRIVATE_PEM_PATH.write_bytes(priv_pem)
        PUBLIC_B64_PATH.write_text(pub_b64, encoding="utf-8")

    except PermissionError as exc:
        logger.exception("Permission error while writing keys.")
        print(f"ERROR: немає прав на запис у: {PRIVATE_PEM_PATH.parent}")
        print(f"DETAILS: {exc}")
        return 3
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while generating/writing keys.")
        print(f"ERROR: {exc}")
        return 4

    # Явні print — щоб ти бачив фініш у будь-якій консолі
    print("OK: ключі створено")
    print(f"OK: {PRIVATE_PEM_PATH}")
    print(f"OK: {PUBLIC_B64_PATH}")
    print(f"PUBLIC_B64: {pub_b64}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
