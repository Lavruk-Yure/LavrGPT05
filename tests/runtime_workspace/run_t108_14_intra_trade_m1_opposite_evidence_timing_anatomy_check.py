"""run_t108_14_intra_trade_m1_opposite_evidence_timing_anatomy_check.py — T108-14.

TEST_ONLY runner запускає незмінений canonical Candidate F Replay окремо для
2025 і 2026, читає тільки factual production trade diagnostics та зіставляє
їх із causal directional events трьох family: MACD, Alligator і Stochastic.
Дані беруться з перевіреного T108-10 harness без Supertrend. MACD читається
як знак factual histogram, Alligator — як factual ACTIVE regime/state, а
Stochastic — як current K/D cross; кожна family дає максимум один напрям на
completed M15 source bar.

Торгова шкала описується в M1 bars і хвилинах між factual entry та factual
exit. Водночас MACD/Alligator/Stochastic не перераховуються як pseudo-M1:
їхня подія стає доступною лише після завершення source M15 bar. Runner не
переносить цей стан назад усередину M15 і не продовжує його на майбутні bars.
Outcome та close reason є лише labels. Модуль не моделює exit, reverse, PnL,
weights, score, threshold або persistence, не змінює production чи MD7 і не
звертається до брокера. Output містить population, family/2-family/3-family
timing, outcome/close-reason/direction зрізи, warning windows, trades без
evidence, повний factual detail і обов'язкові safety assertions.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceMacdAlligatorReplayAlgorithm,
)

TEST_ID = "T108-14"
MODE = "RM108_T108_14_INTRA_TRADE_M1_OPPOSITE_EVIDENCE_TIMING_ANATOMY_TEST_ONLY"
SOURCE_SCRIPT = "run_t108_10_directional_signal_persistence_anatomy_check.py"
PERIOD_CODES = ("2025", "2026")
M15_DELTA = timedelta(minutes=15)
EPSILON = 1e-12

STOCHASTIC_SOURCE = "STOCHASTIC_KD_CROSS_14_1_3"
BASE_FAMILIES = ("MACD", "ALLIGATOR", "STOCHASTIC")
EVIDENCE_TYPES = BASE_FAMILIES + ("ANY_2", "ALL_3")
EXPECTED_POPULATION = {
    "2025": {"trades": 42, "WIN": 30, "LOSS": 11, "BE": 1},
    "2026": {"trades": 18, "WIN": 15, "LOSS": 2, "BE": 1},
}


def _load_source_module() -> ModuleType:
    """Завантажити canonical T108-10 harness з retained workspace path."""

    file_path = TEST_ROOT / SOURCE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location("rm108_t108_14_source", file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = _load_source_module()
PERIODS = getattr(SOURCE, "PERIODS")
RUN_PERIOD: Callable[..., Any] = getattr(SOURCE, "_run_period")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    SOURCE,
    "_production_hashes",
)
BASE_RUNTIME = getattr(SOURCE, "StochasticAnatomyRuntime")


@dataclass(frozen=True, slots=True)
class EvidenceTiming:
    """Перший causal evidence момент певного типу всередині factual trade."""

    evidence_found: bool
    first_evidence_time: datetime | None
    m1_bars_after_entry: int | None
    minutes_after_entry: int | None
    m1_bars_before_factual_exit: int | None
    minutes_before_factual_exit: int | None
    same_m1_bar_as_exit: bool


@dataclass(frozen=True, slots=True)
class TradeTimingRow:
    """Factual production trade та п'ять descriptive evidence timings."""

    period: str
    trade: Any
    direction: str
    outcome: str
    duration_m1_bars: int
    evidence: dict[str, EvidenceTiming]


def _run_with_runtime(spec: Any) -> tuple[Any, Any]:
    """Запустити T108-10 Replay і захопити той самий factual runtime."""

    captured: list[Any] = []

    class CapturingRuntime(BASE_RUNTIME):
        """TEST_ONLY subclass лише зберігає створений canonical runtime."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured.append(self)

    setattr(SOURCE, "StochasticAnatomyRuntime", CapturingRuntime)
    try:
        replay = RUN_PERIOD(spec)
    finally:
        setattr(SOURCE, "StochasticAnatomyRuntime", BASE_RUNTIME)
    assert len(captured) == 1
    runtime = captured[0]
    assert runtime.replay_session is not None
    assert runtime.replay_session.completed
    return replay, runtime


def _trades(runtime: Any) -> tuple[Any, ...]:
    """Прочитати immutable factual production trade diagnostics."""

    execution = runtime.replay_execution
    assert execution is not None
    return tuple(execution.trade_diagnostics())


def _outcome(trade: Any) -> str:
    """Перетворити factual final profit лише на WIN/LOSS/BE label."""

    if trade.final_profit > EPSILON:
        return "WIN"
    if trade.final_profit < -EPSILON:
        return "LOSS"
    return "BE"


def _elapsed_minutes(start: datetime, end: datetime) -> int:
    """Повернути точну кількість цілих M1 інтервалів між timestamps."""

    seconds = (end - start).total_seconds()
    assert seconds >= 0.0
    minutes = seconds / 60.0
    assert minutes.is_integer(), (start, end, seconds)
    return int(minutes)


def _alligator_direction(observation: Any) -> str | None:
    """Повернути лише factual production-compatible ACTIVE direction."""

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


def _family_directions(
    replay: Any,
    runtime: Any,
) -> dict[datetime, dict[str, str]]:
    """Прочитати factual completed-M15 MACD/Alligator/Stochastic states."""

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None and signal_filter is not None
    macd = {item.timestamp: item for item in source.observations}
    alligator = {item.timestamp: item for item in signal_filter.observations}
    stochastic: dict[datetime, str] = {}
    for item in replay.families[STOCHASTIC_SOURCE]:
        previous = stochastic.get(item.timestamp)
        assert previous is None or previous == item.direction
        stochastic[item.timestamp] = item.direction

    normalized: dict[datetime, dict[str, str]] = {}
    for event in replay.events:
        votes: dict[str, str] = {}
        macd_observation = macd[event.timestamp]
        histogram = macd_observation.histogram
        if histogram is not None and histogram > 0.0:
            votes["MACD"] = "BUY"
        elif histogram is not None and histogram < 0.0:
            votes["MACD"] = "SELL"
        alligator_observation = alligator[event.timestamp]
        assert alligator_observation.timestamp == event.timestamp
        alligator_direction = _alligator_direction(alligator_observation)
        if alligator_direction is not None:
            votes["ALLIGATOR"] = alligator_direction
        stochastic_direction = stochastic.get(event.timestamp)
        if stochastic_direction is not None:
            votes["STOCHASTIC"] = stochastic_direction
        normalized[event.timestamp + M15_DELTA] = votes
    return normalized


def _timing(
    entry_time: datetime,
    exit_time: datetime,
    evidence_time: datetime | None,
    trade_m1_timestamps: tuple[datetime, ...],
) -> EvidenceTiming:
    """Побудувати causal M1 timing без зарахування події після exit."""

    if evidence_time is None:
        return EvidenceTiming(False, None, None, None, None, None, False)
    assert entry_time <= evidence_time <= exit_time
    evidence_index = bisect_left(trade_m1_timestamps, evidence_time)
    assert evidence_index < len(trade_m1_timestamps)
    assert trade_m1_timestamps[evidence_index] == evidence_time
    bars_after = evidence_index
    bars_before = len(trade_m1_timestamps) - evidence_index - 1
    minutes_after = _elapsed_minutes(entry_time, evidence_time)
    minutes_before = _elapsed_minutes(evidence_time, exit_time)
    return EvidenceTiming(
        evidence_found=True,
        first_evidence_time=evidence_time,
        m1_bars_after_entry=bars_after,
        minutes_after_entry=minutes_after,
        m1_bars_before_factual_exit=bars_before,
        minutes_before_factual_exit=minutes_before,
        same_m1_bar_as_exit=bars_before == 0,
    )


def _trade_row(
    period: str,
    trade: Any,
    family_directions: dict[datetime, dict[str, str]],
    execution_timestamps: tuple[datetime, ...],
) -> TradeTimingRow:
    """Знайти перші opposite evidence events лише в factual trade interval."""

    direction = "LONG" if trade.direction == "BUY" else "SHORT"
    expected_trade_direction = "BUY" if direction == "LONG" else "SELL"
    opposite = "SELL" if expected_trade_direction == "BUY" else "BUY"
    first: dict[str, datetime | None] = {name: None for name in EVIDENCE_TYPES}
    for available_at in sorted(family_directions):
        if available_at < trade.entry_timestamp:
            continue
        if available_at > trade.close_timestamp:
            break
        votes = family_directions[available_at]
        opposite_families = tuple(
            family for family in BASE_FAMILIES if votes.get(family) == opposite
        )
        for family in opposite_families:
            if first[family] is None:
                first[family] = available_at
        if len(opposite_families) >= 2 and first["ANY_2"] is None:
            first["ANY_2"] = available_at
        if len(opposite_families) == 3 and first["ALL_3"] is None:
            first["ALL_3"] = available_at

    start = bisect_left(execution_timestamps, trade.entry_timestamp)
    stop = bisect_right(execution_timestamps, trade.close_timestamp)
    trade_m1_timestamps = execution_timestamps[start:stop]
    assert trade_m1_timestamps
    assert trade_m1_timestamps[0] == trade.entry_timestamp
    assert trade_m1_timestamps[-1] == trade.close_timestamp
    evidence = {
        name: _timing(
            trade.entry_timestamp,
            trade.close_timestamp,
            first[name],
            trade_m1_timestamps,
        )
        for name in EVIDENCE_TYPES
    }
    return TradeTimingRow(
        period=period,
        trade=trade,
        direction=direction,
        outcome=_outcome(trade),
        duration_m1_bars=len(trade_m1_timestamps),
        evidence=evidence,
    )


def _period_rows(spec: Any) -> tuple[Any, Any, tuple[TradeTimingRow, ...]]:
    """Виконати один period і перевірити factual population contract."""

    replay, runtime = _run_with_runtime(spec)
    assert all(event.timeframe == "M15" for event in replay.events)
    directions = _family_directions(replay, runtime)
    session = runtime.replay_session
    assert session is not None and session.completed and session.multi_resolution
    execution_events = tuple(
        event
        for window in session.execution_windows
        for event in window
    )
    assert execution_events
    assert all(
        event.timeframe == session.source_timeframe == "M1"
        for event in execution_events
    )
    execution_timestamps = tuple(event.timestamp for event in execution_events)
    assert all(
        previous < current
        for previous, current in zip(execution_timestamps, execution_timestamps[1:])
    )
    rows = tuple(
        _trade_row(spec.code, trade, directions, execution_timestamps)
        for trade in sorted(_trades(runtime), key=lambda item: item.entry_timestamp)
    )
    expected = EXPECTED_POPULATION[spec.code]
    outcomes = Counter(row.outcome for row in rows)
    assert len(rows) == expected["trades"]
    assert all(outcomes[name] == expected[name] for name in ("WIN", "LOSS", "BE"))
    assert replay.broker_requests == 0
    assert not replay.broker_execution_attempted
    return replay, runtime, rows


def _number(value: float | None) -> str:
    """Форматувати median/coverage або NONE для порожньої population."""

    return "NONE" if value is None else f"{value:.4f}"


def _median(values: Iterable[int]) -> float | None:
    """Повернути deterministic median цілих timing values."""

    items = tuple(values)
    return None if not items else float(statistics.median(items))


def _coverage(found: int, total: int) -> float:
    """Порахувати descriptive coverage у відсотках без selection."""

    assert total > 0
    return 100.0 * found / total


def _summary_fields(rows: tuple[TradeTimingRow, ...], evidence_type: str) -> str:
    """Сформувати coverage і exit-relative medians одного evidence type."""

    found = tuple(
        row.evidence[evidence_type]
        for row in rows
        if row.evidence[evidence_type].evidence_found
    )
    return (
        f"trades={len(rows)}|trades_with_evidence={len(found)}|"
        f"coverage_percent={_number(_coverage(len(found), len(rows)))}|"
        "median_m1_bars_after_entry="
        f"{_number(_median(item.m1_bars_after_entry for item in found))}|"
        "median_minutes_after_entry="
        f"{_number(_median(item.minutes_after_entry for item in found))}|"
        "median_m1_bars_before_exit="
        f"{_number(_median(item.m1_bars_before_factual_exit for item in found))}|"
        "median_minutes_before_exit="
        f"{_number(_median(item.minutes_before_factual_exit for item in found))}|"
        "same_m1_bar_as_exit_count="
        f"{sum(item.same_m1_bar_as_exit for item in found)}"
    )


def _print_population(rows_by_period: dict[str, tuple[TradeTimingRow, ...]]) -> None:
    """Надрукувати factual population і close reason counts."""

    print("TRADE_POPULATION")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        directions = Counter(row.direction for row in rows)
        outcomes = Counter(row.outcome for row in rows)
        reasons = Counter(row.trade.close_reason for row in rows)
        reason_text = ",".join(f"{key}:{reasons[key]}" for key in sorted(reasons))
        print(
            f"period={period}|trades={len(rows)}|LONG={directions['LONG']}|"
            f"SHORT={directions['SHORT']}|WIN={outcomes['WIN']}|"
            f"LOSS={outcomes['LOSS']}|BE={outcomes['BE']}|"
            f"close_reason_counts={reason_text}"
        )


def _print_primary_summaries(
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]],
) -> None:
    """Надрукувати family та simultaneous evidence summaries."""

    print("FAMILY_OPPOSITE_EVIDENCE")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        for family in BASE_FAMILIES:
            print(f"period={period}|family={family}|{_summary_fields(rows, family)}")
    print("TWO_FAMILY_OPPOSITE_EVIDENCE")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        print(f"period={period}|evidence_type=ANY_2|{_summary_fields(rows, 'ANY_2')}")
    print("THREE_FAMILY_OPPOSITE_EVIDENCE")
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        print(f"period={period}|evidence_type=ALL_3|{_summary_fields(rows, 'ALL_3')}")


def _print_grouped(
    section: str,
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]],
    attribute: str,
) -> None:
    """Надрукувати однакові metrics за outcome, reason або direction."""

    print(section)
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        values = sorted(
            {
                str(
                    row.trade.close_reason
                    if attribute == "close_reason"
                    else getattr(row, attribute)
                )
                for row in rows
            }
        )
        if attribute == "outcome":
            values = [value for value in ("WIN", "LOSS", "BE") if value in values]
        for value in values:
            selected = tuple(
                row
                for row in rows
                if str(
                    row.trade.close_reason
                    if attribute == "close_reason"
                    else getattr(row, attribute)
                )
                == value
            )
            for evidence_type in EVIDENCE_TYPES:
                print(
                    f"period={period}|{attribute}={value}|"
                    f"evidence_type={evidence_type}|"
                    f"{_summary_fields(selected, evidence_type)}"
                )


def _warning_bucket(before_exit: int) -> str:
    """Класифікувати descriptive warning lead time без вибору window."""

    if before_exit >= 15:
        return "GE_15"
    if before_exit >= 10:
        return "10_TO_14"
    if before_exit >= 5:
        return "5_TO_9"
    if before_exit >= 1:
        return "1_TO_4"
    assert before_exit == 0
    return "SAME_BAR_AS_EXIT"


def _print_warning_windows(
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]],
) -> None:
    """Надрукувати всі наперед задані descriptive lead-time buckets."""

    buckets = ("GE_15", "10_TO_14", "5_TO_9", "1_TO_4", "SAME_BAR_AS_EXIT")
    print("EARLY_WARNING_WINDOWS")
    for period in PERIOD_CODES:
        for evidence_type in EVIDENCE_TYPES:
            counts: Counter[str] = Counter()
            for row in rows_by_period[period]:
                timing = row.evidence[evidence_type]
                if timing.evidence_found:
                    assert timing.m1_bars_before_factual_exit is not None
                    counts[_warning_bucket(timing.m1_bars_before_factual_exit)] += 1
            print(
                f"period={period}|evidence_type={evidence_type}|"
                + "|".join(f"{bucket}={counts[bucket]}" for bucket in buckets)
            )


def _value(value: Any) -> str:
    """Форматувати nullable detail field без вигаданого значення."""

    return "NONE" if value is None else str(value)


def _print_no_evidence(
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]],
) -> None:
    """Надрукувати factual trades без жодної opposite base-family події."""

    print("NO_EVIDENCE_TRADES")
    for period in PERIOD_CODES:
        for row in rows_by_period[period]:
            if any(row.evidence[family].evidence_found for family in BASE_FAMILIES):
                continue
            print(
                f"period={period}|trade_id={row.trade.position_id}|"
                f"direction={row.direction}|outcome={row.outcome}|"
                f"close_reason={row.trade.close_reason}|"
                f"trade_duration_m1_bars={row.duration_m1_bars}"
            )


def _print_evidence_detail(
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]],
) -> None:
    """Надрукувати повний per-trade/per-evidence causal timing."""

    print("EVIDENCE_TIMING_DETAIL")
    for period in PERIOD_CODES:
        for row in rows_by_period[period]:
            for evidence_type in EVIDENCE_TYPES:
                item = row.evidence[evidence_type]
                timestamp = (
                    "NONE"
                    if item.first_evidence_time is None
                    else item.first_evidence_time.isoformat()
                )
                print(
                    f"period={period}|trade_id={row.trade.position_id}|"
                    f"direction={row.direction}|entry_time="
                    f"{row.trade.entry_timestamp.isoformat()}|exit_time="
                    f"{row.trade.close_timestamp.isoformat()}|"
                    f"evidence_type={evidence_type}|"
                    f"evidence_found={item.evidence_found}|"
                    f"first_evidence_time={timestamp}|"
                    f"m1_bars_after_entry={_value(item.m1_bars_after_entry)}|"
                    f"minutes_after_entry={_value(item.minutes_after_entry)}|"
                    "m1_bars_before_factual_exit="
                    f"{_value(item.m1_bars_before_factual_exit)}|"
                    "minutes_before_factual_exit="
                    f"{_value(item.minutes_before_factual_exit)}|"
                    f"same_m1_bar_as_exit={item.same_m1_bar_as_exit}|"
                    f"factual_close_reason={row.trade.close_reason}|"
                    f"trade_outcome={row.outcome}"
                )


def _print_factual_detail(
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]],
) -> None:
    """Надрукувати один compact summary рядок для кожної factual trade."""

    print("FACTUAL_DETAIL")
    for period in PERIOD_CODES:
        for row in rows_by_period[period]:
            first_bars = {
                name: _value(row.evidence[name].m1_bars_after_entry)
                for name in EVIDENCE_TYPES
            }
            print(
                f"period={period}|trade_id={row.trade.position_id}|"
                f"direction={row.direction}|outcome={row.outcome}|"
                f"close_reason={row.trade.close_reason}|"
                f"duration_m1_bars={row.duration_m1_bars}|"
                f"first_macd_opposite_bar={first_bars['MACD']}|"
                f"first_alligator_opposite_bar={first_bars['ALLIGATOR']}|"
                f"first_stoch_opposite_bar={first_bars['STOCHASTIC']}|"
                f"first_two_family_opposite_bar={first_bars['ANY_2']}|"
                f"first_three_family_opposite_bar={first_bars['ALL_3']}"
            )


def main() -> int:
    """Виконати T108-14 двічі відтворюваний factual timing checkpoint."""

    before_hashes = PRODUCTION_HASHES()
    print("T108_14_INTRA_TRADE_M1_OPPOSITE_EVIDENCE_TIMING_ANATOMY")
    replays: dict[str, Any] = {}
    rows_by_period: dict[str, tuple[TradeTimingRow, ...]] = {}
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        replay, _, rows = _period_rows(spec)
        replays[spec.code] = replay
        rows_by_period[spec.code] = rows
    assert tuple(rows_by_period) == PERIOD_CODES
    assert PRODUCTION_HASHES() == before_hashes

    _print_population(rows_by_period)
    _print_primary_summaries(rows_by_period)
    _print_grouped("BY_OUTCOME", rows_by_period, "outcome")
    _print_grouped("BY_CLOSE_REASON", rows_by_period, "close_reason")
    print("LONG_SHORT_ASYMMETRY")
    for period in PERIOD_CODES:
        for direction in ("LONG", "SHORT"):
            selected = tuple(
                row for row in rows_by_period[period] if row.direction == direction
            )
            for evidence_type in EVIDENCE_TYPES:
                print(
                    f"period={period}|direction={direction}|"
                    f"evidence_type={evidence_type}|"
                    f"{_summary_fields(selected, evidence_type)}"
                )
    _print_warning_windows(rows_by_period)
    _print_no_evidence(rows_by_period)
    _print_evidence_detail(rows_by_period)
    _print_factual_detail(rows_by_period)

    print("SOURCE_TIMING_SEMANTICS")
    semantics = {
        "MACD": "COMPLETED_M15_HISTOGRAM_SIGN",
        "ALLIGATOR": "COMPLETED_M15_ACTIVE_REGIME_STATE",
        "STOCHASTIC": "COMPLETED_M15_CURRENT_KD_CROSS_14_1_3",
    }
    for family in BASE_FAMILIES:
        print(
            f"family={family}|source_timeframe=M15|"
            "causal_availability_rule=SOURCE_BAR_TIMESTAMP_PLUS_15_MINUTES|"
            f"directional_semantics={semantics[family]}|"
            "state_lifetime=CURRENT_COMPLETED_M15_ONLY"
        )
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=FACTUAL_CURRENT_PRODUCTION_TRADES_ONLY")
    print("timeline=FACTUAL_ENTRY_TO_FACTUAL_EXIT")
    print("families=MACD_ALLIGATOR_STOCHASTIC")
    print("supertrend_included=False")
    print("production_actions_used_as_labels_only=True")
    print("counterfactual_exit_simulated=False")
    print("alternative_exit_simulated=False")
    print("reverse_logic_created=False")
    print("weights_used=False")
    print("score_model_created=False")
    print("score_threshold_selected=False")
    print("best_timing_window_selected=False")
    print("persistence_selected=False")
    print("completed_bars_only=True")
    print("higher_timeframe_backfill_used=False")
    print("lookahead_used=False")
    print("optimization_performed=False")
    print("threshold_sweep_performed=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={sum(item.broker_requests for item in replays.values())}")
    print(
        "broker_execution_attempted="
        f"{any(item.broker_execution_attempted for item in replays.values())}"
    )
    print("T108_14_INTRA_TRADE_M1_OPPOSITE_EVIDENCE_TIMING_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
