# -*- coding: utf-8 -*-
"""RoadMap98.5.4.6 real M1-derived M15 versus broker M15 check."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_historical_source_comparison import (  # noqa: E402
    WorkspaceHistoricalSourceComparison,
    build_workspace_historical_source_comparison,
)
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_replay import WorkspaceReplayService  # noqa: E402

BROKER_M15_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M15"
    / "2026-01-02_2026-07-27_IB_EURUSD_M15.csv"
)
M1_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)
START_UTC = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
END_UTC = datetime(2026, 7, 27, 15, 44, tzinfo=UTC)


def _macd_observations(events):
    source = WorkspaceMacdSignalSource(enabled=True, mode="LINEAR")
    for event in events:
        source.on_market_event(event)
    return source.observations


def _comparison() -> WorkspaceHistoricalSourceComparison:
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))
    broker_data = WorkspaceCsvHistoryLoader().load(
        file_path=BROKER_M15_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter=",",
        decimal_separator=".",
        default_spread=0.00012,
    )
    derived_session = WorkspaceReplayService().create_historical_session(
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        replay_settings={
            "file_path": str(M1_FILE),
            "source_timeframe": "M1",
            "start_utc": START_UTC,
            "end_utc": END_UTC,
            "source_timezone": "UTC",
            "delimiter": ",",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "IB_EURUSD_M1_REAL_COMPARISON",
        },
    )
    return build_workspace_historical_source_comparison(
        broker_data.events,
        derived_session.events,
        _macd_observations(broker_data.events),
        _macd_observations(derived_session.events),
    )


def _timestamp(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "N/A"


def _signal_list(items) -> str:
    if not items:
        return "none"
    return ", ".join(
        f"{item.timestamp.isoformat()} {item.direction}" for item in items[:12]
    )


def main() -> None:
    report = _comparison()
    repeated = _comparison()

    assert report == repeated
    assert report.broker_bars == 13926
    assert report.derived_bars == 13926
    assert report.common_timestamps == 13926
    assert not report.broker_only_timestamps
    assert not report.derived_only_timestamps
    assert report.exact_ohlc_bars + report.differing_ohlc_bars == 13926
    assert report.broker_signals == 1072
    assert report.derived_signals == 1077
    assert report.first_ohlc_difference is not None
    assert report.first_signal_difference is not None
    assert report.signal_differences_without_prior_close_difference == 0

    print("Algorithm Workspace M1/M15 Source Comparison result")
    print(f"  broker_m15_bars={report.broker_bars}")
    print(f"  m1_derived_m15_bars={report.derived_bars}")
    print(f"  common_timestamps={report.common_timestamps}")
    print(f"  exact_ohlc_bars={report.exact_ohlc_bars}")
    print(f"  differing_ohlc_bars={report.differing_ohlc_bars}")
    for item in (
        report.open_difference,
        report.high_difference,
        report.low_difference,
        report.close_difference,
    ):
        print(
            f"  {item.field_name}_diff: bars={item.differing_bars}, "
            f"avg={item.average_absolute_difference:.10f}, "
            f"max={item.maximum_absolute_difference:.10f}, "
            f"max_at={_timestamp(item.maximum_difference_timestamp)}"
        )
    print(f"  first_ohlc_difference={_timestamp(report.first_ohlc_difference)}")
    print(f"  broker_m15_macd_signals={report.broker_signals}")
    print(f"  m1_derived_macd_signals={report.derived_signals}")
    print(f"  common_macd_signals={report.common_signals}")
    print(
        "  broker_only_signals="
        f"{len(report.broker_only_signals)}: "
        f"{_signal_list(report.broker_only_signals)}"
    )
    print(
        "  derived_only_signals="
        f"{len(report.derived_only_signals)}: "
        f"{_signal_list(report.derived_only_signals)}"
    )
    print("  direction_changed_signals=" f"{len(report.direction_changed_timestamps)}")
    print(f"  first_signal_difference={_timestamp(report.first_signal_difference)}")
    print("  all_signal_differences_have_prior_close_difference=True")
    print("  timestamp_alignment=True")
    print("  deterministic=True")
    print("  signal_logic_changed=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_M1_M15_SOURCE_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
