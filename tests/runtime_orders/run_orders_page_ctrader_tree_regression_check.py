"""Synthetic RoadMap91 cTrader flat-tree regression check."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import (  # noqa: E402
    COL_CURRENT,
    COL_ID,
    COL_RECONCILIATION,
    COL_TYPE,
    ROLE_BROKER_POSITION_ID,
    ROLE_STABLE_KEY,
    OrdersPage,
)
from engine.broker_position import BrokerPosition  # noqa: E402
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
)


class CTraderRuntimeEngine:
    def __init__(self) -> None:
        self.modify_calls: list[dict[str, Any]] = []
        self.close_calls: list[str] = []
        self.position = BrokerPosition(
            broker="CTRADER",
            account_id="12345",
            account_mode="DEMO",
            position_id="900001",
            symbol_name="EURUSD",
            side="SELL",
            volume=0.01,
            entry_price=1.151,
            current_price=1.1495,
            stop_loss=1.160,
            take_profit=1.140,
            unrealized_pnl=2.0,
            currency="USD",
            opened_utc="2026-07-20T10:00:00+00:00",
            raw_payload={"unrealized_pnl": 2.0, "pnl_currency": "USD"},
        )

    @staticmethod
    def get_active_broker() -> str:
        return "CTRADER"

    def get_active_broker_positions(self) -> list[BrokerPosition]:
        return [self.position]


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = CTraderRuntimeEngine()
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        assert page.refresh_positions()
        app.processEvents()
        tree = page.ui.tblOpenPositions
        assert tree.topLevelItemCount() == 1
        item = tree.topLevelItem(0)
        assert item.childCount() == 0
        assert item.text(COL_TYPE) == "Broker position"
        assert item.data(COL_ID, ROLE_BROKER_POSITION_ID) == "900001"
        assert item.data(COL_ID, ROLE_STABLE_KEY) == "CTRADER:900001"
        assert item.text(COL_CURRENT) == "1.1495"
        assert item.text(COL_RECONCILIATION) == "—"
        assert page.ui.lblPnlSummary.text() == "Σ PnL: 2.00 USD"
        assert page.ui.spinLots.minimumHeight() >= 26

        tree.setCurrentItem(item)
        item.setSelected(True)
        app.processEvents()
        assert page.ui.editStopLoss.text() == "1.16"
        assert page.ui.editTakeProfit.text() == "1.14"
        assert page.ui.btnModifySlTp.isEnabled()
        assert page.ui.btnClosePosition.isEnabled()

        print("OrdersPage cTrader tree regression result")
        print(f"  top_level_rows={tree.topLevelItemCount()}")
        print(f"  child_rows={item.childCount()}")
        print(f"  stable_key={item.data(COL_ID, ROLE_STABLE_KEY)}")
        print(f"  current_price={item.text(COL_CURRENT)}")
        print("  reconciliation=" f"{item.text(COL_RECONCILIATION)}")
        print(f"  pnl_summary={page.ui.lblPnlSummary.text()}")
        print(f"  spin_min_height={page.ui.spinLots.minimumHeight()}")
        print("ORDERS_PAGE_CTRADER_TREE_REGRESSION_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
