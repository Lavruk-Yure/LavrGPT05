"""run_t108_13_exact_family_composition_position_state_anatomy_check.py — T108-13.

TEST_ONLY anatomy поєднує exact MACD/Alligator/Stochastic compositions GREEN
T108-12 із фактичним FLAT/LONG/SHORT станом canonical production Replay.
Стан фіксується causal на завершенні M15 bar до його наступного M1 execution
window. Production entries і exits є лише factual labels; close reasons
беруться з незмінених trade diagnostics.

Для P1..P5 runner окремо показує position coverage, one-bar outcome кожної
composition/state population, factual entry, support та opposite-exit labels,
а також focus MS_BUY і MAS_SELL у 2025/2026. Наступний completed M15 bar є
тільки outcome label і не входить у decision inputs. Runner не створює угод,
alternative entry/exit, reverse logic, weights, threshold, ranking або best
persistence і не змінює production чи MD7.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-13"
MODE = "RM108_T108_13_EXACT_FAMILY_COMPOSITION_POSITION_STATE_" "ANATOMY_TEST_ONLY"
COMPOSITION_SCRIPT = "run_t108_12_signed_family_combination_anatomy_check.py"
PERSISTENCES = (1, 2, 3, 4, 5)
PERIOD_CODES = ("2025", "2026")
POSITION_STATES = ("FLAT", "LONG", "SHORT")
FOCUS_CLASSES = ("MS_BUY", "MAS_SELL")
BASE_CLOSE_REASONS = (
    "STOP_LOSS",
    "TAKE_PROFIT",
    "PROFIT_DRAWDOWN",
    "SESSION_END",
)
M15_DELTA = timedelta(minutes=15)


def _load_composition_module() -> ModuleType:
    """Завантажити GREEN T108-12 із canonical workspace path."""

    file_path = TEST_ROOT / COMPOSITION_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_13_composition",
        file_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COMPOSITION = _load_composition_module()
VOTE = getattr(COMPOSITION, "VOTE")
PERSISTENCE = getattr(VOTE, "PERSISTENCE")
PERIODS = getattr(COMPOSITION, "PERIODS")
RUN_PERIOD: Callable[..., Any] = getattr(COMPOSITION, "RUN_PERIOD")
DECISION_ROWS: Callable[..., Any] = getattr(COMPOSITION, "DECISION_ROWS")
OUTCOME_METRICS: Callable[..., Any] = getattr(COMPOSITION, "OUTCOME_METRICS")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    COMPOSITION,
    "PRODUCTION_HASHES",
)
SAME_STATES = getattr(COMPOSITION, "SAME_STATES")
CONFLICT_STATES = getattr(COMPOSITION, "CONFLICT_STATES")
SAME_CLASSES = getattr(COMPOSITION, "SAME_CLASSES")
CONFLICT_CLASSES = getattr(COMPOSITION, "CONFLICT_CLASSES")
BASE_RUNTIME = getattr(PERSISTENCE, "StochasticAnatomyRuntime")


@dataclass(frozen=True, slots=True)
class DirectionalOutcomeEvent:
    """Напрям post-decision outcome label одного completed M15 bar."""

    timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class PositionLabel:
    """Causal production state та наступна factual дія для decision bar."""

    state: str
    active_trade: Any | None
    entry_directions: tuple[str, ...]
    exits_before_next: tuple[Any, ...]
    position_still_open_next: bool


@dataclass(frozen=True, slots=True)
class ClassifiedRow:
    """Exact family class одного bar разом із production position label."""

    row: Any
    class_name: str
    direction: str | None
    position: PositionLabel


@dataclass(frozen=True, slots=True)
class PeriodAnalysis:
    """Усі position-aware classifications одного period/P variant."""

    rows: tuple[ClassifiedRow, ...]
    cells: dict[str, dict[str, tuple[ClassifiedRow, ...]]]
    coverage: Counter[str]


def _run_with_runtime(spec: Any) -> tuple[Any, Any]:
    """Отримати той самий canonical Replay і його factual runtime instance."""

    captured: list[Any] = []

    class CapturingRuntime(BASE_RUNTIME):
        """TEST_ONLY subclass, що зберігає завершений canonical runtime."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured.append(self)

    setattr(PERSISTENCE, "StochasticAnatomyRuntime", CapturingRuntime)
    try:
        replay = RUN_PERIOD(spec)
    finally:
        setattr(PERSISTENCE, "StochasticAnatomyRuntime", BASE_RUNTIME)
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


def _position_labels(replay: Any, runtime: Any) -> dict[datetime, PositionLabel]:
    """Визначити state до M1 window та action до наступного M15 decision."""

    trades = _trades(runtime)
    labels: dict[datetime, PositionLabel] = {}
    for index, event in enumerate(replay.events[:-1]):
        decision_at = event.timestamp + M15_DELTA
        next_decision_at = replay.events[index + 1].timestamp + M15_DELTA
        active = tuple(
            trade
            for trade in trades
            if trade.entry_timestamp < decision_at <= trade.close_timestamp
        )
        assert len(active) <= 1, (event.timestamp, active)
        if not active:
            state = "FLAT"
            active_trade = None
        else:
            active_trade = active[0]
            state = "LONG" if active_trade.direction == "BUY" else "SHORT"

        entries = tuple(
            trade.direction
            for trade in trades
            if trade.signal_timestamp == event.timestamp
            and trade.entry_timestamp == decision_at
        )
        exits = tuple(
            trade for trade in active if trade.close_timestamp < next_decision_at
        )
        remains = bool(
            active_trade is not None
            and active_trade.close_timestamp >= next_decision_at
        )
        assert not exits or not remains
        labels[event.timestamp] = PositionLabel(
            state=state,
            active_trade=active_trade,
            entry_directions=entries,
            exits_before_next=exits,
            position_still_open_next=remains,
        )
    return labels


def _class_and_direction(row: Any) -> tuple[str, str | None]:
    """Застосувати exact T108-12 taxonomy без score aggregation."""

    state = (row.macd_vote, row.alligator_vote, row.stochastic_vote)
    if state in SAME_STATES:
        class_name = SAME_STATES[state]
        direction = "BUY" if class_name.endswith("_BUY") else "SELL"
        return class_name, direction
    if state in CONFLICT_STATES:
        return CONFLICT_STATES[state], None
    assert state == (0, 0, 0), state
    return "NEUTRAL", None


def _analyze(
    replay: Any,
    persistence: int,
    positions: dict[datetime, PositionLabel],
) -> PeriodAnalysis:
    """Розкласти exact compositions за causal FLAT/LONG/SHORT state."""

    decision_rows, _, _ = DECISION_ROWS(replay, persistence)
    classified: list[ClassifiedRow] = []
    cells: dict[str, dict[str, list[ClassifiedRow]]] = {
        name: {state: [] for state in POSITION_STATES}
        for name in SAME_CLASSES + CONFLICT_CLASSES + ("NEUTRAL",)
    }
    coverage: Counter[str] = Counter()
    for row in decision_rows:
        class_name, direction = _class_and_direction(row)
        position = positions[row.timestamp]
        item = ClassifiedRow(row, class_name, direction, position)
        classified.append(item)
        cells[class_name][position.state].append(item)
        coverage[position.state] += 1
    assert sum(coverage.values()) == len(decision_rows)
    frozen_cells = {
        name: {state: tuple(items) for state, items in states.items()}
        for name, states in cells.items()
    }
    return PeriodAnalysis(tuple(classified), frozen_cells, coverage)


def _events(
    rows: tuple[ClassifiedRow, ...],
    direction: str,
) -> tuple[DirectionalOutcomeEvent, ...]:
    """Створити factual one-bar outcome labels без execution semantics."""

    return tuple(
        DirectionalOutcomeEvent(item.row.timestamp, direction) for item in rows
    )


def _metrics(replay: Any, rows: tuple[ClassifiedRow, ...], direction: str) -> Any:
    """Порахувати незмінені T108-12 one-bar directional metrics."""

    return OUTCOME_METRICS(replay.events, _events(rows, direction), 1)


def _number(value: float | None) -> str:
    """Форматувати metric або NONE для порожньої population."""

    return "NONE" if value is None else f"{value:.4f}"


def _sample_warning(count: int) -> str:
    """Позначити visibility warning без selection чи rejection."""

    return "SMALL_SAMPLE" if count < 30 else "NONE"


def _reason_counts(
    rows: tuple[ClassifiedRow, ...],
    close_reasons: tuple[str, ...],
) -> str:
    """Сформувати deterministic factual close-reason distribution."""

    counts = Counter(
        trade.close_reason for item in rows for trade in item.position.exits_before_next
    )
    return "|".join(f"close_{reason}={counts[reason]}" for reason in close_reasons)


def _entry_count(rows: tuple[ClassifiedRow, ...], direction: str) -> int:
    """Порахувати factual production fills із сигналу цього decision bar."""

    return sum(direction in item.position.entry_directions for item in rows)


def _exit_count(rows: tuple[ClassifiedRow, ...]) -> int:
    """Порахувати bars, де поточна production position закрилась завчасно."""

    return sum(bool(item.position.exits_before_next) for item in rows)


def _remains_count(rows: tuple[ClassifiedRow, ...]) -> int:
    """Порахувати bars, де та сама position активна на next M15 decision."""

    return sum(item.position.position_still_open_next for item in rows)


def _print_position_coverage(
    results: dict[str, dict[int, PeriodAnalysis]],
) -> None:
    """Вивести повне FLAT/LONG/SHORT coverage для кожного period/P."""

    print("POSITION_STATE_COVERAGE")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            coverage = results[period][persistence].coverage
            print(
                f"period={period}|persistence=P{persistence}|"
                f"FLAT_bars={coverage['FLAT']}|LONG_bars={coverage['LONG']}|"
                f"SHORT_bars={coverage['SHORT']}|"
                f"total_bars={sum(coverage.values())}"
            )


def _print_compositions(
    replays: dict[str, Any],
    results: dict[str, dict[int, PeriodAnalysis]],
) -> None:
    """Вивести outcomes кожної exact composition у кожному position state."""

    print("COMPOSITION_BY_POSITION_STATE")
    for period in PERIOD_CODES:
        replay = replays[period]
        for persistence in PERSISTENCES:
            analysis = results[period][persistence]
            for class_name in SAME_CLASSES:
                direction = "BUY" if class_name.endswith("_BUY") else "SELL"
                for state in POSITION_STATES:
                    rows = analysis.cells[class_name][state]
                    metric = _metrics(replay, rows, direction)
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"class={class_name}|position_state={state}|"
                        f"direction={direction}|bars_count={metric.events}|"
                        f"success_rate={_number(metric.success_rate)}|"
                        f"median_edge_r={_number(metric.net_median)}|"
                        f"sample_warning={_sample_warning(metric.events)}"
                    )
            for class_name in CONFLICT_CLASSES:
                for state in POSITION_STATES:
                    rows = analysis.cells[class_name][state]
                    for direction in ("BUY", "SELL"):
                        metric = _metrics(replay, rows, direction)
                        print(
                            f"period={period}|persistence=P{persistence}|"
                            f"class={class_name}|position_state={state}|"
                            f"outcome_direction={direction}|"
                            f"bars_count={metric.events}|"
                            f"success_rate={_number(metric.success_rate)}|"
                            f"median_edge_r={_number(metric.net_median)}|"
                            f"sample_warning={_sample_warning(metric.events)}"
                        )
            for state in POSITION_STATES:
                count = len(analysis.cells["NEUTRAL"][state])
                print(
                    f"period={period}|persistence=P{persistence}|"
                    f"class=NEUTRAL|position_state={state}|bars_count={count}|"
                    f"success_rate=NONE|median_edge_r=NONE|"
                    f"sample_warning={_sample_warning(count)}"
                )


def _print_entry_labels(
    results: dict[str, dict[int, PeriodAnalysis]],
) -> None:
    """Вивести factual same-direction production entries тільки з FLAT."""

    print("FACTUAL_ENTRY_LABELS")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            analysis = results[period][persistence]
            for class_name in SAME_CLASSES:
                direction = "BUY" if class_name.endswith("_BUY") else "SELL"
                rows = analysis.cells[class_name]["FLAT"]
                entry_count = _entry_count(rows, direction)
                print(
                    f"period={period}|persistence=P{persistence}|"
                    f"class={class_name}|direction={direction}|"
                    f"bars_count={len(rows)}|"
                    "factual_production_entry_same_direction_count="
                    f"{entry_count}|no_production_entry_count="
                    f"{len(rows) - entry_count}"
                )


def _is_opposite(position_state: str, direction: str) -> bool:
    """Перевірити exact directional opposition до LONG або SHORT."""

    return (position_state, direction) in {("LONG", "SELL"), ("SHORT", "BUY")}


def _is_support(position_state: str, direction: str) -> bool:
    """Перевірити exact same-direction support для LONG або SHORT."""

    return (position_state, direction) in {("LONG", "BUY"), ("SHORT", "SELL")}


def _print_exit_labels(
    results: dict[str, dict[int, PeriodAnalysis]],
    close_reasons: tuple[str, ...],
) -> None:
    """Вивести factual exits лише для opposite-direction compositions."""

    print("FACTUAL_EXIT_LABELS")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            analysis = results[period][persistence]
            for class_name in SAME_CLASSES:
                direction = "BUY" if class_name.endswith("_BUY") else "SELL"
                for state in ("LONG", "SHORT"):
                    if not _is_opposite(state, direction):
                        continue
                    rows = analysis.cells[class_name][state]
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"class={class_name}|position_state={state}|"
                        f"bars_count={len(rows)}|"
                        "production_exit_before_next_m15_count="
                        f"{_exit_count(rows)}|position_still_open_count="
                        f"{_remains_count(rows)}|"
                        f"{_reason_counts(rows, close_reasons)}"
                    )


def _print_support_labels(
    results: dict[str, dict[int, PeriodAnalysis]],
) -> None:
    """Вивести factual remains/close для same-direction support."""

    print("SUPPORT_LABELS")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            analysis = results[period][persistence]
            for class_name in SAME_CLASSES:
                direction = "BUY" if class_name.endswith("_BUY") else "SELL"
                for state in ("LONG", "SHORT"):
                    if not _is_support(state, direction):
                        continue
                    rows = analysis.cells[class_name][state]
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"class={class_name}|position_state={state}|"
                        f"bars_count={len(rows)}|"
                        f"position_remains_open_count={_remains_count(rows)}|"
                        f"production_close_count={_exit_count(rows)}"
                    )


def _print_opposite_before_exit(
    replays: dict[str, Any],
    results: dict[str, dict[int, PeriodAnalysis]],
    close_reasons: tuple[str, ...],
) -> None:
    """Зіставити opposite evidence, next-bar outcome і factual exit timing."""

    print("OPPOSITE_SIGNAL_BEFORE_PRODUCTION_EXIT")
    for period in PERIOD_CODES:
        replay = replays[period]
        for persistence in PERSISTENCES:
            analysis = results[period][persistence]
            for class_name in SAME_CLASSES:
                direction = "BUY" if class_name.endswith("_BUY") else "SELL"
                for state in ("LONG", "SHORT"):
                    if not _is_opposite(state, direction):
                        continue
                    rows = analysis.cells[class_name][state]
                    metric = _metrics(replay, rows, direction)
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"class={class_name}|current_position={state}|"
                        f"composition_direction={direction}|"
                        f"bars_count={len(rows)}|"
                        "production_exit_before_next_m15_count="
                        f"{_exit_count(rows)}|"
                        "production_position_still_open_next_m15_count="
                        f"{_remains_count(rows)}|"
                        f"{_reason_counts(rows, close_reasons)}|"
                        "next_bar_directional_success_rate="
                        f"{_number(metric.success_rate)}|"
                        f"median_directional_edge_r={_number(metric.net_median)}"
                    )


def _action_fields(
    rows: tuple[ClassifiedRow, ...],
    direction: str,
    prefix: str = "",
) -> str:
    """Стиснути factual actions focus population без counterfactuals."""

    return (
        f"{prefix}entry_same_direction_count={_entry_count(rows, direction)}|"
        f"{prefix}exit_before_next_m15_count={_exit_count(rows)}|"
        f"{prefix}position_still_open_count={_remains_count(rows)}"
    )


def _print_focus(
    replays: dict[str, Any],
    results: dict[str, dict[int, PeriodAnalysis]],
) -> None:
    """Показати MS_BUY і MAS_SELL без approved-signal interpretation."""

    for focus in FOCUS_CLASSES:
        print(f"FOCUS_{focus}")
        direction = "BUY" if focus.endswith("_BUY") else "SELL"
        for period in PERIOD_CODES:
            replay = replays[period]
            for persistence in PERSISTENCES:
                analysis = results[period][persistence]
                for state in POSITION_STATES:
                    rows = analysis.cells[focus][state]
                    metric = _metrics(replay, rows, direction)
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"position_state={state}|bars_count={len(rows)}|"
                        f"success_rate={_number(metric.success_rate)}|"
                        f"median_edge_r={_number(metric.net_median)}|"
                        f"{_action_fields(rows, direction)}|"
                        f"sample_warning={_sample_warning(len(rows))}"
                    )


def _print_stability(
    replays: dict[str, Any],
    results: dict[str, dict[int, PeriodAnalysis]],
) -> None:
    """Поставити focus facts 2025/2026 поруч без stable threshold."""

    print("CROSS_PERIOD_STABILITY")
    for focus in FOCUS_CLASSES:
        direction = "BUY" if focus.endswith("_BUY") else "SELL"
        for persistence in PERSISTENCES:
            for state in POSITION_STATES:
                left_rows = results["2025"][persistence].cells[focus][state]
                right_rows = results["2026"][persistence].cells[focus][state]
                left = _metrics(replays["2025"], left_rows, direction)
                right = _metrics(replays["2026"], right_rows, direction)
                print(
                    f"class={focus}|persistence=P{persistence}|"
                    f"position_state={state}|2025_bars={len(left_rows)}|"
                    f"2025_success={_number(left.success_rate)}|"
                    f"2025_edge={_number(left.net_median)}|"
                    f"{_action_fields(left_rows, direction, '2025_')}|"
                    f"2026_bars={len(right_rows)}|"
                    f"2026_success={_number(right.success_rate)}|"
                    f"2026_edge={_number(right.net_median)}|"
                    f"{_action_fields(right_rows, direction, '2026_')}"
                )


def main() -> int:
    """Виконати T108-13 factual position-state anatomy і safety checks."""

    before_hashes = PRODUCTION_HASHES()
    print("T108_13_EXACT_FAMILY_COMPOSITION_POSITION_STATE_ANATOMY")
    replays: dict[str, Any] = {}
    runtimes: dict[str, Any] = {}
    positions: dict[str, dict[datetime, PositionLabel]] = {}
    results: dict[str, dict[int, PeriodAnalysis]] = {}
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        replay, runtime = _run_with_runtime(spec)
        replays[spec.code] = replay
        runtimes[spec.code] = runtime
        positions[spec.code] = _position_labels(replay, runtime)
        results[spec.code] = {
            persistence: _analyze(
                replay,
                persistence,
                positions[spec.code],
            )
            for persistence in PERSISTENCES
        }
    assert tuple(results) == PERIOD_CODES
    assert PRODUCTION_HASHES() == before_hashes

    actual_reasons = {
        trade.close_reason
        for runtime in runtimes.values()
        for trade in _trades(runtime)
    }
    close_reasons = BASE_CLOSE_REASONS + tuple(
        sorted(actual_reasons - set(BASE_CLOSE_REASONS))
    )
    _print_position_coverage(results)
    _print_compositions(replays, results)
    _print_entry_labels(results)
    _print_exit_labels(results, close_reasons)
    _print_support_labels(results)
    _print_opposite_before_exit(replays, results, close_reasons)
    _print_focus(replays, results)
    _print_stability(replays, results)

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=FACTUAL_PRODUCTION_POSITION_STATE_COMPLETED_M15_BARS")
    print("family_normalization=True")
    print("max_one_vote_per_family=True")
    print("supertrend_included=False")
    print("weights_used=False")
    print("score_threshold_selected=False")
    print("best_persistence_selected=False")
    print("counterfactual_trades_simulated=False")
    print("alternative_entry_simulated=False")
    print("alternative_exit_simulated=False")
    print("reverse_logic_created=False")
    print("production_actions_used_as_labels_only=True")
    print("decision_bar_in_future_window=False")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("optimization_performed=False")
    print("threshold_sweep_performed=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(
        "broker_requests=" f"{sum(item.broker_requests for item in replays.values())}"
    )
    print(
        "broker_execution_attempted="
        f"{any(item.broker_execution_attempted for item in replays.values())}"
    )
    print("T108_13_EXACT_FAMILY_COMPOSITION_POSITION_STATE_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
