"""
RuntimeEngine exact IB virtual-leg SL/TP Modify persistence check.

RoadMap90:
- select one LGE virtual leg by position_uid;
- reuse the RoadMap89 broker operation path;
- modify only that leg protective pair;
- persist the reconciled prices without changing the second leg.
"""

from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "EURUSD"
CURRENT_CLIENT_ID = 1
TARGET_PARENT_ID = 301
TARGET_TP_ID = 302
TARGET_SL_ID = 303
OTHER_PARENT_ID = 304
OTHER_TP_ID = 305
OTHER_SL_ID = 306
TARGET_NEW_SL = 1.1425
TARGET_NEW_TP = 1.1505
TARGET_COMMENT = "RoadMap90 virtual-leg modify"
TARGET_BROKER_COMMENT = f"[LGE:M] {TARGET_COMMENT}"
TARGET_MODIFY_ORDER_REF = f"{TARGET_BROKER_COMMENT} | SLTP_MODIFY"


class DummyIBRuntimeService(IBRuntimeServiceProtocol):
    """Synthetic service with one exact target leg and one untouched leg."""

    def __init__(self) -> None:
        self.evidence_calls = 0
        self.modify_calls = 0
        self.post_modify_evidence_calls = 0

    @staticmethod
    def _unexpected_call(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected dummy service call: {method_name}")

    def connect_demo(self) -> object | None:
        self._unexpected_call("connect_demo")

    def disconnect(self) -> None:
        self._unexpected_call("disconnect")

    def get_broker_health(self) -> RuntimeBrokerHealth:
        self._unexpected_call("get_broker_health")

    def get_account_state(self) -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id=ACCOUNT_ID,
            broker_name="IB",
            currency="USD",
        )

    def reconnect(self) -> object | None:
        self._unexpected_call("reconnect")

    def get_positions(self) -> list:
        self._unexpected_call("get_positions")

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        del symbol_name, side, quantity, stop_loss, take_profit, comment
        self._unexpected_call("place_market_order")

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        del position_id, quantity, comment
        self._unexpected_call("close_position")

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        del position_id, stop_loss, take_profit
        self._unexpected_call("modify_position_sl_tp")

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        self.evidence_calls += 1

        if self.modify_calls <= 0:
            return deepcopy(_build_evidence(modified=False))

        self.post_modify_evidence_calls += 1
        modified = self.post_modify_evidence_calls >= 2
        return deepcopy(_build_evidence(modified=modified))

    def close_virtual_position_leg(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        comment: str = "LGE virtual-leg close",
    ) -> dict:
        del (
            position_uid,
            position_id,
            account_id,
            symbol_name,
            position_side,
            position_volume,
            parent_order_id,
            stop_loss_order_id,
            take_profit_order_id,
            current_oca_group,
            comment,
        )
        self._unexpected_call("close_virtual_position_leg")

    def modify_virtual_position_leg_sl_tp(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        order_ref: str = "",
    ) -> dict:
        self.modify_calls += 1

        expected = {
            "position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
            "account_id": ACCOUNT_ID,
            "symbol_name": SYMBOL_NAME,
            "position_side": "BUY",
            "position_volume": 1000.0,
            "parent_order_id": TARGET_PARENT_ID,
            "stop_loss_order_id": TARGET_SL_ID,
            "take_profit_order_id": TARGET_TP_ID,
            "current_oca_group": f"LGE_{TARGET_PARENT_ID}",
            "stop_loss": TARGET_NEW_SL,
            "take_profit": TARGET_NEW_TP,
            "order_ref": TARGET_MODIFY_ORDER_REF,
        }
        actual = {
            "position_id": position_id,
            "account_id": account_id,
            "symbol_name": symbol_name,
            "position_side": position_side,
            "position_volume": position_volume,
            "parent_order_id": parent_order_id,
            "stop_loss_order_id": stop_loss_order_id,
            "take_profit_order_id": take_profit_order_id,
            "current_oca_group": current_oca_group,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "order_ref": order_ref,
        }

        if actual != expected:
            raise AssertionError(
                "RuntimeEngine passed incorrect virtual-leg Modify context"
            )

        if not position_uid:
            raise AssertionError("RuntimeEngine lost target position_uid")

        return {
            "position_uid": position_uid,
            "broker_position_id": position_id,
            "stop_loss_action": "MODIFY",
            "take_profit_action": "MODIFY",
            "operation_order_ids": {TARGET_SL_ID, TARGET_TP_ID},
            "confirmed": True,
            "executed": True,
            "no_operation": False,
        }


class MixedGroupModifyService(DummyIBRuntimeService):
    """Expose one reconciled target leg beside unresolved sibling evidence."""

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        evidence = super().get_virtual_position_leg_evidence_snapshot()
        evidence["open_orders"] = [
            row
            for row in evidence["open_orders"]
            if int(row["order_id"]) in {TARGET_TP_ID, TARGET_SL_ID}
        ]
        return evidence


def _order(
    *,
    order_id: int,
    parent_id: int,
    quantity: float,
    order_type: str,
    price: float,
) -> dict[str, Any]:
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": quantity,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "perm_id": order_id + 10000,
        "same_client_id": True,
        "oca_group": f"LGE_{parent_id}",
        "oca_type": 1,
        "status": "Submitted",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def _execution(
    *,
    order_id: int,
    quantity: float,
    price: float,
) -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "broker_position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
        "side": "BOT",
        "shares": quantity,
        "price": price,
        "time": "20260717 09:00:00 US/Eastern",
        "order_id": order_id,
        "perm_id": order_id + 10000,
    }


def _build_evidence(*, modified: bool) -> dict[str, Any]:
    target_sl = TARGET_NEW_SL if modified else 1.143
    target_tp = TARGET_NEW_TP if modified else 1.151
    return {
        "broker": "IB",
        "captured_utc": "2026-07-17T13:00:00+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "account_id": ACCOUNT_ID,
                "broker_position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
                "symbol_name": SYMBOL_NAME,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": 3000.0,
                "side": "BUY",
                "volume": 3000.0,
                "average_cost": 1.146,
            }
        ],
        "open_orders": [
            _order(
                order_id=TARGET_TP_ID,
                parent_id=TARGET_PARENT_ID,
                quantity=1000.0,
                order_type="LMT",
                price=target_tp,
            ),
            _order(
                order_id=TARGET_SL_ID,
                parent_id=TARGET_PARENT_ID,
                quantity=1000.0,
                order_type="STP",
                price=target_sl,
            ),
            _order(
                order_id=OTHER_TP_ID,
                parent_id=OTHER_PARENT_ID,
                quantity=2000.0,
                order_type="LMT",
                price=1.152,
            ),
            _order(
                order_id=OTHER_SL_ID,
                parent_id=OTHER_PARENT_ID,
                quantity=2000.0,
                order_type="STP",
                price=1.142,
            ),
        ],
        "completed_orders": [],
        "executions": [
            _execution(
                order_id=TARGET_PARENT_ID,
                quantity=1000.0,
                price=1.1465,
            ),
            _execution(
                order_id=OTHER_PARENT_ID,
                quantity=2000.0,
                price=1.14575,
            ),
        ],
    }


def _create_persisted_leg(
    engine: RuntimeEngine,
    *,
    volume: float,
    parent_order_id: int,
    stop_loss_order_id: int,
    take_profit_order_id: int,
    stop_loss: float,
    take_profit: float,
    entry_price: float,
    side: str = "BUY",
    leg_status: str = IB_LEG_STATUS_OPEN,
) -> str:
    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol=SYMBOL_NAME,
        side=side,
        volume=volume,
        source="MANUAL",
        comment=TARGET_COMMENT,
    )
    plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=side,
        volume=volume,
        source="MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=plan_uid,
        broker="IB",
        broker_order_id=str(parent_order_id),
        execution_status="FILLED",
        source="MANUAL",
        broker_comment=TARGET_BROKER_COMMENT,
    )
    position_uid = engine.repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
        symbol=SYMBOL_NAME,
        side=side,
        volume=volume,
        open_price=entry_price,
        opened_utc="2026-07-17T13:00:00+00:00",
        state="OPEN",
        source="BROKER",
    )
    leg = IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
        account_id=ACCOUNT_ID,
        symbol_name=SYMBOL_NAME,
        side=side,
        volume=volume,
        entry_price=entry_price,
        opened_utc="2026-07-17T13:00:00+00:00",
        source="MANUAL",
        parent_order_id=parent_order_id,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=f"LGE_{parent_order_id}",
        leg_status=leg_status,
        protection_status=(
            IB_PROTECTION_STATUS_COMPLETE
            if leg_status == IB_LEG_STATUS_OPEN
            else IB_PROTECTION_STATUS_NONE
        ),
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    engine.repository.upsert_ib_virtual_position_leg(
        leg,
        remaining_volume=volume if leg_status == IB_LEG_STATUS_OPEN else 0.0,
    )

    for role, order_id, order_type, action_price in (
        (IB_LEG_ORDER_ROLE_PARENT, parent_order_id, "MKT", entry_price),
        (IB_LEG_ORDER_ROLE_STOP_LOSS, stop_loss_order_id, "STP", stop_loss),
        (
            IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            take_profit_order_id,
            "LMT",
            take_profit,
        ),
    ):
        engine.repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=role,
            broker_order_id=order_id,
            execution_status=(
                "FILLED" if role == IB_LEG_ORDER_ROLE_PARENT else "SUBMITTED"
            ),
            parent_order_id=(
                None if role == IB_LEG_ORDER_ROLE_PARENT else parent_order_id
            ),
            client_id=CURRENT_CLIENT_ID,
            action=(
                side
                if role == IB_LEG_ORDER_ROLE_PARENT
                else ("SELL" if side == "BUY" else "BUY")
            ),
            order_type=order_type,
            quantity=volume,
            price=action_price,
            oca_group=(
                "" if role == IB_LEG_ORDER_ROLE_PARENT else f"LGE_{parent_order_id}"
            ),
            oca_type=None if role == IB_LEG_ORDER_ROLE_PARENT else 1,
            order_ref=TARGET_BROKER_COMMENT,
        )

    if leg_status == IB_LEG_STATUS_CLOSED:
        engine.repository.deactivate_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_STOP_LOSS,
            execution_status="FILLED",
        )
        engine.repository.deactivate_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            execution_status="CANCELLED",
        )

    return position_uid


def _cash_fx_completed_order(
    *,
    order_id: int,
    parent_id: int,
    order_type: str,
    status: str,
    price: float,
) -> dict[str, Any]:
    row = _order(
        order_id=order_id,
        parent_id=parent_id,
        quantity=0.0,
        order_type=order_type,
        price=price,
    )
    row.update(
        {
            "status": status,
            "completed_status": status,
            "filled": 2000.0 if order_id == 116 else 0.0,
            "remaining": 0.0,
        }
    )
    return row


def _build_cash_fx_history_evidence() -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-07-17T16:10:00+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "account_id": ACCOUNT_ID,
                "broker_position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
                "symbol_name": SYMBOL_NAME,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": -3000.0,
                "side": "SELL",
                "volume": 3000.0,
                "average_cost": 1.14143,
            }
        ],
        "open_orders": [
            {
                **_order(
                    order_id=124,
                    parent_id=123,
                    quantity=1000.0,
                    order_type="LMT",
                    price=1.1405,
                ),
                "action": "BUY",
                "oca_group": "LGE_123",
            },
            {
                **_order(
                    order_id=125,
                    parent_id=123,
                    quantity=1000.0,
                    order_type="STP",
                    price=1.148,
                ),
                "action": "BUY",
                "oca_group": "LGE_123",
            },
        ],
        "completed_orders": [
            _cash_fx_completed_order(
                order_id=116,
                parent_id=114,
                order_type="STP",
                status="Filled",
                price=1.14185,
            ),
            _cash_fx_completed_order(
                order_id=115,
                parent_id=114,
                order_type="LMT",
                status="Cancelled",
                price=1.152,
            ),
        ],
        "executions": [
            {
                **_execution(
                    order_id=116,
                    quantity=2000.0,
                    price=1.14185,
                ),
                "side": "SLD",
            },
            {
                **_execution(
                    order_id=123,
                    quantity=1000.0,
                    price=1.1426,
                ),
                "side": "SLD",
            },
        ],
    }


class CashFxHistoryService(DummyIBRuntimeService):
    """Evidence for one persisted closed leg plus one new open leg."""

    def __init__(self, *, virtual_fx_quantity: float = -3000.0) -> None:
        super().__init__()
        self.virtual_fx_quantity = virtual_fx_quantity
        self.current_stop_loss = 1.148
        self.current_take_profit = 1.1405

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        self.evidence_calls += 1
        evidence = deepcopy(_build_cash_fx_history_evidence())
        evidence["positions"][0]["signed_quantity"] = self.virtual_fx_quantity
        evidence["positions"][0]["volume"] = abs(self.virtual_fx_quantity)
        evidence["open_orders"][0]["lmt_price"] = self.current_take_profit
        evidence["open_orders"][1]["aux_price"] = self.current_stop_loss
        return evidence

    def modify_virtual_position_leg_sl_tp(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        order_ref: str = "",
    ) -> dict:
        self.modify_calls += 1

        if not position_uid:
            raise AssertionError("CASH FX Modify lost position_uid")

        expected = {
            "position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
            "account_id": ACCOUNT_ID,
            "symbol_name": SYMBOL_NAME,
            "position_side": "SELL",
            "position_volume": 1000.0,
            "parent_order_id": 123,
            "stop_loss_order_id": 125,
            "take_profit_order_id": 124,
            "current_oca_group": "LGE_123",
            "stop_loss": 1.149,
            "take_profit": 1.1405,
            "order_ref": TARGET_MODIFY_ORDER_REF,
        }
        actual = {
            "position_id": position_id,
            "account_id": account_id,
            "symbol_name": symbol_name,
            "position_side": position_side,
            "position_volume": position_volume,
            "parent_order_id": parent_order_id,
            "stop_loss_order_id": stop_loss_order_id,
            "take_profit_order_id": take_profit_order_id,
            "current_oca_group": current_oca_group,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "order_ref": order_ref,
        }

        if actual != expected:
            raise AssertionError("CASH FX Modify context differs")

        self.current_stop_loss = 1.149
        self.current_take_profit = 1.1405
        return {
            "position_uid": position_uid,
            "broker_position_id": position_id,
            "stop_loss_action": "MODIFY",
            "take_profit_action": "KEEP",
            "operation_order_ids": {125},
            "confirmed": True,
            "executed": True,
            "no_operation": False,
        }


def _run_cash_fx_history_case(db_path: Path) -> None:
    engine = RuntimeEngine(db_path=str(db_path))
    service = CashFxHistoryService()

    try:
        _create_persisted_leg(
            engine,
            volume=2000.0,
            parent_order_id=114,
            stop_loss_order_id=116,
            take_profit_order_id=115,
            stop_loss=1.14185,
            take_profit=1.152,
            entry_price=1.14665,
            side="BUY",
            leg_status=IB_LEG_STATUS_CLOSED,
        )
        open_uid = _create_persisted_leg(
            engine,
            volume=1000.0,
            parent_order_id=123,
            stop_loss_order_id=125,
            take_profit_order_id=124,
            stop_loss=1.148,
            take_profit=1.1405,
            entry_price=1.1426,
            side="SELL",
        )
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        snapshot = engine.get_open_runtime_position_legs()
        open_legs = [
            leg for leg in snapshot.legs if leg.leg_status == IB_LEG_STATUS_OPEN
        ]
        closed_legs = [
            leg for leg in snapshot.legs if leg.leg_status == IB_LEG_STATUS_CLOSED
        ]

        if len(open_legs) != 1 or open_legs[0].position_uid != open_uid:
            raise AssertionError("Cumulative CASH FX history lost the new open leg")

        if len(closed_legs) != 1:
            raise AssertionError(
                "Cumulative CASH FX history lost the persisted closed leg"
            )

        group_id = f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}"

        if snapshot.group_statuses[group_id] != IB_RECONCILIATION_STATUS_RECONCILED:
            raise AssertionError("Cumulative CASH FX Virtual FX row was not reconciled")

        service.virtual_fx_quantity = 0.0
        reset_snapshot = engine.get_open_runtime_position_legs()

        if (
            reset_snapshot.group_statuses[group_id]
            != IB_RECONCILIATION_STATUS_RECONCILED
        ):
            raise AssertionError("Reset CASH FX Virtual FX row blocked persisted leg")

        reset_messages = reset_snapshot.group_messages[group_id]

        if not any("zero/reset" in message for message in reset_messages):
            raise AssertionError("Reset CASH FX reconciliation message is missing")

        service.virtual_fx_quantity = -1000.0
        modify_result = engine.modify_runtime_position_leg_sl_tp(
            position_uid=open_uid,
            stop_loss=1.149,
            take_profit=1.1405,
        )
        modified_leg = engine.repository.get_ib_virtual_position_leg(open_uid)

        if modified_leg is None or modified_leg["stop_loss"] != 1.149:
            raise AssertionError("Nonzero CASH FX offset Modify was not persisted")

        if modify_result["cash_fx_virtual_observation_offset"] != 2000.0:
            raise AssertionError("CASH FX pre-operation observation offset differs")
    finally:
        engine.connection.close()


def _run_mixed_group_modify_case(db_path: Path) -> None:
    engine = RuntimeEngine(db_path=str(db_path))
    service = MixedGroupModifyService()

    try:
        target_uid = _create_persisted_leg(
            engine,
            volume=1000.0,
            parent_order_id=TARGET_PARENT_ID,
            stop_loss_order_id=TARGET_SL_ID,
            take_profit_order_id=TARGET_TP_ID,
            stop_loss=1.143,
            take_profit=1.151,
            entry_price=1.1465,
        )
        other_uid = _create_persisted_leg(
            engine,
            volume=2000.0,
            parent_order_id=OTHER_PARENT_ID,
            stop_loss_order_id=OTHER_SL_ID,
            take_profit_order_id=OTHER_TP_ID,
            stop_loss=1.142,
            take_profit=1.152,
            entry_price=1.14575,
        )
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        result = engine.modify_runtime_position_leg_sl_tp(
            position_uid=target_uid,
            stop_loss=TARGET_NEW_SL,
            take_profit=TARGET_NEW_TP,
        )
        group_id = f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}"

        if (
            result["snapshot"].group_statuses[group_id]
            != IB_RECONCILIATION_STATUS_RECONCILED
        ):
            raise AssertionError("Exact broker exposure did not recover sibling leg")

        target = engine.repository.get_ib_virtual_position_leg(target_uid)
        other = engine.repository.get_ib_virtual_position_leg(other_uid)

        if target is None or target["stop_loss"] != TARGET_NEW_SL:
            raise AssertionError("Mixed-group target Modify was not persisted")

        if other is None or other["stop_loss"] != 1.142:
            raise AssertionError("Mixed-group unresolved sibling was changed")

        other_active = engine.repository.get_ib_virtual_position_leg_orders(
            other_uid,
            active_only=True,
        )

        if len(other_active) != 3:
            raise AssertionError("Mixed-group sibling mappings were rewritten")
    finally:
        engine.connection.close()


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_modify_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService()

        try:
            target_uid = _create_persisted_leg(
                engine,
                volume=1000.0,
                parent_order_id=TARGET_PARENT_ID,
                stop_loss_order_id=TARGET_SL_ID,
                take_profit_order_id=TARGET_TP_ID,
                stop_loss=1.143,
                take_profit=1.151,
                entry_price=1.1465,
            )
            other_uid = _create_persisted_leg(
                engine,
                volume=2000.0,
                parent_order_id=OTHER_PARENT_ID,
                stop_loss_order_id=OTHER_SL_ID,
                take_profit_order_id=OTHER_TP_ID,
                stop_loss=1.142,
                take_profit=1.152,
                entry_price=1.14575,
            )
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            result = engine.modify_runtime_position_leg_sl_tp(
                position_uid=target_uid,
                stop_loss=TARGET_NEW_SL,
                take_profit=TARGET_NEW_TP,
            )
            target_leg = engine.repository.get_ib_virtual_position_leg(target_uid)
            other_leg = engine.repository.get_ib_virtual_position_leg(other_uid)

            if target_leg is None or other_leg is None:
                raise AssertionError("Persisted virtual legs were lost")

            if target_leg["stop_loss"] != TARGET_NEW_SL:
                raise AssertionError("Target Stop Loss was not persisted")

            if target_leg["take_profit"] != TARGET_NEW_TP:
                raise AssertionError("Target Take Profit was not persisted")

            if other_leg["stop_loss"] != 1.142:
                raise AssertionError("Second leg Stop Loss changed")

            if other_leg["take_profit"] != 1.152:
                raise AssertionError("Second leg Take Profit changed")

            target_orders = engine.repository.get_ib_virtual_position_leg_orders(
                target_uid,
                active_only=True,
            )
            target_by_role = {str(row["order_role"]): row for row in target_orders}

            if (
                int(target_by_role[IB_LEG_ORDER_ROLE_STOP_LOSS]["broker_order_id"])
                != TARGET_SL_ID
            ):
                raise AssertionError("Target SL order id changed")

            if (
                int(target_by_role[IB_LEG_ORDER_ROLE_TAKE_PROFIT]["broker_order_id"])
                != TARGET_TP_ID
            ):
                raise AssertionError("Target TP order id changed")

            if service.evidence_calls != 3:
                raise AssertionError("Unexpected evidence call count")

            if result["post_modify_reconciliation_attempts"] != 2:
                raise AssertionError("Post-Modify reconciliation retry was not used")

            group_snapshot = result.get("position_group_snapshot")

            if group_snapshot is None:
                raise AssertionError("Confirmed post-Modify group snapshot is missing")

            target_groups = [
                group
                for group in group_snapshot.groups
                if any(leg.position_uid == target_uid for leg in group.open_legs)
            ]

            if len(target_groups) != 1:
                raise AssertionError("Confirmed post-Modify group is not unique")

            if (
                target_groups[0].reconciliation_status
                != IB_RECONCILIATION_STATUS_RECONCILED
            ):
                raise AssertionError("Confirmed post-Modify group is not reconciled")

            if not result.get("post_modify_group_snapshot_reused"):
                raise AssertionError("Post-Modify group snapshot reuse flag differs")

            if service.modify_calls != 1:
                raise AssertionError("Unexpected Modify call count")

            print("RuntimeEngine IB virtual-leg Modify result")
            print(f"  position_uid={target_uid}")
            print(f"  stop_loss={target_leg['stop_loss']}")
            print(f"  take_profit={target_leg['take_profit']}")
            print(f"  stop_loss_order_id={TARGET_SL_ID}")
            print(f"  take_profit_order_id={TARGET_TP_ID}")
            print("  other_leg_unchanged=True")
            print(f"  evidence_calls={service.evidence_calls}")
            print(f"  modify_calls={service.modify_calls}")
            print(f"  modify_order_ref={TARGET_MODIFY_ORDER_REF}")
            print(
                "  post_modify_reconciliation_attempts="
                f"{result['post_modify_reconciliation_attempts']}"
            )
            print("  stale_post_modify_snapshot_retried=True")
            print("  confirmed_group_snapshot_reused=True")
            print(
                "  persistence_legs_written=" f"{result['persistence']['legs_written']}"
            )
        finally:
            engine.connection.close()

        _run_cash_fx_history_case(Path(temporary_directory) / "cash_fx_history.db")
        print("  cash_fx_cumulative_history_reconciled=True")
        print("  cash_fx_reset_after_restart_reconciled=True")
        print("  cash_fx_nonzero_offset_modify_reconciled=True")
        _run_mixed_group_modify_case(Path(temporary_directory) / "mixed_group.db")
        print("  mixed_group_exact_leg_modify=True")
        print("RUNTIME_ENGINE_IB_VIRTUAL_LEG_MODIFY_CHECK=OK")

    return 0
