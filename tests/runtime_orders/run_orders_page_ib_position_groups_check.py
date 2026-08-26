"""Synthetic RoadMap91 IB group/virtual-leg hierarchy check."""

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
    COL_ENTRY,
    COL_ID,
    COL_PNL,
    COL_SIDE,
    COL_SL,
    COL_SOURCE,
    COL_TP,
    COL_TYPE,
    COL_VOLUME,
    ROLE_BROKER_POSITION_ID,
    ROLE_POSITION_UID,
    ROLE_ROW_KIND,
    ROW_KIND_GROUP,
    ROW_KIND_LEG,
    OrdersPage,
)
from engine.runtime_constants import IB_LEG_STATUS_CLOSED  # noqa: E402
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
        assert page.activate_page()
        app.processEvents()
        assert runtime.group_calls == 1
        assert runtime.pending_open_recovery_calls == 1
        activation_refresh_calls = runtime.group_calls
        activation_open_recovery_calls = (
            runtime.pending_open_recovery_calls
        )

        tree = page.ui.tblOpenPositions
        assert tree.topLevelItemCount() == 1
        initial_group_count = tree.topLevelItemCount()

        group_item = tree.topLevelItem(0)
        assert group_item.childCount() == 2
        assert group_item.isExpanded()
        assert group_item.data(COL_ID, ROLE_ROW_KIND) == ROW_KIND_GROUP
        assert group_item.data(COL_ID, ROLE_BROKER_POSITION_ID) == "IB:DUM513747:EURUSD"
        assert group_item.text(COL_TYPE) == "Virtual FX"
        assert group_item.text(COL_SL) == "MULTI"
        assert group_item.text(COL_TP) == "MULTI"

        first_leg = group_item.child(0)
        second_leg = group_item.child(1)
        assert first_leg.data(COL_ID, ROLE_ROW_KIND) == ROW_KIND_LEG
        assert (
            first_leg.data(COL_ID, ROLE_POSITION_UID)
            == "11111111-1111-1111-1111-111111111111"
        )
        assert first_leg.text(COL_PNL) == "≈ 6.00 USD"
        assert second_leg.text(COL_PNL) == "≈ 4.00 USD"
        assert page.ui.lblPnlSummary.text() == "Σ PnL: ≈ 10.00 USD"

        initial_children = group_item.childCount()
        initial_group_type = group_item.text(COL_TYPE)
        initial_group_sl = group_item.text(COL_SL)
        initial_group_tp = group_item.text(COL_TP)
        initial_first_leg_pnl = first_leg.text(COL_PNL)
        initial_second_leg_pnl = second_leg.text(COL_PNL)

        runtime.snapshot = build_reconciled_snapshot(broker_position_present=False)
        assert page.refresh_positions()
        app.processEvents()

        derived_group_item = tree.topLevelItem(0)
        assert derived_group_item.text(COL_SIDE) == "BUY"
        assert derived_group_item.text(COL_VOLUME) == "3 000"
        assert "derived from reconciled open LGE legs" in (
            derived_group_item.toolTip(COL_VOLUME)
        )
        missing_broker_row_display = (
            f"{derived_group_item.text(COL_SIDE)} "
            f"{derived_group_item.text(COL_VOLUME)}"
        )

        stale_snapshot = build_reconciled_snapshot()
        stale_group = stale_snapshot.groups[0]
        stale_group.legs = [stale_group.legs[1]]
        stale_group.broker_side = "SELL"
        stale_group.broker_volume = 1000.0
        stale_group.broker_signed_volume = -1000.0
        stale_group.broker_entry_price = 1.14005
        stale_group.unrealized_pnl = -2.12
        stale_group.opened_utc = "2026-07-21T04:55:00+00:00"
        runtime.snapshot = stale_snapshot
        assert page.refresh_positions()
        app.processEvents()

        stale_group_item = tree.topLevelItem(0)
        assert stale_group_item.text(COL_SIDE) == "BUY"
        assert stale_group_item.text(COL_VOLUME) == "2 000"
        assert stale_group_item.text(COL_ENTRY) == ""
        assert stale_group_item.text(COL_PNL) == ""
        assert "Virtual FX observation" in stale_group_item.toolTip(COL_VOLUME)
        stale_broker_row_display = (
            f"{stale_group_item.text(COL_SIDE)} " f"{stale_group_item.text(COL_VOLUME)}"
        )
        assert page.ui.lblPnlSummary.text() == "Σ PnL: ≈ 4.00 USD"

        closed_snapshot = build_reconciled_snapshot()
        closed_group = closed_snapshot.groups[0]

        for leg in closed_group.legs:
            leg.leg_status = IB_LEG_STATUS_CLOSED

        closed_group.broker_side = "SELL"
        closed_group.broker_volume = 3000.0
        closed_group.broker_signed_volume = -3000.0
        closed_group.broker_entry_price = 1.14081667
        closed_group.unrealized_pnl = -4.82
        closed_group.opened_utc = "2026-07-21T06:59:00+00:00"
        runtime.snapshot = closed_snapshot
        assert page.refresh_positions()
        app.processEvents()

        assert tree.topLevelItemCount() == 1
        closed_group_item = tree.topLevelItem(0)
        assert closed_group_item.text(COL_SIDE) == "SELL"
        assert closed_group_item.text(COL_VOLUME) == "3 000"
        assert closed_group_item.text(COL_SOURCE) == "BROKER"
        assert page.ui.lblOrdersStatus.text() == (
            "IB position groups refreshed: 1; open legs: 0"
        )
        assert page.ui.lblPnlSummary.text() == "Σ PnL: —"

        print("OrdersPage IB position groups result")
        print(f"  groups={initial_group_count}")
        print(f"  children={initial_children}")
        print(f"  group_type={initial_group_type}")
        print(f"  group_sl={initial_group_sl}")
        print(f"  group_tp={initial_group_tp}")
        print(f"  first_leg_pnl={initial_first_leg_pnl}")
        print(f"  second_leg_pnl={initial_second_leg_pnl}")
        print("  pnl_summary=Σ PnL: ≈ 10.00 USD")
        print("  missing_broker_row_display=" f"{missing_broker_row_display}")
        print("  stale_broker_row_display=" f"{stale_broker_row_display}")
        print("  virtual_fx_broker_fields_hidden=True")
        print("  closed_virtual_fx_with_broker_position_visible=True")
        print("  visible_groups_status=1")
        print("  activation_refresh_calls=" f"{activation_refresh_calls}")
        print(
            "  activation_open_recovery_calls="
            f"{activation_open_recovery_calls}"
        )
        print("ORDERS_PAGE_IB_POSITION_GROUPS_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
