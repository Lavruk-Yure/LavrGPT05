# run_ib_sl_tp_operation_wait_check.py
"""
Synthetic IB SL/TP operation wait check.

RoadMap88:
- не підключається до TWS;
- не викликає placeOrder/cancelOrder;
- перевіряє delayed callbacks;
- перевіряє mixed confirmed + timeout;
- перевіряє CANCEL через error code 202;
- перевіряє broker rejection.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import (  # noqa: E402
    IB_PROTECTION_ACTION_CANCEL,
    IB_PROTECTION_ACTION_CREATE,
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


def _emit_order_status(
    wrapper: Any,
    *,
    order_id: int,
    status: str,
) -> None:
    """
    Передати synthetic orderStatus callback.
    """
    wrapper.orderStatus(
        order_id=order_id,
        status=status,
        filled=0.0,
        remaining=1000.0,
        avg_fill_price=0.0,
        perm_id=order_id + 5000,
        parent_id=0,
        last_fill_price=0.0,
        client_id=2,
        why_held="",
        mkt_cap_price=0.0,
    )


def _emit_error(
    wrapper: Any,
    *,
    order_id: int,
    error_code: int,
    error_string: str,
) -> None:
    """
    Передати synthetic IB error callback.
    """
    wrapper.error(
        req_id=order_id,
        error_time=0,
        error_code=error_code,
        error_string=error_string,
        advanced_order_reject_json="",
    )


def _index_results_by_leg(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Побудувати індекс результатів за protection leg.
    """
    return {str(result["leg"]): result for result in results}


def main() -> int:
    """
    Перевірити очікування broker confirmations.
    """
    logger = logging.getLogger(__name__)

    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )

    wrapper = getattr(adapter, "_wrapper")

    wait_for_results = getattr(
        adapter,
        "_wait_for_sl_tp_operation_results",
    )

    try:
        # 1. Обидва delayed callbacks успішні.
        wrapper.start_sl_tp_operation(
            {
                301,
                302,
            }
        )

        submitted_timer = threading.Timer(
            0.05,
            _emit_order_status,
            kwargs={
                "wrapper": wrapper,
                "order_id": 301,
                "status": "Submitted",
            },
        )

        pre_submitted_timer = threading.Timer(
            0.10,
            _emit_order_status,
            kwargs={
                "wrapper": wrapper,
                "order_id": 302,
                "status": "PreSubmitted",
            },
        )

        submitted_timer.start()
        pre_submitted_timer.start()

        delayed_results = wait_for_results(
            execution_actions=[
                {
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "leg": "STOP_LOSS",
                    "order_id": 301,
                },
                {
                    "action": IB_PROTECTION_ACTION_MODIFY,
                    "leg": "TAKE_PROFIT",
                    "order_id": 302,
                },
            ],
            timeout=1.0,
        )

        submitted_timer.join()
        pre_submitted_timer.join()

        delayed_by_leg = _index_results_by_leg(delayed_results)

        print("Delayed confirmations")
        print("  STOP_LOSS=" f"{delayed_by_leg['STOP_LOSS']['status']}")
        print("  TAKE_PROFIT=" f"{delayed_by_leg['TAKE_PROFIT']['status']}")

        _require_equal(
            delayed_by_leg["STOP_LOSS"]["confirmed"],
            True,
            "Delayed Stop Loss confirmation",
        )
        _require_equal(
            delayed_by_leg["STOP_LOSS"]["status"],
            "Submitted",
            "Delayed Stop Loss status",
        )
        _require_equal(
            delayed_by_leg["STOP_LOSS"]["timeout"],
            False,
            "Delayed Stop Loss timeout",
        )
        _require_equal(
            delayed_by_leg["TAKE_PROFIT"]["confirmed"],
            True,
            "Delayed Take Profit confirmation",
        )
        _require_equal(
            delayed_by_leg["TAKE_PROFIT"]["status"],
            "PreSubmitted",
            "Delayed Take Profit status",
        )
        _require_equal(
            delayed_by_leg["TAKE_PROFIT"]["timeout"],
            False,
            "Delayed Take Profit timeout",
        )

        wrapper.clear_sl_tp_operation()

        # 2. Один leg підтверджений, другий отримує timeout.
        wrapper.start_sl_tp_operation(
            {
                401,
                402,
            }
        )

        partial_timer = threading.Timer(
            0.05,
            _emit_order_status,
            kwargs={
                "wrapper": wrapper,
                "order_id": 401,
                "status": "Submitted",
            },
        )

        partial_timer.start()

        timeout_results = wait_for_results(
            execution_actions=[
                {
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "leg": "STOP_LOSS",
                    "order_id": 401,
                },
                {
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "leg": "TAKE_PROFIT",
                    "order_id": 402,
                },
            ],
            timeout=0.20,
        )

        partial_timer.join()

        timeout_by_leg = _index_results_by_leg(timeout_results)

        print("Mixed confirmation and timeout")
        print("  STOP_LOSS=" f"{timeout_by_leg['STOP_LOSS']['status']}")
        print("  TAKE_PROFIT=" f"{timeout_by_leg['TAKE_PROFIT']['status']}")

        _require_equal(
            timeout_by_leg["STOP_LOSS"]["confirmed"],
            True,
            "Confirmed Stop Loss before timeout",
        )
        _require_equal(
            timeout_by_leg["STOP_LOSS"]["status"],
            "Submitted",
            "Confirmed Stop Loss status",
        )
        _require_equal(
            timeout_by_leg["STOP_LOSS"]["timeout"],
            False,
            "Confirmed Stop Loss timeout flag",
        )
        _require_equal(
            timeout_by_leg["TAKE_PROFIT"]["confirmed"],
            False,
            "Timed-out Take Profit confirmation",
        )
        _require_equal(
            timeout_by_leg["TAKE_PROFIT"]["terminal"],
            True,
            "Timed-out Take Profit terminal state",
        )
        _require_equal(
            timeout_by_leg["TAKE_PROFIT"]["status"],
            "TIMEOUT",
            "Timed-out Take Profit status",
        )
        _require_equal(
            timeout_by_leg["TAKE_PROFIT"]["timeout"],
            True,
            "Timed-out Take Profit flag",
        )

        wrapper.clear_sl_tp_operation()

        # 3. CANCEL підтверджений через IB error code 202.
        wrapper.start_sl_tp_operation(
            {
                501,
            }
        )

        cancel_timer = threading.Timer(
            0.05,
            _emit_error,
            kwargs={
                "wrapper": wrapper,
                "order_id": 501,
                "error_code": 202,
                "error_string": "Synthetic order cancelled",
            },
        )

        cancel_timer.start()

        cancel_results = wait_for_results(
            execution_actions=[
                {
                    "action": IB_PROTECTION_ACTION_CANCEL,
                    "leg": "STOP_LOSS",
                    "order_id": 501,
                }
            ],
            timeout=1.0,
        )

        cancel_timer.join()

        cancel_result = cancel_results[0]

        print("Cancellation confirmation")
        print(f"  status={cancel_result['status']}")

        _require_equal(
            cancel_result["confirmed"],
            True,
            "Cancel confirmation",
        )
        _require_equal(
            cancel_result["terminal"],
            True,
            "Cancel terminal state",
        )
        _require_equal(
            cancel_result["status"],
            "Cancelled",
            "Cancel status",
        )
        _require_equal(
            cancel_result["cancel_confirmed"],
            True,
            "Cancel confirmation flag",
        )
        _require_equal(
            cancel_result["timeout"],
            False,
            "Cancel timeout flag",
        )

        wrapper.clear_sl_tp_operation()

        # 4. Broker rejection завершує очікування без timeout.
        wrapper.start_sl_tp_operation(
            {
                601,
            }
        )

        rejection_timer = threading.Timer(
            0.05,
            _emit_error,
            kwargs={
                "wrapper": wrapper,
                "order_id": 601,
                "error_code": 201,
                "error_string": "Synthetic rejected order",
            },
        )

        rejection_timer.start()

        rejection_results = wait_for_results(
            execution_actions=[
                {
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "leg": "TAKE_PROFIT",
                    "order_id": 601,
                }
            ],
            timeout=1.0,
        )

        rejection_timer.join()

        rejection_result = rejection_results[0]

        print("Broker rejection")
        print(f"  status={rejection_result['status']}")

        _require_equal(
            rejection_result["confirmed"],
            False,
            "Rejected order confirmation",
        )
        _require_equal(
            rejection_result["terminal"],
            True,
            "Rejected order terminal state",
        )
        _require_equal(
            rejection_result["status"],
            "ERROR",
            "Rejected order status",
        )
        _require_equal(
            rejection_result["timeout"],
            False,
            "Rejected order timeout flag",
        )
        _require_equal(
            rejection_result["errors"],
            ["IB SL/TP order error 201: " "Synthetic rejected order"],
            "Rejected order errors",
        )

        wrapper.clear_sl_tp_operation()

    except AssertionError as exc:
        print("IB_SL_TP_OPERATION_WAIT_CHECK=FAILED")
        print(f"reason={exc}")
        return 1
    finally:
        wrapper.clear_sl_tp_operation()

    print("IB_SL_TP_OPERATION_WAIT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
