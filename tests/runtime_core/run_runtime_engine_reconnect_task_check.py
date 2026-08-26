# run_runtime_engine_reconnect_task_check.py
"""
Діагностика RuntimeEngine + RuntimeScheduler + RuntimeReconnectTask.

RoadMap73.5:
- RuntimeEngine має RuntimeScheduler;
- RuntimeReconnectTask підключається до scheduler через RuntimeEngine;
- reconnect виконується через service protocol;
- перевірка без реальної мережі.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402


class DummyRuntimeService:
    """
    Dummy runtime service для reconnect task.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати dummy service.
        """
        self._broker_health = RuntimeBrokerHealth()
        self.reconnect_calls = 0

    def reconnect(self) -> object | None:
        """
        Dummy reconnect.
        """
        self.reconnect_calls += 1
        self._broker_health.set_connected()
        return object()

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути broker health.
        """
        return self._broker_health


def main() -> int:
    """
    Запустити перевірку RuntimeEngine + RuntimeReconnectTask.
    """
    engine = RuntimeEngine()

    service = DummyRuntimeService()
    reconnect_task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=2.0,
    )

    engine.attach_reconnect_task(
        reconnect_task=reconnect_task,
        interval_seconds=1.0,
    )

    engine.startup()
    time.sleep(3.5)
    engine.shutdown()

    print(f"service.reconnect_calls={service.reconnect_calls}")
    print(f"reconnect_task.reconnect_attempts={reconnect_task.reconnect_attempts}")
    print(f"scheduler_running_after_shutdown={engine.is_scheduler_running()}")

    checks = [
        service.reconnect_calls == 1,
        reconnect_task.reconnect_attempts == 1,
        engine.is_scheduler_running() is False,
    ]

    if all(checks):
        print("\nRUNTIME_ENGINE_RECONNECT_TASK_CHECK=OK")
        return 0

    print("\nRUNTIME_ENGINE_RECONNECT_TASK_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
