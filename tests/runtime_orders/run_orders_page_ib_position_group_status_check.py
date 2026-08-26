"""Synthetic RoadMap91 BLOCKED and NET_ONLY operation-state check."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (  # noqa: E402
    COL_ID,
    COL_RECONCILIATION,
    COL_TYPE,
    ROLE_RECONCILIATION_STATUS,
    OrdersPage,
)
from engine.runtime_constants import (  # noqa: E402
    IB_RECONCILIATION_STATUS_BLOCKED,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_blocked_snapshot,
)


def _select(page: OrdersPage, item, app: QApplication) -> None:
    page.ui.tblOpenPositions.setCurrentItem(item)
    item.setSelected(True)
    app.processEvents()


def _item_is_selectable(item) -> bool:
    return bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)


def _selection_is_empty(page: OrdersPage) -> bool:
    tree = page.ui.tblOpenPositions
    return not tree.selectedItems() and tree.currentItem() is None


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(build_blocked_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        tree = page.ui.tblOpenPositions
        assert tree.topLevelItemCount() == 2

        blocked_group = tree.topLevelItem(0)
        blocked_leg = blocked_group.child(0)
        net_only_group = tree.topLevelItem(1)

        assert (
            str(
                blocked_group.data(
                    COL_ID,
                    ROLE_RECONCILIATION_STATUS,
                )
                or ""
            )
            == IB_RECONCILIATION_STATUS_BLOCKED
        )
        assert blocked_group.text(COL_RECONCILIATION) == "Blocked"
        assert blocked_group.toolTip(COL_RECONCILIATION)
        assert not _item_is_selectable(blocked_group)
        assert not _item_is_selectable(blocked_leg)

        _select(page, blocked_leg, app)
        assert _selection_is_empty(page)
        assert not page.ui.btnModifySlTp.isEnabled()
        assert not page.ui.btnClosePosition.isEnabled()

        assert net_only_group.text(COL_TYPE) == "NET ONLY"
        assert not _item_is_selectable(net_only_group)
        assert "Broker net position has no LGE virtual legs" in net_only_group.toolTip(
            COL_RECONCILIATION
        )

        _select(page, net_only_group, app)
        assert _selection_is_empty(page)
        assert not page.ui.btnModifySlTp.isEnabled()
        assert not page.ui.btnClosePosition.isEnabled()
        assert "unmapped protection: 999" in page.ui.lblOrdersStatus.text()
        assert "EURUSD=Blocked" in page.ui.lblOrdersStatus.text()

        print("OrdersPage IB position-group status result")
        print("  blocked_group_selectable=False")
        print("  blocked_leg_selectable=False")
        print("  blocked_leg_operations=False")
        print("  net_only_group_selectable=False")
        print("  net_only_modify=False")
        print("  net_only_close=False")
        print(f"  status={page.ui.lblOrdersStatus.text()}")
        print("ORDERS_PAGE_IB_POSITION_GROUP_STATUS_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
