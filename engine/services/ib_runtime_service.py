# ib_runtime_service.py
"""
Runtime service для Interactive Brokers.

Призначення:
- бути зовнішнім service API для RuntimeEngine;
- не розкривати IBSessionManager назовні;
- не містити UI, QMessageBox або перекладів;
- бути Source Of Truth для IB runtime connection state.

RoadMap75:
- production runtime layer для IB.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime
from typing import Optional, Protocol

from engine.ib_adapter import IBAdapter
from engine.ib_history import (
    IBHistoryDownloadResult,
    IBHistoryProgressCallback,
)
from engine.ib_session_manager import IBSessionManager
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_events import RuntimeEvent, RuntimeEventType

LOGGER = logging.getLogger(__name__)


class IBSessionManagerProtocol(Protocol):
    """
    Мінімальний protocol для IB session manager.
    """

    def connect_demo(self) -> IBAdapter:
        """
        Підключити DEMO/PAPER session.
        """
        ...

    def connect_live(self) -> IBAdapter:
        """
        Підключити LIVE session.
        """
        ...

    def reconnect(self) -> Optional[IBAdapter]:
        """
        Виконати reconnect.
        """
        ...

    def disconnect(self) -> None:
        """
        Відключити session.
        """
        ...

    def get_active_adapter(self) -> Optional[IBAdapter]:
        """
        Повернути active adapter.
        """
        ...

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Отримати read-only IB evidence snapshot.
        """
        ...

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming Forex quotes."""
        ...

    def get_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> IBHistoryDownloadResult:
        """Download historical bars through the active IB adapter."""
        ...

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
        ...

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP через активний IB adapter.
        """
        ...

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
        ...


class IBRuntimeService:
    """
    Runtime service wrapper над IBSessionManager.
    """

    def __init__(
        self,
        session_manager: Optional[IBSessionManagerProtocol] = None,
    ) -> None:
        """
        Ініціалізувати IB runtime service.
        """
        self._session_manager = session_manager or IBSessionManager()

        self._account_state = RuntimeAccountState()

        self._broker_health = RuntimeBrokerHealth()

        self._runtime_events = deque(maxlen=100)

    def connect_demo(self) -> IBAdapter:
        """
        Підключити IB DEMO/PAPER session.
        """
        LOGGER.info("IB runtime service: connect DEMO requested.")

        self._add_event(
            RuntimeEventType.BROKER_CONNECTING,
            "IB DEMO connect requested.",
        )

        adapter = self._session_manager.connect_demo()

        if adapter is not None and adapter.is_connected():
            self._broker_health.set_connected()
            self._load_account_state(adapter)
            self._add_event(
                RuntimeEventType.BROKER_CONNECTED,
                "IB DEMO connected.",
            )
        else:
            self._account_state.clear()
            self._broker_health.set_disconnected(
                error="IB DEMO connection was not established.",
            )
            self._add_event(
                RuntimeEventType.BROKER_CONNECTION_ERROR,
                "IB DEMO connection failed.",
            )

        return adapter

    def connect_live(self) -> IBAdapter:
        """
        Підключити IB LIVE session.
        """
        LOGGER.info("IB runtime service: connect LIVE requested.")

        self._add_event(
            RuntimeEventType.BROKER_CONNECTING,
            "IB LIVE connect requested.",
        )

        adapter = self._session_manager.connect_live()

        if adapter is not None and adapter.is_connected():
            self._broker_health.set_connected()
            self._load_account_state(adapter)
            self._add_event(
                RuntimeEventType.BROKER_CONNECTED,
                "IB LIVE connected.",
            )
        else:
            self._account_state.clear()
            self._broker_health.set_disconnected(
                error="IB LIVE connection was not established.",
            )
            self._add_event(
                RuntimeEventType.BROKER_CONNECTION_ERROR,
                "IB LIVE connection failed.",
            )

        return adapter

    def reconnect(self) -> Optional[IBAdapter]:
        """
        Виконати reconnect поточної IB session.
        """
        LOGGER.info("IB runtime service: reconnect requested.")

        self._account_state.clear()
        self._broker_health.set_reconnecting()

        self._add_event(
            RuntimeEventType.RECONNECT_STARTED,
            "IB reconnect started.",
        )

        adapter = self._session_manager.reconnect()

        if adapter is not None and adapter.is_connected():
            self._broker_health.set_connected()
            self._load_account_state(adapter)
            self._add_event(
                RuntimeEventType.RECONNECT_SUCCESS,
                "IB reconnect successful.",
            )
        else:
            self._account_state.clear()
            self._broker_health.set_safe_disconnected(
                error="IB reconnect did not restore connection.",
            )
            self._add_event(
                RuntimeEventType.RECONNECT_FAILED,
                "IB reconnect failed.",
            )

        return adapter

    def disconnect(self) -> None:
        """
        Відключити поточну IB session.
        """
        LOGGER.info("IB runtime service: disconnect requested.")

        self._session_manager.disconnect()

        self._account_state.clear()
        self._broker_health.set_disconnected(
            error="Manual disconnect.",
            manual=True,
        )

        self._add_event(
            RuntimeEventType.BROKER_DISCONNECTED,
            "Manual IB disconnect.",
        )

    def get_active_adapter(self) -> Optional[IBAdapter]:
        """
        Повернути активний IB adapter.
        """
        return self._session_manager.get_active_adapter()

    def get_account_state(self) -> RuntimeAccountState:
        """
        Повернути runtime account state.
        """
        return self._account_state

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути runtime broker health.
        """
        return self._broker_health

    def get_runtime_events(self) -> list[RuntimeEvent]:
        """
        Повернути список останніх runtime events.
        """
        return list(self._runtime_events)

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Отримати read-only virtual-leg evidence через session manager.
        """
        return self._session_manager.get_virtual_position_leg_evidence_snapshot()

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming Forex quotes through the session."""
        return self._session_manager.get_forex_quote_snapshot(symbol_names)

    def get_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> IBHistoryDownloadResult:
        """Download IB historical bars through SessionManager."""
        return self._session_manager.get_historical_bars(
            symbol_name=symbol_name,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )

    def get_positions(self) -> list:
        """
        Повернути відкриті IB positions з active adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            return []

        if not adapter.is_connected():
            return []

        return adapter.get_positions()

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        """
        Відправити IB MARKET order через active adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.place_market_order(
            symbol_name=symbol_name,
            side=side,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        """
        Закрити IB position через active adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return adapter.close_position(
            position_id=position_id,
            quantity=quantity,
            comment=comment,
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

        return self._session_manager.close_virtual_position_leg(
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

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP IB position через session manager.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active IB adapter")

        if not adapter.is_connected():
            raise RuntimeError("IB adapter is not connected")

        return self._session_manager.modify_position_sl_tp(
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

        return self._session_manager.modify_virtual_position_leg_sl_tp(
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

    def refresh_broker_health(self) -> RuntimeBrokerHealth:
        """
        Оновити runtime broker health за фактичним станом active adapter.
        """
        if not self._broker_health.allows_automatic_reconnect():
            return self._broker_health

        adapter = self.get_active_adapter()

        if adapter is None:
            self._account_state.clear()
            self._broker_health.set_disconnected(
                error="IB active adapter is missing.",
            )
            return self._broker_health

        if adapter.is_connected():
            self._broker_health.set_connected()

            if not self._account_state.is_loaded():
                self._load_account_state(adapter)

            return self._broker_health

        self._account_state.clear()
        self._broker_health.set_safe_disconnected(
            error=f"IB active adapter is not connected: {adapter.broker_state}.",
        )
        return self._broker_health

    def _load_account_state(
        self,
        adapter: IBAdapter,
    ) -> None:
        """
        Завантажити RuntimeAccountState з IBAdapter.get_account_info().
        """
        account = adapter.get_account_info()

        if not account.account_id:
            self._account_state.clear()
            self._add_event(
                RuntimeEventType.ACCOUNT_UPDATED,
                "IB account state is empty.",
            )
            return

        self._account_state.account_id = str(account.account_id)
        self._account_state.trader_login = None
        self._account_state.broker_name = account.broker

        self._account_state.currency = account.currency
        self._account_state.balance = account.balance
        self._account_state.equity = account.equity
        self._account_state.margin = account.margin_used
        self._account_state.free_margin = account.margin_free

        self._account_state.leverage = None

        self._account_state.snapshot_utc = (
            datetime.now(UTC).replace(microsecond=0).isoformat()
        )

        self._add_event(
            RuntimeEventType.ACCOUNT_LOADED,
            "IB account state loaded.",
            payload=account.to_dict(),
        )

    def refresh_account_state(self) -> RuntimeAccountState:
        """
        Перечитати IB account info і оновити RuntimeAccountState.

        Використовується для живого оновлення балансу в StatusBar.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            return self._account_state

        if not adapter.is_connected():
            return self._account_state

        self._load_account_state(adapter)
        return self._account_state

    def _add_event(
        self,
        event_type: RuntimeEventType,
        message: str = "",
        payload: dict | None = None,
    ) -> None:
        """
        Додати runtime event.
        """
        self._runtime_events.append(
            RuntimeEvent(
                event_type=event_type,
                message=message,
                payload=payload or {},
            )
        )

    def get_managed_accounts(self) -> list[str]:
        """
        Повернути список доступних IB accounts через active adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            return []

        return adapter.get_managed_accounts()
