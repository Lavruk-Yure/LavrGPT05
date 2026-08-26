# test_encryption_manager.py
"""
Тестування модуля core.encryption_manager (pytest).
"""

import os

from core.encryption_manager import EncryptionManager


def test_encryption_cycle(tmp_path):
    """Перевіряє, що шифрування-дешифрування працює коректно."""
    key_file = tmp_path / "master.key"
    mgr = EncryptionManager(key_file)
    text = "LavrGPT05-test"

    encrypted = mgr.encrypt(text)
    decrypted = mgr.decrypt(encrypted)

    assert decrypted == text
    assert os.path.exists(key_file)
    assert key_file.stat().st_size == 32


def test_key_rotation(tmp_path):
    """Перевіряє, що після ротації ключ змінюється."""
    key_file = tmp_path / "master.key"
    mgr = EncryptionManager(key_file)
    old_key = key_file.read_bytes()

    mgr.rotate_key()
    new_key = key_file.read_bytes()

    assert old_key != new_key
