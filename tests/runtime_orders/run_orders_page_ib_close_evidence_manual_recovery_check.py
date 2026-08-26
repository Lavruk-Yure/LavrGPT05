"""Synthetic OrdersPage IB close-evidence manual recovery UI check."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orders_page import OrdersPage  # noqa: E402
from engine.ib_position_group import (  # noqa: E402
    IBPositionGroup,
    IBPositionGroupSnapshot,
)
from engine.ib_virtual_position_leg import IBVirtualPositionLeg  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_BROKER_POSITION_KIND_VIRTUAL_FX,
    IB_LEG_STATUS_OPEN,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    DummyLangManager,
)

POSITION_UID = "78ab6bfb-84a5-40bd-95a0-f3639312f1fc"


class UkrainianDummyLangManager(DummyLangManager):
    """Fallback test manager with exact Ukrainian confirmation labels."""

    _OVERRIDES = {
        "CommonConfirmDialog.btnYes": "Так",
        "CommonConfirmDialog.btnNo": "Ні",
    }

    def tr(
        self,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        _ = localized_fallbacks
        return self._OVERRIDES.get(key, fallback)


def build_missing_snapshot() -> IBPositionGroupSnapshot:
    leg = IBVirtualPositionLeg(
        position_uid=POSITION_UID,
        trade_uid="1ee17b45-0605-415c-b052-b0d1d3f3a540",
        broker_position_id="IB:DUM513747:EURUSD",
        account_id="DUM513747",
        symbol_name="EURUSD",
        side="SELL",
        volume=1000.0,
        entry_price=1.13645,
        opened_utc="2026-07-28T08:09:00+00:00",
        source="MANUAL",
        parent_order_id=211,
        stop_loss_order_id=213,
        take_profit_order_id=212,
        stop_loss=1.1385,
        take_profit=1.133,
        oca_group="1209513133",
        leg_status=IB_LEG_STATUS_OPEN,
        protection_status=IB_PROTECTION_STATUS_NONE,
        reconciliation_status=IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
        reconciliation_messages=(
            "CLOSE_EVIDENCE_MISSING: persisted protective orders are not "
            "active and no matching close execution was found",
        ),
    )
    group = IBPositionGroup(
        broker_position_id="IB:DUM513747:EURUSD",
        account_id="DUM513747",
        symbol_name="EURUSD",
        broker_position_present=False,
        broker_side="UNKNOWN",
        broker_volume=0.0,
        broker_signed_volume=0.0,
        broker_entry_price=None,
        broker_position_kind=IB_BROKER_POSITION_KIND_VIRTUAL_FX,
        current_price=1.13999,
        group_mode=IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
        reconciliation_status=IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
        reconciliation_messages=leg.reconciliation_messages,
        legs=[leg],
    )
    return IBPositionGroupSnapshot(
        captured_utc="2026-07-29T05:40:53+00:00",
        complete=True,
        groups=[group],
        unmapped_protective_order_ids=[],
    )


class ManualRecoveryRuntimeEngine:
    """Synthetic runtime tracking only the dedicated recovery action."""

    def __init__(self) -> None:
        self.snapshot = build_missing_snapshot()
        self.resolve_calls: list[str] = []
        self.close_calls: list[str] = []
        self.modify_calls: list[tuple[str, float | None, float | None]] = []

    @staticmethod
    def get_active_broker() -> str:
        return "IB"

    def get_active_broker_position_groups(self) -> IBPositionGroupSnapshot:
        """Return the current synthetic IB group snapshot."""
        return deepcopy(self.snapshot)

    def sync_active_broker_position_groups(self) -> IBPositionGroupSnapshot:
        return deepcopy(self.snapshot)

    @staticmethod
    def recover_pending_ib_manual_market_order_opens() -> dict:
        return {
            "pending": 0,
            "adopted": [],
            "recovered": [],
            "unresolved": [],
        }

    def resolve_ib_close_evidence_missing(self, position_uid: str) -> dict:
        self.resolve_calls.append(position_uid)
        self.snapshot.groups.clear()
        return {
            "closed": True,
            "position_uid": position_uid,
            "broker_operation_attempted": False,
        }

    def close_runtime_position_leg(self, position_uid: str) -> dict:
        self.close_calls.append(position_uid)
        raise AssertionError("Close must not be used for manual recovery")

    def modify_runtime_position_leg_sl_tp(
        self,
        position_uid: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        self.modify_calls.append((position_uid, stop_loss, take_profit))
        raise AssertionError("Modify must not be used for manual recovery")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    runtime = ManualRecoveryRuntimeEngine()
    page = OrdersPage(UkrainianDummyLangManager())
    page.set_runtime_engine(runtime)
    question_texts: list[str] = []
    localized_button_pairs: list[tuple[str, str]] = []
    build_message_box = getattr(
        page,
        "_build_localized_yes_no_message_box",
    )

    def build_and_accept_message_box(*, title: str, text: str) -> QMessageBox:
        dialog = build_message_box(title=title, text=text)
        yes_button = dialog.button(QMessageBox.StandardButton.Yes)
        no_button = dialog.button(QMessageBox.StandardButton.No)
        assert yes_button is not None
        assert no_button is not None
        localized_button_pairs.append((yes_button.text(), no_button.text()))
        question_texts.append(str(text))
        QTimer.singleShot(
            0,
            lambda current_dialog=dialog: current_dialog.done(
                int(QMessageBox.StandardButton.Yes)
            ),
        )
        return dialog

    try:
        assert page.refresh_positions()
        app.processEvents()
        tree = page.ui.tblOpenPositions
        group_item = tree.topLevelItem(0)
        leg_item = group_item.child(0)

        tree.setCurrentItem(group_item)
        group_item.setSelected(True)
        app.processEvents()
        assert not page.ui.btnResolveReconciliation.isEnabled()

        group_item.setSelected(False)
        tree.setCurrentItem(leg_item)
        leg_item.setSelected(True)
        app.processEvents()

        assert page.ui.btnResolveReconciliation.isEnabled()
        assert not page.ui.btnModifySlTp.isEnabled()
        assert not page.ui.btnClosePosition.isEnabled()

        with patch.object(
            page,
            "_build_localized_yes_no_message_box",
            side_effect=build_and_accept_message_box,
        ):
            page.ui.btnResolveReconciliation.click()
            app.processEvents()

        assert localized_button_pairs == [("Так", "Ні"), ("Так", "Ні")]
        assert len(question_texts) == 2
        assert "Broker position: absent / 0" in question_texts[0]
        assert "does not send any order to IB" in question_texts[1]
        assert runtime.resolve_calls == [POSITION_UID]
        assert runtime.close_calls == []
        assert runtime.modify_calls == []
        assert tree.topLevelItemCount() == 0
        assert not page.ui.btnResolveReconciliation.isEnabled()
        assert "No broker order was sent" in page.ui.lblOrdersStatus.text()

        print("OrdersPage IB manual close-evidence recovery result")
        print("  recovery_button_group_enabled=False")
        print("  recovery_button_leg_enabled=True")
        print("  modify_close_blocked=True")
        print("  localized_buttons=Так/Ні")
        print("  confirmations=2")
        print("  runtime_resolve_calls=1")
        print("  broker_close_calls=0")
        print("  broker_modify_calls=0")
        print("  active_groups_after_resolution=0")
        print("ORDERS_PAGE_IB_CLOSE_EVIDENCE_MANUAL_RECOVERY_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
