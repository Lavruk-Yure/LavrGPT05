"""Regression: broker-filled LGE TP must not become external IB FX exposure.

Covers the live failure seen after an LGE-owned EURUSD leg was closed by its
broker-side TP on a later trading day:
- the current CASH Virtual FX row can contain only the SELL close flow;
- historical/cross-session execution evidence can return orderId=0;
- stable permId still proves that the fill belongs to the persisted LGE child;
- after persistence, a repeated refresh must retain the CLOSED leg as evidence
  and must not surface NET_ONLY/external exposure or require manual recovery.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_position_group import build_ib_position_group_snapshot  # noqa: E402
from engine.ib_virtual_position_leg import IBVirtualPositionLeg  # noqa: E402
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine  # noqa: E402

ACCOUNT_ID = "DUM513747"
BROKER_POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"
CURRENT_CLIENT_ID = 1
PARENT_ORDER_ID = 243
STOP_LOSS_ORDER_ID = 245
TAKE_PROFIT_ORDER_ID = 244
PARENT_PERM_ID = 963655516
STOP_LOSS_PERM_ID = 963655518
TAKE_PROFIT_PERM_ID = 963655517
OCA_GROUP = "963655516"


class EvidenceService(IBRuntimeServiceProtocol):
    """Read-only synthetic IB service; every broker operation is forbidden."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.evidence_calls = 0

    @staticmethod
    def _unexpected(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected IB broker operation: {method_name}")

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

    def place_market_order(self, *args, **kwargs) -> dict:
        del args, kwargs
        self._unexpected("place_market_order")

    def close_position(self, *args, **kwargs) -> dict:
        del args, kwargs
        self._unexpected("close_position")

    def modify_position_sl_tp(self, *args, **kwargs) -> dict:
        del args, kwargs
        self._unexpected("modify_position_sl_tp")

    def close_virtual_position_leg(self, *args, **kwargs) -> dict:
        del args, kwargs
        self._unexpected("close_virtual_position_leg")

    def modify_virtual_position_leg_sl_tp(self, *args, **kwargs) -> dict:
        del args, kwargs
        self._unexpected("modify_virtual_position_leg_sl_tp")


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
        open_price=1.15285,
        opened_utc="2026-08-03T02:38:22+00:00",
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
        entry_price=1.15285,
        opened_utc="20260803 02:38:22 US/Eastern",
        source="MANUAL",
        parent_order_id=PARENT_ORDER_ID,
        stop_loss_order_id=STOP_LOSS_ORDER_ID,
        take_profit_order_id=TAKE_PROFIT_ORDER_ID,
        stop_loss=1.145,
        take_profit=1.157,
        oca_group=OCA_GROUP,
        parent_order_perm_id=PARENT_PERM_ID,
        stop_loss_order_perm_id=STOP_LOSS_PERM_ID,
        take_profit_order_perm_id=TAKE_PROFIT_PERM_ID,
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def _protective_order(
    order_id: int,
    perm_id: int,
    order_type: str,
    price: float,
) -> dict[str, Any]:
    row = {
        "order_id": order_id,
        "perm_id": perm_id,
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
        "oca_group": OCA_GROUP,
        "oca_type": 3,
        "order_ref": "[LGE:M] LGE manual UI order",
        "status": "Submitted",
    }
    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price
    return row


def _initial_evidence() -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-08-03T06:38:24+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": [],
        "open_orders": [
            _protective_order(
                STOP_LOSS_ORDER_ID,
                STOP_LOSS_PERM_ID,
                "STP",
                1.145,
            ),
            _protective_order(
                TAKE_PROFIT_ORDER_ID,
                TAKE_PROFIT_PERM_ID,
                "LMT",
                1.157,
            ),
        ],
        "completed_orders": [],
        "executions": [
            {
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "side": "BOT",
                "shares": 1000.0,
                "price": 1.15285,
                "time": "20260803 02:38:22 US/Eastern",
                "order_id": PARENT_ORDER_ID,
                "perm_id": PARENT_PERM_ID,
            }
        ],
    }


def _broker_tp_evidence() -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-08-07T12:35:00+00:00",
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
                "broker_position_id": BROKER_POSITION_ID,
                "account_id": ACCOUNT_ID,
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "symbol_name": "EURUSD",
                "sec_type": "CASH",
                "signed_quantity": -1000.0,
                "position": -1000.0,
            }
        ],
        "open_orders": [],
        "completed_orders": [],
        "executions": [
            {
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "side": "SLD",
                "shares": 1000.0,
                "price": 1.157,
                "time": "20260807 08:34:51 US/Eastern",
                # Historical/cross-session evidence can lose local orderId.
                "order_id": 0,
                "perm_id": TAKE_PROFIT_PERM_ID,
            }
        ],
    }


def _assert_no_external(snapshot) -> None:
    if snapshot.group_statuses[BROKER_POSITION_ID] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("Broker TP close did not remain RECONCILED")

    if snapshot.group_broker_residual_signed_volumes.get(
        BROKER_POSITION_ID,
        0.0,
    ) != 0.0:
        raise AssertionError("LGE TP close became broker residual exposure")

    exposure = snapshot.group_external_exposures.get(BROKER_POSITION_ID)
    if exposure is not None and exposure.is_active:
        raise AssertionError("LGE TP close became external IB FX exposure")


def main() -> int:
    engine = RuntimeEngine(db_path=":memory:")

    try:
        trade_uid, position_uid = _create_runtime_chain(engine)
        leg = _open_leg(trade_uid, position_uid)
        engine.repository.persist_confirmed_ib_virtual_position_leg_open(
            leg=leg,
            evidence_snapshot=_initial_evidence(),
            parent_order_ref="[LGE:M] LGE manual UI order",
        )

        service = EvidenceService(_broker_tp_evidence())
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")

        first = engine.sync_reconciled_ib_virtual_position_legs()
        first_snapshot = first["snapshot"]
        _assert_no_external(first_snapshot)

        if len(first_snapshot.legs) != 1:
            raise AssertionError("Expected exactly one LGE leg on first sync")

        if first_snapshot.legs[0].leg_status != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Broker TP did not close the LGE leg")

        # Critical live regression: after CLOSED is persisted, the next refresh
        # must still load that leg via stable permId evidence. Otherwise the
        # current CASH row is misclassified as NET_ONLY external exposure.
        second = engine.sync_reconciled_ib_virtual_position_legs()
        second_snapshot = second["snapshot"]
        _assert_no_external(second_snapshot)

        if len(second_snapshot.legs) != 1:
            raise AssertionError(
                "Closed LGE leg was not retained for current CASH evidence"
            )

        if second_snapshot.legs[0].leg_status != IB_LEG_STATUS_CLOSED:
            raise AssertionError("Repeated refresh reopened the closed LGE leg")

        position_groups = build_ib_position_group_snapshot(
            reconciliation_snapshot=second_snapshot,
            evidence_snapshot=service.snapshot,
        )
        if position_groups.groups:
            raise AssertionError(
                "Managed broker TP close leaked back as active NET_ONLY row"
            )

        print("RuntimeEngine IB broker protective-fill no-external result")
        print("  close_trigger=TAKE_PROFIT")
        print("  historical_execution_order_id=0")
        print(f"  stable_perm_id={TAKE_PROFIT_PERM_ID}")
        print("  first_sync_closed=True")
        print("  first_sync_external_exposure=False")
        print("  repeated_refresh_closed_leg_retained=True")
        print("  repeated_refresh_external_exposure=False")
        print("  net_only_created=False")
        print("  active_position_group_rows=0")
        print("  manual_reconciliation_required=False")
        print(f"  evidence_calls={service.evidence_calls}")
        print("  broker_execution_attempted=False")
        print("RUNTIME_ENGINE_IB_BROKER_PROTECTIVE_FILL_NO_EXTERNAL_CHECK=OK")
        return 0
    finally:
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
