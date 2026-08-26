# run_runtime_reconnect_task_ctrader_service_check.py
"""
Діагностика RuntimeReconnectTask + CTraderRuntimeService.

RoadMap73:
- reconnect task працює не з adapter напряму;
- reconnect task працює через CTraderRuntimeService;
- CTraderRuntimeService працює через SessionManager protocol;
- RuntimeBrokerHealth оновлюється через service layer.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_events import RuntimeEventType  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402
from engine.runtime_scheduler import RuntimeScheduler  # noqa: E402
from engine.services.ctrader_runtime_service import CTraderRuntimeService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


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
        Dummy successful reconnect.
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


class DummyFailedCTraderSessionManager:
    """
    Dummy SessionManager для невдалого reconnect без мережі.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати failed dummy session manager.
        """
        self.reconnect_calls = 0
        self.disconnect_calls = 0
        self._active_adapter: Any | None = None

    def connect_demo(self) -> Any:  # noqa
        """
        Dummy failed DEMO connect.
        """
        return None

    def connect_live(self) -> Any:  # noqa
        """
        Dummy failed LIVE connect.
        """
        return None

    def reconnect(self) -> Any:
        """
        Dummy failed reconnect.
        """
        self.reconnect_calls += 1
        self._active_adapter = None
        return None

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


def run_success_case() -> bool:
    """
    Перевірити успішний reconnect через CTraderRuntimeService.
    """
    print("\n=== SUCCESS CASE ===")

    session_manager = DummyCTraderSessionManager()
    service = CTraderRuntimeService(session_manager=session_manager)

    reconnect_task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=2.0,
        logger_=logger,
    )

    scheduler = RuntimeScheduler(logger_=logger)
    scheduler.add_periodic_task(
        interval_seconds=1.0,
        task=reconnect_task.check_and_reconnect,
    )

    scheduler.start()
    time.sleep(3.5)
    scheduler.stop()

    broker_health = service.get_broker_health()
    events = service.get_runtime_events()

    print(f"success.reconnect_calls={session_manager.reconnect_calls}")
    print(f"success.reconnect_attempts={reconnect_task.reconnect_attempts}")
    print(f"success.broker_health.state={broker_health.state}")
    print(f"success.broker_health.last_error={broker_health.last_error}")

    return all(
        [
            session_manager.reconnect_calls == 1,
            reconnect_task.reconnect_attempts == 1,
            broker_health.is_connected() is True,
            any(
                event.event_type == RuntimeEventType.RECONNECT_STARTED
                for event in events
            ),
            any(
                event.event_type == RuntimeEventType.RECONNECT_SUCCESS
                for event in events
            ),
        ]
    )


def run_fail_case() -> bool:
    """
    Перевірити невдалий reconnect через CTraderRuntimeService.
    """
    print("\n=== FAIL CASE ===")

    session_manager = DummyFailedCTraderSessionManager()
    service = CTraderRuntimeService(session_manager=session_manager)

    reconnect_task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=2.0,
        logger_=logger,
    )

    scheduler = RuntimeScheduler(logger_=logger)
    scheduler.add_periodic_task(
        interval_seconds=1.0,
        task=reconnect_task.check_and_reconnect,
    )

    scheduler.start()
    time.sleep(3.5)
    scheduler.stop()

    broker_health = service.get_broker_health()
    events = service.get_runtime_events()

    print(f"fail.reconnect_calls={session_manager.reconnect_calls}")
    print(f"fail.reconnect_attempts={reconnect_task.reconnect_attempts}")
    print(f"fail.broker_health.state={broker_health.state}")
    print(f"fail.broker_health.last_error={broker_health.last_error}")

    return all(
        [
            session_manager.reconnect_calls >= 1,
            reconnect_task.reconnect_attempts >= 1,
            "SAFE_DISCONNECTED" in str(broker_health.state),
            broker_health.last_error == "cTrader reconnect did not restore connection.",
            any(
                event.event_type == RuntimeEventType.RECONNECT_STARTED
                for event in events
            ),
            any(
                event.event_type == RuntimeEventType.RECONNECT_FAILED
                for event in events
            ),
        ]
    )


def main() -> int:
    """
    Запустити combined перевірку RuntimeReconnectTask + CTraderRuntimeService.
    """
    success_ok = run_success_case()
    fail_ok = run_fail_case()

    print(f"\nsuccess_ok={success_ok}")
    print(f"fail_ok={fail_ok}")

    if success_ok and fail_ok:
        print("\nRUNTIME_RECONNECT_TASK_CTRADER_SERVICE_CHECK=OK")
        return 0

    print("\nRUNTIME_RECONNECT_TASK_CTRADER_SERVICE_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
