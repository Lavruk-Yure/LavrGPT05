"""Synthetic OrdersPage mixed IB LGE-leg and broker-residual check."""

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
    COL_SIDE,
    COL_SOURCE,
    COL_TYPE,
    COL_VOLUME,
    ROLE_OPERATIONS_ENABLED,
    ROLE_ROW_KIND,
    ROW_KIND_BROKER_RESIDUAL,
    ROW_KIND_LEG,
    OrdersPage,
)
from engine.runtime_constants import (  # noqa: E402
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    snapshot = build_reconciled_snapshot(include_second_leg=False)
    group = snapshot.groups[0]
    leg = group.legs[0]
    leg.side = "SELL"
    leg.volume = 1000.0
    leg.entry_price = 1.1372
    group.broker_position_present = True
    group.broker_side = "BUY"
    group.broker_volume = 2000.0
    group.broker_signed_volume = 2000.0
    group.broker_residual_signed_volume = 3000.0
    group.bid_price = 1.1385
    group.ask_price = 1.1386
    group.current_price = 1.13855
    group.reconciliation_status = (
        IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
    )
    group.reconciliation_messages = (
        "Synthetic sibling close evidence is missing",
    )
    runtime = TrackingGroupRuntimeEngine(snapshot)
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        if not page.refresh_positions():
            raise AssertionError("OrdersPage residual refresh failed")

        app.processEvents()
        tree = page.ui.tblOpenPositions
        group_item = tree.topLevelItem(0)

        if group_item.text(COL_SIDE) != "BUY":
            raise AssertionError("Group row does not show broker net side")

        if group_item.text(COL_VOLUME).replace(" ", "") != "2000":
            raise AssertionError("Group row does not show broker net volume")

        if group_item.childCount() != 2:
            raise AssertionError("Expected one LGE leg and one residual row")

        leg_item = group_item.child(0)
        residual_item = group_item.child(1)

        if leg_item.data(0, ROLE_ROW_KIND) != ROW_KIND_LEG:
            raise AssertionError("Managed child row kind differs")

        if not bool(leg_item.data(0, ROLE_OPERATIONS_ENABLED)):
            raise AssertionError("Managed LGE leg operations are disabled")

        if residual_item.data(0, ROLE_ROW_KIND) != ROW_KIND_BROKER_RESIDUAL:
            raise AssertionError("Broker residual row kind differs")

        if residual_item.text(COL_TYPE) != "External IB exposure":
            raise AssertionError("Broker residual type differs")

        if residual_item.text(COL_SIDE) != "BUY":
            raise AssertionError("Broker residual side differs")

        if residual_item.text(COL_VOLUME).replace(" ", "") != "3000":
            raise AssertionError("Broker residual volume differs")

        if residual_item.text(COL_SOURCE) != "BROKER":
            raise AssertionError("Broker residual source differs")

        if bool(residual_item.data(0, ROLE_OPERATIONS_ENABLED)):
            raise AssertionError("Broker residual operations are enabled")

        page.ui.chkFilterManual.setChecked(False)
        page.ui.chkFilterSemi.setChecked(False)
        page.ui.chkFilterAuto.setChecked(False)
        page.ui.chkFilterBroker.setChecked(True)
        app.processEvents()

        if group_item.isHidden() or residual_item.isHidden():
            raise AssertionError("Broker-only filter hid the residual")

        if not leg_item.isHidden():
            raise AssertionError("Broker-only filter kept the manual LGE leg")

        page.ui.chkFilterManual.setChecked(True)
        page.ui.chkFilterBroker.setChecked(False)
        app.processEvents()

        if group_item.isHidden() or leg_item.isHidden():
            raise AssertionError("Manual filter hid the exact LGE leg")

        if not residual_item.isHidden():
            raise AssertionError("Manual filter kept the broker residual")

        print("OrdersPage IB broker residual result")
        print("  group_net=BUY 2000")
        print("  managed_leg=SELL 1000")
        print("  broker_residual=BUY 3000")
        print("  managed_leg_operations=True")
        print("  group_warning_does_not_block_exact_leg=True")
        print("  broker_residual_operations=False")
        print("  origin_filters=True")
        print("ORDERS_PAGE_IB_BROKER_RESIDUAL_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
