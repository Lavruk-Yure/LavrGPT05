"""OrdersPage blocked closed-leg Virtual FX observation safety check."""

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
    COL_RECONCILIATION,
    COL_TYPE,
    ROLE_RECONCILIATION_STATUS,
    OrdersPage,
)
from engine.ib_position_group import (  # noqa: E402
    IBPositionGroup,
    IBPositionGroupSnapshot,
)
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_RECONCILIATION_STATUS_BLOCKED,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
)

BROKER_POSITION_ID = "IB:DUM513747:EURUSD"
BLOCK_MESSAGE = (
    "IB Virtual FX quantity differs from recognized LGE executions: "
    "cumulative_executions=0.0, current_exposure_executions=0.0, "
    "virtual_fx=1000.0, position=IB:DUM513747:EURUSD"
)


def _snapshot() -> IBPositionGroupSnapshot:
    """Build one visible blocked NET_ONLY Virtual FX observation."""
    group = IBPositionGroup(
        broker_position_id=BROKER_POSITION_ID,
        account_id="DUM513747",
        symbol_name="EURUSD",
        broker_position_present=True,
        broker_side="BUY",
        broker_volume=1000.0,
        broker_signed_volume=1000.0,
        broker_entry_price=1.1456,
        broker_position_kind=IB_BROKER_POSITION_KIND_VIRTUAL_FX,
        currency="USD",
        current_price=1.14372504,
        unrealized_pnl=-1.87,
        group_mode=IB_POSITION_GROUP_MODE_NET_ONLY,
        reconciliation_status=IB_RECONCILIATION_STATUS_BLOCKED,
        reconciliation_messages=(BLOCK_MESSAGE,),
        legs=[],
    )
    return IBPositionGroupSnapshot(
        captured_utc="2026-07-30T08:01:59+00:00",
        complete=True,
        groups=[group],
        unmapped_protective_order_ids=[],
    )


def main() -> int:
    """Verify blocked observation is visible and fully non-operational."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        if not page.refresh_positions():
            raise AssertionError("OrdersPage refresh failed")

        app.processEvents()
        tree = page.ui.tblOpenPositions

        if tree.topLevelItemCount() != 1:
            raise AssertionError("Blocked Virtual FX observation was hidden")

        group_item = tree.topLevelItem(0)
        tree.setCurrentItem(group_item)
        group_item.setSelected(True)
        app.processEvents()

        if group_item.text(COL_TYPE) != "NET ONLY":
            raise AssertionError("Blocked observation type differs")

        if group_item.text(COL_RECONCILIATION) != "Blocked":
            raise AssertionError("Blocked observation display status differs")

        raw_status = group_item.data(COL_ID, ROLE_RECONCILIATION_STATUS)
        if raw_status != IB_RECONCILIATION_STATUS_BLOCKED:
            raise AssertionError("Blocked observation raw status differs")

        if page.ui.btnModifySlTp.isEnabled():
            raise AssertionError("Blocked observation enabled Modify")

        if page.ui.btnClosePosition.isEnabled():
            raise AssertionError("Blocked observation enabled Close")

        if page.ui.btnResolveReconciliation.isEnabled():
            raise AssertionError("Blocked observation enabled Recovery")

        page.ui.btnModifySlTp.click()
        page.ui.btnClosePosition.click()
        page.ui.btnResolveReconciliation.click()
        app.processEvents()

        if runtime.modify_calls or runtime.close_calls:
            raise AssertionError("Blocked observation attempted broker operation")

        print("OrdersPage closed-leg Virtual FX block result")
        print("  group_visible=True")
        print("  group_type=NET_ONLY")
        print("  reconciliation=BLOCKED")
        print("  modify_enabled=False")
        print("  close_enabled=False")
        print("  recovery_enabled=False")
        print("  broker_operation_attempted=False")
        print("ORDERS_PAGE_IB_CLOSED_LEG_VIRTUAL_FX_BLOCK_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
