# run_ib_sl_tp_execution_preparation_check.py
"""
Synthetic IB SL/TP execution-preparation check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє резервування CREATE order ids;
- перевіряє OCA group;
- перевіряє повний execution package;
- перевіряє CANCEL/KEEP без витрачання nextValidId;
- перевіряє blocked і no-operation plans.
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
from engine.runtime_constants import (  # noqa: E402
    IB_SL_TP_OCA_GROUP_PREFIX,
    IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
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


def _index_by_leg(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Побудувати індекс package rows за protection leg.
    """
    return {str(row["leg"]): row for row in rows}


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


def _build_existing_stop_order(
    *,
    order_id: int,
    stop_price: float,
) -> Order:
    """
    Побудувати synthetic existing Stop Loss order.
    """
    order = Order()
    order.orderId = order_id
    order.account = "DUM513747"
    order.action = "SELL"
    order.orderType = "STP"
    order.totalQuantity = 1000.0
    order.auxPrice = stop_price
    order.parentId = 0
    order.tif = "GTC"
    order.transmit = True
    order.orderRef = "EXISTING_STOP"
    order.ocaGroup = ""
    order.ocaType = 0
    return order


def _expect_runtime_error(
    *,
    name: str,
    expected_text: str,
    prepare_execution: Any,
    plan: dict[str, Any],
    position_contract: Contract,
) -> None:
    """
    Перевірити preparation failure.
    """
    try:
        prepare_execution(
            plan=plan,
            account_id="DUM513747",
            protective_action="SELL",
            position_volume=1000.0,
            position_contract_object=position_contract,
        )
    except RuntimeError as exc:
        error_text = str(exc)

        if expected_text not in error_text:
            raise AssertionError(
                f"{name}: unexpected error text: {error_text}"
            ) from exc

        print(name)
        print(f"  error={error_text}")
        print("  result=OK")
        print()
        return

    raise AssertionError(f"{name}: expected RuntimeError")


def main() -> int:
    """
    Перевірити повну підготовку IB SL/TP execution.
    """
    logger = logging.getLogger(__name__)

    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )

    prepare_execution = getattr(
        adapter,
        "_prepare_sl_tp_execution",
    )

    position_contract = _build_contract()

    try:
        with (
            patch.object(
                EClient,
                "placeOrder",
                side_effect=AssertionError("placeOrder must not be called"),
            ),
            patch.object(
                EClient,
                "cancelOrder",
                side_effect=AssertionError("cancelOrder must not be called"),
            ),
        ):
            # 1. CREATE + CREATE:
            #    два нові ids, одна OCA group.
            with patch.object(
                adapter,
                "_get_next_order_id",
                side_effect=[
                    1301,
                    1302,
                ],
            ) as next_order_id_mock:
                create_package = prepare_execution(
                    plan={
                        "blocked": False,
                        "stop_loss_action": IB_PROTECTION_ACTION_CREATE,
                        "take_profit_action": IB_PROTECTION_ACTION_CREATE,
                        "new_stop_loss": 1.14000,
                        "new_take_profit": 1.14542,
                        "requires_oca_group": True,
                        "oca_relink_legs": [],
                    },
                    account_id="DUM513747",
                    protective_action="SELL",
                    position_volume=1000.0,
                    position_contract_object=position_contract,
                )

            create_payloads = _index_by_leg(create_package["broker_payloads"])

            stop_create_order = create_payloads["STOP_LOSS"]["broker_order_object"]

            take_create_order = create_payloads["TAKE_PROFIT"]["broker_order_object"]

            expected_create_oca = f"{IB_SL_TP_OCA_GROUP_PREFIX}_" "2_1301_1302"

            print("CREATE + CREATE preparation")
            print("  create_order_ids=" f"{create_package['create_order_ids']}")
            print("  oca_group=" f"{create_package['oca_group']}")
            print(
                "  operation_order_ids="
                f"{sorted(create_package['operation_order_ids'])}"
            )

            _require_equal(
                next_order_id_mock.call_count,
                2,
                "CREATE nextValidId call count",
            )
            _require_equal(
                create_package["create_order_ids"],
                {
                    "stop_loss": 1301,
                    "take_profit": 1302,
                },
                "CREATE allocated ids",
            )
            _require_equal(
                create_package["oca_group"],
                expected_create_oca,
                "CREATE OCA group",
            )
            _require_equal(
                create_package["operation_order_ids"],
                {
                    1301,
                    1302,
                },
                "CREATE operation order ids",
            )

            _require_equal(
                stop_create_order.orderId,
                1301,
                "CREATE Stop Loss order id",
            )
            _require_equal(
                take_create_order.orderId,
                1302,
                "CREATE Take Profit order id",
            )
            _require_equal(
                stop_create_order.ocaGroup,
                expected_create_oca,
                "CREATE Stop Loss OCA group",
            )
            _require_equal(
                take_create_order.ocaGroup,
                expected_create_oca,
                "CREATE Take Profit OCA group",
            )
            _require_equal(
                stop_create_order.ocaType,
                IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
                "CREATE Stop Loss OCA type",
            )
            _require_equal(
                take_create_order.ocaType,
                IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
                "CREATE Take Profit OCA type",
            )
            _require_equal(
                stop_create_order.transmit,
                True,
                "CREATE Stop Loss transmit",
            )
            _require_equal(
                take_create_order.transmit,
                True,
                "CREATE Take Profit transmit",
            )

            print("  result=OK")
            print()

            # 2. KEEP + CREATE:
            #    KEEP перетворюється на MODIFY для OCA relink,
            #    витрачається лише один новий order id.
            existing_stop_contract = _build_contract()
            existing_stop_order = _build_existing_stop_order(
                order_id=1401,
                stop_price=1.14000,
            )

            with patch.object(
                adapter,
                "_get_next_order_id",
                return_value=1402,
            ) as next_order_id_mock:
                relink_package = prepare_execution(
                    plan={
                        "blocked": False,
                        "stop_loss_action": IB_PROTECTION_ACTION_KEEP,
                        "take_profit_action": IB_PROTECTION_ACTION_CREATE,
                        "new_stop_loss": 1.14000,
                        "new_take_profit": 1.14600,
                        "stop_loss_order_id": 1401,
                        "stop_loss_contract_object": existing_stop_contract,
                        "stop_loss_order_object": existing_stop_order,
                        "requires_oca_group": True,
                        "oca_relink_legs": [
                            "stop_loss",
                        ],
                    },
                    account_id="DUM513747",
                    protective_action="SELL",
                    position_volume=1000.0,
                    position_contract_object=position_contract,
                )

            relink_actions = _index_by_leg(relink_package["execution_actions"])
            relink_payloads = _index_by_leg(relink_package["broker_payloads"])

            relink_stop_order = relink_payloads["STOP_LOSS"]["broker_order_object"]

            relink_take_order = relink_payloads["TAKE_PROFIT"]["broker_order_object"]

            expected_relink_oca = f"{IB_SL_TP_OCA_GROUP_PREFIX}_" "2_1401_1402"

            print("KEEP + CREATE OCA relink preparation")
            print(
                "  STOP_LOSS planner="
                f"{relink_actions['STOP_LOSS']['planner_action']} "
                "execution="
                f"{relink_actions['STOP_LOSS']['action']}"
            )
            print("  create_order_ids=" f"{relink_package['create_order_ids']}")
            print("  oca_group=" f"{relink_package['oca_group']}")

            _require_equal(
                next_order_id_mock.call_count,
                1,
                "Relink nextValidId call count",
            )
            _require_equal(
                relink_package["create_order_ids"],
                {
                    "take_profit": 1402,
                },
                "Relink allocated ids",
            )
            _require_equal(
                relink_actions["STOP_LOSS"]["planner_action"],
                IB_PROTECTION_ACTION_KEEP,
                "Relink planner action",
            )
            _require_equal(
                relink_actions["STOP_LOSS"]["action"],
                IB_PROTECTION_ACTION_MODIFY,
                "Relink execution action",
            )
            _require_equal(
                relink_actions["TAKE_PROFIT"]["action"],
                IB_PROTECTION_ACTION_CREATE,
                "Relink Take Profit action",
            )
            _require_equal(
                relink_package["oca_group"],
                expected_relink_oca,
                "Relink OCA group",
            )
            _require_equal(
                relink_package["operation_order_ids"],
                {
                    1401,
                    1402,
                },
                "Relink operation order ids",
            )
            _require_equal(
                existing_stop_order.ocaGroup,
                "",
                "Original Stop Loss Order changed",
            )
            _require_equal(
                relink_stop_order.ocaGroup,
                expected_relink_oca,
                "Relink Stop Loss OCA group",
            )
            _require_equal(
                relink_take_order.ocaGroup,
                expected_relink_oca,
                "Relink Take Profit OCA group",
            )
            _require_equal(
                relink_stop_order.transmit,
                True,
                "Relink Stop Loss transmit",
            )
            _require_equal(
                relink_take_order.transmit,
                True,
                "Relink Take Profit transmit",
            )

            print("  result=OK")
            print()

            # 3. CANCEL + KEEP:
            #    nextValidId не витрачається.
            with patch.object(
                adapter,
                "_get_next_order_id",
                side_effect=AssertionError("CANCEL + KEEP must not allocate order id"),
            ) as next_order_id_mock:
                cancel_package = prepare_execution(
                    plan={
                        "blocked": False,
                        "stop_loss_action": IB_PROTECTION_ACTION_CANCEL,
                        "take_profit_action": IB_PROTECTION_ACTION_KEEP,
                        "new_stop_loss": None,
                        "new_take_profit": None,
                        "stop_loss_order_id": 1501,
                        "take_profit_order_id": 1502,
                        "requires_oca_group": False,
                        "oca_relink_legs": [],
                    },
                    account_id="DUM513747",
                    protective_action="SELL",
                    position_volume=1000.0,
                    position_contract_object=position_contract,
                )

            cancel_payloads = _index_by_leg(cancel_package["broker_payloads"])

            print("CANCEL + KEEP preparation")
            print("  create_order_ids=" f"{cancel_package['create_order_ids']}")
            print(
                "  operation_order_ids="
                f"{sorted(cancel_package['operation_order_ids'])}"
            )

            _require_equal(
                next_order_id_mock.call_count,
                0,
                "CANCEL + KEEP nextValidId call count",
            )
            _require_equal(
                cancel_package["create_order_ids"],
                {},
                "CANCEL + KEEP allocated ids",
            )
            _require_equal(
                cancel_package["oca_group"],
                None,
                "CANCEL + KEEP OCA group",
            )
            _require_equal(
                cancel_package["operation_order_ids"],
                {
                    1501,
                },
                "CANCEL + KEEP operation order ids",
            )

            for leg_name in (
                "STOP_LOSS",
                "TAKE_PROFIT",
            ):
                _require_equal(
                    cancel_payloads[leg_name]["broker_contract_object"],
                    None,
                    f"{leg_name} passive Contract",
                )
                _require_equal(
                    cancel_payloads[leg_name]["broker_order_object"],
                    None,
                    f"{leg_name} passive Order",
                )

            print("  result=OK")
            print()

            # 4. Blocked plan:
            #    allocation не починається.
            with patch.object(
                adapter,
                "_get_next_order_id",
                side_effect=AssertionError("Blocked plan must not allocate order id"),
            ) as next_order_id_mock:
                _expect_runtime_error(
                    name="Blocked plan preparation",
                    expected_text="create-order id allocation is blocked",
                    prepare_execution=prepare_execution,
                    plan={
                        "blocked": True,
                        "blocked_flags": [
                            "stop_loss_partial",
                        ],
                    },
                    position_contract=position_contract,
                )

            _require_equal(
                next_order_id_mock.call_count,
                0,
                "Blocked plan nextValidId call count",
            )

            # 5. KEEP + KEEP:
            #    package відхиляється як no-op.
            with patch.object(
                adapter,
                "_get_next_order_id",
                side_effect=AssertionError("KEEP + KEEP must not allocate order id"),
            ) as next_order_id_mock:
                _expect_runtime_error(
                    name="KEEP + KEEP no-operation plan",
                    expected_text="contains no broker operations",
                    prepare_execution=prepare_execution,
                    plan={
                        "blocked": False,
                        "stop_loss_action": IB_PROTECTION_ACTION_KEEP,
                        "take_profit_action": IB_PROTECTION_ACTION_KEEP,
                        "new_stop_loss": 1.14000,
                        "new_take_profit": 1.14600,
                        "stop_loss_order_id": 1601,
                        "take_profit_order_id": 1602,
                        "requires_oca_group": False,
                        "oca_relink_legs": [],
                    },
                    position_contract=position_contract,
                )

            _require_equal(
                next_order_id_mock.call_count,
                0,
                "KEEP + KEEP nextValidId call count",
            )

    except AssertionError as exc:
        print("IB_SL_TP_EXECUTION_PREPARATION_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_EXECUTION_PREPARATION_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
