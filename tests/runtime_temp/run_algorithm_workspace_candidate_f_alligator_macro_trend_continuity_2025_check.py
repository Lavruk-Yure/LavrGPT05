# -*- coding: utf-8 -*-
"""RoadMap103 / 7J: continuity diagnostic макро-тренду Alligator за 2025.

Diagnostic-only runner перевіряє гіпотезу, що один візуально цілісний
Alligator-тренд може бути розбитий runtime на кілька окремих ACTIVE runs.
Макро-тренд тут НЕ є новим trading gate і не змінює production logic.

Кандидатне diagnostic-визначення макро-тренду:
- regime лишається TREND_UP або TREND_DOWN в одному напрямку;
- STARTING / ACTIVE / ENDING усередині цього regime не розривають trend;
- короткий пропуск даних до 4 відсутніх M15 bars дозволено мостити;
- FLAT, протилежний regime або більший data gap завершують macro trend.

Окремо фіксується контрольний ручний приклад 2025-09-08..09: run_id
733 належить ширшому BUY macro trend разом з ACTIVE runs 732..737.
Future price не використовується як feature або gate.
"""

from __future__ import annotations

import csv
import math
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

EXPECTED_BASELINE = (59, 40, 18, 1, 9, -4.05, 0.7808, 5.80)
M15 = timedelta(minutes=15)
MAX_MISSING_M15_BARS_TO_BRIDGE = 4
MAX_OBSERVATION_INTERVAL = M15 * (MAX_MISSING_M15_BARS_TO_BRIDGE + 1)
CASE_ACTIVE_RUN_ID = 733

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7J_Alligator_Macro_Trend_Continuity_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "alligator_macro_trends_2025.csv"


@dataclass(frozen=True, slots=True)
class ActiveRun:
    """Один строгий contiguous directional ACTIVE run."""

    run_id: int
    direction: str
    observations: tuple[WorkspaceAlligatorObservation, ...]

    @property
    def start_utc(self) -> datetime:
        return self.observations[0].timestamp

    @property
    def end_utc(self) -> datetime:
        return self.observations[-1].timestamp


@dataclass(frozen=True, slots=True)
class MacroTrend:
    """Diagnostic same-regime macro trend, який може містити ACTIVE паузи."""

    macro_id: int
    direction: str
    observations: tuple[WorkspaceAlligatorObservation, ...]
    active_runs: tuple[ActiveRun, ...]

    @property
    def start_utc(self) -> datetime:
        return self.observations[0].timestamp

    @property
    def end_utc(self) -> datetime:
        return self.observations[-1].timestamp


@dataclass(frozen=True, slots=True)
class Interruption:
    """Проміжок між двома ACTIVE runs одного macro trend."""

    from_run_id: int
    to_run_id: int
    kind: str
    observed_nonactive_bars: int
    missing_m15_bars: int
    phases: str
    states: str
    minimum_opening: float | None
    minimum_slope: float | None


class MacroTrendRuntime(WorkspaceRuntime):
    """Production Runtime без зміни execution для diagnostic Replay."""


def _active_direction(observation: WorkspaceAlligatorObservation) -> str | None:
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return None
    if (
        observation.state == ALLIGATOR_STATE_BULLISH
        and observation.regime == ALLIGATOR_REGIME_TREND_UP
    ):
        return "BUY"
    if (
        observation.state == ALLIGATOR_STATE_BEARISH
        and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
    ):
        return "SELL"
    return None


def _regime_direction(observation: WorkspaceAlligatorObservation) -> str | None:
    if observation.regime == ALLIGATOR_REGIME_TREND_UP:
        return "BUY"
    if observation.regime == ALLIGATOR_REGIME_TREND_DOWN:
        return "SELL"
    return None


def _split_active_runs(
    observations: tuple[WorkspaceAlligatorObservation, ...],
) -> tuple[ActiveRun, ...]:
    raw_runs: list[tuple[str, tuple[WorkspaceAlligatorObservation, ...]]] = []
    current: list[WorkspaceAlligatorObservation] = []
    current_direction: str | None = None
    previous_timestamp: datetime | None = None

    for observation in observations:
        direction = _active_direction(observation)
        contiguous = (
            previous_timestamp is not None
            and observation.timestamp - previous_timestamp == M15
        )
        if direction is None:
            if current:
                assert current_direction is not None
                raw_runs.append((current_direction, tuple(current)))
                current = []
            current_direction = None
            previous_timestamp = observation.timestamp
            continue
        if current and (direction != current_direction or not contiguous):
            assert current_direction is not None
            raw_runs.append((current_direction, tuple(current)))
            current = []
        current.append(observation)
        current_direction = direction
        previous_timestamp = observation.timestamp

    if current:
        assert current_direction is not None
        raw_runs.append((current_direction, tuple(current)))

    return tuple(
        ActiveRun(run_id=index, direction=direction, observations=run)
        for index, (direction, run) in enumerate(raw_runs, start=1)
    )


def _split_macro_trends(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    active_runs: tuple[ActiveRun, ...],
) -> tuple[MacroTrend, ...]:
    raw_macros: list[tuple[str, tuple[WorkspaceAlligatorObservation, ...]]] = []
    current: list[WorkspaceAlligatorObservation] = []
    current_direction: str | None = None
    previous_timestamp: datetime | None = None

    for observation in observations:
        direction = _regime_direction(observation)
        interval_allowed = (
            previous_timestamp is None
            or observation.timestamp - previous_timestamp <= MAX_OBSERVATION_INTERVAL
        )
        must_break = current and (
            direction is None or direction != current_direction or not interval_allowed
        )
        if must_break:
            assert current_direction is not None
            raw_macros.append((current_direction, tuple(current)))
            current = []
            current_direction = None

        if direction is not None:
            current.append(observation)
            current_direction = direction

        previous_timestamp = observation.timestamp

    if current:
        assert current_direction is not None
        raw_macros.append((current_direction, tuple(current)))

    macros: list[MacroTrend] = []
    for macro_id, (direction, macro_observations) in enumerate(
        raw_macros,
        start=1,
    ):
        start_utc = macro_observations[0].timestamp
        end_utc = macro_observations[-1].timestamp
        contained_runs = tuple(
            active_run
            for active_run in active_runs
            if active_run.direction == direction
            and start_utc <= active_run.start_utc
            and active_run.end_utc <= end_utc
        )
        macros.append(
            MacroTrend(
                macro_id=macro_id,
                direction=direction,
                observations=macro_observations,
                active_runs=contained_runs,
            )
        )
    return tuple(macros)


def _interruption(
    macro: MacroTrend,
    left: ActiveRun,
    right: ActiveRun,
) -> Interruption:
    between = tuple(
        observation
        for observation in macro.observations
        if left.end_utc < observation.timestamp < right.start_utc
    )
    expected_slots = max(
        0,
        int((right.start_utc - left.end_utc) / M15) - 1,
    )
    missing_bars = max(0, expected_slots - len(between))
    if between and missing_bars:
        kind = "MIXED_PHASE_AND_DATA_GAP"
    elif between:
        kind = "OBSERVED_PHASE_PAUSE"
    else:
        kind = "MISSING_DATA_GAP"

    openings = tuple(
        float(observation.normalized_opening)
        for observation in between
        if observation.normalized_opening is not None
    )
    slopes = tuple(
        float(observation.normalized_slope)
        for observation in between
        if observation.normalized_slope is not None
    )
    return Interruption(
        from_run_id=left.run_id,
        to_run_id=right.run_id,
        kind=kind,
        observed_nonactive_bars=len(between),
        missing_m15_bars=missing_bars,
        phases="|".join(sorted({observation.regime_phase for observation in between})),
        states="|".join(sorted({observation.state for observation in between})),
        minimum_opening=min(openings) if openings else None,
        minimum_slope=min(slopes) if slopes else None,
    )


def _assert_baseline(runtime: MacroTrendRuntime) -> None:
    summary = runtime.historical_summary
    assert summary is not None
    expected = EXPECTED_BASELINE
    assert summary.opened_trades == expected[0]
    assert summary.winning_trades == expected[1]
    assert summary.losing_trades == expected[2]
    assert summary.break_even_trades == expected[3]
    assert summary.close_reason_count("STOP_LOSS") == expected[4]
    assert math.isclose(summary.net_profit, expected[5], abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, expected[6], abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, expected[7], abs_tol=0.005)


def _run_diagnostic() -> tuple[
    tuple[ActiveRun, ...],
    tuple[MacroTrend, ...],
    MacroTrendRuntime,
]:
    runtime = MacroTrendRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_baseline(runtime)
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    observations = tuple(signal_filter.observations)
    active_runs = _split_active_runs(observations)
    macros = _split_macro_trends(observations, active_runs)
    return active_runs, macros, runtime


def _write_csv(macros: tuple[MacroTrend, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "macro_id",
        "direction",
        "start_utc",
        "end_utc",
        "elapsed_hours",
        "observed_bars",
        "active_bars",
        "nonactive_observed_bars",
        "missing_m15_bars_inside",
        "active_run_count",
        "active_run_ids",
        "opening_start",
        "opening_end",
        "slope_start",
        "slope_end",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for macro in macros:
            active_bars = sum(
                len(active_run.observations) for active_run in macro.active_runs
            )
            expected_bars = int((macro.end_utc - macro.start_utc) / M15) + 1
            missing_bars = max(0, expected_bars - len(macro.observations))
            first = macro.observations[0]
            last = macro.observations[-1]
            elapsed_hours = (
                macro.end_utc - macro.start_utc
            ).total_seconds() / 3600
            writer.writerow(
                {
                    "macro_id": macro.macro_id,
                    "direction": macro.direction,
                    "start_utc": macro.start_utc.isoformat(),
                    "end_utc": macro.end_utc.isoformat(),
                    "elapsed_hours": f"{elapsed_hours:.2f}",
                    "observed_bars": len(macro.observations),
                    "active_bars": active_bars,
                    "nonactive_observed_bars": len(macro.observations) - active_bars,
                    "missing_m15_bars_inside": missing_bars,
                    "active_run_count": len(macro.active_runs),
                    "active_run_ids": "|".join(
                        str(active_run.run_id) for active_run in macro.active_runs
                    ),
                    "opening_start": (
                        ""
                        if first.normalized_opening is None
                        else f"{first.normalized_opening:.6f}"
                    ),
                    "opening_end": (
                        ""
                        if last.normalized_opening is None
                        else f"{last.normalized_opening:.6f}"
                    ),
                    "slope_start": (
                        ""
                        if first.normalized_slope is None
                        else f"{first.normalized_slope:.6f}"
                    ),
                    "slope_end": (
                        ""
                        if last.normalized_slope is None
                        else f"{last.normalized_slope:.6f}"
                    ),
                }
            )
    return OUTPUT_CSV


def _format_optional(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def main() -> None:
    assert_frozen_oos_snapshot()
    active_runs, macros, runtime = _run_diagnostic()

    macros_with_active = tuple(macro for macro in macros if macro.active_runs)
    active_run_distribution = Counter(len(macro.active_runs) for macro in macros)
    assert len(active_runs) == 1077
    assert len(macros) == 957
    assert len(macros_with_active) == 672
    assert sum(len(macro.active_runs) for macro in macros) == len(active_runs)
    assert (
        sum(
            count
            for run_count, count in active_run_distribution.items()
            if run_count >= 2
        )
        == 230
    )
    assert (
        sum(
            count
            for run_count, count in active_run_distribution.items()
            if run_count >= 3
        )
        == 102
    )
    assert (
        sum(
            count
            for run_count, count in active_run_distribution.items()
            if run_count >= 4
        )
        == 46
    )

    case_run = next(
        active_run
        for active_run in active_runs
        if active_run.run_id == CASE_ACTIVE_RUN_ID
    )
    case_macro = next(
        macro
        for macro in macros
        if any(
            active_run.run_id == CASE_ACTIVE_RUN_ID for active_run in macro.active_runs
        )
    )
    case_run_ids = tuple(active_run.run_id for active_run in case_macro.active_runs)
    assert case_run.direction == "BUY"
    assert case_run.start_utc.isoformat() == "2025-09-08T12:15:00+00:00"
    assert case_run.end_utc.isoformat() == "2025-09-08T17:15:00+00:00"
    assert case_macro.macro_id == 641
    assert case_macro.direction == "BUY"
    assert case_macro.start_utc.isoformat() == "2025-09-08T07:15:00+00:00"
    assert case_macro.end_utc.isoformat() == "2025-09-09T07:45:00+00:00"
    assert case_run_ids == (732, 733, 734, 735, 736, 737)

    case_active_bars = sum(
        len(active_run.observations) for active_run in case_macro.active_runs
    )
    case_expected_bars = int((case_macro.end_utc - case_macro.start_utc) / M15) + 1
    case_missing_bars = max(
        0,
        case_expected_bars - len(case_macro.observations),
    )
    assert len(case_macro.observations) == 96
    assert case_active_bars == 68
    assert len(case_macro.observations) - case_active_bars == 28
    assert case_missing_bars == 3

    interruptions = tuple(
        _interruption(case_macro, left, right)
        for left, right in zip(
            case_macro.active_runs,
            case_macro.active_runs[1:],
        )
    )
    assert len(interruptions) == 5
    assert sum(item.kind == "OBSERVED_PHASE_PAUSE" for item in interruptions) == 3
    assert sum(item.kind == "MISSING_DATA_GAP" for item in interruptions) == 2
    assert sum(item.missing_m15_bars for item in interruptions) == 3
    assert all(
        _regime_direction(observation) == "BUY"
        for observation in case_macro.observations
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    output_csv = _write_csv(macros)

    print(
        "Algorithm Workspace Candidate F Alligator Macro Trend "
        "Continuity 2025 result"
    )
    print("  mode=PRODUCTION_6K_CAUSAL_MACRO_TREND_CONTINUITY_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  signal_filter_applied=False")
    print("  alternative_entry_applied=False")
    print("  future_price_used_as_feature=False")
    print("  period=2025_frozen")
    print(
        "  macro_definition=same_direction_regime_with_STARTING_ACTIVE_ENDING_"
        "continuity"
    )
    print(
        "  missing_data_bridge="
        f"up_to_{MAX_MISSING_M15_BARS_TO_BRIDGE}_missing_M15_bars"
    )
    print("  flat_or_opposite_regime_breaks_macro=True")
    print(f"  strict_active_runs={len(active_runs)}")
    print(f"  macro_trends={len(macros)}")
    print(f"  macro_trends_with_active={len(macros_with_active)}")
    print(
        "  fragmentation="
        "2plus:{},3plus:{},4plus:{}".format(
            sum(
                count
                for run_count, count in active_run_distribution.items()
                if run_count >= 2
            ),
            sum(
                count
                for run_count, count in active_run_distribution.items()
                if run_count >= 3
            ),
            sum(
                count
                for run_count, count in active_run_distribution.items()
                if run_count >= 4
            ),
        )
    )
    print("  case_run_733:")
    print(
        "    strict_active="
        f"{case_run.start_utc.isoformat()}->{case_run.end_utc.isoformat()} "
        f"bars:{len(case_run.observations)}"
    )
    print(
        "    macro="
        f"id:{case_macro.macro_id},direction:{case_macro.direction},"
        f"{case_macro.start_utc.isoformat()}->{case_macro.end_utc.isoformat()},"
        f"observed_bars:{len(case_macro.observations)},"
        f"active_bars:{case_active_bars},"
        f"nonactive_observed_bars:{len(case_macro.observations) - case_active_bars},"
        f"missing_bars:{case_missing_bars}"
    )
    print("    active_run_ids=" + "|".join(str(run_id) for run_id in case_run_ids))
    print("    interruptions:")
    for item in interruptions:
        print(
            "      {}->{} kind:{} observed_nonactive:{} missing:{} "
            "phases:{} states:{} min_opening:{} min_slope:{}".format(
                item.from_run_id,
                item.to_run_id,
                item.kind,
                item.observed_nonactive_bars,
                item.missing_m15_bars,
                item.phases or "-",
                item.states or "-",
                _format_optional(item.minimum_opening),
                _format_optional(item.minimum_slope),
            )
        )
    print("    opposite_regime_inside_macro=False")
    print("    manual_visual_hypothesis_supported=True")
    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_alligator_observations_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_ALLIGATOR_MACRO_TREND_"
        "CONTINUITY_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
