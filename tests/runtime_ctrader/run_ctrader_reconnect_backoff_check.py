"""RoadMap99_02F deterministic cTrader reconnect backoff regression check.

The test drives RuntimeReconnectTask with a controlled cTrader-like service
that fails three reconnect attempts and succeeds on the fourth. It verifies the
60 -> 120 -> 300 second failure backoff, confirms that attempts are suppressed
inside each backoff window, and confirms that a successful reconnect resets the
consecutive-failure counter. No real network, broker session or broker order is
used; the purpose is to protect LGE from tight reconnect loops during external
cTrader/OpenAPI outages while preserving automatic recovery.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_reconnect_task import RuntimeReconnectTask  # noqa: E402


class _ControlledService:
    """Fail the first three reconnect calls and succeed on the fourth."""

    def __init__(self) -> None:
        self.health = RuntimeBrokerHealth()
        self.health.set_safe_disconnected(error="initial")
        self.reconnect_calls = 0

    def reconnect(self) -> object | None:
        self.reconnect_calls += 1
        if self.reconnect_calls >= 4:
            self.health.set_connected()
            return object()
        self.health.set_safe_disconnected(error="failed")
        return None

    def get_broker_health(self) -> RuntimeBrokerHealth:
        return self.health


def _run_at(task: RuntimeReconnectTask, now: float) -> None:
    with mock.patch(
        "engine.runtime_reconnect_task.time.monotonic",
        return_value=float(now),
    ):
        task.run_once()


def main() -> int:
    print(
        "cTrader Reconnect Backoff Check — RoadMap99_02F",
        file=sys.stderr,
        flush=True,
    )
    print(
        "  Simulating failures with 60/120/300 second backoff, then recovery.",
        file=sys.stderr,
        flush=True,
    )
    service = _ControlledService()
    task = RuntimeReconnectTask(
        runtime_service=service,
        reconnect_cooldown_seconds=0.0,
        failure_backoff_seconds=(60.0, 120.0, 300.0),
    )

    _run_at(task, 0.0)
    first_calls = service.reconnect_calls
    _run_at(task, 59.0)
    first_backoff_blocks = service.reconnect_calls == first_calls

    _run_at(task, 60.0)
    second_calls = service.reconnect_calls
    _run_at(task, 179.0)
    second_backoff_blocks = service.reconnect_calls == second_calls

    _run_at(task, 180.0)
    third_calls = service.reconnect_calls
    _run_at(task, 479.0)
    third_backoff_blocks = service.reconnect_calls == third_calls

    _run_at(task, 480.0)
    recovered = service.health.is_connected()
    failures_reset = task.consecutive_failures == 0

    checks = {
        "backoff_sequence_60_120_300": (
            first_backoff_blocks and second_backoff_blocks and third_backoff_blocks
        ),
        "fourth_attempt_recovers": (
            service.reconnect_calls == 4 and task.reconnect_attempts == 4 and recovered
        ),
        "success_resets_failure_count": failures_reset,
    }

    print("cTrader Reconnect Backoff result")
    for key, value in checks.items():
        print(f"  {key}={value}")

    ok = all(checks.values())
    print(f"CTRADER_RECONNECT_BACKOFF_CHECK={'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
