# -*- coding: utf-8 -*-
"""RoadMap98.5 controlled Alligator mode comparison check."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_historical_comparison import (  # noqa: E402
    HISTORICAL_COMPARISON_MODES,
    WorkspaceHistoricalComparisonError,
    WorkspaceHistoricalComparisonRun,
    WorkspaceHistoricalComparisonVariant,
    build_workspace_historical_mode_comparison,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    REPLAY_SPEED_MAX,
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from core.workspace_signal_statistics import (  # noqa: E402
    WorkspaceSignalComparisonReport,
    WorkspaceSignalQualityPolicy,
    build_workspace_signal_comparison,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED,
)


class BrokerRequestProbe(WorkspaceBrokerMarketProviderProtocol):
    def __init__(self) -> None:
        self.requests = 0

    def start_workspace(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = (
            workspace_uid,
            broker,
            account_id,
            symbol,
            timeframe,
            warmup_bars,
            spread_limit,
        )
        self.requests += 1
        return ()

    def poll_workspace(
        self,
        workspace_uid: str,
    ) -> WorkspaceMarketEvent | None:
        _ = workspace_uid
        self.requests += 1
        return None

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        _ = workspace_uid
        self.requests += 1
        return True

    def suspend_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        _ = workspace_uid
        self.requests += 1
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        _ = workspace_uid
        self.requests += 1


class FixedReplayService(WorkspaceReplayService):
    def __init__(
        self,
        events: tuple[WorkspaceMarketEvent, ...],
    ) -> None:
        super().__init__()
        self.events = events

    def create_synthetic_session(
        self,
        *,
        broker: str,
        symbol: str,
        timeframe: str,
        replay_settings: dict[str, Any] | None = None,
    ) -> WorkspaceReplaySession:
        _ = broker, symbol, timeframe
        settings = dict(replay_settings or {})
        return WorkspaceReplaySession(
            events=self.events,
            source_name="ROADMAP98_ALLIGATOR_COMPARISON",
            speed=int(settings.get("speed", REPLAY_SPEED_MAX)),
        )


def _append_segment(
    closes: list[float],
    count: int,
    delta: float,
) -> None:
    start = closes[-1]
    closes.extend(start + (index + 1) * delta for index in range(count))


def _closes() -> tuple[float, ...]:
    closes: list[float] = [1.2000] * 35
    _append_segment(closes, 24, 0.00015)
    _append_segment(closes, 24, -0.00015)
    closes.extend([closes[-1]] * (336 - len(closes)))
    _append_segment(closes, 96, 0.00008)
    _append_segment(closes, 24, -0.00005)
    _append_segment(closes, 64, 0.00007)
    _append_segment(closes, 192, -0.00010)
    _append_segment(closes, 24, 0.00005)
    _append_segment(closes, 64, -0.00008)
    return tuple(closes)


def _event(index: int, close: float) -> WorkspaceMarketEvent:
    spread = 0.00012
    return WorkspaceMarketEvent(
        timestamp=datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        broker="IB",
        symbol="EURUSD",
        timeframe="M15",
        bid=close - spread / 2.0,
        ask=close + spread / 2.0,
        spread=spread,
        open=close,
        high=close + 0.00020,
        low=close - 0.00020,
        close=close,
        volume=100.0 + index,
        source_mode=WORKSPACE_DATA_MODE_REPLAY,
    )


def _events() -> tuple[WorkspaceMarketEvent, ...]:
    return tuple(_event(index, close) for index, close in enumerate(_closes()))


def _workspace(mode: str) -> AlgorithmWorkspace:
    filter_enabled = mode != WORKSPACE_ALLIGATOR_CONFIRMATION_DISABLED
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "LINEAR",
            "alligator_filter_enabled": filter_enabled,
            "alligator_confirmation": mode,
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        replay_settings={
            "speed": REPLAY_SPEED_MAX,
            "spread": 0.00012,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
    )


def _run_variant(
    mode: str,
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[
    WorkspaceHistoricalComparisonRun,
    tuple[WorkspaceSignalRecord, ...],
    int,
]:
    records: list[WorkspaceSignalRecord] = []
    broker_probe = BrokerRequestProbe()
    algorithm = WorkspaceMacdAlligatorReplayAlgorithm("RailAlgorithm")
    runtime = WorkspaceRuntime(
        _workspace(mode),
        replay_service=FixedReplayService(events),
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=broker_probe,
        signal_record_observer=records.append,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    summary = runtime.historical_summary
    assert summary is not None
    assert runtime.replay_execution is not None
    assert not runtime.owned_snapshot.active_positions
    return (
        WorkspaceHistoricalComparisonRun(mode=mode, summary=summary),
        tuple(records),
        broker_probe.requests,
    )


def _variant_signature(
    variant: WorkspaceHistoricalComparisonVariant,
) -> tuple[object, ...]:
    return (
        variant.mode,
        variant.alligator_timeframe,
        variant.signals,
        variant.allowed_signals,
        variant.rejected_signals,
        variant.missed_profitable_moves,
        variant.average_confirmation_delay_seconds,
        variant.trades,
        variant.win_rate_percent,
        variant.net_profit,
        variant.profit_factor,
        variant.maximum_drawdown,
        variant.maximum_drawdown_percent,
        variant.average_trade,
    )


def _assert_input_guard(
    runs: tuple[WorkspaceHistoricalComparisonRun, ...],
    signal_report: WorkspaceSignalComparisonReport,
) -> None:
    duplicate = replace(runs[1], mode=runs[0].mode)
    blocked = False
    try:
        build_workspace_historical_mode_comparison(
            (runs[0], duplicate, runs[2], runs[3]),
            signal_report,
        )
    except WorkspaceHistoricalComparisonError:
        blocked = True
    assert blocked


def main() -> None:
    events = _events()
    runs: list[WorkspaceHistoricalComparisonRun] = []
    record_variants: list[tuple[WorkspaceSignalRecord, ...]] = []
    broker_requests = 0

    for mode in HISTORICAL_COMPARISON_MODES:
        run, records, requests = _run_variant(mode, events)
        runs.append(run)
        record_variants.append(records)
        broker_requests += requests

    assert len({len(records) for records in record_variants}) == 1
    signal_report = build_workspace_signal_comparison(
        tuple(record_variants),
        events,
        WorkspaceSignalQualityPolicy(
            horizon_bars=8,
            minimum_directional_move=0.00020,
        ),
    )
    report = build_workspace_historical_mode_comparison(
        tuple(runs),
        signal_report,
    )
    repeat = build_workspace_historical_mode_comparison(
        tuple(runs),
        signal_report,
    )
    assert report == repeat
    assert report.proposal_signatures_identical
    assert report.deterministic
    assert report.accepted_bars == len(events)
    assert report.skipped_bars == 0
    assert report.gaps == 0
    assert broker_requests == 0
    assert report.broker_requests == 0
    assert not report.broker_execution_attempted
    assert tuple(item.mode for item in report.variants) == HISTORICAL_COMPARISON_MODES
    assert all(item.signals == report.variants[0].signals for item in report.variants)
    assert report.variants[0].rejected_signals == 0
    assert report.variants[0].missed_profitable_moves == 0
    assert report.variants[0].alligator_timeframe is None
    assert report.variants[0].average_confirmation_delay_seconds is None
    assert any(item.rejected_signals > 0 for item in report.variants[1:])
    _assert_input_guard(tuple(runs), signal_report)

    print("Algorithm Workspace Alligator Mode Comparison result")
    print(f"  historical_bars={report.accepted_bars}")
    print(f"  symbol={report.symbol}")
    print(f"  timeframe={report.timeframe}")
    print(f"  initial_balance={report.initial_balance:.2f}")
    print("  controlled_variable=ALLIGATOR_MODE_ONLY")
    print(f"  quality_horizon_bars={report.quality_horizon_bars}")
    print(
        "  quality_minimum_directional_move="
        f"{report.quality_minimum_directional_move:.5f}"
    )
    for item in report.variants:
        profit_factor = (
            "N/A" if item.profit_factor is None else f"{item.profit_factor:.4f}"
        )
        delay = (
            "N/A"
            if item.average_confirmation_delay_seconds is None
            else f"{item.average_confirmation_delay_seconds:.1f}"
        )
        print(
            f"  {item.mode}: signals={item.signals}, "
            f"allow={item.allowed_signals}, reject={item.rejected_signals}, "
            f"trades={item.trades}, win_rate={item.win_rate_percent:.2f}%, "
            f"net_pnl={item.net_profit:.2f}, PF={profit_factor}, "
            f"max_dd={item.maximum_drawdown:.2f}, "
            f"avg_trade={item.average_trade:.4f}, "
            f"missed={item.missed_profitable_moves}, "
            f"avg_delay_s={delay}"
        )
    print("  proposal_signatures_identical=True")
    print("  deterministic=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_MODE_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
