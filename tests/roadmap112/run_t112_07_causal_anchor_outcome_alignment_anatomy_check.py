# -*- coding: utf-8 -*-
"""T112-07 — часові точки та ex-post outcome для price-only трендів.

TEST_ONLY. Перевіряє, чому один сильний RM102 32-bar price window
не збігається з міткою наступних 32 барів від Alligator ACTIVE onset.
Жодна ex-post мітка не використовується для вибору entry або anchor.
Production, exit, MD7 і пороги дослідницького RM102 не змінюються.
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
    from tests.runtime_temp import (
        run_algorithm_workspace_candidate_f_trend_coverage_2025_check as rm102,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BAR_INTERVAL = timedelta(minutes=15)
PAST_FEATURE_BARS = 8
HISTORICAL_COUNTS = {
    "2025": (17, 1077, 425, 265, 1),
    "2026": (13, 688, 284, 181, 0),
}
LABEL_ALIGNED = "FORWARD_STRONG_ALIGNED"
LABEL_OPPOSITE = "FORWARD_STRONG_OPPOSITE"
LABEL_CONTROL = "CONTROL_NO_STRONG_ALIGNED_TREND"
LABEL_UNAVAILABLE = "FORWARD_DATA_UNAVAILABLE_OR_GAP"


@dataclass(frozen=True, slots=True)
class Outcome:
    """Ex-post результат фіксованого горизонту; не trading signal."""

    label: str
    reason: str
    move_tr: float | None
    efficiency: float | None
    first_gap_offset: int | None
    bars_available: int


@dataclass(frozen=True, slots=True)
class Onset:
    """Хронологічний ACTIVE onset із незмінними правилами T112-05."""

    index: int
    direction: str
    fate: str
    previous_selected: int | None
    outcome: Outcome | None


def _bootstrap() -> None:
    """Дозволити запуск із tests/roadmap112 без налаштувань IDE."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _source_hashes() -> dict[str, str]:
    """Контроль незмінності робочого дерева production та MD7."""
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
    """Використати frozen OOS workspace та поточний PD=35%."""
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
    """Не продовжувати діагностику при зміненому production baseline."""
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
    """Тільки підтверджена production фаза ACTIVE відповідного напряму."""
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


def _first_gap(
    events: tuple[WorkspaceMarketEvent, ...],
    start: int,
    end: int,
) -> int | None:
    """Повернути offset першого відсутнього M15-переходу."""
    for index in range(start + 1, end + 1):
        if events[index].timestamp - events[index - 1].timestamp != BAR_INTERVAL:
            return index - start
    return None


def _reference(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """RM102 median TR для попередніх 64 completed bars (gaps allowed)."""
    assert events
    previous_close = float(events[0].close)
    ranges: list[float] = []
    for event in events:
        ranges.append(
            max(
                float(event.high) - float(event.low),
                abs(float(event.high) - previous_close),
                abs(float(event.low) - previous_close),
            )
        )
        previous_close = float(event.close)
    return float(statistics.median(ranges))


def _outcome(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    direction: str,
    reference: float,
    bars: int,
    min_move: float,
    min_efficiency: float,
) -> Outcome:
    """Ex-post 32-bar label T112-05; anchor не змінюється через label."""
    end = index + bars - 1
    if end >= len(events):
        return Outcome(
            LABEL_UNAVAILABLE,
            "OUT_OF_RANGE",
            None,
            None,
            None,
            max(0, len(events) - index),
        )
    gap_offset = _first_gap(events, index, end)
    if gap_offset is not None:
        return Outcome(
            LABEL_UNAVAILABLE,
            "M15_GAP",
            None,
            None,
            gap_offset,
            gap_offset,
        )
    sign = 1.0 if direction == "BUY" else -1.0
    delta = float(events[end].close) - float(events[index].close)
    path = math.fsum(
        abs(float(events[pos].close) - float(events[pos - 1].close))
        for pos in range(index + 1, end + 1)
    )
    normalized = sign * delta / reference
    efficiency = 0.0 if path == 0.0 else abs(delta) / path
    if abs(normalized) >= min_move and efficiency >= min_efficiency:
        label = LABEL_ALIGNED if normalized > 0.0 else LABEL_OPPOSITE
        reason = "STRONG_LABEL"
    else:
        label = LABEL_CONTROL
        if abs(normalized) < min_move and efficiency < min_efficiency:
            reason = "MOVE_AND_EFFICIENCY_BELOW"
        elif abs(normalized) < min_move:
            reason = "MOVE_BELOW"
        else:
            reason = "EFFICIENCY_BELOW"
    return Outcome(label, reason, normalized, efficiency, None, bars)


def _onsets(
    events: tuple[WorkspaceMarketEvent, ...],
    active_sides: dict[datetime, str | None],
    bars: int,
    reference_bars: int,
    min_move: float,
    min_efficiency: float,
) -> tuple[tuple[Onset, ...], Counter[str]]:
    """Відтворити хронологічний sampling T112-05 без змін."""
    rows: list[Onset] = []
    counts: Counter[str] = Counter()
    previous_side: str | None = None
    previous_timestamp: datetime | None = None
    last_selected = -bars
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
        counts["onsets_total"] += 1
        fate = "SELECTED"
        reference: float | None = None
        if index < reference_bars:
            fate = "WITHOUT_REFERENCE"
        elif index - last_selected < bars:
            fate = "EMBARGOED"
        elif _first_gap(events, index - PAST_FEATURE_BARS, index) is not None:
            fate = "PAST_8BAR_GAP"
        else:
            reference = _reference(events[index - reference_bars : index])  # noqa
            if reference <= 0.0:
                fate = "ZERO_REFERENCE"
        previous_selected = last_selected if last_selected >= 0 else None
        if fate == "SELECTED":
            assert reference is not None
            last_selected = index
            result = _outcome(
                events,
                index,
                side,
                reference,
                bars,
                min_move,
                min_efficiency,
            )
            counts[f"outcome:{result.label}"] += 1
        else:
            result = None
        counts[f"fate:{fate}"] += 1
        rows.append(Onset(index, side, fate, previous_selected, result))
    return tuple(rows), counts


def _format_outcome(result: Outcome) -> str:
    """Коротка деталізація одного ex-post результату."""
    move = "N/A" if result.move_tr is None else f"{result.move_tr:+.4f}"
    efficiency = "N/A" if result.efficiency is None else f"{result.efficiency:.4f}"
    gap = "NONE" if result.first_gap_offset is None else result.first_gap_offset
    return (
        f"{result.label}:{result.reason}:"
        f"move={move}:eff={efficiency}:gap_offset={gap}:"
        f"bars_available={result.bars_available}"
    )


def _window_audit(
    window: rm102.TrendWindow,
    events: tuple[WorkspaceMarketEvent, ...],
    active_sides: dict[datetime, str | None],
    onsets: tuple[Onset, ...],
    bars: int,
    reference_bars: int,
    min_move: float,
    min_efficiency: float,
) -> Counter[str]:
    """Розкласти відмінність source-window та post-anchor outcome."""
    start = window.start_index
    end = window.end_index
    direction = window.direction
    reference = _reference(events[start - reference_bars : start])  # noqa
    assert reference > 0.0
    source_label = _outcome(
        events,
        start,
        direction,
        reference,
        bars,
        min_move,
        min_efficiency,
    )
    assert source_label.label == LABEL_ALIGNED
    assert math.isclose(
        source_label.move_tr or 0.0,
        window.normalized_move,
        abs_tol=0.000001,
    )
    assert math.isclose(
        source_label.efficiency or 0.0,
        window.path_efficiency,
        abs_tol=0.000001,
    )
    aligned = tuple(
        index
        for index in range(start, end + 1)
        if active_sides.get(events[index].timestamp) == direction
    )
    assert aligned, "T112-02 overlap contract changed"
    first_active = aligned[0]
    matching = tuple(
        item
        for item in onsets
        if item.direction == direction and start <= item.index <= end
    )
    selected = tuple(item for item in matching if item.fate == "SELECTED")
    if selected:
        classification = "SELECTED_ONSET_IN_PRICE_WINDOW"
    elif matching:
        classification = "ONSET_IN_WINDOW_EXCLUDED"
    else:
        classification = "NO_ONSET_IN_WINDOW_ALREADY_ACTIVE"
        assert first_active == start
    # Спільна одиниця TR: лише опис руху всередині того самого RM102 window.
    sign = 1.0 if direction == "BUY" else -1.0
    full_delta = (
        sign * (float(events[end].close) - float(events[start].close)) / reference
    )
    before_active = (
        sign
        * (float(events[first_active].close) - float(events[start].close))
        / reference
    )
    after_active = (
        sign
        * (float(events[end].close) - float(events[first_active].close))
        / reference
    )
    assert math.isclose(
        full_delta,
        before_active + after_active,
        abs_tol=1e-9,
    )
    active_ref = _reference(
        events[first_active - reference_bars : first_active]  # noqa
    )  # noqa
    first_active_result = _outcome(
        events,
        first_active,
        direction,
        active_ref,
        bars,
        min_move,
        min_efficiency,
    )
    counts: Counter[str] = Counter()
    counts[f"window_class:{classification}"] += 1
    counts[f"first_active_label:{first_active_result.label}"] += 1
    counts[f"first_active_reason:{first_active_result.reason}"] += 1
    counts["first_active_before_end"] += int(first_active < end)
    if first_active == start:
        counts["first_active_at_window_start"] += 1
    else:
        counts["first_active_after_window_start"] += 1
    for item in matching:
        counts[f"onset_fate:{item.fate}"] += 1
        if item.fate == "EMBARGOED":
            counts["embargoed_onsets_inside_price_windows"] += 1
            assert item.previous_selected is not None
            assert 0 < item.index - item.previous_selected < bars
    for item in selected:
        assert item.outcome is not None
        counts[f"selected_label:{item.outcome.label}"] += 1
        counts[f"selected_reason:{item.outcome.reason}"] += 1
    # Усі onset без SELECTED мають ex-post shadow label, не trading rule.
    excluded_outcomes = []
    for item in matching:
        if item.fate == "SELECTED":
            continue
        if item.index < reference_bars:
            excluded_outcomes.append("WITHOUT_REFERENCE")
            continue
        ref = _reference(events[item.index - reference_bars : item.index])  # noqa
        if ref <= 0.0:
            excluded_outcomes.append("ZERO_REFERENCE")
            continue
        shadow = _outcome(
            events,
            item.index,
            direction,
            ref,
            bars,
            min_move,
            min_efficiency,
        )
        excluded_outcomes.append(_format_outcome(shadow))
        counts[f"excluded_shadow_label:{shadow.label}"] += 1
    selected_info = (
        ";".join(
            f"{item.index - start}:{_format_outcome(item.outcome)}"
            for item in selected
            if item.outcome is not None
        )
        or "NONE"
    )
    fate_info = (
        ";".join(
            f"{item.index - start}:{item.fate}:"
            + (
                "NONE"
                if item.previous_selected is None
                else str(item.index - item.previous_selected)
            )
            for item in matching
        )
        or "NONE"
    )
    print(
        f"window={events[start].timestamp.isoformat()}"
        f"|end={events[end].timestamp.isoformat()}"
        f"|direction={direction}|class={classification}"
        f"|first_active_offset={first_active - start}"
        f"|bars_remaining_in_window={end - first_active}"
        f"|original_move_tr={window.normalized_move:.4f}"
        f"|original_efficiency={window.path_efficiency:.4f}"
        f"|pre_active_move_tr={before_active:+.4f}"
        f"|post_active_in_window_move_tr={after_active:+.4f}"
        f"|first_active_forward={_format_outcome(first_active_result)}"
        f"|onset_offset_fate_prev_selected_distance={fate_info}"
        f"|selected_forward={selected_info}"
        f"|excluded_shadow_forward={';'.join(excluded_outcomes) or 'NONE'}"
    )
    return counts


def _audit_period(spec) -> None:
    """Replay 2025/2026 із захистом baseline та окремими label."""
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
    sides = {item.timestamp: _active_side(item) for item in observations}
    windows = detector.strongest_non_overlapping(
        detector.price_only_trend_candidates(events)
    )
    bars = detector.TREND_WINDOW_BARS
    ref_bars = detector.TREND_VOLATILITY_REFERENCE_BARS
    min_move = detector.TREND_MIN_NORMALIZED_MOVE
    min_efficiency = detector.TREND_MIN_PATH_EFFICIENCY
    onsets, onset_counts = _onsets(
        events,
        sides,
        bars,
        ref_bars,
        min_move,
        min_efficiency,
    )
    expected_counts = HISTORICAL_COUNTS[spec.code]
    selected_count = onset_counts["fate:SELECTED"]
    valid_count = selected_count - onset_counts[f"outcome:{LABEL_UNAVAILABLE}"]
    strong_count = onset_counts[f"outcome:{LABEL_ALIGNED}"]
    assert (
        len(windows),
        onset_counts["onsets_total"],
        selected_count,
        valid_count,
        strong_count,
    ) == expected_counts, "T112-06 historical population contract diverged"
    print(f"period={spec.code}|baseline={baseline}")
    print(
        f"period={spec.code}|price_only_windows={len(windows)}"
        f"|active_onsets={len(onsets)}|selected={selected_count}"
        f"|valid_outcomes={valid_count}|strong_aligned={strong_count}"
    )
    print("WINDOW_ANCHOR_ALIGNMENT_ROWS")
    window_counts: Counter[str] = Counter()
    for window in windows:
        window_counts.update(
            _window_audit(
                window,
                events,
                sides,
                onsets,
                bars,
                ref_bars,
                min_move,
                min_efficiency,
            )
        )
    print("WINDOW_ALIGNMENT_AGGREGATES")
    for key, count in sorted(window_counts.items()):
        print(f"period={spec.code}|{key}={count}")
    assert sum(
        value for key, value in window_counts.items() if key.startswith("window_class:")
    ) == len(windows)
    print(f"period={spec.code}|broker_requests={probe.requests}")


def _synthetic_contracts() -> None:
    """Перевірити horizon semantics, gap та незалежність anchor."""
    from dataclasses import replace
    from datetime import UTC

    from core.workspace_market_event import WorkspaceMarketEvent
    from tests.runtime_temp import (
        run_algorithm_workspace_candidate_f_trend_coverage_2025_check as detector,
    )

    origin = datetime(2025, 1, 1, tzinfo=UTC)
    events = tuple(
        WorkspaceMarketEvent(
            timestamp=origin + BAR_INTERVAL * index,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
            bid=1.0 + index * 0.002,
            ask=1.0 + index * 0.002,
            spread=0.0,
            open=1.0 + index * 0.002,
            high=1.002 + index * 0.002,
            low=0.998 + index * 0.002,
            close=1.0 + index * 0.002,
            volume=0.0,
            source_mode="REPLAY",
        )
        for index in range(110)
    )
    initial_ref = _reference(events[:64])
    outcome = _outcome(events, 64, "BUY", initial_ref, 32, 8.0, 0.55)
    assert outcome.label == LABEL_ALIGNED
    assert outcome.first_gap_offset is None
    assert outcome.bars_available == 32
    # Майбутній gap не змінює момент anchor; лише статус оцінки.
    changed = list(events)
    changed[70] = replace(
        changed[70],
        timestamp=changed[70].timestamp + BAR_INTERVAL,
    )
    gap_result = _outcome(tuple(changed), 64, "BUY", initial_ref, 32, 8.0, 0.55)
    assert gap_result.label == LABEL_UNAVAILABLE
    assert gap_result.reason == "M15_GAP"
    assert gap_result.first_gap_offset == 6
    assert gap_result.bars_available == 6
    too_short = _outcome(events, 100, "BUY", initial_ref, 32, 8.0, 0.55)
    assert too_short.reason == "OUT_OF_RANGE"
    # Низька ефективність при достатній амплітуді — окрема причина.
    zigzag = list(events)
    for index in range(65, 96):
        close = float(events[64].close) + (index - 64) * 0.002
        if index % 2:
            close += 0.02
        zigzag[index] = replace(
            zigzag[index],
            open=close,
            high=close + 0.002,
            low=close - 0.002,
            close=close,
            bid=close,
            ask=close,
        )
    zigzag_outcome = _outcome(
        tuple(zigzag),
        64,
        "BUY",
        initial_ref,
        32,
        8.0,
        0.55,
    )
    assert zigzag_outcome.reason == "EFFICIENCY_BELOW"

    active_sides = {
        event.timestamp: "BUY" if 80 <= index <= 99 else None
        for index, event in enumerate(events)
    }
    onsets, onset_counts = _onsets(
        events,
        active_sides,
        32,
        64,
        8.0,
        0.55,
    )
    assert onset_counts["onsets_total"] == 1
    assert onset_counts["fate:SELECTED"] == 1
    source = _outcome(
        events,
        64,
        "BUY",
        initial_ref,
        32,
        8.0,
        0.55,
    )
    assert source.move_tr is not None and source.efficiency is not None
    window = detector.TrendWindow(
        start_index=64,
        end_index=95,
        direction="BUY",
        normalized_move=source.move_tr,
        path_efficiency=source.efficiency,
        score=source.move_tr * source.efficiency,
        net_move=events[95].close - events[64].close,
    )
    alignment = _window_audit(
        window,
        events,
        active_sides,
        onsets,
        32,
        64,
        8.0,
        0.55,
    )
    assert alignment["window_class:SELECTED_ONSET_IN_PRICE_WINDOW"] == 1
    assert alignment["selected_label:FORWARD_DATA_UNAVAILABLE_OR_GAP"] == 1
    assert alignment["first_active_after_window_start"] == 1
    print("SYNTHETIC_ANCHOR_OUTCOME_CONTRACT=OK")


def main() -> None:
    """Виміряти межі зіставлення без створення торгової гіпотези."""
    _bootstrap()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    _synthetic_contracts()
    before = _source_hashes()
    print("T112_07_CAUSAL_ANCHOR_OUTCOME_ALIGNMENT_ANATOMY")
    print("source_population=RM102_PRICE_ONLY_32_M15_WINDOWS")
    print("anchor=T112_05_FIRST_ALLIGATOR_ACTIVE_ONSET")
    print("sampling=UNCHANGED_CHRONOLOGICAL_32_BAR_EMBARGO")
    print("shadow_outcomes=EX_POST_DESCRIPTIVE_ONLY")
    print("thresholds=RM102_HISTORICAL_NOT_NEW_ENTRY_PARAMETERS")
    print("label_horizon=32_M15_BARS_FROM_EACH_ANCHOR")
    print("2026_period=PARTIAL_THROUGH_2026_08_25")
    for spec in PERIODS:
        _audit_period(spec)
    assert _source_hashes() == before
    print("SAFETY")
    print("test_id=T112-07")
    print("mode=RM112_T112_07_CAUSAL_ANCHOR_OUTCOME_ALIGNMENT_TEST_ONLY")
    print("ex_post_labels_used_for_entry=False")
    print("new_entry_rule_created=False")
    print("threshold_sweep_performed=False")
    print("trade_simulation_added=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_07_CAUSAL_ANCHOR_OUTCOME_ALIGNMENT_ANATOMY=OK")


if __name__ == "__main__":
    main()
