# run_runtime_engine_ctrader_service_check.py
"""
Перевірка RuntimeEngine + CTraderRuntimeService slot.

Тестуємо:
- RuntimeEngine приймає cTrader runtime service;
- connect_ctrader_demo делегує connect у service;
- context оновлює broker/account_mode/connection_state;
- engine events створюються.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from pprint import pprint

from engine.runtime_broker_health import RuntimeBrokerHealth

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from engine.db.runtime_db import get_runtime_database_path  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402


class DummyAdapter:
    """
    Dummy adapter з мінімальним connection state.
    """

    def is_connected(self) -> bool:
        """
        Повернути fake connected state.
        """
        return bool(self)


class DummyCTraderRuntimeService:
    """
    Dummy cTrader runtime service для RuntimeEngine test.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати dummy service.
        """
        self.connect_demo_called = False
        self._dummy_calls: list[str] = []
        self._health = RuntimeBrokerHealth()
        self._health.set_connected()

        from engine.runtime_account_state import RuntimeAccountState

        self._account_state = RuntimeAccountState()

        self._account_state.account_id = "9870599"
        self._account_state.currency = "USD"
        self._account_state.balance = 869.75

    def connect_demo(self) -> DummyAdapter:
        """
        Симуляція DEMO connect.
        """
        self.connect_demo_called = True
        self._health.set_connected()
        return DummyAdapter()

    def connect_live(self) -> DummyAdapter:
        """
        Симуляція LIVE connect.
        """
        self.connect_demo_called = True
        self._health.set_connected()
        return DummyAdapter()

    def disconnect(self) -> None:
        """
        Симуляція disconnect.
        """
        self._dummy_calls.append("disconnect")
        self._health.set_disconnected()

    def reconnect(self) -> DummyAdapter:
        """
        Симуляція reconnect.
        """
        self._dummy_calls.append("reconnect")
        return DummyAdapter()

    def get_account_list(self) -> list[dict]:
        """
        Повернути dummy account list.
        """
        self._dummy_calls.append("get_account_list")
        return []

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Повернути dummy broker health.
        """
        return self._health

    def get_account_state(self):
        """
        Повернути dummy account state.
        """
        return self._account_state

    def get_positions(self) -> list:
        """
        Повернути dummy positions.
        """
        self._dummy_calls.append("get_positions")
        return []

    def place_market_buy(
        self,
        symbol_name: str = "EURUSD",
        lots: float = 0.01,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual BUY",
    ):
        """
        Dummy BUY MARKET.
        """
        self._dummy_calls.append("place_market_buy")
        _ = symbol_name, lots, stop_loss, take_profit, comment
        return None

    def place_market_sell(
        self,
        symbol_name: str = "EURUSD",
        lots: float = 0.01,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual SELL",
    ):
        """
        Dummy SELL MARKET.
        """
        self._dummy_calls.append("place_market_sell")
        _ = symbol_name, lots, stop_loss, take_profit, comment
        return None

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
        Dummy MARKET order.
        """
        self._dummy_calls.append("place_market_order")
        _ = symbol_name, side, lots, stop_loss, take_profit, comment
        return None

    def close_position(
        self,
        position_id: int | str,
        lots: float | None = None,
    ):
        """
        Dummy close position.
        """
        self._dummy_calls.append("close_position")
        _ = position_id, lots
        return None


def main() -> int:
    """
    Запустити перевірку RuntimeEngine + cTrader runtime service.
    """
    engine = RuntimeEngine(db_path=str(get_runtime_database_path("DEMO")))
    service = DummyCTraderRuntimeService()

    engine.startup()

    service_for_test: Any = service
    engine.set_ctrader_runtime_service(service_for_test)

    connected = engine.connect_ctrader_demo()

    time.sleep(2.5)

    scheduler_running_before_shutdown = engine.is_scheduler_running()

    broker_state_before_shutdown = engine.context.broker_connection_state.value

    engine.shutdown()

    scheduler_running_after_shutdown = engine.is_scheduler_running()

    account_state = engine.ctrader_runtime_service.get_account_state()

    print("\n=== CONTEXT AFTER CTRADER DEMO CONNECT AND SHUTDOWN ===")
    pprint(engine.context.to_dict())

    print("\n=== EVENTS ===")

    print("\n=== ENGINE STATE ===")
    print(f"scheduler_running_before_shutdown=" f"{scheduler_running_before_shutdown}")
    print(f"scheduler_running_after_shutdown=" f"{scheduler_running_after_shutdown}")
    print(f"runtime_state_after_shutdown=" f"{engine.get_runtime_state().value}")

    for event in engine.events:
        pprint(event.to_dict())

    checks = [
        connected is True,
        service.connect_demo_called is True,
        engine.context.broker == "CTRADER",
        engine.context.account_mode == "DEMO",
        broker_state_before_shutdown == "CONNECTED",
        any(
            event.event_type.value == "BROKER_SERVICE_SELECTED"
            for event in engine.events
        ),
        any(event.event_type.value == "BROKER_CONNECTING" for event in engine.events),
        any(event.event_type.value == "BROKER_CONNECTED" for event in engine.events),
        account_state.account_id == "9870599",
        account_state.currency == "USD",
        account_state.balance == 869.75,
        scheduler_running_before_shutdown is True,
        scheduler_running_after_shutdown is False,
        engine.get_runtime_state().value == "OFF",
    ]

    if all(checks):
        print("\nRUNTIME_ENGINE_CTRADER_SERVICE_CHECK=OK")
        return 0

    print("\nRUNTIME_ENGINE_CTRADER_SERVICE_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
