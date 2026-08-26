# -*- coding: utf-8 -*-
"""End-to-end Historical Replay signal and risk determinism check."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import replace
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
from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithm,
    WorkspaceSignalOutput,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_replay import REPLAY_SPEED_MAX  # noqa: E402
from core.workspace_runtime import (  # noqa: E402
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
    WorkspaceTradeIntent,
)
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.constants import (  # noqa: E402
    REPLAY_RISK_SETTING_DAILY_REALIZED_PNL,
    REPLAY_RISK_SETTING_EQUITY,
    REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT,
    RISK_DECISION_ALLOW,
    RISK_DECISION_BLOCK,
    RISK_REASON_APPROVED,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
)
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402


class HistoricalRiskProbeAlgorithm(WorkspaceAlgorithm):
    """Emit the same broker-neutral trade intent for every historical bar."""

    def __init__(self) -> None:
        self.context: WorkspaceRuntimeContext | None = None
        self.started = False

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        _ = parameters
        self.context = context

    def start(self) -> None:
        assert self.context is not None
        self.started = True

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        assert self.started
        return WorkspaceSignalProposal(
            signal_type="HISTORICAL_RISK_ENTRY",
            direction="BUY",
            strength=0.80,
            macd_state="LINEAR_UP",
            alligator_confirmation="SAME_TIMEFRAME",
            reason="historical replay probe",
            trade_intent=WorkspaceTradeIntent(
                requested_volume=500.0,
                estimated_loss_at_stop=400.0,
                stop_loss=event.close - 0.0010,
            ),
        )

    def on_order_event(self, event: object) -> None:
        _ = event

    def stop(self) -> None:
        self.started = False


def _write_history(path: Path) -> None:
    path.write_text(
        "time,open,high,low,close,volume\n"
        "2026-07-20 08:00:00,1.1400,1.1410,1.1390,1.1405,100\n"
        "2026-07-20 08:15:00,1.1405,1.1415,1.1400,1.1410,110\n"
        "2026-07-20 08:30:00,1.1410,1.1420,1.1405,1.1415,120\n"
        "2026-07-20 09:00:00,1.1415,1.1425,1.1410,1.1420,130\n"
        "2026-07-20 09:15:00,1.1420,1.1430,1.1415,1.1425,140\n"
        "2026-07-20 09:30:00,1.1425,1.1435,1.1420,1.1430,150\n"
        "2026-07-20 09:45:00,1.1430,1.1440,1.1425,1.1435,160\n"
        "2026-07-20 10:00:00,1.1435,1.1445,1.1430,1.1440,170\n",
        encoding="utf-8",
    )


def _workspace(history_path: Path) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id="DUM513747",
        account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="HistoricalRiskProbeAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "warmup_bars": 2,
            "spread_limit": 0.00020,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(history_path),
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "HISTORICAL_RISK_TEST",
            REPLAY_RISK_SETTING_EQUITY: 100_000.0,
            REPLAY_RISK_SETTING_DAILY_REALIZED_PNL: -250.0,
            REPLAY_RISK_SETTING_OPEN_POSITIONS_COUNT: 1,
        },
    )


def _run(
    workspace: AlgorithmWorkspace,
    *,
    speed: int,
    step_mode: bool,
    daily_realized_pnl: float | None = -250.0,
) -> tuple[
    tuple[WorkspaceSignalRecord, ...],
    tuple[tuple[str, str | None], ...],
    WorkspaceRiskAccountSnapshot,
    int,
]:
    replay_settings = dict(workspace.replay_settings)
    replay_settings["speed"] = speed
    replay_settings[
        REPLAY_RISK_SETTING_DAILY_REALIZED_PNL
    ] = daily_realized_pnl
    run_workspace = replace(workspace, replay_settings=replay_settings)
    runtime = WorkspaceRuntime(
        run_workspace,
        algorithm_factory=lambda _algorithm_id: HistoricalRiskProbeAlgorithm(),
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    snapshot = runtime.risk_account_snapshot
    assert session is not None
    assert snapshot is not None

    if step_mode:
        assert runtime.toggle_replay_pause()
        while not session.completed:
            assert runtime.step_replay() is not None
    else:
        while not session.completed:
            runtime.advance_replay()

    risk_journal = tuple(
        (
            entry.event,
            entry.details.get("reason_code"),
        )
        for entry in runtime.journal
        if entry.event in {"RISK_ALLOWED", "RISK_BLOCKED"}
    )
    return (
        runtime.signal_records(),
        risk_journal,
        snapshot,
        runtime.chart_snapshot().total_events,
    )


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        history_path = Path(temp_dir) / "eurusd_m15.csv"
        _write_history(history_path)
        workspace = _workspace(history_path)

        runs = {
            "1x": _run(workspace, speed=1, step_mode=False),
            "2x": _run(workspace, speed=2, step_mode=False),
            "5x": _run(workspace, speed=5, step_mode=False),
            "10x": _run(workspace, speed=10, step_mode=False),
            "100x": _run(workspace, speed=100, step_mode=False),
            "1000x": _run(workspace, speed=1000, step_mode=False),
            "MAX": _run(
                workspace,
                speed=REPLAY_SPEED_MAX,
                step_mode=False,
            ),
            "step": _run(workspace, speed=1, step_mode=True),
        }
        baseline_records, baseline_journal, baseline_snapshot, chart_events = (
            runs["1x"]
        )
        assert len(baseline_records) == 8
        assert chart_events == 8
        assert not baseline_records[0].accepted
        assert baseline_records[0].reason == "warmup incomplete"
        assert all(record.accepted for record in baseline_records[1:])
        assert all(
            record.risk_decision == RISK_DECISION_ALLOW
            for record in baseline_records[1:]
        )
        assert all(
            record.risk_reason_code == RISK_REASON_APPROVED
            for record in baseline_records[1:]
        )
        assert len(baseline_journal) == 7
        assert baseline_snapshot.synthetic
        assert baseline_snapshot.equity == 100_000.0
        assert baseline_snapshot.daily_realized_pnl == -250.0
        assert baseline_snapshot.open_positions_count == 1

        for records, journal, snapshot, total_events in runs.values():
            assert records == baseline_records
            assert journal == baseline_journal
            assert snapshot == baseline_snapshot
            assert total_events == chart_events
            assert all(
                not record.risk_execution_attempted for record in records
            )

        missing_records, missing_journal, missing_snapshot, _unused = _run(
            workspace,
            speed=1,
            step_mode=False,
            daily_realized_pnl=None,
        )
        assert missing_snapshot.daily_realized_pnl is None
        assert not missing_records[0].accepted
        assert all(not record.accepted for record in missing_records[1:])
        assert all(
            record.risk_decision == RISK_DECISION_BLOCK
            for record in missing_records[1:]
        )
        assert all(
            record.risk_reason_code
            == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
            for record in missing_records[1:]
        )
        assert len(missing_journal) == 7

        print("Algorithm Workspace Historical Replay Risk result")
        print("  source=HISTORICAL_RISK_TEST")
        print(f"  historical_bars={len(baseline_records)}")
        print("  synthetic_account_snapshot=True")
        print("  snapshot_timestamp_from_history=True")
        print("  risk_allowed=7")
        print("  warmup_rejected=1")
        print("  speed_1x_2x_5x_10x_100x_1000x_max_deterministic=True")
        print("  pause_step_deterministic=True")
        print("  chart_events_preserved=True")
        print("  missing_daily_pnl_not_zero=True")
        print("  signals_journal_connected=True")
        print("  broker_execution_attempted=False")
        print("ALGORITHM_WORKSPACE_HISTORICAL_REPLAY_RISK_CHECK=OK")


if __name__ == "__main__":
    main()
