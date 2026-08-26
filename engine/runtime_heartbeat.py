# runtime_heartbeat.py
"""
Runtime heartbeat для LGE.

RoadMap68:
- інтеграція із RuntimeScheduler;
- контроль, що runtime живий;
- без залежності від UI;
- без залежності від broker API.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class RuntimeHeartbeat:
    """
    Стан і логіка runtime heartbeat.
    """

    def __init__(
        self,
        logger_: logging.Logger | None = None,
    ) -> None:
        self._logger = logger_ or logger

        self._heartbeat_counter = 0
        self._last_heartbeat_utc: str = ""

    @property
    def heartbeat_counter(self) -> int:
        """
        Повернути кількість heartbeat ticks.
        """
        return self._heartbeat_counter

    @property
    def last_heartbeat_utc(self) -> str:
        """
        Повернути UTC-час останнього heartbeat.
        """
        return self._last_heartbeat_utc

    def heartbeat(self) -> None:
        """
        Виконати один runtime heartbeat tick.
        """

        self._heartbeat_counter += 1

        self._last_heartbeat_utc = datetime.now(UTC).replace(microsecond=0).isoformat()

        self._logger.info(
            "Runtime heartbeat | count=%s | utc=%s",
            self._heartbeat_counter,
            self._last_heartbeat_utc,
        )
