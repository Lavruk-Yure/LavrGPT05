# run_runtime_account_state_check.py
"""
Перевірка RuntimeAccountState.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_account_state import RuntimeAccountState  # noqa: E402


def main() -> int:
    """
    Запустити перевірку RuntimeAccountState.
    """
    state = RuntimeAccountState()

    checks_before = [
        state.is_loaded() is False,
        state.account_id is None,
        state.balance is None,
    ]

    state.account_id = "9870599"
    state.trader_login = "9870599"
    state.broker_name = "Raw Trading Ltd"
    state.currency = "USD"
    state.balance = 869.75
    state.leverage = 500.0
    state.snapshot_utc = "2026-05-31 12:30"

    checks_loaded = [
        state.is_loaded() is True,
        state.account_id == "9870599",
        state.currency == "USD",
        state.balance == 869.75,
        state.leverage == 500.0,
    ]

    state.clear()

    checks_after_clear = [
        state.is_loaded() is False,
        state.account_id is None,
        state.currency == "",
        state.balance is None,
        state.leverage is None,
        state.snapshot_utc == "",
    ]

    if all(checks_before + checks_loaded + checks_after_clear):
        print("RUNTIME_ACCOUNT_STATE_CHECK=OK")
        return 0

    print("RUNTIME_ACCOUNT_STATE_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
