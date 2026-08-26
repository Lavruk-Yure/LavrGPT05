# run_runtime_ib_runtime_service_check.py
"""
Тест IBRuntimeService.

RoadMap75:
1. Створення IBRuntimeService.
2. Connect DEMO.
3. Перевірка broker health.
4. Перевірка account state.
5. Перевірка runtime events.
6. Refresh broker health.
7. Disconnect.
"""

from __future__ import annotations

import logging
from pprint import pprint

from engine.services.ib_runtime_service import IBRuntimeService

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


def print_block(title: str) -> None:
    """
    Надрукувати заголовок блоку.
    """
    print()
    print(f"=== {title} ===")


def main() -> None:
    """
    Запустити тест IBRuntimeService.
    """
    print_block("CREATE IB RUNTIME SERVICE")

    service = IBRuntimeService()

    print("service created")

    print_block("CONNECT DEMO")

    adapter = service.connect_demo()

    print_block("ADAPTER")

    pprint(
        {
            "adapter_exists": adapter is not None,
            "connected": adapter.is_connected() if adapter is not None else False,
        }
    )

    print_block("BROKER HEALTH AFTER CONNECT")

    health = service.get_broker_health()

    pprint(
        {
            "state": health.state,
            "last_error": health.last_error,
            "updated_utc": health.updated_utc,
        }
    )

    print_block("ACCOUNT STATE AFTER CONNECT")

    account = service.get_account_state()

    pprint(
        {
            "is_loaded": account.is_loaded(),
            "account_id": account.account_id,
            "trader_login": account.trader_login,
            "broker_name": account.broker_name,
            "currency": account.currency,
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "free_margin": account.free_margin,
            "leverage": account.leverage,
            "snapshot_utc": account.snapshot_utc,
        }
    )

    print_block("BROKER HEALTH AFTER REFRESH")

    refreshed_health = service.refresh_broker_health()

    pprint(
        {
            "state": refreshed_health.state,
            "last_error": refreshed_health.last_error,
            "updated_utc": refreshed_health.updated_utc,
        }
    )

    print_block("RUNTIME EVENTS")

    for event in service.get_runtime_events():
        pprint(event.to_dict())

    print_block("DISCONNECT")

    service.disconnect()

    print_block("BROKER HEALTH AFTER DISCONNECT")

    final_health = service.get_broker_health()

    pprint(
        {
            "state": final_health.state,
            "last_error": final_health.last_error,
            "updated_utc": final_health.updated_utc,
        }
    )

    print_block("ACCOUNT STATE AFTER DISCONNECT")

    final_account = service.get_account_state()

    pprint(
        {
            "is_loaded": final_account.is_loaded(),
            "account_id": final_account.account_id,
            "broker_name": final_account.broker_name,
            "currency": final_account.currency,
        }
    )

    print_block("DONE")


if __name__ == "__main__":
    main()
