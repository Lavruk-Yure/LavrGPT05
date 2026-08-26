# run_ib_sl_tp_broker_operation_check.py
"""
Synthetic IB SL/TP broker-operation orchestration check.

RoadMap88:
- не підключається до TWS;
- dispatcher замінено mock;
- перевіряє dispatch -> callback wait -> result;
- перевіряє partial timeout;
- перевіряє broker rejection;
- перевіряє очищення operation state;
- перевіряє order-id mismatch до broker dispatch.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

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


def _build_action(
    *,
    leg: str,
    action: str,
    order_id: int,
) -> dict[str, Any]:
    """
    Побудувати synthetic execution action.
    """
    return {
        "leg": leg,
        "action": action,
        "order_id": order_id,
        "broker_call_required": True,
    }


def _build_payload(
    *,
    leg: str,
    action: str,
    order_id: int,
) -> dict[str, Any]:
    """
    Побудувати synthetic broker payload.

    Contract і Order тут не потрібні, бо dispatcher замінено mock.
    """
    return {
        "leg": leg,
        "action": action,
        "order_id": order_id,
        "broker_call_required": True,
    }


def _require_operation_state_cleared(
    wrapper: Any,
    message: str,
) -> None:
    """
    Перевірити очищення callback-operation state.
    """
    snapshot = wrapper.get_sl_tp_operation_snapshot()

    _require_equal(
        snapshot["order_ids"],
        set(),
        f"{message}: order ids",
    )
    _require_equal(
        snapshot["open_orders"],
        {},
        f"{message}: open orders",
    )
    _require_equal(
        snapshot["statuses"],
        {},
        f"{message}: statuses",
    )
    _require_equal(
        snapshot["cancelled_order_ids"],
        set(),
        f"{message}: cancelled ids",
    )
    _require_equal(
        snapshot["errors"],
        {},
        f"{message}: errors",
    )


def main() -> int:
    """
    Перевірити повну orchestration broker operation.
    """
    logger = logging.getLogger(__name__)

    adapter = IBAdapter(
        host="127.0.0.1",
        port=7497,
        client_id=2,
        logger=logger,
    )

    wrapper = getattr(adapter, "_wrapper")

    execute_operation = getattr(
        adapter,
        "_execute_sl_tp_broker_operation",
    )

    try:
        setattr(adapter, "_connected", True)

        # 1. Два успішні broker confirmations.
        success_actions = [
            _build_action(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2201,
            ),
            _build_action(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2202,
            ),
        ]

        success_payloads = [
            _build_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2201,
            ),
            _build_payload(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2202,
            ),
        ]

        def dispatch_success(
            *,
            broker_payloads: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            _require_equal(
                broker_payloads,
                success_payloads,
                "Success dispatcher payloads",
            )

            _emit_order_status(
                wrapper,
                order_id=2201,
                status="Submitted",
            )
            _emit_order_status(
                wrapper,
                order_id=2202,
                status="PreSubmitted",
            )

            return [
                {
                    "call": "placeOrder",
                    "leg": "STOP_LOSS",
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "order_id": 2201,
                },
                {
                    "call": "placeOrder",
                    "leg": "TAKE_PROFIT",
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "order_id": 2202,
                },
            ]

        with patch.object(
            adapter,
            "_dispatch_sl_tp_broker_payloads",
            side_effect=dispatch_success,
        ) as dispatch_mock:
            success_result = execute_operation(
                execution_actions=success_actions,
                broker_payloads=success_payloads,
                operation_order_ids={
                    2201,
                    2202,
                },
                timeout=1.0,
            )

        print("Successful broker operation")
        print("  confirmed=" f"{success_result['confirmed']}")
        print(
            "  statuses="
            f"{[
                row['status']
                for row in success_result['action_results']
            ]}"
        )

        _require_equal(
            dispatch_mock.call_count,
            1,
            "Success dispatcher call count",
        )
        _require_equal(
            success_result["executed"],
            True,
            "Success executed",
        )
        _require_equal(
            success_result["confirmed"],
            True,
            "Success confirmed",
        )
        _require_equal(
            success_result["terminal"],
            True,
            "Success terminal",
        )
        _require_equal(
            success_result["timeout"],
            False,
            "Success timeout",
        )
        _require_equal(
            success_result["failed_legs"],
            [],
            "Success failed legs",
        )
        _require_equal(
            success_result["operation_order_ids"],
            {
                2201,
                2202,
            },
            "Success operation order ids",
        )
        _require_equal(
            set(success_result["operation_snapshot"]["statuses"]),
            {
                2201,
                2202,
            },
            "Success operation snapshot statuses",
        )

        _require_operation_state_cleared(
            wrapper,
            "Success cleanup",
        )

        print("  result=OK")
        print()

        # 2. Один leg підтверджений, другий TIMEOUT.
        timeout_actions = [
            _build_action(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_MODIFY,
                order_id=2301,
            ),
            _build_action(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2302,
            ),
        ]

        timeout_payloads = [
            _build_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_MODIFY,
                order_id=2301,
            ),
            _build_payload(
                leg="TAKE_PROFIT",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2302,
            ),
        ]

        def dispatch_partial(
            *,
            broker_payloads: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            _require_equal(
                broker_payloads,
                timeout_payloads,
                "Timeout dispatcher payloads",
            )

            _emit_order_status(
                wrapper,
                order_id=2301,
                status="Submitted",
            )

            return [
                {
                    "call": "placeOrder",
                    "leg": "STOP_LOSS",
                    "action": IB_PROTECTION_ACTION_MODIFY,
                    "order_id": 2301,
                },
                {
                    "call": "placeOrder",
                    "leg": "TAKE_PROFIT",
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "order_id": 2302,
                },
            ]

        with patch.object(
            adapter,
            "_dispatch_sl_tp_broker_payloads",
            side_effect=dispatch_partial,
        ):
            timeout_result = execute_operation(
                execution_actions=timeout_actions,
                broker_payloads=timeout_payloads,
                operation_order_ids={
                    2301,
                    2302,
                },
                timeout=0.05,
            )

        timeout_by_leg = {
            str(row["leg"]): row for row in timeout_result["action_results"]
        }

        print("Partial confirmation and timeout")
        print("  STOP_LOSS=" f"{timeout_by_leg['STOP_LOSS']['status']}")
        print("  TAKE_PROFIT=" f"{timeout_by_leg['TAKE_PROFIT']['status']}")

        _require_equal(
            timeout_result["executed"],
            True,
            "Timeout executed",
        )
        _require_equal(
            timeout_result["confirmed"],
            False,
            "Timeout confirmed",
        )
        _require_equal(
            timeout_result["terminal"],
            True,
            "Timeout terminal",
        )
        _require_equal(
            timeout_result["timeout"],
            True,
            "Timeout flag",
        )
        _require_equal(
            timeout_result["failed_legs"],
            [
                "TAKE_PROFIT",
            ],
            "Timeout failed legs",
        )
        _require_equal(
            timeout_by_leg["STOP_LOSS"]["status"],
            "Submitted",
            "Timeout Stop Loss status",
        )
        _require_equal(
            timeout_by_leg["TAKE_PROFIT"]["status"],
            "TIMEOUT",
            "Timeout Take Profit status",
        )

        _require_operation_state_cleared(
            wrapper,
            "Timeout cleanup",
        )

        print("  result=OK")
        print()

        # 3. Broker rejection.
        rejection_actions = [
            _build_action(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2401,
            )
        ]

        rejection_payloads = [
            _build_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2401,
            )
        ]

        def dispatch_rejection(
            *,
            broker_payloads: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            _require_equal(
                broker_payloads,
                rejection_payloads,
                "Rejection dispatcher payloads",
            )

            _emit_error(
                wrapper,
                order_id=2401,
                error_code=201,
                error_string="Synthetic rejected order",
            )

            return [
                {
                    "call": "placeOrder",
                    "leg": "STOP_LOSS",
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "order_id": 2401,
                }
            ]

        with patch.object(
            adapter,
            "_dispatch_sl_tp_broker_payloads",
            side_effect=dispatch_rejection,
        ):
            rejection_result = execute_operation(
                execution_actions=rejection_actions,
                broker_payloads=rejection_payloads,
                operation_order_ids={
                    2401,
                },
                timeout=1.0,
            )

        rejection_action_result = rejection_result["action_results"][0]

        print("Broker rejection operation")
        print("  status=" f"{rejection_action_result['status']}")

        _require_equal(
            rejection_result["executed"],
            True,
            "Rejection executed",
        )
        _require_equal(
            rejection_result["confirmed"],
            False,
            "Rejection confirmed",
        )
        _require_equal(
            rejection_result["terminal"],
            True,
            "Rejection terminal",
        )
        _require_equal(
            rejection_result["timeout"],
            False,
            "Rejection timeout",
        )
        _require_equal(
            rejection_result["failed_legs"],
            [
                "STOP_LOSS",
            ],
            "Rejection failed legs",
        )
        _require_equal(
            rejection_action_result["status"],
            "ERROR",
            "Rejection status",
        )
        _require_equal(
            rejection_action_result["errors"],
            ["IB SL/TP order error 201: " "Synthetic rejected order"],
            "Rejection errors",
        )

        _require_operation_state_cleared(
            wrapper,
            "Rejection cleanup",
        )

        print("  result=OK")
        print()

        # 4. Dispatcher exception:
        #    operation state має очиститися через finally.
        dispatch_failure_actions = [
            _build_action(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_MODIFY,
                order_id=2501,
            )
        ]

        dispatch_failure_payloads = [
            _build_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_MODIFY,
                order_id=2501,
            )
        ]

        with patch.object(
            adapter,
            "_dispatch_sl_tp_broker_payloads",
            side_effect=RuntimeError("Synthetic dispatch failure"),
        ) as dispatch_mock:
            try:
                execute_operation(
                    execution_actions=dispatch_failure_actions,
                    broker_payloads=dispatch_failure_payloads,
                    operation_order_ids={
                        2501,
                    },
                    timeout=1.0,
                )
            except RuntimeError as exc:
                error_text = str(exc)
            else:
                raise AssertionError("Dispatcher exception must propagate")

        print("Dispatcher exception cleanup")
        print(f"  error={error_text}")

        _require_equal(
            error_text,
            "Synthetic dispatch failure",
            "Dispatcher exception text",
        )
        _require_equal(
            dispatch_mock.call_count,
            1,
            "Failed dispatcher call count",
        )

        _require_operation_state_cleared(
            wrapper,
            "Dispatcher exception cleanup",
        )

        print("  result=OK")
        print()

        # 5. order-id mismatch:
        #    dispatcher не повинен викликатися.
        mismatch_actions = [
            _build_action(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2601,
            )
        ]

        mismatch_payloads = [
            _build_payload(
                leg="STOP_LOSS",
                action=IB_PROTECTION_ACTION_CREATE,
                order_id=2601,
            )
        ]

        with patch.object(
            adapter,
            "_dispatch_sl_tp_broker_payloads",
        ) as dispatch_mock:
            try:
                execute_operation(
                    execution_actions=mismatch_actions,
                    broker_payloads=mismatch_payloads,
                    operation_order_ids={
                        2602,
                    },
                    timeout=1.0,
                )
            except RuntimeError as exc:
                error_text = str(exc)
            else:
                raise AssertionError("Order-id mismatch must raise RuntimeError")

        print("Operation order-id mismatch")
        print(f"  error={error_text}")

        _require(
            "execution action order ids mismatch" in error_text,
            "Unexpected order-id mismatch error",
        )
        _require_equal(
            dispatch_mock.call_count,
            0,
            "Mismatch dispatcher call count",
        )

        _require_operation_state_cleared(
            wrapper,
            "Mismatch state",
        )

        print("  result=OK")
        print()

    except AssertionError as exc:
        print("IB_SL_TP_BROKER_OPERATION_CHECK=FAILED")
        print(f"reason={exc}")
        return 1
    finally:
        wrapper.clear_sl_tp_operation()

    print("IB_SL_TP_BROKER_OPERATION_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
