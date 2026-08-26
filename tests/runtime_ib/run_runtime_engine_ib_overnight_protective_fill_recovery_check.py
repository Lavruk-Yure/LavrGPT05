# run_runtime_engine_ib_overnight_protective_fill_recovery_check.py
"""
RuntimeEngine IB overnight protective-fill recovery check.

RoadMap91:
- completedOrder may be absent for a previous-session protective fill;
- reqExecutions still provides exact persisted child orderId;
- full exact execution closes and persists the virtual leg;
- partial, wrong-action and dual-child evidence remain BLOCKED.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import (  # noqa: E402
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)

ACCOUNT_ID = "DUM513747"
BROKER_POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"
CURRENT_CLIENT_ID = 1
PARENT_ORDER_ID = 180
TAKE_PROFIT_ORDER_ID = 181
STOP_LOSS_ORDER_ID = 182


class _EvidenceService(IBRuntimeServiceProtocol):
    """Synthetic IB service exposing only the expected evidence call."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.evidence_calls = 0

    @staticmethod
    def _unexpected(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected IB service call: {method_name}")

    def connect_demo(self) -> object | None:
        self._unexpected("connect_demo")

    def disconnect(self) -> None:
        self._unexpected("disconnect")

    def get_broker_health(self) -> RuntimeBrokerHealth:
        self._unexpected("get_broker_health")

    def get_account_state(self) -> RuntimeAccountState:
        self._unexpected("get_account_state")

    def reconnect(self) -> object | None:
        self._unexpected("reconnect")

    def get_virtual_position_leg_evidence_snapshot(self) -> dict:
        self.evidence_calls += 1
        return deepcopy(self.snapshot)

    def get_positions(self) -> list:
        self._unexpected("get_positions")

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
        self._unexpected("place_market_order")

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        del position_id, quantity, comment
        self._unexpected("close_position")

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        del position_id, stop_loss, take_profit
        self._unexpected("modify_position_sl_tp")

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
        self._unexpected("close_virtual_position_leg")

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
            stop_loss,
            take_profit,
            order_ref,
        )
        self._unexpected("modify_virtual_position_leg_sl_tp")


def _execution(
    order_id: int,
    side: str,
    shares: float,
    price: float,
) -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "side": side,
        "shares": shares,
        "price": price,
        "time": "20260722 23:34:15 US/Eastern",
        "order_id": order_id,
        "perm_id": order_id + 1190101323,
    }


def _protective_order(
    order_id: int,
    order_type: str,
    price: float,
) -> dict[str, Any]:
    row = {
        "order_id": order_id,
        "parent_id": PARENT_ORDER_ID,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "EURUSD",
        "broker_position_id": BROKER_POSITION_ID,
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "oca_group": "1190101503",
        "order_ref": "[LGE:M] LGE manual UI order",
        "status": "Submitted",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def _complete_snapshot(
    *,
    open_orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-07-23T06:34:59+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": [],
        "open_orders": open_orders,
        "completed_orders": [],
        "executions": executions,
    }


def _create_runtime_chain(engine: RuntimeEngine) -> tuple[str, str]:
    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol="EURUSD",
        side="BUY",
        volume=1000.0,
        source="MANUAL",
        comment="LGE manual UI order",
    )
    order_plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=1000.0,
        source="MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id=str(PARENT_ORDER_ID),
        execution_status="FILLED",
        source="MANUAL",
        broker_comment="[LGE:M] LGE manual UI order",
    )
    position_uid = engine.repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=BROKER_POSITION_ID,
        symbol="EURUSD",
        side="BUY",
        volume=1000.0,
        open_price=1.14135,
        opened_utc="2026-07-22T11:24:00+00:00",
        source="BROKER",
    )
    return trade_uid, position_uid


def _open_leg(trade_uid: str, position_uid: str) -> IBVirtualPositionLeg:
    return IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=BROKER_POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name="EURUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.14135,
        opened_utc="2026-07-22T11:24:00+00:00",
        source="MANUAL",
        parent_order_id=PARENT_ORDER_ID,
        stop_loss_order_id=STOP_LOSS_ORDER_ID,
        take_profit_order_id=TAKE_PROFIT_ORDER_ID,
        stop_loss=1.1391,
        take_profit=1.143,
        oca_group="1190101503",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def _assert_blocked(
    leg: IBVirtualPositionLeg,
    executions: list[dict[str, Any]],
) -> None:
    snapshot = reconcile_ib_virtual_position_legs(
        legs=[leg],
        evidence_snapshot=_complete_snapshot(
            open_orders=[],
            executions=executions,
        ),
    )

    if snapshot.group_statuses[BROKER_POSITION_ID] != (
        IB_RECONCILIATION_STATUS_BLOCKED
    ):
        raise AssertionError("Unsafe execution-only evidence was not BLOCKED")


def main() -> int:
    engine = RuntimeEngine(db_path=":memory:")

    try:
        trade_uid, position_uid = _create_runtime_chain(engine)
        leg = _open_leg(trade_uid, position_uid)
        initial_snapshot = _complete_snapshot(
            open_orders=[
                _protective_order(STOP_LOSS_ORDER_ID, "STP", 1.1391),
                _protective_order(TAKE_PROFIT_ORDER_ID, "LMT", 1.143),
            ],
            executions=[
                _execution(PARENT_ORDER_ID, "BOT", 1000.0, 1.14135),
            ],
        )
        engine.repository.persist_confirmed_ib_virtual_position_leg_open(
            leg=leg,
            evidence_snapshot=initial_snapshot,
            parent_order_ref="[LGE:M] LGE manual UI order",
        )

        execution_only_snapshot = _complete_snapshot(
            open_orders=[],
            executions=[
                _execution(
                    TAKE_PROFIT_ORDER_ID,
                    "SLD",
                    1000.0,
                    1.143,
                )
            ],
        )
        service = _EvidenceService(execution_only_snapshot)
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        result = engine.sync_reconciled_ib_virtual_position_legs()
        snapshot = result["snapshot"]
        recovered_leg = snapshot.legs[0]

        if snapshot.group_statuses[BROKER_POSITION_ID] != (
            IB_RECONCILIATION_STATUS_RECONCILED
        ):
            raise AssertionError("Execution-only protective fill not reconciled")

        if recovered_leg.leg_status != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Execution-only protective fill did not close leg")

        if recovered_leg.protection_status != IB_PROTECTION_STATUS_NONE:
            raise AssertionError("Recovered closed leg retained protection")

        if recovered_leg.take_profit_order_id != TAKE_PROFIT_ORDER_ID:
            raise AssertionError("Recovered TAKE_PROFIT order id differs")

        persisted_leg = engine.repository.get_ib_virtual_position_leg(position_uid)

        if persisted_leg is None:
            raise AssertionError("Recovered leg was not persisted")

        if str(persisted_leg["leg_status"]).strip().upper() != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Persisted recovered leg is not CLOSED")

        open_seeds = engine.repository.get_open_ib_virtual_position_leg_seeds(
            account_id=ACCOUNT_ID,
        )

        if open_seeds:
            raise AssertionError("Recovered closed leg remained an open seed")

        child_rows = engine.connection.execute(
            """
            SELECT order_role, broker_order_id, is_active, execution_status
            FROM ib_virtual_position_leg_orders
            WHERE position_uid = ?
              AND order_role IN ('STOP_LOSS', 'TAKE_PROFIT')
            ORDER BY order_role
            """,
            (position_uid,),
        ).fetchall()

        if len(child_rows) != 2:
            raise AssertionError("Recovered child order history is incomplete")

        if any(int(row["is_active"]) != 0 for row in child_rows):
            raise AssertionError("Recovered child order remained active")

        partial_leg = _open_leg(trade_uid, position_uid)
        _assert_blocked(
            partial_leg,
            [_execution(TAKE_PROFIT_ORDER_ID, "SLD", 500.0, 1.143)],
        )
        _assert_blocked(
            partial_leg,
            [_execution(TAKE_PROFIT_ORDER_ID, "BOT", 1000.0, 1.143)],
        )
        _assert_blocked(
            partial_leg,
            [
                _execution(TAKE_PROFIT_ORDER_ID, "SLD", 1000.0, 1.143),
                _execution(STOP_LOSS_ORDER_ID, "SLD", 1000.0, 1.1391),
            ],
        )

        print("RuntimeEngine IB overnight protective-fill recovery result")
        print("  completed_orders=0")
        print(f"  execution_order_id={TAKE_PROFIT_ORDER_ID}")
        print(f"  recovered_leg_status={recovered_leg.leg_status}")
        print("  reconciliation_status=" f"{recovered_leg.reconciliation_status}")
        print(f"  protection_status={recovered_leg.protection_status}")
        print("  persistence_closed_legs=" f"{result['persistence']['closed_legs']}")
        print(f"  open_seeds={len(open_seeds)}")
        print("  child_orders_inactive=True")
        print("  partial_execution_blocked=True")
        print("  wrong_action_blocked=True")
        print("  dual_child_execution_blocked=True")
        print("RUNTIME_ENGINE_IB_OVERNIGHT_PROTECTIVE_FILL_RECOVERY_CHECK=OK")
        return 0
    finally:
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
