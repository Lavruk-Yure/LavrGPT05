# run_ib_virtual_leg_group_snapshot_check.py
"""
IB virtual-leg position group snapshot check.

RoadMap90:
- broker net row and nested LGE virtual legs remain separate concepts;
- zero-net reconciled LGE group remains visible;
- broker-only position remains NET_ONLY without invented legs;
- explicit zero broker-only rows are not active position groups;
- leg operations are enabled only for reconciled groups with open legs.
"""

from __future__ import annotations

from engine.ib_position_group import build_ib_position_group_snapshot
from engine.ib_virtual_position_leg import (
    IBVirtualPositionLeg,
    IBVirtualPositionLegReconciliationSnapshot,
)
from engine.runtime_constants import (
    IB_BROKER_POSITION_KIND_NET,
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)

ACCOUNT_ID = "DUM513747"


def _leg(
    *,
    position_uid: str,
    trade_uid: str,
    symbol_name: str,
    side: str,
    volume: float,
    entry_price: float,
    leg_status: str,
    parent_order_id: int,
    stop_loss_order_id: int | None = None,
    take_profit_order_id: int | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    oca_group: str = "",
) -> IBVirtualPositionLeg:
    """
    Build one reconciled synthetic virtual leg.
    """
    protection_status = (
        IB_PROTECTION_STATUS_COMPLETE
        if stop_loss_order_id is not None and take_profit_order_id is not None
        else IB_PROTECTION_STATUS_NONE
    )
    return IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=f"IB:{ACCOUNT_ID}:{symbol_name}",
        account_id=ACCOUNT_ID,
        symbol_name=symbol_name,
        side=side,
        volume=volume,
        entry_price=entry_price,
        opened_utc="2026-07-16T12:00:00+00:00",
        source="MANUAL",
        parent_order_id=parent_order_id,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=oca_group,
        leg_status=leg_status,
        protection_status=protection_status,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def main() -> int:
    """
    Run pure broker-net group construction checks.
    """
    eurusd_id = f"IB:{ACCOUNT_ID}:EURUSD"
    gbpusd_id = f"IB:{ACCOUNT_ID}:GBPUSD"
    usdjpy_id = f"IB:{ACCOUNT_ID}:USDJPY"
    audusd_id = f"IB:{ACCOUNT_ID}:AUDUSD"
    legs = [
        _leg(
            position_uid="EUR-1",
            trade_uid="TRADE-EUR-1",
            symbol_name="EURUSD",
            side="BUY",
            volume=1000.0,
            entry_price=1.14685,
            leg_status=IB_LEG_STATUS_CLOSED,
            parent_order_id=111,
            stop_loss_order_id=113,
            stop_loss=1.144,
            oca_group="1620614043",
        ),
        _leg(
            position_uid="EUR-2",
            trade_uid="TRADE-EUR-2",
            symbol_name="EURUSD",
            side="BUY",
            volume=2000.0,
            entry_price=1.14665,
            leg_status=IB_LEG_STATUS_OPEN,
            parent_order_id=114,
            stop_loss_order_id=116,
            take_profit_order_id=115,
            stop_loss=1.143,
            take_profit=1.152,
            oca_group="1620614047",
        ),
        _leg(
            position_uid="GBP-1",
            trade_uid="TRADE-GBP-1",
            symbol_name="GBPUSD",
            side="BUY",
            volume=3000.0,
            entry_price=1.35225,
            leg_status=IB_LEG_STATUS_CLOSED,
            parent_order_id=117,
            stop_loss_order_id=119,
            stop_loss=1.349,
            oca_group="1620614054",
        ),
        _leg(
            position_uid="GBP-2",
            trade_uid="TRADE-GBP-2",
            symbol_name="GBPUSD",
            side="SELL",
            volume=2000.0,
            entry_price=1.35165,
            leg_status=IB_LEG_STATUS_CLOSED,
            parent_order_id=120,
            take_profit_order_id=121,
            take_profit=1.349,
            oca_group="1620614064",
        ),
    ]
    reconciliation = IBVirtualPositionLegReconciliationSnapshot(
        captured_utc="2026-07-17T09:30:00+00:00",
        complete=True,
        legs=legs,
        group_statuses={
            eurusd_id: IB_RECONCILIATION_STATUS_RECONCILED,
            gbpusd_id: IB_RECONCILIATION_STATUS_RECONCILED,
        },
        group_messages={
            eurusd_id: (),
            gbpusd_id: (),
        },
        unmapped_protective_order_ids=[],
    )
    evidence = {
        "complete": True,
        "positions": [
            {
                "broker_position_id": eurusd_id,
                "account_id": ACCOUNT_ID,
                "symbol_name": "EURUSD",
                "sec_type": "CASH",
                "currency": "USD",
                "signed_quantity": 2000.0,
                "average_cost": 1.14665,
            },
            {
                "broker_position_id": usdjpy_id,
                "account_id": ACCOUNT_ID,
                "symbol_name": "USDJPY",
                "currency": "JPY",
                "signed_quantity": -5000.0,
                "average_cost": 157.25,
            },
            {
                "broker_position_id": audusd_id,
                "account_id": ACCOUNT_ID,
                "symbol_name": "AUDUSD",
                "currency": "USD",
                "signed_quantity": 0.0,
                "average_cost": 0.0,
            },
        ],
    }
    snapshot = build_ib_position_group_snapshot(
        reconciliation_snapshot=reconciliation,
        evidence_snapshot=evidence,
    )
    groups_by_id = {group.broker_position_id: group for group in snapshot.groups}

    if [group.broker_position_id for group in snapshot.groups] != [
        eurusd_id,
        gbpusd_id,
        usdjpy_id,
    ]:
        raise AssertionError("Position group order mismatch")

    eurusd = groups_by_id[eurusd_id]
    gbpusd = groups_by_id[gbpusd_id]
    usdjpy = groups_by_id[usdjpy_id]

    if audusd_id in groups_by_id:
        raise AssertionError("Zero broker-only position remained active")

    if eurusd.group_mode != IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS:
        raise AssertionError("EURUSD group mode mismatch")

    if not eurusd.broker_position_present:
        raise AssertionError("EURUSD broker position should be present")

    if eurusd.broker_side != "BUY" or eurusd.broker_volume != 2000.0:
        raise AssertionError("EURUSD broker-net state mismatch")

    if eurusd.broker_position_kind != (IB_BROKER_POSITION_KIND_VIRTUAL_FX):
        raise AssertionError("EURUSD Virtual FX kind mismatch")

    if eurusd.broker_quantity_is_terminal_truth:
        raise AssertionError("EURUSD Virtual FX was treated as strict net")

    if len(eurusd.open_legs) != 1 or len(eurusd.closed_legs) != 1:
        raise AssertionError("EURUSD leg counts mismatch")

    if eurusd.signed_open_leg_volume != 2000.0:
        raise AssertionError("EURUSD signed open-leg volume mismatch")

    if not eurusd.leg_operations_enabled:
        raise AssertionError("EURUSD leg operations should be enabled")

    if gbpusd.broker_position_present:
        raise AssertionError("GBPUSD zero-net broker row should be absent")

    if gbpusd.reconciliation_status != (IB_RECONCILIATION_STATUS_RECONCILED):
        raise AssertionError("GBPUSD zero-net group status mismatch")

    if gbpusd.leg_operations_enabled:
        raise AssertionError("Closed GBPUSD group must disable leg operations")

    if usdjpy.group_mode != IB_POSITION_GROUP_MODE_NET_ONLY:
        raise AssertionError("USDJPY broker-only mode mismatch")

    if usdjpy.broker_position_kind != IB_BROKER_POSITION_KIND_NET:
        raise AssertionError("USDJPY strict broker kind mismatch")

    if usdjpy.legs:
        raise AssertionError("USDJPY broker-only group invented virtual legs")

    if usdjpy.reconciliation_status != (IB_RECONCILIATION_STATUS_UNRECONCILED):
        raise AssertionError("USDJPY net-only status mismatch")

    if usdjpy.leg_operations_enabled:
        raise AssertionError("USDJPY net-only group enabled leg operations")

    print("IB virtual-leg position group snapshot result")
    print(f"  groups={len(snapshot.groups)}")
    print(f"  eurusd_open_legs={len(eurusd.open_legs)}")
    print(f"  eurusd_closed_legs={len(eurusd.closed_legs)}")
    print(f"  eurusd_leg_operations={eurusd.leg_operations_enabled}")
    print(f"  eurusd_broker_kind={eurusd.broker_position_kind}")
    print(f"  gbpusd_broker_present={gbpusd.broker_position_present}")
    print(f"  usdjpy_mode={usdjpy.group_mode}")
    print(f"  usdjpy_leg_operations={usdjpy.leg_operations_enabled}")
    print("  zero_broker_only_row_hidden=True")
    print("IB_VIRTUAL_LEG_GROUP_SNAPSHOT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
