# run_ib_sl_tp_modify_plan_check.py
"""
Synthetic IB SL/TP modify planner check.

RoadMap87:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє KEEP/MODIFY/CANCEL/CREATE/BLOCK matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import (  # noqa: E402
    IB_PROTECTION_ACTION_BLOCK,
    IB_PROTECTION_ACTION_CANCEL,
    IB_PROTECTION_ACTION_CREATE,
    IB_PROTECTION_ACTION_KEEP,
    IB_PROTECTION_ACTION_MODIFY,
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


def _check_plan(
    *,
    title: str,
    current_protection: dict[str, Any] | None,
    stop_loss: float | None,
    take_profit: float | None,
    expected_stop_loss_action: str,
    expected_take_profit_action: str,
    expected_blocked: bool = False,
    expected_oca_relink_legs: list[str] | None = None,
    expected_replacement_pair: tuple[str, str] | None = None,
) -> None:
    """
    Перевірити один synthetic planner case.
    """
    plan = IBAdapter.build_position_sl_tp_modify_plan(
        current_protection=current_protection,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    print(title)
    print(f"  plan={plan}")

    _require_equal(
        plan["blocked"],
        expected_blocked,
        f"{title}: blocked",
    )
    _require_equal(
        plan["stop_loss_action"],
        expected_stop_loss_action,
        f"{title}: stop_loss_action",
    )
    _require_equal(
        plan["take_profit_action"],
        expected_take_profit_action,
        f"{title}: take_profit_action",
    )

    if expected_oca_relink_legs is not None:
        _require_equal(
            plan.get("requires_oca_group"),
            True,
            f"{title}: requires_oca_group",
        )
        _require_equal(
            plan.get("oca_relink_legs"),
            expected_oca_relink_legs,
            f"{title}: oca_relink_legs",
        )

    if expected_replacement_pair is not None:
        survivor_leg, create_leg = expected_replacement_pair
        _require_equal(
            plan.get("replacement_pair_survivor_leg"),
            survivor_leg,
            f"{title}: replacement_pair_survivor_leg",
        )
        _require_equal(
            plan.get("replacement_pair_create_leg"),
            create_leg,
            f"{title}: replacement_pair_create_leg",
        )

    print("  result=OK")
    print()


def main() -> int:
    """
    Запустити synthetic IB SL/TP planner matrix.
    """
    try:
        contract_object = object()
        stop_order_object = object()
        take_order_object = object()
        _check_plan(
            title="No protection -> no protection",
            current_protection=None,
            stop_loss=None,
            take_profit=None,
            expected_stop_loss_action=IB_PROTECTION_ACTION_KEEP,
            expected_take_profit_action=IB_PROTECTION_ACTION_KEEP,
        )

        _check_plan(
            title="Same full SL/TP -> KEEP",
            current_protection={
                "stop_loss": 1.1000,
                "take_profit": 1.2000,
            },
            stop_loss=1.1000,
            take_profit=1.2000,
            expected_stop_loss_action=IB_PROTECTION_ACTION_KEEP,
            expected_take_profit_action=IB_PROTECTION_ACTION_KEEP,
        )

        _check_plan(
            title="Existing SL/TP -> MODIFY",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_id": 101,
                "stop_loss_client_id": 1,
                "stop_loss_perm_id": 5001,
                "stop_loss_same_client_id": True,
                "stop_loss_operational_ambiguous": False,
                "stop_loss_contract_object": contract_object,
                "stop_loss_order_object": stop_order_object,
                "take_profit": 1.2000,
                "take_profit_order_id": 102,
                "take_profit_client_id": 1,
                "take_profit_perm_id": 5002,
                "take_profit_same_client_id": True,
                "take_profit_operational_ambiguous": False,
                "take_profit_contract_object": contract_object,
                "take_profit_order_object": take_order_object,
            },
            stop_loss=1.1100,
            take_profit=1.2100,
            expected_stop_loss_action=IB_PROTECTION_ACTION_MODIFY,
            expected_take_profit_action=IB_PROTECTION_ACTION_MODIFY,
        )

        _check_plan(
            title="Existing SL/TP -> CANCEL",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_id": 101,
                "stop_loss_same_client_id": True,
                "stop_loss_operational_ambiguous": False,
                "take_profit": 1.2000,
                "take_profit_order_id": 102,
                "take_profit_same_client_id": True,
                "take_profit_operational_ambiguous": False,
            },
            stop_loss=None,
            take_profit=None,
            expected_stop_loss_action=IB_PROTECTION_ACTION_CANCEL,
            expected_take_profit_action=IB_PROTECTION_ACTION_CANCEL,
        )

        _check_plan(
            title="Missing SL/TP -> CREATE",
            current_protection=None,
            stop_loss=1.1000,
            take_profit=1.2000,
            expected_stop_loss_action=IB_PROTECTION_ACTION_CREATE,
            expected_take_profit_action=IB_PROTECTION_ACTION_CREATE,
        )

        _check_plan(
            title="SL MODIFY and TP CREATE",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_id": 101,
                "stop_loss_same_client_id": True,
                "stop_loss_operational_ambiguous": False,
                "stop_loss_contract_object": contract_object,
                "stop_loss_order_object": stop_order_object,
            },
            stop_loss=1.1100,
            take_profit=1.2100,
            expected_stop_loss_action=IB_PROTECTION_ACTION_MODIFY,
            expected_take_profit_action=IB_PROTECTION_ACTION_CREATE,
        )

        _check_plan(
            title="Partial SL coverage -> BLOCK",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_partial": True,
                "take_profit": 1.2000,
            },
            stop_loss=1.1100,
            take_profit=1.2100,
            expected_stop_loss_action=IB_PROTECTION_ACTION_BLOCK,
            expected_take_profit_action=IB_PROTECTION_ACTION_BLOCK,
            expected_blocked=True,
        )

        _check_plan(
            title="Ambiguous TP coverage -> BLOCK",
            current_protection={
                "stop_loss": 1.1000,
                "take_profit_ambiguous": True,
            },
            stop_loss=1.1100,
            take_profit=1.2100,
            expected_stop_loss_action=IB_PROTECTION_ACTION_BLOCK,
            expected_take_profit_action=IB_PROTECTION_ACTION_BLOCK,
            expected_blocked=True,
        )
        _check_plan(
            title="Operationally ambiguous SL MODIFY -> BLOCK",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_ids": [201, 202],
                "stop_loss_order_count": 2,
                "stop_loss_same_client_id": True,
                "stop_loss_operational_ambiguous": True,
            },
            stop_loss=1.1100,
            take_profit=None,
            expected_stop_loss_action=IB_PROTECTION_ACTION_BLOCK,
            expected_take_profit_action=IB_PROTECTION_ACTION_BLOCK,
            expected_blocked=True,
        )

        _check_plan(
            title="Different-client SL CANCEL -> BLOCK",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_id": 301,
                "stop_loss_same_client_id": False,
                "stop_loss_operational_ambiguous": False,
            },
            stop_loss=None,
            take_profit=None,
            expected_stop_loss_action=IB_PROTECTION_ACTION_BLOCK,
            expected_take_profit_action=IB_PROTECTION_ACTION_BLOCK,
            expected_blocked=True,
        )

        _check_plan(
            title="Different-client SL KEEP and TP CREATE " "-> BLOCK",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_id": 401,
                "stop_loss_same_client_id": False,
                "stop_loss_operational_ambiguous": False,
            },
            stop_loss=1.1000,
            take_profit=1.2000,
            expected_stop_loss_action=IB_PROTECTION_ACTION_BLOCK,
            expected_take_profit_action=IB_PROTECTION_ACTION_BLOCK,
            expected_blocked=True,
        )

        _check_plan(
            title="Same-client SL KEEP and TP CREATE -> replacement pair",
            current_protection={
                "stop_loss": 1.1000,
                "stop_loss_order_id": 501,
                "stop_loss_client_id": 1,
                "stop_loss_perm_id": 6001,
                "stop_loss_same_client_id": True,
                "stop_loss_operational_ambiguous": False,
                "stop_loss_contract_object": contract_object,
                "stop_loss_order_object": stop_order_object,
                "stop_loss_oca_group": "",
                "stop_loss_oca_type": IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
            },
            stop_loss=1.1000,
            take_profit=1.2000,
            expected_stop_loss_action=IB_PROTECTION_ACTION_KEEP,
            expected_take_profit_action=IB_PROTECTION_ACTION_CREATE,
            expected_oca_relink_legs=[],
            expected_replacement_pair=("stop_loss", "take_profit"),
        )
        try:
            IBAdapter.build_position_sl_tp_modify_plan(
                current_protection=None,
                stop_loss=-1.0,
                take_profit=1.2000,
            )
        except ValueError:
            print("Negative price validation")
            print("  result=OK")
            print()
        else:
            raise AssertionError("Negative IB protection price was not rejected")

    except AssertionError as exc:
        print("IB_SL_TP_MODIFY_PLAN_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_MODIFY_PLAN_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
