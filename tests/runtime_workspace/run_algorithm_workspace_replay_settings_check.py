# -*- coding: utf-8 -*-
"""Runtime check for persisted per-WSP Replay-only configuration."""

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
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_replay_settings import (  # noqa: E402
    WorkspaceReplaySettings,
    WorkspaceReplaySettingsError,
)
from core.workspace_runtime import WorkspaceRuntimeError  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_REPLAY_SOURCE_CSV,
    WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
)


def _write_history(path: Path) -> None:
    path.write_text(
        "time,open,high,low,close,volume\n"
        "2026-07-20 08:00:00,1.1400,1.1410,1.1390,1.1405,100\n"
        "2026-07-20 08:15:00,1.1405,1.1415,1.1400,1.1410,110\n"
        "2026-07-20 08:30:00,1.1410,1.1420,1.1405,1.1415,120\n",
        encoding="utf-8",
    )


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        history_path = directory / "eurusd_m15.csv"
        _write_history(history_path)

        repository = SessionRepository(directory / "Session")
        controller = AlgorithmWorkspaceController(repository)
        first = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="EURUSD",
            timeframe="M15",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
            parameters={"warmup_bars": 1, "spread_limit": 0.00020},
            replay_settings={
                "speed": 2,
                "future_replay_key": "KEEP",
                "download_start_date": "2026-06-20",
                "download_end_date": "2026-07-20",
                "download_timezone": "Europe/Kyiv",
            },
        )
        second = controller.create_workspace(
            broker="IB",
            account_id="DUM513747",
            account_mode=WORKSPACE_ACCOUNT_MODE_PAPER,
            symbol="GBPUSD",
            timeframe="H1",
            algorithm="RailAlgorithm",
            data_mode=WORKSPACE_DATA_MODE_REPLAY,
            control_mode=WORKSPACE_CONTROL_MODE_MANUAL,
        )

        defaults = WorkspaceReplaySettings.from_workspace(second)
        assert defaults.source_type == WORKSPACE_REPLAY_SOURCE_SYNTHETIC
        assert defaults.file_path is None
        assert defaults.source_timezone == "UTC"
        assert defaults.initial_balance == 1_000.0
        assert defaults.speed == 1

        custom = WorkspaceReplaySettings(
            source_type=WORKSPACE_REPLAY_SOURCE_CSV,
            file_path=str(history_path),
            start_utc="2026-07-20T08:00:00Z",
            end_utc="2026-07-20T08:30:00Z",
            source_timezone="UTC",
            delimiter="AUTO",
            decimal_separator=".",
            spread=0.00014,
            source_name="EURUSD_M15_HISTORY",
            initial_balance=2_500.0,
            speed=2,
        )
        updated = controller.update_workspace_replay_settings(
            first.workspace_uid,
            custom,
        )
        assert updated.replay_settings["source_type"] == "CSV"
        assert updated.replay_settings["future_replay_key"] == "KEEP"
        assert updated.replay_settings["speed"] == 2
        assert "download_start_date" not in updated.replay_settings
        assert "download_end_date" not in updated.replay_settings
        assert "download_timezone" not in updated.replay_settings

        persisted = repository.load_workspace(first.workspace_uid)
        persisted_settings = WorkspaceReplaySettings.from_workspace(persisted)
        resolved_history_path = str(history_path.resolve())
        assert persisted_settings.file_path == resolved_history_path
        assert persisted_settings == WorkspaceReplaySettings(
            source_type=custom.source_type,
            file_path=resolved_history_path,
            start_utc=custom.start_utc,
            end_utc=custom.end_utc,
            source_timezone=custom.source_timezone,
            delimiter=custom.delimiter,
            decimal_separator=custom.decimal_separator,
            spread=custom.spread,
            source_name=custom.source_name,
            initial_balance=custom.initial_balance,
            speed=custom.speed,
        )
        second_persisted = repository.load_workspace(second.workspace_uid)
        assert WorkspaceReplaySettings.from_workspace(second_persisted) == defaults

        runtime = controller.attach_workspace_runtime(persisted)
        controller.begin_workspace_runtime_start(first.workspace_uid)
        controller.complete_workspace_runtime_start(first.workspace_uid)
        assert runtime.replay_session is not None
        assert runtime.replay_session.source_name == "EURUSD_M15_HISTORY"
        assert runtime.replay_session.history_report is not None
        assert len(runtime.replay_session.events) == 3

        active_edit_blocked = False
        try:
            controller.update_workspace_replay_settings(
                first.workspace_uid,
                defaults,
            )
        except WorkspaceRuntimeError:
            active_edit_blocked = True
        assert active_edit_blocked

        controller.begin_workspace_runtime_stop(first.workspace_uid)
        controller.complete_workspace_runtime_stop(first.workspace_uid)

        missing_file_blocked = False
        try:
            controller.update_workspace_replay_settings(
                first.workspace_uid,
                WorkspaceReplaySettings(
                    source_type=WORKSPACE_REPLAY_SOURCE_CSV,
                    file_path=str(directory / "missing.csv"),
                ),
            )
        except WorkspaceReplaySettingsError:
            missing_file_blocked = True
        assert missing_file_blocked

        invalid_values_blocked = 0
        invalid_payloads = (
            {"source_type": "UNKNOWN"},
            {
                "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
                "file_path": None,
            },
            {"source_timezone": "Unknown/Timezone"},
            {"delimiter": "^"},
            {"decimal_separator": "x"},
            {"spread": -0.00001},
            {"initial_balance": 99.99},
            {"initial_balance": 100_000.01},
            {
                "start_utc": "2026-07-20T09:00:00Z",
                "end_utc": "2026-07-20T08:00:00Z",
            },
        )
        for payload in invalid_payloads:
            values = {
                "source_type": WORKSPACE_REPLAY_SOURCE_SYNTHETIC,
                "file_path": None,
                "source_timezone": "UTC",
                "delimiter": "AUTO",
                "decimal_separator": ".",
                "spread": 0.00012,
                "initial_balance": 1_000.0,
                "speed": 1,
            }
            values.update(payload)
            try:
                WorkspaceReplaySettings(**values)
            except WorkspaceReplaySettingsError:
                invalid_values_blocked += 1
        assert invalid_values_blocked == len(invalid_payloads)

        print("Algorithm Workspace Replay Settings result")
        print(f"  workspace_uid={first.workspace_uid}")
        print(f"  source_type={custom.source_type}")
        print(f"  source_name={custom.source_name}")
        print(f"  start_utc={custom.start_utc}")
        print(f"  end_utc={custom.end_utc}")
        print(f"  source_timezone={custom.source_timezone}")
        print(f"  spread={custom.spread:.6f}")
        print(f"  initial_balance={custom.initial_balance:.2f}")
        print("  initial_balance_range=100.00..100000.00")
        print("  replay_download_fields_removed=True")
        print("  independent_workspaces=True")
        print("  future_keys_preserved=True")
        print(f"  active_edit_blocked={active_edit_blocked}")
        print("  absolute_path_persisted=True")
        print(f"  missing_file_blocked={missing_file_blocked}")
        print(f"  invalid_values_blocked={invalid_values_blocked}")
        print("ALGORITHM_WORKSPACE_REPLAY_SETTINGS_CHECK=OK")


if __name__ == "__main__":
    main()
