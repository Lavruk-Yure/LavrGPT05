"""RoadMap90 virtual-leg OCA critical-window execution guard check."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from ibapi.client import EClient

from engine.ib_adapter import IBAdapter
from engine.runtime_constants import IB_SL_TP_OPERATION_TIMEOUT_SECONDS

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "EURUSD"
STOP_LOSS_ID = 125
TAKE_PROFIT_ID = 124


class SyntheticIBAdapter(IBAdapter):
    """Expose the pure execution guard without a live IB connection."""

    def __init__(self, snapshots: list[list[dict[str, Any]]]) -> None:
        super().__init__(
            host="127.0.0.1",
            port=7497,
            client_id=1,
            logger=logging.getLogger(__name__),
        )
        self._synthetic_snapshots = [deepcopy(snapshot) for snapshot in snapshots]
        self.execution_requests = 0

    def _request_virtual_leg_execution_evidence(
        self,
        account_ids: list[str],
    ) -> list[dict[str, Any]]:
        if account_ids != [ACCOUNT_ID]:
            raise AssertionError("Execution guard account filter differs")

        self.execution_requests += 1

        if not self._synthetic_snapshots:
            raise AssertionError("Execution guard requested excess evidence")

        return self._synthetic_snapshots.pop(0)

    def build_execution_guard(self) -> dict[str, Any]:
        return self._build_virtual_leg_replacement_execution_guard(
            account_id=ACCOUNT_ID,
            symbol_name=SYMBOL_NAME,
            child_order_ids=(STOP_LOSS_ID, TAKE_PROFIT_ID),
        )

    def validate_execution_guard(
        self,
        guard: dict[str, Any],
    ) -> dict[str, Any]:
        return self._validate_virtual_leg_replacement_execution_guard(guard)


class _DummyClient(EClient):
    def __init__(self, wrapper: object) -> None:
        super().__init__(wrapper)
        self.calls: list[tuple[str, int]] = []

    def placeOrder(
        self,
        order_id: int,
        contract: object,
        order: object,
    ) -> None:
        del contract, order
        self.calls.append(("placeOrder", order_id))

    def cancelOrder(
        self,
        order_id: int,
        cancel: object,
    ) -> None:
        del cancel
        self.calls.append(("cancelOrder", order_id))


class _GuardBranchAdapter(IBAdapter):
    def __init__(self) -> None:
        super().__init__(
            host="127.0.0.1",
            port=7497,
            client_id=1,
            logger=logging.getLogger(__name__),
        )
        self._client = _DummyClient(self._wrapper)
        self.guard_calls = 0

    def execute_survivor_guard_branch(
        self,
        package: dict[str, Any],
    ) -> dict[str, Any]:
        return self._execute_sl_tp_replacement_survivor_operation(
            execution_package=package
        )

    def execute_pair_guard_branch(
        self,
        package: dict[str, Any],
    ) -> dict[str, Any]:
        return self._execute_sl_tp_replacement_pair_operation(execution_package=package)

    def _wait_for_sl_tp_replacement_staged(
        self,
        *,
        order_id: int,
        leg: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        del timeout
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

    def _wait_for_sl_tp_operation_results(
        self,
        *,
        execution_actions: list[dict[str, Any]],
        timeout: float = IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    ) -> list[dict[str, Any]]:
        del timeout
        return [
            {
                "action": action["action"],
                "leg": action["leg"],
                "order_id": action["order_id"],
                "confirmed": True,
                "terminal": True,
                "status": "CONFIRMED",
                "timeout": False,
                "errors": [],
            }
            for action in execution_actions
        ]

    def _validate_virtual_leg_replacement_execution_guard(
        self,
        guard: dict[str, Any],
    ) -> dict[str, Any]:
        if not guard.get("confirmed_for_test"):
            raise AssertionError("Virtual-leg guard package differs")

        self.guard_calls += 1
        return {"confirmed": True}

    def _request_positions_snapshot_for_execution(self) -> list[dict]:
        raise AssertionError("Virtual-leg branch used broker net position")


def _check_execution_guard_branches() -> tuple[int, int]:
    survivor_adapter = _GuardBranchAdapter()
    survivor_result = survivor_adapter.execute_survivor_guard_branch(
        {
            "position_id": "IB:DUM513747:EURUSD",
            "position_side": "SELL",
            "position_volume": 1000.0,
            "replacement_order_id": 203,
            "old_survivor_order_id": 201,
            "old_cancel_order_id": 202,
            "operation_order_ids": {201, 202, 203},
            "replacement_contract_object": object(),
            "replacement_staged_order_object": object(),
            "replacement_active_order_object": object(),
            "replacement_survivor_leg": "stop_loss",
            "replacement_cancel_leg": "take_profit",
            "virtual_leg_execution_guard": {"confirmed_for_test": True},
        }
    )

    if not survivor_result["execution_guard_result"]["confirmed"]:
        raise AssertionError("Survivor execution guard result differs")

    pair_adapter = _GuardBranchAdapter()
    pair_result = pair_adapter.execute_pair_guard_branch(
        {
            "position_id": "IB:DUM513747:EURUSD",
            "position_side": "SELL",
            "position_volume": 1000.0,
            "old_survivor_order_id": 301,
            "create_order_ids": {
                "stop_loss": 302,
                "take_profit": 303,
            },
            "operation_order_ids": {301, 302, 303},
            "replacement_contract_object": object(),
            "replacement_staged_orders": {
                "stop_loss": object(),
                "take_profit": object(),
            },
            "replacement_active_orders": {
                "stop_loss": object(),
                "take_profit": object(),
            },
            "virtual_leg_execution_guard": {"confirmed_for_test": True},
        }
    )

    if not pair_result["execution_guard_result"]["confirmed"]:
        raise AssertionError("Pair execution guard result differs")

    return survivor_adapter.guard_calls, pair_adapter.guard_calls


def _execution(
    *,
    order_id: int,
    symbol: str = "EUR",
    currency: str = "USD",
    side: str = "SLD",
    shares: float = 1000.0,
    price: float = 1.1426,
    time_text: str = "20260717 13:07:10 US/Eastern",
) -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": currency,
        "sec_type": "CASH",
        "side": side,
        "shares": shares,
        "price": price,
        "time": time_text,
        "order_id": order_id,
        "perm_id": order_id + 10000,
    }


def _run_allowed_case(
    fresh_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = [_execution(order_id=123)]
    adapter = SyntheticIBAdapter([baseline, fresh_rows])
    guard = adapter.build_execution_guard()
    result = adapter.validate_execution_guard(guard)

    if adapter.execution_requests != 2:
        raise AssertionError("Execution guard request count differs")

    return result


def _require_blocked(
    fresh_rows: list[dict[str, Any]],
    expected_text: str,
) -> None:
    baseline = [_execution(order_id=123)]
    adapter = SyntheticIBAdapter([baseline, fresh_rows])
    guard = adapter.build_execution_guard()

    try:
        adapter.validate_execution_guard(guard)
    except RuntimeError as error:
        if expected_text not in str(error):
            raise AssertionError(
                "Execution guard error text differs: " f"{error}"
            ) from error
    else:
        raise AssertionError("Unsafe execution guard case was not blocked")


def main() -> int:
    baseline = [_execution(order_id=123)]
    stable_result = _run_allowed_case(deepcopy(baseline))
    unrelated_result = _run_allowed_case(
        [
            *deepcopy(baseline),
            _execution(
                order_id=900,
                symbol="GBP",
                currency="USD",
                price=1.345,
            ),
        ]
    )
    _require_blocked(
        [
            *deepcopy(baseline),
            _execution(
                order_id=STOP_LOSS_ID,
                side="BOT",
                price=1.15,
                time_text="20260717 20:30:01 US/Eastern",
            ),
        ],
        "protective execution occurred",
    )
    _require_blocked(
        [
            *deepcopy(baseline),
            _execution(
                order_id=999,
                side="BOT",
                price=1.144,
                time_text="20260717 20:30:02 US/Eastern",
            ),
        ],
        "unexpected same-contract execution occurred",
    )
    survivor_guard_calls, pair_guard_calls = _check_execution_guard_branches()

    print("IB virtual-leg OCA execution guard result")
    print("  stable_guard_confirmed=" f"{stable_result['confirmed']}")
    print("  unrelated_symbol_ignored=" f"{unrelated_result['confirmed']}")
    print("  protective_execution_blocked=True")
    print("  unknown_execution_blocked=True")
    print(f"  survivor_guard_calls={survivor_guard_calls}")
    print(f"  pair_guard_calls={pair_guard_calls}")
    print("  broker_net_position_guard_bypassed=True")
    print("IB_VIRTUAL_LEG_OCA_EXECUTION_GUARD_CHECK=OK")
    return 0
