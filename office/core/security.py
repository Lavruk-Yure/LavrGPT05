# security.py
# -*- coding: utf-8 -*-
"""
security — пароль LGEOffice (без шифрування, збереження як salt+sha256).

Політика:
- довжина > 12
- є мала літера
- є велика літера
- є цифра
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PasswordCheck:
    ok: bool
    message: str


def validate_password(pwd: str) -> PasswordCheck:
    if len(pwd) <= 12:
        return PasswordCheck(False, "Пароль має бути довший за 12 символів.")
    if not re.search(r"[a-z]", pwd):
        return PasswordCheck(False, "Додай хоча б одну малу літеру (a-z).")
    if not re.search(r"[A-Z]", pwd):
        return PasswordCheck(False, "Додай хоча б одну ВЕЛИКУ літеру (A-Z).")
    if not re.search(r"\d", pwd):
        return PasswordCheck(False, "Додай хоча б одну цифру (0-9).")
    return PasswordCheck(True, "OK")


def make_salt() -> str:
    return os.urandom(16).hex()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_password(pwd: str, salt_hex: str) -> str:
    # sha256(salt + password)
    return sha256_hex(salt_hex + pwd)


def verify_password(pwd: str, salt_hex: str, expected_hash_hex: str) -> bool:
    return hash_password(pwd, salt_hex) == expected_hash_hex
