"""RuntimeEngine persistence check for mixed IB broker residual exposure."""

from __future__ import annotations

import sys
import tempfile
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
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
EURUSD_ID = fixture.EURUSD_ID


class EvidenceService(IBRuntimeServiceProtocol):
    """Synthetic read-only IB service with replaceable evidence."""

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


def build_live_like_evidence(*, include_external_execution: bool) -> dict[str, Any]:
    executions = (
        [fixture.build_external_execution()] if include_external_execution else []
    )
    return fixture.build_snapshot(
        positions=[fixture.build_position(EURUSD_ID, "EUR", "USD", 2000.0)],
        open_orders=[
            fixture.build_protective_order(
                broker_position_id=EURUSD_ID,
                symbol="EUR",
                currency="USD",
                order_id=195,
                parent_id=194,
                order_type="LMT",
                price=1.136,
                oca_group="1329483705",
            ),
            fixture.build_protective_order(
                broker_position_id=EURUSD_ID,
                symbol="EUR",
                currency="USD",
                order_id=196,
                parent_id=194,
                order_type="STP",
                price=1.144,
                oca_group="1329483705",
            ),
        ],
        executions=executions,
    )


def seed_runtime_position(engine: RuntimeEngine) -> str:
    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol="EURUSD",
        side="SELL",
        volume=1000.0,
        source="MANUAL",
        comment="LGE manual UI order",
    )
    order_plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="SELL",
        volume=1000.0,
        source="MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id="194",
        execution_status="FILLED",
        source="MANUAL",
        broker_comment="[LGE:M] LGE manual UI order",
    )
    position_uid = engine.repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=EURUSD_ID,
        symbol="EURUSD",
        side="SELL",
        volume=1000.0,
        open_price=1.1372,
        opened_utc="20260723 09:26:45 US/Eastern",
        source="BROKER",
    )
    leg = replace(
        fixture.build_eurusd_leg(),
        position_uid=position_uid,
        trade_uid=trade_uid,
    )
    engine.repository.upsert_ib_virtual_position_leg(leg)
    return position_uid


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        first_engine = RuntimeEngine(db_path=str(db_path))

        try:
            position_uid = seed_runtime_position(first_engine)
            first_service = EvidenceService(
                build_live_like_evidence(include_external_execution=True)
            )
            first_engine.set_ib_runtime_service(first_service)
            first_engine.set_broker("IB")
            first_snapshot = first_engine.sync_active_broker_position_groups()
            first_group = first_snapshot.groups[0]

            if first_group.reconciliation_status != (
                IB_RECONCILIATION_STATUS_RECONCILED
            ):
                raise AssertionError("Initial mixed group was not reconciled")

            if first_group.broker_residual_signed_volume != 2000.0:
                raise AssertionError("Initial residual volume differs")

            persisted = first_engine.repository.get_ib_virtual_position_leg(
                position_uid
            )

            if persisted is None:
                raise AssertionError("Managed leg was not persisted")

            messages = list(persisted["reconciliation_messages"])

            if not any(
                message.startswith("BROKER_RESIDUAL: signed_volume=")
                for message in messages
            ):
                raise AssertionError("Residual identity was not persisted")
        finally:
            first_engine.connection.close()

        restart_engine = RuntimeEngine(db_path=str(db_path))

        try:
            restart_service = EvidenceService(
                build_live_like_evidence(include_external_execution=False)
            )
            restart_engine.set_ib_runtime_service(restart_service)
            restart_engine.set_broker("IB")
            restart_snapshot = restart_engine.sync_active_broker_position_groups()
            restart_group = restart_snapshot.groups[0]

            if restart_group.reconciliation_status != (
                IB_RECONCILIATION_STATUS_RECONCILED
            ):
                raise AssertionError("Restarted residual group was blocked")

            if restart_group.broker_residual_signed_volume != 2000.0:
                raise AssertionError("Restarted residual volume differs")

            if not restart_group.leg_operations_enabled:
                raise AssertionError("Restart disabled exact leg operations")
        finally:
            restart_engine.connection.close()

    print("RuntimeEngine IB broker residual persistence result")
    print("  virtual_fx_observation=BUY 2000")
    print("  managed_leg=SELL 1000")
    print("  exact_non_lge_execution=BUY 2000")
    print("  broker_residual=BUY 2000")
    print("  residual_identity_persisted=True")
    print("  restart_without_execution_history=True")
    print("  exact_leg_operations=True")
    print("RUNTIME_ENGINE_IB_BROKER_RESIDUAL_PERSISTENCE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
