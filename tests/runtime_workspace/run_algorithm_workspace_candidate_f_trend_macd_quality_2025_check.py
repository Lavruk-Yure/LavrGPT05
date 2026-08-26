# -*- coding: utf-8 -*-
"""RoadMap102: причини MACD Quality reject у сильних OOS-трендах 2025.

Runner продовжує frozen Trend Coverage Diagnostic без зміни detector або
торгових порогів. Він бере лише ті price-only strong M15 segments, які вже
класифіковані як ``MACD_QUALITY_REJECT``, і розкладає всі aligned MACD crosses
за первинною reason-code та за незалежними criterion flags quality diagnostic.

Це research diagnostic: він не змінює MACD/Alligator/Candidate F, не виконує
counterfactual trades і не має performance assertions. Мета — встановити,
який саме quality criterion відсікає сильні price trends до Alligator gate.
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen  # noqa: E402

trend = importlib.import_module(
    "run_algorithm_workspace_candidate_f_trend_coverage_2025_check"
)
from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_macd_crossover_quality import (  # noqa: E402
    MACD_QUALITY_REASON_CROSS_TOO_FLAT,
    MACD_QUALITY_REASON_DISTANCE_TOO_SMALL,
    MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND,
    MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

QUALITY_REJECT_CODES = (
    MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND,
    MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
    MACD_QUALITY_REASON_DISTANCE_TOO_SMALL,
    MACD_QUALITY_REASON_CROSS_TOO_FLAT,
)

_DIAGNOSTIC_VALUE = re.compile(r"(?:^|; )([a-z_]+)=([^;]+)")


@dataclass(frozen=True, slots=True)
class QualityRejectDetail:
    """Структурований evidence одного rejected MACD cross."""

    timestamp: datetime
    direction: str
    reason_code: str
    extremum_found: bool | None
    prominence_pass: bool | None
    distance_pass: bool | None
    angle_pass: bool | None
    prominence: float | None
    distance: float | None
    angle: float | None


def _diagnostic_values(reason: str) -> dict[str, str]:
    """Розібрати canonical ``key=value`` evidence з MACD reason text."""
    return {
        match.group(1): match.group(2).strip()
        for match in _DIAGNOSTIC_VALUE.finditer(reason)
    }


def _optional_bool(values: dict[str, str], key: str) -> bool | None:
    value = values.get(key)
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def _optional_float(values: dict[str, str], key: str) -> float | None:
    value = values.get(key)
    if value is None or value.upper() == "NONE":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def quality_reject_detail(record: WorkspaceSignalRecord) -> QualityRejectDetail:
    """Побудувати typed quality evidence з immutable signal record."""
    values = _diagnostic_values(record.reason)
    return QualityRejectDetail(
        timestamp=record.timestamp,
        direction=record.direction,
        reason_code=str(record.source_reason_code or "").strip().upper(),
        extremum_found=_optional_bool(values, "criterion_extremum_pass"),
        prominence_pass=_optional_bool(values, "criterion_prominence_pass"),
        distance_pass=_optional_bool(values, "criterion_distance_pass"),
        angle_pass=_optional_bool(values, "criterion_angle_pass"),
        prominence=_optional_float(values, "extremum_prominence"),
        distance=_optional_float(values, "extremum_to_cross_distance"),
        angle=_optional_float(values, "effective_angle"),
    )


def _count_reason(details: tuple[QualityRejectDetail, ...], code: str) -> int:
    return sum(item.reason_code == code for item in details)


def _criterion_fail_count(
    details: tuple[QualityRejectDetail, ...],
    attribute: str,
) -> int:
    return sum(getattr(item, attribute) is False for item in details)


def failed_criteria(item: QualityRejectDetail) -> tuple[str, ...]:
    pairs = (
        ("extremum", item.extremum_found),
        ("prominence", item.prominence_pass),
        ("distance", item.distance_pass),
        ("angle", item.angle_pass),
    )
    return tuple(name for name, value in pairs if value is False)


def _fmt_number(value: float | None, digits: int) -> str:
    return "NONE" if value is None else f"{value:.{digits}f}"


def main() -> None:
    frozen.assert_frozen_oos_snapshot()

    runtime = frozen.FrozenOosRuntime(
        frozen.frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    events = session.events
    assert events

    candidates = trend.price_only_trend_candidates(events)
    strong_windows = trend.strongest_non_overlapping(candidates)

    while not session.completed:
        runtime.advance_replay()

    execution = runtime.replay_execution
    assert execution is not None
    records = runtime.historical_signal_records_for_test()
    trades = execution.trade_diagnostics()
    coverage = tuple(
        trend.coverage_for_window(window, events, records, trades)
        for window in strong_windows
    )
    quality_segments = tuple(
        item
        for item in coverage
        if item.coverage == trend.COVERAGE_MACD_QUALITY_REJECT
    )
    assert len(quality_segments) == 12

    all_details: list[QualityRejectDetail] = []
    segment_rows: list[tuple[str, tuple[str, ...]]] = []
    for item in quality_segments:
        start = events[item.window.start_index].timestamp
        end = events[item.window.end_index].timestamp
        aligned = tuple(
            record
            for record in records
            if start <= record.timestamp <= end
            and record.direction == item.window.direction
        )
        details = tuple(quality_reject_detail(record) for record in aligned)
        assert details
        assert all(detail.reason_code in QUALITY_REJECT_CODES for detail in details)
        all_details.extend(details)
        reason_summary = ",".join(
            f"{code}:{_count_reason(details, code)}"
            for code in QUALITY_REJECT_CODES
            if _count_reason(details, code)
        )
        header = (
            f"{start.isoformat()} -> {end.isoformat()} {item.window.direction} "
            f"move:{item.window.normalized_move:.2f}TR "
            f"eff:{item.window.path_efficiency:.3f} "
            f"crosses:{len(details)} reasons:{reason_summary}"
        )
        cross_rows: list[str] = []
        for detail in details:
            failed = ",".join(failed_criteria(detail)) or "NONE"
            cross_rows.append(
                "cross="
                f"{detail.timestamp.isoformat()} reason:{detail.reason_code} "
                f"failed:{failed} "
                f"prom:{_fmt_number(detail.prominence, 8)} "
                f"dist:{_fmt_number(detail.distance, 8)} "
                f"angle:{_fmt_number(detail.angle, 2)}"
            )
        segment_rows.append((header, tuple(cross_rows)))

    details_tuple = tuple(all_details)
    primary_counts = {
        code: _count_reason(details_tuple, code)
        for code in QUALITY_REJECT_CODES
    }
    criterion_counts = {
        "extremum": _criterion_fail_count(details_tuple, "extremum_found"),
        "prominence": _criterion_fail_count(details_tuple, "prominence_pass"),
        "distance": _criterion_fail_count(details_tuple, "distance_pass"),
        "angle": _criterion_fail_count(details_tuple, "angle_pass"),
    }
    single_fail = sum(len(failed_criteria(item)) == 1 for item in details_tuple)
    multi_fail = sum(len(failed_criteria(item)) > 1 for item in details_tuple)
    parse_complete = all(
        None not in (
            item.extremum_found,
            item.prominence_pass,
            item.distance_pass,
            item.angle_pass,
        )
        for item in details_tuple
    )
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert parse_complete
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Trend MACD Quality 2025 result")
    print("  source_detector=PRICE_ONLY_M15_STRONG_WINDOW_V1")
    print(f"  quality_reject_segments={len(quality_segments)}")
    print(f"  aligned_rejected_macd_crosses={len(details_tuple)}")
    print(
        "  primary_reason_counts="
        f"not_found:{primary_counts[MACD_QUALITY_REASON_EXTREMUM_NOT_FOUND]},"
        f"weak:{primary_counts[MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK]},"
        f"distance:{primary_counts[MACD_QUALITY_REASON_DISTANCE_TOO_SMALL]},"
        f"angle:{primary_counts[MACD_QUALITY_REASON_CROSS_TOO_FLAT]}"
    )
    print(
        "  independent_criterion_failures="
        f"extremum:{criterion_counts['extremum']},"
        f"prominence:{criterion_counts['prominence']},"
        f"distance:{criterion_counts['distance']},"
        f"angle:{criterion_counts['angle']}"
    )
    print(f"  single_criterion_failures={single_fail}")
    print(f"  multiple_criterion_failures={multi_fail}")
    print(f"  diagnostic_parse_complete={parse_complete}")
    print("  chronological_quality_reject_segments:")
    for index, (header, cross_rows) in enumerate(segment_rows, start=1):
        print(f"    {index:02d}. {header}")
        for row in cross_rows:
            print(f"        {row}")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  research_diagnostic_only=True")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TREND_MACD_QUALITY_2025_CHECK=OK")


if __name__ == "__main__":
    main()
