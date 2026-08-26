# run_ib_virtual_leg_completed_order_evidence_check.py
"""
Synthetic IB completed-order evidence check.

RoadMap90:
- не підключається до TWS;
- не змінює SQLite;
- перевіряє обидва callback layouts completedOrder;
- перевіряє same-client ownership candidate і order identity fields.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402


class DummyContract:
    """
    Мінімальний synthetic IB contract.
    """

    symbol = "GBP"
    secType = "CASH"
    currency = "USD"
    exchange = "IDEALPRO"
    conId = 12087792


class DummyOrder:
    """
    Мінімальний synthetic completed order.
    """

    def __init__(
        self,
        order_id: int,
        parent_id: int,
        action: str,
        order_type: str,
        quantity: float,
        client_id: int,
    ) -> None:
        self.orderId = order_id
        self.account = "DUM513747"
        self.action = action
        self.orderType = order_type
        self.totalQuantity = quantity
        self.lmtPrice = 1.349
        self.auxPrice = 1.349
        self.parentId = parent_id
        self.clientId = client_id
        self.permId = order_id + 100000
        self.orderRef = ""
        self.tif = "GTC"
        self.ocaGroup = f"LGE_SLTP_{parent_id}"
        self.ocaType = 1


class DummyOrderState:
    """
    Мінімальний synthetic completed order state.
    """

    status = "Filled"
    completedStatus = "Filled"
    completedTime = "20260716 17:57:00 Europe/Kiev"
    filled = 3000.0
    remaining = 0.0
    avgFillPrice = 1.349
    lastFillPrice = 1.349
    whyHeld = ""


class SyntheticIBAdapter(IBAdapter):
    """
    Test-only adapter facade without direct protected-member access in main().
    """

    @property
    def test_wrapper(self) -> Any:
        """Return the synthetic callback wrapper."""
        return self._wrapper

    def install_test_client(self, client: Any) -> None:
        """Install  synchronous synthetic transport."""
        self._client = client
        self._connected = True

    def request_completed_orders_snapshot_for_test(
        self,
        *,
        api_only: bool,
    ) -> list[dict[str, Any]]:
        """Request completed orders through the production implementation."""
        return self._request_completed_orders_snapshot(
            api_only=api_only,
            require_complete=True,
        )

    def enrich_completed_order_row_for_test(
        self,
        row: dict[str, Any],
    ) -> None:
        """Apply production symbol and broker-position normalization."""
        row["symbol_name"] = self._build_symbol_name_from_order_row(row)
        row["broker_position_id"] = self._build_position_id_from_open_order(row)


class DummyCompletedOrdersClient:
    """
    Synthetic client, який синхронно віддає completed orders.
    """

    def __init__(self, wrapper) -> None:
        self.wrapper = wrapper
        self.calls = 0
        self.api_only: bool | None = None

    # noinspection PyPep8Naming
    def reqCompletedOrders(self, api_only: bool) -> None:  # noqa: N802
        """
        Віддати callbacks для двох підтримуваних layouts.
        """
        self.calls += 1
        self.api_only = api_only

        contract = DummyContract()
        state = DummyOrderState()

        stop_order = DummyOrder(
            order_id=119,
            parent_id=117,
            action="SELL",
            order_type="STP",
            quantity=3000.0,
            client_id=1,
        )
        take_profit_order = DummyOrder(
            order_id=121,
            parent_id=120,
            action="BUY",
            order_type="LMT",
            quantity=2000.0,
            client_id=2,
        )

        self.wrapper.completedOrder(
            contract,
            stop_order,
            state,
        )
        self.wrapper.completedOrder(
            121,
            contract,
            take_profit_order,
            state,
        )
        self.wrapper.completedOrdersEnd()


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
    Запустити synthetic completed-order evidence check.
    """
    adapter = SyntheticIBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=1,
        logger=logging.getLogger(__name__),
    )
    client = DummyCompletedOrdersClient(adapter.test_wrapper)
    adapter.install_test_client(client)

    result = adapter.request_completed_orders_snapshot_for_test(
        api_only=False,
    )

    for row in result:
        adapter.enrich_completed_order_row_for_test(row)

    first = result[0]
    second = result[1]

    print("IB virtual-leg completed-order evidence result")
    print(f"  complete_rows={len(result)}")
    print(f"  request_api_only={client.api_only}")
    print(f"  first_order_id={first['order_id']}")
    print(f"  first_parent_id={first['parent_id']}")
    print(f"  first_same_client_id={first['same_client_id']}")
    print(f"  second_order_id={second['order_id']}")
    print(f"  second_same_client_id={second['same_client_id']}")
    print(f"  broker_position_id={first['broker_position_id']}")

    _require_equal(client.calls, 1, "Completed-order request calls")
    _require_equal(client.api_only, False, "Completed-order API-only mode")
    _require_equal(len(result), 2, "Completed-order rows")
    _require_equal(first["order_id"], 119, "Three-argument callback order ID")
    _require_equal(first["parent_id"], 117, "First parent order ID")
    _require_equal(first["same_client_id"], True, "First ownership candidate")
    _require_equal(second["order_id"], 121, "Four-argument callback order ID")
    _require_equal(second["parent_id"], 120, "Second parent order ID")
    _require_equal(
        second["same_client_id"],
        False,
        "Different-client ownership candidate",
    )
    _require_equal(first["completed_status"], "Filled", "Completed status")
    _require_equal(first["symbol_name"], "GBPUSD", "Symbol name")
    _require_equal(
        first["broker_position_id"],
        "IB:DUM513747:GBPUSD",
        "Broker position ID",
    )

    print("IB_VIRTUAL_LEG_COMPLETED_ORDER_EVIDENCE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
