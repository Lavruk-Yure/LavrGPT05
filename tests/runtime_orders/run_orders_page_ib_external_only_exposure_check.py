"""OrdersPage explicit row check for broker-only IB CASH FX exposure."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (  # noqa: E402
    COL_RECONCILIATION,
    COL_SL,
    COL_SOURCE,
    COL_TP,
    COL_TYPE,
    COL_VOLUME,
    ROLE_OPERATIONS_ENABLED,
    ROLE_ROW_KIND,
    ROW_KIND_BROKER_RESIDUAL,
    OrdersPage,
)
from engine.ib_position_group import (  # noqa: E402
    build_ib_position_group_snapshot,
)
from engine.ib_virtual_position_leg import (  # noqa: E402
    reconcile_ib_virtual_position_legs,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
)

ACCOUNT_ID = "DUM513747"
POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"


def _evidence() -> dict:
    return {
        "broker": "IB",
        "captured_utc": "2026-08-04T12:00:00+00:00",
        "current_client_id": 1,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "positions": [
            {
                "broker_position_id": POSITION_ID,
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "symbol_name": "EURUSD",
                "sec_type": "CASH",
                "signed_quantity": 1000.0,
                "average_cost": 1.1525,
            }
        ],
        "open_orders": [
            {
                "broker_position_id": POSITION_ID,
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "symbol_name": "EURUSD",
                "sec_type": "CASH",
                "order_id": 0,
                "perm_id": 9501,
                "parent_id": 500,
                "client_id": 0,
                "same_client_id": False,
                "oca_group": "TWS_500",
                "order_type": "LMT",
                "action": "SELL",
                "total_quantity": 1000.0,
                "lmt_price": 1.157,
                "status": "Submitted",
                "tif": "GTC",
            },
            {
                "broker_position_id": POSITION_ID,
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "symbol_name": "EURUSD",
                "sec_type": "CASH",
                "order_id": 0,
                "perm_id": 9502,
                "parent_id": 500,
                "client_id": 0,
                "same_client_id": False,
                "oca_group": "TWS_500",
                "order_type": "STP",
                "action": "SELL",
                "total_quantity": 1000.0,
                "aux_price": 1.145,
                "status": "Submitted",
                "tif": "GTC",
            },
        ],
        "completed_orders": [],
        "executions": [],
    }


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    evidence = _evidence()
    reconciliation = reconcile_ib_virtual_position_legs([], evidence)
    snapshot = build_ib_position_group_snapshot(reconciliation, evidence)
    runtime = TrackingGroupRuntimeEngine(snapshot)
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        if not page.refresh_positions():
            raise AssertionError("OrdersPage external-only refresh failed")

        app.processEvents()
        tree = page.ui.tblOpenPositions

        if tree.topLevelItemCount() != 1:
            raise AssertionError("External-only group is not visible")

        group_item = tree.topLevelItem(0)

        if group_item.childCount() != 1:
            raise AssertionError("Explicit external child row is missing")

        external_item = group_item.child(0)

        if external_item.data(0, ROLE_ROW_KIND) != ROW_KIND_BROKER_RESIDUAL:
            raise AssertionError("External-only row kind differs")

        if external_item.text(COL_TYPE) != "External IB exposure":
            raise AssertionError("External-only type differs")

        if external_item.text(COL_VOLUME).replace(" ", "") != "1000":
            raise AssertionError("External-only volume differs")

        if external_item.text(COL_SOURCE) != "BROKER":
            raise AssertionError("External-only source differs")

        if external_item.text(COL_RECONCILIATION) != "Reconciled":
            raise AssertionError("Current external evidence status differs")

        if bool(external_item.data(0, ROLE_OPERATIONS_ENABLED)):
            raise AssertionError("External-only operations are enabled")

        if not external_item.flags() & Qt.ItemFlag.ItemIsSelectable:
            raise AssertionError("External-only diagnostic row is not selectable")

        if external_item.text(COL_SL) != "1.145":
            raise AssertionError("Exact foreign Stop Loss is not visible")
        if external_item.text(COL_TP) != "1.157":
            raise AssertionError("Exact foreign Take Profit is not visible")

        tree.setCurrentItem(external_item)
        external_item.setSelected(True)
        app.processEvents()
        if not page.ui.btnResolveReconciliation.isEnabled():
            raise AssertionError("External evidence details action is disabled")

        information_calls: list[tuple[str, str]] = []

        def capture_information(_parent, title, text, *_args, **_kwargs):
            information_calls.append((str(title), str(text)))
            return QMessageBox.StandardButton.Ok

        with patch.object(QMessageBox, "information", capture_information):
            page.ui.btnResolveReconciliation.click()
            app.processEvents()

        if len(information_calls) != 1:
            raise AssertionError("Exact TWS evidence dialog was not shown")
        detail_text = information_calls[0][1]
        for expected in (
            "permId=9501",
            "permId=9502",
            "parentId=500",
            "clientId=0",
            "OCA=TWS_500",
            "orderId=0",
        ):
            if expected not in detail_text:
                raise AssertionError(f"External detail is missing: {expected}")

        group_calls_before_deferred_prepare = runtime.group_calls
        if not page.prepare_external_exposure_resolution(
            account_id=ACCOUNT_ID,
            symbol_name="EURUSD",
            refresh=False,
        ):
            raise AssertionError("Deferred external recovery setup failed")
        if runtime.group_calls != group_calls_before_deferred_prepare:
            raise AssertionError("Deferred recovery setup requested a snapshot")

        group_calls_before_refresh = runtime.group_calls
        if not page.prepare_external_exposure_resolution(
            account_id=ACCOUNT_ID,
            symbol_name="EURUSD",
        ):
            raise AssertionError("External exposure recovery route failed")
        if runtime.group_calls != group_calls_before_refresh + 1:
            raise AssertionError("Post-dialog recovery did not refresh exactly once")
        app.processEvents()
        if not page.ui.chkFilterBroker.isChecked():
            raise AssertionError("Recovery route did not enable external filter")
        if page.ui.cmbSymbol.currentText() != "EURUSD":
            raise AssertionError("Recovery route did not focus EURUSD")
        if "LGE EXCLUSIVE" not in page.ui.lblOrdersStatus.text():
            raise AssertionError("Recovery route lacks user guidance")

        if tree.topLevelItemCount() != 1:
            raise AssertionError("Recovery refresh lost external-only group")

        group_item = tree.topLevelItem(0)

        if group_item.childCount() != 1:
            raise AssertionError("Recovery refresh lost external child row")

        external_item = group_item.child(0)

        if external_item.data(0, ROLE_ROW_KIND) != ROW_KIND_BROKER_RESIDUAL:
            raise AssertionError("Recovery refresh changed external row kind")

        selected_items = tree.selectedItems()
        if len(selected_items) != 1 or selected_items[0] is not external_item:
            raise AssertionError("Recovery refresh did not select external row")

        page.ui.chkFilterManual.setChecked(False)
        page.ui.chkFilterSemi.setChecked(False)
        page.ui.chkFilterAuto.setChecked(False)
        page.ui.chkFilterBroker.setChecked(True)
        app.processEvents()

        if group_item.isHidden() or external_item.isHidden():
            raise AssertionError("External filter hid broker-only exposure")

        page.ui.chkFilterBroker.setChecked(False)
        app.processEvents()

        if not group_item.isHidden():
            raise AssertionError("External filter did not hide broker exposure")

        print("OrdersPage IB external-only exposure result")
        print("  explicit_external_row=True")
        print("  external_volume=BUY 1000")
        print("  external_filter_controls_visibility=True")
        print("  recovery_route_visible=True")
        print("  deferred_prepare_broker_requests=0")
        print("  post_dialog_refresh_called_once=True")
        print("  external_row_selected=True")
        print("  recovery_guidance=LGE_EXCLUSIVE")
        print("  external_selectable=True")
        print("  exact_foreign_sl_tp_visible=True")
        print("  exact_tws_identifiers_visible=True")
        print("  external_operations=False")
        print("ORDERS_PAGE_IB_EXTERNAL_ONLY_EXPOSURE_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
