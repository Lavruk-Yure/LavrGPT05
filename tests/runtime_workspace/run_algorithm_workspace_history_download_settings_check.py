# -*- coding: utf-8 -*-
"""Runtime check for separate WSP broker-history download settings."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.app_paths import get_base_dir  # noqa: E402
from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_ACCOUNT_MODE_PAPER,
    WORKSPACE_CONTROL_MODE_MANUAL,
    WORKSPACE_DATA_MODE_REPLAY,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_history_download_settings import (  # noqa: E402
    WorkspaceHistoryDownloadSettings,
    WorkspaceHistoryDownloadSettingsError,
)
from core.workspace_history_export import (  # noqa: E402
    WorkspaceHistoryCsvWriter,
)
from core.workspace_runtime import WorkspaceRuntimeError  # noqa: E402


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        default_writer = WorkspaceHistoryCsvWriter()
        assert default_writer.history_root == (
            get_base_dir() / "data" / "history"
        ).resolve()
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
            replay_settings={
                "download_start_date": "2026-06-20",
                "download_end_date": "2026-07-20",
                "download_timezone": "Europe/Kyiv",
            },
        )

        legacy = WorkspaceHistoryDownloadSettings.from_workspace(workspace)
        assert legacy.start_date == "2026-06-20"
        assert legacy.end_date == "2026-07-20"
        assert legacy.timezone == "Europe/Kyiv"

        destination = directory / "history" / "IB" / "EURUSD" / "M15"
        custom = WorkspaceHistoryDownloadSettings(
            broker="IB",
            account_id="DUM513747",
            symbol="EURUSD",
            timeframe="M15",
            start_date="2026-01-01",
            end_date="2026-07-27",
            timezone="UTC",
            destination_folder=str(destination),
        )
        updated = controller.update_workspace_history_download_settings(
            workspace.workspace_uid,
            custom,
        )
        persisted = repository.load_workspace(workspace.workspace_uid)
        persisted_values = WorkspaceHistoryDownloadSettings.from_workspace(
            persisted
        )
        assert persisted_values == custom
        assert "download_start_date" not in updated.replay_settings
        assert "download_end_date" not in updated.replay_settings
        assert "download_timezone" not in updated.replay_settings

        start_utc, end_utc = custom.period_utc()
        assert start_utc.isoformat() == "2026-01-01T00:00:00+00:00"
        assert end_utc.isoformat() == "2026-07-27T23:59:59+00:00"
        paris = replace(custom, timezone="Europe/Paris")
        paris_start, paris_end = paris.period_utc()
        assert paris_start.isoformat() == "2025-12-31T23:00:00+00:00"
        assert paris_end.isoformat() == "2026-07-27T21:59:59+00:00"

        current_day = replace(
            custom,
            start_date="2026-01-02",
            end_date="2026-08-11",
            timezone="UTC",
        )
        current_start, current_end = current_day.period_utc(
            now_utc=datetime(2026, 8, 11, 7, 10, 33, tzinfo=UTC)
        )
        assert current_start.isoformat() == "2026-01-02T00:00:00+00:00"
        assert current_end.isoformat() == "2026-08-11T07:10:33+00:00"

        runtime = controller.attach_workspace_runtime(persisted)
        controller.begin_workspace_runtime_start(workspace.workspace_uid)
        assert runtime.context.runtime_state == "STARTING"
        active_edit_blocked = False
        try:
            controller.update_workspace_history_download_settings(
                workspace.workspace_uid,
                custom,
            )
        except WorkspaceRuntimeError:
            active_edit_blocked = True
        assert active_edit_blocked

        invalid_values_blocked = 0
        invalid_payloads = (
            {"broker": "UNKNOWN"},
            {"symbol": ""},
            {"timeframe": "UNKNOWN"},
            {"start_date": "2026-07-27", "end_date": None},
            {"start_date": "2026-07-28", "end_date": "2026-07-27"},
            {"timezone": "Unknown/Timezone"},
        )
        for payload in invalid_payloads:
            values = {
                "broker": "IB",
                "account_id": "DUM513747",
                "symbol": "EURUSD",
                "timeframe": "M15",
                "start_date": "2026-01-01",
                "end_date": "2026-07-27",
                "timezone": "UTC",
            }
            values.update(payload)
            try:
                WorkspaceHistoryDownloadSettings(**values)
            except WorkspaceHistoryDownloadSettingsError:
                invalid_values_blocked += 1
        assert invalid_values_blocked == len(invalid_payloads)

        print("Algorithm Workspace History Download Settings result")
        print(f"  workspace_uid={workspace.workspace_uid}")
        print(f"  start_date={custom.start_date}")
        print(f"  end_date={custom.end_date}")
        print(f"  timezone={custom.timezone}")
        print(f"  destination_folder={custom.destination_folder}")
        print("  legacy_replay_download_migrated=True")
        print("  separate_persistence=True")
        print("  utc_boundaries=True")
        print("  international_timezone=True")
        print("  current_or_future_end_clamped_to_now=True")
        print("  history_root_uses_app_base=True")
        print(f"  active_edit_blocked={active_edit_blocked}")
        print(f"  invalid_values_blocked={invalid_values_blocked}")
        print("ALGORITHM_WORKSPACE_HISTORY_DOWNLOAD_SETTINGS_CHECK=OK")


if __name__ == "__main__":
    main()
