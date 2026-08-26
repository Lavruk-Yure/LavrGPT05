# run_ib_sl_tp_broker_dispatch_check.py
"""
Synthetic IB SL/TP broker-dispatch check.

RoadMap88:
- не підключається до TWS;
- placeOrder/cancelOrder замінені mocks;
- перевіряє порядок placeOrder перед cancelOrder;
- перевіряє повну pre-validation;
- перевіряє connection guard;
- перевіряє зупинку після broker exception.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock, call, patch

from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_cancel import OrderCancel

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import (  # noqa: E402
    IB_PROTECTION_ACTION_CANCEL,
    IB_PROTECTION_ACTION_CREATE,
    IB_PROTECTION_ACTION_KEEP,
    IB_PROTECTION_ACTION_MODIFY,
    IBAdapter,
)


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
    Побудувати synthetic EUR.USD Contract.
    """
    contract = Contract()
    contract.conId = 12087792
    contract.symbol = "EUR"
    contract.currency = "USD"
    contract.secType = "CASH"
    contract.exchange = "IDEALPRO"
    contract.localSymbol = "EUR.USD"
    return contract


def _build_order(
    *,
    order_id: int,
    order_type: str,
    transmit: bool = True,
) -> Order:
    """
    Побудувати synthetic protective Order.
    """
    order = Order()
    order.orderId = order_id
    order.account = "DUM513747"
    order.action = "SELL"
    order.orderType = order_type
    order.totalQuantity = 1000.0
    order.parentId = 0
    order.transmit = transmit

    if order_type == "STP":
        order.auxPrice = 1.14000
    else:
        order.lmtPrice = 1.14600

    return order


def _build_place_payload(
    *,
    leg: str,
    action: str,
    order_id: int,
    contract: Contract,
    order: Order,
) -> dict[str, Any]:
    """
    Побудувати placeOrder dispatcher payload.
    """
    return {
        "leg": leg,
        "action": action,
        "order_id": order_id,
        "broker_call_required": True,
        "broker_contract_object": contract,
        "broker_order_object": order,
    }


def _build_cancel_payload(
    *,
    leg: str,
    order_id: int,
) -> dict[str, Any]:
    """
    Побудувати cancelOrder dispatcher payload.
    """
    return {
        "leg": leg,
        "action": IB_PROTECTION_ACTION_CANCEL,
        "order_id": order_id,
        "broker_call_required": True,
        "broker_contract_object": None,
        "broker_order_object": None,
    }


def _build_keep_payload(
    *,
    leg: str,
    order_id: int,
) -> dict[str, Any]:
    """
    Побудувати KEEP dispatcher payload.
    """
    return {
        "leg": leg,
        "action": IB_PROTECTION_ACTION_KEEP,
        "order_id": order_id,
        "broker_call_required": False,
        "broker_contract_object": None,
        "broker_order_object": None,
    }


def main() -> int:
    """
    Перевірити isolated broker dispatcher.
    """
    logger = logging.getLogger(__name__)

    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )

    dispatch = getattr(
        adapter,
        "_dispatch_sl_tp_broker_payloads",
    )

    client = getattr(adapter, "_client")
    position_contract = _build_contract()

    try:
        setattr(adapter, "_connected", True)

        # 1. CREATE + CREATE:
        #    placeOrder викликається у payload order.
        stop_create_order = _build_order(
            order_id=1701,
            order_type="STP",
            transmit=True,
        )
        take_create_order = _build_order(
            order_id=1702,
            order_type="LMT",
            transmit=True,
        )

        create_payloads = [
            _build_place_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=1701,
                contract=position_contract,
                order=stop_create_order,
            ),
            _build_place_payload(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=1702,
                contract=position_contract,
                order=take_create_order,
            ),
        ]

        with (
            patch.object(
                client,
                "placeOrder",
            ) as place_order_mock,
            patch.object(
                client,
                "cancelOrder",
            ) as cancel_order_mock,
        ):
            call_manager = Mock()
            call_manager.attach_mock(
                place_order_mock,
                "placeOrder",
            )
            call_manager.attach_mock(
                cancel_order_mock,
                "cancelOrder",
            )

            create_calls = dispatch(
                broker_payloads=create_payloads,
            )

            print("CREATE + CREATE dispatch")
            print("  calls=" f"{[row['call'] for row in create_calls]}")
            print("  order_ids=" f"{[row['order_id'] for row in create_calls]}")

            _require_equal(
                create_calls,
                [
                    {
                        "call": "placeOrder",
                        "leg": "STOP_LOSS",
                        "action": IB_PROTECTION_ACTION_CREATE,
                        "order_id": 1701,
                    },
                    {
                        "call": "placeOrder",
                        "leg": "TAKE_PROFIT",
                        "action": IB_PROTECTION_ACTION_CREATE,
                        "order_id": 1702,
                    },
                ],
                "CREATE dispatched calls",
            )
            _require_equal(
                call_manager.mock_calls,
                [
                    call.placeOrder(
                        1701,
                        position_contract,
                        stop_create_order,
                    ),
                    call.placeOrder(
                        1702,
                        position_contract,
                        take_create_order,
                    ),
                ],
                "CREATE broker call order",
            )
            _require_equal(
                cancel_order_mock.call_count,
                0,
                "CREATE cancelOrder call count",
            )

        print("  result=OK")
        print()

        # 2. CANCEL payload навмисно розташований першим,
        #    але MODIFY має піти у broker раніше за CANCEL.
        take_modify_order = _build_order(
            order_id=1802,
            order_type="LMT",
        )

        mixed_payloads = [
            _build_cancel_payload(
                leg="STOP_LOSS",
                order_id=1801,
            ),
            _build_place_payload(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_MODIFY,
                order_id=1802,
                contract=position_contract,
                order=take_modify_order,
            ),
        ]

        with (
            patch.object(
                client,
                "placeOrder",
            ) as place_order_mock,
            patch.object(
                client,
                "cancelOrder",
            ) as cancel_order_mock,
        ):
            call_manager = Mock()
            call_manager.attach_mock(
                place_order_mock,
                "placeOrder",
            )
            call_manager.attach_mock(
                cancel_order_mock,
                "cancelOrder",
            )

            mixed_calls = dispatch(
                broker_payloads=mixed_payloads,
            )

            print("MODIFY before CANCEL dispatch")
            print("  calls=" f"{[row['call'] for row in mixed_calls]}")

            _require_equal(
                [row["call"] for row in mixed_calls],
                [
                    "placeOrder",
                    "cancelOrder",
                ],
                "Mixed dispatched call order",
            )
            _require_equal(
                [row["order_id"] for row in mixed_calls],
                [
                    1802,
                    1801,
                ],
                "Mixed dispatched order ids",
            )

            _require_equal(
                call_manager.mock_calls[0],
                call.placeOrder(
                    1802,
                    position_contract,
                    take_modify_order,
                ),
                "MODIFY must be first broker call",
            )

            _require_equal(
                call_manager.mock_calls[1][0],
                "cancelOrder",
                "CANCEL must be second broker call",
            )

            cancel_args = cancel_order_mock.call_args.args

            _require_equal(
                cancel_args[0],
                1801,
                "CANCEL order id",
            )
            _require(
                isinstance(
                    cancel_args[1],
                    OrderCancel,
                ),
                "CANCEL must receive OrderCancel object",
            )

        print("  result=OK")
        print()

        # 3. KEEP не викликає broker API.
        keep_cancel_payloads = [
            _build_keep_payload(
                leg="STOP_LOSS",
                order_id=1901,
            ),
            _build_cancel_payload(
                leg="TAKE_PROFIT",
                order_id=1902,
            ),
        ]

        with (
            patch.object(
                client,
                "placeOrder",
            ) as place_order_mock,
            patch.object(
                client,
                "cancelOrder",
            ) as cancel_order_mock,
        ):
            keep_cancel_calls = dispatch(
                broker_payloads=keep_cancel_payloads,
            )

            print("KEEP + CANCEL dispatch")
            print("  calls=" f"{[row['call'] for row in keep_cancel_calls]}")

            _require_equal(
                keep_cancel_calls,
                [
                    {
                        "call": "cancelOrder",
                        "leg": "TAKE_PROFIT",
                        "action": IB_PROTECTION_ACTION_CANCEL,
                        "order_id": 1902,
                    }
                ],
                "KEEP + CANCEL dispatched calls",
            )
            _require_equal(
                place_order_mock.call_count,
                0,
                "KEEP must not call placeOrder",
            )
            _require_equal(
                cancel_order_mock.call_count,
                1,
                "KEEP + CANCEL cancelOrder count",
            )

        print("  result=OK")
        print()

        # 4. Помилка в другому payload:
        #    перший payload також не повинен бути відправлений.
        valid_first_order = _build_order(
            order_id=2001,
            order_type="STP",
        )

        invalid_second_order = _build_order(
            order_id=2002,
            order_type="LMT",
        )

        invalid_payloads = [
            _build_place_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2001,
                contract=position_contract,
                order=valid_first_order,
            ),
            _build_place_payload(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2002,
                contract=position_contract,
                order=invalid_second_order,
            ),
        ]

        invalid_payloads[1]["broker_contract_object"] = None

        with (
            patch.object(
                client,
                "placeOrder",
            ) as place_order_mock,
            patch.object(
                client,
                "cancelOrder",
            ) as cancel_order_mock,
        ):
            try:
                dispatch(
                    broker_payloads=invalid_payloads,
                )
            except RuntimeError as exc:
                error_text = str(exc)
            else:
                raise AssertionError("Invalid second payload must raise RuntimeError")

            print("Full pre-validation")
            print(f"  error={error_text}")

            _require(
                "placeOrder Contract is missing" in error_text,
                "Unexpected pre-validation error",
            )
            _require_equal(
                place_order_mock.call_count,
                0,
                "Pre-validation placeOrder call count",
            )
            _require_equal(
                cancel_order_mock.call_count,
                0,
                "Pre-validation cancelOrder call count",
            )

        print("  result=OK")
        print()

        # 5. Disconnected adapter:
        #    broker API не викликається.
        setattr(adapter, "_connected", False)

        with (
            patch.object(
                client,
                "placeOrder",
            ) as place_order_mock,
            patch.object(
                client,
                "cancelOrder",
            ) as cancel_order_mock,
        ):
            try:
                dispatch(
                    broker_payloads=create_payloads,
                )
            except RuntimeError as exc:
                error_text = str(exc)
            else:
                raise AssertionError("Disconnected dispatch must raise RuntimeError")

            print("Disconnected dispatch")
            print(f"  error={error_text}")

            _require_equal(
                error_text,
                "IB adapter is not connected",
                "Disconnected error",
            )
            _require_equal(
                place_order_mock.call_count,
                0,
                "Disconnected placeOrder call count",
            )
            _require_equal(
                cancel_order_mock.call_count,
                0,
                "Disconnected cancelOrder call count",
            )

        print("  result=OK")
        print()

        # 6. Broker exception у placeOrder:
        #    наступний cancelOrder не виконується.
        setattr(adapter, "_connected", True)

        failure_payloads = [
            _build_cancel_payload(
                leg="STOP_LOSS",
                order_id=2101,
            ),
            _build_place_payload(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_MODIFY,
                order_id=2102,
                contract=position_contract,
                order=_build_order(
                    order_id=2102,
                    order_type="LMT",
                ),
            ),
        ]

        with (
            patch.object(
                client,
                "placeOrder",
                side_effect=RuntimeError("Synthetic placeOrder failure"),
            ) as place_order_mock,
            patch.object(
                client,
                "cancelOrder",
            ) as cancel_order_mock,
        ):
            try:
                dispatch(
                    broker_payloads=failure_payloads,
                )
            except RuntimeError as exc:
                error_text = str(exc)
            else:
                raise AssertionError("Broker placeOrder failure must propagate")

            print("Broker exception stops dispatch")
            print(f"  error={error_text}")

            _require_equal(
                error_text,
                "Synthetic placeOrder failure",
                "Broker exception text",
            )
            _require_equal(
                place_order_mock.call_count,
                1,
                "Failed placeOrder call count",
            )
            _require_equal(
                cancel_order_mock.call_count,
                0,
                "cancelOrder after failed placeOrder",
            )

        print("  result=OK")
        print()

    except AssertionError as exc:
        print("IB_SL_TP_BROKER_DISPATCH_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_BROKER_DISPATCH_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
