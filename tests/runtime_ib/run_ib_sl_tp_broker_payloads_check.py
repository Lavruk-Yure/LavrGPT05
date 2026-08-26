# run_ib_sl_tp_broker_payloads_check.py
"""
Synthetic IB SL/TP broker-payloads check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє CREATE payloads;
- перевіряє MODIFY через deepcopy;
- перевіряє KEEP + CREATE OCA relink;
- перевіряє CANCEL/KEEP без Order payload;
- перевіряє OCA safety.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
    Побудувати індекс payloads за protection leg.
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


def _build_existing_order(
    *,
    order_id: int,
    order_type: str,
    price: float,
) -> Order:
    """
    Побудувати synthetic existing protective order.
    """
    order = Order()
    order.orderId = order_id
    order.account = "DUM513747"
    order.action = "SELL"
    order.orderType = order_type
    order.totalQuantity = 500.0
    order.parentId = 85
    order.tif = "GTC"
    order.transmit = True
    order.orderRef = "EXISTING_BROKER_REF"
    order.ocaGroup = "EXISTING_OCA"
    order.ocaType = IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK

    if order_type == "STP":
        order.auxPrice = price
        order.lmtPrice = 0.0
    else:
        order.lmtPrice = price
        order.auxPrice = 0.0

    return order


def _expect_exception(
    *,
    name: str,
    expected_text: str,
    execution_actions: list[dict[str, Any]],
    requires_oca_group: bool,
    oca_group: str | None,
) -> None:
    """
    Перевірити блокувальний payload scenario.
    """
    try:
        IBAdapter.build_sl_tp_broker_order_payloads(
            execution_actions=execution_actions,
            account_id="DUM513747",
            protective_action="SELL",
            position_volume=1000.0,
            position_contract_object=_build_contract(),
            requires_oca_group=requires_oca_group,
            oca_group=oca_group,
        )
    except (RuntimeError, ValueError) as exc:
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

    raise AssertionError(f"{name}: expected exception")


def main() -> int:
    """
    Перевірити broker Contract/Order payloads.
    """
    try:
        position_contract = _build_contract()

        # 1. CREATE + CREATE з однією OCA group.
        create_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_CREATE,
                "take_profit_action": IB_PROTECTION_ACTION_CREATE,
                "new_stop_loss": 1.14000,
                "new_take_profit": 1.14542,
                "requires_oca_group": True,
                "oca_relink_legs": [],
            },
            create_order_ids={
                "stop_loss": 701,
                "take_profit": 702,
            },
        )

        create_payloads = IBAdapter.build_sl_tp_broker_order_payloads(
            execution_actions=create_actions,
            account_id="DUM513747",
            protective_action="SELL",
            position_volume=1000.0,
            position_contract_object=position_contract,
            requires_oca_group=True,
            oca_group="LGE_TEST_OCA_CREATE",
            order_ref="[LGE:M] LGE manual UI order | SLTP_MODIFY",
        )

        create_by_leg = _index_by_leg(create_payloads)

        stop_create_order = create_by_leg["STOP_LOSS"]["broker_order_object"]

        take_create_order = create_by_leg["TAKE_PROFIT"]["broker_order_object"]

        print("CREATE + CREATE OCA payloads")
        print(
            "  STOP_LOSS="
            f"id={stop_create_order.orderId} "
            f"type={stop_create_order.orderType} "
            f"transmit={stop_create_order.transmit}"
        )
        print(
            "  TAKE_PROFIT="
            f"id={take_create_order.orderId} "
            f"type={take_create_order.orderType} "
            f"transmit={take_create_order.transmit}"
        )

        _require(
            create_by_leg["STOP_LOSS"]["broker_contract_object"] is position_contract,
            "CREATE Stop Loss Contract identity mismatch",
        )
        _require(
            create_by_leg["TAKE_PROFIT"]["broker_contract_object"] is position_contract,
            "CREATE Take Profit Contract identity mismatch",
        )

        _require_equal(
            stop_create_order.orderId,
            701,
            "CREATE Stop Loss order id",
        )
        _require_equal(
            stop_create_order.orderType,
            "STP",
            "CREATE Stop Loss order type",
        )
        _require_equal(
            stop_create_order.auxPrice,
            1.14000,
            "CREATE Stop Loss price",
        )
        _require_equal(
            take_create_order.orderId,
            702,
            "CREATE Take Profit order id",
        )
        _require_equal(
            take_create_order.orderType,
            "LMT",
            "CREATE Take Profit order type",
        )
        _require_equal(
            take_create_order.lmtPrice,
            1.14542,
            "CREATE Take Profit price",
        )

        for order in (
            stop_create_order,
            take_create_order,
        ):
            _require_equal(
                order.account,
                "DUM513747",
                "CREATE account",
            )
            _require_equal(
                order.action,
                "SELL",
                "CREATE protective action",
            )
            _require_equal(
                float(order.totalQuantity),
                1000.0,
                "CREATE quantity",
            )
            _require_equal(
                order.parentId,
                0,
                "CREATE parent id",
            )
            _require_equal(
                order.ocaGroup,
                "LGE_TEST_OCA_CREATE",
                "CREATE OCA group",
            )
            _require_equal(
                order.ocaType,
                IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
                "CREATE OCA type",
            )
            _require_equal(
                order.orderRef,
                "[LGE:M] LGE manual UI order | SLTP_MODIFY",
                "CREATE order ref",
            )

        _require_equal(
            stop_create_order.transmit,
            True,
            "CREATE Stop Loss transmit order",
        )
        _require_equal(
            take_create_order.transmit,
            True,
            "CREATE Take Profit transmit order",
        )

        print("  result=OK")
        print()

        # 2. MODIFY + MODIFY через незалежні deepcopy.
        stop_contract = _build_contract()
        take_contract = _build_contract()

        original_stop_order = _build_existing_order(
            order_id=801,
            order_type="STP",
            price=1.14000,
        )

        original_take_order = _build_existing_order(
            order_id=802,
            order_type="LMT",
            price=1.14542,
        )

        modify_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_MODIFY,
                "take_profit_action": IB_PROTECTION_ACTION_MODIFY,
                "new_stop_loss": 1.13900,
                "new_take_profit": 1.14600,
                "stop_loss_order_id": 801,
                "take_profit_order_id": 802,
                "stop_loss_contract_object": stop_contract,
                "stop_loss_order_object": original_stop_order,
                "take_profit_contract_object": take_contract,
                "take_profit_order_object": original_take_order,
                "requires_oca_group": False,
                "oca_relink_legs": [],
            }
        )

        modify_payloads = IBAdapter.build_sl_tp_broker_order_payloads(
            execution_actions=modify_actions,
            account_id="DUM513747",
            protective_action="SELL",
            position_volume=1000.0,
            position_contract_object=position_contract,
            requires_oca_group=False,
            oca_group=None,
            order_ref="[LGE:M] LGE manual UI order | SLTP_MODIFY",
        )

        modify_by_leg = _index_by_leg(modify_payloads)

        modified_stop_order = modify_by_leg["STOP_LOSS"]["broker_order_object"]

        modified_take_order = modify_by_leg["TAKE_PROFIT"]["broker_order_object"]

        print("MODIFY + MODIFY payload copies")
        print(
            "  STOP_LOSS="
            f"old={original_stop_order.auxPrice} "
            f"new={modified_stop_order.auxPrice}"
        )
        print(
            "  TAKE_PROFIT="
            f"old={original_take_order.lmtPrice} "
            f"new={modified_take_order.lmtPrice}"
        )

        _require(
            modified_stop_order is not original_stop_order,
            "MODIFY Stop Loss must use deepcopy",
        )
        _require(
            modified_take_order is not original_take_order,
            "MODIFY Take Profit must use deepcopy",
        )

        _require_equal(
            original_stop_order.auxPrice,
            1.14000,
            "Original Stop Loss changed",
        )
        _require_equal(
            original_take_order.lmtPrice,
            1.14542,
            "Original Take Profit changed",
        )
        _require_equal(
            float(original_stop_order.totalQuantity),
            500.0,
            "Original Stop Loss quantity changed",
        )
        _require_equal(
            float(original_take_order.totalQuantity),
            500.0,
            "Original Take Profit quantity changed",
        )

        _require_equal(
            modified_stop_order.auxPrice,
            1.13900,
            "Modified Stop Loss price",
        )
        _require_equal(
            modified_take_order.lmtPrice,
            1.14600,
            "Modified Take Profit price",
        )
        _require_equal(
            float(modified_stop_order.totalQuantity),
            1000.0,
            "Modified Stop Loss quantity",
        )
        _require_equal(
            float(modified_take_order.totalQuantity),
            1000.0,
            "Modified Take Profit quantity",
        )
        _require_equal(
            modified_stop_order.orderRef,
            "[LGE:M] LGE manual UI order | SLTP_MODIFY",
            "Modified Stop Loss order ref",
        )
        _require_equal(
            modified_take_order.orderRef,
            "[LGE:M] LGE manual UI order | SLTP_MODIFY",
            "Modified Take Profit order ref",
        )
        _require_equal(
            modified_stop_order.ocaGroup,
            "EXISTING_OCA",
            "Modified Stop Loss existing OCA",
        )
        _require_equal(
            modified_take_order.ocaGroup,
            "EXISTING_OCA",
            "Modified Take Profit existing OCA",
        )

        print("  result=OK")
        print()

        # 3. KEEP + CREATE з OCA relink.
        relink_contract = _build_contract()

        original_relink_stop = _build_existing_order(
            order_id=901,
            order_type="STP",
            price=1.14000,
        )
        original_relink_stop.ocaGroup = ""

        relink_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_KEEP,
                "take_profit_action": IB_PROTECTION_ACTION_CREATE,
                "new_stop_loss": 1.14000,
                "new_take_profit": 1.14600,
                "stop_loss_order_id": 901,
                "stop_loss_contract_object": relink_contract,
                "stop_loss_order_object": original_relink_stop,
                "requires_oca_group": True,
                "oca_relink_legs": [
                    "stop_loss",
                ],
            },
            create_order_ids={
                "take_profit": 902,
            },
        )

        relink_payloads = IBAdapter.build_sl_tp_broker_order_payloads(
            execution_actions=relink_actions,
            account_id="DUM513747",
            protective_action="SELL",
            position_volume=1000.0,
            position_contract_object=position_contract,
            requires_oca_group=True,
            oca_group="LGE_TEST_OCA_RELINK",
        )

        relink_by_leg = _index_by_leg(relink_payloads)

        relink_stop_order = relink_by_leg["STOP_LOSS"]["broker_order_object"]

        relink_take_order = relink_by_leg["TAKE_PROFIT"]["broker_order_object"]

        print("KEEP + CREATE OCA relink payloads")
        print(
            "  STOP_LOSS planner="
            f"{relink_by_leg['STOP_LOSS']['planner_action']} "
            "execution="
            f"{relink_by_leg['STOP_LOSS']['action']}"
        )
        print("  OCA=" f"{relink_stop_order.ocaGroup}")

        _require_equal(
            relink_by_leg["STOP_LOSS"]["planner_action"],
            IB_PROTECTION_ACTION_KEEP,
            "Relink planner action",
        )
        _require_equal(
            relink_by_leg["STOP_LOSS"]["action"],
            IB_PROTECTION_ACTION_MODIFY,
            "Relink execution action",
        )
        _require_equal(
            original_relink_stop.ocaGroup,
            "",
            "Original relink Order changed",
        )
        _require_equal(
            relink_stop_order.ocaGroup,
            "LGE_TEST_OCA_RELINK",
            "Relink existing Stop Loss OCA",
        )
        _require_equal(
            relink_take_order.ocaGroup,
            "LGE_TEST_OCA_RELINK",
            "Relink created Take Profit OCA",
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

        # 4. CANCEL + KEEP не створюють placeOrder payload.
        passive_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_CANCEL,
                "take_profit_action": IB_PROTECTION_ACTION_KEEP,
                "new_stop_loss": None,
                "new_take_profit": None,
                "stop_loss_order_id": 1001,
                "take_profit_order_id": 1002,
                "requires_oca_group": False,
                "oca_relink_legs": [],
            }
        )

        passive_payloads = IBAdapter.build_sl_tp_broker_order_payloads(
            execution_actions=passive_actions,
            account_id="DUM513747",
            protective_action="SELL",
            position_volume=1000.0,
            position_contract_object=position_contract,
            requires_oca_group=False,
            oca_group=None,
        )

        passive_by_leg = _index_by_leg(passive_payloads)

        print("CANCEL + KEEP payloads")
        print("  STOP_LOSS=" f"{passive_by_leg['STOP_LOSS']['action']}")
        print("  TAKE_PROFIT=" f"{passive_by_leg['TAKE_PROFIT']['action']}")

        for leg_name in (
            "STOP_LOSS",
            "TAKE_PROFIT",
        ):
            _require_equal(
                passive_by_leg[leg_name]["broker_contract_object"],
                None,
                f"{leg_name} passive Contract payload",
            )
            _require_equal(
                passive_by_leg[leg_name]["broker_order_object"],
                None,
                f"{leg_name} passive Order payload",
            )

        print("  result=OK")
        print()

        # 5. OCA group обов'язкова.
        _expect_exception(
            name="OCA group missing",
            expected_text="OCA group is missing",
            execution_actions=create_actions,
            requires_oca_group=True,
            oca_group=None,
        )

        # 6. OCA batch має містити рівно два placeOrder payloads.
        one_create_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_CREATE,
                "take_profit_action": IB_PROTECTION_ACTION_KEEP,
                "new_stop_loss": 1.14000,
                "new_take_profit": None,
                "requires_oca_group": False,
                "oca_relink_legs": [],
            },
            create_order_ids={
                "stop_loss": 1101,
            },
        )

        _expect_exception(
            name="Invalid one-leg OCA batch",
            expected_text="must contain exactly two placeOrder payloads",
            execution_actions=one_create_actions,
            requires_oca_group=True,
            oca_group="LGE_INVALID_OCA",
        )

    except AssertionError as exc:
        print("IB_SL_TP_BROKER_PAYLOADS_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_BROKER_PAYLOADS_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
