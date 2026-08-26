# test_ctrader_account_utils.py
"""
Тестовий модуль для функції get_account_by_number з модуля ctrader_account_utils.

Перевіряє:
- Коректне знаходження акаунта за номером accountNumber.
- Обробку випадків, коли структура відповіді різна.
- Виключення при відсутності даних акаунтів.
"""

import pytest

from utils.ctrader_account_utils import get_account_by_number


def test_find_account_in_data():
    """Перевіряє знаходження акаунта, якщо дані містяться у ключі 'data'."""
    response = {
        "data": [
            {"accountNumber": 123, "balance": 1000},
            {"accountNumber": 456, "balance": 2000},
        ]
    }
    result = get_account_by_number(response, 456)
    assert result == {"accountNumber": 456, "balance": 2000}


def test_find_account_in_accounts_data():
    """Перевіряє знаходження акаунта, якщо дані містяться у ключі
    'accounts' -> 'data'."""
    response = {
        "accounts": {
            "data": [
                {"accountNumber": 789, "balance": 3000},
                {"accountNumber": 111, "balance": 4000},
            ]
        }
    }
    result = get_account_by_number(response, 111)
    assert result == {"accountNumber": 111, "balance": 4000}


def test_account_not_found_returns_none():
    """Перевіряє, що функція повертає None, якщо акаунт не знайдено."""
    response = {"data": [{"accountNumber": 1}, {"accountNumber": 2}]}
    result = get_account_by_number(response, 999)
    assert result is None


def test_raises_value_error_if_no_accounts():
    """Перевіряє, що при відсутності даних акаунтів підійматися ValueError."""
    response = {"meta": {"total": 0}}
    with pytest.raises(ValueError, match="У відповіді немає даних акаунтів"):
        get_account_by_number(response, 1)
