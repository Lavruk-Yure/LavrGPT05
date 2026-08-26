"""Synthetic OrdersPage side-aware IB virtual-leg quote check."""

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

from core.orders_page import COL_CURRENT, COL_PNL, OrdersPage  # noqa: E402
from engine.ib_position_group import IBPositionGroupSnapshot  # noqa: E402
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


def _quote_snapshot() -> IBPositionGroupSnapshot:
    base_snapshot = build_reconciled_snapshot(include_second_leg=False)
    eur_group = base_snapshot.groups[0]
    eur_group.broker_position_present = False
    eur_group.broker_side = "UNKNOWN"
    eur_group.broker_volume = 0.0
    eur_group.broker_signed_volume = 0.0
    eur_group.current_price = 1.14075
    eur_group.bid_price = 1.14075
    eur_group.ask_price = 1.14085
    eur_group.currency = "USD"
    eur_group.pnl_currency = "USD"
    eur_leg = eur_group.legs[0]
    eur_leg.entry_price = 1.1405
    eur_leg.volume = 1000.0

    zar_group = deepcopy(eur_group)
    zar_group.broker_position_id = "IB:DUM513747:USDZAR"
    zar_group.symbol_name = "USDZAR"
    zar_group.current_price = 16.4301
    zar_group.bid_price = 16.4201
    zar_group.ask_price = 16.4301
    zar_group.currency = "ZAR"
    zar_group.pnl_currency = "ZAR"
    zar_leg = zar_group.legs[0]
    zar_leg.position_uid = "44444444-4444-4444-4444-444444444444"
    zar_leg.trade_uid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    zar_leg.broker_position_id = zar_group.broker_position_id
    zar_leg.symbol_name = "USDZAR"
    zar_leg.side = "SELL"
    zar_leg.entry_price = 16.41
    zar_leg.volume = 1000.0
    zar_leg.stop_loss = 16.47
    zar_leg.take_profit = 16.35

    missing_group = deepcopy(eur_group)
    missing_group.broker_position_id = "IB:DUM513747:GBPUSD"
    missing_group.symbol_name = "GBPUSD"
    missing_group.current_price = None
    missing_group.bid_price = None
    missing_group.ask_price = None
    missing_group.currency = "USD"
    missing_group.pnl_currency = "USD"
    missing_leg = missing_group.legs[0]
    missing_leg.position_uid = "55555555-5555-5555-5555-555555555555"
    missing_leg.trade_uid = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    missing_leg.broker_position_id = missing_group.broker_position_id
    missing_leg.symbol_name = "GBPUSD"
    missing_leg.entry_price = 1.337

    return IBPositionGroupSnapshot(
        captured_utc=base_snapshot.captured_utc,
        complete=True,
        groups=[eur_group, zar_group, missing_group],
        unmapped_protective_order_ids=[],
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(_quote_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        if not page.refresh_positions():
            raise AssertionError("OrdersPage refresh failed")

        app.processEvents()
        tree = page.ui.tblOpenPositions
        eur_leg = tree.topLevelItem(0).child(0)
        zar_leg = tree.topLevelItem(1).child(0)
        missing_leg = tree.topLevelItem(2).child(0)

        if eur_leg.text(COL_CURRENT) != "1.14075":
            raise AssertionError("BUY leg did not display bid")

        if eur_leg.text(COL_PNL) != "≈ 0.25 USD":
            raise AssertionError("BUY leg quote PnL differs")

        if zar_leg.text(COL_CURRENT) != "16.4301":
            raise AssertionError("SELL leg did not display ask")

        if zar_leg.text(COL_PNL) != "≈ -20.10 ZAR":
            raise AssertionError("SELL leg quote PnL differs")

        if missing_leg.text(COL_CURRENT):
            raise AssertionError("Missing quote was rendered as a number")

        if missing_leg.text(COL_PNL):
            raise AssertionError("Missing quote produced a PnL")

        expected_summary = "Σ PnL: ≈ 0.25 USD; ≈ -20.10 ZAR"

        if page.ui.lblPnlSummary.text() != expected_summary:
            raise AssertionError("Side-aware mixed-currency summary differs")

        print("OrdersPage IB virtual-leg quote result")
        print(f"  eurusd_buy_price={eur_leg.text(COL_CURRENT)}")
        print(f"  eurusd_buy_pnl={eur_leg.text(COL_PNL)}")
        print(f"  usdzar_sell_price={zar_leg.text(COL_CURRENT)}")
        print(f"  usdzar_sell_pnl={zar_leg.text(COL_PNL)}")
        print("  missing_quote_is_blank=True")
        print(f"  pnl_summary={page.ui.lblPnlSummary.text()}")
        print("ORDERS_PAGE_IB_VIRTUAL_LEG_QUOTE_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
