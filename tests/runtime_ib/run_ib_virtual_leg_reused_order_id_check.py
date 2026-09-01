# run_ib_virtual_leg_reused_order_id_check.py
"""Regression check for IB orderId reuse across adapter sessions."""

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
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"
CURRENT_CLIENT_ID = 1


def _order(
    order_id: int,
    parent_id: int,
    perm_id: int,
    order_type: str,
    price: float,
) -> dict:
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "perm_id": perm_id,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "symbol_name": "EURUSD",
        "broker_position_id": POSITION_ID,
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "oca_group": "963655516",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def main() -> int:
    old_closed_leg = IBVirtualPositionLeg(
        position_uid="old-closed-leg",
        trade_uid="old-closed-trade",
        broker_position_id=POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name="EURUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.1515,
        opened_utc="20260731 03:59:51 US/Eastern",
        source="MANUAL",
        parent_order_id=243,
        stop_loss_order_id=245,
        take_profit_order_id=244,
        stop_loss=1.15,
        take_profit=1.155,
        oca_group="1900828147",
        parent_order_perm_id=1900828147,
        stop_loss_order_perm_id=1900828149,
        take_profit_order_perm_id=1900828148,
        leg_status=IB_LEG_STATUS_CLOSED,
        protection_status=IB_PROTECTION_STATUS_NONE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    current_open_leg = IBVirtualPositionLeg(
        position_uid="current-open-leg",
        trade_uid="current-open-trade",
        broker_position_id=POSITION_ID,
        account_id=ACCOUNT_ID,
        symbol_name="EURUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.15285,
        opened_utc="20260803 02:38:22 US/Eastern",
        source="MANUAL",
        parent_order_id=243,
        stop_loss_order_id=245,
        take_profit_order_id=244,
        stop_loss=1.145,
        take_profit=1.157,
        oca_group="963655516",
        parent_order_perm_id=963655516,
        stop_loss_order_perm_id=963655518,
        take_profit_order_perm_id=963655517,
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    evidence = {
        "captured_utc": "2026-08-03T07:07:33+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "positions": [
            {
                "broker_position_id": POSITION_ID,
                "signed_quantity": 1000.0,
            }
        ],
        "executions": [
            {
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "side": "BOT",
                "shares": 1000.0,
                "price": 1.15285,
                "time": "20260803 02:38:22 US/Eastern",
                "order_id": 243,
                "perm_id": 963655516,
            }
        ],
        "open_orders": [
            _order(245, 243, 963655518, "STP", 1.145),
            _order(244, 243, 963655517, "LMT", 1.157),
        ],
        "completed_orders": [],
    }

    snapshot = reconcile_ib_virtual_position_legs(
        legs=[old_closed_leg, current_open_leg],
        evidence_snapshot=evidence,
    )
    old_after, current_after = snapshot.legs

    old_closed_stays_reconciled = (
        old_after.leg_status == IB_LEG_STATUS_CLOSED
        and old_after.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
        and old_after.protection_status == IB_PROTECTION_STATUS_NONE
    )
    current_open_owns_protection = (
        current_after.leg_status == IB_LEG_STATUS_OPEN
        and current_after.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
        and current_after.protection_status == IB_PROTECTION_STATUS_COMPLETE
    )
    group_reconciled = (
        snapshot.group_statuses[POSITION_ID] == IB_RECONCILIATION_STATUS_RECONCILED
    )
    no_unmapped_protection = not snapshot.unmapped_protective_order_ids

    print("IB virtual-leg reused orderId result")
    print("  reused_order_ids=[243, 244, 245]")
    print("  old_parent_perm_id=1900828147")
    print("  current_parent_perm_id=963655516")
    print(f"  old_closed_stays_reconciled={old_closed_stays_reconciled}")
    print(f"  current_open_owns_protection={current_open_owns_protection}")
    print(f"  group_reconciled={group_reconciled}")
    print(f"  no_unmapped_protection={no_unmapped_protection}")

    if not all(
        (
            old_closed_stays_reconciled,
            current_open_owns_protection,
            group_reconciled,
            no_unmapped_protection,
        )
    ):
        raise AssertionError("IB reused orderId reconciliation differs")

    print("IB_VIRTUAL_LEG_REUSED_ORDER_ID_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
