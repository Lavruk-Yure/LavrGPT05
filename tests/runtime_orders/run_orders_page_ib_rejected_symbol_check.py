"""Synthetic OrdersPage handling of an IB-rejected symbol."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import OrdersPage  # noqa: E402
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
)


class RejectedSymbolRuntimeEngine:
    """Runtime stub that emulates an IB contract rejection."""

    def __init__(self) -> None:
        self.place_calls: list[dict[str, Any]] = []

    @staticmethod
    def get_active_broker() -> str:
        return "IB"

    def place_manual_market_order(
        self,
        *,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None,
        take_profit: float | None,
        comment: str,
        control_mode: str,
    ) -> dict[str, Any]:
        self.place_calls.append(
            {
                "symbol_name": symbol_name,
                "side": side,
                "lots": lots,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "comment": comment,
                "control_mode": control_mode,
            }
        )
        raise RuntimeError("IB contract details were not found for XAUUSD")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = RejectedSymbolRuntimeEngine()
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)

    try:
        page.ui.cmbSymbol.addItem("XAUUSD")
        page.ui.cmbSymbol.setCurrentText("XAUUSD")
        page.ui.cmbSide.setCurrentIndex(page.ui.cmbSide.findData("BUY"))
        page.ui.spinLots.setValue(0.01)
        page.ui.editStopLoss.clear()
        page.ui.editTakeProfit.clear()
        page.ui.editComment.setText("RoadMap91 rejected symbol")

        with patch.object(
            QMessageBox,
            "warning",
            return_value=QMessageBox.StandardButton.Ok,
        ) as warning_mock:
            page.ui.btnPlaceOrder.click()
            app.processEvents()

        assert runtime.place_calls == [
            {
                "symbol_name": "XAUUSD",
                "side": "BUY",
                "lots": 0.01,
                "stop_loss": None,
                "take_profit": None,
                "comment": "RoadMap91 rejected symbol",
                "control_mode": "MANUAL",
            }
        ]
        assert warning_mock.call_count == 1
        warning_text = str(warning_mock.call_args.args[2])
        assert "contract details were not found" in warning_text
        assert page.ui.tblOpenPositions.topLevelItemCount() == 0
        assert page.ui.lblPnlSummary.text() == "Σ PnL: —"

        print("OrdersPage IB rejected-symbol result")
        print("  symbol=XAUUSD")
        print("  place_calls=1")
        print(f"  warning={warning_text}")
        print("  active_rows=0")
        print("ORDERS_PAGE_IB_REJECTED_SYMBOL_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
