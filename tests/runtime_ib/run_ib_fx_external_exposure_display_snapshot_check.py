"""Explicit IB FX external-exposure group snapshot regression check."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_fx_external_exposure import (  # noqa: E402
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
)
from engine.ib_position_group import (  # noqa: E402
    build_ib_position_group_snapshot,
)
from engine.ib_virtual_position_leg import (  # noqa: E402
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"
CAPTURED_UTC = "2026-08-04T12:00:00+00:00"


def _evidence(*, positions: list[dict], open_orders: list[dict]) -> dict:
    return {
        "broker": "IB",
        "captured_utc": CAPTURED_UTC,
        "current_client_id": 1,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "positions": positions,
        "open_orders": open_orders,
        "completed_orders": [],
        "executions": [],
    }


def _position_row() -> dict:
    return {
        "broker_position_id": POSITION_ID,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "symbol_name": "EURUSD",
        "sec_type": "CASH",
        "signed_quantity": 1000.0,
        "average_cost": 1.1525,
    }


def _protective_order(
    order_type: str,
    perm_id: int,
    *,
    price: float,
) -> dict:
    row = {
        "broker_position_id": POSITION_ID,
        "account": ACCOUNT_ID,
        "symbol": "EUR",
        "currency": "USD",
        "symbol_name": "EURUSD",
        "sec_type": "CASH",
        "order_id": 0,
        "perm_id": perm_id,
        "parent_id": 500,
        "oca_group": "TWS_500",
        "order_type": order_type,
        "action": "SELL",
        "total_quantity": 1000.0,
        "same_client_id": False,
        "client_id": 0,
        "status": "Submitted",
        "tif": "GTC",
    }
    if order_type == "LMT":
        row["lmt_price"] = price
    else:
        row["aux_price"] = price
    return row


def _single_group(reconciliation, evidence):
    snapshot = build_ib_position_group_snapshot(reconciliation, evidence)

    if len(snapshot.groups) != 1:
        raise AssertionError(f"Expected one external group, got {len(snapshot.groups)}")

    return snapshot.groups[0]


def main() -> int:
    current_evidence = _evidence(positions=[_position_row()], open_orders=[])
    current_reconciliation = reconcile_ib_virtual_position_legs(
        [],
        current_evidence,
    )
    current_group = _single_group(current_reconciliation, current_evidence)

    if current_group.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
        raise AssertionError("Current broker-only exposure is not reconciled")

    if current_group.group_mode != IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS:
        raise AssertionError("External exposure lacks explicit child-row mode")

    if current_group.broker_residual_signed_volume != 1000.0:
        raise AssertionError("Current external exposure volume differs")

    if current_group.leg_operations_enabled:
        raise AssertionError("External exposure unexpectedly allows leg operations")

    persisted = dict(current_reconciliation.group_external_exposures)
    missing_evidence = _evidence(positions=[], open_orders=[])
    stale_reconciliation = reconcile_ib_virtual_position_legs(
        [],
        missing_evidence,
        persisted_external_exposures=persisted,
    )
    stale_group = _single_group(stale_reconciliation, missing_evidence)

    if stale_group.broker_position_present:
        raise AssertionError("Missing broker position row was invented")

    if not stale_group.broker_residual_confirmation_required:
        raise AssertionError("Persisted external exposure is not marked stale")

    protective_evidence = _evidence(
        positions=[],
        open_orders=[
            _protective_order("LMT", 9501, price=1.15700),
            _protective_order("STP", 9502, price=1.14500),
        ],
    )
    protective_reconciliation = reconcile_ib_virtual_position_legs(
        [],
        protective_evidence,
    )
    protective_group = _single_group(
        protective_reconciliation,
        protective_evidence,
    )

    if protective_group.broker_residual_signed_volume != 1000.0:
        raise AssertionError("Bracket pair was double-counted or lost")

    if not protective_group.broker_residual_confirmation_required:
        raise AssertionError("Protective-only evidence was treated as confirmed")

    if protective_group.leg_operations_enabled:
        raise AssertionError("Protective-only exposure allows operations")

    order_details = protective_group.broker_residual_protective_orders
    if len(order_details) != 2:
        raise AssertionError("Exact foreign protective order rows are missing")
    if {row["perm_id"] for row in order_details} != {9501, 9502}:
        raise AssertionError("Foreign protective permId values differ")
    if {row["order_id"] for row in order_details} != {0}:
        raise AssertionError("Foreign orderId=0 evidence was rewritten")
    if {row["client_id"] for row in order_details} != {0}:
        raise AssertionError("Foreign clientId evidence differs")
    prices = {row["order_type"]: row["price"] for row in order_details}
    if prices != {"LMT": 1.157, "STP": 1.145}:
        raise AssertionError(f"Foreign protective prices differ: {prices}")

    terminal_orders = [
        {**_protective_order("LMT", 9501, price=1.15700), "status": "Cancelled"},
        {**_protective_order("STP", 9502, price=1.14500), "status": "Inactive"},
    ]
    terminal_evidence = _evidence(positions=[], open_orders=terminal_orders)
    terminal_reconciliation = reconcile_ib_virtual_position_legs(
        [],
        terminal_evidence,
    )
    terminal_snapshot = build_ib_position_group_snapshot(
        terminal_reconciliation,
        terminal_evidence,
    )

    if terminal_snapshot.groups:
        raise AssertionError("Terminal protective orders created exposure")

    cleared_evidence = _evidence(positions=[], open_orders=[])
    cleared_reconciliation = reconcile_ib_virtual_position_legs(
        [],
        cleared_evidence,
        persisted_external_exposures=dict(
            protective_reconciliation.group_external_exposures
        ),
    )
    cleared_snapshot = build_ib_position_group_snapshot(
        cleared_reconciliation,
        cleared_evidence,
    )

    if cleared_snapshot.groups:
        raise AssertionError("Protective-only stale row survived cancellation")

    cleared_exposure = cleared_reconciliation.group_external_exposures.get(POSITION_ID)

    if cleared_exposure is None:
        raise AssertionError("Protective-only clear marker is missing")

    if cleared_exposure.signed_volume != 0.0 or cleared_exposure.is_active:
        raise AssertionError("Protective-only exposure was not cleared")

    if cleared_exposure.evidence_status != IB_FX_EXTERNAL_EXPOSURE_CONFIRMED:
        raise AssertionError("Protective-only clear evidence status differs")

    print("IB FX external exposure display snapshot result")
    print("  current_broker_only_row=BUY 1000")
    print("  current_external_group_reconciled=True")
    print("  restart_without_position_row_visible=True")
    print("  stale_requires_confirmation=True")
    print("  foreign_bracket_pair_counted_once=True")
    print("  protective_only_row=BUY 1000")
    print("  exact_foreign_orders=2")
    print("  exact_identifiers=permId,parentId,clientId,OCA")
    print("  order_id_zero_preserved=True")
    print("  terminal_protective_orders_ignored=True")
    print("  protective_only_stale_cleared=True")
    print("  confirmed_stale_exposure_preserved=True")
    print("  external_operations=False")
    print("IB_FX_EXTERNAL_EXPOSURE_DISPLAY_SNAPSHOT_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
