# run_ib_sl_tp_execution_actions_check.py
"""
Synthetic IB SL/TP execution-actions check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє planner -> execution actions;
- перевіряє OCA relink;
- перевіряє блокувальні сценарії.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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


def _index_by_leg(
    actions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Побудувати індекс execution actions за protection leg.
    """
    return {str(action["leg"]): action for action in actions}


def _expect_exception(
    *,
    name: str,
    exception_type: type[Exception],
    expected_text: str,
    plan: dict[str, Any],
    create_order_ids: dict[str, int] | None = None,
) -> None:
    """
    Перевірити блокувальний сценарій.
    """
    try:
        IBAdapter.build_sl_tp_execution_actions(
            plan=plan,
            create_order_ids=create_order_ids,
        )
    except exception_type as exc:
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

    raise AssertionError(f"{name}: expected {exception_type.__name__}")


def main() -> int:
    """
    Перевірити planner -> execution actions mapping.
    """
    try:
        # 1. CREATE + CREATE.
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

        create_by_leg = _index_by_leg(create_actions)

        print("CREATE + CREATE")
        print(
            "  STOP_LOSS="
            f"{create_by_leg['STOP_LOSS']['action']} "
            f"id={create_by_leg['STOP_LOSS']['order_id']}"
        )
        print(
            "  TAKE_PROFIT="
            f"{create_by_leg['TAKE_PROFIT']['action']} "
            f"id={create_by_leg['TAKE_PROFIT']['order_id']}"
        )

        _require_equal(
            create_by_leg["STOP_LOSS"]["action"],
            IB_PROTECTION_ACTION_CREATE,
            "CREATE Stop Loss action",
        )
        _require_equal(
            create_by_leg["STOP_LOSS"]["order_id"],
            701,
            "CREATE Stop Loss order id",
        )
        _require_equal(
            create_by_leg["STOP_LOSS"]["order_type"],
            "STP",
            "CREATE Stop Loss order type",
        )
        _require_equal(
            create_by_leg["STOP_LOSS"]["price"],
            1.14000,
            "CREATE Stop Loss price",
        )
        _require_equal(
            create_by_leg["TAKE_PROFIT"]["action"],
            IB_PROTECTION_ACTION_CREATE,
            "CREATE Take Profit action",
        )
        _require_equal(
            create_by_leg["TAKE_PROFIT"]["order_id"],
            702,
            "CREATE Take Profit order id",
        )
        _require_equal(
            create_by_leg["TAKE_PROFIT"]["order_type"],
            "LMT",
            "CREATE Take Profit order type",
        )
        _require_equal(
            create_by_leg["TAKE_PROFIT"]["price"],
            1.14542,
            "CREATE Take Profit price",
        )

        print("  result=OK")
        print()

        # 2. MODIFY + MODIFY.
        stop_contract = object()
        stop_order = object()
        take_contract = object()
        take_order = object()

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
                "stop_loss_order_object": stop_order,
                "take_profit_contract_object": take_contract,
                "take_profit_order_object": take_order,
                "oca_relink_legs": [],
            }
        )

        modify_by_leg = _index_by_leg(modify_actions)

        print("MODIFY + MODIFY")
        print(
            "  STOP_LOSS="
            f"{modify_by_leg['STOP_LOSS']['action']} "
            f"id={modify_by_leg['STOP_LOSS']['order_id']}"
        )
        print(
            "  TAKE_PROFIT="
            f"{modify_by_leg['TAKE_PROFIT']['action']} "
            f"id={modify_by_leg['TAKE_PROFIT']['order_id']}"
        )

        _require(
            modify_by_leg["STOP_LOSS"]["contract_object"] is stop_contract,
            "MODIFY Stop Loss Contract identity mismatch",
        )
        _require(
            modify_by_leg["STOP_LOSS"]["order_object"] is stop_order,
            "MODIFY Stop Loss Order identity mismatch",
        )
        _require(
            modify_by_leg["TAKE_PROFIT"]["contract_object"] is take_contract,
            "MODIFY Take Profit Contract identity mismatch",
        )
        _require(
            modify_by_leg["TAKE_PROFIT"]["order_object"] is take_order,
            "MODIFY Take Profit Order identity mismatch",
        )

        print("  result=OK")
        print()

        # 3. KEEP + CREATE із OCA relink.
        relink_contract = object()
        relink_order = object()

        relink_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_KEEP,
                "take_profit_action": IB_PROTECTION_ACTION_CREATE,
                "new_stop_loss": 1.14000,
                "new_take_profit": 1.14600,
                "stop_loss_order_id": 901,
                "stop_loss_contract_object": relink_contract,
                "stop_loss_order_object": relink_order,
                "requires_oca_group": True,
                "oca_relink_legs": [
                    "stop_loss",
                ],
            },
            create_order_ids={
                "take_profit": 902,
            },
        )

        relink_by_leg = _index_by_leg(relink_actions)

        print("KEEP + CREATE with OCA relink")
        print(
            "  STOP_LOSS planner="
            f"{relink_by_leg['STOP_LOSS']['planner_action']} "
            "execution="
            f"{relink_by_leg['STOP_LOSS']['action']}"
        )
        print("  TAKE_PROFIT=" f"{relink_by_leg['TAKE_PROFIT']['action']}")

        _require_equal(
            relink_by_leg["STOP_LOSS"]["planner_action"],
            IB_PROTECTION_ACTION_KEEP,
            "OCA relink planner action",
        )
        _require_equal(
            relink_by_leg["STOP_LOSS"]["action"],
            IB_PROTECTION_ACTION_MODIFY,
            "OCA relink execution action",
        )
        _require_equal(
            relink_by_leg["STOP_LOSS"]["oca_relink"],
            True,
            "OCA relink flag",
        )
        _require_equal(
            relink_by_leg["STOP_LOSS"]["order_id"],
            901,
            "OCA relink existing order id",
        )
        _require_equal(
            relink_by_leg["TAKE_PROFIT"]["order_id"],
            902,
            "OCA relink created order id",
        )

        print("  result=OK")
        print()

        # 4. CANCEL + CANCEL.
        cancel_actions = IBAdapter.build_sl_tp_execution_actions(
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_CANCEL,
                "take_profit_action": IB_PROTECTION_ACTION_CANCEL,
                "new_stop_loss": None,
                "new_take_profit": None,
                "stop_loss_order_id": 1001,
                "take_profit_order_id": 1002,
                "oca_relink_legs": [],
            }
        )

        cancel_by_leg = _index_by_leg(cancel_actions)

        print("CANCEL + CANCEL")
        print("  STOP_LOSS=" f"{cancel_by_leg['STOP_LOSS']['action']}")
        print("  TAKE_PROFIT=" f"{cancel_by_leg['TAKE_PROFIT']['action']}")

        _require_equal(
            cancel_by_leg["STOP_LOSS"]["order_id"],
            1001,
            "CANCEL Stop Loss order id",
        )
        _require_equal(
            cancel_by_leg["TAKE_PROFIT"]["order_id"],
            1002,
            "CANCEL Take Profit order id",
        )
        _require_equal(
            cancel_by_leg["STOP_LOSS"]["broker_call_required"],
            True,
            "CANCEL Stop Loss broker call",
        )
        _require_equal(
            cancel_by_leg["TAKE_PROFIT"]["broker_call_required"],
            True,
            "CANCEL Take Profit broker call",
        )

        print("  result=OK")
        print()

        # 5. Blocked planner result.
        _expect_exception(
            name="Blocked plan",
            exception_type=RuntimeError,
            expected_text="stop_loss_partial",
            plan={
                "blocked": True,
                "reason": "Unsafe protection coverage.",
                "blocked_flags": [
                    "stop_loss_partial",
                ],
            },
        )

        # 6. CREATE без нового order id.
        _expect_exception(
            name="CREATE without order id",
            exception_type=RuntimeError,
            expected_text="execution order id is missing",
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_CREATE,
                "take_profit_action": IB_PROTECTION_ACTION_KEEP,
                "new_stop_loss": 1.14000,
                "new_take_profit": None,
                "oca_relink_legs": [],
            },
        )

        # 7. Дубльований broker order id.
        _expect_exception(
            name="Duplicate execution order id",
            exception_type=RuntimeError,
            expected_text="Duplicate IB SL/TP execution order id",
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_CREATE,
                "take_profit_action": IB_PROTECTION_ACTION_CREATE,
                "new_stop_loss": 1.14000,
                "new_take_profit": 1.14600,
                "oca_relink_legs": [],
            },
            create_order_ids={
                "stop_loss": 1101,
                "take_profit": 1101,
            },
        )

        # 8. MODIFY без broker Order object.
        _expect_exception(
            name="MODIFY without Order object",
            exception_type=RuntimeError,
            expected_text="Order object is missing",
            plan={
                "blocked": False,
                "stop_loss_action": IB_PROTECTION_ACTION_MODIFY,
                "take_profit_action": IB_PROTECTION_ACTION_KEEP,
                "new_stop_loss": 1.13900,
                "new_take_profit": None,
                "stop_loss_order_id": 1201,
                "stop_loss_contract_object": object(),
                "stop_loss_order_object": None,
                "oca_relink_legs": [],
            },
        )

    except AssertionError as exc:
        print("IB_SL_TP_EXECUTION_ACTIONS_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_EXECUTION_ACTIONS_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
