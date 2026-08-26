"""Pure RoadMap91 virtual-leg calculated PnL check."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import OrdersPage  # noqa: E402


def main() -> int:
    buy_pnl = OrdersPage.calculate_virtual_leg_pnl(
        side="BUY",
        volume=1000.0,
        entry_price=1.145,
        current_price=1.151,
    )
    sell_pnl = OrdersPage.calculate_virtual_leg_pnl(
        side="SELL",
        volume=2000.0,
        entry_price=1.151,
        current_price=1.146,
    )
    missing_pnl = OrdersPage.calculate_virtual_leg_pnl(
        side="BUY",
        volume=1000.0,
        entry_price=None,
        current_price=1.151,
    )

    assert buy_pnl is not None and abs(buy_pnl - 6.0) < 0.000001
    assert sell_pnl is not None and abs(sell_pnl - 10.0) < 0.000001
    assert missing_pnl is None

    print("IB virtual-leg PnL result")
    print(f"  buy_pnl={buy_pnl}")
    print(f"  sell_pnl={sell_pnl}")
    print(f"  missing_pnl={missing_pnl}")
    print("IB_VIRTUAL_LEG_PNL_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
