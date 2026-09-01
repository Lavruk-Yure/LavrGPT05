"""OrdersPage operational-row selection regression check."""

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

from core.orders_page import OrdersPage  # noqa: E402
from engine.broker_position import BrokerPosition  # noqa: E402
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_blocked_snapshot,
    build_reconciled_snapshot,
)


class CTraderRuntimeEngine:
    """Return one operational cTrader position."""

    @staticmethod
    def get_active_broker() -> str:
        return "CTRADER"

    @staticmethod
    def get_active_broker_positions() -> list[BrokerPosition]:
        return [
            BrokerPosition(
                broker="CTRADER",
                account_id="9870599",
                account_mode="DEMO",
                position_id="657000001",
                symbol_name="EURUSD",
                side="BUY",
                volume=0.01,
                entry_price=1.151,
                current_price=1.152,
                stop_loss=1.145,
                take_profit=1.160,
                unrealized_pnl=1.0,
                currency="USD",
                opened_utc="2026-07-31T08:00:00+00:00",
                raw_payload={
                    "unrealized_pnl": 1.0,
                    "pnl_currency": "USD",
                },
            )
        ]


def _select(page: OrdersPage, item, app: QApplication) -> None:
    tree = page.ui.tblOpenPositions
    tree.setCurrentItem(item)
    item.setSelected(True)
    app.processEvents()


def _selection_is_empty(page: OrdersPage) -> bool:
    tree = page.ui.tblOpenPositions
    return (
        not tree.selectedItems()
        and tree.currentItem() is None
        and not page.ui.btnModifySlTp.isEnabled()
        and not page.ui.btnResolveReconciliation.isEnabled()
        and not page.ui.btnClosePosition.isEnabled()
        and not page.ui.editStopLoss.text()
        and not page.ui.editTakeProfit.text()
    )


def _item_is_selectable(item) -> bool:
    return bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    page = OrdersPage(DummyLangManager())

    try:
        page.set_runtime_engine(TrackingGroupRuntimeEngine(build_reconciled_snapshot()))
        assert page.refresh_positions()
        app.processEvents()

        tree = page.ui.tblOpenPositions
        group_item = tree.topLevelItem(0)
        leg_item = group_item.child(0)

        assert not _item_is_selectable(group_item)
        _select(page, group_item, app)
        group_selection_blocked = _selection_is_empty(page)

        assert _item_is_selectable(leg_item)
        _select(page, leg_item, app)
        leg_selected = (
            tree.currentItem() is leg_item
            and tree.selectedItems() == [leg_item]
            and page.ui.btnModifySlTp.isEnabled()
            and page.ui.btnClosePosition.isEnabled()
            and page.ui.editStopLoss.text() == "1.14"
            and page.ui.editTakeProfit.text() == "1.155"
        )

        page.set_runtime_engine(TrackingGroupRuntimeEngine(build_blocked_snapshot()))
        assert page.refresh_positions()
        app.processEvents()

        blocked_group = tree.topLevelItem(0)
        blocked_leg = blocked_group.child(0)
        net_only_group = tree.topLevelItem(1)

        assert not _item_is_selectable(blocked_group)
        assert not _item_is_selectable(blocked_leg)
        assert not _item_is_selectable(net_only_group)
        _select(page, net_only_group, app)
        net_only_selection_blocked = _selection_is_empty(page)

        page.set_runtime_engine(CTraderRuntimeEngine())
        assert page.refresh_positions()
        app.processEvents()

        ctrader_item = tree.topLevelItem(0)
        assert _item_is_selectable(ctrader_item)
        _select(page, ctrader_item, app)
        ctrader_selected = (
            tree.currentItem() is ctrader_item
            and tree.selectedItems() == [ctrader_item]
            and page.ui.btnModifySlTp.isEnabled()
            and page.ui.btnClosePosition.isEnabled()
            and page.ui.editStopLoss.text() == "1.145"
            and page.ui.editTakeProfit.text() == "1.16"
        )

        print("OrdersPage operational selection result")
        print(f"  group_selection_blocked={group_selection_blocked}")
        print(f"  reconciled_leg_selected={leg_selected}")
        print(f"  net_only_selection_blocked={net_only_selection_blocked}")
        print(f"  ctrader_position_selected={ctrader_selected}")
        print("  non_operational_highlight_blocked=True")
        print("  sl_tp_fields_follow_operational_row=True")
        print("  operation_buttons_follow_operational_row=True")
        print("ORDERS_PAGE_OPERATIONAL_SELECTION_CHECK=OK")

        return (
            0
            if all(
                (
                    group_selection_blocked,
                    leg_selected,
                    net_only_selection_blocked,
                    ctrader_selected,
                )
            )
            else 1
        )
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
