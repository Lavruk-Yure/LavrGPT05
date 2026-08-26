"""RuntimeEngine recovery check for one unprotected OPEN IB virtual leg."""

from __future__ import annotations

import sys
import tempfile
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
    IB_LEG_ORDER_ROLE_CLOSE,
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import (  # noqa: E402
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)
from tests.runtime_ib import (  # noqa: E402
    run_ib_broker_residual_and_missing_close_evidence_check as fixture,
)

ACCOUNT_ID = fixture.ACCOUNT_ID
USDZAR_ID = fixture.USDZAR_ID


class _EvidenceService(IBRuntimeServiceProtocol):
    """Synthetic read-only IB service for one exact evidence snapshot."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

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
        return deepcopy(self.snapshot)

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


def _create_runtime_leg(
    engine: RuntimeEngine,
    leg: IBVirtualPositionLeg,
) -> str:
    if leg.parent_order_id is None:
        raise AssertionError("Synthetic leg parent order id is missing")

    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol=leg.symbol_name,
        side=leg.side,
        volume=leg.volume,
        source="MANUAL",
        comment="LGE manual UI order",
    )
    order_plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=leg.side,
        volume=leg.volume,
        source="MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id=str(leg.parent_order_id),
        execution_status="FILLED",
        source="MANUAL",
        broker_comment="[LGE:M] LGE manual UI order",
    )
    position_uid = engine.repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=USDZAR_ID,
        symbol=leg.symbol_name,
        side=leg.side,
        volume=leg.volume,
        open_price=leg.entry_price,
        opened_utc=leg.opened_utc,
        source="BROKER",
    )
    persisted_leg = IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=leg.broker_position_id,
        account_id=leg.account_id,
        symbol_name=leg.symbol_name,
        side=leg.side,
        volume=leg.volume,
        entry_price=leg.entry_price,
        opened_utc=leg.opened_utc,
        source=leg.source,
        parent_order_id=leg.parent_order_id,
        stop_loss_order_id=leg.stop_loss_order_id,
        take_profit_order_id=leg.take_profit_order_id,
        stop_loss=leg.stop_loss,
        take_profit=leg.take_profit,
        oca_group=leg.oca_group,
        close_order_ids=leg.close_order_ids,
        leg_status=leg.leg_status,
        protection_status=leg.protection_status,
        reconciliation_status=leg.reconciliation_status,
        reconciliation_messages=leg.reconciliation_messages,
    )
    engine.repository.upsert_ib_virtual_position_leg(persisted_leg)
    engine.repository.set_active_ib_virtual_position_leg_order(
        position_uid=position_uid,
        order_role=IB_LEG_ORDER_ROLE_PARENT,
        broker_order_id=leg.parent_order_id,
        execution_status="FILLED",
        action=leg.side,
        order_type="MKT",
        quantity=leg.volume,
        price=leg.entry_price,
    )

    for order_role, order_id, order_type, price in (
        (
            IB_LEG_ORDER_ROLE_STOP_LOSS,
            leg.stop_loss_order_id,
            "STP",
            leg.stop_loss,
        ),
        (
            IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            leg.take_profit_order_id,
            "LMT",
            leg.take_profit,
        ),
    ):
        if order_id is None:
            continue

        engine.repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=order_role,
            broker_order_id=order_id,
            execution_status="SUBMITTED",
            parent_order_id=leg.parent_order_id,
            client_id=1,
            action=leg.protective_action,
            order_type=order_type,
            quantity=leg.volume,
            price=price,
            oca_group=leg.oca_group,
        )

    for close_order_id in leg.close_order_ids:
        engine.repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_CLOSE,
            broker_order_id=close_order_id,
            execution_status="FILLED",
            action=leg.protective_action,
            order_type="MKT",
            quantity=leg.volume,
        )
        engine.repository.deactivate_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_CLOSE,
            execution_status="FILLED",
        )

    return position_uid


def _evidence() -> dict:
    return fixture.build_snapshot(
        positions=[
            fixture.build_position(USDZAR_ID, "USD", "ZAR", 1000.0)
        ],
        open_orders=[],
        executions=[fixture.build_usdzar_sell_leg_close_execution()],
    )


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="lge_ib_open_exposure_recovery_",
    ) as temporary_directory:
        db_path = Path(temporary_directory) / "runtime.db"
        engine = RuntimeEngine(db_path=str(db_path))

        try:
            open_uid = _create_runtime_leg(engine, fixture.build_usdzar_leg())
            _create_runtime_leg(engine, fixture.build_usdzar_closed_sell_leg())
            engine.set_ib_runtime_service(_EvidenceService(_evidence()))
            engine.set_broker("IB")
            snapshot = engine.sync_active_broker_position_groups()
            group = snapshot.groups[0]
            open_leg = next(
                leg for leg in group.legs if leg.position_uid == open_uid
            )

            if group.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
                raise AssertionError("Recovered broker group is not RECONCILED")

            if open_leg.reconciliation_status != (
                IB_RECONCILIATION_STATUS_RECONCILED
            ):
                raise AssertionError("Recovered OPEN leg is not RECONCILED")

            if open_leg.protection_status != IB_PROTECTION_STATUS_NONE:
                raise AssertionError("Recovered OPEN leg is not unprotected")

            persisted = engine.repository.get_ib_virtual_position_leg(open_uid)

            if persisted is None:
                raise AssertionError("Recovered OPEN leg was not persisted")

            for key in (
                "stop_loss_order_id",
                "take_profit_order_id",
                "stop_loss",
                "take_profit",
            ):
                if persisted[key] is not None:
                    raise AssertionError(f"Recovered state retained {key}")

            if persisted["oca_group"]:
                raise AssertionError("Recovered state retained OCA group")

            active_orders = engine.repository.get_ib_virtual_position_leg_orders(
                open_uid,
                active_only=True,
            )
            active_roles = {
                str(row["order_role"] or "").strip().upper()
                for row in active_orders
            }

            if active_roles != {IB_LEG_ORDER_ROLE_PARENT}:
                raise AssertionError("Stale protective mappings remained active")
        finally:
            engine.connection.close()

        restart_engine = RuntimeEngine(db_path=str(db_path))

        try:
            restart_engine.set_ib_runtime_service(_EvidenceService(_evidence()))
            restart_engine.set_broker("IB")
            restart_snapshot = restart_engine.sync_active_broker_position_groups()
            restart_group = restart_snapshot.groups[0]
            restart_open_leg = next(
                leg
                for leg in restart_group.legs
                if leg.position_uid == open_uid
            )

            if restart_group.reconciliation_status != (
                IB_RECONCILIATION_STATUS_RECONCILED
            ):
                raise AssertionError("Recovered group did not survive restart")

            if restart_open_leg.protection_status != IB_PROTECTION_STATUS_NONE:
                raise AssertionError("Recovered protection did not survive restart")

            if not restart_group.leg_operations_enabled:
                raise AssertionError("Recovered exact leg operations are disabled")
        finally:
            restart_engine.connection.close()

    print("RuntimeEngine IB OPEN exposure recovery result")
    print("  broker_net=BUY 1000")
    print("  recovered_open_leg=BUY 1000")
    print("  reconciliation_status=RECONCILED")
    print("  protection_status=NONE")
    print("  stale_protective_mappings_inactive=True")
    print("  restart_reconciled=True")
    print("  exact_leg_operations=True")
    print("RUNTIME_ENGINE_IB_OPEN_EXPOSURE_RECOVERY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
