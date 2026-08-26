"""OrdersPage visibility check for stale persisted IB FX exposure."""

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
    COL_RECONCILIATION,
    COL_SIDE,
    COL_SOURCE,
    COL_TYPE,
    COL_VOLUME,
    ROLE_OPERATIONS_ENABLED,
    ROLE_ROW_KIND,
    ROW_KIND_BROKER_RESIDUAL,
    OrdersPage,
)
from engine.ib_fx_external_exposure import (  # noqa: E402
    IB_FX_EXTERNAL_EXPOSURE_STALE,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    snapshot = build_reconciled_snapshot(
        include_second_leg=True,
        broker_position_present=False,
    )
    group = snapshot.groups[0]
    group.broker_residual_signed_volume = 1000.0
    group.broker_residual_evidence_status = IB_FX_EXTERNAL_EXPOSURE_STALE
    runtime = TrackingGroupRuntimeEngine(snapshot)
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        if not page.refresh_positions():
            raise AssertionError("OrdersPage stale exposure refresh failed")

        app.processEvents()
        tree = page.ui.tblOpenPositions
        group_item = tree.topLevelItem(0)

        if group_item.text(COL_SIDE) != "BUY":
            raise AssertionError("Persisted group side differs")

        if group_item.text(COL_VOLUME).replace(" ", "") != "4000":
            raise AssertionError("Persisted group net volume differs")

        if group_item.childCount() != 3:
            raise AssertionError("Expected two LGE legs and one residual")

        residual_item = group_item.child(2)

        if residual_item.data(0, ROLE_ROW_KIND) != ROW_KIND_BROKER_RESIDUAL:
            raise AssertionError("Stale residual row kind differs")

        if residual_item.text(COL_TYPE) != "External IB exposure":
            raise AssertionError("Stale residual type differs")

        if residual_item.text(COL_SIDE) != "BUY":
            raise AssertionError("Stale residual side differs")

        if residual_item.text(COL_VOLUME).replace(" ", "") != "1000":
            raise AssertionError("Stale residual volume differs")

        if residual_item.text(COL_SOURCE) != "BROKER":
            raise AssertionError("Stale residual source differs")

        if residual_item.text(COL_RECONCILIATION) != "Needs confirmation":
            raise AssertionError("Stale residual status differs")

        if bool(residual_item.data(0, ROLE_OPERATIONS_ENABLED)):
            raise AssertionError("Stale residual operations are enabled")

        page.ui.chkFilterManual.setChecked(False)
        page.ui.chkFilterSemi.setChecked(False)
        page.ui.chkFilterAuto.setChecked(False)
        page.ui.chkFilterBroker.setChecked(True)
        app.processEvents()

        if group_item.isHidden() or residual_item.isHidden():
            raise AssertionError("External filter hid stale broker exposure")

        for child_index in (0, 1):
            if not group_item.child(child_index).isHidden():
                raise AssertionError("External filter kept an LGE leg")

        print("OrdersPage IB stale external exposure result")
        print("  persisted_group_net=BUY 4000")
        print("  managed_lge_legs=BUY 3000")
        print("  external_residual=BUY 1000")
        print("  evidence_status=STALE")
        print("  confirmation_required=True")
        print("  external_filter_visible=True")
        print("  external_operations=False")
        print("ORDERS_PAGE_IB_STALE_EXTERNAL_EXPOSURE_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
