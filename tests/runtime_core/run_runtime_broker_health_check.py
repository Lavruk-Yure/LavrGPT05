# run_runtime_broker_health_check.py
"""
Перевірка RuntimeBrokerHealth.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_broker_health import (  # noqa: E402
    HEALTH_CONNECTED,
    HEALTH_DISCONNECTED,
    HEALTH_ERROR,
    HEALTH_RECONNECTING,
    HEALTH_SAFE_DISCONNECTED,
    HEALTH_UNKNOWN,
    RuntimeBrokerHealth,
)


def main() -> int:
    """
    Запустити перевірку RuntimeBrokerHealth.
    """
    health = RuntimeBrokerHealth()

    checks_unknown = [
        health.state == HEALTH_UNKNOWN,
        health.is_connected() is False,
        health.last_error == "",
        health.allows_automatic_reconnect() is True,
    ]

    health.set_connected(updated_utc="2026-05-31 13:00")

    checks_connected = [
        health.state == HEALTH_CONNECTED,
        health.is_connected() is True,
        health.last_error == "",
        health.updated_utc == "2026-05-31 13:00",
    ]

    health.set_safe_disconnected(
        updated_utc="2026-05-31 13:05",
        error="Internet connection lost.",
    )

    checks_safe_disconnected = [
        health.state == HEALTH_SAFE_DISCONNECTED,
        health.is_connected() is False,
        health.last_error == "Internet connection lost.",
        health.updated_utc == "2026-05-31 13:05",
    ]

    health.set_reconnecting(updated_utc="2026-05-31 13:06")

    checks_reconnecting = [
        health.state == HEALTH_RECONNECTING,
        health.last_error == "",
        health.updated_utc == "2026-05-31 13:06",
    ]

    health.set_disconnected(
        updated_utc="2026-05-31 13:07",
        error="Manual disconnect.",
    )

    checks_disconnected = [
        health.state == HEALTH_DISCONNECTED,
        health.last_error == "Manual disconnect.",
        health.updated_utc == "2026-05-31 13:07",
        health.allows_automatic_reconnect() is True,
    ]

    health.set_disconnected(
        updated_utc="2026-05-31 13:07:30",
        error="Manual disconnect.",
        manual=True,
    )

    checks_manual_disconnect = [
        health.state == HEALTH_DISCONNECTED,
        health.last_error == "Manual disconnect.",
        health.allows_automatic_reconnect() is False,
    ]

    health.set_error(
        updated_utc="2026-05-31 13:08",
        error="Unexpected broker error.",
    )

    checks_error = [
        health.state == HEALTH_ERROR,
        health.last_error == "Unexpected broker error.",
        health.updated_utc == "2026-05-31 13:08",
    ]

    health.clear()

    checks_clear = [
        health.state == HEALTH_UNKNOWN,
        health.is_connected() is False,
        health.last_error == "",
        health.updated_utc == "",
    ]

    checks = (
        checks_unknown
        + checks_connected
        + checks_safe_disconnected
        + checks_reconnecting
        + checks_disconnected
        + checks_manual_disconnect
        + checks_error
        + checks_clear
    )

    if all(checks):
        print("RUNTIME_BROKER_HEALTH_CHECK=OK")
        return 0

    print("RUNTIME_BROKER_HEALTH_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
