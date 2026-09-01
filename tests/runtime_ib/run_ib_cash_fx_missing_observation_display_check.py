"""IB CASH FX missing Virtual FX observation display regression check."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_position_group import (  # noqa: E402
    build_ib_position_group_snapshot,
)
from engine.ib_virtual_position_leg import (  # noqa: E402
    IB_EXTERNAL_EXPOSURE_PROTECTIVE_EVIDENCE_MESSAGE,
    IBVirtualPositionLeg,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_OPEN,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
CURRENT_CLIENT_ID = 1


def _leg(
    *,
    symbol_name: str,
    position_uid: str,
    parent_order_id: int,
    stop_loss_order_id: int,
    take_profit_order_id: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
) -> IBVirtualPositionLeg:
    """Build one persisted SELL virtual leg from the live scenario."""
    return IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=f"TRADE-{position_uid}",
        broker_position_id=f"IB:{ACCOUNT_ID}:{symbol_name}",
        account_id=ACCOUNT_ID,
        symbol_name=symbol_name,
        side="SELL",
        volume=1000.0,
        entry_price=entry_price,
        opened_utc="20260728 08:09:01 US/Eastern",
        source="MANUAL",
        parent_order_id=parent_order_id,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=f"OCA-{stop_loss_order_id}-{take_profit_order_id}",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )


def _protective_order(
    *,
    leg: IBVirtualPositionLeg,
    order_id: int,
    order_type: str,
    price: float,
    parent_order_id: int | None = None,
    same_client_id: bool = True,
    client_id: int = CURRENT_CLIENT_ID,
    oca_group: str | None = None,
) -> dict[str, Any]:
    """Build one active exact CASH protective order."""
    base_symbol = leg.symbol_name[:3]
    quote_currency = leg.symbol_name[3:]
    row = {
        "order_id": order_id,
        "parent_id": (
            leg.parent_order_id if parent_order_id is None else parent_order_id
        ),
        "account": leg.account_id,
        "symbol": base_symbol,
        "currency": quote_currency,
        "sec_type": "CASH",
        "symbol_name": leg.symbol_name,
        "broker_position_id": leg.broker_position_id,
        "action": "BUY",
        "order_type": order_type,
        "total_quantity": leg.volume,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": client_id,
        "same_client_id": same_client_id,
        "oca_group": leg.oca_group if oca_group is None else oca_group,
        "oca_type": 1,
        "status": "Submitted",
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def _evidence(*, open_orders: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a complete next-session snapshot without a position row."""
    return {
        "broker": "IB",
        "captured_utc": "2026-07-29T05:41:38+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "account_ids": [ACCOUNT_ID],
        "positions": [],
        "open_orders": open_orders,
        "completed_orders": [],
        "executions": [],
    }


def main() -> int:
    """Verify active and unresolved CASH groups retain meaningful display."""
    gbpusd_leg = _leg(
        symbol_name="GBPUSD",
        position_uid="GBP-OPEN",
        parent_order_id=206,
        stop_loss_order_id=209,
        take_profit_order_id=210,
        entry_price=1.33015,
        stop_loss=1.337,
        take_profit=1.1328,
    )
    gbpusd_evidence = _evidence(
        open_orders=[
            _protective_order(
                leg=gbpusd_leg,
                order_id=209,
                order_type="STP",
                price=1.337,
            ),
            _protective_order(
                leg=gbpusd_leg,
                order_id=210,
                order_type="LMT",
                price=1.1328,
            ),
            _protective_order(
                leg=gbpusd_leg,
                order_id=0,
                order_type="STP",
                price=1.337,
                parent_order_id=900,
                same_client_id=False,
                client_id=0,
                oca_group="TWS-900",
            ),
            _protective_order(
                leg=gbpusd_leg,
                order_id=0,
                order_type="LMT",
                price=1.1328,
                parent_order_id=900,
                same_client_id=False,
                client_id=0,
                oca_group="TWS-900",
            ),
        ]
    )
    gbpusd_reconciliation = reconcile_ib_virtual_position_legs(
        [gbpusd_leg],
        gbpusd_evidence,
    )
    gbpusd_group = build_ib_position_group_snapshot(
        reconciliation_snapshot=gbpusd_reconciliation,
        evidence_snapshot=gbpusd_evidence,
    ).groups[0]

    if gbpusd_group.reconciliation_status != (IB_RECONCILIATION_STATUS_RECONCILED):
        raise AssertionError("Active protected CASH leg was not reconciled")

    if not gbpusd_group.leg_operations_enabled:
        raise AssertionError("Exact protected CASH leg operations were blocked")

    if gbpusd_group.broker_position_present:
        raise AssertionError("Absent Virtual FX observation was invented")

    if gbpusd_reconciliation.unmapped_protective_order_ids:
        raise AssertionError("External TWS protection was marked unmapped")

    if IB_EXTERNAL_EXPOSURE_PROTECTIVE_EVIDENCE_MESSAGE not in (
        gbpusd_group.reconciliation_messages
    ):
        raise AssertionError("Missing protective-evidence diagnostic")

    if gbpusd_group.display_side != "SELL":
        raise AssertionError("Protected CASH group display side differs")

    if gbpusd_group.display_volume != 2000.0:
        raise AssertionError("Protected CASH group display volume differs")

    if gbpusd_group.broker_residual_signed_volume != -1000.0:
        raise AssertionError("External protected exposure volume differs")

    if not gbpusd_group.broker_residual_confirmation_required:
        raise AssertionError("Protective-only exposure lacks confirmation flag")

    eurusd_leg = _leg(
        symbol_name="EURUSD",
        position_uid="EUR-MISSING-EVIDENCE",
        parent_order_id=211,
        stop_loss_order_id=213,
        take_profit_order_id=212,
        entry_price=1.13645,
        stop_loss=1.1385,
        take_profit=1.133,
    )
    eurusd_evidence = _evidence(open_orders=[])
    eurusd_reconciliation = reconcile_ib_virtual_position_legs(
        [eurusd_leg],
        eurusd_evidence,
    )
    eurusd_group = build_ib_position_group_snapshot(
        reconciliation_snapshot=eurusd_reconciliation,
        evidence_snapshot=eurusd_evidence,
    ).groups[0]

    if eurusd_group.group_mode != (IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS):
        raise AssertionError("Unresolved CASH group mode differs")

    if eurusd_group.broker_position_kind != (IB_BROKER_POSITION_KIND_VIRTUAL_FX):
        raise AssertionError("Persisted CASH group lost Virtual FX kind")

    if eurusd_group.reconciliation_status != (
        IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
    ):
        raise AssertionError("Missing close evidence warning was lost")

    if eurusd_group.display_side != "SELL":
        raise AssertionError("Unresolved CASH group display side differs")

    if eurusd_group.display_volume != 1000.0:
        raise AssertionError("Unresolved CASH group display volume differs")

    if eurusd_group.leg_operations_enabled:
        raise AssertionError("Unresolved CASH leg operations were enabled")

    print("IB CASH FX missing observation display result")
    print("  protected_group=GBPUSD SELL 2000 RECONCILED")
    print("  protected_leg_operations=True")
    print("  broker_position_present=False")
    print("  external_tws_protection=SELL 1000 STALE")
    print("  unresolved_group=EURUSD SELL 1000 CLOSE_EVIDENCE_MISSING")
    print("  unresolved_broker_kind=VIRTUAL_FX")
    print("  unresolved_leg_operations=False")
    print("IB_CASH_FX_MISSING_OBSERVATION_DISPLAY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
