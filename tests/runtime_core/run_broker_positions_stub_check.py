# run_broker_positions_stub_check.py
"""
Diagnostic:
перевірка unified get_positions() contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ctrader_adapter import CTraderAdapter  # noqa: E402
from engine.ib_adapter import IBAdapter  # noqa: E402


def main() -> int:
    """
    Запуск diagnostic.
    """

    ib_adapter = object.__new__(IBAdapter)
    ctrader_adapter = object.__new__(CTraderAdapter)

    ib_positions = ib_adapter.get_positions()
    ctrader_positions = ctrader_adapter.get_positions()

    print(f"IB positions: {ib_positions}")
    print(f"cTrader positions: {ctrader_positions}")

    checks = [
        isinstance(ib_positions, list),
        isinstance(ctrader_positions, list),
        len(ib_positions) == 0,
        len(ctrader_positions) == 0,
    ]

    if all(checks):
        print("BROKER_POSITIONS_STUB_CHECK=OK")
        return 0

    print("BROKER_POSITIONS_STUB_CHECK=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
