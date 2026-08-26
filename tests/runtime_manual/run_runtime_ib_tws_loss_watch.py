# run_runtime_ib_tws_loss_watch.py
"""
Watch-тест втрати TWS під час роботи IB runtime.

RoadMap75:
1. RuntimeEngine startup.
2. IB DEMO connect через RuntimeEngine.
3. Періодична перевірка broker health.
4. Ручне закриття TWS оператором.
5. Перевірка SAFE_DISCONNECTED / DISCONNECTED поведінки.
6. Shutdown.
"""

from __future__ import annotations

import logging
import time
from pprint import pprint

from engine.runtime_constants import (
    RUNTIME_WATCH_ITERATIONS,
    RUNTIME_WATCH_SLEEP_SECONDS,
)
from engine.db.runtime_db import get_runtime_database_path
from engine.runtime_engine import RuntimeEngine
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


def print_watch_state(
    service: IBRuntimeService,
    iteration: int,
) -> None:
    """
    Надрукувати поточний runtime стан IB service.
    """
    adapter = service.get_active_adapter()
    health = service.refresh_broker_health()
    account = service.get_account_state()

    pprint(
        {
            "iteration": iteration,
            "adapter_exists": adapter is not None,
            "adapter_connected": (
                adapter.is_connected() if adapter is not None else False
            ),
            "adapter_broker_state": (
                adapter.broker_state if adapter is not None else None
            ),
            "health_state": health.state,
            "health_last_error": health.last_error,
            "health_updated_utc": health.updated_utc,
            "account_loaded": account.is_loaded(),
            "account_id": account.account_id,
        }
    )


def main() -> None:
    """
    Запустити watch-тест втрати TWS.
    """
    print_block("CREATE RUNTIME ENGINE")

    engine = RuntimeEngine(db_path=str(get_runtime_database_path("DEMO")))
    service = IBRuntimeService()

    print_block("STARTUP")

    engine.startup()

    print_block("SET IB RUNTIME SERVICE")

    engine.set_ib_runtime_service(service)

    print_block("CONNECT IB DEMO THROUGH ENGINE")

    connected = engine.connect_ib_demo()

    pprint(
        {
            "connected": connected,
            "runtime_state": engine.context.runtime_state.value,
            "broker": engine.context.broker,
            "account_mode": engine.context.account_mode,
            "broker_connection_state": engine.context.broker_connection_state.value,
        }
    )

    print_block("WATCH STARTED")

    print(
        "Закрий TWS вручну після появи iteration=1 або iteration=2. "
        "Тест сам продовжить перевірку."
    )

    try:
        safe_disconnected_count = 0
        reconnect_success = False
        last_reconnect_iteration = 0

        for iteration in range(1, RUNTIME_WATCH_ITERATIONS):
            print_block(f"WATCH ITERATION {iteration}")

            adapter = service.get_active_adapter()
            health = service.refresh_broker_health()
            account = service.get_account_state()

            state_snapshot = {
                "iteration": iteration,
                "adapter_exists": adapter is not None,
                "adapter_connected": (
                    adapter.is_connected() if adapter is not None else False
                ),
                "adapter_broker_state": (
                    adapter.broker_state if adapter is not None else None
                ),
                "health_state": health.state,
                "health_last_error": health.last_error,
                "health_updated_utc": health.updated_utc,
                "account_loaded": account.is_loaded(),
                "account_id": account.account_id,
            }

            pprint(state_snapshot)

            if health.state == "SAFE_DISCONNECTED":
                safe_disconnected_count += 1
            else:
                safe_disconnected_count = 0

            if (
                safe_disconnected_count >= 3
                and not reconnect_success
                and iteration - last_reconnect_iteration >= 3
            ):
                print_block("RECONNECT ATTEMPT")

                last_reconnect_iteration = iteration

                reconnect_adapter = service.reconnect()
                reconnect_health = service.refresh_broker_health()
                reconnect_account = service.get_account_state()

                if reconnect_health.is_connected() and reconnect_account.is_loaded():
                    reconnect_success = True

                pprint(
                    {
                        "reconnect_adapter_exists": reconnect_adapter is not None,
                        "reconnect_adapter_connected": (
                            reconnect_adapter.is_connected()
                            if reconnect_adapter is not None
                            else False
                        ),
                        "reconnect_health_state": reconnect_health.state,
                        "reconnect_health_last_error": reconnect_health.last_error,
                        "reconnect_account_loaded": reconnect_account.is_loaded(),
                        "reconnect_account_id": reconnect_account.account_id,
                    }
                )

            time.sleep(RUNTIME_WATCH_SLEEP_SECONDS)
    finally:
        print_block("SHUTDOWN")
        engine.shutdown()

        pprint(
            {
                "runtime_state": engine.context.runtime_state.value,
                "broker_connection_state": (
                    engine.context.broker_connection_state.value
                ),
                "scheduler_running": engine.is_scheduler_running(),
            }
        )

    print_block("DONE")


if __name__ == "__main__":
    main()
