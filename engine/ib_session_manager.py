# ib_session_manager.py
"""
Session Manager для IB runtime.

Призначення:
- керування lifecycle IBAdapter;
- reconnect без перезапуску всього LGE;
- ізоляція старого IB API thread після disconnect;
- SAFE_DISCONNECTED policy на рівні майбутнього IBRuntimeService.

RoadMap75:
- production runtime architecture для Interactive Brokers.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Optional

from engine.ib_adapter import IBAdapter
from engine.ib_history import (
    IBHistoryDownloadResult,
    IBHistoryProgressCallback,
)

LOGGER = logging.getLogger(__name__)


class IBSessionManager:
    """
    Lifecycle manager для IB adapter.
    """

    def __init__(
        self,
        host: str | None = None,
        demo_port: int | None = None,
        live_port: int | None = None,
        client_id: int | None = None,
    ) -> None:
        """
        Ініціалізувати IB session manager.

        За замовчуванням:
        - DEMO / paper trading TWS: 7497;
        - LIVE TWS: 7496.

        IB Gateway порти 4002/4001 поки не вмикаємо автоматично.
        Це буде окреме налаштування через UI/config.
        """

        self._lock = threading.RLock()

        self._session_generation: int = 0

        self._active_adapter: Optional[IBAdapter] = None

        self._active_account_mode: str = ""

        self._host = host or os.getenv("IB_HOST", "127.0.0.1")
        self._demo_port = demo_port or int(os.getenv("IB_DEMO_PORT", "7497"))
        self._live_port = live_port or int(os.getenv("IB_LIVE_PORT", "7496"))
        self._client_id = client_id or int(os.getenv("IB_CLIENT_ID", "1"))

    # =========================================================
    # PUBLIC
    # =========================================================

    def get_active_adapter(self) -> Optional[IBAdapter]:
        """
        Повернути активний adapter.
        """
        with self._lock:
            return self._active_adapter

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Отримати read-only IB evidence через активний adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.get_virtual_position_leg_evidence_snapshot()

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming Forex quotes from the adapter."""
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.get_forex_quote_snapshot(symbol_names)

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP через активний IB adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.modify_position_sl_tp(
            position_id=position_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def modify_virtual_position_leg_sl_tp(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        order_ref: str = "",
    ) -> dict:
        """Modify one exact persisted IB virtual leg."""
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.modify_virtual_position_leg_sl_tp(
            position_uid=position_uid,
            position_id=position_id,
            account_id=account_id,
            symbol_name=symbol_name,
            position_side=position_side,
            position_volume=position_volume,
            parent_order_id=parent_order_id,
            stop_loss_order_id=stop_loss_order_id,
            take_profit_order_id=take_profit_order_id,
            current_oca_group=current_oca_group,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_ref=order_ref,
        )

    def close_virtual_position_leg(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        comment: str = "LGE virtual-leg close",
    ) -> dict:
        """Close one exact persisted IB virtual leg."""
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.close_virtual_position_leg(
            position_uid=position_uid,
            position_id=position_id,
            account_id=account_id,
            symbol_name=symbol_name,
            position_side=position_side,
            position_volume=position_volume,
            parent_order_id=parent_order_id,
            stop_loss_order_id=stop_loss_order_id,
            take_profit_order_id=take_profit_order_id,
            current_oca_group=current_oca_group,
            comment=comment,
        )

    def get_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> IBHistoryDownloadResult:
        """Download historical bars through the active IB session."""
        adapter = self.get_active_adapter()
        if adapter is None:
            raise RuntimeError("No active IB adapter")
        return adapter.get_historical_bars(
            symbol_name=symbol_name,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )

    def get_active_account_mode(self) -> str:
        """
        Повернути активний account mode.
        """
        with self._lock:
            return self._active_account_mode

    def connect_demo(self) -> IBAdapter:
        """
        Створити нову DEMO/PAPER IB session.
        """
        return self._connect(account_mode="DEMO")

    def connect_live(self) -> IBAdapter:
        """
        Створити нову LIVE IB session.
        """
        return self._connect(account_mode="LIVE")

    def reconnect(self) -> Optional[IBAdapter]:
        """
        Reconnect через новий IBAdapter.
        """
        with self._lock:
            account_mode = self._active_account_mode

            if self._active_adapter is None:
                LOGGER.warning("IB reconnect requested but no active adapter exists.")
                return None

            if not account_mode:
                LOGGER.warning("IB reconnect requested but account_mode is empty.")
                return None

        LOGGER.warning("IB reconnect started. Old adapter will be disconnected.")

        return self._connect(account_mode=account_mode)

    def disconnect(self) -> None:
        """
        Повне відключення поточної IB session.
        """
        with self._lock:
            old_adapter = self._active_adapter

            self._active_adapter = None
            self._active_account_mode = ""

            self._session_generation += 1

        if old_adapter is not None:
            LOGGER.warning("Disconnecting active IB adapter.")

            try:
                old_adapter.disconnect()
            except Exception:  # noqa
                LOGGER.exception("IB adapter disconnect() failed.")

    # =========================================================
    # INTERNAL
    # =========================================================

    def _connect(
        self,
        account_mode: str,
    ) -> IBAdapter:
        """
        Створити новий IBAdapter та відключити старий.
        """

        normalized_mode = account_mode.upper().strip()

        if normalized_mode not in {"DEMO", "LIVE"}:
            raise ValueError(f"Unsupported IB account_mode: {account_mode}")

        with self._lock:
            old_adapter = self._active_adapter

            self._session_generation += 1
            session_generation = self._session_generation

            host = self._host
            port = self._resolve_port(normalized_mode)
            client_id = self._client_id

            LOGGER.warning(
                "Creating new IB adapter. "
                "session_generation=%s account_mode=%s host=%s port=%s clientId=%s",
                session_generation,
                normalized_mode,
                host,
                port,
                client_id,
            )

            adapter = IBAdapter(
                host=host,
                port=port,
                client_id=client_id,
                logger=LOGGER,
            )

            self._active_adapter = adapter
            self._active_account_mode = normalized_mode

        # -----------------------------------------------------
        # disconnect old adapter OUTSIDE LOCK
        # -----------------------------------------------------

        if old_adapter is not None:
            try:
                LOGGER.warning("Disconnecting previous IB adapter.")
                old_adapter.disconnect()
            except Exception:  # noqa
                LOGGER.exception("disconnect() failed on old IB adapter.")

        # -----------------------------------------------------
        # connect new adapter
        # -----------------------------------------------------

        connected = adapter.connect()

        if connected:
            LOGGER.info(
                "New IB adapter connected. session_generation=%s",
                session_generation,
            )
        else:
            LOGGER.warning(
                "New IB adapter created but NOT connected. " "session_generation=%s",
                session_generation,
            )

        return adapter

    def _resolve_port(
        self,
        account_mode: str,
    ) -> int:
        """
        Визначити порт для IB account mode.
        """
        if account_mode == "LIVE":
            return self._live_port

        return self._demo_port
