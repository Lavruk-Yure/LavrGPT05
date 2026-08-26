# -*- coding: utf-8 -*-
"""tests.runtime_workspace.run_algorithm_workspace_historical_replay_runtime_check

End-to-end runtime check for CSV-backed Historical Replay in one WSP.
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
    WORKSPACE_STATE_ERROR,
    WORKSPACE_STATE_RESTORED,
    WORKSPACE_STATE_RUNNING,
    WORKSPACE_STATE_STOPPED,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_replay import WorkspaceReplayError  # noqa: E402
from core.workspace_replay_settings import WorkspaceReplaySettings  # noqa: E402
from engine.runtime_constants import WORKSPACE_REPLAY_SOURCE_CSV  # noqa: E402


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


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        history_path = directory / "eurusd_m15.csv"
        _write_history(history_path)

        repository = SessionRepository(directory / "Session")
        controller = AlgorithmWorkspaceController(repository)
        workspace = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
            parameters={
                "warmup_bars": 2,
                "spread_limit": 0.00020,
            },
            replay_settings={"speed": 1},
        )
        settings = WorkspaceReplaySettings(
            source_type=WORKSPACE_REPLAY_SOURCE_CSV,
            file_path=str(history_path),
            start_utc="2026-07-20T08:15:00Z",
            end_utc="2026-07-20T09:30:00Z",
            source_timezone="UTC",
            delimiter="AUTO",
            decimal_separator=".",
            spread=0.00014,
            source_name="EURUSD_M15_HISTORY",
            speed=2,
        )
        controller.update_workspace_replay_settings(
            workspace.workspace_uid,
            settings,
        )

        runtime = controller.ensure_workspace_runtime(workspace.workspace_uid)
        controller.begin_workspace_runtime_start(workspace.workspace_uid)
        controller.complete_workspace_runtime_start(workspace.workspace_uid)

        session = runtime.replay_session
        assert session is not None
        assert session.source_name == "EURUSD_M15_HISTORY"
        assert session.history_report is not None
        assert len(session.events) == 5
        first_run_events = session.events
        synthetic_fallback_blocked = session.source_name != "SYNTHETIC"
        assert synthetic_fallback_blocked

        report = session.history_report
        assert report.input_rows == 8
        assert report.accepted_rows == 5
        assert report.filtered_rows == 3
        assert report.derived_quotes == 5
        assert report.gap_count == 1
        quality_report_connected = any(
            entry.event == "CSV_HISTORY_LOADED"
            and entry.details.get("accepted_rows") == 5
            and entry.details.get("first_timestamp")
            == report.first_timestamp.isoformat()
            for entry in runtime.journal
        )
        assert quality_report_connected

        startup_events = controller.advance_workspace_replay(
            workspace.workspace_uid
        )
        assert len(startup_events) == 2
        assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
        assert runtime.context.warmup_complete
        assert runtime.context.spread_ok
        assert runtime.can_form_signal()

        assert controller.toggle_workspace_replay_pause(workspace.workspace_uid)
        stepped = controller.step_workspace_replay(workspace.workspace_uid)
        assert stepped is not None
        assert not controller.toggle_workspace_replay_pause(
            workspace.workspace_uid
        )
        controller.set_workspace_replay_speed(workspace.workspace_uid, 5)
        controller.advance_workspace_replay(workspace.workspace_uid)
        assert session.completed
        assert runtime.chart_snapshot().total_events == 5

        controller.begin_workspace_runtime_stop(workspace.workspace_uid)
        controller.complete_workspace_runtime_stop(workspace.workspace_uid)
        assert runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
        persisted = repository.load_workspace(workspace.workspace_uid)
        persisted_settings = WorkspaceReplaySettings.from_workspace(persisted)
        assert persisted_settings.file_path == str(history_path.resolve())
        assert persisted_settings.source_type == WORKSPACE_REPLAY_SOURCE_CSV

        controller.begin_workspace_runtime_start(workspace.workspace_uid)
        controller.complete_workspace_runtime_start(workspace.workspace_uid)
        restarted_session = runtime.replay_session
        assert restarted_session is not None
        assert restarted_session.events == first_run_events
        deterministic_restart = restarted_session.events == first_run_events
        assert deterministic_restart
        controller.begin_workspace_runtime_stop(workspace.workspace_uid)
        controller.complete_workspace_runtime_stop(workspace.workspace_uid)

        restored_controller = AlgorithmWorkspaceController(repository)
        restored_workspace = restored_controller.restore_workspaces()[0]
        assert restored_workspace.runtime_state == WORKSPACE_STATE_RESTORED
        restored_runtime = restored_controller.attach_workspace_runtime(
            restored_workspace
        )
        automatic_restart_blocked = bool(
            restored_runtime.context.runtime_state == WORKSPACE_STATE_STOPPED
            and restored_runtime.replay_session is None
            and restored_runtime.algorithm is None
        )
        assert automatic_restart_blocked

        history_path.unlink()
        missing_file_error = False
        try:
            restored_controller.begin_workspace_runtime_start(
                restored_workspace.workspace_uid
            )
            restored_controller.complete_workspace_runtime_start(
                restored_workspace.workspace_uid
            )
        except WorkspaceReplayError:
            missing_file_error = True
        assert missing_file_error
        assert restored_runtime.context.runtime_state == WORKSPACE_STATE_ERROR
        assert restored_runtime.replay_session is None
        assert restored_runtime.algorithm is None
        journal_events = [entry.event for entry in restored_runtime.journal]
        assert "RUNTIME_ERROR" in journal_events
        assert "STARTED" not in journal_events

        print("Algorithm Workspace Historical Replay Runtime result")
        print(f"  source={session.source_name}")
        print(f"  history_events={len(first_run_events)}")
        print(f"  accepted_rows={report.accepted_rows}")
        print(f"  filtered_rows={report.filtered_rows}")
        print(f"  gap_count={report.gap_count}")
        print(f"  derived_quotes={report.derived_quotes}")
        print(f"  synthetic_fallback_blocked={synthetic_fallback_blocked}")
        print(f"  quality_report_connected={quality_report_connected}")
        print("  warmup_completed=True")
        print("  spread_guard_passed=True")
        print("  pause_step_speed=True")
        print("  chart_updated=True")
        print(f"  deterministic_restart={deterministic_restart}")
        print(f"  missing_file_error={missing_file_error}")
        print(f"  automatic_restart_blocked={automatic_restart_blocked}")
        print("ALGORITHM_WORKSPACE_HISTORICAL_REPLAY_RUNTIME_CHECK=OK")


if __name__ == "__main__":
    main()
