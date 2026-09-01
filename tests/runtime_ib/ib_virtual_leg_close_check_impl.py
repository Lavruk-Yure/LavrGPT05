"""RoadMap90 exact IB virtual-leg Close persistence check."""

from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

from engine.ib_order_errors import (
    IBMarketOrderTimeoutError,
    IBVirtualLegCloseConfirmationPendingError,
)
from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_CLOSE,
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "EURUSD"
POSITION_ID = f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}"
POSITION_SIDE = "SELL"
VOLUME = 1000.0
PARENT_ID = 501
TP_ID = 502
SL_ID = 503
CLOSE_ID = 504
STOP_LOSS = 1.15
TAKE_PROFIT = 1.14
OCA_GROUP = "OCA_502_503"
CURRENT_CLIENT_ID = 1


class DummyIBRuntimeService(IBRuntimeServiceProtocol):
    """Synthetic exact virtual-leg close service."""

    def __init__(
        self,
        pre_virtual_fx_quantity: float = 0.0,
        post_virtual_fx_quantity: float = VOLUME,
        timeout_close: bool = False,
        close_evidence_after_call: int = 0,
    ) -> None:
        self.evidence_calls = 0
        self.close_calls = 0
        self.pre_virtual_fx_quantity = pre_virtual_fx_quantity
        self.post_virtual_fx_quantity = post_virtual_fx_quantity
        self.timeout_close = bool(timeout_close)
        self.close_evidence_after_call = int(close_evidence_after_call)

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
        expected = (
            POSITION_ID,
            ACCOUNT_ID,
            SYMBOL_NAME,
            POSITION_SIDE,
            VOLUME,
            PARENT_ID,
            SL_ID,
            TP_ID,
            OCA_GROUP,
        )
        actual = (
            position_id,
            account_id,
            symbol_name,
            position_side,
            position_volume,
            parent_order_id,
            stop_loss_order_id,
            take_profit_order_id,
            current_oca_group,
        )

        if not position_uid or actual != expected:
            raise AssertionError("Virtual-leg Close context differs")

        if comment != "LGE virtual-leg close":
            raise AssertionError("Virtual-leg Close comment differs")

        self.close_calls += 1

        if self.timeout_close:
            raise IBMarketOrderTimeoutError(
                order_id=CLOSE_ID,
                symbol_name=SYMBOL_NAME,
                side="BUY",
                quantity=VOLUME,
                status="SUBMITTED",
                filled=0.0,
                remaining=VOLUME,
            )

        return {
            "position_uid": position_uid,
            "broker_position_id": position_id,
            "close_side": "BUY",
            "close_quantity": VOLUME,
            "close_order_id": str(CLOSE_ID),
            "cancelled_order_ids": [TP_ID, SL_ID],
            "broker_result": {
                "parent_order_id": str(CLOSE_ID),
                "status": "FILLED",
            },
        }

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        self.evidence_calls += 1
        return deepcopy(
            _build_evidence(
                closed=(
                    self.close_calls > 0
                    and self.evidence_calls > self.close_evidence_after_call
                ),
                pre_virtual_fx_quantity=(self.pre_virtual_fx_quantity),
                post_virtual_fx_quantity=(self.post_virtual_fx_quantity),
            )
        )


class MixedGroupCloseService(DummyIBRuntimeService):
    """Expose one exact target beside a sibling with missing close evidence."""

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        evidence = super().get_virtual_position_leg_evidence_snapshot()
        evidence["executions"].append(
            _execution(
                511,
                "SLD",
                1.1418,
                "20260717 13:10:00 UTC",
            )
        )
        return evidence


def _order(order_id: int, order_type: str, price: float) -> dict[str, Any]:
    return {
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
        "lmt_price": price if order_type == "LMT" else 0.0,
        "aux_price": price if order_type == "STP" else 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "perm_id": order_id + 10000,
        "same_client_id": True,
        "oca_group": OCA_GROUP,
        "oca_type": 1,
        "status": "Submitted",
    }


def _execution(
    order_id: int,
    side: str,
    price: float,
    time_value: str,
) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "perm_id": order_id + 10000,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": POSITION_ID,
        "side": side,
        "shares": VOLUME,
        "price": price,
        "time": time_value,
    }


def _completed_close_order() -> dict[str, Any]:
    return {
        "order_id": CLOSE_ID,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": POSITION_ID,
        "action": "BUY",
        "order_type": "MKT",
        "total_quantity": VOLUME,
        "parent_id": 0,
        "client_id": CURRENT_CLIENT_ID,
        "perm_id": CLOSE_ID + 10000,
        "same_client_id": True,
        "order_ref": "LGE virtual-leg close",
        "status": "Filled",
        "completed_status": "Filled",
        "filled": VOLUME,
        "remaining": 0.0,
    }


def _build_evidence(
    closed: bool,
    pre_virtual_fx_quantity: float = 0.0,
    post_virtual_fx_quantity: float = VOLUME,
) -> dict[str, Any]:
    open_orders = (
        []
        if closed
        else [
            _order(SL_ID, "STP", STOP_LOSS),
            _order(TP_ID, "LMT", TAKE_PROFIT),
        ]
    )
    executions = [_execution(PARENT_ID, "SLD", 1.1426, "20260717 13:07:10 UTC")]

    if closed:
        executions.append(_execution(CLOSE_ID, "BOT", 1.1440, "20260717 15:50:00 UTC"))

    return {
        "broker": "IB",
        "captured_utc": "2026-07-17T15:50:01+00:00",
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
                "signed_quantity": (
                    post_virtual_fx_quantity if closed else pre_virtual_fx_quantity
                ),
                "side": (
                    "BUY"
                    if (post_virtual_fx_quantity if closed else pre_virtual_fx_quantity)
                    > 0.0
                    else (
                        "SELL"
                        if (
                            post_virtual_fx_quantity
                            if closed
                            else pre_virtual_fx_quantity
                        )
                        < 0.0
                        else "UNKNOWN"
                    )
                ),
                "volume": abs(
                    post_virtual_fx_quantity if closed else pre_virtual_fx_quantity
                ),
                "average_cost": 0.0,
            }
        ],
        "open_orders": open_orders,
        "completed_orders": ([_completed_close_order()] if closed else []),
        "executions": executions,
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
        stop_loss_order_id=SL_ID,
        take_profit_order_id=TP_ID,
        stop_loss=STOP_LOSS,
        take_profit=TAKE_PROFIT,
        oca_group=OCA_GROUP,
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
        (IB_LEG_ORDER_ROLE_STOP_LOSS, SL_ID, "STP", STOP_LOSS),
        (IB_LEG_ORDER_ROLE_TAKE_PROFIT, TP_ID, "LMT", TAKE_PROFIT),
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
            action=POSITION_SIDE if role == IB_LEG_ORDER_ROLE_PARENT else "BUY",
            order_type=order_type,
            quantity=VOLUME,
            price=price,
            oca_group="" if role == IB_LEG_ORDER_ROLE_PARENT else OCA_GROUP,
            oca_type=None if role == IB_LEG_ORDER_ROLE_PARENT else 1,
        )

    return position_uid


def _create_missing_close_sibling(engine: RuntimeEngine) -> str:
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
        broker_order_id="511",
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
        open_price=1.1418,
        opened_utc="2026-07-17T13:10:00+00:00",
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
        entry_price=1.1418,
        opened_utc="2026-07-17T13:10:00+00:00",
        source="LGE_MANUAL",
        parent_order_id=511,
        stop_loss_order_id=512,
        take_profit_order_id=513,
        stop_loss=1.15,
        take_profit=1.139,
        oca_group="OCA_512_513",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    engine.repository.upsert_ib_virtual_position_leg(
        leg,
        remaining_volume=VOLUME,
    )

    for role, order_id, order_type, price in (
        (IB_LEG_ORDER_ROLE_PARENT, 511, "MKT", 1.1418),
        (IB_LEG_ORDER_ROLE_STOP_LOSS, 512, "STP", 1.15),
        (IB_LEG_ORDER_ROLE_TAKE_PROFIT, 513, "LMT", 1.139),
    ):
        engine.repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=role,
            broker_order_id=order_id,
            execution_status=(
                "FILLED" if role == IB_LEG_ORDER_ROLE_PARENT else "SUBMITTED"
            ),
            parent_order_id=(None if role == IB_LEG_ORDER_ROLE_PARENT else 511),
            client_id=CURRENT_CLIENT_ID,
            action=POSITION_SIDE if role == IB_LEG_ORDER_ROLE_PARENT else "BUY",
            order_type=order_type,
            quantity=VOLUME,
            price=price,
            oca_group=("" if role == IB_LEG_ORDER_ROLE_PARENT else "OCA_512_513"),
            oca_type=None if role == IB_LEG_ORDER_ROLE_PARENT else 1,
        )

    return position_uid


def _run_mixed_group_close_case(db_path: Path) -> None:
    engine = RuntimeEngine(db_path=str(db_path))
    service = MixedGroupCloseService()

    try:
        target_uid = _create_leg(engine)
        sibling_uid = _create_missing_close_sibling(engine)
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        result = engine.close_runtime_position_leg(target_uid)

        if result["snapshot"].group_statuses[POSITION_ID] != (
            IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
        ):
            raise AssertionError("Mixed Close group warning was lost")

        target = engine.repository.get_ib_virtual_position_leg(target_uid)
        sibling = engine.repository.get_ib_virtual_position_leg(sibling_uid)

        if target is None or target["leg_status"] != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Mixed-group exact Close was not persisted")

        if sibling is None or sibling["leg_status"] != IB_LEG_STATUS_OPEN:
            raise AssertionError("Mixed-group sibling was changed")
    finally:
        engine.connection.close()


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService()

        try:
            position_uid = _create_leg(engine)
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            result = engine.close_runtime_position_leg(position_uid)
            row = engine.repository.get_ib_virtual_position_leg(position_uid)

            if row is None:
                raise AssertionError("Closed virtual leg persistence is missing")

            if row["leg_status"] != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Virtual leg was not persisted CLOSED")

            if float(row["remaining_volume"]) != 0.0:
                raise AssertionError("Closed virtual leg remaining volume differs")

            active_rows = engine.repository.get_ib_virtual_position_leg_orders(
                position_uid,
                active_only=True,
            )
            active_roles = {str(item["order_role"]) for item in active_rows}

            if active_roles != {IB_LEG_ORDER_ROLE_PARENT}:
                raise AssertionError("Protective mapping remained active")

            history = engine.repository.get_ib_virtual_position_leg_orders(
                position_uid,
                active_only=False,
            )
            close_rows = [
                item
                for item in history
                if item["order_role"] == IB_LEG_ORDER_ROLE_CLOSE
            ]

            if len(close_rows) != 1:
                raise AssertionError("Close order history differs")

            if int(close_rows[0]["broker_order_id"]) != CLOSE_ID:
                raise AssertionError("Persisted close order ID differs")

            if service.close_calls != 1 or service.evidence_calls != 2:
                raise AssertionError("Unexpected service call counts")

            if result["leg_status"] != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Close result leg status differs")

            evidence_calls_before_idle_recovery = service.evidence_calls
            idle_recovery = engine.recover_pending_runtime_position_leg_closes()

            if idle_recovery != {
                "pending": 0,
                "recovered": [],
                "unresolved": [],
            }:
                raise AssertionError("Idle pending-Close recovery result differs")

            if service.evidence_calls != evidence_calls_before_idle_recovery:
                raise AssertionError("Idle recovery requested broker evidence")

            print("RuntimeEngine IB virtual-leg Close result")
            print(f"  position_uid={position_uid}")
            print(f"  close_order_id={result['close_order_id']}")
            print(f"  close_side={result['close_side']}")
            print(f"  close_quantity={result['close_quantity']}")
            print(f"  leg_status={result['leg_status']}")
            print(f"  active_order_mappings={len(active_rows)}")
            print(f"  order_history_rows={len(history)}")
            print(f"  evidence_calls={service.evidence_calls}")
            print(f"  close_calls={service.close_calls}")
            print("  idle_recovery_broker_calls=0")
            print(
                "  cash_fx_virtual_observation_offset="
                f"{result['cash_fx_virtual_observation_offset']}"
            )
        finally:
            engine.connection.close()

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_nonzero_offset_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService(
            pre_virtual_fx_quantity=VOLUME,
            post_virtual_fx_quantity=VOLUME * 2.0,
        )

        try:
            position_uid = _create_leg(engine)
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            result = engine.close_runtime_position_leg(position_uid)

            if result["leg_status"] != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Nonzero-offset Close did not close the leg")

            if result["cash_fx_virtual_observation_offset"] != 2000.0:
                raise AssertionError("Nonzero pre-Close CASH FX offset differs")

            print("  cash_fx_nonzero_offset_close_reconciled=True")
        finally:
            engine.connection.close()

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_offset_block_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService(
            post_virtual_fx_quantity=VOLUME * 2.0,
        )

        try:
            position_uid = _create_leg(engine)
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            blocked = False

            try:
                engine.close_runtime_position_leg(position_uid)
            except RuntimeError as error:
                blocked = "observation offset changed" in str(error)

            if not blocked:
                raise AssertionError(
                    "Unexpected CASH FX observation offset was not blocked"
                )

            row = engine.repository.get_ib_virtual_position_leg(position_uid)

            if row is None or row["leg_status"] != IB_LEG_STATUS_OPEN:
                raise AssertionError("Blocked Close changed virtual-leg persistence")

            print("  unexpected_cash_fx_offset_blocked=True")
        finally:
            engine.connection.close()

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_recovery_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService()
        service.close_calls = 1

        try:
            position_uid = _create_leg(engine)
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            result = engine.recover_confirmed_runtime_position_leg_close(
                position_uid=position_uid,
                close_order_id=CLOSE_ID,
            )
            row = engine.repository.get_ib_virtual_position_leg(position_uid)

            if row is None or row["leg_status"] != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Recovered virtual leg is not CLOSED")

            if result.get("already_recovered") is not False:
                raise AssertionError("Recovery result flag differs")

            if service.close_calls != 1:
                raise AssertionError("Recovery sent another broker Close")

            print("  recovered_close_order_id=" f"{result['close_order_id']}")
            print(
                "  recovery_cash_fx_offset="
                f"{result['cash_fx_virtual_observation_offset']}"
            )
        finally:
            engine.connection.close()

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_timeout_auto_recovery_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))
        service = DummyIBRuntimeService(timeout_close=True)

        try:
            position_uid = _create_leg(engine)
            engine.set_ib_runtime_service(service)
            engine.set_broker("IB")
            result = engine.close_runtime_position_leg(position_uid)
            row = engine.repository.get_ib_virtual_position_leg(position_uid)
            pending_rows = (
                engine.repository.get_pending_ib_virtual_position_leg_close_orders()
            )

            if row is None or row["leg_status"] != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Timeout Close was not recovered automatically")

            if not result.get("automatic_timeout_recovery"):
                raise AssertionError("Automatic timeout recovery flag differs")

            if pending_rows:
                raise AssertionError("Recovered timeout Close remained pending")

            if service.close_calls != 1:
                raise AssertionError("Automatic recovery sent a duplicate Close")

            print("  timeout_close_auto_recovered=True")
            print(
                "  timeout_recovery_attempts=" f"{result['timeout_recovery_attempts']}"
            )
        finally:
            engine.connection.close()

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_timeout_refresh_recovery_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        service = DummyIBRuntimeService(
            timeout_close=True,
            close_evidence_after_call=100,
        )
        first_engine = RuntimeEngine(db_path=str(db_path))
        pending_error = None

        try:
            position_uid = _create_leg(first_engine)
            first_engine.set_ib_runtime_service(service)
            first_engine.set_broker("IB")

            try:
                first_engine.close_runtime_position_leg(position_uid)
            except IBVirtualLegCloseConfirmationPendingError as error:
                pending_error = error

            if pending_error is None:
                raise AssertionError("Delayed Close did not enter pending state")

            pending_rows = (
                first_engine.repository.get_pending_ib_virtual_position_leg_close_orders()
            )

            if len(pending_rows) != 1:
                raise AssertionError("Pending Close mapping was not persisted")

            if service.close_calls != 1:
                raise AssertionError("Pending Close sent more than one broker order")

            unresolved_recovery = (
                first_engine.recover_pending_runtime_position_leg_closes()
            )
            blocked_snapshot = first_engine.get_active_broker_position_groups()
            blocked_groups = [
                group
                for group in blocked_snapshot.groups
                if group.broker_position_id == POSITION_ID
            ]

            if unresolved_recovery.get("recovered"):
                raise AssertionError("Unconfirmed Close was recovered prematurely")

            if not unresolved_recovery.get("unresolved"):
                raise AssertionError("Pending Close was not reported unresolved")

            if (
                len(blocked_groups) != 1
                or blocked_groups[0].reconciliation_status != "BLOCKED"
            ):
                raise AssertionError("Pending Close did not block the group")

            if service.close_calls != 1:
                raise AssertionError("Blocked Refresh sent a duplicate Close")
        finally:
            first_engine.connection.close()

        service.close_evidence_after_call = 0
        restarted_engine = RuntimeEngine(db_path=str(db_path))

        try:
            restarted_engine.set_ib_runtime_service(service)
            restarted_engine.set_broker("IB")
            refresh_recovery = (
                restarted_engine.recover_pending_runtime_position_leg_closes()
            )
            snapshot = restarted_engine.get_active_broker_position_groups()
            row = restarted_engine.repository.get_ib_virtual_position_leg(position_uid)
            pending_rows = (
                restarted_engine.repository.get_pending_ib_virtual_position_leg_close_orders()
            )

            if row is None or row["leg_status"] != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Restart Refresh did not recover pending Close")

            if pending_rows:
                raise AssertionError("Restart-recovered Close remained pending")

            if refresh_recovery.get("recovered") != [CLOSE_ID]:
                raise AssertionError("Restart recovery result differs")

            open_leg_count = sum(len(group.open_legs) for group in snapshot.groups)

            if open_leg_count != 0:
                raise AssertionError("Recovered Close remained visible as OPEN")

            if service.close_calls != 1:
                raise AssertionError("Restart recovery sent a duplicate Close")

            print("  timeout_close_pending_saved=True")
            print("  timeout_close_blocked_without_evidence=True")
            print("  timeout_close_restart_recovered=True")
            print("  pending_close_order_id=" f"{pending_error.close_order_id}")
        finally:
            restarted_engine.connection.close()

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_close_mixed_group_",
    ) as temporary_directory:
        _run_mixed_group_close_case(Path(temporary_directory) / "runtime.db")
        print("  mixed_group_exact_leg_close=True")

    print("RUNTIME_ENGINE_IB_VIRTUAL_LEG_CLOSE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
