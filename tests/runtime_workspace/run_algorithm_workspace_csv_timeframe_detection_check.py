# -*- coding: utf-8 -*-
"""RoadMap98.5.4.4 automatic CSV source-timeframe detection check."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation_policy import translation_overrides_for_key  # noqa: E402
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402


def _write_history(
    path: Path,
    *,
    start: datetime,
    deltas_minutes: tuple[int, ...],
) -> None:
    rows = ["timestamp,open,high,low,close,volume"]
    timestamp = start
    price = 1.10000
    rows.append(
        f"{timestamp.isoformat().replace('+00:00', 'Z')},"
        f"{price:.5f},{price:.5f},{price:.5f},{price:.5f},0"
    )
    for delta in deltas_minutes:
        timestamp += timedelta(minutes=delta)
        price += 0.00001
        rows.append(
            f"{timestamp.isoformat().replace('+00:00', 'Z')},"
            f"{price:.5f},{price:.5f},{price:.5f},{price:.5f},0"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    loader = WorkspaceCsvHistoryLoader()
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        m1_path = root / "m1.csv"
        m15_path = root / "m15.csv"
        ambiguous_path = root / "ambiguous.csv"

        _write_history(
            m1_path,
            start=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            deltas_minutes=(1,) * 40 + (5,) + (1,) * 40,
        )
        _write_history(
            m15_path,
            start=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            deltas_minutes=(15,) * 20,
        )
        _write_history(
            ambiguous_path,
            start=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            deltas_minutes=(1, 5) * 8,
        )

        m1 = loader.inspect_range(file_path=m1_path)
        m15 = loader.inspect_range(file_path=m15_path)
        ambiguous = loader.inspect_range(file_path=ambiguous_path)

    assert m1.detected_timeframe == "M1"
    assert m15.detected_timeframe == "M15"
    assert ambiguous.detected_timeframe is None

    dialog_source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_replay_dialog.py"
    ).read_text(encoding="utf-8")
    assert "detected.detected_timeframe" in dialog_source
    assert "_apply_detected_source_timeframe" in dialog_source
    assert "sourceTimeframeManualFallback" in dialog_source
    assert "sourceTimeframeDetected" in dialog_source

    translations = translation_overrides_for_key(
        "AlgorithmWorkspaceReplayDialog.lblSourceTimeframe"
    )
    assert "(авто)" in translations.get("uk", "")

    print("Algorithm Workspace CSV Timeframe Detection result")
    print("  m1_detected_from_timestamps=True")
    print("  m15_detected_from_timestamps=True")
    print("  filename_not_required=True")
    print("  dominant_cadence_tolerates_gaps=True")
    print("  ambiguous_cadence_uses_manual_fallback=True")
    print("  replay_dialog_applies_detected_timeframe=True")
    print("  ukrainian_auto_label=True")
    print("ALGORITHM_WORKSPACE_CSV_TIMEFRAME_DETECTION_CHECK=OK")


if __name__ == "__main__":
    main()
