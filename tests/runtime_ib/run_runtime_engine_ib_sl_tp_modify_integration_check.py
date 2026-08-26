# run_runtime_engine_ib_sl_tp_modify_integration_check.py
"""
Synthetic RuntimeEngine -> IBRuntimeService -> IBSessionManager check.

RoadMap89:
- не підключається до TWS;
- не викликає real IBAdapter execution;
- перевіряє canonical IB SL/TP modify chain;
- перевіряє передачу position_id, SL і TP без спотворення.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ib_adapter import IBAdapter  # noqa: E402
from engine.ib_session_manager import IBSessionManager  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ib_runtime_service import IBRuntimeService  # noqa: E402


class DummyIBAdapter:
    """
    Dummy IB adapter для synthetic integration test.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати dummy adapter.
        """
        self.connected = True
        self.get_positions_calls = 0
        self.modify_calls = 0
        self.last_modify_kwargs: dict[str, Any] = {}

        self.position = BrokerPosition(
            broker="IB",
            account_id="DUM513747",
            account_mode="DEMO",
            position_id="IB:DUM513747:EURUSD",
            symbol_name="EURUSD",
            side="BUY",
            volume=1000.0,
            entry_price=1.14000,
            stop_loss=1.13000,
            take_profit=None,
        )

    def is_connected(self) -> bool:
        """
        Повернути fake connection state.
        """
        return self.connected

    def get_positions(self) -> list[BrokerPosition]:
        """
        Повернути synthetic IB position snapshot.
        """
        self.get_positions_calls += 1
        return [self.position]

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Зафіксувати synthetic SL/TP modify call.
        """
        self.modify_calls += 1
        self.last_modify_kwargs = {
            "position_id": position_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }

        return {
            "adapter": "DummyIBAdapter",
            "executed": True,
            "confirmed": True,
            "position_id": position_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }

    def disconnect(self) -> None:
        """
        Відключити dummy adapter.
        """
        self.connected = False


class TrackingIBSessionManager(IBSessionManager):
    """
    Actual IBSessionManager із synthetic active adapter.
    """

    def __init__(self, adapter: DummyIBAdapter) -> None:
        """
        Ініціалізувати manager без broker connection.
        """
        super().__init__()

        self.modify_calls = 0
        self._active_adapter = cast(
            IBAdapter,
            cast(object, adapter),
        )
        self._active_account_mode = "DEMO"

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Зафіксувати виклик і виконати actual manager passthrough.
        """
        self.modify_calls += 1

        return super().modify_position_sl_tp(
            position_id=position_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


def _require_equal(
    actual: Any,
    expected: Any,
    message: str,
) -> None:
    """
    Перевірити точну рівність.
    """
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r}, actual={actual!r}")


def main() -> int:
    """
    Запустити synthetic canonical-chain test.
    """
    engine = RuntimeEngine(db_path=":memory:")
    adapter = DummyIBAdapter()
    session_manager = TrackingIBSessionManager(adapter)
    service = IBRuntimeService(session_manager=session_manager)

    try:
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")

        result = engine.modify_active_broker_position_sl_tp(
            broker_position_id="IB:DUM513747:EURUSD",
            stop_loss=1.13500,
            take_profit=1.15500,
        )

        print("RuntimeEngine IB SL/TP modify integration result")
        print(f"  broker={result['broker']}")
        print(f"  broker_position_id={result['broker_position_id']}")
        print(f"  side={result['side']}")
        print(f"  stop_loss={result['stop_loss']}")
        print(f"  take_profit={result['take_profit']}")
        print(f"  session_manager_calls={session_manager.modify_calls}")
        print(f"  adapter_calls={adapter.modify_calls}")

        _require_equal(result["broker"], "IB", "Broker")
        _require_equal(
            result["broker_position_id"],
            "IB:DUM513747:EURUSD",
            "Broker position id",
        )
        _require_equal(result["side"], "BUY", "Position side")
        _require_equal(result["stop_loss"], 1.13500, "Stop Loss")
        _require_equal(result["take_profit"], 1.15500, "Take Profit")
        _require_equal(adapter.get_positions_calls, 1, "Positions calls")
        _require_equal(session_manager.modify_calls, 1, "Manager calls")
        _require_equal(adapter.modify_calls, 1, "Adapter calls")
        _require_equal(
            adapter.last_modify_kwargs,
            {
                "position_id": "IB:DUM513747:EURUSD",
                "stop_loss": 1.13500,
                "take_profit": 1.15500,
            },
            "Adapter modify arguments",
        )
        _require_equal(
            result["broker_result"],
            {
                "adapter": "DummyIBAdapter",
                "executed": True,
                "confirmed": True,
                "position_id": "IB:DUM513747:EURUSD",
                "stop_loss": 1.13500,
                "take_profit": 1.15500,
            },
            "Broker result",
        )

        print("RUNTIME_ENGINE_IB_SL_TP_MODIFY_INTEGRATION_CHECK=OK")
        return 0
    finally:
        service.disconnect()
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
