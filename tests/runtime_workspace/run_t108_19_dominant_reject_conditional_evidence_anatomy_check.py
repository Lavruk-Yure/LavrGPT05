"""run_t108_19_dominant_reject_conditional_evidence_anatomy_check.py

T108-19 є TEST_ONLY anatomy домінантної factual reject-популяції
``MACD_EXTREMUM_TOO_WEAK`` усередині causal STRONG production Alligator
segments. Runner повторно використовує незмінені T108-08 residual-move rows
та completed M15 Replay, а потім незалежно накладає чотири вже наявні causal
контексти: production Alligator alignment, first opening expansion, H1 forward
projection і factual CURRENT_BAR Stochastic reject flag.

Для кожного каналу окремо друкуються present/absent групи 2025/2026, їхній
median residual move та descriptive 1R/2R outcome rates. Future movement є
лише outcome label: воно не формує classification, trades або entry/exit
рішення. Наперед зафіксований minimum ``n >= 20`` не оптимізується й лише
захищає cross-period verdict від малих груп.

Runner не поєднує канали, не створює score, weights, persistence, threshold,
counterfactual execution чи production wiring. Canonical Replay hashes,
відсутність broker requests/execution та completed-bar causality перевіряються
assertions; production, thresholds і MD7 не змінюються.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, TEST_ROOT, TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceMacdAlligatorReplayAlgorithm,
)

TEST_ID = "T108-19"
MODE = "RM108_T108_19_DOMINANT_REJECT_CONDITIONAL_EVIDENCE_ANATOMY_TEST_ONLY"
MINIMUM_GROUP_SIZE = 20
EPSILON = 1e-12
T108_08_FILE = (
    TEST_ROOT / "run_t108_08_macd_weak_reject_residual_segment_move_anatomy_check.py"
)
T108_10_FILE = TEST_ROOT / "run_t108_10_directional_signal_persistence_anatomy_check.py"


def _load_module(path: Path, name: str) -> ModuleType:
    """Завантажити retained runner з точного path без копіювання harness."""

    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T108_08 = _load_module(T108_08_FILE, "rm108_t108_19_t108_08")
T108_10 = _load_module(T108_10_FILE, "rm108_t108_19_t108_10")
PERIODS = getattr(T108_08, "PERIODS")
RUN_PERIOD: Callable[..., Any] = getattr(T108_08, "_run_period")
PRODUCTION_HASHES: Callable[[], Any] = getattr(T108_08, "_production_hashes")
BROKER_EXECUTION_ATTEMPTED: Callable[[Any], bool] = getattr(
    T108_08,
    "_broker_execution_attempted",
)
BASE_RUNTIME = getattr(T108_08, "StochasticAnatomyRuntime")
VIEW_ALLIGATOR_FAMILIES: Callable[..., Any] = getattr(
    T108_10,
    "_view_alligator_families",
)


@dataclass(frozen=True, slots=True)
class ConditionalRow:
    """Один factual reject з незалежними causal context labels."""

    period: str
    timestamp: datetime
    direction: str
    residual_move_r: float
    alligator_aligned: bool
    opening_expansion_aligned: bool | None
    h1_projection_aligned: bool | None
    stochastic_reject_flag: bool

    @property
    def reached_1r(self) -> bool:
        """Чи factual residual move досяг descriptive рівня 1R."""

        return self.residual_move_r + EPSILON >= 1.0

    @property
    def reached_2r(self) -> bool:
        """Чи factual residual move досяг descriptive рівня 2R."""

        return self.residual_move_r + EPSILON >= 2.0


@dataclass(frozen=True, slots=True)
class GroupStats:
    """Descriptive outcome summary однієї causal present/absent групи."""

    count: int
    median_move_r: float | None
    mean_move_r: float | None
    reached_1r: int
    reached_2r: int

    @property
    def reached_1r_rate(self) -> float | None:
        """Повернути 1R rate у відсотках або None для порожньої групи."""

        return 100.0 * self.reached_1r / self.count if self.count else None

    @property
    def reached_2r_rate(self) -> float | None:
        """Повернути 2R rate у відсотках або None для порожньої групи."""

        return 100.0 * self.reached_2r / self.count if self.count else None


def _run_with_runtime(spec: Any) -> tuple[Any, Any]:
    """Запустити exact T108-08 і зберегти його завершений runtime."""

    captured: list[Any] = []

    class CapturingRuntime(BASE_RUNTIME):
        """TEST_ONLY subclass, що лише відкриває завершений runtime anatomy."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured.append(self)

    setattr(T108_08, "StochasticAnatomyRuntime", CapturingRuntime)
    try:
        result = RUN_PERIOD(spec)
    finally:
        setattr(T108_08, "StochasticAnatomyRuntime", BASE_RUNTIME)
    assert len(captured) == 1
    runtime = captured[0]
    assert runtime.replay_session is not None
    assert runtime.replay_session.completed
    return result, runtime


def _alligator_side(observation: Any) -> str | None:
    """Відтворити production ACTIVE aligned directional semantics."""

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


def _direction_map(events: tuple[Any, ...]) -> dict[datetime, frozenset[str]]:
    """Згрупувати causal directional events без persistence або backfill."""

    result: dict[datetime, set[str]] = {}
    for event in events:
        result.setdefault(event.timestamp, set()).add(event.direction)
    return {key: frozenset(value) for key, value in result.items()}


def _conditional_rows(
    period: str,
    result: Any,
    runtime: Any,
) -> tuple[ConditionalRow, ...]:
    """Накласти незалежні causal contexts на exact T108-08 reject rows."""

    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    observations = {
        item.timestamp: item for item in algorithm.signal_filter.observations
    }
    strategy_events = tuple(
        runtime.strategy_events[key] for key in sorted(runtime.strategy_events)
    )
    expansion_events, projection_events = VIEW_ALLIGATOR_FAMILIES(strategy_events)
    expansion_map = _direction_map(tuple(expansion_events))
    projection_map = _direction_map(tuple(projection_events))
    record_reasons: dict[tuple[datetime, str], set[str]] = {}
    for record in runtime.historical_signal_records:
        key = (record.timestamp, record.direction)
        record_reasons.setdefault(key, set()).add(record.filter_reason_code)

    rows: list[ConditionalRow] = []
    for source in result.rows:
        observation = observations[source.signal_timestamp]
        reasons = record_reasons.get(
            (source.signal_timestamp, source.direction),
            set(),
        )
        rows.append(
            ConditionalRow(
                period=period,
                timestamp=source.signal_timestamp,
                direction=source.direction,
                residual_move_r=source.residual_move_r,
                alligator_aligned=(_alligator_side(observation) == source.direction),
                opening_expansion_aligned=(
                    source.direction
                    in expansion_map.get(source.signal_timestamp, frozenset())
                ),
                h1_projection_aligned=(
                    source.direction
                    in projection_map.get(source.signal_timestamp, frozenset())
                ),
                stochastic_reject_flag=(
                    ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS in reasons
                ),
            )
        )
    assert len(rows) == len(result.rows)
    return tuple(rows)


def _stats(rows: tuple[ConditionalRow, ...]) -> GroupStats:
    """Порахувати незважені descriptive residual outcome metrics."""

    values = tuple(row.residual_move_r for row in rows)
    return GroupStats(
        count=len(rows),
        median_move_r=median(values) if values else None,
        mean_move_r=mean(values) if values else None,
        reached_1r=sum(row.reached_1r for row in rows),
        reached_2r=sum(row.reached_2r for row in rows),
    )


def _format_optional(value: float | None, digits: int = 4) -> str:
    """Стабільно надрукувати numeric metric або NONE."""

    return "NONE" if value is None else f"{value:.{digits}f}"


def _print_group(channel: str, period: str, label: str, stats: GroupStats) -> None:
    """Надрукувати одну present/absent групу з усіма required metrics."""

    print(
        f"channel={channel}|period={period}|condition={label}|"
        f"n={stats.count}|median_residual_move_r="
        f"{_format_optional(stats.median_move_r)}|mean_residual_move_r="
        f"{_format_optional(stats.mean_move_r)}|reached_1r="
        f"{stats.reached_1r}|reached_1r_rate_percent="
        f"{_format_optional(stats.reached_1r_rate, 2)}|reached_2r="
        f"{stats.reached_2r}|reached_2r_rate_percent="
        f"{_format_optional(stats.reached_2r_rate, 2)}"
    )


def _channel_decision(
    rows_by_period: dict[str, tuple[ConditionalRow, ...]],
    attribute: str,
) -> str:
    """Застосувати predeclared conservative cross-period decision contract."""

    comparisons: list[tuple[float, float]] = []
    for period in ("2025", "2026"):
        rows = rows_by_period[period]
        if any(getattr(row, attribute) is None for row in rows):
            return "UNAVAILABLE"
        present = _stats(tuple(row for row in rows if getattr(row, attribute) is True))
        absent = _stats(tuple(row for row in rows if getattr(row, attribute) is False))
        if present.count < MINIMUM_GROUP_SIZE or absent.count < MINIMUM_GROUP_SIZE:
            return "SMALL_SAMPLE_ONLY"
        assert present.median_move_r is not None
        assert absent.median_move_r is not None
        assert present.reached_2r_rate is not None
        assert absent.reached_2r_rate is not None
        comparisons.append(
            (
                present.median_move_r - absent.median_move_r,
                present.reached_2r_rate - absent.reached_2r_rate,
            )
        )

    favorable = all(
        median_delta >= -EPSILON
        and rate_delta >= -EPSILON
        and (median_delta > EPSILON or rate_delta > EPSILON)
        for median_delta, rate_delta in comparisons
    )
    return "CONDITIONALLY_PROMISING" if favorable else "NO_STABLE_SEPARATION"


def _print_channel(
    channel: str,
    rows_by_period: dict[str, tuple[ConditionalRow, ...]],
    attribute: str,
) -> None:
    """Надрукувати paired groups каналу без causal treatment claim."""

    print(f"{channel.upper()}_PAIRED_PRESENT_ABSENT")
    for period in ("2025", "2026"):
        rows = rows_by_period[period]
        present_rows = tuple(row for row in rows if getattr(row, attribute) is True)
        absent_rows = tuple(row for row in rows if getattr(row, attribute) is False)
        unavailable = sum(getattr(row, attribute) is None for row in rows)
        present = _stats(present_rows)
        absent = _stats(absent_rows)
        _print_group(channel, period, "present", present)
        _print_group(channel, period, "absent", absent)
        print(
            f"channel={channel}|period={period}|unavailable={unavailable}|"
            "comparison_role=DESCRIPTIVE_ASSOCIATION_ONLY"
        )


def _print_rows(rows_by_period: dict[str, tuple[ConditionalRow, ...]]) -> None:
    """Надрукувати compact factual row audit усієї reject-популяції."""

    print("FACTUAL_REJECT_EVENT_ROWS")
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            print(
                f"{period}|{row.timestamp.isoformat()}|{row.direction}|"
                f"residual_move_r={row.residual_move_r:.4f}|"
                f"reached_1r={row.reached_1r}|reached_2r={row.reached_2r}|"
                f"alligator={row.alligator_aligned}|"
                f"opening={row.opening_expansion_aligned}|"
                f"h1_projection={row.h1_projection_aligned}|"
                f"stochastic_reject={row.stochastic_reject_flag}"
            )


def main() -> None:
    """Виконати T108-19, надрукувати verdicts і safety assertions."""

    production_before = PRODUCTION_HASHES()
    rows_by_period: dict[str, tuple[ConditionalRow, ...]] = {}
    broker_requests = 0
    execution_attempted = False
    for spec in PERIODS:
        result, runtime = _run_with_runtime(spec)
        rows = _conditional_rows(spec.code, result, runtime)
        rows_by_period[spec.code] = rows
        broker_requests += result.broker_requests
        execution_attempted = execution_attempted or BROKER_EXECUTION_ATTEMPTED(runtime)
        print(f"period={spec.code}")
        print(f"  production_baseline={result.baseline}")
        print(f"  factual_reject_events={len(rows)}")

    assert set(rows_by_period) == {"2025", "2026"}
    assert broker_requests == 0
    assert not execution_attempted
    assert PRODUCTION_HASHES() == production_before

    channels = (
        ("production_alligator_context", "alligator_aligned"),
        ("first_opening_expansion_context", "opening_expansion_aligned"),
        ("h1_projection_context", "h1_projection_aligned"),
        ("stochastic_reject_flag", "stochastic_reject_flag"),
    )
    for channel, attribute in channels:
        _print_channel(channel, rows_by_period, attribute)
    _print_rows(rows_by_period)

    decisions = {
        channel: (
            "DESCRIPTIVE_ONLY"
            if channel == "stochastic_reject_flag"
            else _channel_decision(rows_by_period, attribute)
        )
        for channel, attribute in channels
    }
    promising = any(
        value == "CONDITIONALLY_PROMISING"
        for key, value in decisions.items()
        if key != "stochastic_reject_flag"
    )

    print("CONDITIONAL_EVIDENCE_DECISIONS")
    for channel, _attribute in channels:
        print(f"{channel}={decisions[channel]}")
    print(
        "NEXT_STEP="
        + (
            "ORTHOGONAL_EVIDENCE_COMBINATION_ANATOMY_REQUIRED"
            if promising
            else "NO_CONDITIONAL_RESCUE_EVIDENCE"
        )
    )
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=factual_reject_events_only")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("generic_score_model_created=False")
    print("weights_used=False")
    print("persistence_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("counterfactual_trades_simulated=False")
    print("new_entry_logic=False")
    print("new_exit_logic=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={execution_attempted}")
    print("T108_19_DOMINANT_REJECT_CONDITIONAL_EVIDENCE_ANATOMY=OK")


if __name__ == "__main__":
    main()
