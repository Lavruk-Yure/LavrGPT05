# -*- coding: utf-8 -*-
"""T112-08 — причинні ACTIVE-можливості й негативні контролі.

TEST_ONLY. Усі моменти відбираються за completed-bar станом Alligator,
без знання майбутнього та без відбору за price-only ex-post трендами.
Після відбору до anchors додається RM102 32-bar ex-post мітка.
Перекривні результати не вважаються незалежними спостереженнями.
Нових входів, PnL, порогів і змін production немає.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workspace_market_event import WorkspaceMarketEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BAR_INTERVAL = timedelta(minutes=15)
PAST_FEATURE_BARS = 8
ANCHOR_CADENCE = 4  # TEST_ONLY: попередньо задана частота без оптимізації
MACD_CONTEXT_BARS = 16
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
    """Оцінка після 32 барів; не є інформацією для entry."""

    label: str
    reason: str
    move_tr: float | None
    efficiency: float | None
    first_gap_offset: int | None
    bars_available: int


@dataclass(frozen=True, slots=True)
class Anchor:
    """Незмінна causal частина і приєднаний лише ex-post результат."""

    index: int
    episode: int
    age: int
    direction: str
    past_move_tr: float
    past_efficiency: float
    past_aligned_steps: int
    alligator_opening: float | None
    macd_context: str
    outcome: Outcome


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


def _scheduled_ages(
    sides: tuple[str | None, ...], times: tuple[datetime, ...]
) -> tuple[tuple[int, int, int], ...]:
    """Часовий графік anchors: лише минулі ACTIVE стани і M15 timestamps."""
    assert len(sides) == len(times)
    scheduled: list[tuple[int, int, int]] = []
    previous_side: str | None = None
    previous_time: datetime | None = None
    episode = -1
    age = 0
    for index, (side, timestamp) in enumerate(zip(sides, times)):
        contiguous = (
            previous_time is not None and timestamp - previous_time == BAR_INTERVAL
        )
        if side is not None:
            if side != previous_side or not contiguous:
                episode += 1
                age = 0
            elif previous_side is not None:
                age += 1
            if age % ANCHOR_CADENCE == 0:
                scheduled.append((index, episode, age))
        previous_side = side
        previous_time = timestamp
    return tuple(scheduled)


def _features(
    events: tuple[WorkspaceMarketEvent, ...], index: int, side: str, reference: float
) -> tuple[float, float, int]:
    """Використати лише вісім попередніх completed M15 переходів."""
    assert index >= PAST_FEATURE_BARS and reference > 0.0
    sign = 1.0 if side == "BUY" else -1.0
    delta = float(events[index].close) - float(events[index - PAST_FEATURE_BARS].close)
    steps = tuple(
        float(events[pos].close) - float(events[pos - 1].close)
        for pos in range(index - PAST_FEATURE_BARS + 1, index + 1)
    )
    path = math.fsum(abs(step) for step in steps)
    return (
        sign * delta / reference,
        0.0 if path == 0.0 else sign * delta / path,
        sum(sign * step > 0.0 for step in steps),
    )


def _quality_lookup(quality: tuple, times: dict[datetime, int]) -> dict:
    """Індексувати фактичні MACD-діагностики за completed-bar часом."""
    result: dict = {}
    for direction in ("BUY", "SELL"):
        items = sorted(
            (
                (times[item.timestamp], item)
                for item in quality
                if item.direction == direction and item.timestamp in times
            ),
            key=lambda pair: pair[0],
        )
        result[direction] = (
            [index for index, _ in items],
            [item for _, item in items],
        )
    return result


def _quality_at(index: int, direction: str, lookup: dict) -> str:
    """Найновіший MACD quality, доступний не пізніше anchor."""
    indexes, rows = lookup[direction]
    position = bisect_right(indexes, index) - 1
    if position < 0 or index - indexes[position] > MACD_CONTEXT_BARS:
        return "NO_RECENT_ALIGNED_MACD_CROSS"
    return (
        "RECENT_MACD_PASS"
        if rows[position].final_quality_pass
        else "RECENT_MACD_REJECT"
    )


def _anchors(
    events: tuple[WorkspaceMarketEvent, ...],
    observations: tuple,
    quality: tuple,
    bars: int,
    reference_bars: int,
    min_move: float,
    min_efficiency: float,
) -> tuple[tuple[Anchor, ...], Counter[str]]:
    """Визначити популяцію до приєднання будь-якого future outcome."""
    from core.workspace_alligator import WorkspaceAlligatorObservation

    lookup = {item.timestamp: pos for pos, item in enumerate(events)}
    assert len(lookup) == len(events)
    by_time: dict[datetime, WorkspaceAlligatorObservation] = {}
    for item in observations:
        assert isinstance(item, WorkspaceAlligatorObservation)
        if item.timestamp in lookup:
            by_time[item.timestamp] = item
    sides = tuple(
        _active_side(by_time[event.timestamp]) if event.timestamp in by_time else None
        for event in events
    )
    indexes = _scheduled_ages(
        sides,
        tuple(event.timestamp for event in events),
    )
    macd = _quality_lookup(quality, lookup)
    candidates: list[tuple] = []
    counts: Counter[str] = Counter()
    counts["scheduled_all"] = len(indexes)
    for index, episode, age in indexes:
        side = sides[index]
        assert side is not None
        observation = by_time[events[index].timestamp]
        # Observation може бути використаний не раніше available_at.
        if observation.available_at > events[index].timestamp:
            counts["not_available_at_anchor"] += 1
            continue
        if index < reference_bars:
            counts["without_reference"] += 1
            continue
        if _first_gap(events, index - PAST_FEATURE_BARS, index) is not None:
            counts["past_8bar_gap"] += 1
            continue
        reference = _reference(events[index - reference_bars : index])
        if reference <= 0.0:
            counts["zero_reference"] += 1
            continue
        past_move, past_eff, past_steps = _features(
            events,
            index,
            side,
            reference,
        )
        quality_context = _quality_at(index, side, macd)
        # До цього рядка жодні future prices або ex-post labels не прочитано.
        candidates.append(
            (
                index,
                episode,
                age,
                side,
                reference,
                past_move,
                past_eff,
                past_steps,
                observation.normalized_opening,
                quality_context,
            )
        )
    counts["causal_candidates"] = len(candidates)
    anchors: list[Anchor] = []
    for (
        index,
        episode,
        age,
        side,
        reference,
        past_move,
        past_eff,
        past_steps,
        opening,
        quality_context,
    ) in candidates:
        outcome = _outcome(
            events,
            index,
            side,
            reference,
            bars,
            min_move,
            min_efficiency,
        )
        anchors.append(
            Anchor(
                index,
                episode,
                age,
                side,
                past_move,
                past_eff,
                past_steps,
                opening,
                quality_context,
                outcome,
            )
        )
        counts[f"label:{outcome.label}"] += 1
    assert sum(
        counts[f"label:{label}"]
        for label in (
            LABEL_ALIGNED,
            LABEL_OPPOSITE,
            LABEL_CONTROL,
            LABEL_UNAVAILABLE,
        )
    ) == len(anchors)
    return tuple(anchors), counts


def _quartiles(numbers: list[float]) -> str:
    """Описова статистика, без підбору predictive cutoff."""
    if not numbers:
        return "N/A"
    median = statistics.median(numbers)
    if len(numbers) < 4:
        return f"median:{median:.4f},q25:N/A,q75:N/A"
    quarters = statistics.quantiles(numbers, n=4, method="inclusive")
    return f"median:{median:.4f},q25:{quarters[0]:.4f}," f"q75:{quarters[2]:.4f}"


def _describe(period: str, anchors: tuple[Anchor, ...], counts: Counter[str]) -> None:
    """Показати positives і controls з одного prospective universe."""
    valid = tuple(item for item in anchors if item.outcome.label != LABEL_UNAVAILABLE)
    positive = tuple(item for item in valid if item.outcome.label == LABEL_ALIGNED)
    negative = tuple(item for item in valid if item.outcome.label != LABEL_ALIGNED)
    episodes = {item.episode for item in valid}
    print(
        f"period={period}|scheduled={counts['scheduled_all']}"
        f"|causal_candidates={len(anchors)}|valid_outcomes={len(valid)}"
        f"|positive={len(positive)}|controls={len(negative)}"
        f"|distinct_episodes={len(episodes)}"
    )
    for key in (
        "not_available_at_anchor",
        "without_reference",
        "past_8bar_gap",
        "zero_reference",
    ):
        print(f"period={period}|exclusion:{key}={counts[key]}")
    for label in (LABEL_ALIGNED, LABEL_OPPOSITE, LABEL_CONTROL, LABEL_UNAVAILABLE):
        print(f"period={period}|outcome:{label}={counts[f'label:{label}']}")
    for title, cohort in (("POSITIVE", positive), ("NEGATIVE_CONTROL", negative)):
        print(
            f"period={period}|cohort={title}|count={len(cohort)}"
            f"|episodes={len({item.episode for item in cohort})}"
        )
        for feature, values in (
            ("past_8bar_move_tr", [item.past_move_tr for item in cohort]),
            ("past_8bar_efficiency", [item.past_efficiency for item in cohort]),
            ("past_aligned_steps", [float(item.past_aligned_steps) for item in cohort]),
            (
                "alligator_opening",
                [
                    item.alligator_opening
                    for item in cohort
                    if item.alligator_opening is not None
                ],
            ),
        ):
            print(
                f"period={period}|cohort={title}|feature={feature}"
                f"|{_quartiles(values)}"
            )
        for context in (
            "RECENT_MACD_PASS",
            "RECENT_MACD_REJECT",
            "NO_RECENT_ALIGNED_MACD_CROSS",
        ):
            count = sum(item.macd_context == context for item in cohort)
            print(
                f"period={period}|cohort={title}"
                f"|macd_context={context}|count={count}"
            )
    print(
        f"period={period}|causal_cohort_status="
        + (
            "DESCRIPTIVE_BOTH_CLASSES_PRESENT"
            if positive and negative
            else "INCONCLUSIVE_MISSING_COHORT"
        )
    )
    # Перекривні 32-bar future labels корельовані: не незалежні кейси.
    print("overlap_warning=ANCHORS_WITHIN_EPISODE_NOT_INDEPENDENT")


def _price_window_overlap(
    events: tuple[WorkspaceMarketEvent, ...],
    anchors: tuple[Anchor, ...],
    windows: tuple,
    period: str,
) -> None:
    """Ex-post overlap з RM102 windows; не використовувати для відбору."""
    totals: Counter[str] = Counter()
    for window in windows:
        matched = [
            item
            for item in anchors
            if window.start_index <= item.index <= window.end_index
            and item.direction == window.direction
        ]
        if not matched:
            kind = "NO_CAUSAL_ANCHOR_IN_WINDOW"
        elif any(item.outcome.label == LABEL_ALIGNED for item in matched):
            kind = "HAS_FUTURE_POSITIVE_ANCHOR"
        else:
            kind = "ANCHORS_PRESENT_NONE_FUTURE_POSITIVE"
        totals[kind] += 1
        print(
            f"period={period}|window={events[window.start_index].timestamp}"
            f"|direction={window.direction}|class={kind}"
            f"|candidate_anchors={len(matched)}"
        )
    assert sum(totals.values()) == len(windows)
    for kind, count in sorted(totals.items()):
        print(f"period={period}|price_window:{kind}={count}")
    print("price_window_overlap=EX_POST_AUDIT_NOT_ANCHOR_SELECTOR")


def _audit_period(spec) -> None:
    """Запустити чинний Replay і відтворити всі базові лічильники."""
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
    assert algorithm.signal_filter is not None and algorithm.source is not None
    observations = tuple(algorithm.signal_filter.observations)
    quality = tuple(algorithm.source.quality_diagnostics)
    events_by_time = runtime.strategy_events
    events = tuple(events_by_time[time] for time in sorted(events_by_time))
    assert len(events) > 100
    assert len({item.timestamp for item in events}) == len(events)
    assert all(item.timeframe == "M15" for item in events)
    assert all(
        events[index - 1].timestamp < events[index].timestamp
        for index in range(1, len(events))
    )
    windows = detector.strongest_non_overlapping(
        detector.price_only_trend_candidates(events)
    )
    bars = detector.TREND_WINDOW_BARS
    ref_bars = detector.TREND_VOLATILITY_REFERENCE_BARS
    onset_counters = _historical_onsets(
        events,
        observations,
        bars,
        ref_bars,
        detector.TREND_MIN_NORMALIZED_MOVE,
        detector.TREND_MIN_PATH_EFFICIENCY,
    )
    expected = HISTORICAL_COUNTS[spec.code]
    assert (
        len(windows),
        onset_counters["onsets_total"],
        onset_counters["fate:SELECTED"],
        onset_counters["fate:SELECTED"]
        - onset_counters[f"outcome:{LABEL_UNAVAILABLE}"],
        onset_counters[f"outcome:{LABEL_ALIGNED}"],
    ) == expected, "Historical population contract diverged"
    anchors, counts = _anchors(
        events,
        observations,
        quality,
        bars,
        ref_bars,
        detector.TREND_MIN_NORMALIZED_MOVE,
        detector.TREND_MIN_PATH_EFFICIENCY,
    )
    print(f"period={spec.code}|baseline={baseline}")
    print(
        f"period={spec.code}|historical_price_windows={len(windows)}"
        f"|historical_active_onsets={onset_counters['onsets_total']}"
    )
    _describe(spec.code, anchors, counts)
    _price_window_overlap(events, anchors, windows, spec.code)
    print(f"period={spec.code}|broker_requests={probe.requests}")


def _historical_onsets(
    events: tuple[WorkspaceMarketEvent, ...],
    observations: tuple,
    bars: int,
    ref_bars: int,
    min_move: float,
    min_eff: float,
) -> Counter[str]:
    """Контракт числа T112-05 без приватних імпортів інших тестів."""
    from core.workspace_alligator import WorkspaceAlligatorObservation

    by_time = {
        item.timestamp: _active_side(item)
        for item in observations
        if isinstance(item, WorkspaceAlligatorObservation)
    }
    previous_side: str | None = None
    previous_time: datetime | None = None
    last_selected = -bars
    counts: Counter[str] = Counter()
    for index, event in enumerate(events):
        side = by_time.get(event.timestamp)
        gap = (
            previous_time is not None
            and event.timestamp - previous_time != BAR_INTERVAL
        )
        onset = side is not None and (side != previous_side or gap)
        previous_side = side
        previous_time = event.timestamp
        if not onset or side is None:
            continue
        counts["onsets_total"] += 1
        fate = "SELECTED"
        reference: float | None = None
        if index < ref_bars:
            fate = "WITHOUT_REFERENCE"
        elif index - last_selected < bars:
            fate = "EMBARGOED"
        elif _first_gap(events, index - PAST_FEATURE_BARS, index) is not None:
            fate = "PAST_8BAR_GAP"
        else:
            reference = _reference(events[index - ref_bars : index])
            if reference <= 0.0:
                fate = "ZERO_REFERENCE"
        if fate == "SELECTED":
            assert reference is not None and reference > 0.0
            last_selected = index
            outcome = _outcome(
                events,
                index,
                side,
                reference,
                bars,
                min_move,
                min_eff,
            )
            counts[f"outcome:{outcome.label}"] += 1
        counts[f"fate:{fate}"] += 1
    return counts


def _synthetic() -> None:
    """Розділити causal anchor від ex-post майбутнього та M15 gaps."""
    from dataclasses import replace

    from core.workspace_market_event import WorkspaceMarketEvent

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
        for index in range(112)
    )
    times = tuple(item.timestamp for item in events)
    sides = tuple("BUY" if 64 <= index <= 100 else None for index in range(len(events)))
    schedule = _scheduled_ages(sides, times)
    assert [index for index, _, _ in schedule] == list(range(64, 101, 4))
    assert all(age == index - 64 for index, _, age in schedule)
    modified = list(events)
    for index in range(65, len(events)):
        item = modified[index]
        # Майбутній рух не змінює вже обчислених causal ознак.
        modified[index] = replace(
            item,
            open=item.open - 0.001,
            high=item.high,
            low=item.low - 0.001,
            close=item.close - 0.001,
            bid=item.bid - 0.001,
            ask=item.ask - 0.001,
        )
    past = _reference(events[:64])
    assert _features(events, 64, "BUY", past) == _features(
        tuple(modified),
        64,
        "BUY",
        past,
    )
    original_outcome = _outcome(events, 64, "BUY", past, 32, 8.0, 0.55)
    assert original_outcome.label == LABEL_ALIGNED
    changed_time = list(times)
    changed_time[70] += timedelta(minutes=1)
    assert _scheduled_ages(sides, tuple(changed_time)) != schedule
    gap_events = list(events)
    gap_events[70] = replace(
        gap_events[70], timestamp=gap_events[70].timestamp + timedelta(minutes=1)
    )
    assert (
        _outcome(
            tuple(gap_events),
            64,
            "BUY",
            past,
            32,
            8.0,
            0.55,
        ).reason
        == "M15_GAP"
    )
    print("SYNTHETIC_CAUSAL_ANCHOR_NEGATIVE_CONTROL=OK")


def main() -> None:
    """Оцінити наступні 32 бари, не добираючи anchors за результатом."""
    _bootstrap()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    _synthetic()
    before = _source_hashes()
    print("T112_08_CAUSAL_OPPORTUNITY_FEASIBILITY_NEGATIVE_CONTROLS")
    print("anchor=ALL_ACTIVE_EPISODES_AGE_0_AND_EVERY_4_COMPLETED_M15")
    print("causality=NO_EX_POST_SELECTOR_8_PAST_BARS_ONLY")
    print("outcome=RM102_32_M15_FORWARD_EX_POST_ONLY")
    print("negative_control=SAME_ACTIVE_UNIVERSE_NON_POSITIVE_FUTURE")
    print("sampling=OVERLAPPING_FUTURES_NOT_INDEPENDENT")
    print("2026_period=PARTIAL_THROUGH_2026_08_25")
    for spec in PERIODS:
        _audit_period(spec)
    assert _source_hashes() == before
    print("SAFETY")
    print("test_id=T112-08")
    print("mode=RM112_T112_08_CAUSAL_OPPORTUNITY_NEGATIVE_CONTROLS_TEST_ONLY")
    print("ex_post_labels_used_for_entry=False")
    print("new_entry_rule_created=False")
    print("trade_simulation_added=False")
    print("threshold_sweep_performed=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_08_CAUSAL_OPPORTUNITY_NEGATIVE_CONTROLS=OK")


if __name__ == "__main__":
    main()
