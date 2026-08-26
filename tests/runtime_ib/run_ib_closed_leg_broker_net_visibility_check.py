"""IB historical CLOSED leg with active broker NET visibility regression."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_position_group import (  # noqa: E402
    build_ib_position_group_snapshot,
)
from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
    IBVirtualPositionLegReconciliationSnapshot,
)
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_CLOSED,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)

BROKER_POSITION_ID = "IB:DUM513747:EURUSD"


def _build_closed_leg() -> IBVirtualPositionLeg:
    """Build the historical CLOSED EURUSD leg from the live scenario."""
    return IBVirtualPositionLeg(
        position_uid="44444444-4444-4444-4444-444444444444",
        trade_uid="dddddddd-dddd-dddd-dddd-dddddddddddd",
        broker_position_id=BROKER_POSITION_ID,
        account_id="DUM513747",
        symbol_name="EURUSD",
        side="SELL",
        volume=1000.0,
        entry_price=1.145,
        opened_utc="2026-07-27T08:00:00+00:00",
        source="LGE_MANUAL",
        parent_order_id=194,
        stop_loss_order_id=196,
        take_profit_order_id=195,
        stop_loss=1.15,
        take_profit=1.13,
        oca_group="1329483705",
        leg_status=IB_LEG_STATUS_CLOSED,
        protection_status=IB_PROTECTION_STATUS_NONE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        reconciliation_messages=(),
    )


def _build_reconciliation() -> IBVirtualPositionLegReconciliationSnapshot:
    """Build one reconciled historical CLOSED leg snapshot."""
    return IBVirtualPositionLegReconciliationSnapshot(
        captured_utc="2026-07-28T08:02:41+00:00",
        complete=True,
        legs=[_build_closed_leg()],
        group_statuses={
            BROKER_POSITION_ID: IB_RECONCILIATION_STATUS_RECONCILED,
        },
        group_messages={
            BROKER_POSITION_ID: (
                "Historical closed LGE leg was reconciled",
            ),
        },
        unmapped_protective_order_ids=[],
        group_broker_residual_signed_volumes={BROKER_POSITION_ID: 0.0},
    )


def _build_evidence(*, broker_present: bool) -> dict[str, object]:
    """Build complete CASH evidence with optional active BUY 1K row."""
    positions: list[dict[str, object]] = []

    if broker_present:
        positions.append(
            {
                "broker_position_id": BROKER_POSITION_ID,
                "account_id": "DUM513747",
                "symbol_name": "EURUSD",
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": 1000.0,
                "average_cost": 1.1393,
                "current_price": 1.13705,
                "unrealized_pnl": -2.25,
            }
        )

    return {
        "complete": True,
        "positions": positions,
        "open_orders": [],
        "completed_orders": [],
        "executions": [],
    }


def main() -> int:
    """Verify active NET reclassification without losing history-only state."""
    reconciliation = _build_reconciliation()
    active_snapshot = build_ib_position_group_snapshot(
        reconciliation_snapshot=reconciliation,
        evidence_snapshot=_build_evidence(broker_present=True),
    )
    active_group = active_snapshot.groups[0]

    if active_group.group_mode != IB_POSITION_GROUP_MODE_NET_ONLY:
        raise AssertionError("Active broker NET was not reclassified")

    if active_group.legs:
        raise AssertionError("Historical CLOSED legs leaked into NET_ONLY")

    if active_group.reconciliation_status != (
        IB_RECONCILIATION_STATUS_UNRECONCILED
    ):
        raise AssertionError("Broker NET reconciliation status differs")

    if not active_group.broker_position_present:
        raise AssertionError("Active broker row was lost")

    if active_group.broker_position_kind != (
        IB_BROKER_POSITION_KIND_VIRTUAL_FX
    ):
        raise AssertionError("IB CASH broker kind differs")

    if active_group.display_side != "BUY":
        raise AssertionError("Active broker side differs")

    if active_group.display_volume != 1000.0:
        raise AssertionError("Active broker volume differs")

    if active_group.broker_residual_present:
        raise AssertionError("NET_ONLY row created a duplicate residual")

    historical_snapshot = build_ib_position_group_snapshot(
        reconciliation_snapshot=reconciliation,
        evidence_snapshot=_build_evidence(broker_present=False),
    )
    historical_group = historical_snapshot.groups[0]

    if historical_group.group_mode != (
        IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS
    ):
        raise AssertionError("Historical-only group mode changed")

    if historical_group.broker_position_present:
        raise AssertionError("Historical-only group invented a broker row")

    if len(historical_group.closed_legs) != 1:
        raise AssertionError("Historical CLOSED leg was lost")

    print("IB closed-leg broker NET visibility result")
    print("  historical_closed_legs=1")
    print("  broker_present=True")
    print("  broker_net=BUY 1000")
    print("  active_group_mode=NET_ONLY")
    print("  active_group_legs=0")
    print("  broker_residual=False")
    print("  historical_only_group_mode=LGE_VIRTUAL_LEGS")
    print("IB_CLOSED_LEG_BROKER_NET_VISIBILITY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
