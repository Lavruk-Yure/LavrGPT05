"""run_t108_11_unweighted_family_vote_anatomy_check.py — T108-11.

TEST_ONLY anatomy агрегує factual causal events GREEN T108-10 у три base
families: MACD, Alligator і Stochastic. Supertrend додається лише в окремий
control. Для P1..P5 кожне джерело зберігає напрям фіксовану кількість
completed M15 bars, включно з causal event bar; нова подія оновлює тільки
своє джерело. Узгоджені джерела дають family vote BUY/SELL, внутрішній
конфлікт завжди дає NEUTRAL, тому одна family не може мати кілька голосів.

На кожному decision bar, крім останнього без наступного completed bar,
runner описово вимірює one-bar-ahead HIGH/LOW outcome у causal signal-bar R.
Decision bar не входить у future window. Це не trading strategy: runner не
відкриває угод, не використовує NEXT_BAR_OPEN, SL/TP/PD, weights, threshold
selection, reverse logic або optimization і не змінює production чи MD7.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-11"
MODE = "RM108_T108_11_UNWEIGHTED_FAMILY_VOTE_ANATOMY_TEST_ONLY"
PERSISTENCE_SCRIPT = "run_t108_10_directional_signal_persistence_anatomy_check.py"
PERSISTENCES = (1, 2, 3, 4, 5)
BASE_SCORES = (-3, -2, -1, 0, 1, 2, 3)
CONTROL_SCORES = (-4, -3, -2, -1, 0, 1, 2, 3, 4)
BASE_ABS_SCORES = (1, 2, 3)
CONTROL_ABS_SCORES = (1, 2, 3, 4)
EPSILON = 1e-12

MACD_SOURCES = (
    "MACD_CROSS_EXTENDED_QUALITY",
    "MACD_RELATIVE_RESTART_DOMINANT_ACCELERATION",
)
ALLIGATOR_SOURCES = (
    "ALLIGATOR_ACTIVE_DIRECTION_START",
    "ALLIGATOR_FIRST_OPENING_EXPANSION",
    "ALLIGATOR_FORWARD_SHIFT_H1_PROJECTION_EVENT",
)
STOCHASTIC_SOURCE = "STOCHASTIC_KD_CROSS_14_1_3"
SUPERTREND_SOURCE = "SUPERTREND_DIRECTION_SWITCH_10_3"
ALL_SOURCES = (
    MACD_SOURCES
    + ALLIGATOR_SOURCES
    + (
        STOCHASTIC_SOURCE,
        SUPERTREND_SOURCE,
    )
)


def _load_persistence_module() -> ModuleType:
    """Завантажити GREEN T108-10 з явного canonical workspace path."""

    file_path = TEST_ROOT / PERSISTENCE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_11_persistence",
        file_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PERSISTENCE = _load_persistence_module()
PERIODS = getattr(PERSISTENCE, "PERIODS")
RUN_PERIOD: Callable[..., Any] = getattr(PERSISTENCE, "_run_period")
OUTCOME_METRICS: Callable[..., Any] = getattr(PERSISTENCE, "_metrics")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    PERSISTENCE,
    "_production_hashes",
)


@dataclass(frozen=True, slots=True)
class DirectionalOutcomeEvent:
    """Очікуваний напрям aggregated score на одному completed decision bar."""

    timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class DecisionRow:
    """Нормалізовані family votes і два unweighted scores одного bar."""

    timestamp: datetime
    macd_vote: int
    alligator_vote: int
    stochastic_vote: int
    supertrend_vote: int
    base_score: int
    control_score: int


@dataclass(frozen=True, slots=True)
class Coverage:
    """Family coverage і кількість активних base families."""

    macd: int
    alligator: int
    stochastic: int
    supertrend: int
    base_active_1: int
    base_active_2: int
    base_active_3: int


@dataclass(frozen=True, slots=True)
class Conflicts:
    """Overlap facts усередині multi-source MACD та Alligator families."""

    macd_same: int
    macd_conflicting: int
    alligator_same: int
    alligator_conflicting: int


@dataclass(frozen=True, slots=True)
class VariantResult:
    """Повний descriptive result одного period та fixed persistence."""

    rows: tuple[DecisionRow, ...]
    coverage: Coverage
    conflicts: Conflicts
    base_buckets: dict[int, Any]
    control_buckets: dict[int, Any]
    base_abs: dict[int, Any]
    control_abs: dict[int, Any]


def _event_indexes(replay: Any) -> dict[str, dict[int, int]]:
    """Перетворити factual timestamps T108-10 на source/index/direction map."""

    timestamp_indexes = {
        event.timestamp: index for index, event in enumerate(replay.events)
    }
    result: dict[str, dict[int, int]] = {}
    for source in ALL_SOURCES:
        indexed: dict[int, int] = {}
        for item in replay.families[source]:
            index = timestamp_indexes[item.timestamp]
            direction = 1 if item.direction == "BUY" else -1
            previous = indexed.get(index)
            assert previous is None or previous == direction
            indexed[index] = direction
        result[source] = indexed
    return result


def _family_vote(
    sources: tuple[str, ...],
    states: dict[str, tuple[int, int] | None],
    index: int,
) -> tuple[int, bool, bool]:
    """Дати максимум один vote; будь-який source conflict повертає zero."""

    active = [
        states[source][0]
        for source in sources
        if states[source] is not None and states[source][1] >= index
    ]
    if not active:
        return 0, False, False
    directions = set(active)
    overlap = len(active) >= 2
    if len(directions) != 1:
        return 0, False, overlap
    return active[0], overlap, False


def _decision_rows(
    replay: Any,
    persistence: int,
) -> tuple[tuple[DecisionRow, ...], Coverage, Conflicts]:
    """Побудувати causal Pn family states без читання наступного bar."""

    indexed = _event_indexes(replay)
    states: dict[str, tuple[int, int] | None] = {source: None for source in ALL_SOURCES}
    rows: list[DecisionRow] = []
    coverage_counter: Counter[str] = Counter()
    conflict_counter: Counter[str] = Counter()

    for index, event in enumerate(replay.events[:-1]):
        for source in ALL_SOURCES:
            state = states[source]
            if state is not None and state[1] < index:
                states[source] = None
            direction = indexed[source].get(index)
            if direction is not None:
                states[source] = (direction, index + persistence - 1)

        macd_vote, macd_same, macd_conflict = _family_vote(
            MACD_SOURCES,
            states,
            index,
        )
        alligator_vote, alligator_same, alligator_conflict = _family_vote(
            ALLIGATOR_SOURCES,
            states,
            index,
        )
        stochastic_vote, _, _ = _family_vote(
            (STOCHASTIC_SOURCE,),
            states,
            index,
        )
        supertrend_vote, _, _ = _family_vote(
            (SUPERTREND_SOURCE,),
            states,
            index,
        )
        base_score = macd_vote + alligator_vote + stochastic_vote
        control_score = base_score + supertrend_vote
        assert -3 <= base_score <= 3
        assert -4 <= control_score <= 4

        votes = (macd_vote, alligator_vote, stochastic_vote)
        active_base = sum(vote != 0 for vote in votes)
        coverage_counter["macd"] += macd_vote != 0
        coverage_counter["alligator"] += alligator_vote != 0
        coverage_counter["stochastic"] += stochastic_vote != 0
        coverage_counter["supertrend"] += supertrend_vote != 0
        coverage_counter[f"base_active_{active_base}"] += active_base > 0
        conflict_counter["macd_same"] += macd_same
        conflict_counter["macd_conflicting"] += macd_conflict
        conflict_counter["alligator_same"] += alligator_same
        conflict_counter["alligator_conflicting"] += alligator_conflict
        rows.append(
            DecisionRow(
                timestamp=event.timestamp,
                macd_vote=macd_vote,
                alligator_vote=alligator_vote,
                stochastic_vote=stochastic_vote,
                supertrend_vote=supertrend_vote,
                base_score=base_score,
                control_score=control_score,
            )
        )

    coverage = Coverage(
        macd=coverage_counter["macd"],
        alligator=coverage_counter["alligator"],
        stochastic=coverage_counter["stochastic"],
        supertrend=coverage_counter["supertrend"],
        base_active_1=coverage_counter["base_active_1"],
        base_active_2=coverage_counter["base_active_2"],
        base_active_3=coverage_counter["base_active_3"],
    )
    conflicts = Conflicts(
        macd_same=conflict_counter["macd_same"],
        macd_conflicting=conflict_counter["macd_conflicting"],
        alligator_same=conflict_counter["alligator_same"],
        alligator_conflicting=conflict_counter["alligator_conflicting"],
    )
    return tuple(rows), coverage, conflicts


def _score_events(
    rows: tuple[DecisionRow, ...],
    score_attribute: str,
    accepted: Callable[[int], bool],
) -> tuple[DirectionalOutcomeEvent, ...]:
    """Перетворити non-zero score bars на descriptive BUY/SELL labels."""

    result: list[DirectionalOutcomeEvent] = []
    for row in rows:
        score = int(getattr(row, score_attribute))
        if score == 0 or not accepted(score):
            continue
        direction = "BUY" if score > 0 else "SELL"
        result.append(DirectionalOutcomeEvent(row.timestamp, direction))
    return tuple(result)


def _bucket_metrics(
    replay: Any,
    rows: tuple[DecisionRow, ...],
    score_attribute: str,
    scores: tuple[int, ...],
) -> dict[int, Any]:
    """Порахувати one-bar outcomes для кожного signed score bucket."""

    result: dict[int, Any] = {}
    for score in scores:
        events = _score_events(
            rows,
            score_attribute,
            lambda value, target=score: value == target,
        )
        if score == 0:
            result[score] = len(
                [row for row in rows if int(getattr(row, score_attribute)) == 0]
            )
        else:
            result[score] = OUTCOME_METRICS(replay.events, events, 1)
    return result


def _absolute_metrics(
    replay: Any,
    rows: tuple[DecisionRow, ...],
    score_attribute: str,
    abs_scores: tuple[int, ...],
) -> dict[int, Any]:
    """Агрегувати signed directions за magnitude без threshold selection."""

    return {
        magnitude: OUTCOME_METRICS(
            replay.events,
            _score_events(
                rows,
                score_attribute,
                lambda value, target=magnitude: abs(value) == target,
            ),
            1,
        )
        for magnitude in abs_scores
    }


def _analyze_variant(replay: Any, persistence: int) -> VariantResult:
    """Зібрати coverage, conflicts, signed і absolute anatomy одного Pn."""

    rows, coverage, conflicts = _decision_rows(replay, persistence)
    return VariantResult(
        rows=rows,
        coverage=coverage,
        conflicts=conflicts,
        base_buckets=_bucket_metrics(replay, rows, "base_score", BASE_SCORES),
        control_buckets=_bucket_metrics(
            replay,
            rows,
            "control_score",
            CONTROL_SCORES,
        ),
        base_abs=_absolute_metrics(
            replay,
            rows,
            "base_score",
            BASE_ABS_SCORES,
        ),
        control_abs=_absolute_metrics(
            replay,
            rows,
            "control_score",
            CONTROL_ABS_SCORES,
        ),
    )


def _number(value: float | None) -> str:
    """Форматувати deterministic metric або NONE для порожнього bucket."""

    return "NONE" if value is None else f"{value:.4f}"


def _score_text(score: int) -> str:
    """Показати signed bucket з явним плюсом для додатного score."""

    return f"{score:+d}" if score > 0 else str(score)


def _metric_line(score: int, metric: Any) -> str:
    """Сформувати повний signed non-zero score bucket output."""

    return (
        f"score={_score_text(score)}|bars_count={metric.events}|"
        f"directional_success_count={metric.successes}|"
        f"directional_success_rate_percent={_number(metric.success_rate)}|"
        f"favorable_move_r_median={_number(metric.favorable_median)}|"
        f"adverse_move_r_median={_number(metric.adverse_median)}|"
        f"net_directional_edge_r_median={_number(metric.net_median)}"
    )


def _non_decreasing(values: list[float]) -> bool:
    """Перевірити лише factual adjacent magnitudes без tuning."""

    return all(right + EPSILON >= left for left, right in zip(values, values[1:]))


def _monotonicity(metrics: dict[int, Any]) -> tuple[bool, bool]:
    """Оцінити monotonicity на всіх непорожніх absolute buckets."""

    populated = [metrics[key] for key in sorted(metrics) if metrics[key].events]
    success = [float(item.success_rate) for item in populated]
    net = [float(item.net_median) for item in populated]
    return _non_decreasing(success), _non_decreasing(net)


def _distribution(metrics: dict[int, Any]) -> str:
    """Стиснути absolute-score populations в один deterministic рядок."""

    return ",".join(
        f"A{magnitude}:{metrics[magnitude].events}" for magnitude in sorted(metrics)
    )


def _overall_metric(
    replay: Any,
    result: VariantResult,
    score_attribute: str,
) -> Any:
    """Описати всі non-zero decision bars моделі без score selection."""

    events = _score_events(
        result.rows,
        score_attribute,
        lambda value: value != 0,
    )
    return OUTCOME_METRICS(replay.events, events, 1)


def _control_label(base: Any, control: Any) -> tuple[str, float, float]:
    """Дати descriptive improves/degrades/mixed за двома factual deltas."""

    assert base.success_rate is not None and base.net_median is not None
    assert control.success_rate is not None and control.net_median is not None
    success_delta = float(control.success_rate) - float(base.success_rate)
    net_delta = float(control.net_median) - float(base.net_median)
    if success_delta > EPSILON and net_delta > EPSILON:
        label = "improves"
    elif success_delta < -EPSILON and net_delta < -EPSILON:
        label = "degrades"
    else:
        label = "mixed"
    return label, success_delta, net_delta


def main() -> int:
    """Виконати T108-11 anatomy та зупинитися до будь-якого trading Replay."""

    before_hashes = PRODUCTION_HASHES()
    print("T108_11_UNWEIGHTED_FAMILY_VOTE_ANATOMY")
    replays: dict[str, Any] = {}
    results: dict[str, dict[int, VariantResult]] = {}
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        replay = RUN_PERIOD(spec)
        replays[spec.code] = replay
        results[spec.code] = {
            persistence: _analyze_variant(replay, persistence)
            for persistence in PERSISTENCES
        }
    assert PRODUCTION_HASHES() == before_hashes

    print("FAMILY_COVERAGE")
    for period in ("2025", "2026"):
        for persistence in PERSISTENCES:
            coverage = results[period][persistence].coverage
            print(
                f"period={period}|persistence=P{persistence}|"
                f"bars_with_macd_vote={coverage.macd}|"
                f"bars_with_alligator_vote={coverage.alligator}|"
                f"bars_with_stochastic_vote={coverage.stochastic}|"
                f"bars_with_supertrend_vote={coverage.supertrend}|"
                f"bars_with_1_active_base_family={coverage.base_active_1}|"
                f"bars_with_2_active_base_families={coverage.base_active_2}|"
                f"bars_with_3_active_base_families={coverage.base_active_3}"
            )

    print("FAMILY_CONFLICTS")
    for period in ("2025", "2026"):
        for persistence in PERSISTENCES:
            conflicts = results[period][persistence].conflicts
            print(
                f"period={period}|persistence=P{persistence}|family=MACD|"
                f"same_direction_overlap_count={conflicts.macd_same}|"
                f"conflicting_overlap_count={conflicts.macd_conflicting}"
            )
            print(
                f"period={period}|persistence=P{persistence}|family=ALLIGATOR|"
                f"same_direction_overlap_count={conflicts.alligator_same}|"
                f"conflicting_overlap_count={conflicts.alligator_conflicting}"
            )

    for section, model, scores, attribute in (
        ("BASE_SCORE_BUCKETS", "BASE", BASE_SCORES, "base_buckets"),
        ("CONTROL_SCORE_BUCKETS", "CONTROL", CONTROL_SCORES, "control_buckets"),
    ):
        print(section)
        for period in ("2025", "2026"):
            for persistence in PERSISTENCES:
                buckets = getattr(results[period][persistence], attribute)
                print(f"model={model}|period={period}|persistence=P{persistence}")
                for score in scores:
                    if score == 0:
                        print(f"score=0|bars_count={buckets[score]}")
                    else:
                        print(_metric_line(score, buckets[score]))

    print("ABS_SCORE_ANATOMY")
    for period in ("2025", "2026"):
        for persistence in PERSISTENCES:
            result = results[period][persistence]
            for model, metrics in (
                ("BASE", result.base_abs),
                ("CONTROL", result.control_abs),
            ):
                for magnitude in sorted(metrics):
                    item = metrics[magnitude]
                    print(
                        f"model={model}|period={period}|persistence=P{persistence}|"
                        f"abs_score={magnitude}|bars_count={item.events}|"
                        "directional_success_rate_percent="
                        f"{_number(item.success_rate)}|"
                        "net_directional_edge_r_median="
                        f"{_number(item.net_median)}"
                    )

    print("MONOTONICITY_CHECK")
    for period in ("2025", "2026"):
        for persistence in PERSISTENCES:
            result = results[period][persistence]
            for model, metrics in (
                ("BASE", result.base_abs),
                ("CONTROL", result.control_abs),
            ):
                success, net = _monotonicity(metrics)
                print(
                    f"model={model}|period={period}|persistence=P{persistence}|"
                    f"success_rate_monotonic_non_decreasing={success}|"
                    f"net_edge_monotonic_non_decreasing={net}"
                )

    print("CROSS_PERIOD_STABILITY")
    for persistence in PERSISTENCES:
        for model, attribute in (
            ("BASE", "base_abs"),
            ("CONTROL", "control_abs"),
        ):
            left = getattr(results["2025"][persistence], attribute)
            right = getattr(results["2026"][persistence], attribute)
            for magnitude in sorted(left):
                left_item = left[magnitude]
                right_item = right[magnitude]
                print(
                    f"persistence=P{persistence}|model={model}|"
                    f"abs_score={magnitude}|2025_bars={left_item.events}|"
                    f"2025_success_rate={_number(left_item.success_rate)}|"
                    f"2025_net_edge={_number(left_item.net_median)}|"
                    f"2026_bars={right_item.events}|"
                    f"2026_success_rate={_number(right_item.success_rate)}|"
                    f"2026_net_edge={_number(right_item.net_median)}"
                )

    print("SUPERTREND_CONTROL_COMPARISON")
    for period in ("2025", "2026"):
        replay = replays[period]
        for persistence in PERSISTENCES:
            result = results[period][persistence]
            base = _overall_metric(replay, result, "base_score")
            control = _overall_metric(replay, result, "control_score")
            label, success_delta, net_delta = _control_label(base, control)
            print(
                f"period={period}|persistence=P{persistence}|"
                f"base_abs_distribution={_distribution(result.base_abs)}|"
                f"base_success_rate={_number(base.success_rate)}|"
                f"base_net_edge={_number(base.net_median)}|"
                "control_abs_distribution="
                f"{_distribution(result.control_abs)}|"
                f"control_success_rate={_number(control.success_rate)}|"
                f"control_net_edge={_number(control.net_median)}|"
                f"success_rate_delta={success_delta:+.4f}|"
                f"net_edge_delta={net_delta:+.4f}|"
                f"descriptive_label={label}"
            )

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=COMPLETED_M15_SCORE_DECISION_BARS")
    print("family_normalization=True")
    print("max_one_vote_per_family=True")
    print("weights_used=False")
    print("score_threshold_selected=False")
    print("best_persistence_selected=False")
    print("decision_bar_in_future_window=False")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("optimization_performed=False")
    print("threshold_sweep_performed=False")
    print("counterfactual_trades_simulated=False")
    print("next_bar_open_execution_simulated=False")
    print("sl_tp_pd_simulated=False")
    print("new_entry_rule_created=False")
    print("new_exit_rule_created=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={sum(item.broker_requests for item in replays.values())}")
    print(
        "broker_execution_attempted="
        f"{any(item.broker_execution_attempted for item in replays.values())}"
    )
    print("T108_11_UNWEIGHTED_FAMILY_VOTE_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
