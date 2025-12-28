#  test_token_manager.py
"""
test_token_manager.py

Базові тести для TokenManager:
- Збереження і завантаження токенів у файл.
- Оновлення токена при відсутності файлу.
"""

import os
import time

import pytest

from core.token_manager import load_tokens, refresh_if_needed, save_tokens

TEST_TOKEN_FILE = "test_tokens.json"


@pytest.fixture(autouse=True)
def env_tok_path(monkeypatch):
    monkeypatch.setenv("TOKENS_PATH", TEST_TOKEN_FILE)
    yield
    if os.path.exists(TEST_TOKEN_FILE):
        os.remove(TEST_TOKEN_FILE)


def test_save_and_load_tokens():
    tokens = {
        "access_token": "test_access",
        "refresh_token": "test_refresh",
        "expires_in": 3600,
        "expires_at": int(time.time()) + 3600,
    }

    save_tokens(tokens)
    assert os.path.exists(TEST_TOKEN_FILE)

    loaded = load_tokens()
    assert loaded["access_token"] == "test_access"
    assert loaded["refresh_token"] == "test_refresh"
    assert loaded["expires_in"] == 3600
    assert "_comment" in loaded


def test_refresh_if_needed_no_file():
    if os.path.exists(TEST_TOKEN_FILE):
        os.remove(TEST_TOKEN_FILE)

    result = refresh_if_needed()
    assert result is None
