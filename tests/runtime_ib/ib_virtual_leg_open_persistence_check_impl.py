# run_runtime_engine_ib_virtual_leg_open_persistence_check.py
"""
RuntimeEngine IB manual Open automatic virtual-leg persistence check.

RoadMap90:
- existing IB manual Open lifecycle stays intact;
- a newly filled LGE-owned IB order becomes one persisted virtual leg;
- parent, SL and TP mappings are stored automatically;
- the broker result remains successful even if persistence must be reported
  separately.
"""

from __future__ import annotations

import logging
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

from engine.broker_position import BrokerPosition
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_PERSISTENCE_STATUS_ERROR,
    IB_LEG_PERSISTENCE_STATUS_RECONCILED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "EURUSD"
PARENT_ORDER_ID = 201
TAKE_PROFIT_ORDER_ID = 202
STOP_LOSS_ORDER_ID = 203
CURRENT_CLIENT_ID = 1


class DummyIBRuntimeService(IBRuntimeServiceProtocol):
    """
    Synthetic IB service for one successful LGE-owned bracket Open.
    """

    def __init__(self, *, evidence_complete: bool = True) -> None:
        self.position_calls = 0
        self.place_calls = 0
        self.evidence_calls = 0
        self.evidence_complete = evidence_complete

    @staticmethod
    def _unexpected_call(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected dummy service call: {method_name}")

    def connect_demo(self) -> object | None:
        self._unexpected_call("connect_demo")

    def disconnect(self) -> None:
        self._unexpected_call("disconnect")

    def get_broker_health(self) -> RuntimeBrokerHealth:
        self._unexpected_call("get_broker_health")

    def reconnect(self) -> object | None:
        self._unexpected_call("reconnect")

    def get_account_state(self) -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id=ACCOUNT_ID,
            broker_name="IB",
            currency="USD",
        )

    def get_positions(self) -> list[BrokerPosition]:
        self.position_calls += 1

        if self.position_calls == 1:
            return []

        return [
            BrokerPosition(
                broker="IB",
                account_id=ACCOUNT_ID,
                account_mode="DEMO",
                position_id=f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
                symbol_name=SYMBOL_NAME,
                side="BUY",
                volume=1000.0,
                entry_price=1.1465,
                opened_utc="2026-07-17T12:30:00+00:00",
            )
        ]

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict[str, Any]:
        self.place_calls += 1

        if comment != "[LGE:M] RoadMap90 automatic persistence check" and (
            comment
            != "[LGE:M] RoadMap90 persistence failure reporting check"
        ):
            raise AssertionError("Unexpected synthetic IB broker comment")

        if symbol_name != SYMBOL_NAME or side != "BUY":
            raise AssertionError("Unexpected synthetic IB Open identity")

        if quantity != 1000.0:
            raise AssertionError("Unexpected synthetic IB Open quantity")

        if stop_loss != 1.143 or take_profit != 1.152:
            raise AssertionError("Unexpected synthetic IB Open protection")

        return {
            "broker": "IB",
            "order_id": str(PARENT_ORDER_ID),
            "broker_order_id": str(PARENT_ORDER_ID),
            "parent_order_id": str(PARENT_ORDER_ID),
            "child_order_ids": [
                str(TAKE_PROFIT_ORDER_ID),
                str(STOP_LOSS_ORDER_ID),
            ],
            "stop_loss_order_id": str(STOP_LOSS_ORDER_ID),
            "take_profit_order_id": str(TAKE_PROFIT_ORDER_ID),
            "current_client_id": CURRENT_CLIENT_ID,
            "symbol_name": SYMBOL_NAME,
            "side": "BUY",
            "quantity": 1000.0,
            "status": "FILLED",
            "filled": 1000.0,
            "remaining": 0.0,
            "avg_fill_price": 1.1465,
            "control_mode": "MANUAL",
            "display_comment": comment.removeprefix("[LGE:M] "),
            "broker_comment": comment,
            "stop_loss": 1.143,
            "take_profit": 1.152,
            "open_orders": [],
            "order_statuses": [],
        }

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        self.evidence_calls += 1
        snapshot = deepcopy(_build_evidence())

        if not self.evidence_complete:
            snapshot["complete"] = False

        return snapshot

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
        )
        self._unexpected_call("modify_virtual_position_leg_sl_tp")


def _order(
    *,
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
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "perm_id": order_id + 10000,
        "same_client_id": True,
        "oca_group": "",
        "oca_type": 0,
        "order_ref": "[LGE:M] RoadMap90 automatic persistence check",
        "status": "Submitted",
    }

    if order_type == "LMT":
        row["lmt_price"] = price
    else:
        row["aux_price"] = price

    return row


def _build_evidence() -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-07-17T12:30:02+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "account_id": ACCOUNT_ID,
                "broker_position_id": f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}",
                "symbol_name": SYMBOL_NAME,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": -1000.0,
                "side": "SELL",
                "volume": 1000.0,
                "average_cost": 1.1465,
            }
        ],
        "open_orders": [
            _order(
                order_id=TAKE_PROFIT_ORDER_ID,
                order_type="LMT",
                price=1.152,
            ),
            _order(
                order_id=STOP_LOSS_ORDER_ID,
                order_type="STP",
                price=1.143,
            ),
        ],
        "completed_orders": [],
        "executions": [
            {
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "side": "BOT",
                "shares": 1000.0,
                "price": 1.1465,
                "time": "20260717 08:30:00 US/Eastern",
                "order_id": PARENT_ORDER_ID,
                "perm_id": PARENT_ORDER_ID + 10000,
            }
        ],
    }


def _run_persistence_failure_case(db_path: Path) -> None:
    engine = RuntimeEngine(db_path=str(db_path))
    service = DummyIBRuntimeService(evidence_complete=False)

    runtime_logger = logging.getLogger("engine.runtime_engine")
    logger_disabled = runtime_logger.disabled
    runtime_logger.disabled = True

    try:
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        result = engine.place_manual_market_order(
            symbol_name=SYMBOL_NAME,
            side="BUY",
            lots=0.01,
            stop_loss=1.143,
            take_profit=1.152,
            comment="RoadMap90 persistence failure reporting check",
        )

        position_uid = str(result.get("position_uid") or "")

        if not position_uid:
            raise AssertionError(
                "Persistence failure case lost broker position identity"
            )

        if (
            result.get("virtual_leg_persistence_status")
            != IB_LEG_PERSISTENCE_STATUS_ERROR
        ):
            raise AssertionError("Persistence failure was not reported separately")

        if not result.get("virtual_leg_persistence_error"):
            raise AssertionError("Persistence failure error message is empty")

        if engine.repository.get_ib_virtual_position_leg(position_uid):
            raise AssertionError("Incomplete evidence wrote an IB virtual leg")
    finally:
        runtime_logger.disabled = logger_disabled
        engine.connection.close()


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_open_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService()

        try:
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            result = engine.place_manual_market_order(
                symbol_name=SYMBOL_NAME,
                side="BUY",
                lots=0.01,
                stop_loss=1.143,
                take_profit=1.152,
                comment="RoadMap90 automatic persistence check",
            )

            position_uid = str(result.get("position_uid") or "")

            if not position_uid:
                raise AssertionError("IB Open did not create position_uid")

            if (
                result.get("virtual_leg_persistence_status")
                != IB_LEG_PERSISTENCE_STATUS_RECONCILED
            ):
                raise AssertionError(
                    "IB Open virtual-leg persistence was not reconciled"
                )

            if result.get("virtual_leg_persistence_error"):
                raise AssertionError("IB Open returned a virtual-leg persistence error")

            leg = engine.repository.get_ib_virtual_position_leg(position_uid)

            if leg is None:
                raise AssertionError("Persisted IB virtual leg was not found")

            if leg["leg_status"] != IB_LEG_STATUS_OPEN:
                raise AssertionError("Persisted IB virtual leg is not OPEN")

            if leg["reconciliation_status"] != IB_RECONCILIATION_STATUS_RECONCILED:
                raise AssertionError("Persisted IB virtual leg is not RECONCILED")

            if leg["protection_status"] != IB_PROTECTION_STATUS_COMPLETE:
                raise AssertionError(
                    "Persisted IB virtual leg protection is not COMPLETE"
                )

            if str(leg["parent_order_id"]) != str(PARENT_ORDER_ID):
                raise AssertionError("Parent order mapping differs")

            if str(leg["stop_loss_order_id"]) != str(STOP_LOSS_ORDER_ID):
                raise AssertionError("Stop Loss order mapping differs")

            if str(leg["take_profit_order_id"]) != str(TAKE_PROFIT_ORDER_ID):
                raise AssertionError("Take Profit order mapping differs")

            orders = engine.repository.get_ib_virtual_position_leg_orders(
                position_uid=position_uid,
                active_only=True,
            )
            roles = {str(row["order_role"]): row for row in orders}

            expected_roles = {
                IB_LEG_ORDER_ROLE_PARENT,
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            }

            if set(roles) != expected_roles:
                raise AssertionError("Persisted IB order roles differ")

            expected_order_ref = (
                "[LGE:M] RoadMap90 automatic persistence check"
            )

            if any(
                str(row.get("order_ref") or "") != expected_order_ref
                for row in roles.values()
            ):
                raise AssertionError("Persisted IB orderRef differs")

            trade_row = engine.connection.execute(
                """
                SELECT comment
                FROM trades
                WHERE trade_uid = ?
                """,
                (str(result["trade_uid"]),),
            ).fetchone()
            broker_order_row = engine.connection.execute(
                """
                SELECT broker_comment
                FROM broker_orders
                WHERE broker_order_uid = ?
                """,
                (str(result["broker_order_uid"]),),
            ).fetchone()

            if trade_row is None or trade_row[0] != (
                "RoadMap90 automatic persistence check"
            ):
                raise AssertionError("Persisted Trade comment differs")

            if broker_order_row is None or broker_order_row[0] != (
                expected_order_ref
            ):
                raise AssertionError("Persisted BrokerOrder comment differs")

            if service.position_calls != 2:
                raise AssertionError("Unexpected IB position call count")

            if service.place_calls != 1:
                raise AssertionError("Unexpected IB place call count")

            if service.evidence_calls != 1:
                raise AssertionError("Unexpected IB evidence call count")

            open_seeds = engine.repository.get_open_ib_virtual_position_leg_seeds()

            if len(open_seeds) != 1:
                raise AssertionError("Expected one persisted open leg seed")

            print("RuntimeEngine IB virtual-leg Open persistence result")
            print(f"  position_uid={position_uid}")
            print("  persistence_status=" f"{result['virtual_leg_persistence_status']}")
            print(f"  parent_order_id={leg['parent_order_id']}")
            print(f"  stop_loss_order_id={leg['stop_loss_order_id']}")
            print("  take_profit_order_id=" f"{leg['take_profit_order_id']}")
            print(f"  protection_status={leg['protection_status']}")
            print(f"  active_order_mappings={len(orders)}")
            print(f"  open_seed_count={len(open_seeds)}")
            print(f"  position_calls={service.position_calls}")
            print(f"  place_calls={service.place_calls}")
            print("  virtual_fx_quantity=-1000.0")
            print(f"  evidence_calls={service.evidence_calls}")
            print(
                "  trade_comment="
                "RoadMap90 automatic persistence check"
            )
            print(
                "  broker_order_comment="
                "[LGE:M] RoadMap90 automatic persistence check"
            )
            print("  leg_order_refs_exact=True")
        finally:
            engine.connection.close()

        _run_persistence_failure_case(Path(temporary_directory) / "runtime_failure.db")
        print("  persistence_failure_reported=True")
        print("RUNTIME_ENGINE_IB_VIRTUAL_LEG_OPEN_PERSISTENCE_CHECK=OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
