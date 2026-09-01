"""
Synthetic IB SL/TP replacement pair check.

RoadMap89:
- не підключається до TWS;
- перевіряє KEEP/MODIFY + CREATE;
- перевіряє staged OCA pair з двома новими orderId;
- перевіряє порядок stage pair -> cancel old -> position guard -> activate pair;
- перевіряє safety guard до cancel старого survivor.
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
    IB_PROTECTION_ACTION_CREATE,
    IB_PROTECTION_ACTION_KEEP,
    IB_PROTECTION_ACTION_MODIFY,
    IBAdapter,
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
) -> Order:
    """
    Побудувати synthetic standalone protective Order.
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
    order.ocaGroup = ""
    order.ocaType = 0

    if order_type == "STP":
        order.auxPrice = price
    else:
        order.lmtPrice = price

    return order


def _build_standalone_sl(
    contract: Contract,
) -> dict[str, Any]:
    """
    Побудувати standalone Stop Loss metadata.
    """
    return {
        "stop_loss": 1.143,
        "take_profit": None,
        "stop_loss_order_id": 2101,
        "stop_loss_same_client_id": True,
        "stop_loss_operational_ambiguous": False,
        "stop_loss_contract_object": contract,
        "stop_loss_order_object": _build_order(
            order_id=2101,
            order_type="STP",
            price=1.143,
        ),
        "stop_loss_oca_group": "",
        "stop_loss_oca_type": 0,
    }


def _build_standalone_tp(
    contract: Contract,
) -> dict[str, Any]:
    """
    Побудувати standalone Take Profit metadata.
    """
    return {
        "stop_loss": None,
        "take_profit": 1.148,
        "take_profit_order_id": 2102,
        "take_profit_same_client_id": True,
        "take_profit_operational_ambiguous": False,
        "take_profit_contract_object": contract,
        "take_profit_order_object": _build_order(
            order_id=2102,
            order_type="LMT",
            price=1.148,
        ),
        "take_profit_oca_group": "",
        "take_profit_oca_type": 0,
    }


def main() -> int:
    """
    Запустити synthetic replacement pair test.
    """
    logger = logging.getLogger(__name__)
    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )
    contract = _build_contract()

    try:
        setattr(adapter, "_connected", True)

        plan = IBAdapter.build_position_sl_tp_modify_plan(
            current_protection=_build_standalone_sl(contract),
            stop_loss=1.143,
            take_profit=1.148,
        )

        print("KEEP SL + CREATE TP replacement pair plan")
        print(f"  stop_loss_action={plan['stop_loss_action']}")
        print(f"  take_profit_action={plan['take_profit_action']}")
        print(
            "  replacement_pair_survivor_leg="
            f"{plan['replacement_pair_survivor_leg']}"
        )
        print("  replacement_pair_create_leg=" f"{plan['replacement_pair_create_leg']}")

        _require_equal(plan["blocked"], False, "Planner blocked")
        _require_equal(
            plan["stop_loss_action"],
            IB_PROTECTION_ACTION_KEEP,
            "Stop Loss planner action",
        )
        _require_equal(
            plan["take_profit_action"],
            IB_PROTECTION_ACTION_CREATE,
            "Take Profit planner action",
        )
        _require_equal(
            plan["replacement_pair_survivor_leg"],
            "stop_loss",
            "Replacement pair survivor leg",
        )
        _require_equal(
            plan["replacement_pair_create_leg"],
            "take_profit",
            "Replacement pair create leg",
        )
        _require_equal(plan["oca_relink_legs"], [], "Legacy OCA relink legs")

        prepare_pair = getattr(
            adapter,
            "_prepare_sl_tp_replacement_pair_execution",
        )
        execute_pair = getattr(
            adapter,
            "_execute_sl_tp_replacement_pair_operation",
        )

        with patch.object(
            adapter,
            "_get_next_order_id",
            side_effect=[2201, 2202],
        ):
            execution_package = prepare_pair(
                plan=plan,
                position_id="IB:DUM513747:EURUSD",
                position_side="BUY",
                account_id="DUM513747",
                protective_action="SELL",
                position_volume=1000.0,
                position_contract_object=contract,
                order_ref="[LGE:M] LGE manual UI order | SLTP_MODIFY",
            )

        staged_orders = execution_package["replacement_staged_orders"]
        active_orders = execution_package["replacement_active_orders"]
        oca_group = execution_package["oca_group"]

        print("Replacement pair preparation")
        print("  order_ids=" f"{sorted(execution_package['operation_order_ids'])}")
        print(f"  oca_group={oca_group!r}")
        print(
            "  staged_transmit="
            f"{[staged_orders[key].transmit for key in staged_orders]}"
        )
        print(
            "  active_transmit="
            f"{[active_orders[key].transmit for key in active_orders]}"
        )

        _require_equal(
            execution_package["create_order_ids"],
            {
                "stop_loss": 2201,
                "take_profit": 2202,
            },
            "Replacement pair create ids",
        )
        for staged_order in staged_orders.values():
            _require_equal(
                staged_order.orderRef,
                "[LGE:M] LGE manual UI order | SLTP_MODIFY",
                "Replacement pair order ref",
            )
        _require_equal(
            execution_package["old_survivor_order_id"],
            2101,
            "Old standalone survivor id",
        )
        _require_equal(
            staged_orders["stop_loss"].ocaGroup,
            oca_group,
            "Staged Stop Loss OCA group",
        )
        _require_equal(
            staged_orders["take_profit"].ocaGroup,
            oca_group,
            "Staged Take Profit OCA group",
        )
        _require_equal(
            staged_orders["stop_loss"].transmit,
            False,
            "Staged Stop Loss transmit",
        )
        _require_equal(
            staged_orders["take_profit"].transmit,
            False,
            "Staged Take Profit transmit",
        )
        _require_equal(
            active_orders["stop_loss"].transmit,
            True,
            "Active Stop Loss transmit",
        )
        _require_equal(
            active_orders["take_profit"].transmit,
            True,
            "Active Take Profit transmit",
        )

        client = getattr(adapter, "_client")
        call_order: list[tuple[str, int, bool | None]] = []

        def record_place_order(
            order_id: int,
            _contract: Contract,
            order: Order,
        ) -> None:
            """
            Зафіксувати synthetic placeOrder.
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
            Зафіксувати synthetic cancelOrder.
            """
            call_order.append(("cancelOrder", order_id, None))

        def confirm_stage(
            *,
            order_id: int,
            leg: str,
            timeout: float,
        ) -> dict[str, Any]:
            """
            Підтвердити local staged order.
            """
            if timeout <= 0.0:
                raise AssertionError("Stage timeout must be positive")

            return {
                "action": "STAGE_LOCAL",
                "leg": leg,
                "order_id": order_id,
                "confirmed": True,
                "terminal": True,
                "status": "STAGED_LOCAL_NO_ERROR",
                "timeout": False,
                "errors": [],
            }

        def confirm_wait(
            *,
            execution_actions: list[dict[str, Any]],
            timeout: float,
        ) -> list[dict[str, Any]]:
            """
            Підтвердити cancel старого survivor та activation pair.
            """
            if timeout <= 0.0:
                raise AssertionError("Wait timeout must be positive")

            if execution_actions[0]["leg"] == "OLD_SURVIVOR":
                return [
                    {
                        "leg": "OLD_SURVIVOR",
                        "order_id": 2101,
                        "confirmed": True,
                        "terminal": True,
                        "status": "Cancelled",
                        "timeout": False,
                    }
                ]

            return [
                {
                    "leg": row["leg"],
                    "order_id": row["order_id"],
                    "confirmed": True,
                    "terminal": True,
                    "status": "Submitted",
                    "timeout": False,
                    "transmit": True,
                }
                for row in execution_actions
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
            operation_result = execute_pair(
                execution_package=execution_package,
            )

        print("Replacement pair execution")
        print(f"  call_order={call_order}")
        print(f"  confirmed={operation_result['confirmed']}")

        _require_equal(
            call_order,
            [
                ("placeOrder", 2201, False),
                ("placeOrder", 2202, False),
                ("cancelOrder", 2101, None),
                ("placeOrder", 2201, True),
                ("placeOrder", 2202, True),
            ],
            "Replacement pair broker call order",
        )
        _require_equal(
            operation_result["confirmed"],
            True,
            "Replacement pair confirmation",
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

        def reject_first_stage(
            *,
            order_id: int,
            leg: str,
            timeout: float,
        ) -> dict[str, Any]:
            """
            Відхилити перший local stage.
            """
            if timeout <= 0.0:
                raise AssertionError("Rejected timeout must be positive")

            return {
                "action": "STAGE_LOCAL",
                "leg": leg,
                "order_id": order_id,
                "confirmed": False,
                "terminal": True,
                "status": "ERROR",
                "timeout": False,
                "errors": ["Synthetic replacement pair stage error"],
            }

        try:
            with (
                patch.object(
                    client,
                    "placeOrder",
                    side_effect=record_failed_stage_place,
                ),
                patch.object(
                    adapter,
                    "_wait_for_sl_tp_replacement_staged",
                    side_effect=reject_first_stage,
                ),
            ):
                execute_pair(
                    execution_package=execution_package,
                )
        except RuntimeError as exc:
            failed_stage_error = str(exc)
        else:
            raise AssertionError("Rejected replacement pair stage must fail")

        print("Replacement pair stage safety guard")
        print(f"  call_order={failed_stage_calls}")
        print(f"  error={failed_stage_error}")

        _require_equal(
            failed_stage_calls,
            [
                ("placeOrder", 2201, False),
            ],
            "Failed pair stage broker call order",
        )

        modify_plan = IBAdapter.build_position_sl_tp_modify_plan(
            current_protection=_build_standalone_sl(contract),
            stop_loss=1.142,
            take_profit=1.148,
        )
        _require_equal(
            modify_plan["stop_loss_action"],
            IB_PROTECTION_ACTION_MODIFY,
            "Modified survivor planner action",
        )
        _require_equal(
            modify_plan["replacement_pair_survivor_leg"],
            "stop_loss",
            "Modified survivor replacement pair",
        )

        reverse_plan = IBAdapter.build_position_sl_tp_modify_plan(
            current_protection=_build_standalone_tp(contract),
            stop_loss=1.143,
            take_profit=1.148,
        )

        print("KEEP TP + CREATE SL replacement pair plan")
        print(
            "  replacement_pair_survivor_leg="
            f"{reverse_plan['replacement_pair_survivor_leg']}"
        )
        print(
            "  replacement_pair_create_leg="
            f"{reverse_plan['replacement_pair_create_leg']}"
        )

        _require_equal(
            reverse_plan["replacement_pair_survivor_leg"],
            "take_profit",
            "Reverse pair survivor leg",
        )
        _require_equal(
            reverse_plan["replacement_pair_create_leg"],
            "stop_loss",
            "Reverse pair create leg",
        )

        print("IB_SL_TP_REPLACEMENT_PAIR_CHECK=OK")
        return 0
    finally:
        setattr(adapter, "_connected", False)


if __name__ == "__main__":
    raise SystemExit(main())
