# -*- coding: utf-8 -*-
"""T112-05 — незалежні causal opportunities і негативні контрприклади.

TEST_ONLY. Opportunity фіксує тільки підтверджений Alligator ACTIVE на
завершеному M15-барі. Ознаки використовують цей та попередні бари.
Майбутні 32 бари використовуються виключно для ex-post outcome label.
Контрольні випадки беруться з тієї самої сукупності ACTIVE opportunities.
Ні торгової стратегії, ні підбору порогів, ні counterfactual PnL тут немає.
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
TEST_ID = "T112-05"
MODE = "RM112_T112_05_CAUSAL_CONTINUATION_OPPORTUNITY_ANATOMY_TEST_ONLY"
BAR_INTERVAL = timedelta(minutes=15)
PAST_FEATURE_BARS = 8
MACD_CONTEXT_BARS = 16
BASELINE_TOLERANCE = 0.005
OUTCOME_ALIGNED = "FORWARD_STRONG_ALIGNED"
OUTCOME_OPPOSITE = "FORWARD_STRONG_OPPOSITE"
OUTCOME_CONTROL = "CONTROL_NO_STRONG_ALIGNED_TREND"
OUTCOME_UNAVAILABLE = "FORWARD_DATA_UNAVAILABLE_OR_GAP"


@dataclass(frozen=True, slots=True)
class CausalOpportunity:
    """Causal snapshot із відкладеною лише для оцінки outcome-міткою."""

    timestamp: datetime
    direction: str
    past_move_tr: float
    past_efficiency: float
    past_aligned_steps: int
    active_opening: float | None
    active_slope: float | None
    macd_context: str
    outcome: str
    future_move_tr: float | None
    future_efficiency: float | None


def _bootstrap() -> None:
    """Підтримати прямий запуск tests/roadmap112 без зміни PYTHONPATH."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _source_hashes() -> dict[str, str]:
    """Контроль незмінності production, MD7 і активної локалізації."""
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
    """Взяти незмінний WSP із frozen OOS та canonical PD=35%."""
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
    """Перевірити незмінний entry/exit за чинним regression contract."""
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
    assert summary.close_reason_count("SESSION_END") == 0
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},be:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )


def _active_side(observation) -> str | None:
    """Дозволити тільки напрям підтвердженого production ACTIVE."""
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


def _contiguous(events: tuple[WorkspaceMarketEvent, ...], start: int, end: int) -> bool:
    """Перевірити кожний M15 перехід у включному діапазоні."""
    return all(
        events[index].timestamp - events[index - 1].timestamp == BAR_INTERVAL
        for index in range(start + 1, end + 1)
    )


def _reference_tr(events: tuple[WorkspaceMarketEvent, ...]) -> float:
    """Той самий median true range, що у RM102 price-only detector."""
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


def _causal_features(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    direction: str,
    reference_tr: float,
) -> tuple[float, float, int]:
    """Тільки bars[index-8:index+1], без читання future bars."""
    assert index >= PAST_FEATURE_BARS and reference_tr > 0.0
    sign = 1.0 if direction == "BUY" else -1.0
    delta = float(events[index].close) - float(events[index - PAST_FEATURE_BARS].close)
    steps = [
        float(events[pos].close) - float(events[pos - 1].close)
        for pos in range(index - PAST_FEATURE_BARS + 1, index + 1)
    ]
    total_path = math.fsum(abs(step) for step in steps)
    return (
        sign * delta / reference_tr,
        0.0 if total_path == 0.0 else sign * delta / total_path,
        sum(sign * step > 0.0 for step in steps),
    )


def _forward_label(
    events: tuple[WorkspaceMarketEvent, ...],
    index: int,
    direction: str,
    reference_tr: float,
    bars: int,
    min_move: float,
    min_efficiency: float,
) -> tuple[str, float | None, float | None]:
    """Ex-post outcome, жодного використання для моменту opportunity."""
    end = index + bars - 1
    if end >= len(events) or not _contiguous(events, index, end):
        return OUTCOME_UNAVAILABLE, None, None
    sign = 1.0 if direction == "BUY" else -1.0
    delta = float(events[end].close) - float(events[index].close)
    path = math.fsum(
        abs(float(events[pos].close) - float(events[pos - 1].close))
        for pos in range(index + 1, end + 1)
    )
    normalized = sign * delta / reference_tr
    efficiency = 0.0 if path == 0.0 else abs(delta) / path
    if abs(normalized) >= min_move and efficiency >= min_efficiency:
        outcome = OUTCOME_ALIGNED if normalized > 0.0 else OUTCOME_OPPOSITE
    else:
        outcome = OUTCOME_CONTROL
    return outcome, normalized, efficiency


def _quality_context(
    index: int, direction: str, diagnostics: dict, indexes: dict, max_age: int
) -> str:
    """Останній MACD quality event не пізніше поточного completed bar."""
    times, items = diagnostics[direction]
    position = bisect_right(times, index) - 1
    if position < 0 or index - times[position] > max_age:
        return "NO_RECENT_ALIGNED_MACD_CROSS"
    item = items[position]
    assert indexes.get(item.timestamp, -1) == times[position]
    return "RECENT_MACD_PASS" if item.final_quality_pass else "RECENT_MACD_REJECT"


def _construct_opportunities(
    events: tuple[WorkspaceMarketEvent, ...],
    observations: tuple,
    quality: tuple,
    bars: int,
    reference_bars: int,
    min_move: float,
    min_efficiency: float,
) -> tuple[tuple[CausalOpportunity, ...], Counter[str]]:
    """Вибір anchor до outcome; embargo не залежить від майбутньої ціни."""
    assert bars >= 2 and reference_bars >= PAST_FEATURE_BARS
    lookup = {event.timestamp: index for index, event in enumerate(events)}
    assert len(lookup) == len(events)
    observation_by_index = {
        lookup[item.timestamp]: item
        for item in observations
        if item.timestamp in lookup
    }
    quality_context: dict = {}
    for direction in ("BUY", "SELL"):
        pairs = sorted(
            (
                (lookup[item.timestamp], item)
                for item in quality
                if item.direction == direction and item.timestamp in lookup
            ),
            key=lambda pair: pair[0],
        )
        quality_context[direction] = (
            [index for index, _ in pairs],
            [item for _, item in pairs],
        )
    counters: Counter[str] = Counter()
    opportunities: list[CausalOpportunity] = []
    last_selected = -bars
    previous_side: str | None = None
    previous_timestamp: datetime | None = None
    for index, event in enumerate(events):
        observation = observation_by_index.get(index)
        side = _active_side(observation) if observation is not None else None
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
        if index < reference_bars:
            counters["onsets_without_reference"] += 1
            continue
        if index - last_selected < bars:
            counters["onsets_embargoed"] += 1
            continue
        # Ознаки беруть останні 8 безперервних завершених M15-барів.
        # RM102 не вимагає суцільності 64 попередніх reference-барів.
        if not _contiguous(events, index - PAST_FEATURE_BARS, index):
            counters["onsets_with_past_8bar_gap"] += 1
            continue
        reference_start = index - reference_bars
        if not _contiguous(events, reference_start, index):
            counters["selected_reference_64bar_with_gap"] += 1
        reference = _reference_tr(events[reference_start:index])
        if reference <= 0.0:
            counters["onsets_zero_reference"] += 1
            continue
        assert observation is not None
        assert observation.timestamp <= observation.available_at
        past_move, past_eff, aligned_steps = _causal_features(
            events,
            index,
            side,
            reference,
        )
        context = _quality_context(
            index,
            side,
            quality_context,
            lookup,
            MACD_CONTEXT_BARS,
        )
        # Відбір anchor не залежить від label; навіть gap outcome лишається
        # облікованим, а не зникає заднім числом із сукупності.
        last_selected = index
        label, future_move, future_eff = _forward_label(
            events,
            index,
            side,
            reference,
            bars,
            min_move,
            min_efficiency,
        )
        if label == OUTCOME_UNAVAILABLE:
            if index + bars - 1 >= len(events):
                counters["forward_out_of_range"] += 1
            else:
                counters["forward_has_m15_gap"] += 1
        opportunities.append(
            CausalOpportunity(
                timestamp=observation.available_at,
                direction=side,
                past_move_tr=past_move,
                past_efficiency=past_eff,
                past_aligned_steps=aligned_steps,
                active_opening=observation.normalized_opening,
                active_slope=observation.normalized_slope,
                macd_context=context,
                outcome=label,
                future_move_tr=future_move,
                future_efficiency=future_eff,
            )
        )
        counters[f"label:{label}"] += 1
    assert counters["active_onsets_total"] >= len(opportunities)
    assert sum(
        counters[f"label:{label}"]
        for label in (
            OUTCOME_ALIGNED,
            OUTCOME_OPPOSITE,
            OUTCOME_CONTROL,
            OUTCOME_UNAVAILABLE,
        )
    ) == len(opportunities)
    return tuple(opportunities), counters


def _summary(values: list[float]) -> str:
    """Суто описова медіана/IQR, без оптимізації та significance claims."""
    if not values:
        return "N/A"
    values = sorted(values)
    median = statistics.median(values)
    if len(values) < 4:
        return f"median:{median:.4f},iqr:INSUFFICIENT_N"
    quarters = statistics.quantiles(values, n=4, method="inclusive")
    return f"median:{median:.4f},q25:{quarters[0]:.4f}," f"q75:{quarters[2]:.4f}"


def _report(
    period: str, opportunities: tuple[CausalOpportunity, ...], counters: Counter[str]
) -> None:
    """Окремо надрукувати позитивні й негативні групи та MACD контекст."""
    print(f"period={period}|active_onsets={counters['active_onsets_total']}")
    for key in (
        "onsets_without_reference",
        "onsets_embargoed",
        "onsets_with_past_8bar_gap",
        "onsets_zero_reference",
        "selected_reference_64bar_with_gap",
        "forward_has_m15_gap",
        "forward_out_of_range",
    ):
        print(f"period={period}|{key}={counters[key]}")
    print(f"period={period}|causal_anchors={len(opportunities)}")
    valid = [row for row in opportunities if row.outcome != OUTCOME_UNAVAILABLE]
    positives = sum(row.outcome == OUTCOME_ALIGNED for row in valid)
    controls = len(valid) - positives
    cohort_status = (
        "DESCRIPTIVE_COHORTS_PRESENT"
        if positives and controls
        else "INCONCLUSIVE_MISSING_COHORT"
    )
    print(f"period={period}|valid_outcomes={len(valid)}")
    print(f"period={period}|positive_count={positives}|control_count={controls}")
    print(f"period={period}|cohort_status={cohort_status}")
    for label in (
        OUTCOME_ALIGNED,
        OUTCOME_OPPOSITE,
        OUTCOME_CONTROL,
        OUTCOME_UNAVAILABLE,
    ):
        group = [row for row in opportunities if row.outcome == label]
        print(f"period={period}|outcome={label}|count={len(group)}")
        if label == OUTCOME_UNAVAILABLE:
            continue
        for name, values in (
            ("past_8bar_move_tr", [row.past_move_tr for row in group]),
            ("past_8bar_efficiency", [row.past_efficiency for row in group]),
            (
                "past_8bar_aligned_steps",
                [float(row.past_aligned_steps) for row in group],
            ),
            (
                "alligator_opening_context",
                [
                    float(row.active_opening)
                    for row in group
                    if row.active_opening is not None
                ],
            ),
        ):
            print(
                f"period={period}|outcome={label}|feature={name}" f"|{_summary(values)}"
            )
        for context in (
            "RECENT_MACD_PASS",
            "RECENT_MACD_REJECT",
            "NO_RECENT_ALIGNED_MACD_CROSS",
        ):
            count = sum(row.macd_context == context for row in group)
            print(
                f"period={period}|outcome={label}"
                f"|macd_context={context}|count={count}"
            )
    print("INFERENCE=DESCRIPTIVE_ONLY_NO_ENTRY_CANDIDATE_NO_PNL")


def _synthetic_contract() -> None:
    """Довести, що майбутні дані не змінюють causal ознаки."""
    from core.workspace_market_event import WorkspaceMarketEvent

    def bar_at(
        timestamp: datetime,
        close: float,
        high: float,
        low: float,
    ) -> WorkspaceMarketEvent:
        """Збудувати валідний M15 Replay event для контрольного тесту."""
        bid = close - 0.00002
        ask = close + 0.00002
        return WorkspaceMarketEvent(
            timestamp=timestamp,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
            bid=bid,
            ask=ask,
            spread=ask - bid,
            open=close,
            high=high,
            low=low,
            close=close,
            volume=1.0,
            source_mode="REPLAY",
        )

    begin = datetime(2025, 1, 6, tzinfo=UTC)
    base = tuple(
        bar_at(
            timestamp=begin + BAR_INTERVAL * index,
            close=1.0 + index * 0.00001,
            high=1.0 + index * 0.00001 + 0.00005,
            low=1.0 + index * 0.00001 - 0.00005,
        )
        for index in range(110)
    )
    anchor = 64
    reference = _reference_tr(base[:anchor])
    original = _causal_features(base, anchor, "BUY", reference)
    modified = list(base)
    for index in range(anchor + 1, len(base)):
        current = modified[index]
        new_close = current.close + 0.001 * (index - anchor)
        modified[index] = bar_at(
            timestamp=current.timestamp,
            close=new_close,
            high=max(current.high, new_close) + 0.00005,
            low=min(current.low, new_close) - 0.00005,
        )
    changed = tuple(modified)
    assert _causal_features(changed, anchor, "BUY", reference) == original
    before_label = _forward_label(base, anchor, "BUY", reference, 32, 8.0, 0.55)
    after_label = _forward_label(changed, anchor, "BUY", reference, 32, 8.0, 0.55)
    assert before_label != after_label
    assert after_label[0] == OUTCOME_ALIGNED
    opposite = list(base)
    for index in range(anchor + 1, len(base)):
        current = opposite[index]
        new_close = current.close - 0.001 * (index - anchor)
        opposite[index] = bar_at(
            timestamp=current.timestamp,
            close=new_close,
            high=max(current.high, new_close) + 0.00005,
            low=min(current.low, new_close) - 0.00005,
        )
    assert (
        _forward_label(
            tuple(opposite),
            anchor,
            "BUY",
            reference,
            32,
            8.0,
            0.55,
        )[0]
        == OUTCOME_OPPOSITE
    )
    assert _contiguous(base, anchor, anchor + 31)
    gap_bars = list(base)
    current = gap_bars[anchor + 10]
    gap_bars[anchor + 10] = bar_at(
        timestamp=current.timestamp + timedelta(minutes=1),
        close=current.close,
        high=current.high,
        low=current.low,
    )
    assert (
        _forward_label(
            tuple(gap_bars),
            anchor,
            "BUY",
            reference,
            32,
            8.0,
            0.55,
        )[0]
        == OUTCOME_UNAVAILABLE
    )
    assert (
        _causal_features(
            tuple(gap_bars),
            anchor,
            "BUY",
            reference,
        )
        == original
    )
    # Контракт RM102: 64 reference-бари можуть перетинати ринковий gap,
    # але 8 барів causal features мають лишатися строго безперервними.
    reference_gap_bars = list(base)
    past_index = anchor - 20
    past_event = reference_gap_bars[past_index]
    reference_gap_bars[past_index] = bar_at(
        timestamp=past_event.timestamp + timedelta(minutes=1),
        close=past_event.close,
        high=past_event.high,
        low=past_event.low,
    )
    reference_gap_events = tuple(reference_gap_bars)
    assert not _contiguous(reference_gap_events, anchor - 64, anchor)
    assert _contiguous(reference_gap_events, anchor - 8, anchor)
    assert (
        _causal_features(
            reference_gap_events,
            anchor,
            "BUY",
            reference,
        )
        == original
    )
    assert (
        _forward_label(base, 109, "BUY", reference, 32, 8.0, 0.55)[0]
        == OUTCOME_UNAVAILABLE
    )


def _run_period(spec) -> Counter[str]:
    """Один чинний Replay; outcome label — лише після його завершення."""
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
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    assert algorithm.signal_filter is not None and algorithm.source is not None
    observations = tuple(algorithm.signal_filter.observations)
    quality = tuple(algorithm.source.quality_diagnostics)
    events_by_time = runtime.strategy_events
    events = tuple(events_by_time[time] for time in sorted(events_by_time))
    assert len(events) > 100
    assert len({event.timestamp for event in events}) == len(events)
    assert all(event.timeframe == "M15" for event in events)
    assert all(
        events[index].timestamp > events[index - 1].timestamp
        for index in range(1, len(events))
    )
    opportunities, counters = _construct_opportunities(
        events,
        observations,
        quality,
        detector.TREND_WINDOW_BARS,
        detector.TREND_VOLATILITY_REFERENCE_BARS,
        detector.TREND_MIN_NORMALIZED_MOVE,
        detector.TREND_MIN_PATH_EFFICIENCY,
    )
    print(f"period={spec.code}|baseline={baseline}")
    _report(spec.code, opportunities, counters)
    print(f"period={spec.code}|broker_requests={probe.requests}")
    return counters


def main() -> None:
    """Порівняти all ACTIVE onset opportunities з ex-post outcome controls."""
    _bootstrap()
    from tests.runtime_workspace.run_t105_10_pd_35_production_regression_check import (
        PERIODS,
    )

    _synthetic_contract()
    before = _source_hashes()
    print("T112_05_CAUSAL_CONTINUATION_OPPORTUNITY_ANATOMY")
    print("anchor=FIRST_CAUSAL_ALLIGATOR_ACTIVE_BAR_PER_CONTIGUOUS_EPISODE")
    print("sampling=CHRONOLOGICAL_32_BAR_EMBARGO_BEFORE_OUTCOME_LABEL")
    print("causal_features=STRICT_PAST_8_COMPLETED_M15_BARS")
    print("reference=PAST_64_COMPLETED_BARS_GAPS_ALLOWED_AS_IN_RM102")
    print("macd_context=LAST_ALIGNED_QUALITY_AT_OR_BEFORE_ANCHOR_MAX_16_BARS")
    print("outcome=FUTURE_32_M15_PRICE_ONLY_EX_POST_LABEL_NOT_ENTRY")
    print("control=ALL_NON_STRONG_ALIGNED_OUTCOMES_IN_SAME_ACTIVE_UNIVERSE")
    print("future_gaps=REPORTED_UNAVAILABLE_NOT_DROPPED_SILENTLY")
    print("period_2026=PARTIAL_THROUGH_2026_08_25")
    print("historical_rm102_thresholds=DESCRIPTIVE_NOT_PRODUCTION_PARAMETERS")
    totals: Counter[str] = Counter()
    for spec in PERIODS:
        totals.update(_run_period(spec))
    assert _source_hashes() == before
    print("AGGREGATE_COHORT_COUNTS")
    for key, count in sorted(totals.items()):
        print(f"metric={key}|count={count}")
    valid = sum(
        totals[f"label:{label}"]
        for label in (OUTCOME_ALIGNED, OUTCOME_OPPOSITE, OUTCOME_CONTROL)
    )
    print(f"aggregate_valid_outcomes={valid}")
    assert valid > 0, "No valid ex-post outcomes: research inconclusive"
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("ex_post_labels_used_for_entry=False")
    print("new_entry_rule_created=False")
    print("trade_simulation_added=False")
    print("threshold_sweep_performed=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_05_CAUSAL_CONTINUATION_OPPORTUNITY_ANATOMY=OK")


if __name__ == "__main__":
    main()
