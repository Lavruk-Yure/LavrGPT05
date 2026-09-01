# run_runtime_engine_ib_virtual_leg_evidence_check.py
"""
Synthetic RuntimeEngine -> IBRuntimeService -> IBSessionManager evidence check.

RoadMap90:
- не підключається до TWS;
- не змінює SQLite;
- не виконує orders;
- перевіряє canonical read-only evidence chain без спотворення snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402
from engine.ib_session_manager import IBSessionManager  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ib_runtime_service import IBRuntimeService  # noqa: E402


class DummyIBAdapter:
    """
    Dummy IB adapter для read-only evidence integration check.
    """

    def __init__(self) -> None:
        """
        Ініціалізувати dummy adapter.
        """
        self.connected = True
        self.evidence_calls = 0
        self.snapshot = {
            "broker": "IB",
            "captured_utc": "2026-07-16T13:00:00+00:00",
            "current_client_id": 1,
            "complete": True,
            "positions_complete": True,
            "open_orders_complete": True,
            "completed_orders_complete": True,
            "executions_complete": True,
            "completed_orders_api_only": False,
            "account_ids": ["DUM513747"],
            "positions": [
                {
                    "broker_position_id": "IB:DUM513747:EURUSD",
                    "signed_quantity": 3000.0,
                }
            ],
            "open_orders": [
                {
                    "order_id": 112,
                    "parent_id": 111,
                    "oca_group": "LGE_OCA_111",
                }
            ],
            "completed_orders": [
                {
                    "order_id": 119,
                    "parent_id": 117,
                    "completed_status": "Filled",
                }
            ],
            "executions": [
                {
                    "order_id": 111,
                    "side": "BOT",
                    "shares": 1000.0,
                    "price": 1.14885,
                }
            ],
        }

    def is_connected(self) -> bool:
        """
        Повернути fake connection state.
        """
        return self.connected

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Повернути synthetic evidence snapshot.
        """
        self.evidence_calls += 1
        return self.snapshot

    def disconnect(self) -> None:
        """
        Відключити dummy adapter.
        """
        self.connected = False


class TrackingIBSessionManager(IBSessionManager):
    """
    Actual session manager із synthetic active adapter.
    """

    def __init__(self, adapter: DummyIBAdapter) -> None:
        """
        Ініціалізувати manager без broker connection.
        """
        super().__init__()

        self.evidence_calls = 0
        self._active_adapter = cast(
            IBAdapter,
            cast(object, adapter),
        )
        self._active_account_mode = "DEMO"

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        """
        Зафіксувати виклик і виконати actual manager passthrough.
        """
        self.evidence_calls += 1
        return super().get_virtual_position_leg_evidence_snapshot()


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
    Запустити synthetic canonical evidence-chain check.
    """
    engine = RuntimeEngine(db_path=":memory:")
    adapter = DummyIBAdapter()
    session_manager = TrackingIBSessionManager(adapter)
    service = IBRuntimeService(session_manager=session_manager)

    try:
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")

        result = engine.get_ib_virtual_position_leg_evidence_snapshot()

        print("RuntimeEngine IB virtual-leg evidence result")
        print(f"  complete={result['complete']}")
        print(f"  positions={len(result['positions'])}")
        print(f"  open_orders={len(result['open_orders'])}")
        print(f"  completed_orders={len(result['completed_orders'])}")
        print(f"  executions={len(result['executions'])}")
        print(f"  session_manager_calls={session_manager.evidence_calls}")
        print(f"  adapter_calls={adapter.evidence_calls}")

        _require_equal(result, adapter.snapshot, "Evidence snapshot")
        _require_equal(session_manager.evidence_calls, 1, "Manager calls")
        _require_equal(adapter.evidence_calls, 1, "Adapter calls")

        print("RUNTIME_ENGINE_IB_VIRTUAL_LEG_EVIDENCE_CHECK=OK")
        return 0
    finally:
        service.disconnect()
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
