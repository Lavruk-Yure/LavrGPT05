"""Regression check for external TWS bracket protection on broker residual."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"
CURRENT_CLIENT_ID = 1


def _protective_order(
    *,
    order_id: int,
    parent_id: int,
    order_type: str,
    same_client_id: bool,
    client_id: int,
    oca_group: str,
) -> dict:
    return {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": "EURUSD",
        "broker_position_id": POSITION_ID,
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": 1.157 if order_type == "LMT" else 0.0,
        "aux_price": 1.145 if order_type == "STP" else 0.0,
        "client_id": client_id,
        "same_client_id": same_client_id,
        "perm_id": order_id + 10000 if order_id > 0 else 90000 + parent_id,
        "oca_group": oca_group,
    }


def main() -> int:
    leg = IBVirtualPositionLeg(
        position_uid="lge-eur-position",
        trade_uid="lge-eur-trade",
        broker_position_id=POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name="EURUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.1525,
        opened_utc="2026-08-03T09:00:00+00:00",
        source="LGE_MANUAL",
        parent_order_id=100,
        stop_loss_order_id=102,
        take_profit_order_id=101,
        oca_group="LGE_100",
    )

    evidence = {
        "broker": "IB",
        "captured_utc": "2026-08-03T09:47:39+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "positions": [
            {
                "broker_position_id": POSITION_ID,
                "signed_quantity": 2000.0,
                "sec_type": "CASH",
            }
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
                "price": 1.1525,
                "time": "20260803 09:00:00",
                "order_id": 100,
                "perm_id": 10100,
            },
            {
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "side": "BOT",
                "shares": 1000.0,
                "price": 1.1528,
                "time": "20260803 09:30:00",
                "order_id": 500,
                "perm_id": 90500,
            }
        ],
        "open_orders": [
            _protective_order(
                order_id=101,
                parent_id=100,
                order_type="LMT",
                same_client_id=True,
                client_id=CURRENT_CLIENT_ID,
                oca_group="LGE_100",
            ),
            _protective_order(
                order_id=102,
                parent_id=100,
                order_type="STP",
                same_client_id=True,
                client_id=CURRENT_CLIENT_ID,
                oca_group="LGE_100",
            ),
            _protective_order(
                order_id=0,
                parent_id=500,
                order_type="LMT",
                same_client_id=False,
                client_id=0,
                oca_group="TWS_500",
            ),
            _protective_order(
                order_id=0,
                parent_id=500,
                order_type="STP",
                same_client_id=False,
                client_id=0,
                oca_group="TWS_500",
            ),
        ],
    }

    snapshot = reconcile_ib_virtual_position_legs([leg], evidence)
    reconciled_leg = snapshot.legs[0]
    residual = snapshot.group_broker_residual_signed_volumes[POSITION_ID]

    print("IB virtual-leg external residual protection result")
    print(f"  status={snapshot.group_statuses[POSITION_ID]}")
    print(f"  protection={reconciled_leg.protection_status}")
    print(f"  residual={residual}")
    print(f"  unmapped={snapshot.unmapped_protective_order_ids}")
    print(f"  group_messages={snapshot.group_messages[POSITION_ID]}")
    print(f"  leg_messages={reconciled_leg.reconciliation_messages}")
    print("  external_tws_protection_read_only=True")

    if snapshot.group_statuses[POSITION_ID] != IB_RECONCILIATION_STATUS_RECONCILED:
        raise AssertionError("External TWS bracket blocked the LGE group")

    if reconciled_leg.protection_status != IB_PROTECTION_STATUS_COMPLETE:
        raise AssertionError("LGE protection was not preserved")

    if residual != 1000.0:
        raise AssertionError("Broker residual quantity differs")

    if snapshot.unmapped_protective_order_ids:
        raise AssertionError("External TWS protection was marked unmapped")

    print("IB_VIRTUAL_LEG_EXTERNAL_RESIDUAL_PROTECTION_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
