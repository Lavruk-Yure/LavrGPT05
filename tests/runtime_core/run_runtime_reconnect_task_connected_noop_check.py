# run_runtime_reconnect_task_connected_noop_check.py
"""
RoadMap74.2.

Перевірка:
якщо broker health = CONNECTED,
RuntimeReconnectTask нічого не робить.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402


class ConnectedRuntimeServiceStub:
    """
    Runtime service stub зі станом CONNECTED.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати stub.
        """
        self.reconnect_calls = 0
        self.health_calls = 0
        self.health = RuntimeBrokerHealth()
        self.health.set_connected()

    def reconnect(self) -> object | None:
        """
        Reconnect не має викликатись.
        """
        self.reconnect_calls += 1
        return None

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути CONNECTED health.
        """
        self.health_calls += 1
        return self.health


def main() -> int:
    """
    Запустити перевірку no-op поведінки reconnect task.
    """
    service = ConnectedRuntimeServiceStub()
    task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=0.0,
    )

    task.run_once()
    task.check_and_reconnect()

    print("\n=== CONNECTED NO-OP CHECK ===")
    print(f"health_calls={service.health_calls}")
    print(f"reconnect_calls={service.reconnect_calls}")
    print(f"reconnect_attempts={task.reconnect_attempts}")
    print(f"broker_health_state={service.health.state}")

    checks = [
        service.health_calls == 2,
        service.reconnect_calls == 0,
        task.reconnect_attempts == 0,
        service.health.is_connected() is True,
    ]

    if all(checks):
        print("\nRUNTIME_RECONNECT_TASK_CONNECTED_NOOP_CHECK=OK")
        return 0

    print("\nRUNTIME_RECONNECT_TASK_CONNECTED_NOOP_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
