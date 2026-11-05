# -*- coding: utf-8 -*-
"""RoadMap115 / T115-24: adjacent placebo transitions (TEST_ONLY).

H1 entry/exit з T115-15 залишаються незмінними. M15 passive only.
Порівняти два сусідні переходи тієї самої H1-позиції:
  t-30 -> t-15: M15 aligned ACTIVE -> aligned ACTIVE (placebo);
  t-15 -> t:    M15 aligned ACTIVE -> ENDING (warning).

Усі три спостереження доступні лише після завершення M15.
Для порівняння потрібні повні contiguous outcome labels 60/120 хв.
Майбутні ціни не використовуються для вибору переходу чи ордерів.
Різниця сусідніх перекривних outcome не є причинним ефектом.
"""

from __future__ import annotations

import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    PERIODS,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_DOWN,
    DIRECTION_UP,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    _aggregate_all,
    _synthetic_check,
)
from T115_21_H1_M15_Trend_Watch_Audit import (  # noqa: E402
    EXPECTED_H1,
    H1_MIN,
    M15_MIN,
    _observe_m15,
    _synthetic_watch,
    _trace_h1,
    _watch,
)
from T115_22_M15_Warning_Predictive_Value_Audit import (  # noqa: E402
    EXPECTED_WARNINGS,
    HORIZONS,
    Label,
    Scored,
    WatchPoint,
    _points,
    _score,
    _synthetic_predictive,
)
from T115_23_Matched_Warning_Control_Audit import (  # noqa: E402
    Matched,
    _match,
    _synthetic_matching,
)

SIDES = (DIRECTION_UP, DIRECTION_DOWN)
SPAN = timedelta(minutes=M15_MIN)
EXPECTED = {
    "2025": {60: (161, 142), 120: (154, 137)},
    "2026_TO_2026_08_25": {
        60: (82, 77), 120: (76, 73),
    },
}


@dataclass(frozen=True, slots=True)
class TransitionTriple:
    """Causal warning + попередні дві послідовні ACTIVE точки."""

    previous: Scored
    control: Scored
    warning: Scored


def _triples(scored: list[Scored]) -> tuple[list[TransitionTriple], int]:
    """Вибрати часові трійки, не дивлячись на outcome значення."""
    matches, count = _match(scored)
    aligned = {
        (record.point.trade_index, record.point.state_index): record
        for record in scored if record.point.group == "ALIGNED"
    }
    triples: list[TransitionTriple] = []
    for pair in matches:
        assert isinstance(pair, Matched)
        warning = pair.warning
        control = pair.control
        if pair.lag_minutes != M15_MIN:
            continue
        if control.point.state_index + 1 != warning.point.state_index:
            continue
        key = (
            warning.point.trade_index,
            control.point.state_index - 1,
        )
        previous = aligned.get(key)
        if previous is None:
            continue
        if control.point.at - previous.point.at != SPAN:
            continue
        if not (
            previous.point.side == control.point.side
            == warning.point.side
        ):
            continue
        assert previous.point.trade_index == warning.point.trade_index
        assert previous.point.group == control.point.group == "ALIGNED"
        assert warning.point.group == "WARNING"
        assert previous.point.at + SPAN == control.point.at
        assert control.point.at + SPAN == warning.point.at
        triples.append(TransitionTriple(previous, control, warning))
    assert len(triples) <= len(matches) <= count
    keys = [
        (triple.warning.point.trade_index,
         triple.warning.point.state_index)
        for triple in triples
    ]
    assert len(keys) == len(set(keys))
    return triples, count


def _difference(
    triple: TransitionTriple, attribute: str,
) -> tuple[float, float, float]:
    """Warning delta, placebo delta, їх різниця (post-hoc)."""
    past = getattr(triple.previous.label, attribute)
    control = getattr(triple.control.label, attribute)
    warning = getattr(triple.warning.label, attribute)
    warning_delta = warning - control
    placebo_delta = control - past
    excess = warning_delta - placebo_delta
    assert math.isclose(
        warning_delta - placebo_delta, excess, abs_tol=1e-10,
    )
    return warning_delta, placebo_delta, excess


def _mean(numbers: list[float]) -> str:
    """Порожні групи не підміняти нулем."""
    return f"{statistics.fmean(numbers):+.3f}" if numbers else "NONE"


def _median(numbers: list[float]) -> str:
    """Медіана по реально спостережених трійках."""
    return f"{statistics.median(numbers):+.3f}" if numbers else "NONE"


def _report(
    label: str,
    horizon: int,
    scored: list[Scored],
) -> None:
    """Placebo з однаковим 15-хвилинним зсувом у тій же угоді."""
    triples, warning_count = _triples(scored)
    expected_warnings, expected_eligible = EXPECTED[label][horizon]
    assert warning_count == expected_warnings
    assert len(triples) == expected_eligible
    print(
        f"PLACEBO_CENSUS|PERIOD={label}|HORIZON={horizon}|"
        f"OBSERVED_WARNINGS={warning_count}|"
        f"ELIGIBLE_TRIPLES={len(triples)}|"
        f"MISSING_ADJACENT_PLACEBO={warning_count - len(triples)}"
    )
    for side in SIDES:
        selected = [
            triple for triple in triples
            if triple.warning.point.side == side
        ]
        end = [
            _difference(triple, "end_adverse")
            for triple in selected
        ]
        worst = [
            _difference(triple, "max_close_adverse")
            for triple in selected
        ]
        by_trade: dict[int, list[float]] = defaultdict(list)
        by_trade_worst: dict[int, list[float]] = defaultdict(list)
        for triple, result, worst_result in zip(
            selected, end, worst
        ):
            trade = triple.warning.point.trade_index
            by_trade[trade].append(result[2])
            by_trade_worst[trade].append(worst_result[2])
        weighted_end = [
            statistics.fmean(values) for values in by_trade.values()
        ]
        weighted_worst = [
            statistics.fmean(values)
            for values in by_trade_worst.values()
        ]
        # Всі три outcome стартують на сусідніх M15 close.
        overlap = sum(
            triple.previous.point.at + timedelta(minutes=horizon)
            > triple.warning.point.at
            for triple in selected
        )
        assert overlap == len(selected)
        print(
            f"PLACEBO_SIDE|PERIOD={label}|SIDE={side}|"
            f"HORIZON={horizon}|TRIPLES={len(selected)}|"
            f"TRADES={len(by_trade)}|"
            f"ADJACENT_M15_MIN={M15_MIN}|"
            f"OVERLAPPING_OUTCOME_WINDOWS={overlap}"
        )
        print(
            f"END_DELTA|PERIOD={label}|SIDE={side}|"
            f"HORIZON={horizon}|"
            f"WARNING_STEP={_mean([value[0] for value in end])}|"
            f"PLACEBO_STEP={_mean([value[1] for value in end])}|"
            f"EXCESS={_mean([value[2] for value in end])}|"
            f"TRADE_WEIGHTED_EXCESS={_mean(weighted_end)}|"
            f"TRADE_MEDIAN_EXCESS={_median(weighted_end)}"
        )
        print(
            f"WORST_DELTA|PERIOD={label}|SIDE={side}|"
            f"HORIZON={horizon}|"
            f"WARNING_STEP={_mean([value[0] for value in worst])}|"
            f"PLACEBO_STEP={_mean([value[1] for value in worst])}|"
            f"EXCESS={_mean([value[2] for value in worst])}|"
            f"TRADE_WEIGHTED_EXCESS={_mean(weighted_worst)}"
        )
        assert all(
            math.isclose(a - b, c, abs_tol=1e-8)
            for a, b, c in end + worst
        )
    assert len(triples) == sum(
        sum(triple.warning.point.side == side for triple in triples)
        for side in SIDES
    )
    print(f"PLACEBO_RECONCILIATION={label}:{horizon}:OK")


def _synthetic_placebo() -> None:
    """Перевірити суміжність, same trade, відсутність look-ahead."""
    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")

    def scored(
        index: int, group: str, adverse: float,
        trade: int = 0,
    ) -> Scored:
        point = WatchPoint(
            trade, index, DIRECTION_UP, group,
            origin + index * SPAN, 1.1000,
        )
        return Scored(
            point, Label(adverse, adverse + 2.0),
            index * M15_MIN, 120,
        )

    a = scored(0, "ALIGNED", 1.0)
    b = scored(1, "ALIGNED", 2.0)
    c = scored(2, "WARNING", 5.0)
    triples, warnings = _triples([c, a, b])
    assert warnings == 1 and len(triples) == 1
    assert _difference(triples[0], "end_adverse") == (3, 1, 2)
    assert _triples([c, b]) == ([], 1)
    assert _triples([a, b, scored(3, "WARNING", 3.0)]) == ([], 1)
    assert _triples([a, b, scored(2, "WARNING", 5.0, 1)]) == (
        [], 1,
    )
    future = scored(3, "ALIGNED", 10.0)
    assert _triples([a, b, c]) == _triples([a, b, c, future])
    print("SYNTHETIC_ADJACENT_PLACEBO_CAUSALITY=OK")


def main() -> None:
    """Read-only H1/M15 placebo: жодних торгових рішень M15."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-24|TEST_ONLY|M15_PLACEBO_TRANSITION_AUDIT")
    print("H1_ENTRY_EXIT=UNCHANGED|M15=PASSIVE_ONLY")
    print("WARNING=ACTIVE_TO_ENDING|PLACEBO=ACTIVE_TO_ACTIVE")
    print("ADJACENT_TRANSITIONS=15_MIN|OUTCOMES=60,120")
    print("POST_HOC_OUTCOMES_ONLY=True|OVERLAPPING_WINDOWS=True")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_predictive()
    _synthetic_matching()
    _synthetic_placebo()
    for label, filename, *_ in PERIODS:
        source = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        total, selected, bars = _aggregate_all(
            source, int(label[:4]), cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={total}|"
            f"SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        engine, windows = _trace_h1(bars[H1_MIN])
        expected_closed, expected_open, gross, net = EXPECTED_H1[label]
        assert len(windows) == expected_closed
        assert engine.result.open_at_end == expected_open
        assert math.isclose(math.fsum([
            window.trade.pips for window in windows
        ]), gross, abs_tol=1e-6)
        assert math.isclose(math.fsum([
            window.trade.pips - NET_COST_PIPS for window in windows
        ]), net, abs_tol=1e-6)
        print(
            f"H1_BASELINE_MATCH={label}:OK|CLOSED={expected_closed}|"
            f"GROSS={gross:+.2f}|NET040={net:+.2f}"
        )
        states = _observe_m15(bars[M15_MIN])
        watches = _watch(windows, states)
        warning_counts = {
            side: sum(
                warning.side == side
                for watch in watches for warning in watch.warnings
            ) for side in SIDES
        }
        assert warning_counts == EXPECTED_WARNINGS[label]
        assert all(
            warning.kind == "ENDING"
            for watch in watches for warning in watch.warnings
        )
        points = _points(windows, states, watches)
        for horizon in HORIZONS:
            scored, census = _score(points, windows, states, horizon)
            assert sum(
                sum(groups.values()) for groups in census.values()
            ) == len(points)
            _report(label, horizon, scored)
        assert watches == _watch(windows, states)
        print(f"REPLAY_MIRROR_DETERMINISTIC={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_24_M15_PLACEBO_TRANSITION_AUDIT=OK")


if __name__ == "__main__":
    main()
