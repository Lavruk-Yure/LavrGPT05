# license_keygen.py
# -*- coding: utf-8 -*-
"""
License key generator for LGE (Ed25519)
RoadMap23 / Patch 23.2a (console-stable)

Key format:
    LICENSE_KEY = payload_b64.signature_b64
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# ===== CONFIG =====

DEBUG_LICENSE_KEYGEN = False

PRIVATE_PEM_PATH = Path(__file__).parent / "_private_ed25519.pem"
PRIVATE_RAW_PATH = Path(__file__).parent / "_private_ed25519.key"

# ===== LOGGING =====

logging.basicConfig(
    level=logging.DEBUG if DEBUG_LICENSE_KEYGEN else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


# ===== INPUT HELPERS =====


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:  # noqa
        return False


def _ask_secret(prompt: str) -> str:
    """
    Надійний консольний ввід секрету.
    getpass НЕ використовується — він ламається у PyCharm / Windows.
    """
    print(prompt, end="", flush=True)
    if _stdin_is_tty() and os.environ.get("PYCHARM_HOSTED") != "1":
        try:
            import getpass

            return getpass.getpass("").strip()
        except Exception:  # noqa
            pass

    print("\n[INFO] Прихований ввід недоступний, пароль буде видно.")
    return input(">>> ").strip()


def ask(prompt: str, default: Optional[str] = None) -> str:
    if default:
        s = input(f"{prompt} [{default}]: ").strip()
        return s or default
    return input(f"{prompt}: ").strip()


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    s = ask(f"{prompt} ({'/'.join(choices)})", default).lower()
    return s if s in choices else default


# ===== CORE =====


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def load_private_key() -> Ed25519PrivateKey:
    if PRIVATE_PEM_PATH.exists():
        logger.debug("Loading private key from PEM: %s", PRIVATE_PEM_PATH)
        pw_text = _ask_secret("Введіть пароль для private key: ")

        # Захист від помилкового "вставив PEM/BASE64 замість пароля"
        if (
            ("BEGIN" in pw_text)
            or pw_text.strip().startswith("MIG")
            or len(pw_text) > 128
        ):
            raise SystemExit(
                "Схоже, ти вставив PEM/ключовий текст замість пароля. "
                "Введи саме пароль, який задавав у ed25519_keypair.py."
            )

        password = pw_text.encode("utf-8")

        try:
            key = serialization.load_pem_private_key(
                PRIVATE_PEM_PATH.read_bytes(),
                password=password,
            )
        except Exception as exc:
            raise SystemExit(f"Помилка розшифрування private key: {exc}") from exc

        if not isinstance(key, Ed25519PrivateKey):
            raise SystemExit("Файл не є Ed25519 private key.")

        return key

    if PRIVATE_RAW_PATH.exists():
        raw = PRIVATE_RAW_PATH.read_bytes()
        if len(raw) != 32:
            raise SystemExit("Legacy private key має неправильний розмір.")
        return Ed25519PrivateKey.from_private_bytes(raw)

    raise SystemExit("Private key не знайдено.")


def main() -> int:
    print("=== LGE License Key Generator ===")

    private_key = load_private_key()

    edition = ask_choice("Edition", ["pro", "pro_plus"], "pro")
    source = ask_choice("Source", ["manual", "gumroad", "ctrader"], "manual")
    order_id = ask("Order ID", "TEST-001")
    email = ask("Customer email", "lavrhome@gmail.com")

    version_min = ask("Min app version (optional)", "") or None
    expires_at = ask("Expires at ISO (optional)", "") or None
    note = ask("Note (optional)", "") or None

    payload: Dict[str, Any] = {
        "product": "LGE",
        "edition": edition,
        "source": source,
        "order_id": order_id,
        "email": email,
        "issued_at": datetime.now(UTC).isoformat(),
        "version_min": version_min,
        "expires_at": expires_at,
        "note": note,
    }

    payload_bytes = canonical_json(payload)
    signature = private_key.sign(payload_bytes)

    license_key = f"{b64url(payload_bytes)}.{b64url(signature)}"

    print("\nLICENSE_KEY:")
    print(license_key)

    print("\nPayload:")
    print(payload_bytes.decode("utf-8"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
