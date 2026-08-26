"""RoadMap90 exact IB virtual-leg CREATE/CANCEL persistence check."""

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
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "EURUSD"
POSITION_ID = f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}"
POSITION_SIDE = "SELL"
VOLUME = 1000.0
PARENT_ID = 401
INITIAL_TP_ID = 402
INITIAL_SL_ID = 403
RELINK_SL_ID = 405
RELINK_TP_ID = 406
SURVIVOR_SL_ID = 407
FINAL_SL_ID = 408
FINAL_TP_ID = 409
INITIAL_SL = 1.15
INITIAL_TP = 1.14
CURRENT_CLIENT_ID = 1
INITIAL_OCA = "OCA_401"
RELINK_OCA = "OCA_405_406"
FINAL_OCA = "OCA_408_409"


class DummyIBRuntimeService(IBRuntimeServiceProtocol):
    """Synthetic service for pair -> survivor -> pair transitions."""

    def __init__(self) -> None:
        self.evidence_calls = 0
        self.modify_calls = 0

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

    def get_virtual_position_leg_evidence_snapshot(
        self,
    ) -> dict[str, Any]:
        self.evidence_calls += 1
        return deepcopy(_build_evidence(self.modify_calls))

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
        expected_common = {
            "position_id": POSITION_ID,
            "account_id": ACCOUNT_ID,
            "symbol_name": SYMBOL_NAME,
            "position_side": POSITION_SIDE,
            "position_volume": VOLUME,
            "parent_order_id": PARENT_ID,
        }
        actual_common = {
            "position_id": position_id,
            "account_id": account_id,
            "symbol_name": symbol_name,
            "position_side": position_side,
            "position_volume": position_volume,
            "parent_order_id": parent_order_id,
        }

        if actual_common != expected_common or not position_uid:
            raise AssertionError("Virtual-leg CREATE/CANCEL context differs")

        self.modify_calls += 1

        if self.modify_calls == 1:
            if (
                stop_loss_order_id != INITIAL_SL_ID
                or take_profit_order_id != INITIAL_TP_ID
                or current_oca_group != INITIAL_OCA
                or stop_loss is not None
                or take_profit is not None
            ):
                raise AssertionError("CANCEL context differs")

            return {
                "position_uid": position_uid,
                "broker_position_id": position_id,
                "stop_loss_action": "CANCEL",
                "take_profit_action": "CANCEL",
                "create_order_ids": {},
                "oca_group": None,
                "operation_order_ids": {
                    INITIAL_SL_ID,
                    INITIAL_TP_ID,
                },
                "confirmed": True,
                "executed": True,
                "no_operation": False,
            }

        if self.modify_calls == 2:
            if (
                stop_loss_order_id is not None
                or take_profit_order_id is not None
                or current_oca_group
                or stop_loss != INITIAL_SL
                or take_profit != INITIAL_TP
            ):
                raise AssertionError("CREATE context differs")

            return {
                "position_uid": position_uid,
                "broker_position_id": position_id,
                "stop_loss_action": "CREATE",
                "take_profit_action": "CREATE",
                "create_order_ids": {
                    "stop_loss": RELINK_SL_ID,
                    "take_profit": RELINK_TP_ID,
                },
                "oca_group": RELINK_OCA,
                "operation_order_ids": {
                    RELINK_SL_ID,
                    RELINK_TP_ID,
                },
                "confirmed": True,
                "executed": True,
                "no_operation": False,
            }

        if self.modify_calls == 3:
            if (
                stop_loss_order_id != RELINK_SL_ID
                or take_profit_order_id != RELINK_TP_ID
                or current_oca_group != RELINK_OCA
                or stop_loss != INITIAL_SL
                or take_profit is not None
            ):
                raise AssertionError("Single-child CANCEL context differs")

            return {
                "position_uid": position_uid,
                "broker_position_id": position_id,
                "stop_loss_action": "KEEP",
                "take_profit_action": "CANCEL",
                "create_order_ids": {
                    "stop_loss": SURVIVOR_SL_ID,
                },
                "oca_group": None,
                "operation_order_ids": {
                    RELINK_SL_ID,
                    RELINK_TP_ID,
                    SURVIVOR_SL_ID,
                },
                "execution_guard_result": {"confirmed": True},
                "confirmed": True,
                "executed": True,
                "no_operation": False,
            }

        if self.modify_calls == 4:
            if (
                stop_loss_order_id != SURVIVOR_SL_ID
                or take_profit_order_id is not None
                or current_oca_group
                or stop_loss != INITIAL_SL
                or take_profit != INITIAL_TP
            ):
                raise AssertionError("Single-child CREATE context differs")

            return {
                "position_uid": position_uid,
                "broker_position_id": position_id,
                "stop_loss_action": "KEEP",
                "take_profit_action": "CREATE",
                "create_order_ids": {
                    "stop_loss": FINAL_SL_ID,
                    "take_profit": FINAL_TP_ID,
                },
                "oca_group": FINAL_OCA,
                "operation_order_ids": {
                    SURVIVOR_SL_ID,
                    FINAL_SL_ID,
                    FINAL_TP_ID,
                },
                "execution_guard_result": {"confirmed": True},
                "confirmed": True,
                "executed": True,
                "no_operation": False,
            }

        raise AssertionError("Unexpected CREATE/CANCEL Modify call count")


def _order(
    *,
    order_id: int,
    order_type: str,
    price: float,
    oca_group: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "order_id": order_id,
        "parent_id": 0,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": POSITION_ID,
        "action": "BUY",
        "order_type": order_type,
        "total_quantity": VOLUME,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "perm_id": order_id + 10000,
        "same_client_id": True,
        "oca_group": oca_group,
        "oca_type": 1 if oca_group else 0,
        "status": "Submitted",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def _build_evidence(stage: int) -> dict[str, Any]:
    if stage <= 0:
        open_orders = [
            _order(
                order_id=INITIAL_SL_ID,
                order_type="STP",
                price=INITIAL_SL,
                oca_group=INITIAL_OCA,
            ),
            _order(
                order_id=INITIAL_TP_ID,
                order_type="LMT",
                price=INITIAL_TP,
                oca_group=INITIAL_OCA,
            ),
        ]
    elif stage == 1:
        open_orders = []
    elif stage == 2:
        open_orders = [
            _order(
                order_id=RELINK_SL_ID,
                order_type="STP",
                price=INITIAL_SL,
                oca_group=RELINK_OCA,
            ),
            _order(
                order_id=RELINK_TP_ID,
                order_type="LMT",
                price=INITIAL_TP,
                oca_group=RELINK_OCA,
            ),
        ]
    elif stage == 3:
        open_orders = [
            _order(
                order_id=SURVIVOR_SL_ID,
                order_type="STP",
                price=INITIAL_SL,
                oca_group="",
            ),
        ]
    else:
        open_orders = [
            _order(
                order_id=FINAL_SL_ID,
                order_type="STP",
                price=INITIAL_SL,
                oca_group=FINAL_OCA,
            ),
            _order(
                order_id=FINAL_TP_ID,
                order_type="LMT",
                price=INITIAL_TP,
                oca_group=FINAL_OCA,
            ),
        ]

    return {
        "broker": "IB",
        "captured_utc": "2026-07-17T16:30:00+00:00",
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
                "broker_position_id": POSITION_ID,
                "symbol_name": SYMBOL_NAME,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": 0.0,
                "side": "UNKNOWN",
                "volume": 0.0,
                "average_cost": 0.0,
            }
        ],
        "open_orders": open_orders,
        "completed_orders": [],
        "executions": [],
    }


def _create_leg(engine: RuntimeEngine) -> str:
    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol=SYMBOL_NAME,
        side=POSITION_SIDE,
        volume=VOLUME,
        source="LGE_MANUAL",
    )
    plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=POSITION_SIDE,
        volume=VOLUME,
        source="LGE_MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=plan_uid,
        broker="IB",
        broker_order_id=str(PARENT_ID),
        execution_status="FILLED",
        source="LGE_MANUAL",
    )
    position_uid = engine.repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=POSITION_ID,
        symbol=SYMBOL_NAME,
        side=POSITION_SIDE,
        volume=VOLUME,
        open_price=1.1426,
        opened_utc="2026-07-17T13:07:10+00:00",
        state="OPEN",
        source="BROKER",
    )
    leg = IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name=SYMBOL_NAME,
        side=POSITION_SIDE,
        volume=VOLUME,
        entry_price=1.1426,
        opened_utc="2026-07-17T13:07:10+00:00",
        source="LGE_MANUAL",
        parent_order_id=PARENT_ID,
        stop_loss_order_id=INITIAL_SL_ID,
        take_profit_order_id=INITIAL_TP_ID,
        stop_loss=INITIAL_SL,
        take_profit=INITIAL_TP,
        oca_group=INITIAL_OCA,
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    engine.repository.upsert_ib_virtual_position_leg(
        leg,
        remaining_volume=VOLUME,
    )

    for role, order_id, order_type, price in (
        (IB_LEG_ORDER_ROLE_PARENT, PARENT_ID, "MKT", 1.1426),
        (
            IB_LEG_ORDER_ROLE_STOP_LOSS,
            INITIAL_SL_ID,
            "STP",
            INITIAL_SL,
        ),
        (
            IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            INITIAL_TP_ID,
            "LMT",
            INITIAL_TP,
        ),
    ):
        engine.repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=role,
            broker_order_id=order_id,
            execution_status=(
                "FILLED" if role == IB_LEG_ORDER_ROLE_PARENT else "SUBMITTED"
            ),
            parent_order_id=(None if role == IB_LEG_ORDER_ROLE_PARENT else PARENT_ID),
            client_id=CURRENT_CLIENT_ID,
            action=(POSITION_SIDE if role == IB_LEG_ORDER_ROLE_PARENT else "BUY"),
            order_type=order_type,
            quantity=VOLUME,
            price=price,
            oca_group=("" if role == IB_LEG_ORDER_ROLE_PARENT else INITIAL_OCA),
            oca_type=(None if role == IB_LEG_ORDER_ROLE_PARENT else 1),
        )

    return position_uid


def _active_orders_by_role(
    engine: RuntimeEngine,
    position_uid: str,
) -> dict[str, dict[str, Any]]:
    rows = engine.repository.get_ib_virtual_position_leg_orders(
        position_uid,
        active_only=True,
    )
    return {str(row["order_role"]): row for row in rows}


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_create_cancel_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService()

        try:
            position_uid = _create_leg(engine)
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            cancel_result = engine.modify_runtime_position_leg_sl_tp(
                position_uid=position_uid,
                stop_loss=None,
                take_profit=None,
            )
            cancelled_leg = engine.repository.get_ib_virtual_position_leg(position_uid)

            if cancelled_leg is None:
                raise AssertionError("CANCEL persistence leg is missing")

            if cancelled_leg["stop_loss_order_id"] is not None:
                raise AssertionError("Cancelled SL mapping remained active")

            if cancelled_leg["take_profit_order_id"] is not None:
                raise AssertionError("Cancelled TP mapping remained active")

            cancel_active = _active_orders_by_role(
                engine,
                position_uid,
            )

            if IB_LEG_ORDER_ROLE_STOP_LOSS in cancel_active:
                raise AssertionError("SL remained active after CANCEL")

            if IB_LEG_ORDER_ROLE_TAKE_PROFIT in cancel_active:
                raise AssertionError("TP remained active after CANCEL")

            create_result = engine.modify_runtime_position_leg_sl_tp(
                position_uid=position_uid,
                stop_loss=INITIAL_SL,
                take_profit=INITIAL_TP,
            )
            recreated_leg = engine.repository.get_ib_virtual_position_leg(position_uid)

            if recreated_leg is None:
                raise AssertionError("CREATE persistence leg is missing")

            if int(recreated_leg["stop_loss_order_id"]) != RELINK_SL_ID:
                raise AssertionError("Relinked SL order ID differs")

            if int(recreated_leg["take_profit_order_id"]) != RELINK_TP_ID:
                raise AssertionError("Relinked TP order ID differs")

            if recreated_leg["oca_group"] != RELINK_OCA:
                raise AssertionError("Relinked OCA group differs")

            create_active = _active_orders_by_role(
                engine,
                position_uid,
            )

            if (
                int(create_active[IB_LEG_ORDER_ROLE_STOP_LOSS]["broker_order_id"])
                != RELINK_SL_ID
            ):
                raise AssertionError("New active SL mapping differs")

            if (
                int(create_active[IB_LEG_ORDER_ROLE_TAKE_PROFIT]["broker_order_id"])
                != RELINK_TP_ID
            ):
                raise AssertionError("New active TP mapping differs")

            survivor_result = engine.modify_runtime_position_leg_sl_tp(
                position_uid=position_uid,
                stop_loss=INITIAL_SL,
                take_profit=None,
            )
            survivor_leg = engine.repository.get_ib_virtual_position_leg(
                position_uid
            )

            if survivor_leg is None:
                raise AssertionError("Survivor persistence leg is missing")

            if int(survivor_leg["stop_loss_order_id"]) != SURVIVOR_SL_ID:
                raise AssertionError("Replacement survivor SL ID differs")

            if survivor_leg["take_profit_order_id"] is not None:
                raise AssertionError("Cancelled TP remained after survivor")

            if survivor_leg["oca_group"]:
                raise AssertionError("Standalone survivor retained OCA group")

            final_result = engine.modify_runtime_position_leg_sl_tp(
                position_uid=position_uid,
                stop_loss=INITIAL_SL,
                take_profit=INITIAL_TP,
            )
            final_leg = engine.repository.get_ib_virtual_position_leg(
                position_uid
            )

            if final_leg is None:
                raise AssertionError("Final replacement pair is missing")

            if int(final_leg["stop_loss_order_id"]) != FINAL_SL_ID:
                raise AssertionError("Final replacement SL ID differs")

            if int(final_leg["take_profit_order_id"]) != FINAL_TP_ID:
                raise AssertionError("Final replacement TP ID differs")

            if final_leg["oca_group"] != FINAL_OCA:
                raise AssertionError("Final replacement OCA group differs")

            history = engine.repository.get_ib_virtual_position_leg_orders(
                position_uid,
                active_only=False,
            )

            if len(history) != 8:
                raise AssertionError("Order replacement history differs")

            if service.modify_calls != 4 or service.evidence_calls != 8:
                raise AssertionError("Unexpected service call counts")

            print("RuntimeEngine IB virtual-leg CREATE/CANCEL result")
            print(f"  position_uid={position_uid}")
            print("  cancel_stop_loss_order_id=None")
            print("  cancel_take_profit_order_id=None")
            print(
                "  relink_stop_loss_order_id=" f"{recreated_leg['stop_loss_order_id']}"
            )
            print(
                "  relink_take_profit_order_id="
                f"{recreated_leg['take_profit_order_id']}"
            )
            print(f"  relink_oca_group={recreated_leg['oca_group']}")
            print(f"  order_history_rows={len(history)}")
            print(f"  evidence_calls={service.evidence_calls}")
            print(f"  modify_calls={service.modify_calls}")
            print(
                "  cancel_reconciliation_attempts="
                f"{cancel_result['post_modify_reconciliation_attempts']}"
            )
            print(
                "  create_reconciliation_attempts="
                f"{create_result['post_modify_reconciliation_attempts']}"
            )
            print(
                "  survivor_stop_loss_order_id="
                f"{survivor_leg['stop_loss_order_id']}"
            )
            print(
                "  final_stop_loss_order_id="
                f"{final_leg['stop_loss_order_id']}"
            )
            print(
                "  final_take_profit_order_id="
                f"{final_leg['take_profit_order_id']}"
            )
            print(
                "  survivor_reconciliation_attempts="
                f"{survivor_result['post_modify_reconciliation_attempts']}"
            )
            print(
                "  final_reconciliation_attempts="
                f"{final_result['post_modify_reconciliation_attempts']}"
            )
            print("RUNTIME_ENGINE_IB_VIRTUAL_LEG_CREATE_CANCEL_CHECK=OK")
        finally:
            engine.connection.close()

    return 0
