# run_ib_sl_tp_replacement_survivor_check.py
"""
Synthetic IB SL/TP replacement survivor check.

RoadMap89:
- не підключається до TWS;
- перевіряє KEEP + CANCEL для старої OCA-пари;
- перевіряє новий standalone survivor з новим orderId;
- перевіряє staged transmit=False;
- перевіряє порядок stage -> cancel old OCA -> activate;
- перевіряє cleanup staged replacement при помилці до cancel confirmation.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ibapi.contract import Contract
from ibapi.order import Order

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import (  # noqa: E402
    IB_PROTECTION_ACTION_CANCEL,
    IB_PROTECTION_ACTION_KEEP,
    IBAdapter,
)
from engine.runtime_constants import (  # noqa: E402
    IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
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
    price: float,
    oca_group: str,
) -> Order:
    """
    Побудувати synthetic existing protective Order.
    """
    order = Order()
    order.orderId = order_id
    order.account = "DUM513747"
    order.action = "SELL"
    order.orderType = order_type
    order.totalQuantity = 1000.0
    order.parentId = 0
    order.tif = "GTC"
    order.transmit = True
    order.orderRef = "LGE_SL_TP"
    order.ocaGroup = oca_group
    order.ocaType = IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK

    if order_type == "STP":
        order.auxPrice = price
    else:
        order.lmtPrice = price

    return order


def _build_current_protection(
    contract: Contract,
) -> dict[str, Any]:
    """
    Побудувати synthetic OCA protection metadata.
    """
    old_oca_group = "LGE_TEST_OLD_OCA"

    return {
        "stop_loss": 1.133,
        "take_profit": 1.145,
        "stop_loss_order_id": 1901,
        "take_profit_order_id": 1902,
        "stop_loss_same_client_id": True,
        "take_profit_same_client_id": True,
        "stop_loss_operational_ambiguous": False,
        "take_profit_operational_ambiguous": False,
        "stop_loss_contract_object": contract,
        "take_profit_contract_object": contract,
        "stop_loss_order_object": _build_order(
            order_id=1901,
            order_type="STP",
            price=1.133,
            oca_group=old_oca_group,
        ),
        "take_profit_order_object": _build_order(
            order_id=1902,
            order_type="LMT",
            price=1.145,
            oca_group=old_oca_group,
        ),
        "stop_loss_oca_group": old_oca_group,
        "take_profit_oca_group": old_oca_group,
        "stop_loss_oca_type": IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
        "take_profit_oca_type": IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
    }


def main() -> int:
    """
    Запустити synthetic replacement survivor test.
    """
    logger = logging.getLogger(__name__)
    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )
    contract = _build_contract()
    current_protection = _build_current_protection(contract)

    try:
        setattr(adapter, "_connected", True)

        plan = IBAdapter.build_position_sl_tp_modify_plan(
            current_protection=current_protection,
            stop_loss=1.133,
            take_profit=None,
        )

        print("KEEP SL + CANCEL TP replacement plan")
        print(f"  stop_loss_action={plan['stop_loss_action']}")
        print(f"  take_profit_action={plan['take_profit_action']}")
        print("  replacement_survivor_leg=" f"{plan['replacement_survivor_leg']}")
        print("  replacement_cancel_leg=" f"{plan['replacement_cancel_leg']}")

        _require_equal(plan["blocked"], False, "Planner blocked")
        _require_equal(
            plan["stop_loss_action"],
            IB_PROTECTION_ACTION_KEEP,
            "Stop Loss planner action",
        )
        _require_equal(
            plan["take_profit_action"],
            IB_PROTECTION_ACTION_CANCEL,
            "Take Profit planner action",
        )
        _require_equal(
            plan["replacement_survivor_leg"],
            "stop_loss",
            "Replacement survivor leg",
        )
        _require_equal(
            plan["replacement_cancel_leg"],
            "take_profit",
            "Replacement cancel leg",
        )

        prepare_replacement = getattr(
            adapter,
            "_prepare_sl_tp_replacement_survivor_execution",
        )
        execute_replacement = getattr(
            adapter,
            "_execute_sl_tp_replacement_survivor_operation",
        )

        with patch.object(
            adapter,
            "_get_next_order_id",
            return_value=2001,
        ):
            execution_package = prepare_replacement(
                plan=plan,
                position_id="IB:DUM513747:EURUSD",
                position_side="BUY",
                account_id="DUM513747",
                protective_action="SELL",
                position_volume=1000.0,
                position_contract_object=contract,
                order_ref="[LGE:M] LGE manual UI order | SLTP_MODIFY",
            )

        staged_order = execution_package["replacement_staged_order_object"]
        active_order = execution_package["replacement_active_order_object"]

        print("Replacement survivor preparation")
        print("  order_ids=" f"{sorted(execution_package['operation_order_ids'])}")
        print(f"  staged_transmit={staged_order.transmit}")
        print(f"  active_transmit={active_order.transmit}")
        print(f"  oca_group={staged_order.ocaGroup!r}")

        _require_equal(
            execution_package["replacement_order_id"],
            2001,
            "Replacement order id",
        )
        _require_equal(
            execution_package["old_survivor_order_id"],
            1901,
            "Old survivor order id",
        )
        _require_equal(
            execution_package["old_cancel_order_id"],
            1902,
            "Old cancel order id",
        )
        _require_equal(staged_order.orderType, "STP", "Staged type")
        _require_equal(
            staged_order.orderRef,
            "[LGE:M] LGE manual UI order | SLTP_MODIFY",
            "Staged order ref",
        )
        _require_equal(staged_order.auxPrice, 1.133, "Staged price")
        _require_equal(staged_order.transmit, False, "Staged transmit")
        _require_equal(staged_order.ocaGroup, "", "Staged OCA group")
        _require_equal(staged_order.ocaType, 0, "Staged OCA type")
        _require_equal(active_order.transmit, True, "Active transmit")

        waiting_activation = IBAdapter.build_sl_tp_operation_results(
            execution_actions=[
                {
                    "action": "CREATE",
                    "leg": "STOP_LOSS",
                    "order_id": 2001,
                    "require_transmit_true": True,
                }
            ],
            operation_snapshot={
                "open_orders": {
                    2001: {
                        "status": "Submitted",
                        "transmit": False,
                    }
                },
                "statuses": {
                    2001: {
                        "status": "Submitted",
                    }
                },
            },
        )[0]
        confirmed_activation = IBAdapter.build_sl_tp_operation_results(
            execution_actions=[
                {
                    "action": "CREATE",
                    "leg": "STOP_LOSS",
                    "order_id": 2001,
                    "require_transmit_true": True,
                }
            ],
            operation_snapshot={
                "open_orders": {
                    2001: {
                        "status": "Submitted",
                        "transmit": True,
                    }
                },
                "statuses": {
                    2001: {
                        "status": "Submitted",
                    }
                },
            },
        )[0]

        print("Replacement transmit confirmation")
        print(f"  waiting_status={waiting_activation['status']}")
        print(f"  confirmed={confirmed_activation['confirmed']}")

        _require_equal(
            waiting_activation["status"],
            "WAITING_TRANSMIT_CONFIRMATION",
            "Waiting activation status",
        )
        _require_equal(
            waiting_activation["confirmed"],
            False,
            "Waiting activation confirmation",
        )
        _require_equal(
            confirmed_activation["confirmed"],
            True,
            "Active replacement confirmation",
        )

        client = getattr(adapter, "_client")
        call_order: list[tuple[str, int, bool | None]] = []

        def record_place_order(
            order_id: int,
            _contract: Contract,
            order: Order,
        ) -> None:
            """
            Зафіксувати placeOrder stage/activate.
            """
            call_order.append(
                (
                    "placeOrder",
                    order_id,
                    bool(order.transmit),
                )
            )

        def record_cancel_order(
            order_id: int,
            _order_cancel: Any,
        ) -> None:
            """
            Зафіксувати cancelOrder.
            """
            call_order.append(("cancelOrder", order_id, None))

        def confirm_stage(
            *,
            order_id: int,
            leg: str,
            timeout: float,
        ) -> dict[str, Any]:
            """
            Підтвердити local staged replacement.
            """
            _require_equal(order_id, 2001, "Stage order id")
            _require_equal(leg, "STOP_LOSS", "Stage leg")

            if timeout <= 0.0:
                raise AssertionError("Stage timeout must be positive")

            return {
                "action": "STAGE_LOCAL",
                "leg": leg,
                "order_id": order_id,
                "confirmed": True,
                "terminal": True,
                "status": "PendingSubmit",
                "timeout": False,
                "errors": [],
            }

        def confirm_wait(
            *,
            execution_actions: list[dict[str, Any]],
            timeout: float,
        ) -> list[dict[str, Any]]:
            """
            Підтвердити old OCA cancel і replacement activation.
            """
            if timeout <= 0.0:
                raise AssertionError("Wait timeout must be positive")

            first_leg = str(execution_actions[0]["leg"])

            if first_leg.startswith("OLD_"):
                return [
                    {
                        "leg": row["leg"],
                        "order_id": row["order_id"],
                        "confirmed": True,
                        "terminal": True,
                        "status": "Cancelled",
                        "timeout": False,
                    }
                    for row in execution_actions
                ]

            _require_equal(
                execution_actions[0]["require_transmit_true"],
                True,
                "Activation transmit requirement",
            )

            return [
                {
                    "leg": first_leg,
                    "order_id": 2001,
                    "confirmed": True,
                    "terminal": True,
                    "status": "Submitted",
                    "timeout": False,
                    "transmit": True,
                }
            ]

        with (
            patch.object(
                client,
                "placeOrder",
                side_effect=record_place_order,
            ),
            patch.object(
                client,
                "cancelOrder",
                side_effect=record_cancel_order,
            ),
            patch.object(
                adapter,
                "_wait_for_sl_tp_replacement_staged",
                side_effect=confirm_stage,
            ),
            patch.object(
                adapter,
                "_wait_for_sl_tp_operation_results",
                side_effect=confirm_wait,
            ),
            patch.object(
                adapter,
                "_request_positions_snapshot_for_execution",
                return_value=[
                    {
                        "account": "DUM513747",
                        "position": 1000.0,
                        "contract": contract,
                    }
                ],
            ),
        ):
            operation_result = execute_replacement(
                execution_package=execution_package,
            )

        wrapper = getattr(adapter, "_wrapper")
        wait_for_stage = getattr(
            adapter,
            "_wait_for_sl_tp_replacement_staged",
        )

        wrapper.start_sl_tp_operation({2001})

        try:
            local_stage_result = wait_for_stage(
                order_id=2001,
                leg="STOP_LOSS",
                timeout=0.01,
            )
        finally:
            wrapper.clear_sl_tp_operation()

        print("Replacement local no-error stage")
        print(f"  status={local_stage_result['status']}")
        print(f"  confirmed={local_stage_result['confirmed']}")

        _require_equal(
            local_stage_result["status"],
            "STAGED_LOCAL_NO_ERROR",
            "Local stage status",
        )
        _require_equal(
            local_stage_result["confirmed"],
            True,
            "Local stage confirmation",
        )

        print("Replacement survivor execution")
        print(f"  call_order={call_order}")
        print(f"  confirmed={operation_result['confirmed']}")

        _require_equal(
            call_order,
            [
                ("placeOrder", 2001, False),
                ("cancelOrder", 1902, None),
                ("placeOrder", 2001, True),
            ],
            "Replacement broker call order",
        )
        _require_equal(
            operation_result["confirmed"],
            True,
            "Replacement confirmation",
        )

        failed_stage_calls: list[tuple[str, int, bool | None]] = []

        def record_failed_stage_place(
            order_id: int,
            _contract: Contract,
            order: Order,
        ) -> None:
            """
            Зафіксувати staged placeOrder перед помилкою.
            """
            failed_stage_calls.append(
                (
                    "placeOrder",
                    order_id,
                    bool(order.transmit),
                )
            )

        def record_failed_stage_cancel(
            order_id: int,
            _order_cancel: Any,
        ) -> None:
            """
            Зафіксувати cleanup staged replacement.
            """
            failed_stage_calls.append(("cancelOrder", order_id, None))

        def reject_stage(
            *,
            order_id: int,
            leg: str,
            timeout: float,
        ) -> dict[str, Any]:
            """
            Відхилити local stage confirmation.
            """
            _require_equal(
                timeout > 0.0,
                True,
                "Rejected local stage timeout",
            )

            return {
                "action": "STAGE_LOCAL",
                "leg": leg,
                "order_id": order_id,
                "confirmed": False,
                "terminal": True,
                "status": "ERROR",
                "timeout": False,
                "errors": ["Synthetic local stage error"],
            }

        try:
            with (
                patch.object(
                    client,
                    "placeOrder",
                    side_effect=record_failed_stage_place,
                ),
                patch.object(
                    client,
                    "cancelOrder",
                    side_effect=record_failed_stage_cancel,
                ),
                patch.object(
                    adapter,
                    "_wait_for_sl_tp_replacement_staged",
                    side_effect=reject_stage,
                ),
            ):
                execute_replacement(
                    execution_package=execution_package,
                )
        except RuntimeError as exc:
            failed_stage_error = str(exc)
        else:
            raise AssertionError("Unconfirmed replacement stage must fail")

        print("Replacement stage safety guard")
        print(f"  call_order={failed_stage_calls}")
        print(f"  error={failed_stage_error}")

        _require_equal(
            failed_stage_calls,
            [
                ("placeOrder", 2001, False),
            ],
            "Failed stage broker call order",
        )

        reverse_plan = IBAdapter.build_position_sl_tp_modify_plan(
            current_protection=current_protection,
            stop_loss=None,
            take_profit=1.145,
        )

        print("KEEP TP + CANCEL SL replacement plan")
        print(
            "  replacement_survivor_leg=" f"{reverse_plan['replacement_survivor_leg']}"
        )
        print("  replacement_cancel_leg=" f"{reverse_plan['replacement_cancel_leg']}")

        _require_equal(
            reverse_plan["replacement_survivor_leg"],
            "take_profit",
            "Reverse replacement survivor leg",
        )
        _require_equal(
            reverse_plan["replacement_cancel_leg"],
            "stop_loss",
            "Reverse replacement cancel leg",
        )

        print("IB_SL_TP_REPLACEMENT_SURVIVOR_CHECK=OK")
        return 0
    finally:
        setattr(adapter, "_connected", False)


if __name__ == "__main__":
    raise SystemExit(main())
