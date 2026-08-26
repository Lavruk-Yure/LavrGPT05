# run_ib_sl_tp_operation_state_check.py
"""
Synthetic IB SL/TP operation-state check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє start/callback/snapshot/clear lifecycle;
- перевіряє ізоляцію SL/TP callbacks від сторонніх order ids.
"""

from __future__ import annotations

import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_state import OrderState

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import ib_adapter as ib_adapter_module  # noqa: E402


def _require(
    condition: bool,
    message: str,
) -> None:
    """
    Перервати test зі зрозумілою причиною.
    """
    if not condition:
        raise AssertionError(message)


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


def _build_contract() -> Contract:
    """
    Побудувати synthetic EUR.USD contract.
    """
    contract = Contract()
    contract.conId = 12087792
    contract.symbol = "EUR"
    contract.currency = "USD"
    contract.secType = "CASH"
    contract.exchange = "IDEALPRO"
    contract.localSymbol = "EUR.USD"
    return contract


def _build_stop_order(
    order_id: int,
) -> Order:
    """
    Побудувати synthetic Stop Loss order.
    """
    order = Order()
    order.orderId = order_id
    order.account = "DUM513747"
    order.action = "SELL"
    order.orderType = "STP"
    order.totalQuantity = Decimal("1000")
    order.auxPrice = 1.14000
    order.lmtPrice = 0.0
    order.parentId = 0
    order.clientId = 2
    order.permId = 5001
    order.orderRef = "LGE_SL_TP_MODIFY"
    order.tif = "GTC"
    order.transmit = True
    order.ocaGroup = "LGE_TEST_OCA"
    return order


def main() -> int:
    """
    Перевірити lifecycle окремого SL/TP operation state.
    """
    logger = logging.getLogger(__name__)

    wrapper_class = getattr(
        ib_adapter_module,
        "_IBWrapper",
    )

    wrapper = wrapper_class(logger)

    contract = _build_contract()
    stop_order = _build_stop_order(order_id=101)

    submitted_state = OrderState()
    submitted_state.status = "Submitted"

    ignored_order = _build_stop_order(order_id=999)

    try:
        wrapper.start_sl_tp_operation(
            {
                101,
                102,
                103,
            }
        )

        initial_snapshot = wrapper.get_sl_tp_operation_snapshot()

        _require_equal(
            initial_snapshot["order_ids"],
            {101, 102, 103},
            "Initial order ids",
        )
        _require_equal(
            initial_snapshot["open_orders"],
            {},
            "Initial open orders",
        )
        _require_equal(
            initial_snapshot["statuses"],
            {},
            "Initial statuses",
        )
        _require_equal(
            initial_snapshot["cancelled_order_ids"],
            set(),
            "Initial cancelled order ids",
        )
        _require_equal(
            initial_snapshot["errors"],
            {},
            "Initial errors",
        )
        _require(
            not wrapper.sl_tp_operation_event.is_set(),
            "Operation event must be clear after start",
        )

        wrapper.openOrder(
            999,
            contract,
            ignored_order,
            submitted_state,
        )

        ignored_snapshot = wrapper.get_sl_tp_operation_snapshot()

        _require_equal(
            ignored_snapshot["open_orders"],
            {},
            "Unrelated openOrder callback must be ignored",
        )

        wrapper.openOrder(
            101,
            contract,
            stop_order,
            submitted_state,
        )

        wrapper.orderStatus(
            order_id=102,
            status="Submitted",
            filled=0.0,
            remaining=1000.0,
            avg_fill_price=0.0,
            perm_id=5002,
            parent_id=0,
            last_fill_price=0.0,
            client_id=2,
            why_held="",
            mkt_cap_price=0.0,
        )

        wrapper.orderStatus(
            order_id=103,
            status="ApiCancelled",
            filled=0.0,
            remaining=1000.0,
            avg_fill_price=0.0,
            perm_id=5003,
            parent_id=0,
            last_fill_price=0.0,
            client_id=2,
            why_held="",
            mkt_cap_price=0.0,
        )

        wrapper.error(
            req_id=101,
            error_time=0,
            error_code=201,
            error_string="Synthetic rejected order",
            advanced_order_reject_json="",
        )

        wrapper.error(
            req_id=102,
            error_time=0,
            error_code=202,
            error_string="Synthetic order cancelled",
            advanced_order_reject_json="",
        )

        callback_snapshot = wrapper.get_sl_tp_operation_snapshot()

        print("IB SL/TP operation callback snapshot")
        print("  order_ids=" f"{sorted(callback_snapshot['order_ids'])}")
        print("  open_order_ids=" f"{sorted(callback_snapshot['open_orders'])}")
        print("  status_order_ids=" f"{sorted(callback_snapshot['statuses'])}")
        print(
            "  cancelled_order_ids="
            f"{sorted(callback_snapshot['cancelled_order_ids'])}"
        )
        print("  error_order_ids=" f"{sorted(callback_snapshot['errors'])}")

        _require(
            wrapper.sl_tp_operation_event.is_set(),
            "Operation event must be set after matching callbacks",
        )
        _require(
            101 in callback_snapshot["open_orders"],
            "Matching openOrder callback was not captured",
        )
        _require(
            102 in callback_snapshot["statuses"],
            "Matching orderStatus callback was not captured",
        )
        _require_equal(
            callback_snapshot["statuses"][102]["status"],
            "Submitted",
            "Captured order status",
        )
        _require_equal(
            callback_snapshot["statuses"][103]["status"],
            "ApiCancelled",
            "Captured cancelled order status",
        )
        _require_equal(
            callback_snapshot["cancelled_order_ids"],
            {102, 103},
            "Cancelled order confirmations",
        )
        _require(
            101 in callback_snapshot["errors"],
            "Matching error callback was not captured",
        )
        _require(
            102 not in callback_snapshot["errors"],
            "Cancellation code 202 must not be stored as an error",
        )
        _require(
            103 not in callback_snapshot["errors"],
            "ApiCancelled status must not create an error",
        )
        _require_equal(
            callback_snapshot["errors"][101],
            ["IB SL/TP order error 201: " "Synthetic rejected order"],
            "Captured operation error",
        )
        _require(
            999 not in callback_snapshot["open_orders"],
            "Unrelated order callback leaked into operation state",
        )

        callback_snapshot["order_ids"].clear()
        callback_snapshot["open_orders"].clear()
        callback_snapshot["statuses"].clear()
        callback_snapshot["cancelled_order_ids"].clear()
        callback_snapshot["errors"].clear()

        independent_snapshot = wrapper.get_sl_tp_operation_snapshot()

        _require_equal(
            independent_snapshot["order_ids"],
            {101, 102, 103},
            "Snapshot order ids must be independent",
        )
        _require(
            101 in independent_snapshot["open_orders"],
            "Open-order snapshot copy is not independent",
        )
        _require_equal(
            independent_snapshot["cancelled_order_ids"],
            {102, 103},
            "Cancelled snapshot copy is not independent",
        )
        _require(
            102 in independent_snapshot["statuses"],
            "Status snapshot copy is not independent",
        )
        _require(
            101 in independent_snapshot["errors"],
            "Error snapshot copy is not independent",
        )

        wrapper.clear_sl_tp_operation()

        cleared_snapshot = wrapper.get_sl_tp_operation_snapshot()

        _require_equal(
            cleared_snapshot["order_ids"],
            set(),
            "Cleared order ids",
        )
        _require_equal(
            cleared_snapshot["open_orders"],
            {},
            "Cleared open orders",
        )
        _require_equal(
            cleared_snapshot["statuses"],
            {},
            "Cleared statuses",
        )
        _require_equal(
            cleared_snapshot["cancelled_order_ids"],
            set(),
            "Cleared cancelled order ids",
        )
        _require_equal(
            cleared_snapshot["errors"],
            {},
            "Cleared errors",
        )
        _require(
            not wrapper.sl_tp_operation_event.is_set(),
            "Operation event must be clear after cleanup",
        )

    except AssertionError as exc:
        print("IB_SL_TP_OPERATION_STATE_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_OPERATION_STATE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
