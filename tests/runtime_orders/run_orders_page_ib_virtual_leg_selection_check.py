"""Synthetic RoadMap91 virtual-leg selection and button-state check."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import OrdersPage  # noqa: E402
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


def _select(page: OrdersPage, item, app: QApplication) -> None:
    page.ui.tblOpenPositions.setCurrentItem(item)
    item.setSelected(True)
    app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(build_reconciled_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        group_item = page.ui.tblOpenPositions.topLevelItem(0)
        leg_item = group_item.child(0)

        _select(page, group_item, app)
        assert not page.ui.btnModifySlTp.isEnabled()
        assert not page.ui.btnClosePosition.isEnabled()

        _select(page, leg_item, app)
        assert page.ui.btnModifySlTp.isEnabled()
        assert page.ui.btnClosePosition.isEnabled()
        assert page.ui.cmbSymbol.currentText() == "EURUSD"
        assert page.ui.cmbSide.currentData() == "BUY"
        assert page.ui.editStopLoss.text() == "1.14"
        assert page.ui.editTakeProfit.text() == "1.155"

        print("OrdersPage IB virtual-leg selection result")
        print("  group_modify_enabled=False")
        print("  group_close_enabled=False")
        print("  leg_modify_enabled=True")
        print("  leg_close_enabled=True")
        print(f"  stop_loss={page.ui.editStopLoss.text()}")
        print(f"  take_profit={page.ui.editTakeProfit.text()}")
        print("ORDERS_PAGE_IB_VIRTUAL_LEG_SELECTION_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
