# -*- coding: utf-8 -*-
"""T112-02 — незалежні price-only тренди проти Alligator ACTIVE, TEST_ONLY.

Дослідницька розмітка ex-post не передається алгоритму та не змінює entry.
Кожний період відтворюється чинним зареєстрованим Candidate F.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_alligator import WorkspaceAlligatorObservation
    from core.workspace_market_event import WorkspaceMarketEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "T112-02"
MODE = "RM112_T112_02_PRICE_ONLY_VS_ACTIVE_POPULATION_OVERLAP_TEST_ONLY"
EXPECTED_STRONG_ACTIVE = {"2025": 139, "2026": 80}
STRONG_MOVE_R = 2.0
BAR_INTERVAL = timedelta(minutes=15)
BASELINE_TOLERANCE = 0.005


@dataclass(frozen=True, slots=True)
class ActiveSegment:
    """Безперервна послідовність directional ACTIVE observations."""

    side: str
    observations: tuple[WorkspaceAlligatorObservation, ...]


def _bootstrap_import_path() -> None:
    """Дозволити окремий запуск tests/roadmap112 з будь-якого каталогу."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _source_hashes() -> dict[str, str]:
    """Звірити незмінність production коду і файлу локалізації."""
    roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "engine")
    paths = sorted(path for root in roots for path in root.rglob("*.py"))
    strings_path = PROJECT_ROOT / "lang" / "strings.json"
    if strings_path.is_file():
        paths.append(strings_path)
    md7_path = PROJECT_ROOT / "doc" / "LGE_Runtime_07.md"
    if md7_path.is_file():
        paths.append(md7_path)
    assert paths, "Production source files not found"
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def _active_side(observation: WorkspaceAlligatorObservation) -> str | None:
    """Відтворити напрямок ACTIVE з T108-06 без імпорту private helper."""
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


def _active_segments(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    *,
    split_on_gap: bool,
) -> tuple[ActiveSegment, ...]:
    """Порівняти legacy T108 сегментацію з gap-aware варіантом."""
    result: list[ActiveSegment] = []
    current: list[WorkspaceAlligatorObservation] = []
    current_side: str | None = None
    for observation in observations:
        side = _active_side(observation)
        gap = bool(
            current and observation.timestamp - current[-1].timestamp != BAR_INTERVAL
        )
        if side is not None and side == current_side and not (split_on_gap and gap):
            current.append(observation)
            continue
        if current_side is not None and current:
            result.append(ActiveSegment(current_side, tuple(current)))
        current_side = side
        current = [observation] if side is not None else []
    if current_side is not None and current:
        result.append(ActiveSegment(current_side, tuple(current)))
    return tuple(result)


def _strong_move_r(
    segment: ActiveSegment,
    events: dict[datetime, WorkspaceMarketEvent],
) -> float:
    """Обчислити historical T108-06 2R label тільки після Replay."""
    first = events[segment.observations[0].timestamp]
    stop = max(first.high - first.low, first.spread * 10.0)
    assert stop > 0.0
    segment_events = tuple(events[ob.timestamp] for ob in segment.observations)
    if segment.side == "BUY":
        favorable = max(event.high for event in segment_events) - first.close
    else:
        favorable = first.close - min(event.low for event in segment_events)
    return max(favorable, 0.0) / stop


def _workspace_for_period(spec):
    """Відтворити налаштування production 35% із T105-10."""
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen,
    )

    workspace = frozen.frozen_oos_workspace()
    workspace.broker = "CTRADER"
    protection = dict(workspace.profit_protection)
    protection["max_profit_drawdown_percent"] = (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
    )
    workspace.profit_protection = protection
    settings = dict(workspace.replay_settings)
    settings.update(
        {
            "file_path": str(
                PROJECT_ROOT
                / "data"
                / "history"
                / "CTRADER"
                / "EURUSD"
                / "M1"
                / spec.file_name
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
    """Повторити перевірку метрик та exit geometry з T105-18."""
    from core.workspace_alligator import (
        ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
        WorkspaceMacdAlligatorReplayAlgorithm,
    )
    from core.workspace_profit_guard import (
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    from engine.runtime_constants import (
        DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
    )
    from tests.runtime_workspace import (
        run_t105_18_stochastic_current_bar_production_regression_check as regression,
    )

    expected = regression.EXPECTATIONS[spec.code]
    summary = runtime.historical_summary
    execution = runtime.replay_execution
    session = runtime.replay_session
    assert summary is not None and execution is not None and session is not None
    assert session.completed
    assert type(runtime.algorithm) is WorkspaceMacdAlligatorReplayAlgorithm
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT == 35.0
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        35.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    ) == (expected.trades, expected.wins, expected.losses, expected.break_even)
    assert math.isclose(
        summary.net_profit,
        expected.net,
        rel_tol=0.0,
        abs_tol=BASELINE_TOLERANCE,
    )
    assert math.isclose(
        summary.profit_factor,
        expected.profit_factor,
        rel_tol=0.0,
        abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown,
        expected.drawdown,
        rel_tol=0.0,
        abs_tol=BASELINE_TOLERANCE,
    )
    assert execution.policy.stop_range_multiplier == 1.0
    assert execution.policy.minimum_spread_multiples == 10.0
    assert execution.policy.take_profit_r_multiple == 2.0
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == expected.profit_drawdown
    assert summary.close_reason_count("STOP_LOSS") == expected.stop_loss
    assert summary.close_reason_count("TAKE_PROFIT") == expected.take_profit
    assert summary.close_reason_count("SESSION_END") == 0
    records = runtime.signal_records_for_ui()
    accepted = {record.signal_uid: record for record in records if record.accepted}
    events_by_time = {event.timestamp: event for event in session.events}
    diagnostics = execution.trade_diagnostics()
    assert len(diagnostics) == summary.opened_trades
    for trade in diagnostics:
        signal = accepted[trade.signal_uid]
        event = events_by_time[signal.timestamp]
        distance = max(event.high - event.low, event.spread * 10.0)
        assert math.isclose(
            trade.stop_loss_distance,
            distance,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        assert math.isclose(
            trade.take_profit_distance,
            distance * 2.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    rejected = tuple(
        record
        for record in records
        if record.filter_reason_code == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
    )
    assert len(rejected) == regression.EXPECTED_REJECTS[spec.code]
    assert all(event.timeframe == "M15" for event in session.events)
    assert not any(
        bool(item.details.get("broker_execution_attempted"))
        for item in runtime.journal
        if isinstance(item.details, dict)
    )
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},be:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )


def _audit_period(spec) -> None:
    """Replay одного періоду з двома незалежними ex-post labels."""
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
        _workspace_for_period(spec),
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

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    observations = tuple(signal_filter.observations)
    events_by_time = runtime.strategy_events
    assert all(ob.timestamp in events_by_time for ob in observations)
    events = tuple(events_by_time[key] for key in sorted(events_by_time))
    assert len(events) > 96
    assert len({event.timestamp for event in events}) == len(events)
    assert all(
        events[index - 1].timestamp < events[index].timestamp
        for index in range(1, len(events))
    )
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()

    # Price-only candidate detector читає лише завершені OHLC ex-post.
    windows = detector.strongest_non_overlapping(
        detector.price_only_trend_candidates(events)
    )
    active_sides = {ob.timestamp: _active_side(ob) for ob in observations}
    counts: Counter[str] = Counter()
    late_first_active: list[int] = []
    covered = 0
    rows: list[str] = []
    for window in windows:
        chunk = events[window.start_index : window.end_index + 1]  # noqa
        assert len(chunk) == 32
        assert all(
            chunk[index].timestamp - chunk[index - 1].timestamp == BAR_INTERVAL
            for index in range(1, len(chunk))
        )
        aligned = [
            index
            for index, event in enumerate(chunk)
            if active_sides.get(event.timestamp) == window.direction
        ]
        opposite = [
            index
            for index, event in enumerate(chunk)
            if active_sides.get(event.timestamp) not in (None, window.direction)
        ]
        if aligned:
            classification = "ALIGNED_ACTIVE_PRESENT"
            late_first_active.append(aligned[0])
        elif opposite:
            classification = "OPPOSITE_ACTIVE_ONLY"
        else:
            classification = "NO_DIRECTIONAL_ACTIVE"
        counts[classification] += 1
        trade_count = sum(
            chunk[0].timestamp <= trade.signal_timestamp <= chunk[-1].timestamp
            and trade.direction == window.direction
            for trade in trades
        )
        covered += bool(trade_count)
        rows.append(
            f"window={chunk[0].timestamp.isoformat()}"
            f"|end={chunk[-1].timestamp.isoformat()}"
            f"|direction={window.direction}|class={classification}"
            f"|first_aligned_bar={aligned[0] if aligned else 'NONE'}"
            f"|opposite_bars={len(opposite)}|aligned_trades={trade_count}"
            f"|normalized_move={window.normalized_move:.4f}"
            f"|efficiency={window.path_efficiency:.4f}"
        )

    # Legacy популяція T108-06 без gap check: контроль історичних чисел.
    legacy = _active_segments(observations, split_on_gap=False)
    gap_aware = _active_segments(observations, split_on_gap=True)
    strong_legacy = sum(
        _strong_move_r(segment, events_by_time) + 1e-12 >= STRONG_MOVE_R
        for segment in legacy
    )
    strong_gap_aware = sum(
        _strong_move_r(segment, events_by_time) + 1e-12 >= STRONG_MOVE_R
        for segment in gap_aware
    )
    assert strong_legacy == EXPECTED_STRONG_ACTIVE[spec.code], (
        spec.code,
        strong_legacy,
        EXPECTED_STRONG_ACTIVE[spec.code],
    )
    assert len(gap_aware) >= len(legacy)
    assert sum(counts.values()) == len(windows)
    assert len({(w.start_index, w.end_index) for w in windows}) == len(windows)

    print(f"period={spec.code}|baseline={baseline}")
    print(f"price_only_windows={len(windows)}")
    print(f"historical_strong_active_segments={strong_legacy}")
    print(f"gap_aware_strong_active_segments={strong_gap_aware}")
    print(f"active_segment_count_legacy={len(legacy)}")
    print(f"active_segment_count_gap_aware={len(gap_aware)}")
    for classification in (
        "ALIGNED_ACTIVE_PRESENT",
        "OPPOSITE_ACTIVE_ONLY",
        "NO_DIRECTIONAL_ACTIVE",
    ):
        print(f"classification={classification}|count={counts[classification]}")
    print(f"price_windows_with_aligned_production_trade={covered}")
    print(
        "aligned_active_first_bar_0_based_min="
        f"{min(late_first_active) if late_first_active else 'NONE'}"
    )
    print(
        "aligned_active_first_bar_0_based_max="
        f"{max(late_first_active) if late_first_active else 'NONE'}"
    )
    print("PRICE_ONLY_WINDOW_ROWS")
    for row in rows:
        print(row)
    print(f"period={spec.code}|broker_requests={probe.requests}")


def main() -> None:
    """Запустити T112-02 без модифікації production."""
    _bootstrap_import_path()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    original_hashes = _source_hashes()
    print("T112_02_PRICE_ONLY_VS_ACTIVE_POPULATION_OVERLAP")
    print("overlap_rule=ANY_SAME_DIRECTION_ACTIVE_ON_32_COMPLETED_M15_BARS")
    print("gap_rule=STRICT_15_MINUTES_INSIDE_PRICE_WINDOW")
    print("active_segment_gap_audit=LEGACY_VS_STRICT_15_MINUTES")
    print("price_label=EX_POST_ONLY_NOT_ENTRY")
    for period in PERIODS:
        _audit_period(period)
    assert _source_hashes() == original_hashes
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_02_PRICE_ONLY_VS_ACTIVE_POPULATION_OVERLAP=OK")


if __name__ == "__main__":
    main()
