# run_runtime_ib_reconnect_task_watch.py
"""
Watch-тест RuntimeReconnectTask + IBRuntimeService.

RoadMap75:
1. RuntimeEngine startup.
2. IB DEMO connect через RuntimeEngine.
3. Підключення RuntimeReconnectTask.
4. Ручне закриття TWS.
5. Reconnect attempts через RuntimeReconnectTask.
6. Ручний запуск TWS.
7. Перевірка повернення CONNECTED.
8. Shutdown.
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
from engine.runtime_reconnect_task import RuntimeReconnectTask
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


def print_state(
    service: IBRuntimeService,
    reconnect_task: RuntimeReconnectTask,
    iteration: int,
) -> None:
    """
    Надрукувати поточний runtime стан.
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
            "reconnect_attempts": reconnect_task.reconnect_attempts,
        }
    )


def main() -> None:
    """
    Запустити watch-тест RuntimeReconnectTask для IB.
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

    print_block("CREATE RECONNECT TASK")

    reconnect_task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=15.0,
    )

    print(
        "Закрий TWS після iteration=1 або iteration=2. "
        "Потім запусти TWS знову. Reconnect робитиме RuntimeReconnectTask."
    )

    try:
        for iteration in range(1, RUNTIME_WATCH_ITERATIONS):
            print_block(f"WATCH ITERATION {iteration}")

            print_state(
                service=service,
                reconnect_task=reconnect_task,
                iteration=iteration,
            )

            reconnect_task.run_once()

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
                "reconnect_attempts": reconnect_task.reconnect_attempts,
            }
        )

    print_block("DONE")


if __name__ == "__main__":
    main()
