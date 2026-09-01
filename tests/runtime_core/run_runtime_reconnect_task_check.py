# run_runtime_reconnect_task_check.py
"""
Діагностика RuntimeReconnectTask.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402
from engine.runtime_scheduler import RuntimeScheduler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


class DummyRuntimeService:
    """
    Dummy runtime service для reconnect test.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати dummy service.
        """
        self._broker_health = RuntimeBrokerHealth()
        self.reconnect_calls = 0

    def reconnect(self) -> object | None:
        """
        Симуляція reconnect через service layer.
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
    Запустити reconnect diagnostic.
    """
    service = DummyRuntimeService()

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

    print(f"reconnect_calls={service.reconnect_calls}")
    print(f"reconnect_attempts={reconnect_task.reconnect_attempts}")

    manual_service = DummyRuntimeService()
    manual_service.get_broker_health().set_disconnected(
        error="Manual disconnect.",
        manual=True,
    )
    manual_task = RuntimeReconnectTask(
        runtime_service=manual_service,
        reconnect_cooldown_seconds=0.0,
        logger_=logger,
    )
    manual_task.run_once()

    print(
        "manual_disconnect_reconnect_blocked=" f"{manual_service.reconnect_calls == 0}"
    )

    checks = [
        service.reconnect_calls == 1,
        reconnect_task.reconnect_attempts == 1,
        service.get_broker_health().is_connected() is True,
        scheduler.is_running is False,
        manual_service.reconnect_calls == 0,
        manual_task.reconnect_attempts == 0,
    ]

    if all(checks):
        print("RUNTIME_RECONNECT_TASK_CHECK=OK")
        return 0

    print("RUNTIME_RECONNECT_TASK_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
