# -*- coding: utf-8 -*-
"""RoadMap100 manual Replay ``Крок`` / ``Тік`` chronology regression.

Перевірка відтворює multi-resolution M1 -> M15 без broker execution і доводить
нову diagnostic semantics: UI ``Крок`` приймає завершений strategy M15 bar та
зупиняється перед його M1 execution window; ``Тік`` обробляє рівно один вже
staged M1 execution event і ніколи сам не просуває strategy M15 bar. Scheduler
у стані PAUSED також не має права догравати решту staged M1 window після одного
ручного Tick. Перший M1 після accepted signal має створити virtual position,
щоб Entry/SL/TP overlay можна було перевірити до внутрішньобарного закриття.
Старий programmatic ``step_replay()`` лишається full strategy step і окремо
покривається чинним multi-resolution regression. Тут broker integration
відсутня, а journal Tick явно фіксує broker_execution_attempted=False.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
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
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
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


class ReplayTickProbeAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Видати один deterministic signal на першому завершеному M15 bar."""

    def __init__(self) -> None:
        super().__init__("REPLAY_TICK_PROBE")
        self.context: WorkspaceRuntimeContext | None = None
        self.started = False
        self.strategy_events: list[WorkspaceMarketEvent] = []

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        _ = parameters
        self.context = context

    def warmup_requirements(self) -> tuple[WorkspaceWarmupRequirement, ...]:
        return ()

    def start(self) -> None:
        assert self.context is not None
        self.strategy_events = []
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        assert self.started
        self.strategy_events.append(event)
        if len(self.strategy_events) != 1:
            return None
        return WorkspaceSignalProposal(
            signal_type="REPLAY_TICK_ENTRY",
            direction="SELL",
            strength=0.001,
            macd_state="PROBE_CROSS_DOWN",
            alligator_confirmation="DISABLED",
            reason="manual Replay Tick chronology probe",
            trade_intent=WorkspaceTradeIntent(
                requested_volume=1000.0,
                estimated_loss_at_stop=0.20,
                stop_loss=event.close + 0.00020,
            ),
        )

    def on_order_event(self, event: object) -> None:
        _ = event

    def stop(self) -> None:
        self.started = False


def _write_m1_history(path: Path) -> None:
    """Записати три повні M15 buckets із детермінованими M1 timestamps."""
    start = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
    rows = ["time,open,high,low,close,volume"]
    for index in range(60):
        timestamp = start + timedelta(minutes=index)
        close = 1.10000 - index * 0.000001
        rows.append(
            f"{timestamp:%Y-%m-%d %H:%M:%S},"
            f"{close:.6f},{close + 0.00002:.6f},{close - 0.00002:.6f},"
            f"{close:.6f},{100 + index}"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _workspace(history_path: Path) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="REPLAY_TICK_PROBE",
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
            "enabled": False,
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
            "source": "EURUSD_M1_REPLAY_TICK",
            "initial_balance": 1000.0,
            "speed": 1,
        },
    )


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        history_path = Path(temp_dir) / "eurusd_m1_tick.csv"
        _write_m1_history(history_path)
        algorithm = ReplayTickProbeAlgorithm()
        runtime = WorkspaceRuntime(
            _workspace(history_path),
            algorithm_factory=lambda _algorithm_id: algorithm,
        )
        runtime.begin_start()
        runtime.complete_start()
        session = runtime.replay_session
        assert runtime.broker_market_provider is None
        assert session is not None
        assert session.multi_resolution
        assert session.source_timeframe == "M1"
        assert session.strategy_timeframe == "M15"

        runtime.toggle_replay_pause()
        strategy_event = runtime.step_replay_strategy_bar()
        assert strategy_event is not None
        assert strategy_event.timeframe == "M15"
        assert strategy_event.timestamp == datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
        assert runtime.context.current_execution_event is None
        assert len(runtime.owned_snapshot.active_orders) == 1
        assert len(runtime.owned_snapshot.active_positions) == 0
        assert len(algorithm.strategy_events) == 1

        first_tick = runtime.step_replay_tick()
        assert first_tick is not None
        assert first_tick.timeframe == "M1"
        assert first_tick.timestamp == datetime(2026, 8, 10, 8, 15, tzinfo=UTC)
        assert runtime.context.current_execution_event == first_tick
        assert len(runtime.owned_snapshot.active_orders) == 0
        assert len(runtime.owned_snapshot.active_positions) == 1
        position = runtime.owned_snapshot.active_positions[0]
        assert position.opened_at == first_tick.timestamp.isoformat()
        assert position.side == "SELL"

        session_index_after_first_tick = session.index
        scheduler_events = runtime.advance_replay()
        assert scheduler_events == []
        assert session.index == session_index_after_first_tick
        assert runtime.context.current_execution_event == first_tick
        assert runtime.replay_tick_available
        assert len(runtime.owned_snapshot.active_positions) == 1

        second_tick = runtime.step_replay_tick()
        assert second_tick is not None
        assert second_tick.timestamp == datetime(2026, 8, 10, 8, 16, tzinfo=UTC)
        assert len(algorithm.strategy_events) == 1
        assert len(runtime.owned_snapshot.active_positions) == 1

        next_strategy = runtime.step_replay_strategy_bar()
        assert next_strategy is not None
        assert next_strategy.timestamp == datetime(2026, 8, 10, 8, 15, tzinfo=UTC)
        assert len(algorithm.strategy_events) == 2
        assert runtime.context.current_execution_event is not None
        assert runtime.context.current_execution_event.timestamp == datetime(
            2026,
            8,
            10,
            8,
            29,
            tzinfo=UTC,
        )
        assert runtime.replay_tick_available

        second_window_ticks: list[WorkspaceMarketEvent] = []
        for _index in range(15):
            tick = runtime.step_replay_tick()
            assert tick is not None
            second_window_ticks.append(tick)
        assert second_window_ticks[0].timestamp == datetime(
            2026, 8, 10, 8, 30, tzinfo=UTC
        )
        assert second_window_ticks[-1].timestamp == datetime(
            2026, 8, 10, 8, 44, tzinfo=UTC
        )
        assert not runtime.replay_tick_available

        strategy_count_before_idle_tick = len(algorithm.strategy_events)
        session_index_before_idle_tick = session.index
        chart_count_before_idle_tick = runtime.chart_model.total_events
        market_event_before_idle_tick = runtime.context.current_market_event
        idle_tick = runtime.step_replay_tick()
        assert idle_tick is None
        assert len(algorithm.strategy_events) == strategy_count_before_idle_tick
        assert session.index == session_index_before_idle_tick
        assert runtime.chart_model.total_events == chart_count_before_idle_tick
        assert runtime.context.current_market_event == market_event_before_idle_tick

        third_strategy = runtime.step_replay_strategy_bar()
        assert third_strategy is not None
        assert third_strategy.timestamp == datetime(2026, 8, 10, 8, 30, tzinfo=UTC)
        assert len(algorithm.strategy_events) == 3
        assert runtime.replay_tick_available
        third_window_first_tick = runtime.step_replay_tick()
        assert third_window_first_tick is not None
        assert third_window_first_tick.timestamp == datetime(
            2026, 8, 10, 8, 45, tzinfo=UTC
        )

        tick_entries = [
            entry
            for entry in runtime.journal
            if entry.event == "EXECUTION_TICK_STEPPED"
        ]
        assert len(tick_entries) == 18
        assert all(
            entry.details.get("broker_execution_attempted") is False
            for entry in tick_entries
        )

        print("Algorithm Workspace Replay Tick result")
        print("  strategy_step_stops_before_execution_window=True")
        print("  first_tick_timeframe=M1")
        print("  first_tick_timestamp=2026-08-10T08:15:00+00:00")
        print("  first_tick_opens_virtual_position=True")
        print("  one_tick_one_execution_event=True")
        print("  paused_scheduler_preserves_pending_ticks=True")
        print("  next_strategy_step_consumes_remaining_window=True")
        print("  tick_never_advances_strategy_bar=True")
        print("  idle_tick_preserves_chart_navigation_state=True")
        print("  algorithm_receives_only_completed_m15=True")
        print("  no_look_ahead=True")
        print("  broker_requests=0")
        print("  broker_execution_attempted=False")
        print("ALGORITHM_WORKSPACE_REPLAY_TICK_CHECK=OK")


if __name__ == "__main__":
    main()
