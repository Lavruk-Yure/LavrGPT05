"""Synthetic OrdersPage order-origin checkbox filter check."""

from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (  # noqa: E402
    COL_ID,
    COL_SOURCE,
    ROLE_ORDER_ORIGIN,
    OrdersPage,
)
from engine.broker_position import BrokerPosition  # noqa: E402
from engine.ib_position_group import (  # noqa: E402
    IBPositionGroup,
    IBPositionGroupSnapshot,
)
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_NET,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_RECONCILIATION_STATUS_UNRECONCILED,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)


class _CTraderRuntime:
    def __init__(self) -> None:
        self.positions = [
            BrokerPosition(
                broker="CTRADER",
                account_id="12345",
                account_mode="DEMO",
                position_id="LGE-1",
                symbol_name="EURUSD",
                side="BUY",
                volume=0.01,
                entry_price=1.10,
                current_price=1.11,
                unrealized_pnl=1.0,
                currency="USD",
                raw_payload={
                    "order_control_mode": "MANUAL",
                    "broker_comment": "[LGE:M] manual",
                },
            ),
            BrokerPosition(
                broker="CTRADER",
                account_id="12345",
                account_mode="DEMO",
                position_id="BROKER-1",
                symbol_name="GBPUSD",
                side="SELL",
                volume=0.01,
                entry_price=1.30,
                current_price=1.29,
                unrealized_pnl=2.0,
                currency="USD",
                raw_payload={
                    "comment": "opened in cTrader",
                },
            ),
        ]

    @staticmethod
    def get_active_broker() -> str:
        return "CTRADER"

    def get_active_broker_positions(self) -> list[BrokerPosition]:
        return deepcopy(self.positions)


def _build_ib_filter_snapshot() -> IBPositionGroupSnapshot:
    snapshot = build_reconciled_snapshot()
    group = snapshot.groups[0]
    group.legs[0].source = "MANUAL"
    group.legs[1].source = "SEMI"

    auto_leg = deepcopy(group.legs[0])
    auto_leg.position_uid = "33333333-3333-3333-3333-333333333333"
    auto_leg.trade_uid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    auto_leg.source = "AUTO"
    auto_leg.entry_price = 1.150
    auto_leg.volume = 1000.0
    group.legs.append(auto_leg)
    group.broker_volume = 4000.0
    group.broker_signed_volume = 4000.0

    broker_group = IBPositionGroup(
        broker_position_id="IB:DUM513747:USDJPY",
        account_id="DUM513747",
        symbol_name="USDJPY",
        broker_position_present=True,
        broker_side="BUY",
        broker_volume=1000.0,
        broker_signed_volume=1000.0,
        broker_entry_price=150.0,
        broker_position_kind=IB_BROKER_POSITION_KIND_NET,
        currency="JPY",
        pnl_currency="JPY",
        current_price=150.1,
        unrealized_pnl=3.0,
        group_mode=IB_POSITION_GROUP_MODE_NET_ONLY,
        reconciliation_status=IB_RECONCILIATION_STATUS_UNRECONCILED,
        reconciliation_messages=("Broker-only synthetic position",),
        legs=[],
    )
    snapshot.groups.append(broker_group)
    return snapshot


def _assert_ib_filters(app: QApplication) -> None:
    runtime = TrackingGroupRuntimeEngine(_build_ib_filter_snapshot())
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        tree = page.ui.tblOpenPositions
        lge_group = tree.topLevelItem(0)
        broker_group = tree.topLevelItem(1)

        assert not lge_group.isHidden()
        assert not broker_group.isHidden()
        assert [lge_group.child(index).text(COL_SOURCE) for index in range(3)] == [
            "MANUAL",
            "SEMI",
            "AUTO",
        ]
        assert [
            lge_group.child(index).data(COL_ID, ROLE_ORDER_ORIGIN)
            for index in range(3)
        ] == ["MANUAL", "SEMI", "AUTO"]
        assert broker_group.text(COL_SOURCE) == "BROKER"
        assert page.ui.lblPnlSummary.text() == "Σ PnL: 3.00 JPY; ≈ 11.00 USD"

        page.ui.chkFilterManual.setChecked(False)
        app.processEvents()
        assert lge_group.child(0).isHidden()
        assert not lge_group.child(1).isHidden()
        assert not lge_group.child(2).isHidden()
        assert page.ui.lblPnlSummary.text() == "Σ PnL: 3.00 JPY; ≈ 5.00 USD"

        page.ui.chkFilterSemi.setChecked(False)
        page.ui.chkFilterAuto.setChecked(False)
        app.processEvents()
        assert lge_group.isHidden()
        assert not broker_group.isHidden()
        assert page.ui.lblPnlSummary.text() == "Σ PnL: 3.00 JPY"

        page.ui.chkFilterBroker.setChecked(False)
        app.processEvents()
        assert lge_group.isHidden()
        assert broker_group.isHidden()
        assert page.ui.lblPnlSummary.text() == "Σ PnL: —"

        page.ui.chkFilterManual.setChecked(True)
        app.processEvents()
        assert not lge_group.isHidden()
        assert not lge_group.child(0).isHidden()
        assert lge_group.child(1).isHidden()
        assert lge_group.child(2).isHidden()
        assert page.ui.lblPnlSummary.text() == "Σ PnL: ≈ 6.00 USD"
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def _assert_ctrader_filters(app: QApplication) -> None:
    runtime = _CTraderRuntime()
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        tree = page.ui.tblOpenPositions
        manual_item = tree.topLevelItem(0)
        broker_item = tree.topLevelItem(1)

        assert manual_item.text(COL_SOURCE) == "MANUAL"
        assert broker_item.text(COL_SOURCE) == "BROKER"

        page.ui.chkFilterSemi.setChecked(False)
        page.ui.chkFilterAuto.setChecked(False)
        page.ui.chkFilterBroker.setChecked(False)
        app.processEvents()
        assert not manual_item.isHidden()
        assert broker_item.isHidden()
        assert page.ui.lblPnlSummary.text() == "Σ PnL: 1.00 USD"

        page.ui.chkFilterManual.setChecked(False)
        page.ui.chkFilterBroker.setChecked(True)
        app.processEvents()
        assert manual_item.isHidden()
        assert not broker_item.isHidden()
        assert page.ui.lblPnlSummary.text() == "Σ PnL: 2.00 USD"
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    _assert_ib_filters(app)
    _assert_ctrader_filters(app)

    print("OrdersPage order-origin filter result")
    print("  default_filters_checked=True")
    print("  manual_filter=True")
    print("  semi_filter=True")
    print("  auto_filter=True")
    print("  broker_filter=True")
    print("  ib_parent_visibility_by_children=True")
    print("  filtered_pnl_summary=True")
    print("  ctrader_broker_metadata_classification=True")
    print("ORDERS_PAGE_ORDER_ORIGIN_FILTER_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
