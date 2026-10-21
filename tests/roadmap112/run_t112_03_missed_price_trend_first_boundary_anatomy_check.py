# -*- coding: utf-8 -*-
"""T112-03 — first observed entry boundary on missed price trends, TEST_ONLY.

Використовується незмінений production Replay та ex-post price-only labels.
Ні початок, ні кінець трендового вікна не передаються до алгоритму.

Перший запис сигналу — перша СПОСТЕРЕЖЕНА межа, а не обов'язково
первинна внутрішня причина. Відсутність proposal не доводить причину.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_signal import WorkspaceSignalRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "T112-03"
MODE = "RM112_T112_03_MISSED_PRICE_TREND_FIRST_BOUNDARY_ANATOMY_TEST_ONLY"
BAR_INTERVAL = timedelta(minutes=15)
EXPECTED_WINDOWS = {"2025": 17, "2026": 13}
EXPECTED_COVERED = {"2025": 3, "2026": 0}
EXPECTED_MISSED_TOTAL = 27
BASELINE_TOLERANCE = 0.005


def _bootstrap() -> None:
    """Дозволити запуск із tests/roadmap112 через абсолютний шлях."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _protected_hashes() -> dict[str, str]:
    """Контроль того, що TEST_ONLY не змінив production та MD7."""
    roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "engine")
    paths = sorted(path for root in roots for path in root.rglob("*.py"))
    for name in ("lang/strings.json", "doc/LGE_Runtime_07.md"):
        path = PROJECT_ROOT / name
        if path.is_file():
            paths.append(path)
    assert paths, "Production source files not found"
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def _workspace(spec):
    """Використати ту саму production-конфігурацію, що в T112-02."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    workspace.broker = "CTRADER"
    protection = dict(workspace.profit_protection)
    pd_percent = DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    protection["max_profit_drawdown_percent"] = pd_percent
    workspace.profit_protection = protection
    settings = dict(workspace.replay_settings)
    settings.update(
        {
            "file_path": str(
                PROJECT_ROOT / "data" / "history" / "CTRADER"
                / "EURUSD" / "M1" / spec.file_name
            ),
            "start_utc": spec.start_utc,
            "end_utc": spec.end_utc,
            "source": Path(spec.file_name).stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    assert Path(settings["file_path"]).is_file(), settings["file_path"]
    return workspace


def _assert_baseline(spec, runtime) -> str:
    """Зафіксувати канонічну базу 2025/2026 перед аналізом причин."""
    from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
    from tests.runtime_workspace import (
        run_t105_18_stochastic_current_bar_production_regression_check as regression,
    )

    expected = regression.EXPECTATIONS[spec.code]
    summary = runtime.historical_summary
    session = runtime.replay_session
    execution = runtime.replay_execution
    assert summary is not None and session is not None and execution is not None
    assert session.completed
    assert isinstance(runtime.algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    assert (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    ) == (expected.trades, expected.wins, expected.losses, expected.break_even)
    assert math.isclose(
        summary.net_profit, expected.net,
        rel_tol=0.0, abs_tol=BASELINE_TOLERANCE,
    )
    assert math.isclose(
        summary.profit_factor, expected.profit_factor,
        rel_tol=0.0, abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown, expected.drawdown,
        rel_tol=0.0, abs_tol=BASELINE_TOLERANCE,
    )
    assert execution.policy.stop_range_multiplier == 1.0
    assert execution.policy.minimum_spread_multiples == 10.0
    assert execution.policy.take_profit_r_multiple == 2.0
    assert summary.close_reason_count("SESSION_END") == 0
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},be:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )


def _active_side(observation) -> str | None:
    """Класифікація напряму точно за production Alligator ACTIVE."""
    from core.workspace_alligator import (
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        ALLIGATOR_REGIME_TREND_UP,
        ALLIGATOR_STATE_BEARISH,
        ALLIGATOR_STATE_BULLISH,
    )

    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return None
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        and observation.state == ALLIGATOR_STATE_BULLISH
    ):
        return "BUY"
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    ):
        return "SELL"
    return None


def _boundary(record: WorkspaceSignalRecord, executed: set[str]) -> str:
    """Встановити лише фактично досягнуту межу для одного proposal."""
    if record.accepted:
        if record.signal_uid in executed:
            return "ACCEPTED_EXECUTED"
        return "ACCEPTED_NO_FACTUAL_TRADE"
    if record.risk_decision == "BLOCK":
        return "RISK_REJECT"
    if record.filter_decision == "REJECT":
        return "FILTER_REJECT"
    return "RUNTIME_OR_SPREAD_BLOCKED"


def _record_description(record: WorkspaceSignalRecord) -> str:
    """Повернути незмінений код відмови й terminal lifecycle, якщо є."""
    code = (
        record.risk_reason_code or record.filter_reason_code
        or record.source_reason_code or "NONE"
    )
    action = record.candidate_f_lifecycle_action or "NONE"
    terminal = record.candidate_f_lifecycle_reason or "NONE"
    return f"{code};lifecycle={action};terminal={terminal}"


def _summarize_window(
    chunk,
    direction: str,
    active_by_time,
    records,
    crosses,
    qualities,
    executed: set[str],
) -> tuple[str, str, Counter[str], Counter[str]]:
    """Знайти earliest observed boundary та всі супутні причини вікна."""
    start = chunk[0].timestamp
    end = chunk[-1].timestamp
    indexes = {event.timestamp: index for index, event in enumerate(chunk)}
    aligned = [
        index for index, event in enumerate(chunk)
        if active_by_time.get(event.timestamp) == direction
    ]
    assert aligned, "T112-02 expected aligned ACTIVE in every price window"
    same_records = sorted(
        (
            record for record in records
            if start <= record.timestamp <= end and record.direction == direction
        ),
        key=lambda record: (record.timestamp, record.signal_uid),
    )
    from core.workspace_macd import MACD_STATE_CROSS_DOWN, MACD_STATE_CROSS_UP

    cross_state = (
        MACD_STATE_CROSS_UP if direction == "BUY" else MACD_STATE_CROSS_DOWN
    )
    same_crosses = [
        observation for observation in crosses
        if start <= observation.timestamp <= end
        and observation.state == cross_state
    ]
    same_qualities = [
        diagnostic for diagnostic in qualities
        if start <= diagnostic.timestamp <= end
        and diagnostic.direction == direction
    ]
    boundary_counts: Counter[str] = Counter(
        _boundary(record, executed) for record in same_records
    )
    reason_counts: Counter[str] = Counter(
        _record_description(record) for record in same_records
        if not record.accepted
    )
    if not same_records:
        first_boundary = (
            "NO_ALIGNED_MACD_CROSS"
            if not same_crosses else "MACD_CROSS_WITHOUT_RECORDED_PROPOSAL"
        )
        first_code = "NONE"
    else:
        first = same_records[0]
        first_boundary = _boundary(first, executed)
        first_code = _record_description(first)
    first_proposal_bar = (
        indexes[same_records[0].timestamp] if same_records else "NONE"
    )
    first_cross_bar = (
        indexes[same_qualities[0].timestamp] if same_qualities else "NONE"
    )
    first_active_bar = aligned[0]
    quality_failed = sum(not item.final_quality_pass for item in same_qualities)
    quality_passed = len(same_qualities) - quality_failed
    quality_reasons = Counter(item.reason_code for item in same_qualities)
    boundaries_text = ",".join(
        f"{code}:{count}" for code, count in sorted(boundary_counts.items())
    ) or "NONE"
    rejects_text = ",".join(
        f"{code}:{count}" for code, count in sorted(reason_counts.items())
    ) or "NONE"
    quality_text = ",".join(
        f"{code}:{count}" for code, count in sorted(quality_reasons.items())
    ) or "NONE"
    line = (
        f"first_active_bar={first_active_bar}"
        f"|bars_after_first_active={len(chunk) - 1 - first_active_bar}"
        f"|aligned_cross_observations={len(same_crosses)}"
        f"|macd_quality_pass={quality_passed}"
        f"|macd_quality_reject={quality_failed}"
        f"|first_quality_bar={first_cross_bar}"
        f"|macd_quality_reasons={quality_text}"
        f"|aligned_proposals={len(same_records)}"
        f"|first_proposal_bar={first_proposal_bar}"
        f"|first_boundary={first_boundary}"
        f"|first_reason={first_code}"
        f"|all_boundary_counts={boundaries_text}"
        f"|all_reject_reasons={rejects_text}"
    )
    return first_boundary, line, boundary_counts, reason_counts


def _run_period(spec) -> tuple[int, int, Counter[str]]:
    """Незмінений Replay, потім діагностика лише missed price-only windows."""
    from core.workspace_algorithm import create_registered_workspace_algorithm
    from core.workspace_alligator import WorkspaceMacdAlligatorReplayAlgorithm
    from tests.runtime_temp import (
        run_algorithm_workspace_candidate_f_trend_coverage_2025_check as detector,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_replay_virtual_execution_check as regression,
    )
    from tests.runtime_workspace.run_t105_15_stochastic_entry_anatomy_check import (
        StochasticAnatomyRuntime,
    )

    assert detector.EXPECTED_M15_DELTA == BAR_INTERVAL
    probe = regression.BrokerRequestProbe()
    runtime = StochasticAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=probe,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    baseline = _assert_baseline(spec, runtime)
    assert probe.requests == 0
    assert not any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal if isinstance(entry.details, dict)
    )
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    source = algorithm.source
    assert signal_filter is not None and source is not None
    active_by_time = {
        observation.timestamp: _active_side(observation)
        for observation in signal_filter.observations
    }
    events_by_time = runtime.strategy_events
    events = tuple(events_by_time[key] for key in sorted(events_by_time))
    assert len(events) > 96
    windows = detector.strongest_non_overlapping(
        detector.price_only_trend_candidates(events)
    )
    assert len(windows) == EXPECTED_WINDOWS[spec.code]
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    executed = {trade.signal_uid for trade in trades}
    records = runtime.historical_signal_records
    crosses = source.observations
    qualities = source.quality_diagnostics
    summary = runtime.historical_summary
    assert summary is not None
    assert len(trades) == summary.opened_trades
    missed_count = 0
    covered_count = 0
    first_counts: Counter[str] = Counter()
    all_boundaries: Counter[str] = Counter()
    all_reasons: Counter[str] = Counter()
    print(f"period={spec.code}|baseline={baseline}")
    print(f"price_only_windows={len(windows)}")
    print("MISSED_WINDOW_ROWS")
    for window in windows:
        chunk = events[window.start_index:window.end_index + 1]
        assert len(chunk) == 32
        assert all(
            chunk[index].timestamp - chunk[index - 1].timestamp == BAR_INTERVAL
            for index in range(1, len(chunk))
        )
        same_trades = [
            trade for trade in trades
            if chunk[0].timestamp <= trade.signal_timestamp <= chunk[-1].timestamp
            and trade.direction == window.direction
        ]
        if same_trades:
            covered_count += 1
            continue
        missed_count += 1
        first, details, boundaries, reasons = _summarize_window(
            chunk, window.direction, active_by_time,
            records, crosses, qualities, executed,
        )
        first_counts[first] += 1
        all_boundaries.update(boundaries)
        all_reasons.update(reasons)
        print(
            f"window={chunk[0].timestamp.isoformat()}"
            f"|end={chunk[-1].timestamp.isoformat()}"
            f"|direction={window.direction}|{details}"
        )
    assert covered_count == EXPECTED_COVERED[spec.code]
    assert missed_count == EXPECTED_WINDOWS[spec.code] - covered_count
    assert sum(first_counts.values()) == missed_count
    print(f"covered_windows={covered_count}")
    print(f"missed_windows={missed_count}")
    print("FIRST_OBSERVED_BOUNDARY_COUNTS")
    for code, count in sorted(first_counts.items()):
        print(f"first_boundary={code}|windows={count}")
    print("ALL_PROPOSAL_BOUNDARY_COUNTS_NOT_WINDOW_COUNTS")
    for code, count in sorted(all_boundaries.items()):
        print(f"proposal_boundary={code}|events={count}")
    print("ALL_REJECT_REASON_COUNTS_NOT_WINDOW_COUNTS")
    for code, count in sorted(all_reasons.items()):
        print(f"reject_reason={code}|events={count}")
    print(f"period={spec.code}|broker_requests={probe.requests}")
    return missed_count, probe.requests, first_counts


def main() -> None:
    """T112-03 із незмінним Replay та окремими 2025/2026 звітами."""
    _bootstrap()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    before = _protected_hashes()
    print("T112_03_MISSED_PRICE_TREND_FIRST_BOUNDARY_ANATOMY")
    print("population=PRICE_ONLY_32_M15_NONOVERLAPPING_EX_POST_LABELS")
    print("boundary=FIRST_CHRONOLOGICAL_SAME_DIRECTION_PRODUCTION_SIGNAL_RECORD")
    print("no_proposal=OBSERVED_ONLY_NOT_CAUSAL_ROOT_PROOF")
    print("2026_period=PARTIAL_THROUGH_2026_08_25")
    print("comparison=PER_WINDOW_NOT_RAW_ANNUAL_TOTALS")
    total_missed = 0
    total_requests = 0
    all_first: Counter[str] = Counter()
    for spec in PERIODS:
        missed, requests, first_counts = _run_period(spec)
        total_missed += missed
        total_requests += requests
        all_first.update(first_counts)
    assert total_missed == EXPECTED_MISSED_TOTAL
    assert total_requests == 0
    assert _protected_hashes() == before
    print("AGGREGATE_FIRST_OBSERVED_BOUNDARIES")
    for code, count in sorted(all_first.items()):
        print(f"first_boundary={code}|windows={count}")
    print(f"total_missed_windows={total_missed}")
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("ex_post_labels_used_for_entry=False")
    print("new_entry_rule_created=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_03_MISSED_PRICE_TREND_FIRST_BOUNDARY_ANATOMY=OK")


if __name__ == "__main__":
    main()
