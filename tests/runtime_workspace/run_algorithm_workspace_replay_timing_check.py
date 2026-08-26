# -*- coding: utf-8 -*-
"""RoadMap98.5.4.5 Historical Replay selection/run timing check."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.translation_policy import translation_overrides_for_key  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402


def _write_m1_history(path: Path) -> None:
    rows = ["timestamp,open,high,low,close,volume"]
    start = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    for index in range(45):
        timestamp = start + timedelta(minutes=index)
        price = 1.10000 + index * 0.00001
        rows.append(
            f"{timestamp.isoformat().replace('+00:00', 'Z')},"
            f"{price:.5f},{price:.5f},{price:.5f},{price:.5f},0"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        history_path = Path(temp_dir) / "eurusd_m1.csv"
        _write_m1_history(history_path)
        workspace = AlgorithmWorkspace.create(
            broker="IB",
            account_id="DUM513747",
            account_mode="PAPER",
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
            parameters={"warmup_bars": 1, "spread_limit": 0.00020},
            replay_settings={
                "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
                "file_path": str(history_path),
                "source_timeframe": "M1",
                "source_timezone": "UTC",
                "delimiter": "AUTO",
                "decimal_separator": ".",
                "spread": 0.00012,
                "speed": 1000,
            },
        )
        runtime = WorkspaceRuntime(workspace)
        runtime.begin_start()
        runtime.complete_start()
        session = runtime.replay_session
        assert session is not None
        while not session.completed:
            runtime.advance_replay()

        summary = runtime.historical_summary
        assert summary is not None
        assert summary.source_timeframe == "M1"
        assert summary.timeframe == "M15"
        assert summary.csv_selection_elapsed_seconds is not None
        assert summary.csv_selection_elapsed_seconds >= 0.0
        assert summary.replay_elapsed_seconds is not None
        assert summary.replay_elapsed_seconds >= 0.0
        assert any(
            entry.event == "CSV_HISTORY_LOADED"
            and entry.details.get("csv_selection_elapsed_seconds") is not None
            for entry in runtime.journal
        )
        assert any(
            entry.event == "SESSION_COMPLETED"
            and entry.details.get("replay_elapsed_seconds") is not None
            for entry in runtime.journal
        )

    runtime_source = (PROJECT_ROOT / "core" / "workspace_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "selection_started = time.monotonic()" in runtime_source
    assert "_historical_replay_started_monotonic" in runtime_source
    assert "replay_elapsed_seconds" in runtime_source

    ui_path = PROJECT_ROOT / "ui" / "algorithm_workspace_historical_summary_dialog.ui"
    ui_source = ui_path.read_text(encoding="utf-8")
    assert "lblSourceTimeframe" in ui_source
    assert "lblCsvSelectionTime" in ui_source
    assert "lblReplayTime" in ui_source

    assert "Час вибірки CSV:" in translation_overrides_for_key(
        "AlgorithmWorkspaceHistoricalSummaryDialog.csvSelectionTime"
    ).get("uk", "")
    assert "Час прогону Replay:" in translation_overrides_for_key(
        "AlgorithmWorkspaceHistoricalSummaryDialog.replayTime"
    ).get("uk", "")

    print("Algorithm Workspace Replay Timing result")
    print("  source_timeframe=M1")
    print("  strategy_timeframe=M15")
    print("  csv_selection_monotonic_timing=True")
    print("  replay_run_monotonic_timing=True")
    print("  summary_carries_source_timeframe=True")
    print("  designer_timing_fields=True")
    print("  ukrainian_timing_labels=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_REPLAY_TIMING_CHECK=OK")


if __name__ == "__main__":
    main()
