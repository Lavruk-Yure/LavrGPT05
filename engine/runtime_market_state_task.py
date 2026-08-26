# runtime_market_state_task.py
"""
Scheduler task для оновлення market state.

RoadMap68:
- інтеграція із RuntimeScheduler;
- періодична перевірка market state;
- broker-independent логіка;
- без залежності від UI.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from engine.market_availability_state import (
    detect_market_state,
)

logger = logging.getLogger(__name__)


class RuntimeMarketStateTask:
    """
    Runtime task для періодичного оновлення market state.
    """

    def __init__(
        self,
        broker: str,
        symbol_name: str,
        logger_: logging.Logger | None = None,
    ) -> None:
        self._logger = logger_ or logger

        self._broker = broker
        self._symbol_name = symbol_name

        self._last_state = "UNKNOWN"
        self._last_check_utc = ""
        self._market_checks_count = 0

    @property
    def last_state(self) -> str:
        """
        Повернути останній market state.
        """
        return self._last_state

    @property
    def last_check_utc(self) -> str:
        """
        Повернути UTC-час останньої перевірки.
        """
        return self._last_check_utc

    @property
    def market_checks_count(self) -> int:
        """
        Повернути кількість виконаних перевірок market state.
        """
        return self._market_checks_count

    def refresh_market_state(self) -> None:
        """
        Виконати періодичне оновлення market state.
        """

        self._market_checks_count += 1

        checked_utc = datetime.now(UTC)

        result = detect_market_state(
            broker=self._broker,
            symbol_name=self._symbol_name,
            checked_utc=checked_utc,
        )

        self._last_state = result.state
        self._last_check_utc = checked_utc.replace(microsecond=0).isoformat()

        self._logger.info(
            "Runtime market check | "
            "broker=%s | "
            "symbol=%s | "
            "state=%s | "
            "market_order=%s | "
            "pending_order=%s | "
            "count=%s",
            self._broker,
            self._symbol_name,
            result.state,
            result.can_place_market_order,
            result.can_place_pending_order,
            self._market_checks_count,
        )
