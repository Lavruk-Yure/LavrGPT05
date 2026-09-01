"""Synthetic OrdersPage mixed-currency PnL check."""

from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import COL_PNL, OrdersPage  # noqa: E402
from engine.ib_position_group import IBPositionGroupSnapshot  # noqa: E402
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


def _mixed_currency_snapshot() -> IBPositionGroupSnapshot:
    eur_snapshot = build_reconciled_snapshot(include_second_leg=False)
    eur_group = eur_snapshot.groups[0]
    eur_group.current_price = 1.151
    eur_group.currency = "USD"

    zar_group = deepcopy(eur_group)
    zar_group.broker_position_id = "IB:DUM513747:USDZAR"
    zar_group.symbol_name = "USDZAR"
    zar_group.currency = "ZAR"
    zar_group.current_price = 16.478
    zar_group.broker_entry_price = 16.4855
    zar_group.broker_volume = 1000.0
    zar_group.broker_signed_volume = 1000.0
    zar_leg = zar_group.legs[0]
    zar_leg.position_uid = "44444444-4444-4444-4444-444444444444"
    zar_leg.trade_uid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    zar_leg.broker_position_id = zar_group.broker_position_id
    zar_leg.symbol_name = "USDZAR"
    zar_leg.entry_price = 16.4855
    zar_leg.volume = 1000.0
    zar_leg.stop_loss = 16.465
    zar_leg.take_profit = 16.55

    return IBPositionGroupSnapshot(
        captured_utc=eur_snapshot.captured_utc,
        complete=True,
        groups=[eur_group, zar_group],
        unmapped_protective_order_ids=[],
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(_mixed_currency_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        tree = page.ui.tblOpenPositions
        eur_leg = tree.topLevelItem(0).child(0)
        zar_leg = tree.topLevelItem(1).child(0)

        assert eur_leg.text(COL_PNL) == "≈ 6.00 USD"
        assert zar_leg.text(COL_PNL) == "≈ -7.50 ZAR"
        assert page.ui.lblPnlSummary.text() == ("Σ PnL: ≈ 6.00 USD; ≈ -7.50 ZAR")

        print("OrdersPage PnL currency result")
        print(f"  eurusd_pnl={eur_leg.text(COL_PNL)}")
        print(f"  usdzar_pnl={zar_leg.text(COL_PNL)}")
        print(f"  pnl_summary={page.ui.lblPnlSummary.text()}")
        print("  mixed_currency_not_added=True")
        print("ORDERS_PAGE_PNL_CURRENCY_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
