"""Synthetic IB virtual-leg single protective order CREATE regression check."""

from __future__ import annotations

import logging
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from ibapi.contract import Contract
from ibapi.order import Order

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_adapter import IBAdapter  # noqa: E402

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "EURUSD"
POSITION_ID = f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}"
POSITION_UID = "5adf3514-0000-4000-8000-000000000001"
PARENT_ORDER_ID = 500
EXISTING_STOP_LOSS_ORDER_ID = 501
UNMAPPED_TAKE_PROFIT_ORDER_ID = 502
STOP_LOSS = 1.1427
TAKE_PROFIT = 1.1493
OLD_OCA_GROUP = "LGE_SLTP_1_501_502"


class SyntheticIBAdapter(IBAdapter):
    """Exercise virtual-leg guard routing without broker dispatch."""

    def __init__(self, open_orders: list[dict[str, Any]] | None = None) -> None:
        super().__init__(
            host="127.0.0.1",
            port=7497,
            client_id=1,
            logger=logging.getLogger(__name__),
        )
        self._connected = True
        self._open_orders = deepcopy(open_orders or [])
        self.execution_evidence_calls = 0
        self.execution_contexts: list[dict[str, Any]] = []

    def _request_open_orders_snapshot(
        self,
        include_objects: bool = False,
        require_complete: bool = False,
    ) -> list[dict[str, Any]]:
        if not include_objects or not require_complete:
            raise AssertionError("Virtual-leg Modify requested a weak order snapshot")

        return deepcopy(self._open_orders)

    def _request_virtual_leg_execution_evidence(
        self,
        account_ids: list[str],
    ) -> list[dict[str, Any]]:
        if account_ids != [ACCOUNT_ID]:
            raise AssertionError("Virtual-leg guard account filter differs")

        self.execution_evidence_calls += 1
        return []

    def _execute_sl_tp_modify_from_context(
        self,
        position_context: dict[str, Any],
        current_protection: dict[str, Any],
        stop_loss_price: float | None,
        take_profit_price: float | None,
        virtual_leg_execution_guard: dict[str, Any] | None = None,
        order_ref: str = "",
    ) -> dict[str, Any]:
        plan = self.build_position_sl_tp_modify_plan(
            current_protection=current_protection,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
        )
        context = {
            "position_context": dict(position_context),
            "current_protection": dict(current_protection),
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "guard": dict(virtual_leg_execution_guard or {}),
            "order_ref": order_ref,
            "plan": dict(plan),
        }
        self.execution_contexts.append(context)
        return context


def _contract() -> Contract:
    contract = Contract()
    contract.symbol = "EUR"
    contract.currency = "USD"
    contract.secType = "CASH"
    contract.exchange = "IDEALPRO"
    return contract


def _stop_loss_row(*, oca_group: str = "") -> dict[str, Any]:
    order = Order()
    order.account = ACCOUNT_ID
    order.action = "SELL"
    order.orderType = "STP"
    order.totalQuantity = 1000.0
    order.auxPrice = STOP_LOSS
    order.lmtPrice = 0.0
    order.ocaGroup = oca_group
    order.ocaType = 1 if oca_group else 0
    return {
        "order_id": EXISTING_STOP_LOSS_ORDER_ID,
        "parent_id": PARENT_ORDER_ID,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": POSITION_ID,
        "action": "SELL",
        "order_type": "STP",
        "total_quantity": 1000.0,
        "lmt_price": 0.0,
        "aux_price": STOP_LOSS,
        "client_id": 1,
        "perm_id": 1501,
        "same_client_id": True,
        "oca_group": oca_group,
        "oca_type": 1 if oca_group else 0,
        "status": "Submitted",
        "contract_object": _contract(),
        "order_object": order,
    }


def _unmapped_take_profit_row() -> dict[str, Any]:
    order = Order()
    order.account = ACCOUNT_ID
    order.action = "SELL"
    order.orderType = "LMT"
    order.totalQuantity = 1000.0
    order.auxPrice = 0.0
    order.lmtPrice = TAKE_PROFIT
    order.ocaGroup = OLD_OCA_GROUP
    order.ocaType = 1
    return {
        "order_id": UNMAPPED_TAKE_PROFIT_ORDER_ID,
        "parent_id": PARENT_ORDER_ID,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": POSITION_ID,
        "action": "SELL",
        "order_type": "LMT",
        "total_quantity": 1000.0,
        "lmt_price": TAKE_PROFIT,
        "aux_price": 0.0,
        "client_id": 1,
        "perm_id": 1502,
        "same_client_id": True,
        "oca_group": OLD_OCA_GROUP,
        "oca_type": 1,
        "status": "Submitted",
        "contract_object": _contract(),
        "order_object": order,
    }


def _modify(
    adapter: SyntheticIBAdapter,
    *,
    stop_loss_order_id: int | None,
    take_profit_order_id: int | None,
    stop_loss: float | None,
    take_profit: float | None,
    current_oca_group: str = "",
) -> dict[str, Any]:
    return adapter.modify_virtual_position_leg_sl_tp(
        position_uid=POSITION_UID,
        position_id=POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name=SYMBOL_NAME,
        position_side="BUY",
        position_volume=1000.0,
        parent_order_id=PARENT_ORDER_ID,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        current_oca_group=current_oca_group,
        stop_loss=stop_loss,
        take_profit=take_profit,
        order_ref="[LGE:M] Single protection regression | SLTP_MODIFY",
    )


def main() -> int:
    stop_only_adapter = SyntheticIBAdapter()
    stop_only_result = _modify(
        stop_only_adapter,
        stop_loss_order_id=None,
        take_profit_order_id=None,
        stop_loss=STOP_LOSS,
        take_profit=None,
    )
    stop_only_plan = stop_only_result["plan"]

    if stop_only_plan["stop_loss_action"] != "CREATE":
        raise AssertionError("Missing Stop Loss was not planned as CREATE")

    if stop_only_plan["take_profit_action"] != "KEEP":
        raise AssertionError("Absent Take Profit was not retained as absent")

    if stop_only_result["guard"]:
        raise AssertionError("Guard was created without existing child orders")

    if stop_only_adapter.execution_evidence_calls != 0:
        raise AssertionError("Guard evidence was requested without child orders")

    take_only_adapter = SyntheticIBAdapter()
    take_only_result = _modify(
        take_only_adapter,
        stop_loss_order_id=None,
        take_profit_order_id=None,
        stop_loss=None,
        take_profit=TAKE_PROFIT,
    )
    take_only_plan = take_only_result["plan"]

    if take_only_plan["stop_loss_action"] != "KEEP":
        raise AssertionError("Absent Stop Loss was not retained as absent")

    if take_only_plan["take_profit_action"] != "CREATE":
        raise AssertionError("Missing Take Profit was not planned as CREATE")

    if take_only_result["guard"]:
        raise AssertionError("Guard was created without existing child orders")

    if take_only_adapter.execution_evidence_calls != 0:
        raise AssertionError("Guard evidence was requested without child orders")

    pair_adapter = SyntheticIBAdapter([_stop_loss_row()])
    pair_result = _modify(
        pair_adapter,
        stop_loss_order_id=EXISTING_STOP_LOSS_ORDER_ID,
        take_profit_order_id=None,
        stop_loss=STOP_LOSS,
        take_profit=TAKE_PROFIT,
    )
    pair_plan = pair_result["plan"]

    if pair_plan["stop_loss_action"] != "KEEP":
        raise AssertionError("Existing standalone Stop Loss action differs")

    if pair_plan["take_profit_action"] != "CREATE":
        raise AssertionError("Second protective order was not planned as CREATE")

    if not pair_result["guard"]:
        raise AssertionError("Existing child replacement guard was bypassed")

    if pair_adapter.execution_evidence_calls != 1:
        raise AssertionError("Existing child guard evidence request count differs")

    orphan_adapter = SyntheticIBAdapter(
        [_stop_loss_row(oca_group=OLD_OCA_GROUP)]
    )
    orphan_result = _modify(
        orphan_adapter,
        stop_loss_order_id=EXISTING_STOP_LOSS_ORDER_ID,
        take_profit_order_id=None,
        current_oca_group=OLD_OCA_GROUP,
        stop_loss=STOP_LOSS,
        take_profit=TAKE_PROFIT,
    )
    orphan_plan = orphan_result["plan"]

    if orphan_plan["blocked"]:
        raise AssertionError("Orphaned OCA survivor was blocked")

    if not orphan_plan.get("stop_loss_oca_group_is_orphaned"):
        raise AssertionError("Orphaned OCA survivor was not identified")

    if orphan_plan["replacement_pair_survivor_leg"] != "stop_loss":
        raise AssertionError("Orphaned OCA survivor replacement route differs")

    if orphan_adapter.execution_evidence_calls != 1:
        raise AssertionError("Orphaned OCA survivor guard request count differs")

    unsafe_adapter = SyntheticIBAdapter(
        [
            _stop_loss_row(oca_group=OLD_OCA_GROUP),
            _unmapped_take_profit_row(),
        ]
    )
    unsafe_result = _modify(
        unsafe_adapter,
        stop_loss_order_id=EXISTING_STOP_LOSS_ORDER_ID,
        take_profit_order_id=None,
        current_oca_group=OLD_OCA_GROUP,
        stop_loss=STOP_LOSS,
        take_profit=TAKE_PROFIT,
    )
    unsafe_plan = unsafe_result["plan"]

    if not unsafe_plan["blocked"]:
        raise AssertionError("Active unmapped OCA peer was not blocked")

    expected_flag = "replacement_pair_stop_loss_not_standalone"

    if expected_flag not in unsafe_plan["blocked_flags"]:
        raise AssertionError("Active unmapped OCA peer block reason differs")

    print("IB virtual-leg single protection CREATE result")
    print("  no_children_add_stop_loss=CREATE")
    print("  no_children_add_take_profit=CREATE")
    print("  no_children_guard_bypassed=True")
    print("  existing_child_pair_guard_preserved=True")
    print("  orphaned_oca_survivor_replaced=True")
    print("  active_unmapped_oca_peer_blocked=True")
    print("IB_VIRTUAL_LEG_SINGLE_PROTECTION_CREATE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
