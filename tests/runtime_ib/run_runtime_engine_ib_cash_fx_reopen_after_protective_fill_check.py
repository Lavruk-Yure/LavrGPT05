# run_runtime_engine_ib_cash_fx_reopen_after_protective_fill_check.py
"""IB CASH FX reopen after an older protective fill regression check."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_virtual_position_leg import IBVirtualPositionLeg  # noqa: E402
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
OLD_PARENT_ID = 180
OLD_TP_ID = 181
OLD_SL_ID = 182
NEW_PARENT_ID = 183
NEW_TP_ID = 184
NEW_SL_ID = 185


class _EvidenceService(IBRuntimeServiceProtocol):
    """Synthetic IB service for one exact evidence snapshot."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.evidence_calls = 0
        self.position_calls = 0

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
        self.position_calls += 1
        return []

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
        "time": "20260723 04:36:00 US/Eastern",
        "order_id": order_id,
        "perm_id": order_id + 1329483368,
    }


def _position(signed_quantity: float) -> dict[str, Any]:
    return {
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "EURUSD",
        "broker_position_id": BROKER_POSITION_ID,
        "signed_quantity": signed_quantity,
        "position": signed_quantity,
        "avg_cost": 1.14105,
    }


def _protective_order(
    *,
    order_id: int,
    parent_id: int,
    action: str,
    order_type: str,
    price: float,
    oca_group: str,
) -> dict[str, Any]:
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "EURUSD",
        "broker_position_id": BROKER_POSITION_ID,
        "action": action,
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "oca_group": oca_group,
        "order_ref": "[LGE:M] LGE manual UI order",
        "status": "Submitted",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def _snapshot(
    *,
    positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-07-23T09:00:08+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": positions,
        "open_orders": open_orders,
        "completed_orders": [],
        "executions": executions,
    }


def _create_leg(
    engine: RuntimeEngine,
    *,
    side: str,
    parent_order_id: int,
    stop_loss_order_id: int,
    take_profit_order_id: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    oca_group: str,
) -> tuple[str, IBVirtualPositionLeg]:
    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol="EURUSD",
        side=side,
        volume=1000.0,
        source="MANUAL",
        comment="LGE manual UI order",
    )
    order_plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=side,
        volume=1000.0,
        source="MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id=str(parent_order_id),
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
        side=side,
        volume=1000.0,
        open_price=entry_price,
        opened_utc="2026-07-23T08:36:00+00:00",
        source="BROKER",
    )
    leg = IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=BROKER_POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name="EURUSD",
        side=side,
        volume=1000.0,
        entry_price=entry_price,
        opened_utc="2026-07-23T08:36:00+00:00",
        source="MANUAL",
        parent_order_id=parent_order_id,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=oca_group,
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    return position_uid, leg


def _persist_open(
    engine: RuntimeEngine,
    leg: IBVirtualPositionLeg,
) -> None:
    protective_action = "SELL" if leg.side == "BUY" else "BUY"
    evidence = _snapshot(
        positions=[_position(leg.signed_volume)],
        open_orders=[
            _protective_order(
                order_id=int(leg.stop_loss_order_id or 0),
                parent_id=int(leg.parent_order_id or 0),
                action=protective_action,
                order_type="STP",
                price=float(leg.stop_loss or 0.0),
                oca_group=leg.oca_group,
            ),
            _protective_order(
                order_id=int(leg.take_profit_order_id or 0),
                parent_id=int(leg.parent_order_id or 0),
                action=protective_action,
                order_type="LMT",
                price=float(leg.take_profit or 0.0),
                oca_group=leg.oca_group,
            ),
        ],
        executions=[
            _execution(
                int(leg.parent_order_id or 0),
                "BOT" if leg.side == "BUY" else "SLD",
                1000.0,
                float(leg.entry_price or 0.0),
            )
        ],
    )
    engine.repository.persist_confirmed_ib_virtual_position_leg_open(
        leg=leg,
        evidence_snapshot=evidence,
        parent_order_ref="[LGE:M] LGE manual UI order",
    )


def main() -> int:
    engine = RuntimeEngine(db_path=":memory:")

    try:
        old_uid, old_leg = _create_leg(
            engine,
            side="BUY",
            parent_order_id=OLD_PARENT_ID,
            stop_loss_order_id=OLD_SL_ID,
            take_profit_order_id=OLD_TP_ID,
            entry_price=1.14135,
            stop_loss=1.1391,
            take_profit=1.143,
            oca_group="1190101503",
        )
        new_uid, new_leg = _create_leg(
            engine,
            side="SELL",
            parent_order_id=NEW_PARENT_ID,
            stop_loss_order_id=NEW_SL_ID,
            take_profit_order_id=NEW_TP_ID,
            entry_price=1.14105,
            stop_loss=1.144,
            take_profit=1.14,
            oca_group="1329483551",
        )
        _persist_open(engine, old_leg)
        _persist_open(engine, new_leg)

        current_evidence = _snapshot(
            positions=[_position(-1000.0)],
            open_orders=[
                _protective_order(
                    order_id=NEW_SL_ID,
                    parent_id=NEW_PARENT_ID,
                    action="BUY",
                    order_type="STP",
                    price=1.144,
                    oca_group="1329483551",
                ),
                _protective_order(
                    order_id=NEW_TP_ID,
                    parent_id=NEW_PARENT_ID,
                    action="BUY",
                    order_type="LMT",
                    price=1.14,
                    oca_group="1329483551",
                ),
            ],
            executions=[
                _execution(OLD_TP_ID, "SLD", 1000.0, 1.143),
                _execution(NEW_PARENT_ID, "SLD", 1000.0, 1.14105),
            ],
        )
        service = _EvidenceService(current_evidence)
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        group_snapshot = engine.sync_active_broker_position_groups()
        group = group_snapshot.groups[0]
        legs_by_uid = {leg.position_uid: leg for leg in group.legs}
        recovered_old = legs_by_uid[old_uid]
        reopened_new = legs_by_uid[new_uid]

        if group.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise AssertionError("CASH FX reopen group was not RECONCILED")

        if recovered_old.leg_status != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Older BUY leg was not CLOSED")

        if recovered_old.protection_status != IB_PROTECTION_STATUS_NONE:
            raise AssertionError("Older closed leg retained protection")

        if reopened_new.leg_status != IB_LEG_STATUS_OPEN:
            raise AssertionError("New SELL leg was not OPEN")

        if reopened_new.protection_status != IB_PROTECTION_STATUS_COMPLETE:
            raise AssertionError("New SELL leg protection is incomplete")

        persisted_old = engine.repository.get_ib_virtual_position_leg(old_uid)
        persisted_new = engine.repository.get_ib_virtual_position_leg(new_uid)

        if persisted_old is None or persisted_new is None:
            raise AssertionError("Reopen persistence rows are missing")

        if str(persisted_old["leg_status"]).strip().upper() != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Older leg closure was not persisted")

        if str(persisted_new["leg_status"]).strip().upper() != IB_LEG_STATUS_OPEN:
            raise AssertionError("New SELL leg open state was not persisted")

        state_before_blocked = engine.connection.execute(
            """
            SELECT position_uid, leg_status, reconciliation_status, updated_utc
            FROM ib_virtual_position_legs
            ORDER BY position_uid
            """
        ).fetchall()
        service.snapshot = _snapshot(
            positions=[_position(-500.0)],
            open_orders=current_evidence["open_orders"],
            executions=current_evidence["executions"],
        )
        blocked_groups = engine.sync_active_broker_position_groups()
        blocked_group = blocked_groups.groups[0]
        state_after_blocked = engine.connection.execute(
            """
            SELECT position_uid, leg_status, reconciliation_status, updated_utc
            FROM ib_virtual_position_legs
            ORDER BY position_uid
            """
        ).fetchall()

        if blocked_group.reconciliation_status != IB_RECONCILIATION_STATUS_BLOCKED:
            raise AssertionError("Unsafe CASH FX mismatch was not BLOCKED")

        if [tuple(row) for row in state_after_blocked] != [
            tuple(row) for row in state_before_blocked
        ]:
            raise AssertionError("BLOCKED refresh changed persistence")

        print("RuntimeEngine IB CASH FX reopen result")
        print("  prior_parent_execution_outside_history=True")
        print(f"  prior_take_profit_execution={OLD_TP_ID}")
        print(f"  new_parent_execution={NEW_PARENT_ID}")
        print("  broker_virtual_fx=-1000.0")
        print("  current_exposure_executions=-1000.0")
        print(f"  old_leg_status={recovered_old.leg_status}")
        print(f"  new_leg_status={reopened_new.leg_status}")
        print(f"  new_protection={reopened_new.protection_status}")
        print(f"  group_status={group.reconciliation_status}")
        print("  persistence_written=True")
        print("  blocked_refresh_returned_snapshot=True")
        print("  blocked_refresh_persistence_unchanged=True")
        print("RUNTIME_ENGINE_IB_CASH_FX_REOPEN_AFTER_PROTECTIVE_FILL_CHECK=OK")
        return 0
    finally:
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
