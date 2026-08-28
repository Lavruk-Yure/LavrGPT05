# -*- coding: utf-8 -*-
"""RoadMap104 / T104-18: Accelerator Oscillator acceleration anatomy.

TEST_ONLY runner reuses the frozen GREEN 8C.1 Alligator opening candidates and
their unchanged SL/TP simulator. Canonical Bill Williams AO/AC is calculated
only from completed M15 HL2 bars: AO=SMA(HL2,5)-SMA(HL2,34),
AC=AO-SMA(AO,5).

There are no tuned numeric thresholds or association windows. Each GREEN
opening is associated structurally with the start of its current directional
AC-delta phase, or with the first later phase in the GREEN direction when the
current phase is not aligned. Outcomes are descriptive and never select an
event or a trade.
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
TEST_ID = "T104-18"
AO_FAST = 5
AO_SLOW = 34
AC_SIGNAL = 5


@dataclass(frozen=True, slots=True)
class AcObservation:
    """Canonical AC state known at one completed M15 bar."""

    index: int
    ac: float
    delta: float
    delta_sign: int
    position_sign: int
    transition: bool
    continued: bool
    price_delta_sign: int


@dataclass(frozen=True, slots=True)
class OpeningMatch:
    """One unchanged GREEN opening associated with an AC acceleration phase."""

    candidate: Any
    trade: Any
    observation: AcObservation
    opening_observation: AcObservation
    lead_bars: int


def _load_base_module() -> ModuleType:
    file_path = Path(__file__).with_name(BASE_SCRIPT_NAME)
    assert file_path.is_file(), file_path
    module_name = "rm104_t104_18_green_8c1_base"
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
    BASE, "_confirmed_expansion_candidates"
)
_simulate_trade: Callable[..., Any] = getattr(BASE, "_simulate_trade")


def _sign(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


def _rolling_sma(
    values: tuple[float | None, ...], length: int
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(length - 1, len(values)):
        window = values[index - length + 1 : index + 1]  # noqa
        if all(value is not None for value in window):
            result[index] = statistics.fmean(float(value) for value in window)
    return tuple(result)


def _canonical_ac(events: tuple[Any, ...]) -> tuple[float | None, ...]:
    hl2 = tuple((float(event.high) + float(event.low)) / 2.0 for event in events)
    fast = _rolling_sma(hl2, AO_FAST)
    slow = _rolling_sma(hl2, AO_SLOW)
    ao = tuple(
        None if left is None or right is None else left - right
        for left, right in zip(fast, slow)
    )
    ao_signal = _rolling_sma(ao, AC_SIGNAL)
    return tuple(
        None if value is None or signal is None else value - signal
        for value, signal in zip(ao, ao_signal)
    )


def _observations(run: Any) -> tuple[AcObservation | None, ...]:
    ac = _canonical_ac(tuple(run.events))
    result: list[AcObservation | None] = [None] * len(ac)
    for index in range(1, len(ac)):
        current = ac[index]
        previous = ac[index - 1]
        if current is None or previous is None:
            continue
        delta = current - previous
        delta_sign = _sign(delta)
        prior_delta_sign = 0
        if index > 1 and ac[index - 2] is not None:
            prior_delta_sign = _sign(previous - float(ac[index - 2]))
        price_delta = float(run.events[index].close) - float(
            run.events[index - 1].close
        )
        result[index] = AcObservation(
            index=index,
            ac=current,
            delta=delta,
            delta_sign=delta_sign,
            position_sign=_sign(current),
            transition=bool(delta_sign != 0 and prior_delta_sign != delta_sign),
            continued=bool(delta_sign != 0 and prior_delta_sign == delta_sign),
            price_delta_sign=_sign(price_delta),
        )
    return tuple(result)


def _direction_sign(direction: str) -> int:
    assert direction in {"BUY", "SELL"}
    return 1 if direction == "BUY" else -1


def _phase_start(
    observations: tuple[AcObservation | None, ...], index: int, sign: int
) -> AcObservation:
    while index > 0:
        previous = observations[index - 1]
        if previous is None or previous.delta_sign != sign:
            break
        index -= 1
    observation = observations[index]
    assert observation is not None and observation.delta_sign == sign
    return observation


def _structural_match(
    observations: tuple[AcObservation | None, ...], opening_index: int, sign: int
) -> AcObservation | None:
    current = observations[opening_index]
    if current is not None and current.delta_sign == sign:
        return _phase_start(observations, opening_index, sign)
    for index in range(opening_index + 1, len(observations)):
        observation = observations[index]
        if observation is not None and observation.delta_sign == sign:
            return _phase_start(observations, index, sign)
    return None


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _median(values: list[int]) -> str:
    return "NONE" if not values else f"{statistics.median(values):.3f}"


def _position_name(sign: int) -> str:
    return {1: "POSITIVE", 0: "ZERO", -1: "NEGATIVE"}[sign]


def _bucket(counter: Counter[str]) -> str:
    return "|".join(f"{key}:{counter[key]}" for key in sorted(counter)) or "NONE"


def _run_window(window: Any) -> dict[str, Any]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    candidates, openings, invalidated, timed_out, aligned_at_start = (
        _confirmed_expansion_candidates(run)
    )
    observations = _observations(run)
    matches: list[OpeningMatch] = []
    opening_states: Counter[str] = Counter()

    for candidate in candidates:
        direction_sign = _direction_sign(str(candidate.direction))
        opening_observation = observations[int(candidate.start_index)]
        opening_state = "UNWARMED"
        if opening_observation is not None:
            if opening_observation.delta_sign == direction_sign:
                opening_state = "DIRECTIONAL_ACCELERATION"
            elif opening_observation.delta_sign == 0:
                opening_state = "ZERO_DELTA"
            else:
                opening_state = "OPPOSITE_ACCELERATION"
        opening_states[opening_state] += 1
        observation = _structural_match(
            observations, int(candidate.start_index), direction_sign
        )
        if observation is None or opening_observation is None:
            continue
        matches.append(
            OpeningMatch(
                candidate=candidate,
                trade=_simulate_trade(run, candidate, macd_exit_enabled=False),
                observation=observation,
                opening_observation=opening_observation,
                lead_bars=int(candidate.start_index) - observation.index,
            )
        )

    assert candidates and matches
    assert all(match.observation.transition for match in matches)
    assert all(
        match.observation.delta_sign == _direction_sign(str(match.candidate.direction))
        for match in matches
    )
    return {
        "candidates": tuple(candidates),
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "aligned_at_start": aligned_at_start,
        "observations": observations,
        "matches": tuple(matches),
        "opening_states": opening_states,
    }


def _print_scope(label: str, matches: tuple[OpeningMatch, ...]) -> None:
    leads = [match.lead_bars for match in matches]
    timing = Counter(
        "LEAD" if value > 0 else "SAME" if value == 0 else "LAG" for value in leads
    )
    outcome = Counter(str(match.trade.close_reason) for match in matches)
    anatomy = Counter(
        (
            f"{match.trade.close_reason}/"
            f"{'TRANSITION' if match.opening_observation.transition else 'CONTINUED'}/"
            f"DELTA_{match.opening_observation.delta_sign:+d}/"
            f"AC_{_position_name(match.opening_observation.position_sign)}"
        )
        for match in matches
    )
    early = tuple(match for match in matches if match.lead_bars > 0)
    sign_agreement = sum(
        match.observation.position_sign
        == _direction_sign(str(match.candidate.direction))
        for match in early
    )
    ac_only = sum(
        match.observation.price_delta_sign
        != _direction_sign(str(match.candidate.direction))
        for match in early
    )
    joint = Counter(
        (
            "AC_AND_PRICE"
            if match.observation.price_delta_sign
            == _direction_sign(str(match.candidate.direction))
            else "AC_ONLY_PRICE_NOT_DIRECTIONAL"
        )
        for match in early
    )
    print(
        f"  {label}/ALIGNMENT=matched:{len(matches)},lead:{timing['LEAD']},"
        f"same:{timing['SAME']},lag:{timing['LAG']},"
        f"median_alligator_minus_ac_bars:{_median(leads)}"
    )
    print(f"  {label}/OUTCOMES={_bucket(outcome)}")
    print(f"  {label}/ANATOMY={_bucket(anatomy)}")
    print(
        f"  {label}/DIRECTIONAL_SIGN=agreed:{sign_agreement},"
        f"early_events:{len(early)},"
        f"rate:{_ratio(sign_agreement, len(early)):.6f},"
        f"ac_zero:{sum(match.observation.position_sign == 0 for match in early)}"
    )
    print(
        f"  {label}/PRICE_INCREMENTAL=ac_only:{ac_only},"
        f"early_events:{len(early)},"
        f"ac_only_rate:{_ratio(ac_only, len(early)):.6f},joint:{_bucket(joint)}"
    )


def main() -> int:
    results = {window.label: _run_window(window) for window in WINDOWS}

    print("T104-18 Accelerator Oscillator Acceleration Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY")
    print("  base=GREEN_8C1_ALLIGATOR_OPENING_EXPANSION")
    print("  production_logic_changed=False")
    print("  candidate_f_logic_changed=False")
    print("  entry_exit_logic_changed=False")
    print("  sl_tp_changed=False")
    print("  bbw_logic_changed=False")
    print("  stochastic_dmi_adx_changed=False")
    print("  ao=SMA_HL2_5_MINUS_SMA_HL2_34")
    print("  ac=AO_MINUS_SMA_AO_5")
    print("  acceleration=STRICT_SIGN_OF_AC_DELTA")
    print("  association=STRUCTURAL_DIRECTIONAL_DELTA_PHASE_NO_NUMERIC_WINDOW")
    print("  tuned_numeric_thresholds=False")

    for window in WINDOWS:
        data = results[window.label]
        matches = data["matches"]
        candidates = data["candidates"]
        observations = tuple(item for item in data["observations"] if item is not None)
        transitions = sum(item.transition for item in observations)
        continued = sum(item.continued for item in observations)
        zero_position = sum(item.position_sign == 0 for item in observations)
        print(
            f"  {window.label}/AC=observations:{len(observations)},"
            f"transitions:{transitions},continued:{continued},"
            f"zero_delta:{sum(item.delta_sign == 0 for item in observations)},"
            f"zero_position:{zero_position}"
        )
        print(
            f"  {window.label}/COVERAGE=green_openings:{len(candidates)},"
            f"matched:{len(matches)},"
            f"coverage:{_ratio(len(matches), len(candidates)):.6f},"
            f"opening_states:{_bucket(data['opening_states'])}"
        )
        for direction in ("BUY", "SELL"):
            side = tuple(
                match
                for match in matches
                if str(match.candidate.direction) == direction
            )
            _print_scope(f"{window.label}/{direction}", side)

    print("  outcome_used_for_selection=False")
    print("  price_movement_used_for_selection=False")
    print("  identical_metric_schema_for_2025_and_2026=True")
    print("  completed_bars_only=True")
    print("  future_price_used=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T104_18_ALGORITHM_WORKSPACE_AC_ACCELERATION_ANATOMY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
