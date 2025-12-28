# ctrader_account_utils.py
"""
Модуль утиліт для роботи з акаунтами cTrader API.

Містить функції для пошуку акаунтів у відповіді від API.
"""


def get_account_by_number(resp: dict, target_number: int):
    """
    Знаходить акаунт у відповіді cTrader API за номером accountNumber.

    Деякі ендпоінти cTrader повертають список акаунтів у ключі "data",
    інші — у вкладеному полі "accounts" → "data".

    :param resp: dict — JSON-відповідь з API.
    :param target_number: int — номер акаунта (accountNumber), який треба знайти.
    :return: dict або None — знайдений акаунт або None, якщо не знайдено.
    :raises ValueError: якщо у відповіді немає даних акаунтів.
    """
    accounts = None

    # Перевіряємо, де саме містяться дані
    if "data" in resp and isinstance(resp["data"], list):
        accounts = resp["data"]
    elif "accounts" in resp and isinstance(resp["accounts"], dict):
        if "data" in resp["accounts"] and isinstance(resp["accounts"]["data"], list):
            accounts = resp["accounts"]["data"]

    if not accounts:
        raise ValueError("У відповіді немає даних акаунтів")

    # Повертаємо акаунт або None, якщо не знайдено
    return next((a for a in accounts if a.get("accountNumber") == target_number), None)
