# run_ctrader_connection_account_selection_check.py
"""
Перевірка відновлення вибраного cTrader account після reload/reconnect.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDialog,
)

from core.ctrader_connection_dialog import (  # noqa: E402
    CTraderConnectionDialog,
)


class _DialogHarness(CTraderConnectionDialog):
    """Мінімальний cTrader dialog harness без broker connection."""

    _saved_account_id_for_check = ""

    def __init__(self, saved_account_id: str) -> None:
        QDialog.__init__(self)
        type(self)._saved_account_id_for_check = saved_account_id
        self.ui = SimpleNamespace(
            comboAccountId=QComboBox(),
            comboAccountMode=QComboBox(),
        )
        self.ui.comboAccountMode.addItem("Demo", "DEMO")

    @staticmethod
    def _get_saved_account_id() -> str:
        return _DialogHarness._saved_account_id_for_check

    def load_accounts(self, accounts: list[dict]) -> None:
        """Завантажити account list через production helper діалогу."""
        self._load_accounts_to_combo(accounts)


def main() -> int:
    """Запустити перевірку account selection restore."""
    app = QApplication.instance() or QApplication([])
    harness = _DialogHarness(saved_account_id="46368962")

    harness.ui.comboAccountId.addItem(
        "Saved account: 46368962",
        "46368962",
    )

    accounts = [
        {
            "account_id": "11111111",
            "trader_login": "9565209",
            "currency": "USD",
            "balance": "3.92",
            "leverage": "1:500",
        },
        {
            "account_id": "46368962",
            "trader_login": "9870599",
            "currency": "USD",
            "balance": "900.70",
            "leverage": "1:500",
        },
    ]

    harness.load_accounts(accounts)

    saved_account_restored = (
        harness.ui.comboAccountId.currentData() == "46368962"
        and harness.ui.comboAccountId.currentText().startswith("9870599")
    )

    first_index = harness.ui.comboAccountId.findData("11111111")
    harness.ui.comboAccountId.setCurrentIndex(first_index)

    harness.load_accounts(list(reversed(accounts)))

    current_dialog_selection_restored = (
        harness.ui.comboAccountId.currentData() == "11111111"
        and harness.ui.comboAccountId.currentText().startswith("9565209")
    )

    account_order_independent = (
        harness.ui.comboAccountId.currentIndex()
        == harness.ui.comboAccountId.findData("11111111")
    )

    print("cTrader Connection Account Selection result")
    print(f"  saved_account_restored={saved_account_restored}")
    print("  current_dialog_selection_restored=" f"{current_dialog_selection_restored}")
    print(f"  account_order_independent={account_order_independent}")

    app.processEvents()

    if all(
        (
            saved_account_restored,
            current_dialog_selection_restored,
            account_order_independent,
        )
    ):
        print("CTRADER_CONNECTION_ACCOUNT_SELECTION_CHECK=OK")
        return 0

    print("CTRADER_CONNECTION_ACCOUNT_SELECTION_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
