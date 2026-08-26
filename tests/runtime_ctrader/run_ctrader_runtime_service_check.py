# run_ctrader_runtime_service_check.py
"""
Перевірка CTraderRuntimeService.

Тестуємо:
- делегування в session manager;
- active adapter;
- runtime account state;
- runtime broker health.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional, Protocol

from engine.broker_account import BrokerAccount  # noqa: E402
from engine.services.ctrader_runtime_service import (  # noqa: E402
    CTraderRuntimeService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class DummyAdapter:
    """
    Dummy adapter з мінімальним connection state для service layer test.
    """

    def __init__(self, connected: bool = True) -> None:
        """
        Ініціалізувати dummy adapter.
        """
        self._connected = connected

    def is_connected(self) -> bool:
        """
        Повернути fake connection state.
        """
        return self._connected

    def get_account_info(self) -> BrokerAccount:  # noqa
        """
        Повернути dummy account info.
        """
        return BrokerAccount(
            broker="CTRADER",
            account_id="9870599",
            account_mode="DEMO",
            currency="USD",
            balance=869.75,
        )


class DummySessionManagerProtocol(Protocol):
    """
    Protocol для тестового dummy session manager.
    """

    def connect_demo(self) -> DummyAdapter:
        """
        Симуляція DEMO connect.
        """

    def connect_live(self) -> DummyAdapter:
        """
        Симуляція LIVE connect.
        """

    def reconnect(self) -> DummyAdapter:
        """
        Симуляція reconnect.
        """

    def disconnect(self) -> None:
        """
        Симуляція disconnect.
        """

    def get_active_adapter(self) -> Optional[DummyAdapter]:
        """
        Повернути active dummy adapter.
        """


class DummySessionManager:
    """
    Dummy session manager для перевірки делегування.
    """

    def __init__(self) -> None:
        self.demo_connected = False
        self.live_connected = False
        self.reconnect_called = False
        self.disconnect_called = False
        self.active_adapter: Optional[DummyAdapter] = None

    def connect_demo(self) -> DummyAdapter:
        """
        Симуляція DEMO connect.
        """
        self.demo_connected = True
        self.active_adapter = DummyAdapter()
        return self.active_adapter

    def connect_live(self) -> DummyAdapter:
        """
        Симуляція LIVE connect.
        """
        self.live_connected = True
        self.active_adapter = DummyAdapter()
        return self.active_adapter

    def reconnect(self) -> DummyAdapter:
        """
        Симуляція reconnect.
        """
        self.reconnect_called = True
        self.active_adapter = DummyAdapter()
        return self.active_adapter

    def disconnect(self) -> None:
        """
        Симуляція disconnect.
        """
        self.disconnect_called = True
        self.active_adapter = None

    def get_active_adapter(self) -> Optional[DummyAdapter]:
        """
        Повернути active adapter.
        """
        return self.active_adapter

    @staticmethod
    def get_forex_quote_snapshot(symbol_names: list[str]) -> dict:
        """Return one deterministic quote snapshot for service tests."""
        return {
            "captured_utc": "2026-07-28T09:00:00+00:00",
            "complete": True,
            "quotes": {
                symbol: {
                    "symbol_name": symbol,
                    "bid": 1.17074,
                    "ask": 1.17086,
                    "timestamp": "2026-07-28T09:00:00+00:00",
                }
                for symbol in symbol_names
            },
            "subscribed_symbols": list(symbol_names),
        }


def main() -> int:
    """
    Запустити перевірку CTraderRuntimeService.
    """
    manager = DummySessionManager()

    service = CTraderRuntimeService()
    service._session_manager = manager

    adapter_demo = service.connect_demo()
    adapter_active = service.get_active_adapter()

    broker_health_connected = service.get_broker_health().is_connected()
    runtime_events_before = service.get_runtime_events()

    adapter_reconnect = service.reconnect()
    quote_snapshot = service.get_forex_quote_snapshot(["EURUSD"])

    service.disconnect()
    broker_health_after_disconnect = service.get_broker_health()
    adapter_after_disconnect = service.get_active_adapter()
    account_state_after_disconnect = service.get_account_state()
    runtime_events_after = service.get_runtime_events()

    checks = [
        manager.demo_connected is True,
        manager.live_connected is False,
        manager.reconnect_called is True,
        manager.disconnect_called is True,
        adapter_demo is not None,
        adapter_active is adapter_demo,
        adapter_reconnect is not None,
        adapter_after_disconnect is None,
        account_state_after_disconnect.is_loaded() is False,
        account_state_after_disconnect.account_id is None,
        account_state_after_disconnect.currency == "",
        account_state_after_disconnect.balance is None,
        broker_health_connected is True,
        broker_health_after_disconnect.is_connected() is False,
        broker_health_after_disconnect.last_error == "Manual disconnect.",
        len(runtime_events_before) >= 1,
        len(runtime_events_after) >= 3,
        quote_snapshot["complete"] is True,
        quote_snapshot["quotes"]["EURUSD"]["bid"] == 1.17074,
        quote_snapshot["quotes"]["EURUSD"]["ask"] == 1.17086,
    ]

    if all(checks):
        print("  forex_quote_snapshot=True")
        print("CTRADER_RUNTIME_SERVICE_CHECK=OK")
        return 0

    print("CTRADER_RUNTIME_SERVICE_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
