"""Synthetic RoadMap91 exact virtual-leg Modify dispatch check."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (  # noqa: E402
    COL_ID,
    COL_SL,
    COL_TP,
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
    runtime = TrackingGroupRuntimeEngine(
        build_reconciled_snapshot(include_second_leg=False)
    )
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        leg_item = page.ui.tblOpenPositions.topLevelItem(0).child(0)
        page.ui.tblOpenPositions.setCurrentItem(leg_item)
        leg_item.setSelected(True)
        app.processEvents()

        page.ui.editStopLoss.setText("1.142")
        page.ui.editTakeProfit.setText("1.159")

        with patch.object(
            page,
            "_ask_localized_yes_no",
            return_value=True,
        ) as confirmation:
            page.ui.btnModifySlTp.click()
            app.processEvents()

        assert confirmation.call_count == 1

        assert runtime.modify_calls == [
            {
                "position_uid": "11111111-1111-1111-1111-111111111111",
                "stop_loss": 1.142,
                "take_profit": 1.159,
            }
        ]
        current_item = page.ui.tblOpenPositions.currentItem()
        assert current_item is not None
        assert (
            current_item.data(COL_ID, ROLE_POSITION_UID)
            == "11111111-1111-1111-1111-111111111111"
        )
        assert current_item.text(COL_SL) == "1.142"
        assert current_item.text(COL_TP) == "1.159"
        assert runtime.group_calls == 1

        print("OrdersPage IB virtual-leg Modify result")
        print(f"  modify_calls={runtime.modify_calls}")
        print(f"  group_refresh_calls={runtime.group_calls}")
        print("  post_modify_snapshot_reused=True")
        print("  localized_confirmation_route=True")
        print(f"  selected_uid={current_item.data(COL_ID, ROLE_POSITION_UID)}")
        print(f"  stop_loss={current_item.text(COL_SL)}")
        print(f"  take_profit={current_item.text(COL_TP)}")
        print("ORDERS_PAGE_IB_VIRTUAL_LEG_MODIFY_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
