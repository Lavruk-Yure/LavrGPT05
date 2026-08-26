"""Synthetic OrdersPage IB reconciliation translation check."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.lang_manager import LangManager  # noqa: E402
from core.orders_page import COL_ID, COL_RECONCILIATION, OrdersPage  # noqa: E402
from core.translation_policy import translation_override_for_key  # noqa: E402
from engine.ib_virtual_position_leg import (  # noqa: E402
    IB_EXTERNAL_PROTECTION_WITHOUT_OBSERVATION_MESSAGE,
)
from engine.runtime_constants import (  # noqa: E402
    IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING,
)
from tests.runtime_orders.orders_page_group_test_support import (  # noqa: E402
    TrackingGroupRuntimeEngine,
    build_blocked_snapshot,
    build_reconciled_snapshot,
)


class FallbackLangManager(LangManager):
    """Language manager backed by canonical fallback values."""

    def __init__(self) -> None:
        super().__init__()
        fallback_path = PROJECT_ROOT / "lang" / "strings_fallback.json"
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
        self._current_lang = "en"
        self._fallback = fallback

    def set_test_language(self, code: str) -> None:
        """Change the synthetic active language."""
        self._current_lang = code

    def tr(
        self,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        _ = localized_fallbacks
        override = translation_override_for_key(key, self._current_lang)

        if override:
            return override

        values = self._fallback.get(key, {})

        if isinstance(values, dict):
            value = values.get(self._current_lang)

            if isinstance(value, str) and value.strip():
                return value

        return fallback

    def resolve(self, key: str, fallback: str = "") -> str | None:
        return self.tr(key, fallback) or None


def main() -> int:
    """Verify localized cell values and the compact warning status."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    lang = FallbackLangManager()
    blocked_snapshot = build_blocked_snapshot()
    blocked_group = blocked_snapshot.groups[0]
    blocked_group.reconciliation_messages = (
        "IB CASH Forex position row is a Virtual FX observation; "
        "LGE leg state was reconciled by exact order executions",
        IB_EXTERNAL_PROTECTION_WITHOUT_OBSERVATION_MESSAGE,
        "IB CASH Forex external exposure is represented from exact "
        "non-LGE executions, not from Virtual FX minus managed-leg "
        "arithmetic: external=1000.0, "
        "virtual_fx_minus_managed=-1000.0, managed=2000.0, "
        "virtual_fx=1000.0, position=IB:DUM513747:GBPUSD",
        "IB CASH Forex external exposure is retained from persisted exact "
        "evidence because the current execution snapshot no longer contains "
        "that non-LGE execution: external=1000.0, "
        "virtual_fx_minus_managed=-1000.0, managed=2000.0, "
        "virtual_fx=1000.0, position=IB:DUM513747:GBPUSD",
    )
    blocked_group.legs[0].reconciliation_messages = (
        "Parent MARKET execution is outside current IB history; "
        "persisted reconciled entry was retained",
        "CLOSE_EVIDENCE_MISSING: persisted protective orders are not active "
        "and no matching close execution was found",
    )
    runtime = TrackingGroupRuntimeEngine(blocked_snapshot)
    page = OrdersPage(lang)
    page.set_runtime_engine(runtime)

    try:
        if not page.refresh_positions():
            raise AssertionError("Blocked translation refresh failed")

        app.processEvents()
        tree = page.ui.tblOpenPositions
        blocked_group_item = tree.topLevelItem(0)
        net_only_item = tree.topLevelItem(1)

        if blocked_group_item.text(COL_RECONCILIATION) != "Blocked":
            raise AssertionError("English BLOCKED status differs")

        lang.set_test_language("uk")
        page.apply_translation()
        app.processEvents()

        if blocked_group_item.text(COL_RECONCILIATION) != "Заблоковано":
            raise AssertionError("BLOCKED group status is not localized")

        blocked_leg_item = blocked_group_item.child(0)

        if blocked_leg_item.text(COL_RECONCILIATION) != "Заблоковано":
            raise AssertionError("BLOCKED leg status is not localized")

        group_tooltip = blocked_group_item.toolTip(COL_ID)
        leg_tooltip = blocked_leg_item.toolTip(COL_ID)

        if "стан віртуальних позицій LGE узгоджено" not in group_tooltip:
            raise AssertionError("Virtual FX group tooltip is not localized")

        if "зовнішній обсяг позиції неможливо визначити" not in group_tooltip:
            raise AssertionError("External-protection tooltip is not localized")

        if "точними виконаннями поза ордерами LGE" not in group_tooltip:
            raise AssertionError("External-execution tooltip is not localized")

        if "раніше підтвердженими точними доказами" not in group_tooltip:
            raise AssertionError("Persisted-execution tooltip is not localized")

        if "поза поточною історією IB" not in leg_tooltip:
            raise AssertionError("Parent history tooltip is not localized")

        if "відповідного виконання закриття не знайдено" not in leg_tooltip:
            raise AssertionError("Close-evidence tooltip is not localized")

        if "Стан віртуальної позиції: Відкрита" not in leg_tooltip:
            raise AssertionError("Virtual-leg lifecycle status is not localized")

        if "Стан захисту: Повний" not in leg_tooltip:
            raise AssertionError("Virtual-leg protection status is not localized")

        if net_only_item.text(COL_RECONCILIATION) != "Неузгоджено":
            raise AssertionError("UNRECONCILED status is not localized")

        net_only_tooltip = net_only_item.toolTip(COL_ID)

        if (
            "Для нетто-позиції брокера немає віртуальних позицій LGE"
            not in net_only_tooltip
        ):
            raise AssertionError("UNRECONCILED tooltip is not localized")

        blocked_warning = page.ui.lblOrdersStatus.text()

        if "захист без прив'язки: 999" not in blocked_warning:
            raise AssertionError("Unmapped protection status is not localized")

        if "EURUSD=Заблоковано" not in blocked_warning:
            raise AssertionError("Warning status value is not localized")

        close_snapshot = build_reconciled_snapshot(include_second_leg=False)
        close_group = close_snapshot.groups[0]
        close_status = IB_RECONCILIATION_STATUS_CLOSE_EVIDENCE_MISSING
        close_group.reconciliation_status = close_status
        close_group.legs[0].reconciliation_status = close_status
        runtime.snapshot = close_snapshot

        if not page.refresh_positions():
            raise AssertionError("Close-evidence translation refresh failed")

        app.processEvents()
        close_group_item = tree.topLevelItem(0)
        close_leg_item = close_group_item.child(0)
        close_text = "Відсутнє підтвердження закриття"

        if close_group_item.text(COL_RECONCILIATION) != close_text:
            raise AssertionError("Close-evidence group status is not localized")

        if close_leg_item.text(COL_RECONCILIATION) != close_text:
            raise AssertionError("Close-evidence leg status is not localized")

        close_warning = page.ui.lblOrdersStatus.text()

        if f"EURUSD={close_text}" not in close_warning:
            raise AssertionError("Close-evidence warning value is not localized")

        mixed_snapshot = build_reconciled_snapshot(include_second_leg=False)
        reconciled_group = mixed_snapshot.groups[0]
        close_group.symbol_name = "USDZAR"
        close_group.broker_position_id = "IB:DUM513747:USDZAR"
        close_group.legs[0].symbol_name = "USDZAR"
        close_group.legs[0].broker_position_id = "IB:DUM513747:USDZAR"
        close_group.legs[0].position_uid = "44444444-4444-4444-4444-444444444444"
        close_group.legs[0].trade_uid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        mixed_snapshot.groups = [close_group, reconciled_group]
        runtime.snapshot = mixed_snapshot

        if not page.refresh_positions():
            raise AssertionError("Mixed selection-status refresh failed")

        app.processEvents()
        disabled_leg_item = tree.topLevelItem(0).child(0)
        enabled_leg_item = tree.topLevelItem(1).child(0)
        tree.setCurrentItem(disabled_leg_item)
        app.processEvents()
        disabled_selection_status = page.ui.lblOrdersStatus.text()

        if close_text not in disabled_selection_status:
            raise AssertionError("Disabled-leg selection warning differs")

        tree.setCurrentItem(enabled_leg_item)
        app.processEvents()
        enabled_selection_status = page.ui.lblOrdersStatus.text()

        if enabled_selection_status != "EURUSD: Узгоджено":
            raise AssertionError("Selected reconciled-leg status differs")

        if "Вибрану віртуальну позицію" in enabled_selection_status:
            raise AssertionError("Disabled-leg selection warning remained stale")

        tree.clearSelection()
        tree.setCurrentItem(None)
        tree.itemSelectionChanged.emit()
        app.processEvents()
        restored_refresh_status = page.ui.lblOrdersStatus.text()

        if f"USDZAR={close_text}" not in restored_refresh_status:
            raise AssertionError(
                "IB refresh warning was not restored without selection"
            )

        reconciled_snapshot = build_reconciled_snapshot(include_second_leg=False)
        runtime.snapshot = reconciled_snapshot

        if not page.refresh_positions():
            raise AssertionError("Reconciled translation refresh failed")

        app.processEvents()
        reconciled_group_item = tree.topLevelItem(0)
        reconciled_leg_item = reconciled_group_item.child(0)

        if reconciled_group_item.text(COL_RECONCILIATION) != "Узгоджено":
            raise AssertionError("RECONCILED group status is not localized")

        if reconciled_leg_item.text(COL_RECONCILIATION) != "Узгоджено":
            raise AssertionError("RECONCILED leg status is not localized")

        print("OrdersPage IB reconciliation translation result")
        print("  reconciled=Узгоджено")
        print("  unreconciled=Неузгоджено")
        print(
            "  unreconciled_tooltip="
            "Для нетто-позиції брокера немає віртуальних позицій LGE"
        )
        print("  blocked=Заблоковано")
        print("  close_evidence_missing=Відсутнє підтвердження закриття")
        print("  selected_reconciled_leg_status=EURUSD: Узгоджено")
        print("  no_selection_refresh_status_restored=True")
        print(f"  warning={blocked_warning}")
        print("ORDERS_PAGE_IB_RECONCILIATION_TRANSLATION_CHECK=OK")
        return 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
