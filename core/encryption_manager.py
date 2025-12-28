# encryption_manager.py
"""
encryption_manager.py — клас для шифрування і дешифрування в LavrGPT05 (LGE05).

Відповідає принципу "чистий модуль ядра":
  - не містить print, logging, CLI чи тестових викликів;
  - лише логіку класу EncryptionManager.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

# noinspection PyPackageRequirements
from Crypto.Cipher import AES

# noinspection PyPackageRequirements
from Crypto.Random import get_random_bytes


class EncryptionManager:
    """Керує шифруванням і дешифруванням конфіденційних даних (AES-256-GCM)."""

    def __init__(self, key_file: str | Path = "secure_storage/master.key") -> None:
        self.key_path = Path(key_file)
        self.key: Optional[bytes] = None
        self._ensure_key_exists()

    # ---------------------------------------------------------
    # 🔑  ІНІЦІАЛІЗАЦІЯ КЛЮЧА
    # ---------------------------------------------------------
    def _ensure_key_exists(self) -> None:
        """Перевіряє наявність AES-ключа, створює при відсутності."""
        if not self.key_path.parent.exists():
            self.key_path.parent.mkdir(parents=True)
        if not self.key_path.exists():
            self._generate_key()
        self.key = self.key_path.read_bytes()

    def _generate_key(self) -> None:
        """Створює новий AES-256 ключ і зберігає його у файл."""
        key = get_random_bytes(32)
        self.key_path.write_bytes(key)

    # ---------------------------------------------------------
    # 🔒  ШИФРУВАННЯ / ДЕШИФРУВАННЯ
    # ---------------------------------------------------------
    def encrypt(self, plain_text: str) -> str:
        """Шифрує рядок за допомогою AES-GCM."""
        cipher = AES.new(self.key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plain_text.encode("utf-8"))
        payload = cipher.nonce + tag + ciphertext
        return base64.b64encode(payload).decode("utf-8")

    def decrypt(self, encrypted_text: str) -> str:
        """Розшифровує base64-рядок."""
        raw = base64.b64decode(encrypted_text)
        nonce, tag, ciphertext = raw[:16], raw[16:32], raw[32:]
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")

    # ---------------------------------------------------------
    # 🧾  СЛУЖБОВІ
    # ---------------------------------------------------------
    def rotate_key(self) -> None:
        """Ротує ключ (створює новий і замінює існуючий)."""
        backup = self.key_path.with_suffix(".bak")
        if self.key_path.exists():
            self.key_path.replace(backup)
        self._generate_key()
        self.key = self.key_path.read_bytes()

    def get_key_info(self) -> str:
        """Повертає коротку інформацію про ключ."""
        if not self.key:
            return "⚠️ Ключ не завантажено."
        size = len(self.key) * 8
        return f"AES-{size} key, path={self.key_path}"
