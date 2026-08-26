# runtime_reconnect_task.py
"""
Runtime reconnect task.

RoadMap73:
- reconnect task працює через Runtime Service;
- task не знає про конкретний broker adapter;
- adapter/session details приховані всередині service layer.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_constants import RUNTIME_RECONNECT_COOLDOWN_SECONDS

LOGGER = logging.getLogger(__name__)


class RuntimeReconnectServiceProtocol(Protocol):
    """
    Мінімальний protocol для broker runtime service.
    """

    def reconnect(self) -> object | None:
        """
        Виконати reconnect через service layer.
        """

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути runtime broker health.
        """


class RuntimeReconnectTask:
    """
    Runtime reconnect task для scheduler.
    """

    def __init__(
        self,
        runtime_service: RuntimeReconnectServiceProtocol,
        reconnect_cooldown_seconds: float = RUNTIME_RECONNECT_COOLDOWN_SECONDS,
        logger_: logging.Logger | None = None,
        failure_backoff_seconds: tuple[float, ...] = (),
    ) -> None:
        """
        Ініціалізувати reconnect task.
        """
        self._logger = logger_ or LOGGER
        self._lock = threading.RLock()

        self._runtime_service = runtime_service
        self._reconnect_cooldown_seconds = max(
            0.0,
            float(reconnect_cooldown_seconds),
        )
        self._failure_backoff_seconds = tuple(
            max(0.0, float(value)) for value in failure_backoff_seconds
        )

        self._last_reconnect_monotonic: float = 0.0
        self._next_reconnect_monotonic: float = 0.0
        self._reconnect_attempts: int = 0
        self._consecutive_failures: int = 0

    @property
    def reconnect_attempts(self) -> int:
        """
        Повернути кількість reconnect attempts.
        """
        return self._reconnect_attempts

    @property
    def consecutive_failures(self) -> int:
        """Return the current consecutive reconnect failure count."""
        return self._consecutive_failures

    def run_once(self) -> None:
        """
        Виконати одну reconnect iteration.
        """
        with self._lock:
            broker_health = self._runtime_service.get_broker_health()

            if broker_health.is_connected():
                self._reset_failure_backoff_locked()
                return

            if not broker_health.allows_automatic_reconnect():
                return

            now = time.monotonic()
            if now < self._next_reconnect_monotonic:
                return

            delta = now - self._last_reconnect_monotonic

            if delta < self._reconnect_cooldown_seconds:
                return

            self._last_reconnect_monotonic = now
            self._reconnect_attempts += 1

            self._logger.warning(
                "Reconnect attempt #%s started.",
                self._reconnect_attempts,
            )

        self._perform_reconnect()

    def check_and_reconnect(self) -> None:
        """
        Backward-compatible alias для scheduler tests.
        """
        self.run_once()

    def _perform_reconnect(self) -> None:
        """
        Виконати reconnect через runtime service.
        """
        try:
            self._runtime_service.reconnect()

            broker_health = self._runtime_service.get_broker_health()

            if broker_health.is_connected():
                with self._lock:
                    self._reset_failure_backoff_locked()
                self._logger.warning(
                    "Runtime service reconnect successful.",
                )
                return

            self._logger.warning(
                "Runtime service reconnect finished but broker is not connected. "
                "state=%s last_error=%s",
                broker_health.state,
                broker_health.last_error,
            )
            self._register_reconnect_failure()

        except Exception as exc:  # noqa: BLE001
            self._logger.exception(
                "Runtime service reconnect failed: %s",
                exc,
            )
            self._register_reconnect_failure()

    def _register_reconnect_failure(self) -> None:
        """Register one failure and arm an optional adaptive retry backoff."""
        with self._lock:
            self._consecutive_failures += 1
            if not self._failure_backoff_seconds:
                return

            index = min(
                self._consecutive_failures - 1,
                len(self._failure_backoff_seconds) - 1,
            )
            backoff_seconds = self._failure_backoff_seconds[index]
            self._next_reconnect_monotonic = time.monotonic() + backoff_seconds

            self._logger.warning(
                "Reconnect backoff armed after failure #%s: %.0f seconds.",
                self._consecutive_failures,
                backoff_seconds,
            )

    def _reset_failure_backoff_locked(self) -> None:
        """Reset failure/backoff state after a successful connection."""
        self._consecutive_failures = 0
        self._next_reconnect_monotonic = 0.0
