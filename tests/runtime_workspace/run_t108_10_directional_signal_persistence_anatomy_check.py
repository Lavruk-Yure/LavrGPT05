"""run_t108_10_directional_signal_persistence_anatomy_check.py — T108-10.

TEST_ONLY anatomy відтворює сім уже досліджених causal directional event
families на двох фактичних cTrader Replay періодах і вимірює їхній factual
рух лише на наступних H1..H5 completed M15 bars. Signal bar виключено з
future window; R формується тільки з його range і відомого spread.

Події нормалізовано як одноразові переходи: accepted extended-quality MACD
cross, combined relative restart/dominant acceleration, початок contiguous
ACTIVE Alligator state, first opening expansion, causal H1 forward-geometry
projection, Stochastic 14/1/3 K/D cross і Supertrend(10,3) direction switch.
Future HIGH/LOW є лише outcome labels; runner не створює trades, score,
weights, threshold sweep, lifetime selection, entry/exit rules і не змінює
production або MD7. Результат — compact deterministic H1..H5 summary та
cross-period decay без aggregate verdict.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, TEST_ROOT, TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_replay_virtual_execution_check import (  # noqa: E402
    BrokerRequestProbe,
)
from run_t105_10_pd_35_production_regression_check import _workspace  # noqa: E402
from run_t105_15_stochastic_entry_anatomy_check import (  # noqa: E402
    CROSS_DOWN,
    CROSS_UP,
    StochasticAnatomyRuntime,
    _canonical_stochastic,
    _cross_direction,
    _production_hashes,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (  # noqa: E402, E501
    PERIODS,
    _assert_geometry,
    _assert_metrics,
    _assert_policy,
    _assert_stochastic_path,
    _broker_execution_attempted,
)
from run_t108_06_production_reject_anatomy_strong_trend_segments_check import (  # noqa: E402, E501
    _segments,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING,
    WorkspaceAlligatorCausalProjection,
    WorkspaceAlligatorFilter,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

TEST_ID = "T108-10"
MODE = "RM108_T108_10_DIRECTIONAL_SIGNAL_PERSISTENCE_ANATOMY_TEST_ONLY"
HORIZONS = (1, 2, 3, 4, 5)
EPSILON = 1e-12
FAMILIES = (
    "MACD_CROSS_EXTENDED_QUALITY",
    "MACD_RELATIVE_RESTART_DOMINANT_ACCELERATION",
    "ALLIGATOR_ACTIVE_DIRECTION_START",
    "ALLIGATOR_FIRST_OPENING_EXPANSION",
    "ALLIGATOR_FORWARD_SHIFT_H1_PROJECTION_EVENT",
    "STOCHASTIC_KD_CROSS_14_1_3",
    "SUPERTREND_DIRECTION_SWITCH_10_3",
)

OPENING_SCRIPT = (
    "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
)
RESTART_SCRIPT = (
    "run_t104_10_algorithm_workspace_macd_momentum_freshness_through_"
    "donchian_pullback_2025_2026_check.py"
)
SUPERTREND_SCRIPT = (
    "run_t104_24_algorithm_workspace_supertrend_dynamic_sl_exit_anatomy_"
    "2025_2026_check.py"
)


def _load_test_module(file_name: str, module_name: str) -> ModuleType:
    """Завантажити factual TEST_ONLY dependency з явного runtime_temp path."""

    file_path = TEMP_ROOT / file_name
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


OPENING = _load_test_module(OPENING_SCRIPT, "rm108_t108_10_opening")
RESTART = _load_test_module(RESTART_SCRIPT, "rm108_t108_10_restart")
SUPERTREND = _load_test_module(SUPERTREND_SCRIPT, "rm108_t108_10_supertrend")
OPENING_PRIMARY = getattr(OPENING, "BASE")

OPENING_IS_EXPANSION: Callable[..., bool] = getattr(
    OPENING,
    "_is_expansion_from_compressed",
)
OPENING_DIRECTION: Callable[..., str | None] = getattr(
    OPENING,
    "_incipient_opening_direction",
)
RESTART_WINDOWS = getattr(RESTART, "WINDOWS")
RESTART_RUN_BASE: Callable[..., Any] = getattr(RESTART, "_run_base_window")
RESTART_LOAD_INDICATORS: Callable[..., Any] = getattr(
    RESTART,
    "_load_indicator_run",
)
RESTART_ANATOMY: Callable[..., Any] = getattr(RESTART, "_anatomy")
CANONICAL_SUPERTREND: Callable[..., Any] = getattr(
    SUPERTREND,
    "_canonical_supertrend",
)
ALLIGATOR_RUNTIME_PROFILE: Callable[..., Any] = getattr(
    OPENING_PRIMARY,
    "_alligator_runtime_profile",
)


@dataclass(frozen=True, slots=True)
class DirectionalEvent:
    """Одна causal-known directional подія на completed M15 signal bar."""

    timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    """Описові outcome-метрики однієї family/period/horizon комірки."""

    events: int
    successes: int
    success_rate: float | None
    favorable_median: float | None
    adverse_median: float | None
    net_median: float | None


@dataclass(frozen=True, slots=True)
class FamilyPeriodResult:
    """Події та H1..H5 summary однієї family в одному Replay періоді."""

    events: tuple[DirectionalEvent, ...]
    horizons: dict[int, HorizonMetrics]


@dataclass(frozen=True, slots=True)
class PeriodReplay:
    """Незмінений production Replay і потрібні post-hoc event families."""

    events: tuple[WorkspaceMarketEvent, ...]
    families: dict[str, tuple[DirectionalEvent, ...]]
    broker_requests: int
    broker_execution_attempted: bool


def _event_rows(
    rows: list[DirectionalEvent] | tuple[DirectionalEvent, ...],
) -> tuple[DirectionalEvent, ...]:
    """Нормалізувати candidate rows до однієї event на timestamp/direction."""

    unique = {(item.timestamp, item.direction): item for item in rows}
    ordered = tuple(unique[key] for key in sorted(unique))
    assert all(item.direction in {"BUY", "SELL"} for item in ordered)
    return ordered


def _projection_direction(
    projection: WorkspaceAlligatorCausalProjection,
) -> str | None:
    """Визначити напрям лише з causal forward-shift line geometry."""

    slope = projection.center_slope_per_bar
    if slope is None:
        return None
    if projection.lips > projection.jaw and slope > 0.0:
        return "BUY"
    if projection.lips < projection.jaw and slope < 0.0:
        return "SELL"
    return None


def _projected_h1_opening(
    projections: tuple[WorkspaceAlligatorCausalProjection, ...],
    previous_observation: Any,
) -> str | None:
    """Відтворити T104-14 H1 causal first-expansion event без future price."""

    if len(projections) < 2:
        return None
    current = projections[0]
    forward = projections[1]
    if (
        current.normalized_opening is None
        or forward.normalized_opening is None
        or current.range_reference is None
        or current.range_reference <= 0.0
        or previous_observation.opening is None
    ):
        return None
    if current.normalized_opening > ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING:
        return None
    if forward.normalized_opening <= current.normalized_opening + EPSILON:
        return None
    previous_normalized = float(previous_observation.opening) / current.range_reference
    current_was_already_expanding = bool(
        previous_normalized <= ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING
        and current.normalized_opening > previous_normalized + EPSILON
    )
    if current_was_already_expanding:
        return None
    return _projection_direction(forward)


def _view_alligator_families(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[tuple[DirectionalEvent, ...], tuple[DirectionalEvent, ...]]:
    """Відтворити canonical first expansion і H1 projection causal streams."""

    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=ALLIGATOR_RUNTIME_PROFILE(),
        timeframe="M15",
    )
    observations: list[Any] = []
    projection_history: list[tuple[WorkspaceAlligatorCausalProjection, ...]] = []
    for event in events:
        available_at = event.timestamp + timedelta(minutes=15)
        observations.append(
            signal_filter.on_market_event(event, available_at=available_at)
        )
        projection_history.append(signal_filter.causal_forward_projections())

    observation_tuple = tuple(observations)
    expansion_rows: list[DirectionalEvent] = []
    for index, event in enumerate(events):
        if not OPENING_IS_EXPANSION(observation_tuple, index):
            continue
        direction = OPENING_DIRECTION(observation_tuple[index])
        if direction is not None:
            expansion_rows.append(DirectionalEvent(event.timestamp, direction))

    projection_rows: list[DirectionalEvent] = []
    for index in range(1, len(events)):
        direction = _projected_h1_opening(
            projection_history[index],
            observation_tuple[index - 1],
        )
        if direction is not None:
            projection_rows.append(DirectionalEvent(events[index].timestamp, direction))
    return _event_rows(expansion_rows), _event_rows(projection_rows)


def _stochastic_events(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[DirectionalEvent, ...]:
    """Зібрати тільки фактичні completed-bar K/D crosses 14/1/3."""

    percent_k, percent_d = _canonical_stochastic(events)
    rows: list[DirectionalEvent] = []
    for index in range(1, len(events)):
        values = (
            percent_k[index - 1],
            percent_d[index - 1],
            percent_k[index],
            percent_d[index],
        )
        if None in values:
            continue
        direction = _cross_direction(*(float(value) for value in values))
        if direction == CROSS_UP:
            rows.append(DirectionalEvent(events[index].timestamp, "BUY"))
        elif direction == CROSS_DOWN:
            rows.append(DirectionalEvent(events[index].timestamp, "SELL"))
    return _event_rows(rows)


def _supertrend_events(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[DirectionalEvent, ...]:
    """Зібрати лише factual canonical Supertrend(10,3) state switches."""

    points = CANONICAL_SUPERTREND(events)
    rows = [
        DirectionalEvent(events[index].timestamp, str(point.state))
        for index, point in enumerate(points)
        if point.switched and point.state in {"BUY", "SELL"}
    ]
    return _event_rows(rows)


def _fresh_restart(anatomy: Any) -> bool:
    """Повторити T104-11 causal transition у favorable MACD momentum."""

    return bool(
        anatomy.signal_momentum_favorable and not anatomy.pre_signal_momentum_favorable
    )


def _dominant_acceleration(anatomy: Any) -> bool:
    """Повторити T104-11 relative delta > absolute histogram relation."""

    return bool(
        anatomy.signal_momentum_favorable
        and anatomy.signal_histogram_delta > abs(anatomy.signal_histogram) + EPSILON
    )


def _restart_events(period: str) -> tuple[DirectionalEvent, ...]:
    """Відтворити T104-11 combined restart event і його causal signal bar."""

    window = next(
        item for item in RESTART_WINDOWS if str(item.label).startswith(period)
    )
    base = RESTART_RUN_BASE(window)
    indicator_run = RESTART_LOAD_INDICATORS(window)
    rows: list[DirectionalEvent] = []
    for candidate, row in zip(base["candidates"], base["rows"]):
        if (
            row.reentry_trade is None
            or row.pullback_index is None
            or row.signal_index is None
        ):
            continue
        anatomy = RESTART_ANATOMY(indicator_run, candidate, row)
        if not (_fresh_restart(anatomy) and _dominant_acceleration(anatomy)):
            continue
        signal_index = int(row.signal_index)
        rows.append(
            DirectionalEvent(
                indicator_run.events[signal_index].timestamp,
                str(candidate.direction),
            )
        )
    return _event_rows(rows)


def _run_period(spec: Any) -> PeriodReplay:
    """Запустити production Replay і побудувати сім post-hoc event streams."""

    broker_probe = BrokerRequestProbe()
    runtime = StochasticAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
    )
    _assert_policy(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_metrics(spec, runtime)
    _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    source = algorithm.source
    signal_filter = algorithm.signal_filter
    assert source is not None and signal_filter is not None

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    indexes = {event.timestamp: index for index, event in enumerate(events)}
    assert len(indexes) == len(events)
    assert all(event.timeframe == "M15" for event in events)

    macd_quality = _event_rows(
        [
            DirectionalEvent(item.timestamp, item.direction)
            for item in source.quality_diagnostics
            if item.final_quality_pass
        ]
    )
    active_starts = _event_rows(
        [
            DirectionalEvent(segment.start_timestamp, segment.side)
            for segment in _segments(tuple(signal_filter.observations))
        ]
    )
    opening_events, projection_events = _view_alligator_families(events)
    family_events = {
        "MACD_CROSS_EXTENDED_QUALITY": macd_quality,
        "MACD_RELATIVE_RESTART_DOMINANT_ACCELERATION": _restart_events(spec.code),
        "ALLIGATOR_ACTIVE_DIRECTION_START": active_starts,
        "ALLIGATOR_FIRST_OPENING_EXPANSION": opening_events,
        "ALLIGATOR_FORWARD_SHIFT_H1_PROJECTION_EVENT": projection_events,
        "STOCHASTIC_KD_CROSS_14_1_3": _stochastic_events(events),
        "SUPERTREND_DIRECTION_SWITCH_10_3": _supertrend_events(events),
    }
    assert tuple(family_events) == FAMILIES
    assert all(
        item.timestamp in indexes for rows in family_events.values() for item in rows
    )
    attempted = _broker_execution_attempted(runtime)
    assert broker_probe.requests == 0
    assert not attempted
    return PeriodReplay(events, family_events, broker_probe.requests, attempted)


def _metrics(
    events: tuple[WorkspaceMarketEvent, ...],
    directional_events: tuple[DirectionalEvent, ...],
    horizon: int,
) -> HorizonMetrics:
    """Порахувати descriptive directional labels на наступних bars."""

    indexes = {event.timestamp: index for index, event in enumerate(events)}
    favorable_values: list[float] = []
    adverse_values: list[float] = []
    net_values: list[float] = []
    successes = 0
    for directional_event in directional_events:
        index = indexes[directional_event.timestamp]
        if index + horizon >= len(events):
            continue
        signal_bar = events[index]
        future = events[slice(index + 1, index + horizon + 1)]
        assert len(future) == horizon
        risk = max(
            float(signal_bar.high) - float(signal_bar.low),
            float(signal_bar.spread) * 10.0,
        )
        assert risk > 0.0
        if directional_event.direction == "BUY":
            favorable = max(float(item.high) for item in future) - float(
                signal_bar.close
            )
            adverse = float(signal_bar.close) - min(float(item.low) for item in future)
        else:
            favorable = float(signal_bar.close) - min(
                float(item.low) for item in future
            )
            adverse = max(float(item.high) for item in future) - float(signal_bar.close)
        favorable_r = favorable / risk
        adverse_r = adverse / risk
        net_r = favorable_r - adverse_r
        favorable_values.append(favorable_r)
        adverse_values.append(adverse_r)
        net_values.append(net_r)
        successes += favorable_r > adverse_r

    count = len(net_values)
    return HorizonMetrics(
        events=count,
        successes=successes,
        success_rate=None if not count else 100.0 * successes / count,
        favorable_median=(
            None if not favorable_values else float(statistics.median(favorable_values))
        ),
        adverse_median=(
            None if not adverse_values else float(statistics.median(adverse_values))
        ),
        net_median=None if not net_values else float(statistics.median(net_values)),
    )


def _number(value: float | None) -> str:
    """Форматувати deterministic metric або NONE для порожньої population."""

    return "NONE" if value is None else f"{value:.4f}"


def _summarize(replay: PeriodReplay) -> dict[str, FamilyPeriodResult]:
    """Побудувати H1..H5 summaries для кожної дозволеної family."""

    return {
        family: FamilyPeriodResult(
            events=replay.families[family],
            horizons={
                horizon: _metrics(
                    replay.events,
                    replay.families[family],
                    horizon,
                )
                for horizon in HORIZONS
            },
        )
        for family in FAMILIES
    }


def _print_family_period(period: str, result: FamilyPeriodResult) -> None:
    """Надрукувати compact metrics одного family/period блоку."""

    directions = Counter(item.direction for item in result.events)
    print(f"period={period}")
    print(f"BUY_events={directions['BUY']}")
    print(f"SELL_events={directions['SELL']}")
    for horizon in HORIZONS:
        row = result.horizons[horizon]
        print(
            f"H{horizon}|events={row.events}|success={row.successes}|"
            f"success_rate_percent={_number(row.success_rate)}|"
            f"favorable_r_median={_number(row.favorable_median)}|"
            f"adverse_r_median={_number(row.adverse_median)}|"
            f"net_edge_r_median={_number(row.net_median)}"
        )


def _series(result: FamilyPeriodResult, attribute: str) -> str:
    """Сформувати H1..H5 series для cross-period decay table."""

    values = []
    for horizon in HORIZONS:
        row = result.horizons[horizon]
        value = getattr(row, attribute)
        values.append(f"H{horizon}:{_number(value)}")
    return ",".join(values)


def main() -> int:
    """Виконати T108-10 без production mutation або lifetime selection."""

    before_hashes = _production_hashes()
    print("T108_10_DIRECTIONAL_SIGNAL_PERSISTENCE_ANATOMY")
    replays: dict[str, PeriodReplay] = {}
    summaries: dict[str, dict[str, FamilyPeriodResult]] = {}
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        replay = _run_period(spec)
        replays[spec.code] = replay
        summaries[spec.code] = _summarize(replay)
    assert _production_hashes() == before_hashes

    for family in FAMILIES:
        print(f"FAMILY={family}")
        for period in ("2025", "2026"):
            _print_family_period(period, summaries[period][family])

    print("CROSS_PERIOD_SIGNAL_DECAY")
    for family in FAMILIES:
        print(f"family={family}")
        print(
            "2025_success_rates="
            f"{_series(summaries['2025'][family], 'success_rate')}"
        )
        print(
            "2026_success_rates="
            f"{_series(summaries['2026'][family], 'success_rate')}"
        )
        print(
            "2025_net_edge_medians="
            f"{_series(summaries['2025'][family], 'net_median')}"
        )
        print(
            "2026_net_edge_medians="
            f"{_series(summaries['2026'][family], 'net_median')}"
        )

    print("UNAVAILABLE_SOURCES")
    print("NONE")
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=FACTUAL_CAUSAL_DIRECTIONAL_EVENTS")
    print("signal_bar_in_future_window=False")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("best_lifetime_selected=False")
    print("score_model_created=False")
    print("weights_created=False")
    print("counterfactual_trades_simulated=False")
    print("new_entry_rule_created=False")
    print("new_exit_rule_created=False")
    print("alternative_exit_simulated=False")
    print("production_threshold_changed=False")
    print("production_logic_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={sum(item.broker_requests for item in replays.values())}")
    print(
        "broker_execution_attempted="
        f"{any(item.broker_execution_attempted for item in replays.values())}"
    )
    print("T108_10_DIRECTIONAL_SIGNAL_PERSISTENCE_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
