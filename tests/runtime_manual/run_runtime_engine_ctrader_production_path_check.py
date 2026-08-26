# run_runtime_engine_ctrader_production_path_check.py
"""
RoadMap74.1.

Production path перевірка:

RuntimeEngine
↓
CTraderRuntimeService
↓
CTraderSessionManager
↓
CTraderAdapter
↓
OpenAPI

Без Dummy-класів.
Без reconnect.
Без GUI.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import get_runtime_database_path  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ctrader_runtime_service import CTraderRuntimeService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> int:
    """
    Запустити production path перевірку RuntimeEngine + cTrader.
    """
    engine = RuntimeEngine(db_path=str(get_runtime_database_path("DEMO")))
    service = CTraderRuntimeService()

    engine.startup()
    engine.set_ctrader_runtime_service(service)

    connected = engine.connect_ctrader_demo()

    broker_health = service.get_broker_health()
    account_state = service.get_account_state()
    active_adapter = service.get_active_adapter()

    print("\n=== CONNECT RESULT ===")
    print(f"connected={connected}")
    print(f"broker_health.state={broker_health.state}")
    print(f"broker_health.last_error={broker_health.last_error}")

    print("\n=== ACTIVE ADAPTER ===")
    print(
        f"active_adapter_class="
        f"{active_adapter.__class__.__name__ if active_adapter else None}"
    )
    print(
        f"active_adapter_connected="
        f"{active_adapter.is_connected() if active_adapter else None}"
    )
    print(
        f"active_adapter_alive="
        f"{active_adapter.is_session_alive() if active_adapter else None}"
    )

    print("\n=== ACCOUNT STATE ===")
    pprint(asdict(account_state))

    print("\n=== ENGINE CONTEXT BEFORE SHUTDOWN ===")
    pprint(engine.context.to_dict())

    print("\n=== ENGINE EVENTS ===")
    for event in engine.events:
        pprint(event.to_dict())

    pre_shutdown_checks = [
        connected is True,
        broker_health.is_connected() is True,
        active_adapter is not None,
        active_adapter.is_connected() is True,
        active_adapter.is_session_alive() is True,
        engine.context.broker == "CTRADER",
        engine.context.account_mode == "DEMO",
        engine.context.broker_connection_state.value == "CONNECTED",
        engine.get_runtime_state().value == "RUNNING",
    ]

    engine.shutdown()

    print("\n=== ENGINE CONTEXT AFTER SHUTDOWN ===")
    pprint(engine.context.to_dict())

    post_shutdown_checks = [
        engine.context.broker == "CTRADER",
        engine.context.account_mode == "DEMO",
        engine.context.broker_connection_state.value == "DISCONNECTED",
        engine.get_runtime_state().value == "OFF",
    ]

    checks = pre_shutdown_checks + post_shutdown_checks

    if all(checks):
        print("\nRUNTIME_ENGINE_CTRADER_PRODUCTION_PATH_CHECK=OK")
        return 0

    print("\nRUNTIME_ENGINE_CTRADER_PRODUCTION_PATH_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
