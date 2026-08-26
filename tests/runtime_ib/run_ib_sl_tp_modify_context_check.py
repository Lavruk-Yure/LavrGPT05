# run_ib_sl_tp_modify_context_check.py
"""
Synthetic IB SL/TP modify production-context check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє повний adapter plan-only path;
- перевіряє broker Contract/Order object identity.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.order import Order

from engine.runtime_constants import (  # noqa: E402
    IB_SL_TP_OCA_GROUP_PREFIX,
    IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import (  # noqa: E402
    IB_PROTECTION_ACTION_CREATE,
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


def main() -> int:
    """
    Перевірити adapter production context без broker execution.
    """
    logger = logging.getLogger(__name__)

    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )

    adapter._connected = True

    position_contract = Contract()
    position_contract.conId = 12087792
    position_contract.symbol = "EUR"
    position_contract.currency = "USD"
    position_contract.secType = "CASH"
    position_contract.exchange = "IDEALPRO"

    stop_contract = Contract()
    stop_contract.conId = 12087792
    stop_contract.symbol = "EUR"
    stop_contract.currency = "USD"
    stop_contract.secType = "CASH"
    stop_contract.exchange = "IDEALPRO"

    stop_order_object = Order()
    stop_order_object.orderId = 101
    stop_order_object.account = "DUM513747"
    stop_order_object.action = "SELL"
    stop_order_object.orderType = "STP"
    stop_order_object.totalQuantity = 1000.0
    stop_order_object.auxPrice = 1.13000
    stop_order_object.lmtPrice = 0.0
    stop_order_object.parentId = 0
    stop_order_object.tif = "GTC"
    stop_order_object.transmit = True
    stop_order_object.orderRef = "EXISTING_STOP"
    stop_order_object.ocaGroup = ""
    stop_order_object.ocaType = 0

    position_rows = [
        {
            "account": "DUM513747",
            "contract": position_contract,
            "position": 1000.0,
            "avg_cost": 1.14000,
        }
    ]

    open_orders = [
        {
            "order_id": 101,
            "client_id": 2,
            "perm_id": 5001,
            "account": "DUM513747",
            "symbol": "EUR",
            "currency": "USD",
            "sec_type": "CASH",
            "order_type": "STP",
            "action": "SELL",
            "total_quantity": 1000.0,
            "lmt_price": 0.0,
            "aux_price": 1.13000,
            "same_client_id": True,
            "contract_object": stop_contract,
            "order_object": stop_order_object,
        }
    ]
    operation_result = {
        "operation_order_ids": {
            101,
            102,
        },
        "dispatched_calls": [
            {
                "call": "placeOrder",
                "leg": "STOP_LOSS",
                "action": IB_PROTECTION_ACTION_MODIFY,
                "order_id": 101,
            },
            {
                "call": "placeOrder",
                "leg": "TAKE_PROFIT",
                "action": IB_PROTECTION_ACTION_CREATE,
                "order_id": 102,
            },
        ],
        "action_results": [
            {
                "leg": "STOP_LOSS",
                "action": IB_PROTECTION_ACTION_MODIFY,
                "order_id": 101,
                "confirmed": True,
                "terminal": True,
                "status": "Submitted",
                "timeout": False,
                "errors": [],
            },
            {
                "leg": "TAKE_PROFIT",
                "action": IB_PROTECTION_ACTION_CREATE,
                "order_id": 102,
                "confirmed": True,
                "terminal": True,
                "status": "PreSubmitted",
                "timeout": False,
                "errors": [],
            },
        ],
        "operation_snapshot": {
            "order_ids": {
                101,
                102,
            },
            "open_orders": {},
            "statuses": {},
            "cancelled_order_ids": set(),
            "errors": {},
        },
        "executed": True,
        "confirmed": True,
        "terminal": True,
        "timeout": False,
        "failed_legs": [],
    }

    try:
        with (
            patch.object(
                adapter,
                "_request_positions_snapshot_for_execution",
                return_value=position_rows,
            ) as positions_snapshot_mock,
            patch.object(
                adapter,
                "_request_open_orders_snapshot",
                return_value=open_orders,
            ) as open_orders_snapshot_mock,
            patch.object(
                adapter,
                "_get_next_order_id",
                return_value=102,
            ) as next_order_id_mock,
            patch.object(
                adapter,
                "_execute_sl_tp_broker_operation",
                return_value=operation_result,
            ) as execute_operation_mock,
            patch.object(
                EClient,
                "placeOrder",
            ) as place_order_mock,
            patch.object(
                EClient,
                "cancelOrder",
            ) as cancel_order_mock,
            patch.object(
                EClient,
                "placeOrder",
                side_effect=AssertionError("Real placeOrder must not be called"),
            ) as place_order_mock,
            patch.object(
                EClient,
                "cancelOrder",
                side_effect=AssertionError("Real cancelOrder must not be called"),
            ) as cancel_order_mock,
        ):
            result = adapter.modify_position_sl_tp(
                position_id="IB:DUM513747:EURUSD",
                stop_loss=1.13500,
                take_profit=1.15500,
            )
        execute_kwargs = execute_operation_mock.call_args.kwargs

        execution_actions = {
            str(row["leg"]): row for row in execute_kwargs["execution_actions"]
        }

        broker_payloads = {
            str(row["leg"]): row for row in execute_kwargs["broker_payloads"]
        }

        stop_payload_order = broker_payloads["STOP_LOSS"]["broker_order_object"]

        take_payload_order = broker_payloads["TAKE_PROFIT"]["broker_order_object"]

        expected_oca_group = f"{IB_SL_TP_OCA_GROUP_PREFIX}_2_101_102"
        print("IB SL/TP modify context result")
        print(f"  broker_position_id={result['broker_position_id']}")
        print(f"  position_side={result['position_side']}")
        print(f"  position_volume={result['position_volume']}")
        print(f"  protective_action={result['protective_action']}")
        print(f"  stop_loss_action={result['stop_loss_action']}")
        print(f"  take_profit_action={result['take_profit_action']}")
        print(f"  requires_oca_group={result['requires_oca_group']}")
        print(f"  blocked={result['blocked']}")
        print(f"  blocked_flags={result['blocked_flags']}")
        print(f"  plan_only={result['plan_only']}")

        _require_equal(
            result["broker_position_id"],
            "IB:DUM513747:EURUSD",
            "Broker position id",
        )
        _require_equal(
            result["account_id"],
            "DUM513747",
            "Account id",
        )
        _require_equal(
            result["symbol_name"],
            "EURUSD",
            "Symbol name",
        )
        _require_equal(
            result["position_side"],
            "BUY",
            "Position side",
        )
        _require_equal(
            result["position_volume"],
            1000.0,
            "Position volume",
        )
        _require_equal(
            result["protective_action"],
            "SELL",
            "Protective action",
        )
        _require_equal(
            result["stop_loss_action"],
            IB_PROTECTION_ACTION_MODIFY,
            "Stop Loss action",
        )
        _require_equal(
            result["take_profit_action"],
            IB_PROTECTION_ACTION_CREATE,
            "Take Profit action",
        )
        _require_equal(
            result["requires_oca_group"],
            True,
            "OCA group requirement",
        )
        _require_equal(
            result["blocked"],
            False,
            "Plan blocked state",
        )
        _require_equal(
            result["plan_only"],
            False,
            "Plan-only state",
        )
        _require_equal(
            result["executed"],
            True,
            "Execution state",
        )
        _require_equal(
            result["confirmed"],
            True,
            "Confirmation state",
        )
        _require_equal(
            result["terminal"],
            True,
            "Terminal state",
        )
        _require_equal(
            result["timeout"],
            False,
            "Timeout state",
        )
        _require_equal(
            result["failed_legs"],
            [],
            "Failed legs",
        )
        _require_equal(
            result["no_operation"],
            False,
            "No-operation state",
        )
        _require_equal(
            result["create_order_ids"],
            {
                "take_profit": 102,
            },
            "CREATE order ids",
        )
        _require_equal(
            result["oca_group"],
            expected_oca_group,
            "OCA group",
        )
        _require_equal(
            result["operation_order_ids"],
            {
                101,
                102,
            },
            "Operation order ids",
        )

        _require(
            result["position_contract_object"] is position_contract,
            "Position Contract object identity mismatch",
        )
        _require(
            result["stop_loss_contract_object"] is stop_contract,
            "Stop Loss Contract object identity mismatch",
        )
        _require(
            result["stop_loss_order_object"] is stop_order_object,
            "Stop Loss Order object identity mismatch",
        )

        _require_equal(
            execution_actions["STOP_LOSS"]["action"],
            IB_PROTECTION_ACTION_MODIFY,
            "Stop Loss execution action",
        )
        _require_equal(
            execution_actions["STOP_LOSS"]["order_id"],
            101,
            "Stop Loss execution order id",
        )
        _require_equal(
            execution_actions["TAKE_PROFIT"]["action"],
            IB_PROTECTION_ACTION_CREATE,
            "Take Profit execution action",
        )
        _require_equal(
            execution_actions["TAKE_PROFIT"]["order_id"],
            102,
            "Take Profit execution order id",
        )

        _require(
            broker_payloads["STOP_LOSS"]["broker_contract_object"] is stop_contract,
            "Stop Loss payload Contract mismatch",
        )
        _require(
            stop_payload_order is not stop_order_object,
            "Stop Loss payload must use deepcopy",
        )
        _require_equal(
            stop_order_object.auxPrice,
            1.13000,
            "Original Stop Loss price changed",
        )
        _require_equal(
            stop_payload_order.auxPrice,
            1.13500,
            "Stop Loss payload price",
        )
        _require_equal(
            stop_payload_order.ocaGroup,
            expected_oca_group,
            "Stop Loss payload OCA group",
        )
        _require_equal(
            stop_payload_order.ocaType,
            IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
            "Stop Loss payload OCA type",
        )
        _require_equal(
            stop_payload_order.transmit,
            False,
            "Stop Loss payload transmit",
        )

        _require(
            broker_payloads["TAKE_PROFIT"]["broker_contract_object"]
            is position_contract,
            "Take Profit payload Contract mismatch",
        )
        _require_equal(
            take_payload_order.orderId,
            102,
            "Take Profit payload order id",
        )
        _require_equal(
            take_payload_order.orderType,
            "LMT",
            "Take Profit payload order type",
        )
        _require_equal(
            take_payload_order.lmtPrice,
            1.15500,
            "Take Profit payload price",
        )
        _require_equal(
            take_payload_order.ocaGroup,
            expected_oca_group,
            "Take Profit payload OCA group",
        )
        _require_equal(
            take_payload_order.ocaType,
            IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
            "Take Profit payload OCA type",
        )
        _require_equal(
            take_payload_order.transmit,
            True,
            "Take Profit payload transmit",
        )

        positions_snapshot_mock.assert_called_once_with()

        open_orders_snapshot_mock.assert_called_once_with(
            include_objects=True,
            require_complete=True,
        )
        next_order_id_mock.assert_called_once_with()

        execute_operation_mock.assert_called_once()

        _require_equal(
            execute_kwargs["operation_order_ids"],
            {
                101,
                102,
            },
            "Execution handoff order ids",
        )

        place_order_mock.assert_not_called()
        cancel_order_mock.assert_not_called()

    except AssertionError as exc:
        print("IB_SL_TP_MODIFY_CONTEXT_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_MODIFY_CONTEXT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
