# run_ib_sl_tp_operation_confirmation_check.py
"""
Synthetic IB SL/TP broker-confirmation policy check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє KEEP/BLOCK/CREATE/MODIFY/CANCEL;
- перевіряє accepted, cancelled, rejected і waiting states.
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


def _run_case(
    *,
    name: str,
    action: str,
    leg: str,
    order_id: int | None,
    operation_snapshot: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """
    Перевірити один confirmation scenario.
    """
    result = IBAdapter.build_sl_tp_operation_action_result(
        action=action,
        leg=leg,
        order_id=order_id,
        operation_snapshot=operation_snapshot,
    )

    print(name)
    print(
        "  "
        f"action={result['action']} | "
        f"leg={result['leg']} | "
        f"order_id={result['order_id']} | "
        f"confirmed={result['confirmed']} | "
        f"terminal={result['terminal']} | "
        f"status={result['status']}"
    )

    for key, expected_value in expected.items():
        _require_equal(
            result.get(key),
            expected_value,
            f"{name}: {key}",
        )

    print("  result=OK")
    print()


def main() -> int:
    """
    Перевірити confirmation policy для всіх основних actions.
    """
    try:
        _run_case(
            name="KEEP -> confirmed without callback",
            action=IB_PROTECTION_ACTION_KEEP,
            leg="STOP_LOSS",
            order_id=101,
            operation_snapshot={},
            expected={
                "confirmed": True,
                "terminal": True,
                "status": "KEEP",
                "callback_received": False,
            },
        )

        _run_case(
            name="BLOCK -> terminal failure",
            action=IB_PROTECTION_ACTION_BLOCK,
            leg="TAKE_PROFIT",
            order_id=None,
            operation_snapshot={},
            expected={
                "confirmed": False,
                "terminal": True,
                "status": "BLOCKED",
            },
        )

        _run_case(
            name="CREATE + Submitted -> confirmed",
            action=IB_PROTECTION_ACTION_CREATE,
            leg="STOP_LOSS",
            order_id=201,
            operation_snapshot={
                "statuses": {
                    201: {
                        "status": "Submitted",
                    }
                }
            },
            expected={
                "confirmed": True,
                "terminal": True,
                "status": "Submitted",
                "callback_received": True,
                "status_received": True,
            },
        )

        _run_case(
            name="MODIFY + PreSubmitted openOrder -> confirmed",
            action=IB_PROTECTION_ACTION_MODIFY,
            leg="TAKE_PROFIT",
            order_id=202,
            operation_snapshot={
                "open_orders": {
                    202: {
                        "status": "PreSubmitted",
                    }
                }
            },
            expected={
                "confirmed": True,
                "terminal": True,
                "status": "PreSubmitted",
                "callback_received": True,
                "open_order_received": True,
            },
        )

        _run_case(
            name="CANCEL + ApiCancelled -> confirmed",
            action=IB_PROTECTION_ACTION_CANCEL,
            leg="STOP_LOSS",
            order_id=203,
            operation_snapshot={
                "statuses": {
                    203: {
                        "status": "ApiCancelled",
                    }
                },
                "cancelled_order_ids": {
                    203,
                },
            },
            expected={
                "confirmed": True,
                "terminal": True,
                "status": "ApiCancelled",
                "cancel_confirmed": True,
            },
        )

        _run_case(
            name="CANCEL + error 202 state -> confirmed",
            action=IB_PROTECTION_ACTION_CANCEL,
            leg="TAKE_PROFIT",
            order_id=204,
            operation_snapshot={
                "cancelled_order_ids": {
                    204,
                }
            },
            expected={
                "confirmed": True,
                "terminal": True,
                "status": "Cancelled",
                "cancel_confirmed": True,
                "errors": [],
            },
        )

        _run_case(
            name="CREATE + broker rejection -> terminal failure",
            action=IB_PROTECTION_ACTION_CREATE,
            leg="STOP_LOSS",
            order_id=205,
            operation_snapshot={
                "errors": {
                    205: ["IB SL/TP order error 201: " "Synthetic rejected order"]
                }
            },
            expected={
                "confirmed": False,
                "terminal": True,
                "status": "ERROR",
                "callback_received": True,
                "errors": ["IB SL/TP order error 201: " "Synthetic rejected order"],
            },
        )

        _run_case(
            name="MODIFY + Inactive -> terminal failure",
            action=IB_PROTECTION_ACTION_MODIFY,
            leg="TAKE_PROFIT",
            order_id=206,
            operation_snapshot={
                "statuses": {
                    206: {
                        "status": "Inactive",
                    }
                }
            },
            expected={
                "confirmed": False,
                "terminal": True,
                "status": "Inactive",
                "callback_received": True,
            },
        )

        _run_case(
            name="CREATE + PendingSubmit -> waiting",
            action=IB_PROTECTION_ACTION_CREATE,
            leg="STOP_LOSS",
            order_id=207,
            operation_snapshot={
                "statuses": {
                    207: {
                        "status": "PendingSubmit",
                    }
                }
            },
            expected={
                "confirmed": False,
                "terminal": False,
                "status": "PendingSubmit",
                "callback_received": True,
            },
        )

        _run_case(
            name="CANCEL + Submitted -> waiting",
            action=IB_PROTECTION_ACTION_CANCEL,
            leg="TAKE_PROFIT",
            order_id=208,
            operation_snapshot={
                "statuses": {
                    208: {
                        "status": "Submitted",
                    }
                }
            },
            expected={
                "confirmed": False,
                "terminal": False,
                "status": "Submitted",
                "callback_received": True,
                "cancel_confirmed": False,
            },
        )

        _run_case(
            name="CREATE without order id -> terminal failure",
            action=IB_PROTECTION_ACTION_CREATE,
            leg="STOP_LOSS",
            order_id=None,
            operation_snapshot={},
            expected={
                "confirmed": False,
                "terminal": True,
                "status": "ORDER_ID_MISSING",
                "callback_received": False,
            },
        )

    except AssertionError as exc:
        print("IB_SL_TP_OPERATION_CONFIRMATION_CHECK=FAILED")
        print(f"reason={exc}")
        return 1

    print("IB_SL_TP_OPERATION_CONFIRMATION_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
