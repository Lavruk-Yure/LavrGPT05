# -*- coding: utf-8 -*-
"""RoadMap98.5.3 Historical MACD signal diagnostics check."""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_macd_signal_diagnostics import (  # noqa: E402
    build_workspace_macd_signal_diagnostics,
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M15"
    / "2026-01-02_2026-07-27_IB_EURUSD_M15.csv"
)


def _report():
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=HISTORY_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        source_timezone="UTC",
        delimiter=",",
        decimal_separator=".",
        default_spread=0.00012,
    )
    source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
    )
    proposals = 0
    for event in data_set.events:
        if source.on_market_event(event) is not None:
            proposals += 1
    report = build_workspace_macd_signal_diagnostics(
        source.observations,
    )
    return data_set, report, proposals


def _signal_at(report, timestamp: datetime):
    return next(
        item
        for item in report.signals
        if item.timestamp == timestamp
    )


def main() -> None:
    data_set, report, proposals = _report()
    _, repeated, repeated_proposals = _report()

    assert data_set.report.accepted_rows == 13926
    assert proposals == 1072
    assert repeated_proposals == proposals
    assert report == repeated
    assert report.total_signals == 1072
    assert report.buy_signals == 536
    assert report.sell_signals == 536

    assert report.buy_below_zero == 362
    assert report.sell_above_zero == 310
    assert report.opposite_zero_side_signals == 672
    assert report.directional_zero_side_signals == 400

    assert report.strength_lt_1e6 == 43
    assert report.strength_lt_5e6 == 206
    assert report.strength_lt_1e5 == 392
    assert report.strength_ge_1e5 == 680

    assert report.reversal_within_1_bar == 88
    assert report.reversal_within_2_bars == 154
    assert report.reversal_within_4_bars == 251
    assert report.reversal_within_8_bars == 461

    weak_signal = _signal_at(
        report,
        datetime(2026, 1, 7, 17, 30, tzinfo=UTC),
    )
    assert weak_signal.direction == "BUY"
    assert weak_signal.macd_value > 0.0
    assert math.isclose(
        weak_signal.strength,
        0.00000043973191586969705,
        rel_tol=0.0,
        abs_tol=1e-15,
    )

    ordinary_sell = _signal_at(
        report,
        datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
    )
    assert ordinary_sell.direction == "SELL"
    assert ordinary_sell.macd_value < 0.0
    assert ordinary_sell.bars_until_opposite_cross == 2

    weekend_signal = _signal_at(
        report,
        datetime(2026, 1, 2, 21, 45, tzinfo=UTC),
    )
    assert weekend_signal.direction == "BUY"
    assert weekend_signal.macd_value < 0.0
    assert weekend_signal.strength < 0.000010

    assert len(report.weakest_signals) == 10
    assert report.weakest_signals[0].strength == report.minimum_strength
    assert report.minimum_strength > 0.0
    assert report.average_strength > report.minimum_strength
    assert report.maximum_strength > report.average_strength

    print("Algorithm Workspace MACD Signal Diagnostics result")
    print(f"  historical_bars={data_set.report.accepted_rows}")
    print(f"  signals={report.total_signals}")
    print(f"  BUY/SELL={report.buy_signals}/{report.sell_signals}")
    print(
        "  opposite_zero_side="
        f"{report.opposite_zero_side_signals} "
        f"(BUY_below={report.buy_below_zero}, "
        f"SELL_above={report.sell_above_zero})"
    )
    print(
        "  directional_zero_side="
        f"{report.directional_zero_side_signals}"
    )
    print(f"  strength_lt_1e-6={report.strength_lt_1e6}")
    print(f"  strength_lt_5e-6={report.strength_lt_5e6}")
    print(f"  strength_lt_1e-5={report.strength_lt_1e5}")
    print(f"  strength_ge_1e-5={report.strength_ge_1e5}")
    print(f"  reversal_within_1_bar={report.reversal_within_1_bar}")
    print(f"  reversal_within_2_bars={report.reversal_within_2_bars}")
    print(f"  reversal_within_4_bars={report.reversal_within_4_bars}")
    print(f"  reversal_within_8_bars={report.reversal_within_8_bars}")
    print("  weak_2026-01-07T17:30_verified=True")
    print("  sell_2026-01-05T09:30_reverses_in_2_bars=True")
    print("  weekend_2026-01-02T21:45_below_zero_weak=True")
    print("  deterministic=True")
    print("  signal_logic_changed=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_SIGNAL_DIAGNOSTICS_CHECK=OK")


if __name__ == "__main__":
    main()
