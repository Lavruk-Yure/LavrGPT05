# run_ib_virtual_leg_model_check.py
"""
Synthetic IBVirtualPositionLeg DTO check.

RoadMap90:
- без TWS;
- без SQLite;
- без broker operations.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
)
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)


def main() -> int:
    """
    Перевірити canonical virtual-leg DTO.
    """
    buy_leg = IBVirtualPositionLeg(
        position_uid="position-buy-1",
        trade_uid="trade-buy-1",
        broker_position_id="IB:DUM513747:EURUSD",
        account_id="DUM513747",
        symbol_name="EURUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.14885,
        opened_utc="2026-07-16T12:00:00+00:00",
        source="LGE_MANUAL",
        parent_order_id=111,
        stop_loss_order_id=113,
        take_profit_order_id=112,
        stop_loss=1.144,
        take_profit=1.151,
        oca_group="LGE_EURUSD_1K",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_COMPLETE,
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    sell_leg = IBVirtualPositionLeg(
        position_uid="position-sell-1",
        trade_uid="trade-sell-1",
        broker_position_id="IB:DUM513747:GBPUSD",
        account_id="DUM513747",
        symbol_name="GBPUSD",
        side="SELL",
        volume=2000.0,
        entry_price=1.3529166667,
        opened_utc="2026-07-16T12:10:00+00:00",
        source="LGE_MANUAL",
        parent_order_id=120,
    )

    if buy_leg.signed_volume != 1000.0:
        raise AssertionError("BUY signed volume mismatch")

    if sell_leg.signed_volume != -2000.0:
        raise AssertionError("SELL signed volume mismatch")

    if buy_leg.protective_action != "SELL":
        raise AssertionError("BUY protective action mismatch")

    if sell_leg.protective_action != "BUY":
        raise AssertionError("SELL protective action mismatch")

    payload = buy_leg.to_dict()

    if payload["position_uid"] != "position-buy-1":
        raise AssertionError("position_uid was not preserved")

    if payload["stop_loss_order_id"] != 113:
        raise AssertionError("stop_loss_order_id was not preserved")

    if payload["take_profit_order_id"] != 112:
        raise AssertionError("take_profit_order_id was not preserved")

    print("IB virtual-leg model result")
    print(f"  buy_signed_volume={buy_leg.signed_volume}")
    print(f"  sell_signed_volume={sell_leg.signed_volume}")
    print(f"  buy_protective_action={buy_leg.protective_action}")
    print(f"  sell_protective_action={sell_leg.protective_action}")
    print(f"  fields={len(payload)}")
    print("IB_VIRTUAL_LEG_MODEL_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
