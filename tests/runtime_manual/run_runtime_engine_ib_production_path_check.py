# run_runtime_engine_ib_production_path_check.py
"""
Production-path тест RuntimeEngine + IBRuntimeService.

RoadMap75:
1. RuntimeEngine startup.
2. Підключення IBRuntimeService.
3. IB DEMO connect через RuntimeEngine.
4. Перевірка RuntimeContext.
5. Перевірка IB account state.
6. Перевірка broker health.
7. Shutdown.
"""

from __future__ import annotations

import logging
from pprint import pprint

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


def main() -> None:
    """
    Запустити production-path тест IB runtime.
    """
    print_block("CREATE RUNTIME ENGINE")

    engine = RuntimeEngine(db_path=str(get_runtime_database_path("DEMO")))
    service = IBRuntimeService()

    print("engine created")
    print("IB runtime service created")

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
            "execution_mode": engine.context.execution_mode,
            "broker_connection_state": engine.context.broker_connection_state.value,
            "active_db": engine.context.active_db,
            "session_id": engine.context.session_id,
        }
    )

    print_block("IB BROKER HEALTH")

    broker_health = service.get_broker_health()

    pprint(
        {
            "state": broker_health.state,
            "last_error": broker_health.last_error,
            "updated_utc": broker_health.updated_utc,
        }
    )

    print_block("IB ACCOUNT STATE")

    account_state = service.get_account_state()

    pprint(
        {
            "is_loaded": account_state.is_loaded(),
            "account_id": account_state.account_id,
            "trader_login": account_state.trader_login,
            "broker_name": account_state.broker_name,
            "currency": account_state.currency,
            "balance": account_state.balance,
            "equity": account_state.equity,
            "margin": account_state.margin,
            "free_margin": account_state.free_margin,
            "leverage": account_state.leverage,
            "snapshot_utc": account_state.snapshot_utc,
        }
    )

    print_block("ENGINE EVENTS")

    for event in engine.events:
        pprint(event.to_dict())

    print_block("IB SERVICE EVENTS")

    for event in service.get_runtime_events():
        pprint(event.to_dict())

    print_block("SHUTDOWN")

    engine.shutdown()

    pprint(
        {
            "runtime_state": engine.context.runtime_state.value,
            "broker_connection_state": engine.context.broker_connection_state.value,
            "scheduler_running": engine.is_scheduler_running(),
        }
    )

    print_block("DONE")


if __name__ == "__main__":
    main()
