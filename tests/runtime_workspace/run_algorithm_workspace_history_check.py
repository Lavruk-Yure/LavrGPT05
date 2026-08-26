# -*- coding: utf-8 -*-
"""tests.runtime_workspace.run_algorithm_workspace_history_check

Runtime check for validated CSV history and deterministic WSP Replay.
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
    WORKSPACE_STATE_RUNNING,
    AlgorithmWorkspace,
)
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_replay import (  # noqa: E402
    WorkspaceReplayError,
    WorkspaceReplayService,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_REPLAY_SOURCE_CSV,
)


def _write_csv(path: Path, rows: list[str], header: str | None = None) -> None:
    csv_header = header or "time,open,high,low,close,volume"
    path.write_text(
        csv_header + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def _history_rows() -> list[str]:
    return [
        "2026-07-20 08:00:00,1.1400,1.1410,1.1390,1.1405,100",
        "2026-07-20 08:15:00,1.1405,1.1415,1.1400,1.1410,110",
        "2026-07-20 08:30:00,1.1410,1.1420,1.1405,1.1415,120",
        "2026-07-20 09:00:00,1.1415,1.1425,1.1410,1.1420,130",
        "2026-07-20 09:15:00,1.1420,1.1430,1.1415,1.1425,140",
        "2026-07-20 09:30:00,1.1425,1.1435,1.1420,1.1430,150",
        "2026-07-20 09:45:00,1.1430,1.1440,1.1425,1.1435,160",
        "2026-07-20 10:00:00,1.1435,1.1445,1.1430,1.1440,170",
    ]


def _history_settings(path: Path) -> dict[str, object]:
    return {
        "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
        "source": "HISTORICAL_TEST",
        "file_path": str(path),
        "source_timezone": "UTC",
        "start_utc": "2026-07-20T08:15:00Z",
        "end_utc": "2026-07-20T09:30:00Z",
        "spread": 0.00014,
        "speed": 2,
    }


def _expect_replay_error(
    service: WorkspaceReplayService,
    path: Path,
    *,
    settings: dict[str, object] | None = None,
) -> bool:
    replay_settings = dict(settings or _history_settings(path))
    replay_settings["file_path"] = str(path)
    try:
        service.create_session(
            broker="IB",
            symbol="EURUSD",
            timeframe="M15",
            replay_settings=replay_settings,
        )
    except WorkspaceReplayError:
        return True
    return False


def main() -> None:
    service = WorkspaceReplayService()
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        history_path = directory / "eurusd_m15.csv"
        _write_csv(history_path, _history_rows())
        settings = _history_settings(history_path)

        detected_range = WorkspaceCsvHistoryLoader().inspect_range(
            file_path=history_path,
            source_timezone="UTC",
            delimiter="AUTO",
        )
        assert detected_range.row_count == 8
        assert detected_range.first_timestamp.isoformat() == (
            "2026-07-20T08:00:00+00:00"
        )
        assert detected_range.last_timestamp.isoformat() == (
            "2026-07-20T10:00:00+00:00"
        )

        first = service.create_session(
            broker="IB",
            symbol="EURUSD",
            timeframe="M15",
            replay_settings=settings,
        )
        second = service.create_session(
            broker="IB",
            symbol="EURUSD",
            timeframe="M15",
            replay_settings=settings,
        )
        assert first.events == second.events
        assert first.source_name == "HISTORICAL_TEST"
        assert first.speed == 2
        report = first.history_report
        assert report is not None
        assert report.input_rows == 8
        assert report.accepted_rows == 5
        assert report.filtered_rows == 3
        assert report.derived_quotes == 5
        assert report.gap_count == 1
        assert abs(first.events[0].spread - 0.00014) < 1e-12

        localized_path = directory / "localized_history.csv"
        _write_csv(
            localized_path,
            [
                "20.07.2026 08:00:00;1,1400;1,1410;1,1390;1,1405;100;0,00016",
                "20.07.2026 08:15:00;1,1405;1,1415;1,1400;1,1410;110;0,00016",
            ],
            header="time;open;high;low;close;volume;spread",
        )
        localized = service.create_session(
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
            replay_settings={
                "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
                "source": "LOCALIZED_CSV_TEST",
                "file_path": str(localized_path),
                "source_timezone": "UTC",
                "delimiter": "AUTO",
                "decimal_separator": ",",
                "speed": 1,
            },
        )
        assert len(localized.events) == 2
        assert localized.history_report is not None
        assert localized.history_report.derived_quotes == 2
        assert abs(localized.events[0].spread - 0.00016) < 1e-12

        workspace = AlgorithmWorkspace.create(
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
            replay_settings=settings,
        )
        runtime = WorkspaceRuntime(workspace)
        runtime.begin_start()
        runtime.complete_start()
        for _unused in range(len(first.events)):
            runtime.advance_replay()
            if runtime.context.runtime_state == WORKSPACE_STATE_RUNNING:
                break
        assert runtime.context.runtime_state == WORKSPACE_STATE_RUNNING
        journal_events = [entry.event for entry in runtime.journal]
        assert "CSV_HISTORY_LOADED" in journal_events
        runtime.stop()

        duplicate_path = directory / "duplicate.csv"
        duplicate_rows = _history_rows()[:2]
        duplicate_rows.append(duplicate_rows[-1])
        _write_csv(duplicate_path, duplicate_rows)
        duplicate_blocked = _expect_replay_error(service, duplicate_path)
        assert duplicate_blocked

        invalid_ohlc_path = directory / "invalid_ohlc.csv"
        _write_csv(
            invalid_ohlc_path,
            ["2026-07-20 08:00:00,1.1400,1.1390,1.1380,1.1405,100"],
        )
        invalid_ohlc_blocked = _expect_replay_error(
            service,
            invalid_ohlc_path,
            settings={
                "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
                "file_path": str(invalid_ohlc_path),
                "spread": 0.00014,
            },
        )
        assert invalid_ohlc_blocked

        missing_column_path = directory / "missing_column.csv"
        _write_csv(
            missing_column_path,
            ["2026-07-20 08:00:00,1.1400,1.1390,1.1405,100"],
            header="time,open,low,close,volume",
        )
        missing_column_blocked = _expect_replay_error(
            service,
            missing_column_path,
            settings={
                "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
                "file_path": str(missing_column_path),
                "spread": 0.00014,
            },
        )
        assert missing_column_blocked

        unsupported_source_blocked = False
        try:
            service.create_session(
                broker="IB",
                symbol="EURUSD",
                timeframe="M15",
                replay_settings={"source_type": "UNKNOWN"},
            )
        except WorkspaceReplayError:
            unsupported_source_blocked = True
        assert unsupported_source_blocked

        print("Algorithm Workspace Historical Replay result")
        print(f"  source={first.source_name}")
        print(f"  input_rows={report.input_rows}")
        print(f"  accepted_rows={report.accepted_rows}")
        print(f"  filtered_rows={report.filtered_rows}")
        print(f"  derived_quotes={report.derived_quotes}")
        print(f"  gap_count={report.gap_count}")
        print(f"  first_timestamp={report.first_timestamp.isoformat()}")
        print(f"  last_timestamp={report.last_timestamp.isoformat()}")
        print("  range_detected=True")
        print("  deterministic=True")
        print("  localized_csv_supported=True")
        print("  runtime_history_logged=True")
        print(f"  duplicate_blocked={duplicate_blocked}")
        print(f"  invalid_ohlc_blocked={invalid_ohlc_blocked}")
        print(f"  missing_column_blocked={missing_column_blocked}")
        print(f"  unsupported_source_blocked={unsupported_source_blocked}")
        print("ALGORITHM_WORKSPACE_HISTORY_CHECK=OK")


if __name__ == "__main__":
    main()
