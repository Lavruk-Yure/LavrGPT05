"""run_t108_20_macd_weak_reject_internal_temporal_geometry_anatomy_check.py.

T108-20 є TEST_ONLY anatomy factual ``MACD_EXTREMUM_TOO_WEAK`` rejects
усередині causal STRONG Alligator segments. Runner повторно використовує
canonical T108-08/T108-19 Replay population та незмінний residual-move label,
а causal features читає лише з production MACD diagnostic на reject bar або
з уже завершеної M15 chronology цього самого segment.

Звіт розділяє 2025/2026 і три наперед визначені outcome groups, показує
distribution та IQR overlap для доступної extremum/cross geometry, temporal
ages і reject clustering. Ordinal bins FIRST/SECOND/THIRD_PLUS фіксовані до
outcome. Future residual move не є feature. Runner не створює threshold,
classifier, score, weights, trades, entry/exit/reverse logic і не змінює
production чи MD7.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, median
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-20"
MODE = "RM108_T108_20_MACD_WEAK_REJECT_INTERNAL_TEMPORAL_GEOMETRY_ANATOMY_TEST_ONLY"
SOURCE_SCRIPT = "run_t108_19_dominant_reject_conditional_evidence_anatomy_check.py"
EXPECTED_COUNTS = {"2025": 136, "2026": 96}
PERIOD_CODES = ("2025", "2026")
OUTCOME_GROUPS = ("REACHED_2R", "REACHED_1R_ONLY", "BELOW_1R")
ORDINAL_BINS = ("FIRST", "SECOND", "THIRD_PLUS")
MINIMUM_OUTCOME_GROUP_SIZE = 10
EPSILON = 1e-12

FEATURES = (
    "extremum_prominence",
    "prominence_ratio",
    "extremum_distance",
    "normalized_distance",
    "extremum_to_cross_age",
    "cross_to_reject_age",
    "extremum_to_reject_age",
    "histogram_before_cross",
    "histogram_on_cross",
    "crossover_steepness",
    "crossover_steepness_per_minute",
    "macd_slope_per_minute",
    "signal_slope_per_minute",
    "effective_angle_degrees",
    "reject_ordinal",
    "prior_weak_rejects",
    "elapsed_bars_from_first_weak_reject",
)


def _load_source_module() -> ModuleType:
    """Завантажити GREEN T108-19 з canonical workspace path."""

    file_path = TEST_ROOT / SOURCE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_20_source",
        file_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = _load_source_module()
PERIODS = getattr(SOURCE, "PERIODS")
RUN_WITH_RUNTIME: Callable[..., tuple[Any, Any]] = getattr(
    SOURCE,
    "_run_with_runtime",
)
PRODUCTION_HASHES: Callable[[], Any] = getattr(SOURCE, "PRODUCTION_HASHES")
BROKER_EXECUTION_ATTEMPTED: Callable[[Any], bool] = getattr(
    SOURCE,
    "BROKER_EXECUTION_ATTEMPTED",
)


@dataclass(frozen=True, slots=True)
class AnatomyRow:
    """Causal internal features та окремі post-hoc outcome labels reject-а."""

    period: str
    segment_start: datetime
    timestamp: datetime
    direction: str
    residual_move_r: float
    values: dict[str, float]

    @property
    def reached_1r(self) -> bool:
        """Чи post-hoc residual move досяг factual 1R label."""

        return self.residual_move_r + EPSILON >= 1.0

    @property
    def reached_2r(self) -> bool:
        """Чи post-hoc residual move досяг factual 2R label."""

        return self.residual_move_r + EPSILON >= 2.0

    @property
    def outcome_group(self) -> str:
        """Повернути одну з трьох наперед визначених outcome populations."""

        if self.reached_2r:
            return "REACHED_2R"
        if self.reached_1r:
            return "REACHED_1R_ONLY"
        return "BELOW_1R"


@dataclass(frozen=True, slots=True)
class Distribution:
    """Descriptive seven-number summary factual continuous feature."""

    count: int
    minimum: float | None
    q1: float | None
    median_value: float | None
    q3: float | None
    maximum: float | None
    mean_value: float | None


def _diagnostic_map(runtime: Any) -> dict[tuple[datetime, str], Any]:
    """Зіставити factual weak rejects із production diagnostic records."""

    algorithm = runtime.algorithm
    source = algorithm.source
    assert source is not None
    result = {
        (item.timestamp, item.direction): item
        for item in source.quality_diagnostics
        if item.reason_code == "MACD_EXTREMUM_TOO_WEAK"
    }
    assert len(result) == sum(
        item.reason_code == "MACD_EXTREMUM_TOO_WEAK"
        for item in source.quality_diagnostics
    )
    return result


def _thresholds(runtime: Any) -> tuple[float, float]:
    """Прочитати незмінні production prominence/distance thresholds."""

    source = runtime.algorithm.source
    assert source is not None
    prominence = float(source.extremum_min_prominence)
    distance = float(source.extremum_to_cross_min_distance)
    assert prominence > 0.0 and distance > 0.0
    return prominence, distance


def _causal_cluster_values(
    source_rows: tuple[Any, ...],
    event_indexes: dict[datetime, int],
) -> dict[tuple[datetime, str], tuple[int, int, int]]:
    """Побудувати ordinal/prior/elapsed лише з already-observed rejects."""

    counts: Counter[tuple[datetime, str]] = Counter()
    first_timestamp: dict[tuple[datetime, str], datetime] = {}
    result: dict[tuple[datetime, str], tuple[int, int, int]] = {}
    for row in sorted(source_rows, key=lambda item: item.signal_timestamp):
        segment_key = (row.segment_start, row.direction)
        prior = counts[segment_key]
        if prior == 0:
            first_timestamp[segment_key] = row.signal_timestamp
        elapsed = (
            event_indexes[row.signal_timestamp]
            - event_indexes[first_timestamp[segment_key]]
        )
        result[(row.signal_timestamp, row.direction)] = (
            prior + 1,
            prior,
            elapsed,
        )
        counts[segment_key] += 1
    assert len(result) == len(source_rows)
    return result


def _rows(period: str, result: Any, runtime: Any) -> tuple[AnatomyRow, ...]:
    """Зібрати доступні causal fields без future reconstruction."""

    diagnostics = _diagnostic_map(runtime)
    prominence_threshold, distance_threshold = _thresholds(runtime)
    event_indexes = {
        timestamp: index
        for index, timestamp in enumerate(sorted(runtime.strategy_events))
    }
    cluster_values = _causal_cluster_values(result.rows, event_indexes)
    rows: list[AnatomyRow] = []
    for source_row in result.rows:
        key = (source_row.signal_timestamp, source_row.direction)
        diagnostic = diagnostics[key]
        assert diagnostic.extremum_timestamp is not None
        assert diagnostic.extremum_prominence is not None
        assert diagnostic.extremum_to_cross_distance is not None
        extremum_age = (
            event_indexes[diagnostic.timestamp]
            - event_indexes[diagnostic.extremum_timestamp]
        )
        assert extremum_age > 0
        ordinal, prior, elapsed = cluster_values[key]
        prominence = float(diagnostic.extremum_prominence)
        distance = float(diagnostic.extremum_to_cross_distance)
        values = {
            "extremum_prominence": prominence,
            "prominence_ratio": prominence / prominence_threshold,
            "extremum_distance": distance,
            "normalized_distance": distance / distance_threshold,
            "extremum_to_cross_age": float(extremum_age),
            "cross_to_reject_age": 0.0,
            "extremum_to_reject_age": float(extremum_age),
            "histogram_before_cross": float(diagnostic.histogram_before),
            "histogram_on_cross": float(diagnostic.histogram_after),
            "crossover_steepness": float(diagnostic.crossover_steepness),
            "crossover_steepness_per_minute": float(
                diagnostic.crossover_steepness_per_minute
            ),
            "macd_slope_per_minute": float(diagnostic.macd_slope_per_minute),
            "signal_slope_per_minute": float(
                diagnostic.signal_slope_per_minute
            ),
            "effective_angle_degrees": float(
                diagnostic.effective_angle_degrees
            ),
            "reject_ordinal": float(ordinal),
            "prior_weak_rejects": float(prior),
            "elapsed_bars_from_first_weak_reject": float(elapsed),
        }
        assert set(values) == set(FEATURES)
        assert all(math.isfinite(value) for value in values.values())
        rows.append(
            AnatomyRow(
                period=period,
                segment_start=source_row.segment_start,
                timestamp=source_row.signal_timestamp,
                direction=source_row.direction,
                residual_move_r=float(source_row.residual_move_r),
                values=values,
            )
        )
    assert len(rows) == EXPECTED_COUNTS[period]
    return tuple(rows)


def _quantile(values: tuple[float, ...], fraction: float) -> float:
    """Обчислити deterministic inclusive linear quantile."""

    assert values
    ordered = sorted(values)
    location = (len(ordered) - 1) * fraction
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    weight = location - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _distribution(rows: tuple[AnatomyRow, ...], feature: str) -> Distribution:
    """Порахувати factual feature distribution однієї outcome group."""

    values = tuple(row.values[feature] for row in rows)
    if not values:
        return Distribution(0, None, None, None, None, None, None)
    return Distribution(
        count=len(values),
        minimum=min(values),
        q1=_quantile(values, 0.25),
        median_value=median(values),
        q3=_quantile(values, 0.75),
        maximum=max(values),
        mean_value=fmean(values),
    )


def _optional(value: float | None) -> str:
    """Форматувати factual number або NONE."""

    return "NONE" if value is None else f"{value:.8f}"


def _rate(count: int, total: int) -> str:
    """Форматувати factual rate або NONE для empty bin."""

    return "NONE" if not total else f"{100.0 * count / total:.4f}"


def _print_availability(
    thresholds: dict[str, tuple[float, float]],
) -> None:
    """Показати source availability без підміни відсутніх полів."""

    print("FEATURE_AVAILABILITY")
    for period in PERIOD_CODES:
        prominence, distance = thresholds[period]
        print(
            f"period={period}|extremum_prominence=AVAILABLE|"
            "production_prominence_threshold=AVAILABLE|"
            f"production_prominence_threshold_value={prominence:.10f}|"
            "prominence_ratio=AVAILABLE|extremum_distance=AVAILABLE|"
            "production_minimum_distance=AVAILABLE|"
            f"production_minimum_distance_value={distance:.10f}|"
            "normalized_distance=AVAILABLE"
        )
        print(
            f"period={period}|extremum_to_cross_age=AVAILABLE|"
            "cross_to_reject_age=AVAILABLE|"
            "cross_to_reject_semantics=SAME_COMPLETED_CROSS_DECISION_BAR|"
            "extremum_to_reject_age=AVAILABLE"
        )
        print(
            f"period={period}|histogram_before_cross=AVAILABLE|"
            "histogram_on_cross=AVAILABLE|causal_cross_change=AVAILABLE|"
            "crossover_steepness_per_minute=AVAILABLE|"
            "macd_slope_per_minute=AVAILABLE|"
            "signal_slope_per_minute=AVAILABLE|"
            "cross_too_flat_effective_angle=AVAILABLE"
        )
        print(
            f"period={period}|reject_ordinal=AVAILABLE|"
            "prior_weak_rejects=AVAILABLE|"
            "elapsed_bars_from_first_weak_reject=AVAILABLE"
        )


def _print_distributions(rows_by_period: dict[str, tuple[AnatomyRow, ...]]) -> None:
    """Вивести seven-number stats у трьох outcome groups."""

    print("CONTINUOUS_FEATURE_OUTCOME_GROUPS")
    for period in PERIOD_CODES:
        for feature in FEATURES:
            for group in OUTCOME_GROUPS:
                rows = tuple(
                    row
                    for row in rows_by_period[period]
                    if row.outcome_group == group
                )
                stats = _distribution(rows, feature)
                print(
                    f"period={period}|feature={feature}|group={group}|"
                    f"n={stats.count}|min={_optional(stats.minimum)}|"
                    f"q1={_optional(stats.q1)}|"
                    f"median={_optional(stats.median_value)}|"
                    f"q3={_optional(stats.q3)}|max={_optional(stats.maximum)}|"
                    f"mean={_optional(stats.mean_value)}"
                )


def _iqr_overlap(win: Distribution, weak: Distribution) -> tuple[Any, ...]:
    """Описати IQR overlap REACHED_2R проти BELOW_1R без classifier."""

    if win.q1 is None or win.q3 is None or weak.q1 is None or weak.q3 is None:
        return None, None, None, None
    low = max(win.q1, weak.q1)
    high = min(win.q3, weak.q3)
    overlap = high + EPSILON >= low
    width = max(0.0, high - low)
    return overlap, low, high, width


def _print_iqr_overlap(rows_by_period: dict[str, tuple[AnatomyRow, ...]]) -> None:
    """Вивести descriptive WIN-like/weak-outcome IQR intersections."""

    print("WIN_LIKE_VS_WEAK_OUTCOME_IQR_OVERLAP")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        win_rows = tuple(row for row in rows if row.reached_2r)
        weak_rows = tuple(row for row in rows if not row.reached_1r)
        for feature in FEATURES:
            win = _distribution(win_rows, feature)
            weak = _distribution(weak_rows, feature)
            overlap, low, high, width = _iqr_overlap(win, weak)
            print(
                f"period={period}|feature={feature}|"
                f"win_like_n={win.count}|weak_outcome_n={weak.count}|"
                f"iqr_overlap={overlap if overlap is not None else 'NONE'}|"
                f"overlap_low={_optional(low)}|overlap_high={_optional(high)}|"
                f"overlap_width={_optional(width)}|"
                "association_role=DESCRIPTIVE_ONLY"
            )


def _ordinal_bin(row: AnatomyRow) -> str:
    """Застосувати fixed FIRST/SECOND/THIRD_PLUS ordinal bins."""

    ordinal = int(row.values["reject_ordinal"])
    if ordinal == 1:
        return "FIRST"
    if ordinal == 2:
        return "SECOND"
    return "THIRD_PLUS"


def _print_ordinal_bins(rows_by_period: dict[str, tuple[AnatomyRow, ...]]) -> None:
    """Вивести factual residual outcomes fixed ordinal bins."""

    print("REJECT_ORDINAL_BINS")
    for period in PERIOD_CODES:
        for bin_name in ORDINAL_BINS:
            rows = tuple(
                row
                for row in rows_by_period[period]
                if _ordinal_bin(row) == bin_name
            )
            moves = tuple(row.residual_move_r for row in rows)
            reached_1r = sum(row.reached_1r for row in rows)
            reached_2r = sum(row.reached_2r for row in rows)
            print(
                f"period={period}|bin={bin_name}|n={len(rows)}|"
                "median_residual_move_r="
                f"{_optional(median(moves) if moves else None)}|"
                f"reached_1r_rate={_rate(reached_1r, len(rows))}|"
                f"reached_2r_rate={_rate(reached_2r, len(rows))}"
            )


def _period_separation(rows: tuple[AnatomyRow, ...], feature: str) -> int:
    """Оцінити predeclared ordered median/IQR separation одного period."""

    groups = {
        group: _distribution(
            tuple(row for row in rows if row.outcome_group == group),
            feature,
        )
        for group in OUTCOME_GROUPS
    }
    if any(
        item.count < MINIMUM_OUTCOME_GROUP_SIZE for item in groups.values()
    ):
        return 0
    win = groups["REACHED_2R"]
    middle = groups["REACHED_1R_ONLY"]
    weak = groups["BELOW_1R"]
    values = (
        win.median_value,
        middle.median_value,
        weak.median_value,
        win.q1,
        weak.q1,
        win.q3,
        weak.q3,
    )
    assert all(value is not None for value in values)
    win_median, middle_median, weak_median, win_q1, weak_q1, win_q3, weak_q3 = (
        float(value) for value in values
    )
    positive = bool(
        win_median > weak_median + EPSILON
        and win_median + EPSILON >= middle_median
        and middle_median + EPSILON >= weak_median
        and win_q1 + EPSILON >= weak_q1
        and win_q3 + EPSILON >= weak_q3
    )
    negative = bool(
        win_median < weak_median - EPSILON
        and win_median <= middle_median + EPSILON
        and middle_median <= weak_median + EPSILON
        and win_q1 <= weak_q1 + EPSILON
        and win_q3 <= weak_q3 + EPSILON
    )
    if positive:
        return 1
    if negative:
        return -1
    return 0


def _feature_decision(
    rows_by_period: dict[str, tuple[AnatomyRow, ...]],
    feature: str,
) -> str:
    """Застосувати fixed cross-period separation contract без cutoff."""

    directions = {
        period: _period_separation(rows_by_period[period], feature)
        for period in PERIOD_CODES
    }
    if directions["2025"] and directions["2025"] == directions["2026"]:
        return "CROSS_PERIOD_SEPARATION_CANDIDATE"
    if bool(directions["2025"]) != bool(directions["2026"]):
        return "ONE_PERIOD_ONLY"
    return "NO_STABLE_SEPARATION"


def _combined_decision(decisions: dict[str, str], features: tuple[str, ...]) -> str:
    """Згорнути споріднені factual fields у required anatomy decision."""

    values = tuple(decisions[feature] for feature in features)
    if "CROSS_PERIOD_SEPARATION_CANDIDATE" in values:
        return "CROSS_PERIOD_SEPARATION_CANDIDATE"
    if "ONE_PERIOD_ONLY" in values:
        return "ONE_PERIOD_ONLY"
    if all(value == "UNAVAILABLE" for value in values):
        return "UNAVAILABLE"
    return "NO_STABLE_SEPARATION"


def _decisions(feature_decisions: dict[str, str]) -> dict[str, str]:
    """Побудувати required six decisions без створення hypothesis."""

    return {
        "prominence_geometry": _combined_decision(
            feature_decisions,
            ("extremum_prominence", "prominence_ratio"),
        ),
        "extremum_distance_geometry": _combined_decision(
            feature_decisions,
            ("extremum_distance", "normalized_distance"),
        ),
        "extremum_to_cross_age": feature_decisions["extremum_to_cross_age"],
        "cross_to_reject_age": feature_decisions["cross_to_reject_age"],
        "cross_histogram_geometry": _combined_decision(
            feature_decisions,
            (
                "histogram_before_cross",
                "histogram_on_cross",
                "crossover_steepness",
                "crossover_steepness_per_minute",
                "macd_slope_per_minute",
                "signal_slope_per_minute",
                "effective_angle_degrees",
            ),
        ),
        "reject_ordinal": feature_decisions["reject_ordinal"],
    }


def main() -> int:
    """Виконати T108-20 anatomy, reconciliation і safety assertions."""

    production_before = PRODUCTION_HASHES()
    rows_by_period: dict[str, tuple[AnatomyRow, ...]] = {}
    thresholds: dict[str, tuple[float, float]] = {}
    broker_requests = 0
    execution_attempted = False
    print("T108_20_MACD_WEAK_REJECT_INTERNAL_TEMPORAL_GEOMETRY_ANATOMY")
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        result, runtime = RUN_WITH_RUNTIME(spec)
        rows = _rows(spec.code, result, runtime)
        rows_by_period[spec.code] = rows
        thresholds[spec.code] = _thresholds(runtime)
        broker_requests += result.broker_requests
        execution_attempted = (
            execution_attempted or BROKER_EXECUTION_ATTEMPTED(runtime)
        )
        print(
            f"period={spec.code}|factual_weak_reject_events={len(rows)}|"
            f"expected={EXPECTED_COUNTS[spec.code]}|reconciled=True"
        )
    assert tuple(rows_by_period) == PERIOD_CODES
    assert broker_requests == 0
    assert not execution_attempted
    assert PRODUCTION_HASHES() == production_before

    _print_availability(thresholds)
    _print_distributions(rows_by_period)
    _print_iqr_overlap(rows_by_period)
    _print_ordinal_bins(rows_by_period)
    feature_decisions = {
        feature: _feature_decision(rows_by_period, feature)
        for feature in FEATURES
    }
    print("FEATURE_SEPARATION_DECISIONS")
    for feature, decision in feature_decisions.items():
        print(f"feature={feature}|decision={decision}")
    decisions = _decisions(feature_decisions)
    print("INTERNAL_ANATOMY_DECISIONS")
    for name, decision in decisions.items():
        print(f"{name}={decision}")
    promising = any(
        value == "CROSS_PERIOD_SEPARATION_CANDIDATE"
        for value in decisions.values()
    )
    print(
        "NEXT_STEP="
        + (
            "SINGLE_PREDEFINED_CAUSAL_HYPOTHESIS_REQUIRED"
            if promising
            else "STRICT_ENTRY_RESCUE_BRANCH_EXHAUSTED_CURRENT_EVIDENCE"
        )
    )

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=factual_weak_reject_events_only")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("future_segment_information_used_as_feature=False")
    print(f"minimum_outcome_group_size={MINIMUM_OUTCOME_GROUP_SIZE}")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("classifier_created=False")
    print("generic_score_model_created=False")
    print("weights_used=False")
    print("counterfactual_trades_simulated=False")
    print("new_entry_logic=False")
    print("new_exit_logic=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={execution_attempted}")
    print("T108_20_MACD_WEAK_REJECT_INTERNAL_TEMPORAL_GEOMETRY_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
