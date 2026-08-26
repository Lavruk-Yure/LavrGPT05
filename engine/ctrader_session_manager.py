# ctrader_session_manager.py
"""Session Manager для cTrader runtime.

Керує lifecycle активного adapter, reconnect та делегує broker operations.
Для історії прозоро передає progress callback, не додаючи UI-залежностей.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from datetime import datetime
from typing import Optional

from engine.ctrader_adapter import HOST_DEMO, HOST_LIVE, PORT, CTraderAdapter
from engine.ctrader_history import (
    CTraderHistoryDownloadResult,
    CTraderHistoryProgressCallback,
)
from engine.runtime_constants import (
    CTRADER_HOST_CHECK_TIMEOUT_SECONDS,
    CTRADER_LATE_CONNECT_TIMEOUT_SECONDS,
    CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS,
    CTRADER_STARTUP_READINESS_GRACE_SECONDS,
    CTRADER_STARTUP_READINESS_POLL_INTERVAL_SECONDS,
    CTRADER_STARTUP_READINESS_PROBE_TIMEOUT_SECONDS,
)

LOGGER = logging.getLogger(__name__)


class CTraderSessionManager:
    """
    Lifecycle manager для cTrader adapter.
    """

    def __init__(self) -> None:
        """
        Ініціалізація manager.
        """
        self._lock = threading.RLock()

        self._session_generation: int = 0

        self._active_adapter: Optional[CTraderAdapter] = None

        self._active_account_mode: str = ""

    # =========================================================
    # PUBLIC
    # =========================================================

    def get_active_adapter(self) -> Optional[CTraderAdapter]:
        """
        Повернути активний adapter.
        """
        with self._lock:
            return self._active_adapter

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming Forex quotes from the active adapter."""
        adapter = self.get_active_adapter()
        if adapter is None:
            return {
                "captured_utc": "",
                "complete": False,
                "quotes": {},
                "subscribed_symbols": [],
            }
        return adapter.get_forex_quote_snapshot(symbol_names)

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        """Download historical bars through the active cTrader session."""
        adapter = self.get_active_adapter()
        if adapter is None:
            raise RuntimeError("No active cTrader adapter")
        return adapter.get_historical_trendbars(
            symbol_name=symbol_name,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP через активний cTrader adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active cTrader adapter")

        return adapter.modify_position_sl_tp(
            position_id=position_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def get_active_account_mode(self) -> str:
        """
        Повернути активний account mode.
        """
        with self._lock:
            return self._active_account_mode

    def prepare_startup_connection(
        self,
        account_mode: str,
        timeout_seconds: float = CTRADER_STARTUP_READINESS_GRACE_SECONDS,
        poll_interval_seconds: float = CTRADER_STARTUP_READINESS_POLL_INTERVAL_SECONDS,
    ) -> bool:
        """Wait for bounded DNS/TCP readiness before Startup AutoConnect.

        This method does not create or retire an adapter and does not advance
        session generation. It only preserves the intended account mode and
        polls broker reachability for a short bounded grace period.
        """
        normalized_mode = account_mode.upper().strip()

        if normalized_mode not in {"DEMO", "LIVE"}:
            raise ValueError(f"Unsupported cTrader account_mode: {account_mode}")

        with self._lock:
            self._active_account_mode = normalized_mode

        host, port = self._get_ctrader_host_port(normalized_mode)

        return self._wait_for_ctrader_host_ready(
            host=host,
            port=port,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    def connect_demo(self) -> Optional[CTraderAdapter]:
        """
        Створити нову DEMO session.
        """
        return self._connect(account_mode="DEMO")

    def connect_live(self) -> Optional[CTraderAdapter]:
        """
        Створити нову LIVE session.
        """
        return self._connect(account_mode="LIVE")

    def reconnect(self) -> Optional[CTraderAdapter]:
        """
        Reconnect через новий adapter.
        """
        with self._lock:
            account_mode = self._active_account_mode

            if not account_mode:
                LOGGER.warning("cTrader reconnect requested but account_mode is empty.")
                return None

        LOGGER.warning("cTrader reconnect started. Old adapter will be retired.")

        return self._connect(account_mode=account_mode)

    def disconnect(self) -> None:
        """
        Повне відключення поточної session.
        """
        with self._lock:

            old_adapter = self._active_adapter

            self._active_adapter = None

            self._active_account_mode = ""

            self._session_generation += 1

        if old_adapter is not None:

            LOGGER.warning("Disconnecting active cTrader adapter.")

            try:
                old_adapter.retire_session()

            except Exception:  # noqa
                LOGGER.exception("retire_session() failed during disconnect.")

            try:
                old_adapter.disconnect()

            except Exception:  # noqa
                LOGGER.exception("disconnect() failed.")

    # =========================================================
    # INTERNAL
    # =========================================================

    def _connect(
        self,
        account_mode: str,
    ) -> CTraderAdapter | None:
        """
        Створити новий cTrader adapter.

        Для cTrader не можна авторизувати новий OpenAPI client,
        поки стара OpenAPI session ще жива: сервер може повернути
        ALREADY_LOGGED_IN.

        Тому порядок такий:
        - зберегти account_mode як намір reconnect;
        - перевірити TCP-доступність host;
        - забрати старий active_adapter;
        - retire/disconnect старий adapter;
        - bounded wait на evidence закриття старої session;
        - створити candidate adapter;
        - якщо candidate connected -> зробити active;
        - якщо candidate failed -> active лишається None, account_mode збережений.
        """

        normalized_mode = account_mode.upper().strip()

        if normalized_mode not in {"DEMO", "LIVE"}:
            raise ValueError(f"Unsupported cTrader account_mode: {account_mode}")

        with self._lock:
            self._active_account_mode = normalized_mode

        host, port = self._get_ctrader_host_port(normalized_mode)

        if not self._is_ctrader_host_reachable(
            host,
            port,
        ):
            LOGGER.warning(
                "cTrader host unreachable. host=%s port=%s",
                host,
                port,
            )
            return None

        with self._lock:
            old_adapter = self._active_adapter
            self._active_adapter = None

            self._session_generation += 1
            session_generation = self._session_generation

        if old_adapter is not None:
            try:
                LOGGER.warning("Retiring previous cTrader adapter before reconnect.")
                old_adapter.retire_session()
            except Exception:  # noqa
                LOGGER.exception("retire_session() failed on previous adapter.")

            old_session_closed = old_adapter.wait_for_retired_disconnect(
                timeout_seconds=CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS,
            )
            if not old_session_closed:
                LOGGER.warning(
                    "Old cTrader session close evidence timeout. "
                    "session_generation=%s timeout_seconds=%s",
                    session_generation,
                    CTRADER_OLD_SESSION_CLOSE_TIMEOUT_SECONDS,
                )

            try:
                old_adapter.disconnect()
            except Exception:  # noqa
                LOGGER.exception("disconnect() failed on previous adapter.")

        LOGGER.warning(
            "Creating new cTrader candidate adapter. "
            "session_generation=%s account_mode=%s",
            session_generation,
            normalized_mode,
        )

        candidate_adapter = CTraderAdapter.from_env(
            account_mode=normalized_mode,
        )

        candidate_adapter.set_session_generation(session_generation)

        connected = candidate_adapter.connect()

        if not connected:
            connected = self._wait_for_late_connect(
                adapter=candidate_adapter,
                session_generation=session_generation,
                timeout_seconds=CTRADER_LATE_CONNECT_TIMEOUT_SECONDS,
            )

        if not connected:
            LOGGER.warning(
                "New cTrader candidate adapter NOT connected. session_generation=%s",
                session_generation,
            )

            try:
                candidate_adapter.retire_session()
            except Exception:  # noqa
                LOGGER.exception("retire_session() failed on candidate adapter.")

            try:
                candidate_adapter.disconnect()
            except Exception:  # noqa
                LOGGER.exception("disconnect() failed on candidate adapter.")

            return None

        with self._lock:
            self._active_adapter = candidate_adapter
            self._active_account_mode = normalized_mode

        LOGGER.info(
            "New cTrader adapter promoted to active. session_generation=%s",
            session_generation,
        )

        return candidate_adapter

    def _wait_for_late_connect(  # noqa
        self,
        adapter: CTraderAdapter,
        session_generation: int,
        timeout_seconds: float = CTRADER_LATE_CONNECT_TIMEOUT_SECONDS,
    ) -> bool:
        """Wait for one bounded late cTrader connect/auth completion event."""
        LOGGER.warning(
            "Waiting for late cTrader connect. "
            "session_generation=%s timeout_seconds=%s",
            session_generation,
            timeout_seconds,
        )

        if not adapter.is_session_alive():
            LOGGER.warning(
                "Late connect wait stopped: adapter is retired. "
                "session_generation=%s",
                session_generation,
            )
            return False

        if adapter.is_connected():
            return True

        connected = adapter.wait_for_connect_result(
            timeout_seconds=max(0.0, float(timeout_seconds)),
        )

        if not adapter.is_session_alive():
            LOGGER.warning(
                "Late connect result ignored: adapter is retired. "
                "session_generation=%s",
                session_generation,
            )
            return False

        if connected or adapter.is_connected():
            LOGGER.info(
                "Late cTrader connect accepted. session_generation=%s",
                session_generation,
            )
            return True

        return False

    @staticmethod
    def _get_ctrader_host_port(account_mode: str) -> tuple[str, int]:
        """
        Повернути cTrader host/port для DEMO або LIVE.
        """

        normalized_mode = account_mode.upper().strip()

        if normalized_mode == "DEMO":
            return HOST_DEMO, int(PORT)

        if normalized_mode == "LIVE":
            return HOST_LIVE, int(PORT)

        raise ValueError(f"Unsupported cTrader account_mode: {account_mode}")

    def _wait_for_ctrader_host_ready(
        self,
        host: str,
        port: int,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> bool:
        """Poll DNS/TCP readiness without creating a broker adapter."""
        timeout = max(0.0, float(timeout_seconds))
        poll_interval = max(0.01, float(poll_interval_seconds))
        deadline = time.monotonic() + timeout
        wait_event = threading.Event()

        while True:
            remaining = max(0.0, deadline - time.monotonic())
            probe_timeout = min(
                CTRADER_STARTUP_READINESS_PROBE_TIMEOUT_SECONDS,
                max(0.01, remaining),
            )

            if self._is_ctrader_host_reachable(
                host=host,
                port=port,
                timeout_seconds=probe_timeout,
            ):
                return True

            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return False

            wait_event.wait(min(poll_interval, remaining))

    @staticmethod
    def _is_ctrader_host_reachable(
        host: str,
        port: int,
        timeout_seconds: float = CTRADER_HOST_CHECK_TIMEOUT_SECONDS,
    ) -> bool:
        """Check cTrader DNS/TCP reachability with a bounded TCP timeout."""
        try:
            with socket.create_connection(
                (host, port),
                timeout=max(0.01, float(timeout_seconds)),
            ):
                return True

        except OSError:
            return False
