# -*- coding: utf-8 -*-
"""RoadMap99_02 production EXTENDED MACD quality filter check."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_macd import (  # noqa: E402
    MACD_STATE_CROSS_UP,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
)
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY,
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
END_UTC = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)


def _data_set():
    return WorkspaceCsvHistoryLoader().load(
        file_path=M1_FILE,
        broker="IB",
        symbol="EURUSD",
        timeframe="M1",
        start_utc=START_UTC,
        end_utc=END_UTC,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=0.00012,
        source_name="IB_EURUSD_M1_RM99_PRODUCTION",
    )


def _run_source(data_set, *, mode: str, angle: float = 45.0):
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    source = WorkspaceMacdSignalSource.from_parameters(
        {
            "macd_signal_enabled": True,
            "macd_signal_mode": mode,
            WORKSPACE_MACD_CROSS_MIN_ANGLE_KEY: angle,
        }
    )
    proposals = []
    for event in data_set.events:
        completed = aggregator.on_market_event(event)
        if completed is None:
            continue
        proposal = source.on_market_event(completed.event)
        if proposal is not None:
            proposals.append(proposal)
    final = aggregator.complete()
    if final is not None:
        proposal = source.on_market_event(final.event)
        if proposal is not None:
            proposals.append(proposal)
    return tuple(proposals), source, aggregator


class _RejectedSource:
    def __init__(self, proposal: WorkspaceSignalProposal) -> None:
        self.proposal = proposal

    def on_market_event(self, _event: WorkspaceMarketEvent) -> WorkspaceSignalProposal:
        return self.proposal


class _TrackingAlligator:
    def __init__(self) -> None:
        self.updated = 0
        self.evaluated = 0

    def on_market_event(self, _event: WorkspaceMarketEvent):
        self.updated += 1
        return None

    def evaluate(self, *_args, **_kwargs):
        self.evaluated += 1
        raise AssertionError("Alligator must not evaluate rejected MACD quality")


def _assert_reject_stops_before_alligator() -> None:
    proposal = WorkspaceSignalProposal(
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.00001,
        macd_state=MACD_STATE_CROSS_UP,
        alligator_confirmation="DISABLED",
        reason="MACD_CROSS_TOO_FLAT; final_quality_pass=False",
        source_reason_code="MACD_CROSS_TOO_FLAT",
        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        filter_reason_code="MACD_CROSS_TOO_FLAT",
    )
    event = WorkspaceMarketEvent(
        timestamp=START_UTC,
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=1.09994,
        ask=1.10006,
        spread=0.00012,
        open=1.10000,
        high=1.10020,
        low=1.09980,
        close=1.10000,
        volume=100.0,
        source_mode="REPLAY",
    )
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm()
    tracker = _TrackingAlligator()
    algorithm.source = _RejectedSource(proposal)  # type: ignore[assignment]
    algorithm.signal_filter = tracker  # type: ignore[assignment]
    algorithm.started = True
    output = algorithm.on_market_event(event)
    assert output == proposal
    assert tracker.updated == 1
    assert tracker.evaluated == 0


def main() -> None:
    if not M1_FILE.is_file():
        raise FileNotFoundError("Real EURUSD M1 history is required: " + str(M1_FILE))

    _assert_reject_stops_before_alligator()
    data_set = _data_set()
    linear, linear_source, linear_aggregator = _run_source(
        data_set,
        mode="LINEAR",
    )
    extended, extended_source, extended_aggregator = _run_source(
        data_set,
        mode="EXTENDED",
    )
    repeated, repeated_source, repeated_aggregator = _run_source(
        data_set,
        mode="EXTENDED",
    )

    assert len(linear) == 320
    assert len(extended) == len(linear)
    assert extended == repeated
    assert extended_source.quality_diagnostics == repeated_source.quality_diagnostics
    assert linear_source.quality_diagnostics == ()
    assert linear_aggregator.completed_bars == 3888
    assert extended_aggregator.completed_bars == 3888
    assert repeated_aggregator.completed_bars == 3888

    decisions = Counter(item.filter_decision for item in extended)
    reasons = Counter(item.source_reason_code for item in extended)
    assert decisions == {
        WORKSPACE_SIGNAL_FILTER_ALLOW: 23,
        WORKSPACE_SIGNAL_FILTER_REJECT: 297,
    }
    assert reasons == {
        "MACD_CROSS_ACCEPTED": 23,
        "MACD_EXTREMUM_NOT_FOUND": 74,
        "MACD_EXTREMUM_TOO_WEAK": 133,
        "MACD_EXTREMUM_DISTANCE_TOO_SMALL": 49,
        "MACD_CROSS_TOO_FLAT": 41,
    }
    assert len(extended_source.quality_diagnostics) == 320
    assert all(item.source_reason_code == "MACD_CLASSIC_CROSS" for item in linear)
    assert all(item.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW for item in linear)

    accepted = tuple(
        item
        for item in extended
        if item.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
    )
    rejected = tuple(
        item
        for item in extended
        if item.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
    )
    assert all(item.source_reason_code == "MACD_CROSS_ACCEPTED" for item in accepted)
    assert all(item.filter_reason_code is None for item in accepted)
    assert all(item.filter_reason_code == item.source_reason_code for item in rejected)
    assert all("effective_angle=" in item.reason for item in extended)
    assert all("final_quality_pass=" in item.reason for item in extended)

    angle_40, _angle_40_source, _angle_40_aggregator = _run_source(
        data_set,
        mode="EXTENDED",
        angle=40.0,
    )
    angle_40_decisions = Counter(item.filter_decision for item in angle_40)
    assert angle_40_decisions[WORKSPACE_SIGNAL_FILTER_ALLOW] == 39
    assert angle_40_decisions[WORKSPACE_SIGNAL_FILTER_REJECT] == 281

    print("Algorithm Workspace MACD Quality Filter result")
    print(f"  source_rows={data_set.report.accepted_rows}")
    print(f"  completed_m15_bars={extended_aggregator.completed_bars}")
    print(f"  classic_linear_crosses={len(linear)}")
    print(f"  extended_quality_candidates={len(extended)}")
    print(
        "  quality_allow_reject="
        f"{decisions[WORKSPACE_SIGNAL_FILTER_ALLOW]}/"
        f"{decisions[WORKSPACE_SIGNAL_FILTER_REJECT]}"
    )
    print(
        "  reject_reasons="
        f"not_found:{reasons['MACD_EXTREMUM_NOT_FOUND']} "
        f"weak:{reasons['MACD_EXTREMUM_TOO_WEAK']} "
        f"distance:{reasons['MACD_EXTREMUM_DISTANCE_TOO_SMALL']} "
        f"flat:{reasons['MACD_CROSS_TOO_FLAT']}"
    )
    print("  extended_mode_is_quality_filter=True")
    print("  linear_mode_unchanged=True")
    print("  full_diagnostic_reason=True")
    print("  quality_reject_blocks_before_alligator=True")
    print("  parameter_angle_45_to_40_allow=23->39")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_MACD_QUALITY_FILTER_CHECK=OK")


if __name__ == "__main__":
    main()
