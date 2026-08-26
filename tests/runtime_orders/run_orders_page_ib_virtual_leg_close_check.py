"""Synthetic RoadMap91 exact virtual-leg Close dispatch check."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import OrdersPage  # noqa: E402
from engine.ib_order_errors import (  # noqa: E402
    IBVirtualLegCloseConfirmationPendingError,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


class PendingCloseRuntimeEngine(TrackingGroupRuntimeEngine):
    """Synthetic timeout state: one Close was sent and saved as pending."""

    def close_runtime_position_leg(
        self,
        position_uid: str,
    ) -> dict[str, object]:
        self.close_calls.append(position_uid)
        raise IBVirtualLegCloseConfirmationPendingError(
            position_uid=position_uid,
            close_order_id=777,
            details="Synthetic delayed execution evidence",
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(build_reconciled_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        leg_item = page.ui.tblOpenPositions.topLevelItem(0).child(0)
        page.ui.tblOpenPositions.setCurrentItem(leg_item)
        leg_item.setSelected(True)
        app.processEvents()

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            page.ui.btnClosePosition.click()
            app.processEvents()

        assert runtime.close_calls == [
            "11111111-1111-1111-1111-111111111111"
        ]
        group_item = page.ui.tblOpenPositions.topLevelItem(0)
        assert group_item.childCount() == 1
        assert page.ui.tblOpenPositions.currentItem() is None
        assert not page.ui.btnModifySlTp.isEnabled()
        assert not page.ui.btnClosePosition.isEnabled()

        print("OrdersPage IB virtual-leg Close result")
        print(f"  close_calls={runtime.close_calls}")
        print(f"  remaining_children={group_item.childCount()}")
        print("  selection_cleared=True")
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()

    pending_runtime = PendingCloseRuntimeEngine(build_reconciled_snapshot())
    pending_page = OrdersPage(DummyLangManager())
    pending_page.set_runtime_engine(pending_runtime)
    warnings: list[str] = []

    try:
        assert pending_page.refresh_positions()
        app.processEvents()
        leg_item = pending_page.ui.tblOpenPositions.topLevelItem(0).child(0)
        pending_page.ui.tblOpenPositions.setCurrentItem(leg_item)
        leg_item.setSelected(True)
        app.processEvents()

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda _parent, _title, text: warnings.append(str(text)),
        ):
            pending_page.ui.btnClosePosition.click()
            app.processEvents()

        assert pending_runtime.close_calls == [
            "11111111-1111-1111-1111-111111111111"
        ]
        assert pending_runtime.group_calls == 2
        assert len(warnings) == 1
        assert "Do not repeat Close" in warnings[0]
        assert "close_order_id=777" in warnings[0]

        print("  pending_close_warning_shown=True")
        print("  pending_close_refresh_calls=1")
        print("  duplicate_close_calls=0")
        print("ORDERS_PAGE_IB_VIRTUAL_LEG_CLOSE_CHECK=OK")
        return 0
    finally:
        pending_page.close()
        pending_page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
