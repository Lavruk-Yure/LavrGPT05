# tests/runtime_workspace/run_t104_17_algorithm_workspace_bbw_compression_expansion_anatomy_2025_2026_check.py
# -*- coding: utf-8 -*-
"""RoadMap104 / T104-17: BBW compression -> expansion anatomy.

TEST_ONLY runner повторно використовує GREEN 8C.1 opening-expansion pipeline
та незмінний SL/TP simulator. Canonical Bollinger BandWidth обчислюється на
20 completed M15 Close bars із population StdDev і multiplier 2. Жодного
абсолютного BBW threshold або production wiring немає.

First expansion є causal переходом від contraction/minimum та delta <= 0 до
першого positive delta. Наступний positive delta вимірюється окремо як anatomy
continuation і не бере участі у виявленні first expansion.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_SCRIPT_NAME = (
    "run_algorithm_workspace_alligator_opening_expansion_2025_2026_check.py"
)
TEST_ID = "T104-17"
BBW_LENGTH = 20
BBW_STDDEV = 2.0
MATCH_WINDOW_BARS = BBW_LENGTH
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class BbwExpansionEvent:
    """Один causal BBW first-expansion event на completed M15 bar."""

    index: int
    contraction_start_index: int
    contraction_bars: int
    bbw: float
    delta: float
    continued_positive_delta: bool
    price_range_delta_positive: bool


@dataclass(frozen=True, slots=True)
class OpeningMatch:
    """Зіставлення одного GREEN 8C.1 opening із найближчим BBW event."""

    candidate: Any
    trade: Any
    bbw_event: BbwExpansionEvent
    lead_bars: int


def _load_base_module() -> ModuleType:
    """Завантажити GREEN 8C.1 runner як read-only dependency."""
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_17_green_8c1_base"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
WINDOWS = getattr(BASE, "WINDOWS")
_load_indicator_run: Callable[..., Any] = getattr(BASE, "_load_indicator_run")
_confirmed_expansion_candidates: Callable[..., Any] = getattr(
    BASE,
    "_confirmed_expansion_candidates",
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")


def _canonical_bbw(events: tuple[Any, ...]) -> tuple[float | None, ...]:
    """Обчислити canonical BBW(20, Close, 2 StdDev) causal rolling-вікном."""
    result: list[float | None] = [None] * len(events)
    for index in range(BBW_LENGTH - 1, len(events)):
        closes = tuple(
            float(events[item].close)
            for item in range(index - BBW_LENGTH + 1, index + 1)
        )
        middle = statistics.fmean(closes)
        if abs(middle) <= EPSILON:
            continue
        deviation = statistics.pstdev(closes)
        upper = middle + BBW_STDDEV * deviation
        lower = middle - BBW_STDDEV * deviation
        result[index] = (upper - lower) / middle
    return tuple(result)


def _bbw_deltas(values: tuple[float | None, ...]) -> tuple[float | None, ...]:
    """Повернути causal delta між сусідніми completed BBW values."""
    deltas: list[float | None] = [None] * len(values)
    for index in range(1, len(values)):
        current = values[index]
        previous = values[index - 1]
        if current is not None and previous is not None:
            deltas[index] = current - previous
    return tuple(deltas)


def _first_expansion_events(
    run: Any,
    bbw: tuple[float | None, ...],
    deltas: tuple[float | None, ...],
) -> tuple[BbwExpansionEvent, ...]:
    """Знайти first positive delta після causal contraction/minimum."""
    result: list[BbwExpansionEvent] = []
    for index in range(BBW_LENGTH + 1, len(bbw)):
        current = bbw[index]
        delta = deltas[index]
        previous_delta = deltas[index - 1]
        if current is None or delta is None or previous_delta is None:
            continue
        if delta <= EPSILON or previous_delta > EPSILON:
            continue

        contraction_start = index - 1
        while contraction_start > BBW_LENGTH - 1:
            contraction_delta = deltas[contraction_start]
            if contraction_delta is None or contraction_delta > EPSILON:
                break
            contraction_start -= 1
        contraction_start += 1
        contraction_bars = index - contraction_start
        if contraction_bars < 1:
            continue

        recent_values = tuple(
            value for value in bbw[contraction_start:index] if value is not None
        )
        if not recent_values or bbw[index - 1] != min(recent_values):
            continue

        next_delta = deltas[index + 1] if index + 1 < len(deltas) else None
        current_range = float(run.events[index].high) - float(run.events[index].low)
        previous_range = float(run.events[index - 1].high) - float(
            run.events[index - 1].low
        )
        result.append(
            BbwExpansionEvent(
                index=index,
                contraction_start_index=contraction_start,
                contraction_bars=contraction_bars,
                bbw=current,
                delta=delta,
                continued_positive_delta=bool(
                    next_delta is not None and next_delta > EPSILON
                ),
                price_range_delta_positive=current_range > previous_range + EPSILON,
            )
        )
    return tuple(result)


def _nearest_bbw_event(
    opening_index: int,
    events: tuple[BbwExpansionEvent, ...],
) -> BbwExpansionEvent | None:
    """Знайти найближчий event у canonical BBW-length association window."""
    eligible = tuple(
        event
        for event in events
        if abs(opening_index - event.index) <= MATCH_WINDOW_BARS
    )
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda event: (
            abs(opening_index - event.index),
            event.index > opening_index,
            event.index,
        ),
    )


def _opening_matches(
    run: Any,
    candidates: tuple[Any, ...],
    bbw_events: tuple[BbwExpansionEvent, ...],
) -> tuple[OpeningMatch, ...]:
    """Зіставити GREEN openings із BBW без зміни trade selection."""
    result: list[OpeningMatch] = []
    for candidate in candidates:
        event = _nearest_bbw_event(int(candidate.start_index), bbw_events)
        if event is None:
            continue
        result.append(
            OpeningMatch(
                candidate=candidate,
                trade=_simulate_trade(run, candidate, macd_exit_enabled=False),
                bbw_event=event,
                lead_bars=int(candidate.start_index) - event.index,
            )
        )
    return tuple(result)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _median(values: tuple[int, ...]) -> float | None:
    return statistics.median(values) if values else None


def _number(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.3f}"


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    candidates, openings, invalidated, timed_out, aligned_at_start = (
        _confirmed_expansion_candidates(run)
    )
    bbw = _canonical_bbw(tuple(run.events))
    deltas = _bbw_deltas(bbw)
    bbw_events = _first_expansion_events(run, bbw, deltas)
    matches = _opening_matches(run, tuple(candidates), bbw_events)

    matched_event_indices = {match.bbw_event.index for match in matches}
    leads = tuple(match.lead_bars for match in matches)
    early = tuple(match for match in matches if match.lead_bars > 0)
    same_bar = tuple(match for match in matches if match.lead_bars == 0)
    lagging = tuple(match for match in matches if match.lead_bars < 0)
    outcomes = Counter(str(match.trade.close_reason) for match in matches)
    early_without_price_expansion = sum(
        not match.bbw_event.price_range_delta_positive for match in early
    )

    assert openings > 0
    assert candidates
    assert bbw_events
    assert all(value is None for value in bbw[: BBW_LENGTH - 1])
    assert all(event.delta > EPSILON for event in bbw_events)
    assert all(deltas[event.index - 1] <= EPSILON for event in bbw_events)

    return {
        "run": run,
        "candidates": tuple(candidates),
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "bbw_events": bbw_events,
        "matches": matches,
        "coverage": _ratio(len(matches), len(candidates)),
        "precision": _ratio(len(matched_event_indices), len(bbw_events)),
        "leads": leads,
        "early": early,
        "same_bar": same_bar,
        "lagging": lagging,
        "outcomes": outcomes,
        "continued": sum(event.continued_positive_delta for event in bbw_events),
        "early_without_price_expansion": early_without_price_expansion,
    }


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-17 BBW Compression -> Expansion Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  base=GREEN_8C1_ALLIGATOR_OPENING_EXPANSION")
    print("  production_logic_changed=False")
    print("  candidate_f_logic_changed=False")
    print("  entry_exit_logic_changed=False")
    print("  sl_tp_changed=False")
    print("  ac_stochastic_dmi_adx_changed=False")
    print("  bbw_length=20")
    print("  bbw_source=CLOSE")
    print("  bbw_stddev=2")
    print("  bbw_stddev_population=True")
    print("  bbw_absolute_tuned_thresholds=False")
    print("  matching_window=CANONICAL_BBW_LENGTH_20_NOT_TUNED")
    print("  structural_transition=RECENT_CONTRACTION_MINIMUM_TO_FIRST_POSITIVE_DELTA")
    print("  continuation_is_anatomy_not_event_selection=True")

    for window in WINDOWS:
        data = results[window.label]
        leads = data["leads"]
        outcomes = data["outcomes"]
        early = data["early"]
        other_outcomes = (
            len(data["matches"]) - outcomes["TAKE_PROFIT"] - outcomes["STOP_LOSS"]
        )
        print(
            f"  {window.label}/BBW="
            f"first_expansions:{len(data['bbw_events'])},"
            f"continued_positive:{data['continued']},"
            f"continued_rate:{_ratio(data['continued'], len(data['bbw_events'])):.6f}"
        )
        print(
            f"  {window.label}/ALIGNMENT="
            f"green_openings:{len(data['candidates'])},"
            f"matched:{len(data['matches'])},"
            f"coverage:{data['coverage']:.6f},"
            f"precision:{data['precision']:.6f},"
            f"bbw_leads:{len(data['early'])},"
            f"same_bar:{len(data['same_bar'])},"
            f"bbw_lags:{len(data['lagging'])},"
            f"median_alligator_minus_bbw_bars:{_number(_median(leads))}"
        )
        print(
            f"  {window.label}/OUTCOMES="
            f"take_profit:{outcomes['TAKE_PROFIT']},"
            f"stop_loss:{outcomes['STOP_LOSS']},"
            f"other:{other_outcomes}"
        )
        print(
            f"  {window.label}/EARLY_INFORMATION="
            f"bbw_before_alligator:{len(early)},"
            "bbw_before_alligator_without_positive_price_range_delta:"
            f"{data['early_without_price_expansion']},"
            "non_duplicate_early_rate:"
            f"{_ratio(data['early_without_price_expansion'], len(early)):.6f}"
        )

    assert all(results[window.label]["matches"] for window in WINDOWS)
    print("  identical_metric_schema_for_2025_and_2026=True")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_17_ALGORITHM_WORKSPACE_BBW_COMPRESSION_EXPANSION_" "ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
