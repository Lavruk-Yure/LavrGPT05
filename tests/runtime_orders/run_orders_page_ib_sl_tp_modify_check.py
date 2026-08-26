"""Synthetic OrdersPage exact IB virtual-leg SL/TP modify check.

The check does not connect to TWS. It verifies:
- selection of one reconciled operational IB virtual leg;
- Stop Loss / Take Profit fields populated from the selected leg;
- exact position_uid dispatch through RuntimeEngine;
- post-modify group snapshot reuse without a second broker refresh;
- table and raw-role updates after success;
- warning/status behavior after a RuntimeEngine error;
- no refresh after a failed modify operation.
"""

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

from core.orders_page import (  # noqa: E402
    COL_ID,
    COL_SL,
    COL_TP,
    ROLE_POSITION_UID,
    ROLE_RAW_SL,
    ROLE_RAW_TP,
    OrdersPage,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
    TrackingGroupRuntimeEngine,
    build_reconciled_snapshot,
)

POSITION_UID = "11111111-1111-1111-1111-111111111111"


def _require_equal(
    actual: Any,
    expected: Any,
    message: str,
) -> None:
    """Require exact equality with a useful failure message."""
    if actual != expected:
        raise AssertionError(
            f"{message}: expected={expected!r}, actual={actual!r}"
        )


def _require_true(value: bool, message: str) -> None:
    """Require a true condition."""
    if not value:
        raise AssertionError(message)


def _select_first_leg(
    page: OrdersPage,
    app: QApplication,
) -> None:
    """Select the first exact virtual leg under the first IB group."""
    group_item = page.ui.tblOpenPositions.topLevelItem(0)

    if group_item is None or group_item.childCount() == 0:
        raise AssertionError("Synthetic IB virtual-leg row was not rendered")

    leg_item = group_item.child(0)
    page.ui.tblOpenPositions.setCurrentItem(leg_item)
    leg_item.setSelected(True)
    app.processEvents()


def main() -> int:
    """Run the exact IB virtual-leg Modify SL/TP UI check."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = TrackingGroupRuntimeEngine(
        build_reconciled_snapshot(include_second_leg=False)
    )
    page = OrdersPage(DummyLangManager())
    page.set_runtime_engine(runtime)
    warnings: list[tuple[str, str]] = []

    def capture_warning(
        _parent,
        title: str,
        message: str,
        *_args,
        **_kwargs,
    ) -> QMessageBox.StandardButton:
        """Capture QMessageBox.warning without opening a dialog."""
        warnings.append((str(title), str(message)))
        return QMessageBox.StandardButton.Ok

    try:
        _require_true(page.refresh_positions(), "Initial IB group refresh failed")
        app.processEvents()
        _require_equal(runtime.group_calls, 1, "Initial group snapshot calls")
        _require_equal(
            page.ui.tblOpenPositions.topLevelItemCount(),
            1,
            "Initial IB group count",
        )

        _select_first_leg(page, app)
        current_item = page.ui.tblOpenPositions.currentItem()
        _require_true(current_item is not None, "Operational leg was not selected")
        _require_equal(
            current_item.data(COL_ID, ROLE_POSITION_UID),
            POSITION_UID,
            "Selected virtual-leg position_uid",
        )
        _require_equal(
            page.ui.editStopLoss.text(),
            "1.14",
            "Selected Stop Loss field",
        )
        _require_equal(
            page.ui.editTakeProfit.text(),
            "1.155",
            "Selected Take Profit field",
        )
        _require_true(
            page.ui.btnModifySlTp.isEnabled(),
            "Modify SL/TP button is disabled for a reconciled leg",
        )

        page.ui.editStopLoss.setText("1.135")
        page.ui.editTakeProfit.setText("1.156")

        with patch.object(
            page,
            "_ask_localized_yes_no",
            return_value=True,
        ) as confirmation:
            page.ui.btnModifySlTp.click()
            app.processEvents()

        _require_equal(confirmation.call_count, 1, "Modify confirmation calls")
        _require_equal(
            runtime.modify_calls,
            [
                {
                    "position_uid": POSITION_UID,
                    "stop_loss": 1.135,
                    "take_profit": 1.156,
                }
            ],
            "RuntimeEngine exact virtual-leg modify arguments",
        )
        _require_equal(
            runtime.group_calls,
            1,
            "Post-modify snapshot must be reused without broker refresh",
        )

        current_item = page.ui.tblOpenPositions.currentItem()
        _require_true(current_item is not None, "Selection was lost after modify")
        _require_equal(current_item.text(COL_SL), "1.135", "Updated table SL")
        _require_equal(current_item.text(COL_TP), "1.156", "Updated table TP")
        _require_equal(
            current_item.data(COL_ID, ROLE_RAW_SL),
            1.135,
            "Updated raw Stop Loss",
        )
        _require_equal(
            current_item.data(COL_ID, ROLE_RAW_TP),
            1.156,
            "Updated raw Take Profit",
        )
        _require_equal(
            page.ui.lblOrdersStatus.text(),
            "Updated",
            "Success status",
        )
        _require_equal(
            page.ui.lblOrdersStatus.styleSheet(),
            "",
            "Success status style",
        )

        _select_first_leg(page, app)
        page.ui.editStopLoss.setText("1.136")
        page.ui.editTakeProfit.setText("1.157")
        group_calls_before_error = runtime.group_calls

        with (
            patch.object(
                page,
                "_ask_localized_yes_no",
                return_value=True,
            ),
            patch.object(
                runtime,
                "modify_runtime_position_leg_sl_tp",
                side_effect=RuntimeError("Synthetic IB modify failure"),
            ) as failed_modify,
            patch.object(
                QMessageBox,
                "warning",
                new=capture_warning,
            ),
        ):
            page.ui.btnModifySlTp.click()
            app.processEvents()

        failed_modify.assert_called_once_with(
            position_uid=POSITION_UID,
            stop_loss=1.136,
            take_profit=1.157,
        )
        _require_equal(
            runtime.group_calls,
            group_calls_before_error,
            "Refresh must not run after modify error",
        )
        _require_equal(
            page.ui.lblOrdersStatus.text(),
            "Modify SL/TP failed: Synthetic IB modify failure",
            "Error status",
        )
        _require_true(
            "#ff5555" in page.ui.lblOrdersStatus.styleSheet(),
            "Error status must use warning style",
        )
        _require_equal(
            warnings,
            [
                (
                    "Modify SL/TP",
                    "Modify SL/TP failed: Synthetic IB modify failure",
                )
            ],
            "Warning dialog",
        )

        print("OrdersPage IB exact virtual-leg SL/TP modify result")
        print(f"  selected_position_uid={POSITION_UID}")
        print(f"  successful_modify_calls={runtime.modify_calls}")
        print(f"  group_snapshot_calls={runtime.group_calls}")
        print("  post_modify_snapshot_reused=True")
        print("  failed_modify_refresh_blocked=True")
        print(f"  warnings={warnings}")
        print("ORDERS_PAGE_IB_SL_TP_MODIFY_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
