"""run_t108_22_causal_weak_reject_population_rebuild_anatomy_check.py.

T108-22 є TEST_ONLY anatomy повної causal population factual production/source
``MACD_EXTREMUM_TOO_WEAK`` rejects. Runner повторно використовує canonical
T108-20 Replay harness, але не переносить його hindsight-selected strong/missed
segment filter: кожен reject входить до population вже на completed M15
decision bar.

Вісім наперед визначених features походять із causal production diagnostic або
з уже спостереженої chronology поточного ACTIVE Alligator segment. Ordinal,
prior count та elapsed bars накопичуються зліва направо; майбутні rejects,
кінець сегмента, strong label і factual trade coverage не читаються.

Outcome є лише descriptive label: canonical fixed horizon H=8 наступних
completed M15 bars та causal signal-bar R = max(range, spread * 10). Runner
показує cross-period distributions, IQR overlap, ordinal bins і descriptive
decisions без cutoff, classifier, trades, entry/exit/reverse logic, production
змін або MD7.
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

from core.workspace_macd_crossover_quality import (  # noqa: E402
    MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK,
    WorkspaceMacdCrossoverQualityDiagnostic,
)

TEST_ID = "T108-22"
MODE = "RM108_T108_22_CAUSAL_WEAK_REJECT_POPULATION_REBUILD_ANATOMY_TEST_ONLY"
SOURCE_SCRIPT = (
    "run_t108_20_macd_weak_reject_internal_temporal_geometry_anatomy_check.py"
)
PERIOD_CODES = ("2025", "2026")
HISTORICAL_T108_20_COUNTS = {"2025": 136, "2026": 96}
BASELINE_2025_COUNTS = "trades:42,wins:30,losses:11,break_even:1,"
BASELINE_2025_RESULT = "net:+4.03,pf:1.5424,dd:3.58"
BASELINE_2026_COUNTS = "trades:18,wins:15,losses:2,break_even:1,"
BASELINE_2026_RESULT = "net:+3.68,pf:3.7669,dd:1.20"
EXPECTED_BASELINE_PREFIXES = {
    "2025": BASELINE_2025_COUNTS + BASELINE_2025_RESULT,
    "2026": BASELINE_2026_COUNTS + BASELINE_2026_RESULT,
}
OUTCOME_HORIZON_BARS = 8
MINIMUM_OUTCOME_GROUP_SIZE = 10
EPSILON = 1e-12
FEATURES = (
    "extremum_distance",
    "normalized_distance",
    "crossover_steepness",
    "crossover_steepness_per_minute",
    "effective_angle_degrees",
    "reject_ordinal",
    "prior_weak_rejects",
    "elapsed_bars_from_first_weak_reject",
)
OUTCOME_GROUPS = ("REACHED_2R", "REACHED_1R_ONLY", "BELOW_1R")
ORDINAL_BINS = ("FIRST", "SECOND", "THIRD_PLUS")


def _load_source_module() -> ModuleType:
    """Завантажити GREEN T108-20 з exact retained workspace path."""

    file_path = TEST_ROOT / SOURCE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_22_source",
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
    "RUN_WITH_RUNTIME",
)
THRESHOLDS: Callable[[Any], tuple[float, float]] = getattr(
    SOURCE,
    "_thresholds",
)
PRODUCTION_HASHES: Callable[[], Any] = getattr(SOURCE, "PRODUCTION_HASHES")
BROKER_EXECUTION_ATTEMPTED: Callable[[Any], bool] = getattr(
    SOURCE,
    "BROKER_EXECUTION_ATTEMPTED",
)


@dataclass(frozen=True, slots=True)
class CausalWeakRejectRow:
    """Один causal weak reject з окремим fixed-horizon outcome label."""

    period: str
    timestamp: datetime
    direction: str
    favorable_move_r: float | None
    values: dict[str, float | None]

    @property
    def outcome_available(self) -> bool:
        """Чи доступні всі H=8 майбутніх completed bars для label."""

        return self.favorable_move_r is not None

    @property
    def reached_1r(self) -> bool:
        """Чи factual H=8 favorable move досяг descriptive 1R."""

        assert self.favorable_move_r is not None
        return self.favorable_move_r + EPSILON >= 1.0

    @property
    def reached_2r(self) -> bool:
        """Чи factual H=8 favorable move досяг descriptive 2R."""

        assert self.favorable_move_r is not None
        return self.favorable_move_r + EPSILON >= 2.0

    @property
    def outcome_group(self) -> str:
        """Повернути fixed descriptive outcome group або UNAVAILABLE."""

        if not self.outcome_available:
            return "UNAVAILABLE"
        if self.reached_2r:
            return "REACHED_2R"
        if self.reached_1r:
            return "REACHED_1R_ONLY"
        return "BELOW_1R"


@dataclass(frozen=True, slots=True)
class Distribution:
    """П'ятиелементний descriptive summary одного causal feature."""

    count: int
    q1: float | None
    median_value: float | None
    q3: float | None
    mean_value: float | None


def _observation_side_helper() -> Callable[[Any], str | None]:
    """Отримати канонічне causal трактування ACTIVE observation side."""

    t108_19 = getattr(SOURCE, "SOURCE")
    t108_08 = getattr(t108_19, "T108_08")
    missed = getattr(t108_08, "_missed_strong_segments")
    segments = missed.__globals__["_segments"]
    return segments.__globals__["_observation_side"]


OBSERVATION_SIDE = _observation_side_helper()


def _factual_weak_diagnostics(
    runtime: Any,
) -> tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...]:
    """Зібрати typed tuple усіх factual source weak-reject diagnostics."""

    algorithm = runtime.algorithm
    source = algorithm.source
    assert source is not None
    result: list[WorkspaceMacdCrossoverQualityDiagnostic] = []
    for diagnostic in source.quality_diagnostics:
        if diagnostic.reason_code == MACD_QUALITY_REASON_EXTREMUM_TOO_WEAK:
            result.append(diagnostic)
    keys = {(item.timestamp, item.direction) for item in result}
    assert len(keys) == len(result)
    return tuple(result)


def _causal_segment_starts(
    runtime: Any,
) -> dict[tuple[datetime, str], datetime]:
    """Відтворити лише already-known start поточного ACTIVE segment."""

    algorithm = runtime.algorithm
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    current_side: str | None = None
    current_start: datetime | None = None
    result: dict[tuple[datetime, str], datetime] = {}
    observations = sorted(
        signal_filter.observations,
        key=lambda item: item.timestamp,
    )
    for observation in observations:
        side = OBSERVATION_SIDE(observation)
        if side != current_side:
            current_side = side
            current_start = observation.timestamp if side is not None else None
        if side is not None:
            assert current_start is not None
            result[(observation.timestamp, side)] = current_start
    return result


def _cluster_values(
    diagnostics: tuple[WorkspaceMacdCrossoverQualityDiagnostic, ...],
    segment_starts: dict[tuple[datetime, str], datetime],
    event_indexes: dict[datetime, int],
) -> dict[tuple[datetime, str], tuple[int, int, int]]:
    """Накопичити ordinal/prior/elapsed лише з prior/current rejects."""

    counts: Counter[tuple[datetime, str]] = Counter()
    first_timestamp: dict[tuple[datetime, str], datetime] = {}
    result: dict[tuple[datetime, str], tuple[int, int, int]] = {}
    eligible = tuple(
        item
        for item in diagnostics
        if (item.timestamp, item.direction) in segment_starts
    )
    for diagnostic in sorted(eligible, key=lambda item: item.timestamp):
        key = (diagnostic.timestamp, diagnostic.direction)
        segment_key = (segment_starts[key], diagnostic.direction)
        prior = counts[segment_key]
        if prior == 0:
            first_timestamp[segment_key] = diagnostic.timestamp
        elapsed = (
            event_indexes[diagnostic.timestamp]
            - event_indexes[first_timestamp[segment_key]]
        )
        result[key] = (prior + 1, prior, elapsed)
        counts[segment_key] += 1
    assert len(result) == len(eligible)
    return result


def _favorable_move_r(
    diagnostic: WorkspaceMacdCrossoverQualityDiagnostic,
    timestamps: tuple[datetime, ...],
    event_indexes: dict[datetime, int],
    events: dict[datetime, Any],
) -> float | None:
    """Обчислити H=8 future label від causal signal-bar R geometry."""

    signal_index = event_indexes[diagnostic.timestamp]
    first_future = signal_index + 1
    end_future = first_future + OUTCOME_HORIZON_BARS
    if end_future > len(timestamps):
        return None
    signal_event = events[diagnostic.timestamp]
    stop_distance = max(
        signal_event.high - signal_event.low,
        signal_event.spread * 10.0,
    )
    assert stop_distance > 0.0
    future_events = tuple(
        events[timestamp] for timestamp in timestamps[first_future:end_future]
    )
    assert len(future_events) == OUTCOME_HORIZON_BARS
    if diagnostic.direction == "BUY":
        highest_future = max(item.high for item in future_events)
        favorable = highest_future - signal_event.close
    else:
        assert diagnostic.direction == "SELL"
        lowest_future = min(item.low for item in future_events)
        favorable = signal_event.close - lowest_future
    return max(float(favorable), 0.0) / float(stop_distance)


def _rows(period: str, runtime: Any) -> tuple[CausalWeakRejectRow, ...]:
    """Побудувати повну decision-time population без hindsight selection."""

    diagnostics = _factual_weak_diagnostics(runtime)
    _, distance_threshold = THRESHOLDS(runtime)
    timestamps = tuple(sorted(runtime.strategy_events))
    event_indexes = dict(zip(timestamps, range(len(timestamps))))
    segment_starts = _causal_segment_starts(runtime)
    clusters = _cluster_values(
        diagnostics,
        segment_starts,
        event_indexes,
    )
    result: list[CausalWeakRejectRow] = []
    for diagnostic in sorted(diagnostics, key=lambda item: item.timestamp):
        assert diagnostic.extremum_to_cross_distance is not None
        key = (diagnostic.timestamp, diagnostic.direction)
        cluster = clusters.get(key)
        if cluster is None:
            ordinal = None
            prior = None
            elapsed = None
        else:
            ordinal, prior, elapsed = cluster
        distance = float(diagnostic.extremum_to_cross_distance)
        angle = float(diagnostic.effective_angle_degrees)
        ordinal_value = float(ordinal) if ordinal is not None else None
        values = {
            "extremum_distance": distance,
            "normalized_distance": distance / distance_threshold,
            "crossover_steepness": float(diagnostic.crossover_steepness),
            "crossover_steepness_per_minute": float(
                diagnostic.crossover_steepness_per_minute
            ),
            "effective_angle_degrees": angle,
            "reject_ordinal": ordinal_value,
            "prior_weak_rejects": float(prior) if prior is not None else None,
            "elapsed_bars_from_first_weak_reject": (
                float(elapsed) if elapsed is not None else None
            ),
        }
        assert set(values) == set(FEATURES)
        for value in values.values():
            assert value is None or math.isfinite(value)
        result.append(
            CausalWeakRejectRow(
                period=period,
                timestamp=diagnostic.timestamp,
                direction=diagnostic.direction,
                favorable_move_r=_favorable_move_r(
                    diagnostic,
                    timestamps,
                    event_indexes,
                    runtime.strategy_events,
                ),
                values=values,
            )
        )
    assert len(result) == len(diagnostics)
    return tuple(result)


def _quantile(values: tuple[float, ...], fraction: float) -> float:
    """Обчислити deterministic inclusive linear quantile."""

    ordered = sorted(values)
    assert ordered
    location = (len(ordered) - 1) * fraction
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    weight = location - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _distribution(
    rows: tuple[CausalWeakRejectRow, ...],
    feature: str,
) -> Distribution:
    """Порахувати requested stats causal feature в outcome group."""

    collected: list[float] = []
    for row in rows:
        value = row.values[feature]
        if value is not None:
            collected.append(float(value))
    values = tuple(collected)
    if not values:
        return Distribution(0, None, None, None, None)
    return Distribution(
        count=len(values),
        q1=_quantile(values, 0.25),
        median_value=median(values),
        q3=_quantile(values, 0.75),
        mean_value=fmean(values),
    )


def _optional(value: float | None) -> str:
    """Форматувати factual число або NONE."""

    return "NONE" if value is None else f"{value:.8f}"


def _rate(count: int, total: int) -> str:
    """Форматувати відсоткову частку або NONE для empty bin."""

    return "NONE" if not total else f"{100.0 * count / total:.4f}"


def _outcome_rows(
    rows: tuple[CausalWeakRejectRow, ...],
    group: str,
) -> tuple[CausalWeakRejectRow, ...]:
    """Відібрати rows одного factual outcome group для звіту."""

    return tuple(row for row in rows if row.outcome_group == group)


def _print_feature_tables(
    rows_by_period: dict[str, tuple[CausalWeakRejectRow, ...]],
) -> None:
    """Надрукувати distributions та reached2R/below1R IQR overlap."""

    print("CAUSAL_FEATURE_AVAILABILITY")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        for feature in FEATURES:
            available = sum(row.values[feature] is not None for row in rows)
            print(
                f"period={period}|feature={feature}|available_n={available}|"
                f"unavailable_n={len(rows) - available}|"
                "availability_known_at_decision_time=True"
            )

    print("CAUSAL_FEATURE_OUTCOME_GROUPS")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        for feature in FEATURES:
            for group in OUTCOME_GROUPS:
                group_rows = _outcome_rows(rows, group)
                stats = _distribution(group_rows, feature)
                print(
                    f"period={period}|feature={feature}|group={group}|"
                    f"n={stats.count}|q1={_optional(stats.q1)}|"
                    f"median={_optional(stats.median_value)}|"
                    f"q3={_optional(stats.q3)}|"
                    f"mean={_optional(stats.mean_value)}"
                )

    print("REACHED_2R_VS_BELOW_1R_IQR_OVERLAP")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        for feature in FEATURES:
            win = _distribution(
                _outcome_rows(rows, "REACHED_2R"),
                feature,
            )
            weak = _distribution(
                _outcome_rows(rows, "BELOW_1R"),
                feature,
            )
            if win.q1 is None or win.q3 is None:
                overlap: bool | None = None
                low = None
                high = None
                width = None
            elif weak.q1 is None or weak.q3 is None:
                overlap = None
                low = None
                high = None
                width = None
            else:
                low = max(win.q1, weak.q1)
                high = min(win.q3, weak.q3)
                overlap = high + EPSILON >= low
                width = max(0.0, high - low)
            print(
                f"period={period}|feature={feature}|"
                f"reached_2r_n={win.count}|below_1r_n={weak.count}|"
                f"iqr_overlap={overlap if overlap is not None else 'NONE'}|"
                f"overlap_low={_optional(low)}|overlap_high={_optional(high)}|"
                f"overlap_width={_optional(width)}"
            )


def _ordinal_bin(row: CausalWeakRejectRow) -> str:
    """Застосувати predefined FIRST/SECOND/THIRD_PLUS bins."""

    value = row.values["reject_ordinal"]
    assert value is not None
    ordinal = int(value)
    if ordinal == 1:
        return "FIRST"
    if ordinal == 2:
        return "SECOND"
    return "THIRD_PLUS"


def _ordinal_outcome_rows(
    rows: tuple[CausalWeakRejectRow, ...],
) -> tuple[CausalWeakRejectRow, ...]:
    """Залишити rows з causal ordinal та доступним H=8 outcome."""

    result: list[CausalWeakRejectRow] = []
    for row in rows:
        if row.outcome_available and row.values["reject_ordinal"] is not None:
            result.append(row)
    return tuple(result)


def _ordinal_bin_rows(
    rows: tuple[CausalWeakRejectRow, ...],
    bin_name: str,
) -> tuple[CausalWeakRejectRow, ...]:
    """Відібрати ordinal rows одного predefined bin."""

    return tuple(row for row in rows if _ordinal_bin(row) == bin_name)


def _print_ordinal_bins(
    rows_by_period: dict[str, tuple[CausalWeakRejectRow, ...]],
) -> None:
    """Надрукувати fixed-horizon anatomy predefined ordinal bins."""

    print("REJECT_ORDINAL_BINS")
    for period in PERIOD_CODES:
        available = _ordinal_outcome_rows(rows_by_period[period])
        for bin_name in ORDINAL_BINS:
            rows = _ordinal_bin_rows(available, bin_name)
            moves = tuple(
                float(row.favorable_move_r)
                for row in rows
                if row.favorable_move_r is not None
            )
            reached_1r = sum(row.reached_1r for row in rows)
            reached_2r = sum(row.reached_2r for row in rows)
            print(
                f"period={period}|bin={bin_name}|n={len(rows)}|"
                "median_favorable_move_r="
                f"{_optional(median(moves) if moves else None)}|"
                f"reached_1r_rate={_rate(reached_1r, len(rows))}|"
                f"reached_2r_rate={_rate(reached_2r, len(rows))}"
            )


def _period_direction(
    rows: tuple[CausalWeakRejectRow, ...],
    feature: str,
) -> tuple[str, int]:
    """Оцінити ordered median/IQR separation одного period без cutoff."""

    groups = {
        group: _distribution(
            tuple(row for row in rows if row.outcome_group == group),
            feature,
        )
        for group in OUTCOME_GROUPS
    }
    if any(item.count == 0 for item in groups.values()):
        return "UNAVAILABLE", 0
    group_counts = tuple(item.count for item in groups.values())
    if min(group_counts) < MINIMUM_OUTCOME_GROUP_SIZE:
        return "SMALL_SAMPLE_ONLY", 0
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
    (
        win_median,
        middle_median,
        weak_median,
        win_q1,
        weak_q1,
        win_q3,
        weak_q3,
    ) = (float(value) for value in values)
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
        return "SEPARATED", 1
    if negative:
        return "SEPARATED", -1
    return "NO_STABLE_SEPARATION", 0


def _feature_decision(
    rows_by_period: dict[str, tuple[CausalWeakRejectRow, ...]],
    feature: str,
) -> str:
    """Застосувати predeclared cross-period descriptive decision contract."""

    results = {
        period: _period_direction(rows_by_period[period], feature)
        for period in PERIOD_CODES
    }
    states = tuple(result[0] for result in results.values())
    directions = tuple(result[1] for result in results.values())
    if "UNAVAILABLE" in states:
        return "UNAVAILABLE"
    if "SMALL_SAMPLE_ONLY" in states:
        return "SMALL_SAMPLE_ONLY"
    if directions[0] and directions[0] == directions[1]:
        return "CAUSAL_POPULATION_SEPARATION_CANDIDATE"
    if bool(directions[0]) != bool(directions[1]):
        return "ONE_PERIOD_ONLY"
    return "NO_STABLE_SEPARATION"


def main() -> int:
    """Виконати causal population rebuild, anatomy та safety assertions."""

    production_before = PRODUCTION_HASHES()
    rows_by_period: dict[str, tuple[CausalWeakRejectRow, ...]] = {}
    broker_requests = 0
    execution_attempted = False

    print("T108_22_CAUSAL_WEAK_REJECT_POPULATION_REBUILD_ANATOMY")
    print(f"outcome_horizon_completed_m15_bars={OUTCOME_HORIZON_BARS}")
    print("horizon_source=CANONICAL_PREVIOUS_ROADMAP_FIXED_HORIZON")
    print("horizon_selected_before_outcome_analysis=True")
    print("outcome_normalization=SIGNAL_BAR_MAX_RANGE_SPREAD_X10")
    print("outcome_normalization_causal=True")
    print("POPULATION")
    for spec in PERIODS:
        assert spec.code in PERIOD_CODES
        print(f"running_period={spec.code}", flush=True)
        result, runtime = RUN_WITH_RUNTIME(spec)
        rows = _rows(spec.code, runtime)
        rows_by_period[spec.code] = rows
        available = sum(row.outcome_available for row in rows)
        unavailable = len(rows) - available
        assert available > 0
        expected_prefix = EXPECTED_BASELINE_PREFIXES[spec.code]
        assert result.baseline.startswith(expected_prefix)
        broker_requests += result.broker_requests
        period_attempted = BROKER_EXECUTION_ATTEMPTED(runtime)
        execution_attempted = execution_attempted or period_attempted
        print(
            f"period={spec.code}|all_factual_weak_reject_events={len(rows)}|"
            f"outcome_labels_available={available}|"
            f"outcome_labels_unavailable_tail={unavailable}|"
            "decision_time_population_causal=True"
        )
        print(
            f"period={spec.code}|historical_t108_20_population_label="
            f"{HISTORICAL_T108_20_COUNTS[spec.code]}|"
            "historical_label_used_as_filter=False"
        )
        print(f"period={spec.code}|production_baseline={result.baseline}")

    assert tuple(rows_by_period) == PERIOD_CODES
    assert broker_requests == 0
    assert not execution_attempted
    assert PRODUCTION_HASHES() == production_before

    _print_feature_tables(rows_by_period)
    _print_ordinal_bins(rows_by_period)
    decisions: dict[str, str] = {}
    for feature in FEATURES:
        decisions[feature] = _feature_decision(rows_by_period, feature)
    print("CAUSAL_POPULATION_DECISIONS")
    for feature in FEATURES:
        print(f"{feature}={decisions[feature]}")
    if "CAUSAL_POPULATION_SEPARATION_CANDIDATE" in decisions.values():
        print("NEXT_STEP=SINGLE_CAUSAL_HYPOTHESIS_MAY_BE_DEFINED")
    else:
        next_step = "STRICT_ENTRY_RESCUE_BRANCH_EXHAUSTED_CURRENT_EVIDENCE"
        print(f"NEXT_STEP={next_step}")

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=all_factual_weak_reject_events")
    print("population_causal_at_decision_time=True")
    print("strong_missed_population_filter_used=False")
    print("future_segment_information_used=False")
    print("future_trade_coverage_used=False")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("future_reject_count_used=False")
    print("future_segment_boundary_used=False")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("classifier_created=False")
    print("counterfactual_trades_simulated=False")
    print("new_entry_logic=False")
    print("new_exit_logic=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={execution_attempted}")
    print("T108_22_CAUSAL_WEAK_REJECT_POPULATION_REBUILD_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
