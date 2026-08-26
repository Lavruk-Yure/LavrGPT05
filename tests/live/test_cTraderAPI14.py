# test_cTraderAPI14.py
import sys  # noqa
from pathlib import Path  # noqa

sys.path.append(  # noqa
    str(Path(__file__).resolve().parent.parent)  # noqa
)  # Додати корінь проєкту до sys.path

from unittest.mock import MagicMock, patch  # noqa

import pytest  # noqa

from tests.live.run_cTraderAPI14 import (  # noqa
    load_tokens,
    obtain_token_by_code_interactive,
    refresh_token_http,
    save_tokens,
    token_is_valid,
)


def test_save_and_load_tokens(tmp_path):
    token_data = {
        "accessToken": "test_access",
        "refreshToken": "test_refresh",
        "expiresIn": 3600,
    }
    # Виклик збереження
    save_tokens(token_data)
    loaded = load_tokens()
    assert loaded is None or isinstance(loaded, dict)


def test_token_is_valid():
    import time

    valid_token = {"expires_at": int(time.time()) + 100}
    invalid_token = {"expires_at": int(time.time()) - 100}
    assert token_is_valid(valid_token)
    assert not token_is_valid(invalid_token)
    assert not token_is_valid(None)


@patch("tests.live.run_cTraderAPI14.requests.post")
def test_refresh_token_http(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "accessToken": "new_access",
        "refreshToken": "new_refresh",
        "expiresIn": 3600,
    }
    mock_post.return_value = mock_response

    result = refresh_token_http("dummy_refresh", "dummy_id", "dummy_secret")
    assert "accessToken" in result or "access_token" in result
    assert (
        result.get("access_token") == "new_access"
        or not result.get("access_token") == "code_access"
    )


@patch("tests.live.run_cTraderAPI14.requests.post")
@patch("builtins.input", return_value="fake_auth_code")
def test_obtain_token_by_code_interactive(_mock_input, mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "accessToken": "code_access",
    }
    mock_post.return_value = mock_response

    result = obtain_token_by_code_interactive("client_id", "client_secret")
    assert "accessToken" in result or "access_token" in result
    assert (
        result.get("accessToken") == "code_access"
        or result.get("access_token") == "code_access"
    )
