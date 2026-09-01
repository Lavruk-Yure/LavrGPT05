# run_ib_virtual_leg_reconciliation_check.py
"""
Synthetic IB virtual-leg reconciliation check.

RoadMap90 cases:
- EURUSD BUY 1K + BUY 2K = broker BUY 3K;
- GBPUSD BUY 3K + SELL 2K = broker BUY 1K;
- exact parentOrderId protection mapping;
- group mismatch blocks operations.
"""

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
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_RECONCILED,
)

ACCOUNT_ID = "DUM513747"
CURRENT_CLIENT_ID = 1


def _build_legs() -> list[IBVirtualPositionLeg]:
    """
    Побудувати чотири logical entries RoadMap90.
    """
    return [
        IBVirtualPositionLeg(
            position_uid="eur-1k-position",
            trade_uid="eur-1k-trade",
            broker_position_id=f"IB:{ACCOUNT_ID}:EURUSD",
            account_id=ACCOUNT_ID,
            symbol_name="EURUSD",
            side="BUY",
            volume=1000.0,
            entry_price=None,
            opened_utc="",
            source="LGE_MANUAL",
            parent_order_id=111,
        ),
        IBVirtualPositionLeg(
            position_uid="eur-2k-position",
            trade_uid="eur-2k-trade",
            broker_position_id=f"IB:{ACCOUNT_ID}:EURUSD",
            account_id=ACCOUNT_ID,
            symbol_name="EURUSD",
            side="BUY",
            volume=2000.0,
            entry_price=None,
            opened_utc="",
            source="LGE_MANUAL",
            parent_order_id=114,
        ),
        IBVirtualPositionLeg(
            position_uid="gbp-3k-position",
            trade_uid="gbp-3k-trade",
            broker_position_id=f"IB:{ACCOUNT_ID}:GBPUSD",
            account_id=ACCOUNT_ID,
            symbol_name="GBPUSD",
            side="BUY",
            volume=3000.0,
            entry_price=None,
            opened_utc="",
            source="LGE_MANUAL",
            parent_order_id=117,
        ),
        IBVirtualPositionLeg(
            position_uid="gbp-2k-position",
            trade_uid="gbp-2k-trade",
            broker_position_id=f"IB:{ACCOUNT_ID}:GBPUSD",
            account_id=ACCOUNT_ID,
            symbol_name="GBPUSD",
            side="SELL",
            volume=2000.0,
            entry_price=None,
            opened_utc="",
            source="LGE_MANUAL",
            parent_order_id=120,
        ),
    ]


def _build_evidence() -> dict:
    """
    Побудувати complete synthetic broker evidence.
    """
    return {
        "broker": "IB",
        "captured_utc": "2026-07-16T13:00:00+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "positions": [
            {
                "broker_position_id": f"IB:{ACCOUNT_ID}:EURUSD",
                "signed_quantity": 3000.0,
            },
            {
                "broker_position_id": f"IB:{ACCOUNT_ID}:GBPUSD",
                "signed_quantity": 1000.0,
            },
        ],
        "completed_orders": [],
        "executions": [
            _execution(111, "EUR", "USD", "BOT", 1000.0, 1.14885),
            _execution(114, "EUR", "USD", "BOT", 2000.0, 1.14765),
            _execution(117, "GBP", "USD", "BOT", 3000.0, 1.35225),
            _execution(120, "GBP", "USD", "SLD", 2000.0, 1.35125),
        ],
        "open_orders": [
            _order(112, 111, "EUR", "USD", "SELL", "LMT", 1000, 1.151),
            _order(113, 111, "EUR", "USD", "SELL", "STP", 1000, 1.144),
            _order(115, 114, "EUR", "USD", "SELL", "LMT", 2000, 1.152),
            _order(116, 114, "EUR", "USD", "SELL", "STP", 2000, 1.143),
            _order(118, 117, "GBP", "USD", "SELL", "LMT", 3000, 1.361),
            _order(119, 117, "GBP", "USD", "SELL", "STP", 3000, 1.349),
            _order(121, 120, "GBP", "USD", "BUY", "LMT", 2000, 1.349),
            _order(122, 120, "GBP", "USD", "BUY", "STP", 2000, 1.359),
        ],
    }


def _execution(
    order_id: int,
    symbol: str,
    currency: str,
    side: str,
    shares: float,
    price: float,
) -> dict:
    """
    Побудувати execution row.
    """
    return {
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": currency,
        "side": side,
        "shares": shares,
        "price": price,
        "time": "20260716 12:00:00",
        "order_id": order_id,
        "perm_id": order_id + 10000,
    }


def _order(
    order_id: int,
    parent_id: int,
    symbol: str,
    currency: str,
    action: str,
    order_type: str,
    quantity: float,
    price: float,
) -> dict:
    """
    Побудувати open protective order row.
    """
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": currency,
        "symbol_name": f"{symbol}{currency}",
        "broker_position_id": f"IB:{ACCOUNT_ID}:{symbol}{currency}",
        "action": action,
        "order_type": order_type,
        "total_quantity": quantity,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "oca_group": f"LGE_{parent_id}",
    }

    if order_type == "LMT":
        row["lmt_price"] = price
    else:
        row["aux_price"] = price

    return row


def main() -> int:
    """
    Запустити synthetic reconciliation matrix.
    """
    legs = _build_legs()
    evidence = _build_evidence()
    snapshot = reconcile_ib_virtual_position_legs(legs, evidence)

    eur_position_id = f"IB:{ACCOUNT_ID}:EURUSD"
    gbp_position_id = f"IB:{ACCOUNT_ID}:GBPUSD"

    if snapshot.group_statuses[eur_position_id] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("EURUSD group was not reconciled")

    if snapshot.group_statuses[gbp_position_id] != (
        IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise AssertionError("GBPUSD group was not reconciled")

    if snapshot.unmapped_protective_order_ids:
        raise AssertionError("Unexpected unmapped protective orders")

    for leg in snapshot.legs:
        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise AssertionError(f"Leg was not reconciled: {leg.position_uid}")

        if leg.protection_status != IB_PROTECTION_STATUS_COMPLETE:
            raise AssertionError(f"Leg protection is incomplete: {leg.position_uid}")

    eur_1k = snapshot.legs[0]
    eur_2k = snapshot.legs[1]
    gbp_sell_2k = snapshot.legs[3]

    if eur_1k.stop_loss != 1.144 or eur_1k.take_profit != 1.151:
        raise AssertionError("EURUSD 1K protection mismatch")

    if eur_2k.stop_loss != 1.143 or eur_2k.take_profit != 1.152:
        raise AssertionError("EURUSD 2K protection mismatch")

    if gbp_sell_2k.protective_action != "BUY":
        raise AssertionError("GBPUSD SELL leg protective action mismatch")

    mismatch_evidence = _build_evidence()
    mismatch_evidence["positions"][0]["signed_quantity"] = 2000.0
    mismatch_snapshot = reconcile_ib_virtual_position_legs(
        _build_legs(),
        mismatch_evidence,
    )

    if mismatch_snapshot.group_statuses[eur_position_id] != (
        IB_RECONCILIATION_STATUS_BLOCKED
    ):
        raise AssertionError("EURUSD mismatch did not block group")

    print("IB virtual-leg reconciliation result")
    print(f"  complete={snapshot.complete}")
    print(f"  legs={len(snapshot.legs)}")
    print(f"  eurusd_status={snapshot.group_statuses[eur_position_id]}")
    print(f"  gbpusd_status={snapshot.group_statuses[gbp_position_id]}")
    print(f"  unmapped_orders={snapshot.unmapped_protective_order_ids}")
    print("  mismatch_status=" f"{mismatch_snapshot.group_statuses[eur_position_id]}")
    print("IB_VIRTUAL_LEG_RECONCILIATION_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
