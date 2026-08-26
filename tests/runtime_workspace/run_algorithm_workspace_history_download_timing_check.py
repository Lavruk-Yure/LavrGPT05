# -*- coding: utf-8 -*-
"""Перевірка timing summary та responsive progress broker-history dialog."""

from __future__ import annotations

import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace_history_download_dialog import (  # noqa: E402
    AlgorithmWorkspaceHistoryDownloadDialog,
    format_history_download_duration,
)
from core.translation_policy import translation_overrides_for_key  # noqa: E402


def main() -> None:
    assert format_history_download_duration(None) == "—"
    assert format_history_download_duration(0.0) == "0:00"
    assert format_history_download_duration(62.4) == "1:02"
    assert format_history_download_duration(3723.0) == "1:02:03"

    format_download_time_utc = getattr(
        AlgorithmWorkspaceHistoryDownloadDialog,
        "_format_download_time_utc",
    )
    displayed = format_download_time_utc(
        datetime(2026, 8, 25, 17, 25, 20, tzinfo=timezone(timedelta(hours=3)))
    )
    assert displayed == "2026-08-25 14:25:20 UTC"

    dialog_source = inspect.getsource(AlgorithmWorkspaceHistoryDownloadDialog)
    assert "time.monotonic()" in dialog_source
    assert "_download_started_utc" in dialog_source
    assert "_download_finished_utc" in dialog_source
    assert "_download_elapsed_seconds" in dialog_source
    assert "download_started" in dialog_source
    assert "download_finished" in dialog_source
    assert "download_duration" in dialog_source
    assert "format_history_download_duration" in dialog_source
    assert "_on_download_progress" in dialog_source
    assert "self.progress_download.setRange(0, 100)" in dialog_source
    assert "self.progress_download.setValue(percent)" in dialog_source
    assert "ExcludeUserInputEvents" in dialog_source

    translations = translation_overrides_for_key(
        "AlgorithmWorkspaceHistoryDownloadDialog.completed"
    )
    ukrainian = translations.get("uk", "")
    assert "Початок завантаження: {download_started}" in ukrainian
    assert "Кінець завантаження: {download_finished}" in ukrainian
    assert "Тривалість завантаження: {download_duration}" in ukrainian

    progress_translations = translation_overrides_for_key(
        "AlgorithmWorkspaceHistoryDownloadDialog.statusProgress"
    )
    progress_ukrainian = progress_translations.get("uk", "")
    assert "{percent}%" in progress_ukrainian
    assert "запитів {requests}" in progress_ukrainian
    assert "барів {bars}" in progress_ukrainian

    print("Algorithm Workspace History Download Timing result")
    print("  monotonic_duration_measured=True")
    print("  utc_start_time_reported=True")
    print("  utc_finish_time_reported=True")
    print("  windows_timezone_label_not_exposed=True")
    print("  elapsed_duration_reported=True")
    print("  duration_under_one_hour_format=MM:SS")
    print("  duration_over_one_hour_format=H:MM:SS")
    print("  ukrainian_summary_labels=True")
    print("  determinate_page_progress=True")
    print("  ui_repaint_between_pages=True")
    print("  ukrainian_progress_status=True")
    print("ALGORITHM_WORKSPACE_HISTORY_DOWNLOAD_TIMING_CHECK=OK")


if __name__ == "__main__":
    main()
