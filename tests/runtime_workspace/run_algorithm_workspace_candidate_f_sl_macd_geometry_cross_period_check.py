# -*- coding: utf-8 -*-
"""RoadMap103 / 7G: cross-period MACD geometry anatomy для production SL.

Diagnostic-only runner повторює production Candidate F після 6K для frozen
2025 та трьох відомих вікон 2026. Для кожної фактично відкритої угоди він
читає лише MACD Quality evidence, яке вже було сформоване на завершеному M15
signal bar: prominence, extremum-to-cross distance, ABC effective angle,
crossover steepness та search window.

Мета — перевірити, чи STOP_LOSS мають стабільно слабшу MACD geometry, ніж
інші losses і winners, не вводячи нового gate, не змінюючи SL/TP, Candidate F
profile або 6K exit recovery. Future price не використовується як feature;
PnL потрібен тільки для post-trade групування результатів.
"""

from __future__ import annotations

import math
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    new_workspace_indicator_profile_bindings,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

HISTORY_2026 = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)

WINDOWS_2026 = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T00:00:00+00:00",
    ),
    (
        "VALIDATION",
        "2026-03-01T00:00:00+00:00",
        "2026-05-31T23:59:00+00:00",
    ),
    (
        "HOLDOUT",
        "2026-06-01T00:00:00+00:00",
        "2026-08-11T08:24:00+00:00",
    ),
)

EXPECTED_BASELINES = {
    "2025": (59, 40, 18, 1, 9, -4.05, 0.7808, 5.80),
    "DEVELOPMENT": (7, 6, 1, 0, 0, 1.11, 10.2500, 0.12),
    "VALIDATION": (16, 12, 4, 0, 2, -0.78, 0.8579, 3.69),
    "HOLDOUT": (7, 6, 1, 0, 0, 0.46, 7.5714, 0.07),
}

PROMINENCE_THRESHOLD = 0.000015
DISTANCE_THRESHOLD = 0.000050
ABC_ANGLE_THRESHOLD = 2.25

OUTCOME_STOP_LOSS = "STOP_LOSS"
OUTCOME_OTHER_LOSS = "OTHER_LOSS"
OUTCOME_WIN = "WIN"
OUTCOME_BREAK_EVEN = "BREAK_EVEN"
OUTCOMES = (
    OUTCOME_STOP_LOSS,
    OUTCOME_OTHER_LOSS,
    OUTCOME_WIN,
    OUTCOME_BREAK_EVEN,
)
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class MacdGeometryEvidence:
    """Causal MACD Quality geometry однієї фактично відкритої угоди."""

    window: str
    signal_timestamp: datetime
    direction: str
    outcome: str
    final_profit: float
    prominence: float
    prominence_multiple: float
    distance: float
    distance_multiple: float
    effective_angle: float
    angle_multiple: float
    crossover_steepness: float
    search_window: int
    minimum_quality_multiple: float


class FullSignalHistoryRuntime(WorkspaceRuntime):
    """Production Runtime з public immutable full signal history для тесту."""

    @property
    def historical_signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути повну історію signal records deterministic Replay."""
        return tuple(self._historical_signal_records)


def _candidate_bindings() -> dict[str, dict[str, object]]:
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def _workspace_2026(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM103 7G SL MACD Geometry Cross-Period",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            "spread_limit": 0.00020,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": PROMINENCE_THRESHOLD,
            "macd_extremum_to_cross_min_distance": DISTANCE_THRESHOLD,
            "macd_cross_min_angle": 45.0,
            "macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "macd_cross_min_abc_angle": ABC_ANGLE_THRESHOLD,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(HISTORY_2026),
            "start_utc": start_utc,
            "end_utc": end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "2026-01-02_2026-08-11_IB_EURUSD_M1",
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=_candidate_bindings(),
    )


def _outcome(close_reason: str, final_profit: float) -> str:
    if close_reason == "STOP_LOSS":
        return OUTCOME_STOP_LOSS
    if final_profit > EPSILON:
        return OUTCOME_WIN
    if final_profit < -EPSILON:
        return OUTCOME_OTHER_LOSS
    return OUTCOME_BREAK_EVEN


def _reason_float(reason: str, key: str) -> float:
    match = re.search(rf"(?:^|; ){re.escape(key)}=([+-]?\d+(?:\.\d+)?)", reason)
    assert match is not None, (key, reason)
    return float(match.group(1))


def _reason_int(reason: str, key: str) -> int:
    match = re.search(rf"(?:^|; ){re.escape(key)}=(\d+)", reason)
    assert match is not None, (key, reason)
    return int(match.group(1))


def _macd_source_record(
    trade_record: WorkspaceSignalRecord,
    records_by_timestamp: dict[datetime, tuple[WorkspaceSignalRecord, ...]],
) -> WorkspaceSignalRecord:
    """Resolve original MACD record for direct or Candidate F deferred release."""
    if "extremum_prominence=" in trade_record.reason:
        return trade_record

    match = re.search(
        r"original_signal_timestamp=([^;]+)",
        trade_record.reason,
    )
    assert match is not None, trade_record.reason
    original_timestamp = datetime.fromisoformat(match.group(1))
    candidates = records_by_timestamp.get(original_timestamp, ())
    source_records = tuple(
        record
        for record in candidates
        if "extremum_prominence=" in record.reason
        and record.direction == trade_record.direction
    )
    assert len(source_records) == 1, (
        original_timestamp,
        trade_record.direction,
        source_records,
    )
    return source_records[0]


def _evidence(
    window: str,
    trade,
    record: WorkspaceSignalRecord,
) -> MacdGeometryEvidence:
    reason = record.reason
    prominence = _reason_float(reason, "extremum_prominence")
    distance = _reason_float(reason, "extremum_to_cross_distance")
    effective_angle = _reason_float(reason, "effective_angle")
    crossover_steepness = _reason_float(reason, "crossover_steepness")
    search_window = _reason_int(reason, "search_window")

    prominence_multiple = prominence / PROMINENCE_THRESHOLD
    distance_multiple = distance / DISTANCE_THRESHOLD
    angle_multiple = effective_angle / ABC_ANGLE_THRESHOLD
    minimum_quality_multiple = min(
        prominence_multiple,
        distance_multiple,
        angle_multiple,
    )

    assert prominence_multiple >= 1.0 - 1e-6
    assert distance_multiple >= 1.0 - 1e-6
    assert angle_multiple >= 1.0 - 0.01
    assert search_window in (3, 5, 7)

    return MacdGeometryEvidence(
        window=window,
        signal_timestamp=trade.signal_timestamp,
        direction=trade.direction,
        outcome=_outcome(trade.close_reason, trade.final_profit),
        final_profit=trade.final_profit,
        prominence=prominence,
        prominence_multiple=prominence_multiple,
        distance=distance,
        distance_multiple=distance_multiple,
        effective_angle=effective_angle,
        angle_multiple=angle_multiple,
        crossover_steepness=crossover_steepness,
        search_window=search_window,
        minimum_quality_multiple=minimum_quality_multiple,
    )


def _run(
    window: str,
    workspace: AlgorithmWorkspace,
) -> tuple[MacdGeometryEvidence, ...]:
    runtime = FullSignalHistoryRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    expected = EXPECTED_BASELINES[window]
    assert summary.opened_trades == expected[0]
    assert summary.winning_trades == expected[1]
    assert summary.losing_trades == expected[2]
    assert summary.break_even_trades == expected[3]
    assert summary.close_reason_count("STOP_LOSS") == expected[4]
    assert math.isclose(summary.net_profit, expected[5], abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, expected[6], abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, expected[7], abs_tol=0.005)

    signal_history = runtime.historical_signal_records
    records = {record.signal_uid: record for record in signal_history}
    records_by_timestamp: dict[datetime, list[WorkspaceSignalRecord]] = {}
    for record in signal_history:
        records_by_timestamp.setdefault(record.timestamp, []).append(record)
    immutable_by_timestamp = {
        timestamp: tuple(items)
        for timestamp, items in records_by_timestamp.items()
    }

    evidence: list[MacdGeometryEvidence] = []
    for trade in execution.trade_diagnostics():
        trade_record = records.get(trade.signal_uid)
        assert trade_record is not None, trade.signal_uid
        macd_record = _macd_source_record(trade_record, immutable_by_timestamp)
        evidence.append(_evidence(window, trade, macd_record))

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    return tuple(evidence)


def _median(items: tuple[MacdGeometryEvidence, ...], attribute: str) -> float:
    values = tuple(float(getattr(item, attribute)) for item in items)
    assert values
    return float(statistics.median(values))


def _group_line(name: str, items: tuple[MacdGeometryEvidence, ...]) -> str:
    search_windows = Counter(item.search_window for item in items)
    return (
        f"    {name}=n:{len(items)},"
        f"prom:{_median(items, 'prominence'):.8f}/"
        f"{_median(items, 'prominence_multiple'):.2f}x,"
        f"distance:{_median(items, 'distance'):.8f}/"
        f"{_median(items, 'distance_multiple'):.2f}x,"
        f"angle:{_median(items, 'effective_angle'):.2f}/"
        f"{_median(items, 'angle_multiple'):.2f}x,"
        f"steep:{_median(items, 'crossover_steepness'):.8f},"
        f"min_quality:{_median(items, 'minimum_quality_multiple'):.2f}x,"
        f"search:3={search_windows[3]},5={search_windows[5]},7={search_windows[7]}"
    )


def _rule_matrix(
    evidence: tuple[MacdGeometryEvidence, ...],
) -> tuple[str, ...]:
    rules = (
        (
            "minimum_quality<=1.10x",
            lambda item: item.minimum_quality_multiple <= 1.10,
        ),
        (
            "minimum_quality<=1.25x",
            lambda item: item.minimum_quality_multiple <= 1.25,
        ),
        (
            "prominence<=1.25x",
            lambda item: item.prominence_multiple <= 1.25,
        ),
        (
            "distance<=1.25x",
            lambda item: item.distance_multiple <= 1.25,
        ),
        (
            "angle<=1.25x",
            lambda item: item.angle_multiple <= 1.25,
        ),
        (
            "search_window=7",
            lambda item: item.search_window == 7,
        ),
    )
    rows: list[str] = []
    for name, predicate in rules:
        matched = tuple(item for item in evidence if predicate(item))
        counts = Counter(item.outcome for item in matched)
        by_window = Counter(item.window for item in matched)
        pnl = sum(item.final_profit for item in matched)
        rows.append(
            "    "
            f"{name}: SL:{counts[OUTCOME_STOP_LOSS]},"
            f"OTHER_LOSS:{counts[OUTCOME_OTHER_LOSS]},"
            f"WIN:{counts[OUTCOME_WIN]},BE:{counts[OUTCOME_BREAK_EVEN]},"
            f"pnl:{pnl:+.2f},"
            f"windows:2025={by_window['2025']},DEV={by_window['DEVELOPMENT']},"
            f"VAL={by_window['VALIDATION']},HOLD={by_window['HOLDOUT']}"
        )
    return tuple(rows)


def main() -> None:
    """Запустити cross-period causal MACD geometry diagnostic."""
    assert_frozen_oos_snapshot()
    assert HISTORY_2026.is_file(), HISTORY_2026

    all_evidence: list[MacdGeometryEvidence] = []
    all_evidence.extend(_run("2025", frozen_oos_workspace()))
    for window, start_utc, end_utc in WINDOWS_2026:
        all_evidence.extend(_run(window, _workspace_2026(start_utc, end_utc)))
    evidence = tuple(all_evidence)

    groups = {
        outcome: tuple(item for item in evidence if item.outcome == outcome)
        for outcome in OUTCOMES
    }
    assert len(evidence) == 89
    assert len(groups[OUTCOME_STOP_LOSS]) == 11
    assert len(groups[OUTCOME_OTHER_LOSS]) == 13
    assert len(groups[OUTCOME_WIN]) == 64
    assert len(groups[OUTCOME_BREAK_EVEN]) == 1

    stop_windows = Counter(item.window for item in groups[OUTCOME_STOP_LOSS])
    assert stop_windows == Counter({"2025": 9, "VALIDATION": 2})

    print("Algorithm Workspace Candidate F SL MACD Geometry Cross-Period result")
    print("  mode=PRODUCTION_6K_CAUSAL_MACD_GEOMETRY_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  signal_filter_applied=False")
    print("  alternative_stop_applied=False")
    print("  exit_recovery_policy=PRODUCTION_6K_PRESERVED")
    print("  future_price_used_as_feature=False")
    print("  periods=2025_frozen_plus_2026_development_validation_holdout")
    print("  2026_is_not_blind_oos=True")
    print(
        "  fixed_quality_thresholds="
        f"prominence:{PROMINENCE_THRESHOLD:.6f},"
        f"distance:{DISTANCE_THRESHOLD:.6f},ABC:{ABC_ANGLE_THRESHOLD:.2f}"
    )
    print(
        "  groups="
        f"stop_loss:{len(groups[OUTCOME_STOP_LOSS])},"
        f"other_loss:{len(groups[OUTCOME_OTHER_LOSS])},"
        f"win:{len(groups[OUTCOME_WIN])},"
        f"break_even:{len(groups[OUTCOME_BREAK_EVEN])}"
    )
    print("  group_medians_and_search_windows:")
    for outcome in OUTCOMES:
        items = groups[outcome]
        if items:
            print(_group_line(outcome, items))
    print("  fixed_diagnostic_rule_matrix:")
    for row in _rule_matrix(evidence):
        print(row)
    print("  chronological_stop_loss_macd_geometry:")
    for index, item in enumerate(groups[OUTCOME_STOP_LOSS], start=1):
        print(
            "    "
            f"{index:02d}. {item.window} {item.signal_timestamp.isoformat()} "
            f"{item.direction} pnl:{item.final_profit:+.2f} "
            f"prom:{item.prominence:.8f}/{item.prominence_multiple:.2f}x "
            f"distance:{item.distance:.8f}/{item.distance_multiple:.2f}x "
            f"angle:{item.effective_angle:.2f}/{item.angle_multiple:.2f}x "
            f"steep:{item.crossover_steepness:.8f} "
            f"minQ:{item.minimum_quality_multiple:.2f}x "
            f"search:{item.search_window}"
        )
    print("  completed_bars_only=True")
    print("  causal_signal_macd_quality_evidence_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_MACD_GEOMETRY_CROSS_PERIOD_CHECK=OK")


if __name__ == "__main__":
    main()
