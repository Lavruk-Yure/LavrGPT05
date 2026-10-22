# -*- coding: utf-8 -*-
"""T112-06 — звірення популяцій price-only та ACTIVE-onset; TEST_ONLY.

Відтворює методику RM102/T112-02 і правила anchor із T112-05.
Мітки майбутнього руху використовуються винятково після завершення Replay.
Не формує entry, не підбирає порогів і не змінює production або MD7.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_market_event import WorkspaceMarketEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "T112-06"
BAR_INTERVAL = timedelta(minutes=15)
FEATURE_BARS = 8
HISTORICAL_COUNTS = {
    "2025": (17, 1077, 425, 265, 1),
    "2026": (13, 688, 284, 181, 0),
}
LABEL_ALIGNED = "FORWARD_STRONG_ALIGNED"
LABEL_OPPOSITE = "FORWARD_STRONG_OPPOSITE"
LABEL_CONTROL = "CONTROL_NO_STRONG_ALIGNED_TREND"
LABEL_UNAVAILABLE = "FORWARD_DATA_UNAVAILABLE_OR_GAP"


@dataclass(frozen=True, slots=True)
class OnsetRecord:
    """Один ACTIVE onset з фактичним статусом відбору за T112-05."""

    index: int
    direction: str
    fate: str
    outcome: str | None
    future_move_tr: float | None


def _bootstrap() -> None:
    """Підтримати автономний запуск із tests/roadmap112."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _source_hashes() -> dict[str, str]:
    """Перевірити, що дослідницький тест не редагує production."""
    roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "engine")
    paths = sorted(path for root in roots for path in root.rglob("*.py"))
    for relative in ("doc/LGE_Runtime_07.md", "lang/strings.json"):
        path = PROJECT_ROOT / relative
        if path.is_file():
            paths.append(path)
    assert paths, "Production files not found"
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def _workspace(spec):
    """Використати ідентичний frozen OOS workspace та PD=35%."""
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
    path = (
        PROJECT_ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1" / spec.file_name
    )
    assert path.is_file(), str(path)
    settings.update(
        {
            "file_path": str(path),
            "start_utc": spec.start_utc,
            "end_utc": spec.end_utc,
            "source": Path(spec.file_name).stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = settings
    return workspace


def _baseline(spec, runtime) -> str:
    """Не приймати діагностику, якщо чинний Replay baseline змінився."""
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
    assert math.isclose(summary.net_profit, expected.net, abs_tol=0.005)
    assert math.isclose(
        summary.profit_factor,
        expected.profit_factor,
        abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown,
        expected.drawdown,
        abs_tol=0.005,
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
    """Напрям тільки production Alligator ACTIVE, не ex-post label."""
    from core.workspace_alligator import (
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        ALLIGATOR_REGIME_TREND_UP,
        ALLIGATOR_STATE_BEARISH,
        ALLIGATOR_STATE_BULLISH,
    )

    if observation is None or observation.regime_phase != (
        ALLIGATOR_REGIME_PHASE_ACTIVE
    ):
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


def _contiguous(events: tuple[WorkspaceMarketEvent, ...], start: int, end: int) -> bool:
    """Виключити розриви всередині потрібного M15-інтервалу."""
    return all(
        events[index].timestamp - events[index - 1].timestamp == BAR_INTERVAL
        for index in range(start + 1, end + 1)
    )


def _reference_tr(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """Той самий median true range, що в RM102/T112-05."""
    assert events
    previous = float(events[0].close)
    ranges: list[float] = []
    for event in events:
        ranges.append(
            max(
                float(event.high) - float(event.low),
                abs(float(event.high) - previous),
                abs(float(event.low) - previous),
            )
        )
        previous = float(event.close)
    return float(statistics.median(ranges))


def _forward_label(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    direction: str,
    reference: float,
    bars: int,
    min_move: float,
    min_efficiency: float,
) -> tuple[str, float | None]:
    """Повторити T112-05 outcome на майбутніх 32 M15-барах, ex-post."""
    end = index + bars - 1
    if end >= len(events) or not _contiguous(events, index, end):
        return LABEL_UNAVAILABLE, None
    sign = 1.0 if direction == "BUY" else -1.0
    delta = float(events[end].close) - float(events[index].close)
    path = math.fsum(
        abs(float(events[pos].close) - float(events[pos - 1].close))
        for pos in range(index + 1, end + 1)
    )
    normalized = sign * delta / reference
    efficiency = 0.0 if path == 0.0 else abs(delta) / path
    if abs(normalized) >= min_move and efficiency >= min_efficiency:
        return (
            LABEL_ALIGNED if normalized > 0.0 else LABEL_OPPOSITE,
            normalized,
        )
    return LABEL_CONTROL, normalized


def _onset_records(
    events: tuple[WorkspaceMarketEvent, ...],
    active_sides: dict[datetime, str | None],
    bars: int,
    reference_bars: int,
    min_move: float,
    min_efficiency: float,
) -> tuple[tuple[OnsetRecord, ...], Counter[str]]:
    """Відтворити переходи та пріоритети виключення з T112-05."""
    counters: Counter[str] = Counter()
    records: list[OnsetRecord] = []
    last_selected = -bars
    previous_side: str | None = None
    previous_timestamp: datetime | None = None
    for index, event in enumerate(events):
        side = active_sides.get(event.timestamp)
        gap = (
            previous_timestamp is not None
            and event.timestamp - previous_timestamp != BAR_INTERVAL
        )
        onset = side is not None and (side != previous_side or gap)
        previous_side = side
        previous_timestamp = event.timestamp
        if not onset or side is None:
            continue
        counters["active_onsets_total"] += 1
        reference: float | None = None
        fate = "SELECTED"
        if index < reference_bars:
            fate = "WITHOUT_REFERENCE"
        elif index - last_selected < bars:
            fate = "EMBARGOED"
        elif not _contiguous(events, index - FEATURE_BARS, index):
            fate = "PAST_8BAR_GAP"
        else:
            reference = _reference_tr(events[index - reference_bars : index])  # noqa
            if reference <= 0.0:
                fate = "ZERO_REFERENCE"
        if fate != "SELECTED":
            counters[f"fate:{fate}"] += 1
            records.append(OnsetRecord(index, side, fate, None, None))
            continue
        assert reference is not None, "Selected onset has no reference"
        last_selected = index
        label, future_move = _forward_label(
            events,
            index,
            side,
            reference,
            bars,
            min_move,
            min_efficiency,
        )
        counters["fate:SELECTED"] += 1
        counters[f"outcome:{label}"] += 1
        records.append(OnsetRecord(index, side, fate, label, future_move))
    return tuple(records), counters


def _window_overlap(
    window,
    events: tuple[WorkspaceMarketEvent, ...],
    active_sides: dict[datetime, str | None],
    onsets: tuple[OnsetRecord, ...],
    bars: int,
) -> tuple[str, Counter[str]]:
    """Зіставити один RM102 price window з реальними onset/anchor."""
    start = window.start_index
    end = window.end_index
    direction = window.direction
    aligned_offsets = tuple(
        index - start
        for index in range(start, end + 1)
        if active_sides.get(events[index].timestamp) == direction
    )
    aligned_bars = len(aligned_offsets)
    assert aligned_bars > 0, "T112-02 overlap changed"
    matching_onsets = tuple(
        row
        for row in onsets
        if row.direction == direction and start <= row.index <= end
    )
    selected = tuple(row for row in matching_onsets if row.fate == "SELECTED")
    prior_overlaps = tuple(
        row
        for row in onsets
        if row.direction == direction
        and row.fate == "SELECTED"
        and row.index < start <= row.index + bars - 1
    )
    if selected:
        classification = "SELECTED_ONSET_IN_PRICE_WINDOW"
    elif matching_onsets:
        classification = "ONSET_IN_WINDOW_EXCLUDED"
    else:
        classification = "NO_ONSET_IN_WINDOW_ALREADY_ACTIVE"
        assert active_sides.get(events[start].timestamp) == direction
    counter: Counter[str] = Counter()
    counter[f"window_class:{classification}"] += 1
    for row in matching_onsets:
        counter[f"matched_onset_fate:{row.fate}"] += 1
    for row in selected:
        assert row.outcome is not None
        counter[f"matched_selected_outcome:{row.outcome}"] += 1
    earliest_fate = (
        ",".join(f"{row.index - start}:{row.fate}" for row in matching_onsets) or "NONE"
    )
    anchor_labels = (
        ",".join(
            f"{row.index - start}:{row.outcome}:"
            + (
                f"{row.future_move_tr:+.4f}"
                if row.future_move_tr is not None
                else "N/A"
            )
            for row in selected
        )
        or "NONE"
    )
    print(
        f"window={events[start].timestamp.isoformat()}"
        f"|end={events[end].timestamp.isoformat()}"
        f"|direction={direction}|class={classification}"
        f"|aligned_active_bars={aligned_bars}"
        f"|first_aligned_active_offset={aligned_offsets[0]}"
        f"|aligned_onsets_in_window={len(matching_onsets)}"
        f"|selected_onsets_in_window={len(selected)}"
        f"|selected_pre_window_horizon_overlap={len(prior_overlaps)}"
        f"|onset_offsets_and_fates={earliest_fate}"
        f"|selected_offset_outcome_move={anchor_labels}"
        f"|price_window_normalized_move={window.normalized_move:.4f}"
        f"|price_window_efficiency={window.path_efficiency:.4f}"
    )
    return classification, counter


def _audit_period(spec) -> None:
    """Replay одного періоду з окремими ex-post population labels."""
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
    baseline = _baseline(spec, runtime)
    assert probe.requests == 0
    assert not any(
        bool(item.details.get("broker_execution_attempted"))
        for item in runtime.journal
        if isinstance(item.details, dict)
    )
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    assert algorithm.signal_filter is not None
    events_by_time = runtime.strategy_events
    events = tuple(events_by_time[time] for time in sorted(events_by_time))
    assert len(events) > 96
    assert len({event.timestamp for event in events}) == len(events)
    assert all(event.timeframe == "M15" for event in events)
    assert all(
        events[index - 1].timestamp < events[index].timestamp
        for index in range(1, len(events))
    )
    observations = tuple(algorithm.signal_filter.observations)
    assert all(item.timestamp in events_by_time for item in observations)
    active_sides = {item.timestamp: _active_side(item) for item in observations}
    price_windows = detector.strongest_non_overlapping(
        detector.price_only_trend_candidates(events)
    )
    onsets, counters = _onset_records(
        events,
        active_sides,
        detector.TREND_WINDOW_BARS,
        detector.TREND_VOLATILITY_REFERENCE_BARS,
        detector.TREND_MIN_NORMALIZED_MOVE,
        detector.TREND_MIN_PATH_EFFICIENCY,
    )
    (
        windows_expected,
        onsets_expected,
        selected_expected,
        valid_expected,
        aligned_expected,
    ) = HISTORICAL_COUNTS[spec.code]
    selected = counters["fate:SELECTED"]
    valid = selected - counters[f"outcome:{LABEL_UNAVAILABLE}"]
    aligned = counters[f"outcome:{LABEL_ALIGNED}"]
    assert (
        len(price_windows),
        counters["active_onsets_total"],
        selected,
        valid,
        aligned,
    ) == (
        windows_expected,
        onsets_expected,
        selected_expected,
        valid_expected,
        aligned_expected,
    ), "T112-02/T112-05 population contract diverged"
    assert sum(
        counters[f"fate:{status}"]
        for status in (
            "SELECTED",
            "WITHOUT_REFERENCE",
            "EMBARGOED",
            "PAST_8BAR_GAP",
            "ZERO_REFERENCE",
        )
    ) == len(onsets)
    assert counters["active_onsets_total"] == len(onsets)
    print(f"period={spec.code}|baseline={baseline}")
    print(
        f"period={spec.code}|price_only_windows={len(price_windows)}"
        f"|active_onsets={len(onsets)}"
        f"|selected_anchors={selected}|valid_outcomes={valid}"
        f"|strong_aligned={aligned}"
    )
    for key, count in sorted(counters.items()):
        print(f"period={spec.code}|{key}={count}")
    print("PRICE_WINDOW_TO_ONSET_ROWS")
    window_counts: Counter[str] = Counter()
    for window in price_windows:
        _, evidence = _window_overlap(
            window,
            events,
            active_sides,
            onsets,
            detector.TREND_WINDOW_BARS,
        )
        window_counts.update(evidence)
    print("WINDOW_RECONCILIATION_COUNTS")
    for key, count in sorted(window_counts.items()):
        print(f"period={spec.code}|{key}={count}")
    assert sum(
        count for key, count in window_counts.items() if key.startswith("window_class:")
    ) == len(price_windows)
    print(f"period={spec.code}|broker_requests={probe.requests}")


def main() -> None:
    """Дослідити відмінність population labels без змін стратегії."""
    _bootstrap()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    before = _source_hashes()
    print("T112_06_OUTCOME_POPULATION_RECONCILIATION")
    print("price_windows=RM102_32_COMPLETED_M15_EX_POST_ONLY")
    print("anchors=T112_05_FIRST_ACTIVE_ONSET_CHRONOLOGICAL_EMBARGO")
    print("forward_labels=POST_ANCHOR_32_M15_EX_POST_ONLY")
    print("matching=TIMESTAMP_AND_DIRECTION_NO_LOOKAHEAD_ENTRY")
    print("2026_period=PARTIAL_THROUGH_2026_08_25")
    for spec in PERIODS:
        _audit_period(spec)
    assert _source_hashes() == before
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print("mode=RM112_T112_06_POPULATION_RECONCILIATION_TEST_ONLY")
    print("ex_post_labels_used_for_entry=False")
    print("entry_rule_changed=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_06_OUTCOME_POPULATION_RECONCILIATION=OK")


if __name__ == "__main__":
    main()
