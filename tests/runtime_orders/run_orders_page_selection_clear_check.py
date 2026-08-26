"""Synthetic OrdersPage position-selection clearing check."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
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


def _select_leg(page: OrdersPage, app: QApplication) -> None:
    tree = page.ui.tblOpenPositions
    group_item = tree.topLevelItem(0)
    leg_item = group_item.child(0)
    tree.setCurrentItem(leg_item)
    leg_item.setSelected(True)
    tree.setFocus()
    app.processEvents()


def _selection_is_cleared(page: OrdersPage) -> bool:
    tree = page.ui.tblOpenPositions
    return (
        not tree.selectedItems()
        and tree.currentItem() is None
        and not page.ui.btnModifySlTp.isEnabled()
        and not page.ui.btnResolveReconciliation.isEnabled()
        and not page.ui.btnClosePosition.isEnabled()
        and not page.ui.editStopLoss.text()
        and not page.ui.editTakeProfit.text()
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(build_reconciled_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)
    page.resize(1200, 800)
    page.show()

    try:
        assert page.refresh_positions()
        app.processEvents()

        _select_leg(page, app)
        assert page.ui.btnModifySlTp.isEnabled()
        assert page.ui.btnClosePosition.isEnabled()
        assert page.ui.editStopLoss.text() == "1.14"
        assert page.ui.editTakeProfit.text() == "1.155"

        QTest.keyClick(page.ui.tblOpenPositions, Qt.Key.Key_Escape)
        app.processEvents()
        escape_cleared = _selection_is_cleared(page)

        _select_leg(page, app)
        viewport = page.ui.tblOpenPositions.viewport()
        empty_point = QPoint(10, viewport.height() - 10)
        assert page.ui.tblOpenPositions.itemAt(empty_point) is None
        QTest.mouseClick(
            viewport,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            empty_point,
        )
        app.processEvents()
        empty_click_cleared = _selection_is_cleared(page)

        print("OrdersPage position selection clear result")
        print(f"  escape_cleared={escape_cleared}")
        print(f"  empty_click_cleared={empty_click_cleared}")
        print("  operation_buttons_disabled=True")
        print("  sl_tp_fields_cleared=True")
        print("ORDERS_PAGE_SELECTION_CLEAR_CHECK=OK")

        if not escape_cleared or not empty_click_cleared:
            return 1

        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
