# run_runtime_engine_ctrader_runtime_service_check.py
"""
Інтеграційна діагностика RuntimeEngine + CTraderRuntimeService.

RoadMap73.6:
- RuntimeEngine запускає RuntimeScheduler;
- RuntimeReconnectTask підключається через RuntimeEngine;
- RuntimeReconnectTask працює через CTraderRuntimeService;
- CTraderRuntimeService працює через SessionManager protocol;
- перевірка виконується без реальної мережі.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_account import BrokerAccount  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_events import RuntimeEventType  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402
from engine.services.ctrader_runtime_service import CTraderRuntimeService  # noqa: E402


class DummyAdapter:
    """
    Dummy adapter для імітації успішного cTrader reconnect.
    """

    def __init__(self, connected: bool = True) -> None:
        """
        Ініціалізувати dummy adapter.
        """
        self._connected = connected

    def is_connected(self) -> bool:
        """
        Повернути fake connection state.
        """
        return self._connected

    def get_account_info(self) -> BrokerAccount:  # noqa
        """
        Повернути dummy account info.
        """
        return BrokerAccount(
            broker="CTRADER",
            account_id="9870599",
            account_mode="DEMO",
            currency="USD",
            balance=869.75,
        )


class DummyCTraderSessionManager:
    """
    Dummy SessionManager для успішного reconnect без мережі.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати dummy session manager.
        """
        self.reconnect_calls = 0
        self.disconnect_calls = 0
        self._active_adapter: Any | None = None

    def connect_demo(self) -> Any:
        """
        Dummy DEMO connect.
        """
        self._active_adapter = DummyAdapter(connected=True)
        return self._active_adapter

    def connect_live(self) -> Any:
        """
        Dummy LIVE connect.
        """
        self._active_adapter = DummyAdapter(connected=True)
        return self._active_adapter

    def reconnect(self) -> Any:
        """
        Dummy reconnect.
        """
        self.reconnect_calls += 1
        self._active_adapter = DummyAdapter(connected=True)
        return self._active_adapter

    def disconnect(self) -> None:
        """
        Dummy disconnect.
        """
        self.disconnect_calls += 1
        self._active_adapter = None

    def get_active_adapter(self) -> Any | None:
        """
        Повернути active dummy adapter.
        """
        return self._active_adapter


def main() -> int:
    """
    Запустити перевірку RuntimeEngine + CTraderRuntimeService.
    """
    engine = RuntimeEngine()

    session_manager = DummyCTraderSessionManager()
    service = CTraderRuntimeService(
        session_manager=session_manager,
    )

    reconnect_task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=2.0,
    )

    engine.set_ctrader_runtime_service(service)

    engine.attach_reconnect_task(
        reconnect_task=reconnect_task,
        interval_seconds=1.0,
    )

    engine.startup()
    time.sleep(3.5)

    broker_health_after_reconnect = service.get_broker_health()
    broker_health_after_reconnect_state = broker_health_after_reconnect.state
    broker_health_after_reconnect_last_error = broker_health_after_reconnect.last_error
    service_events = service.get_runtime_events()

    engine.shutdown()

    broker_health_after_shutdown = service.get_broker_health()
    broker_health_after_shutdown_state = broker_health_after_shutdown.state
    broker_health_after_shutdown_last_error = broker_health_after_shutdown.last_error

    print(
        "broker_health_after_reconnect.state=" f"{broker_health_after_reconnect_state}"
    )
    print(
        "broker_health_after_reconnect.last_error="
        f"{broker_health_after_reconnect_last_error}"
    )
    print("broker_health_after_shutdown.state=" f"{broker_health_after_shutdown_state}")
    print(
        "broker_health_after_shutdown.last_error="
        f"{broker_health_after_shutdown_last_error}"
    )

    print("broker_health_after_shutdown.state=" f"{broker_health_after_shutdown.state}")
    print(
        "broker_health_after_shutdown.last_error="
        f"{broker_health_after_shutdown.last_error}"
    )
    print(f"engine.scheduler_running={engine.is_scheduler_running()}")

    print("\n=== SERVICE EVENTS ===")
    for event in service_events:
        print(event.to_dict())

    checks = [
        session_manager.reconnect_calls == 1,
        reconnect_task.reconnect_attempts == 1,
        broker_health_after_reconnect_state == "CONNECTED",
        broker_health_after_shutdown_state == "DISCONNECTED",
        session_manager.disconnect_calls == 1,
        engine.is_scheduler_running() is False,
        any(
            event.event_type == RuntimeEventType.RECONNECT_STARTED
            for event in service_events
        ),
        any(
            event.event_type == RuntimeEventType.RECONNECT_SUCCESS
            for event in service_events
        ),
    ]

    if all(checks):
        print("\nRUNTIME_ENGINE_CTRADER_RUNTIME_SERVICE_CHECK=OK")
        return 0

    print("\nRUNTIME_ENGINE_CTRADER_RUNTIME_SERVICE_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
