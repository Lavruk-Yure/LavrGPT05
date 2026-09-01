# tests/runtime_orders/run_orders_page_retranslation_check.py
"""Synthetic OrdersPage retranslation and responsive-table check."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QHeaderView  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.lang_manager import LangManager  # noqa: E402
from core.orders_page import OrdersPage  # noqa: E402


class DummyLangManager(LangManager):
    """Language manager backed by canonical fallback Polish values."""

    def __init__(self) -> None:
        super().__init__()
        fallback_path = PROJECT_ROOT / "lang" / "strings_fallback.json"
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))

        self._current_lang = "en"
        self._pl = {
            key: value["pl"]
            for key, value in fallback.items()
            if isinstance(value, dict)
            and isinstance(value.get("pl"), str)
            and value.get("pl", "").strip()
        }

    def set_test_language(self, code: str) -> None:
        """Change language without touching real translation files."""
        self._current_lang = code

    def tr(
        self,
        key: str,
        fallback: str,
        localized_fallbacks: Mapping[str, str] | None = None,
    ) -> str:
        _ = localized_fallbacks
        if self.current_language == "pl":
            return self._pl.get(key, fallback)
        return fallback

    def resolve(self, key: str, fallback: str = "") -> str | None:
        if self.current_language == "pl":
            return self._pl.get(key, fallback) or None
        return fallback or None


def main() -> None:
    """Run dynamic translation and responsive-column checks."""
    app = QApplication.instance() or QApplication([])
    lang = DummyLangManager()
    page = OrdersPage(lang)

    lang.set_test_language("pl")
    page.apply_translation()
    app.processEvents()

    header_item = page.ui.tblOpenPositions.headerItem()
    headers = [
        header_item.text(index)
        for index in range(page.ui.tblOpenPositions.columnCount())
    ]

    expected = [
        "ID",
        "Para",
        "Typ",
        "Kierunek",
        "Wolumen",
        "Cena wejścia",
        "Aktualna cena",
        "SL",
        "TP",
        "Zysk netto",
        "Uzgodnienie",
        "Źródło",
        "Czas",
    ]

    assert headers == expected, (
        f"Translated headers differ: expected={expected!r}, " f"actual={headers!r}"
    )
    assert page.ui.btnModifySlTp.text() == "Zmień SL/TP"
    assert page.ui.lblPositionFilter.text() == "Filtr"
    assert page.ui.chkFilterManual.text() == "Ręczny"
    assert page.ui.chkFilterSemi.text() == "Półautomatyczny"
    assert page.ui.chkFilterAuto.text() == "Automatyczny"
    assert page.ui.chkFilterBroker.text() == "Zewnętrzne u brokera"
    assert page.ui.chkFilterManual.isChecked()
    assert page.ui.chkFilterSemi.isChecked()
    assert page.ui.chkFilterAuto.isChecked()
    assert page.ui.chkFilterBroker.isChecked()
    assert page.ui.lblPnlSummary.text() == "Σ PnL: —"
    assert page.ui.spinLots.minimumHeight() >= 26
    assert page.ui.statusLayout.stretch(0) == 1
    assert page.ui.statusSpacer.sizeHint().width() == 0

    additional_warning = lang.tr(
        "OrdersPage.statusAdditionalWarnings",
        "and {count} more",
    ).format(count=1)
    mixed_warning = lang.tr(
        "OrdersPage.statusProtectionMixed",
        "{leg} mixed {quantity}/{volume}",
    ).format(leg="SL", quantity="3 000", volume="1 000")

    assert additional_warning == "i jeszcze 1"
    assert mixed_warning == "SL niejednoznaczny 3 000/1 000"

    header = page.ui.tblOpenPositions.header()

    for column_index in range(page.ui.tblOpenPositions.columnCount()):
        assert (
            header.sectionResizeMode(column_index) == QHeaderView.ResizeMode.Interactive
        )

    assert header.stretchLastSection()
    assert page.ui.tblOpenPositions.columnWidth(0) == 105
    assert page.ui.tblOpenPositions.columnWidth(12) >= 90
    assert (
        page.ui.tblOpenPositions.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )

    modes = [
        header.sectionResizeMode(index).name
        for index in range(page.ui.tblOpenPositions.columnCount())
    ]

    print("OrdersPage retranslation result")
    print(f"  headers={headers}")
    print(f"  modify_button={page.ui.btnModifySlTp.text()}")
    print(
        "  filters="
        f"{page.ui.chkFilterManual.text()},"
        f"{page.ui.chkFilterSemi.text()},"
        f"{page.ui.chkFilterAuto.text()},"
        f"{page.ui.chkFilterBroker.text()}"
    )
    print(f"  additional_warning={additional_warning}")
    print(f"  mixed_warning={mixed_warning}")
    print(f"  resize_modes={modes}")
    print(f"  pnl_summary={page.ui.lblPnlSummary.text()}")
    print(f"  spin_min_height={page.ui.spinLots.minimumHeight()}")
    print(f"  orders_status_stretch={page.ui.statusLayout.stretch(0)}")
    print("  status_spacer_width=" f"{page.ui.statusSpacer.sizeHint().width()}")
    print("ORDERS_PAGE_RETRANSLATION_CHECK=OK")

    page.close()


if __name__ == "__main__":
    main()
