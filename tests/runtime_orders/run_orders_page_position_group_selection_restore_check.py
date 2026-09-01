"""Synthetic RoadMap91 stable selection restore and safe clear check."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (  # noqa: E402
    COL_ID,
    ROLE_POSITION_UID,
    OrdersPage,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(build_reconciled_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        second_leg = page.ui.tblOpenPositions.topLevelItem(0).child(1)
        page.ui.tblOpenPositions.setCurrentItem(second_leg)
        second_leg.setSelected(True)
        app.processEvents()

        assert page.refresh_positions()
        app.processEvents()
        restored = page.ui.tblOpenPositions.currentItem()
        assert restored is not None
        assert (
            restored.data(COL_ID, ROLE_POSITION_UID)
            == "22222222-2222-2222-2222-222222222222"
        )
        assert restored.parent() is not None
        assert restored.parent().isExpanded()

        runtime.close_runtime_position_leg("22222222-2222-2222-2222-222222222222")
        assert page.refresh_positions()
        app.processEvents()
        assert page.ui.tblOpenPositions.currentItem() is None
        assert not page.ui.btnModifySlTp.isEnabled()
        assert not page.ui.btnClosePosition.isEnabled()

        print("OrdersPage position-group selection restore result")
        print("  same_leg_restored=True")
        print("  parent_expanded=True")
        print("  closed_leg_selection_cleared=True")
        print("ORDERS_PAGE_POSITION_GROUP_SELECTION_RESTORE_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
