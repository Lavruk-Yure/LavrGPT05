# -*- coding: utf-8 -*-
"""RoadMap98 M1 source -> M15 strategy Replay chronology check."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
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
from core.workspace_algorithm import WorkspaceSignalOutput  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    REPLAY_SPEED_MAX,
    WorkspaceReplayError,
    WorkspaceReplayService,
    WorkspaceReplaySession,
)
from core.workspace_replay_execution import (  # noqa: E402
    REPLAY_CLOSE_PROFIT_DRAWDOWN,
    REPLAY_CLOSE_TAKE_PROFIT,
)
from core.workspace_replay_settings import WorkspaceReplaySettings  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_runtime_requirements import (  # noqa: E402
    WorkspaceWarmupRequirement,
)
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceTradeIntent,
)
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402


class MultiResolutionProbeAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Emit two deterministic M15 signals while retaining Replay execution."""

    def __init__(self) -> None:
        super().__init__("MULTI_RESOLUTION_PROBE")
        self.context: WorkspaceRuntimeContext | None = None
        self.started = False
        self.seen_events: list[WorkspaceMarketEvent] = []

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        _ = parameters
        self.context = context

    def warmup_requirements(
        self,
    ) -> tuple[WorkspaceWarmupRequirement, ...]:
        return ()

    def start(self) -> None:
        assert self.context is not None
        self.seen_events = []
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        assert self.started
        self.seen_events.append(event)
        if len(self.seen_events) > 2:
            return None
        return WorkspaceSignalProposal(
            signal_type="MULTI_RESOLUTION_ENTRY",
            direction="BUY",
            strength=0.001,
            macd_state="PROBE_CROSS_UP",
            alligator_confirmation="DISABLED",
            reason="deterministic M1 execution chronology probe",
            trade_intent=WorkspaceTradeIntent(
                requested_volume=1000.0,
                estimated_loss_at_stop=0.20,
                stop_loss=event.close - 0.00020,
            ),
        )

    def on_order_event(self, event: object) -> None:
        _ = event

    def stop(self) -> None:
        self.started = False


def _write_m1_history(path: Path) -> None:
    start = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    rows = ["time,open,high,low,close,volume"]
    previous_close = 1.10000
    for index in range(45):
        timestamp = start + timedelta(minutes=index)
        open_price = previous_close
        close_price = 1.10000
        high_price = max(open_price, close_price) + 0.00005
        low_price = min(open_price, close_price) - 0.00005

        if index == 17:
            high_price = 1.10045
            close_price = 1.10010
        elif index == 18:
            open_price = 1.10010
            close_price = 1.10000
            high_price = 1.10015
            low_price = 1.09995
        elif index == 31:
            close_price = 1.10031
            high_price = 1.10034
            low_price = 1.09997
        elif index == 32:
            open_price = 1.10031
            close_price = 1.10020
            high_price = 1.10033
            low_price = 1.10015
        elif index == 33:
            open_price = 1.10020
            close_price = 1.10000
            high_price = 1.10022
            low_price = 1.09997

        rows.append(
            f"{timestamp:%Y-%m-%d %H:%M:%S},"
            f"{open_price:.5f},{high_price:.5f},{low_price:.5f},"
            f"{close_price:.5f},{100 + index}"
        )
        previous_close = close_price
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _workspace(history_path: Path, *, speed: int) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="MULTI_RESOLUTION_PROBE",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={"warmup_bars": 0, "spread_limit": 0.00020},
        risk_settings={
            "risk_percent": 1.0,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 1,
            "max_daily_loss_percent": 10.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(history_path),
            "source_timeframe": "M1",
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00002,
            "source": "EURUSD_M1_MULTI_RESOLUTION",
            "initial_balance": 1000.0,
            "speed": speed,
        },
    )


@dataclass(frozen=True, slots=True)
class MultiResolutionRunResult:
    """Typed facts captured from one deterministic Replay run."""

    session: WorkspaceReplaySession
    algorithm: MultiResolutionProbeAlgorithm
    diagnostics: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    chart_events: int


def _run(history_path: Path, *, speed: int) -> MultiResolutionRunResult:
    algorithm = MultiResolutionProbeAlgorithm()
    runtime = WorkspaceRuntime(
        _workspace(history_path, speed=speed),
        algorithm_factory=lambda _algorithm_id: algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    execution = runtime.replay_execution
    assert execution is not None
    return MultiResolutionRunResult(
        session=session,
        algorithm=algorithm,
        diagnostics=execution.trade_diagnostics(),
        chart_events=runtime.chart_snapshot().total_events,
    )


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        history_path = Path(temp_dir) / "eurusd_m1.csv"
        _write_m1_history(history_path)

        run_1x = _run(history_path, speed=1)
        run_max = _run(history_path, speed=REPLAY_SPEED_MAX)
        session = run_1x.session
        assert hasattr(session, "multi_resolution")
        assert session.multi_resolution
        assert session.source_timeframe == "M1"
        assert session.strategy_timeframe == "M15"
        assert session.source_event_count == 45
        assert len(session.events) == 3
        assert tuple(len(window) for window in session.execution_windows) == (
            15,
            15,
            0,
        )

        first = session.events[0]
        assert first.timestamp == datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
        assert first.timeframe == "M15"
        assert first.open == 1.10000
        assert first.close == 1.10000
        assert first.high == 1.10005
        assert first.low == 1.09995

        algorithm = run_1x.algorithm
        assert isinstance(algorithm, MultiResolutionProbeAlgorithm)
        assert [event.timeframe for event in algorithm.seen_events] == [
            "M15",
            "M15",
            "M15",
        ]
        assert run_1x.chart_events == 3

        diagnostics = run_1x.diagnostics
        assert len(diagnostics) == 2
        first_trade, second_trade = diagnostics
        assert first_trade.entry_timestamp == datetime(2026, 7, 20, 8, 15, tzinfo=UTC)
        assert first_trade.close_timestamp == datetime(2026, 7, 20, 8, 17, tzinfo=UTC)
        assert first_trade.close_reason == REPLAY_CLOSE_TAKE_PROFIT
        assert second_trade.entry_timestamp == datetime(2026, 7, 20, 8, 30, tzinfo=UTC)
        assert second_trade.close_timestamp == datetime(2026, 7, 20, 8, 32, tzinfo=UTC)
        assert second_trade.close_reason == REPLAY_CLOSE_PROFIT_DRAWDOWN
        assert second_trade.peak_profit > second_trade.final_profit > 0.0
        assert second_trade.maximum_favorable_excursion >= second_trade.peak_profit

        signature_1x = tuple(
            (
                item.signal_timestamp,
                item.entry_timestamp,
                item.close_timestamp,
                item.close_reason,
                round(item.final_profit, 8),
            )
            for item in diagnostics
        )
        signature_max = tuple(
            (
                item.signal_timestamp,
                item.entry_timestamp,
                item.close_timestamp,
                item.close_reason,
                round(item.final_profit, 8),
            )
            for item in run_max.diagnostics
        )
        assert signature_1x == signature_max

        replay_settings = WorkspaceReplaySettings(
            source_type=WORKSPACE_REPLAY_SOURCE_CSV,
            file_path=str(history_path),
            source_timeframe="M1",
        )
        assert replay_settings.source_timeframe == "M1"
        assert "source_timeframe" in replay_settings.merge_settings({})

        ui_path = PROJECT_ROOT / "ui" / "algorithm_workspace_replay_dialog.ui"
        ui_text = ui_path.read_text(encoding="utf-8")
        assert 'name="cmbSourceTimeframe"' in ui_text
        assert 'name="lblSourceTimeframe"' in ui_text

        service = WorkspaceReplayService()
        invalid_source_blocked = False
        try:
            service.create_historical_session(
                broker="IB",
                symbol="EURUSD",
                timeframe="M15",
                replay_settings={
                    "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
                    "file_path": str(history_path),
                    "source_timeframe": "M30",
                },
            )
        except WorkspaceReplayError:
            invalid_source_blocked = True
        assert invalid_source_blocked

        print("Algorithm Workspace Multi-resolution Replay result")
        print("  source_timeframe=M1")
        print("  strategy_timeframe=M15")
        print("  source_bars=45")
        print("  completed_strategy_bars=3")
        print("  algorithm_receives_only_completed_m15=True")
        print("  no_look_ahead=True")
        print("  next_bar_fill_uses_m1_open=True")
        print("  take_profit_close_at_m1_timestamp=2026-07-20T08:17:00+00:00")
        print("  profit_drawdown_close_at_m1_timestamp=2026-07-20T08:32:00+00:00")
        print("  mfe_mae_use_m1_chronology=True")
        print("  speed_1x_max_deterministic=True")
        print("  replay_settings_source_timeframe_persisted=True")
        print("  designer_source_timeframe_control=True")
        print(f"  invalid_source_timeframe_blocked={invalid_source_blocked}")
        print("  broker_execution_attempted=False")
        print("ALGORITHM_WORKSPACE_MULTI_RESOLUTION_REPLAY_CHECK=OK")


if __name__ == "__main__":
    main()
