"""IB CLOSED leg with conflicting Virtual FX observation safety check."""

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
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_BLOCKED,
)

BROKER_POSITION_ID = "IB:DUM513747:EURUSD"
BLOCK_MESSAGE = (
    "IB Virtual FX quantity differs from recognized LGE executions: "
    "cumulative_executions=0.0, current_exposure_executions=0.0, "
    "virtual_fx=1000.0, position=IB:DUM513747:EURUSD"
)


def _closed_blocked_leg() -> IBVirtualPositionLeg:
    """Build the exact closed EURUSD leg from the live safety case."""
    return IBVirtualPositionLeg(
        position_uid="5da08ab4-06d5-480c-8e9f-99f2af361c6b",
        trade_uid="c1009c9a-749a-470f-8405-cffe544387fe",
        broker_position_id=BROKER_POSITION_ID,
        account_id="DUM513747",
        symbol_name="EURUSD",
        side="SELL",
        volume=1000.0,
        entry_price=1.1451,
        opened_utc="2026-07-29T23:35:07+00:00",
        source="MANUAL",
        parent_order_id=220,
        stop_loss_order_id=222,
        take_profit_order_id=221,
        stop_loss=1.149,
        take_profit=1.1436,
        oca_group="868563351",
        leg_status=IB_LEG_STATUS_CLOSED,
        protection_status=IB_PROTECTION_STATUS_NONE,
        reconciliation_status=IB_RECONCILIATION_STATUS_BLOCKED,
        reconciliation_messages=(BLOCK_MESSAGE,),
    )


def _reconciliation_snapshot() -> IBVirtualPositionLegReconciliationSnapshot:
    """Build the blocked reconciliation result produced by exact evidence."""
    return IBVirtualPositionLegReconciliationSnapshot(
        captured_utc="2026-07-30T08:01:59+00:00",
        complete=True,
        legs=[_closed_blocked_leg()],
        group_statuses={
            BROKER_POSITION_ID: IB_RECONCILIATION_STATUS_BLOCKED,
        },
        group_messages={BROKER_POSITION_ID: (BLOCK_MESSAGE,)},
        unmapped_protective_order_ids=[],
        group_broker_residual_signed_volumes={BROKER_POSITION_ID: 0.0},
    )


def _evidence_snapshot() -> dict[str, object]:
    """Build one nonzero IB CASH Virtual FX observation row."""
    return {
        "complete": True,
        "positions": [
            {
                "broker_position_id": BROKER_POSITION_ID,
                "account_id": "DUM513747",
                "symbol_name": "EURUSD",
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": 1000.0,
                "average_cost": 1.1456,
                "current_price": 1.14372504,
                "unrealized_pnl": -1.87,
            }
        ],
        "open_orders": [],
        "completed_orders": [],
        "executions": [],
    }


def main() -> int:
    """Verify that conflicting Virtual FX evidence stays visible and blocked."""
    snapshot = build_ib_position_group_snapshot(
        reconciliation_snapshot=_reconciliation_snapshot(),
        evidence_snapshot=_evidence_snapshot(),
    )

    if len(snapshot.groups) != 1:
        raise AssertionError("Conflicting Virtual FX group count differs")

    group = snapshot.groups[0]

    if group.group_mode != IB_POSITION_GROUP_MODE_NET_ONLY:
        raise AssertionError("Closed-leg conflict did not use NET_ONLY mode")

    if group.reconciliation_status != IB_RECONCILIATION_STATUS_BLOCKED:
        raise AssertionError("Closed-leg Virtual FX conflict lost BLOCKED status")

    if group.reconciliation_messages != (BLOCK_MESSAGE,):
        raise AssertionError("Closed-leg Virtual FX conflict message was lost")

    if group.broker_position_kind != IB_BROKER_POSITION_KIND_VIRTUAL_FX:
        raise AssertionError("Closed-leg conflict lost Virtual FX kind")

    if not group.broker_position_present:
        raise AssertionError("Conflicting Virtual FX observation was hidden")

    if group.broker_side != "BUY" or group.broker_volume != 1000.0:
        raise AssertionError("Conflicting Virtual FX observation differs")

    if group.legs:
        raise AssertionError("Historical CLOSED leg leaked into active NET_ONLY")

    if group.leg_operations_enabled:
        raise AssertionError("Blocked NET_ONLY group enabled leg operations")

    print("IB closed-leg Virtual FX observation block result")
    print("  closed_lge_legs=1")
    print("  exact_close_evidence=True")
    print("  current_exposure_executions=0")
    print("  virtual_fx_observation=BUY 1000")
    print("  active_group_mode=NET_ONLY")
    print("  active_group_status=BLOCKED")
    print("  active_group_legs=0")
    print("  leg_operations=False")
    print("IB_CLOSED_LEG_VIRTUAL_FX_OBSERVATION_BLOCK_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
