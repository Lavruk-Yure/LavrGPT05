# ctrader_runtime_service.py
"""Runtime service для cTrader.

Зовнішній service API для RuntimeEngine над CTraderSessionManager. Модуль не
містить UI; history progress callback лише прозоро проходить service chain.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime
from typing import Optional, Protocol

from engine.ctrader_adapter import CTraderAdapter
from engine.ctrader_history import (
    CTraderHistoryDownloadResult,
    CTraderHistoryProgressCallback,
)
from engine.ctrader_session_manager import CTraderSessionManager
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_events import (
    RuntimeEvent,
    RuntimeEventType,
)

LOGGER = logging.getLogger(__name__)


class CTraderSessionManagerProtocol(Protocol):
    """
    Мінімальний protocol для cTrader session manager.
    """

    def prepare_startup_connection(
        self,
        account_mode: str,
    ) -> bool:
        """Check bounded Startup Readiness without creating an adapter."""
        ...

    def connect_demo(self) -> CTraderAdapter:
        """
        Підключити DEMO session.
        """

    def connect_live(self) -> CTraderAdapter:
        """
        Підключити LIVE session.
        """

    def reconnect(self) -> Optional[CTraderAdapter]:
        """
        Виконати reconnect.
        """

    def disconnect(self) -> None:
        """
        Відключити session.
        """

    def get_active_adapter(self) -> Optional[CTraderAdapter]:
        """
        Повернути active adapter.
        """
        ...

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming Forex quotes."""
        ...

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        """Download cTrader historical bars via the active session."""
        ...

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP через active cTrader session.
        """
        ...


class CTraderRuntimeService:
    """
    Runtime service wrapper над CTraderSessionManager.
    """

    def __init__(
        self,
        session_manager: Optional[CTraderSessionManagerProtocol] = None,
    ) -> None:
        """
        Ініціалізувати cTrader runtime service.
        """
        self._session_manager = session_manager or CTraderSessionManager()

        self._account_state = RuntimeAccountState()

        self._broker_health = RuntimeBrokerHealth()

        self._runtime_events = deque(maxlen=100)

    def prepare_startup_connection(
        self,
        account_mode: str,
    ) -> bool:
        """Prepare Startup AutoConnect without creating a broker adapter."""
        ready = self._session_manager.prepare_startup_connection(
            account_mode=account_mode,
        )

        if ready:
            return True

        self._account_state.clear()
        self._broker_health.set_safe_disconnected(
            error="cTrader Startup Readiness timeout.",
        )
        self._add_event(
            RuntimeEventType.BROKER_CONNECTION_ERROR,
            "cTrader Startup Readiness timeout.",
        )
        return False

    def connect_demo(self) -> CTraderAdapter:
        """
        Підключити DEMO session.
        """
        LOGGER.info("cTrader runtime service: connect DEMO requested.")

        self._add_event(
            RuntimeEventType.BROKER_CONNECTING,
            "cTrader DEMO connect requested.",
        )

        adapter = self._session_manager.connect_demo()

        if adapter is not None and adapter.is_connected():
            self._broker_health.set_connected()
            self._load_account_state(adapter)
            self._add_event(
                RuntimeEventType.BROKER_CONNECTED,
                "cTrader DEMO connected.",
            )
        else:
            self._account_state.clear()
            self._broker_health.set_disconnected(
                error="cTrader DEMO connection was not established.",
            )
            self._add_event(
                RuntimeEventType.BROKER_CONNECTION_ERROR,
                "cTrader DEMO connection failed.",
            )

        return adapter

    def connect_live(self) -> CTraderAdapter:
        """
        Підключити LIVE session.
        """
        LOGGER.info("cTrader runtime service: connect LIVE requested.")

        adapter = self._session_manager.connect_live()

        if adapter is not None and adapter.is_connected():
            self._broker_health.set_connected()
            self._load_account_state(adapter)
        else:
            self._account_state.clear()
            self._broker_health.set_disconnected(
                error="cTrader LIVE connection was not established.",
            )

        return adapter

    def reconnect(self) -> Optional[CTraderAdapter]:
        """
        Виконати reconnect поточної cTrader session.
        """
        LOGGER.info("cTrader runtime service: reconnect requested.")
        self._account_state.clear()
        self._broker_health.set_reconnecting()

        self._add_event(
            RuntimeEventType.RECONNECT_STARTED,
            "cTrader reconnect started.",
        )

        adapter = self._session_manager.reconnect()

        if adapter is not None and adapter.is_connected():
            self._broker_health.set_connected()
            self._load_account_state(adapter)
            self._add_event(
                RuntimeEventType.RECONNECT_SUCCESS,
                "cTrader reconnect successful.",
            )
        else:
            self._account_state.clear()
            self._broker_health.set_safe_disconnected(
                error="cTrader reconnect did not restore connection.",
            )
            self._add_event(
                RuntimeEventType.RECONNECT_FAILED,
                "cTrader reconnect failed.",
            )

        return adapter

    def disconnect(self) -> None:
        """
        Відключити поточну cTrader session.
        """
        LOGGER.info("cTrader runtime service: disconnect requested.")
        self._session_manager.disconnect()
        self._account_state.clear()
        self._broker_health.set_disconnected(
            error="Manual disconnect.",
            manual=True,
        )
        self._add_event(
            RuntimeEventType.BROKER_DISCONNECTED,
            "Manual cTrader disconnect.",
        )

    def get_active_adapter(self) -> Optional[CTraderAdapter]:
        """
        Повернути активний cTrader adapter.
        """
        return self._session_manager.get_active_adapter()

    def get_account_state(self) -> RuntimeAccountState:
        """
        Повернути runtime account state.
        """
        return self._account_state

    def get_account_list(self) -> list[dict]:
        """
        Повернути список cTrader accounts з активного adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            return []

        if not hasattr(adapter, "get_account_list"):
            return []

        return adapter.get_account_list()

    def get_positions(self):
        """
        Повернути відкриті cTrader positions з active adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            return []

        return adapter.get_positions()

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict:
        """Return cached streaming Forex quotes through the session."""
        return self._session_manager.get_forex_quote_snapshot(symbol_names)

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        """Download cTrader historical bars through SessionManager."""
        return self._session_manager.get_historical_trendbars(
            symbol_name=symbol_name,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
            progress_callback=progress_callback,
        )

    def place_market_buy(
        self,
        symbol_name: str = "EURUSD",
        lots: float = 0.01,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual BUY",
    ):
        """
        Відкрити BUY MARKET через active cTrader adapter.
        """
        return self.place_market_order(
            symbol_name=symbol_name,
            side="BUY",
            lots=lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def place_market_sell(
        self,
        symbol_name: str = "EURUSD",
        lots: float = 0.01,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual SELL",
    ):
        """
        Відкрити SELL MARKET через active cTrader adapter.
        """
        return self.place_market_order(
            symbol_name=symbol_name,
            side="SELL",
            lots=lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ):
        """
        Відправити MARKET order через active cTrader adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active cTrader adapter")

        return adapter.place_market_order(
            symbol_name=symbol_name,
            side=side,
            lots=lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def close_position(
        self,
        position_id: int | str,
        lots: float | None = None,
    ):
        """
        Закрити cTrader position через active adapter.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            raise RuntimeError("No active cTrader adapter")

        return adapter.close_position(
            position_id=position_id,
            lots=lots,
        )

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити SL/TP cTrader position через session manager.
        """
        return self._session_manager.modify_position_sl_tp(
            position_id=position_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

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

    def refresh_broker_health(self) -> RuntimeBrokerHealth:
        """
        Оновити runtime broker health за фактичним станом active adapter.

        Це production-check для scheduler/watch/reconnect flow.
        """
        if not self._broker_health.allows_automatic_reconnect():
            return self._broker_health

        adapter = self.get_active_adapter()

        if adapter is None:
            self._account_state.clear()
            self._broker_health.set_disconnected(
                error="cTrader active adapter is missing.",
            )
            return self._broker_health

        if adapter.is_connected() and adapter.is_session_alive():
            self._broker_health.set_connected()

            if not self._account_state.is_loaded():
                self._load_account_state(adapter)

            return self._broker_health

        self._account_state.clear()
        self._broker_health.set_safe_disconnected(
            error="cTrader active adapter is not alive.",
        )
        return self._broker_health

    def refresh_account_state(self) -> RuntimeAccountState:
        """
        Перечитати cTrader account info і оновити RuntimeAccountState.

        Використовується для живого оновлення балансу в StatusBar.
        """
        adapter = self.get_active_adapter()

        if adapter is None:
            return self._account_state

        if not adapter.is_connected():
            return self._account_state

        if not adapter.is_session_alive():
            return self._account_state

        if hasattr(adapter, "refresh_account_info"):
            adapter.refresh_account_info()

        self._load_account_state(adapter)
        return self._account_state

    def _load_account_state(
        self,
        adapter: CTraderAdapter,
    ) -> None:
        """
        Завантажити RuntimeAccountState з CTraderAdapter.get_account_info().
        """
        account = adapter.get_account_info()

        if not account.account_id:
            self._account_state.clear()
            self._add_event(
                RuntimeEventType.ACCOUNT_UPDATED,
                "cTrader account state is empty.",
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
            "cTrader account state loaded.",
            payload=account.to_dict(),
        )
