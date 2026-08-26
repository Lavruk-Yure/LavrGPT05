# key_manager.py
# -*- coding: utf-8 -*-
"""
key_manager — керування Ed25519 ключами для LGEOffice.

Правила:
1) keys/_private_ed25519.pem — приватний ключ (PEM)
   ЗАВЖДИ зашифрований паролем адміністратора.
2) keys/_public_ed25519.b64 — публічний ключ (base64) без шифрування.
3) ensure_ed25519_keys() створює keys/ та генерує ключі, якщо їх немає.
"""

from __future__ import annotations

import base64
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from office.core.office_paths import (
    get_keys_dir,
    get_private_key_path,
    get_public_key_path,
)

logger = logging.getLogger(__name__)


def ensure_ed25519_keys(*, admin_password: str) -> None:
    """
    Гарантує, що пара ключів Ed25519 існує.

    Якщо файлів немає:
    - генерує Ed25519 private key
    - зберігає PEM приватного ключа, зашифрований паролем адміністратора
    - зберігає публічний ключ як base64
    """
    keys_dir = get_keys_dir()
    keys_dir.mkdir(parents=True, exist_ok=True)

    priv_path = get_private_key_path()
    pub_path = get_public_key_path()

    if priv_path.exists() and pub_path.exists():
        return

    if not admin_password:
        raise ValueError("admin_password is required to generate encrypted private key")

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    enc = serialization.BestAvailableEncryption(admin_password.encode("utf-8"))

    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=enc,
    )

    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")

    priv_path.write_bytes(priv_pem)
    pub_path.write_text(pub_b64, encoding="utf-8")

    logger.info("Ed25519 keys created: %s | %s", priv_path, pub_path)
