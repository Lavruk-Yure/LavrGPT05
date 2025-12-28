# run_ctrader_account_utils.py
"""
Демонстраційний скрипт для перевірки функції get_account_by_number
з модуля ctrader_account_utils.

Тестує два варіанти відповіді API:
- {"data": [...]} — звичайний список акаунтів.
- {"accounts": {"data": [...]}} — вкладена структура.
"""

from utils.ctrader_account_utils import get_account_by_number


def main() -> None:
    """Запускає тестові приклади виклику get_account_by_number."""
    # Приклад 1: структура {"data": [...]}
    resp_simple = {
        "data": [
            {"accountNumber": 12345, "balance": 1000},
            {"accountNumber": 67890, "balance": 2500},
        ]
    }

    # Приклад 2: структура {"accounts": {"data": [...]}}
    resp_nested = {
        "accounts": {
            "data": [
                {"accountNumber": 11111, "balance": 500},
                {"accountNumber": 22222, "balance": 1200},
            ]
        }
    }

    print("=== Тест 1: простий формат ===")
    result1 = get_account_by_number(resp_simple, 67890)
    print(result1)

    print("\n=== Тест 2: вкладений формат ===")
    result2 = get_account_by_number(resp_nested, 22222)
    print(result2)

    print("\n=== Тест 3: акаунта немає ===")
    result3 = get_account_by_number(resp_simple, 99999)
    print(result3)


if __name__ == "__main__":
    main()
