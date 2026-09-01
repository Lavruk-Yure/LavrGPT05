"""Synthetic NET_ONLY external-IB resolution route check."""

from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (
    COL_ID,
    ROLE_ROW_KIND,
    ROW_KIND_GROUP,
    OrdersPage,
)  # noqa: E402
from engine.ib_position_group import (
    IBPositionGroup,
    IBPositionGroupSnapshot,
)  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)
from tests.runtime_orders.orders_page_group_test_support import (
    DummyLangManager,
)  # noqa: E402


class RuntimeStub:
    """Read-only runtime stub for one external Virtual FX NET_ONLY row."""

    def __init__(self) -> None:
        group = IBPositionGroup(
            broker_position_id="IB:DUM513747:EURUSD",
            account_id="DUM513747",
            symbol_name="EURUSD",
            broker_position_present=True,
            broker_side="SELL",
            broker_volume=1000.0,
            broker_signed_volume=-1000.0,
            broker_entry_price=1.155,
            broker_position_kind=IB_BROKER_POSITION_KIND_VIRTUAL_FX,
            currency="USD",
            current_price=1.15792501,
            unrealized_pnl=-2.93,
            group_mode=IB_POSITION_GROUP_MODE_NET_ONLY,
            reconciliation_status=IB_RECONCILIATION_STATUS_UNRECONCILED,
            reconciliation_messages=("Broker net position has no LGE virtual legs",),
            legs=[],
        )
        self.snapshot = IBPositionGroupSnapshot(
            captured_utc="2026-08-07T12:48:00+00:00",
            complete=True,
            groups=[group],
            unmapped_protective_order_ids=[],
        )

    @staticmethod
    def get_active_broker() -> str:
        return "IB"

    def get_active_broker_position_groups(self) -> IBPositionGroupSnapshot:
        return deepcopy(self.snapshot)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(RuntimeStub())
    info_calls: list[tuple[str, str]] = []

    def capture_information(_parent, title, text, *_args, **_kwargs):
        info_calls.append((str(title), str(text)))
        return QMessageBox.StandardButton.Ok

    try:
        if not page.refresh_positions():
            raise AssertionError("IB NET_ONLY snapshot refresh failed")
        app.processEvents()

        tree = page.ui.tblOpenPositions
        if tree.topLevelItemCount() != 1:
            raise AssertionError("Expected one NET_ONLY external group")

        item = tree.topLevelItem(0)
        if str(item.data(COL_ID, ROLE_ROW_KIND) or "") != ROW_KIND_GROUP:
            raise AssertionError("External NET_ONLY row is not a GROUP row")

        tree.setCurrentItem(item)
        item.setSelected(True)
        app.processEvents()

        if not page.ui.btnResolveReconciliation.isEnabled():
            raise AssertionError("Resolve reconciliation stayed disabled")
        if page.ui.btnModifySlTp.isEnabled():
            raise AssertionError("External NET_ONLY row enabled Modify")
        if page.ui.btnClosePosition.isEnabled():
            raise AssertionError("External NET_ONLY row enabled Close")

        with patch.object(QMessageBox, "information", capture_information):
            page.ui.btnResolveReconciliation.click()
            app.processEvents()

        if len(info_calls) != 1:
            raise AssertionError("External details dialog was not shown once")
        details = info_calls[0][1]
        if "DUM513747" not in details or "EURUSD" not in details:
            raise AssertionError("External details lost account/symbol identity")
        if "SELL" not in details or "1 000" not in details:
            raise AssertionError("External details lost side/volume identity")

        print("OrdersPage IB NET_ONLY external resolution result")
        print("  row_kind=GROUP")
        print("  group_mode=NET_ONLY")
        print("  external_virtual_fx=True")
        print("  resolve_enabled=True")
        print("  modify_enabled=False")
        print("  close_enabled=False")
        print("  details_dialog_once=True")
        print("  account_symbol_preserved=True")
        print("  broker_execution_attempted=False")
        print("ORDERS_PAGE_IB_NET_ONLY_EXTERNAL_RESOLUTION_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
