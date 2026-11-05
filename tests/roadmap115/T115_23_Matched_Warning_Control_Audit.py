# -*- coding: utf-8 -*-
"""RoadMap115 / T115-23: age-matched M15 warning audit (TEST_ONLY).

H1 торгує як у T115-15; M15 працює виключно як спостерігач.
Для кожного попередження з доступним outcome вибрати найближчий
попередній aligned ACTIVE у тій самій H1-позиції, не давніший за
60 хвилин. Обидва outcome мають бути завершені до H1 exit signal
і складатися тільки із суміжних завершених M15-барів.

Майбутні ціни використовуються лише для ретроспективних міток;
вибір контролю не створює або не змінює торгових рішень.
Мітки контролю та попередження можуть перекриватися — це не
причинний експеримент і не готове правило виходу.
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

MAX_MATCH_AGE_MIN = 60
SIDES = (DIRECTION_UP, DIRECTION_DOWN)


@dataclass(frozen=True, slots=True)
class Matched:
    """Warning та хронологічно попередній контроль тієї ж позиції."""

    warning: Scored
    control: Scored
    lag_minutes: int


def _match(scored: list[Scored]) -> tuple[list[Matched], int]:
    """Зіставити без пошуку майбутнього стану для вибору control.

    Вибір контролю за часом і H1 trade_index, але доступність
    outcome перевірена окремо в _score (лише post-hoc аналіз).
    """
    aligned: dict[int, list[Scored]] = defaultdict(list)
    warnings: list[Scored] = []
    for item in scored:
        if item.point.group == "ALIGNED":
            aligned[item.point.trade_index].append(item)
        else:
            assert item.point.group == "WARNING"
            warnings.append(item)
    matches: list[Matched] = []
    for warning in warnings:
        candidates = [
            control
            for control in aligned[warning.point.trade_index]
            if control.point.side == warning.point.side
            and control.point.at < warning.point.at
            and 0 < warning.age_minutes - control.age_minutes <= MAX_MATCH_AGE_MIN
        ]
        if not candidates:
            continue
        # Найпізніший придатний ACTIVE: детерміноване порівняння.
        control = max(candidates, key=lambda candidate: candidate.point.at)
        lag = warning.age_minutes - control.age_minutes
        assert 0 < lag <= MAX_MATCH_AGE_MIN
        assert control.point.state_index < warning.point.state_index
        assert control.point.at < warning.point.at
        assert warning.point.trade_index == control.point.trade_index
        assert warning.point.side == control.point.side
        matches.append(Matched(warning, control, lag))
    assert len(
        {
            (item.warning.point.trade_index, item.warning.point.state_index)
            for item in matches
        }
    ) == len(matches)
    assert len(matches) <= len(warnings)
    return matches, len(warnings)


def _mean(values: list[float]) -> str:
    """Не маскувати порожню групу нульовим середнім."""
    return f"{statistics.fmean(values):+.3f}" if values else "NONE"


def _median(values: list[float] | list[int]) -> str:
    """Медіана для наявних спостережень."""
    return f"{statistics.median(values):.2f}" if values else "NONE"


def _delta_pct(pairs: list[Matched]) -> str:
    """Різниця часток несприятливих outcome >= 5 пунктів."""
    if not pairs:
        return "NONE"
    value = sum(
        float(pair.warning.label.end_adverse >= 5.0)
        - float(pair.control.label.end_adverse >= 5.0)
        for pair in pairs
    )
    return f"{100 * value / len(pairs):+.2f}"


def _report(
    label: str,
    windows_count: int,
    scored: list[Scored],
    horizon: int,
) -> None:
    """Парні метрики, включно з залежністю повторних подій."""
    matches, observed_warnings = _match(scored)
    print(
        f"MATCH_CENSUS|PERIOD={label}|HORIZON={horizon}|"
        f"WARNINGS_OBSERVED={observed_warnings}|"
        f"MATCHED={len(matches)}|"
        f"UNMATCHED={observed_warnings - len(matches)}|"
        f"H1_CLOSED={windows_count}"
    )
    for side in SIDES:
        selected = [pair for pair in matches if pair.warning.point.side == side]
        end_delta = [
            pair.warning.label.end_adverse - pair.control.label.end_adverse
            for pair in selected
        ]
        worst_delta = [
            pair.warning.label.max_close_adverse - pair.control.label.max_close_adverse
            for pair in selected
        ]
        lags = [pair.lag_minutes for pair in selected]
        reused = len(selected) - len(
            {
                (pair.control.point.trade_index, pair.control.point.state_index)
                for pair in selected
            }
        )
        overlap = sum(
            pair.control.point.at + timedelta(minutes=horizon) > pair.warning.point.at
            for pair in selected
        )
        by_trade: dict[int, list[float]] = defaultdict(list)
        by_trade_worst: dict[int, list[float]] = defaultdict(list)
        for pair, d_end, d_worst in zip(selected, end_delta, worst_delta):
            trade_id = pair.warning.point.trade_index
            by_trade[trade_id].append(d_end)
            by_trade_worst[trade_id].append(d_worst)
        trade_delta = [statistics.fmean(values) for values in by_trade.values()]
        worst_trade_delta = [
            statistics.fmean(values) for values in by_trade_worst.values()
        ]
        print(
            f"MATCHED_SIDE|PERIOD={label}|SIDE={side}|"
            f"HORIZON={horizon}|PAIRS={len(selected)}|"
            f"TRADES={len(by_trade)}|"
            f"LAG_MEDIAN_MIN={_median(lags)}|"
            f"CONTROL_REUSES={reused}|OVERLAPPING_PATHS={overlap}"
        )
        print(
            f"MATCHED_END|PERIOD={label}|SIDE={side}|"
            f"HORIZON={horizon}|WARN_MINUS_CONTROL_MEAN="
            f"{_mean(end_delta)}|TRADE_WEIGHTED_MEAN="
            f"{_mean(trade_delta)}|TRADE_MEDIAN="
            f"{_median(trade_delta)}|"
            f"EVENT_ADVERSE_GE5_DELTA_PP={_delta_pct(selected)}"
        )
        print(
            f"MATCHED_WORST|PERIOD={label}|SIDE={side}|"
            f"HORIZON={horizon}|WARN_MINUS_CONTROL_MEAN="
            f"{_mean(worst_delta)}|TRADE_WEIGHTED_MEAN="
            f"{_mean(worst_trade_delta)}|"
            f"TRADE_MEDIAN={_median(worst_trade_delta)}"
        )
    assert len(matches) == sum(
        pair.warning.point.side == side for side in SIDES for pair in matches
    )
    print(f"MATCH_RECONCILIATION={label}:{horizon}:OK")


def _synthetic_matching() -> None:
    """Відкинути іншу угоду, майбутній ACTIVE та контроль >60 хв."""
    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")
    controls = [
        Scored(
            WatchPoint(
                0, i, DIRECTION_UP, "ALIGNED", origin + timedelta(minutes=15 * i), 1.1
            ),
            Label(0.0, 0.0),
            15 * i,
            120,
        )
        for i in (1, 2, 3)
    ]
    warning = Scored(
        WatchPoint(0, 4, DIRECTION_UP, "WARNING", origin + timedelta(minutes=60), 1.1),
        Label(1.0, 2.0),
        60,
        120,
    )
    future = Scored(
        WatchPoint(0, 5, DIRECTION_UP, "ALIGNED", origin + timedelta(minutes=75), 1.1),
        Label(0.0, 0.0),
        75,
        120,
    )
    other_trade = Scored(
        WatchPoint(1, 3, DIRECTION_UP, "ALIGNED", origin + timedelta(minutes=45), 1.1),
        Label(0.0, 0.0),
        45,
        120,
    )
    matches, count = _match(
        [
            future,
            warning,
            other_trade,
            *controls,
        ]
    )
    assert count == 1 and len(matches) == 1
    assert matches[0].control.point.state_index == 3
    assert matches[0].lag_minutes == 15
    old_warning = Scored(
        WatchPoint(
            2, 20, DIRECTION_DOWN, "WARNING", origin + timedelta(minutes=300), 1.1
        ),
        Label(0.0, 0.0),
        300,
        120,
    )
    lonely, count = _match(controls + [old_warning])
    assert count == 1 and not lonely
    late = Scored(
        WatchPoint(0, 9, DIRECTION_UP, "WARNING", origin + timedelta(minutes=135), 1.1),
        Label(0.0, 0.0),
        135,
        120,
    )
    distant, count = _match(controls + [late])
    assert count == 1 and not distant
    # Наявність контрольної точки після warning не дає витоку.
    assert _match(controls + [warning]) == _match(controls + [warning, future])
    print("SYNTHETIC_CAUSAL_MATCHING=OK")


def main() -> None:
    """Read-only matched warning audit; ніяких нових H1-ордерів."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-23|TEST_ONLY|MATCHED_WARNING_CONTROL_AUDIT")
    print("H1_ENTRY_EXIT=UNCHANGED|M15=PASSIVE_ONLY")
    print("CONTROL=SAME_H1_TRADE_PRECEDING_ALIGNED_ACTIVE")
    print("MATCH_MAX_AGE_DIFF_MIN=60|OUTCOMES=60,120")
    print("MATCH=POST_HOC|OUTCOME_PATHS_CAN_OVERLAP=True")
    print("OUTCOME=CONTIGUOUS_COMPLETED_M15_CLOSES_ONLY")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_predictive()
    _synthetic_matching()
    for label, filename, *_ in PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, bars = _aggregate_all(
            path,
            int(label[:4]),
            cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={source}|"
            f"SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        engine, windows = _trace_h1(bars[H1_MIN])
        expected_closed, expected_open, gross, net = EXPECTED_H1[label]
        assert len(windows) == expected_closed
        assert engine.result.open_at_end == expected_open
        assert math.isclose(
            math.fsum([window.trade.pips for window in windows]),
            gross,
            abs_tol=1e-6,
        )
        assert math.isclose(
            math.fsum([window.trade.pips - NET_COST_PIPS for window in windows]),
            net,
            abs_tol=1e-6,
        )
        print(
            f"H1_BASELINE_MATCH={label}:OK|CLOSED={expected_closed}|"
            f"GROSS={gross:+.2f}|NET040={net:+.2f}"
        )
        states = _observe_m15(bars[M15_MIN])
        watch = _watch(windows, states)
        warning_counts = {
            side: sum(item.side == side for stats in watch for item in stats.warnings)
            for side in SIDES
        }
        assert warning_counts == EXPECTED_WARNINGS[label]
        points = _points(windows, states, watch)
        assert len(points) == len(
            set((point.trade_index, point.state_index) for point in points)
        )
        print(
            f"T115_22_COHORT_MATCH={label}:OK|"
            f"WARNINGS={sum(
                point.group == 'WARNING' for point in points
            )}|CONTROLS={sum(
                point.group == 'ALIGNED' for point in points
            )}"
        )
        for horizon in HORIZONS:
            scored, census = _score(points, windows, states, horizon)
            assert sum(sum(counts.values()) for counts in census.values()) == len(
                points
            )
            _report(label, len(windows), scored, horizon)
        again = _watch(windows, states)
        assert watch == again
        assert points == _points(windows, states, again)
        print(f"REPLAY_MIRROR_DETERMINISTIC={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_23_MATCHED_WARNING_CONTROL_AUDIT=OK")


if __name__ == "__main__":
    main()
