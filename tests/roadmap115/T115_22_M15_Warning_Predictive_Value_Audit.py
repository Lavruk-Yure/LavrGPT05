# -*- coding: utf-8 -*-
"""RoadMap115 / T115-22 — predictive value of M15 warnings (TEST_ONLY).

H1 entry/exit повністю незмінні від T115-15/T115-21.
M15 warning з T115-21 порівнюється з M15 aligned ACTIVE
спостереженнями тієї ж H1-позиції, без нових правил торгівлі.

Для кожного горизонту використовуються тільки суміжні завершені M15.
Основний outcome рахується тільки поки H1-позиція ще існує;
майбутні ціни — post-hoc мітки, не вхід до прийняття рішення.
Повторні спостереження в позиції корелюють: показано також
порівняння середніх warning/control усередині однієї позиції.
Це діагностика, не оцінка готового early-exit алгоритму.
"""

from __future__ import annotations

import math
import statistics
import sys
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
    ClosedTrade,
    PIP,
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
    M15_SPAN,
    TradeWindow,
    WatchBar,
    WatchStats,
    _is_aligned,
    _observe_m15,
    _synthetic_watch,
    _trace_h1,
    _watch,
)

HORIZONS = (60, 120)
SIDES = (DIRECTION_UP, DIRECTION_DOWN)
EXPECTED_WARNINGS = {
    "2025": {DIRECTION_UP: 140, DIRECTION_DOWN: 34},
    "2026_TO_2026_08_25": {
        DIRECTION_UP: 68,
        DIRECTION_DOWN: 17,
    },
}


@dataclass(frozen=True, slots=True)
class WatchPoint:
    """Історично зафіксований момент спостереження M15."""

    trade_index: int
    state_index: int
    side: str
    group: str
    at: datetime
    close: float


@dataclass(frozen=True, slots=True)
class Label:
    """Тільки майбутній outcome, без застосування до сигналу."""

    end_adverse: float
    max_close_adverse: float


@dataclass(frozen=True, slots=True)
class Scored:
    """Пара спостереження й доступного outcome."""

    point: WatchPoint
    label: Label
    age_minutes: int
    remaining_minutes: int


def _points(
    windows: list[TradeWindow],
    states: list[WatchBar],
    watch: list[WatchStats],
) -> list[WatchPoint]:
    """Сформувати warning і aligned controls тільки з минулого стану."""
    points: list[WatchPoint] = []
    warning_keys = {
        (warning.trade_index, warning.m15_index)
        for item in watch for warning in item.warnings
    }
    assert len(warning_keys) == sum(
        len(item.warnings) for item in watch
    )
    index = 0
    for trade_index, window in enumerate(windows):
        while index < len(states) and states[index].at < window.entry_at:
            index += 1
        cursor = index
        side = window.trade.direction
        while (
            cursor < len(states)
            and states[cursor].at < window.exit_signal_at
        ):
            state = states[cursor]
            if _is_aligned(state, side):
                assert (trade_index, cursor) not in warning_keys
                points.append(WatchPoint(
                    trade_index, cursor, side, "ALIGNED", state.at,
                    state.close,
                ))
            cursor += 1
        index = cursor
    for trade_index, item in enumerate(watch):
        window = windows[trade_index]
        for warning in item.warnings:
            state = states[warning.m15_index]
            assert warning.at == state.at
            assert warning.close == state.close
            assert not _is_aligned(state, warning.side)
            assert window.entry_at <= warning.at < window.exit_signal_at
            points.append(WatchPoint(
                trade_index, warning.m15_index, warning.side,
                "WARNING", warning.at, warning.close,
            ))
    assert len(points) == len({
        (p.trade_index, p.state_index) for p in points
    })
    return sorted(
        points, key=lambda p: (p.trade_index, p.state_index)
    )


def _label(
    point: WatchPoint,
    window: TradeWindow,
    states: list[WatchBar],
    horizon: int,
) -> tuple[Label | None, str]:
    """Causal endpoint та повний M15 path; label лише post hoc."""
    count = horizon // M15_MIN
    assert count > 0 and horizon % M15_MIN == 0
    endpoint = point.at + timedelta(minutes=horizon)
    if endpoint > window.exit_signal_at:
        return None, "EXIT_CENSORED"
    if point.state_index + count >= len(states):
        return None, "DATA_CENSORED"
    sign = -1 if point.side == DIRECTION_UP else 1
    path: list[float] = []
    for offset in range(1, count + 1):
        state = states[point.state_index + offset]
        if state.at != point.at + offset * M15_SPAN:
            return None, "GAP_CENSORED"
        adverse = sign * (state.close - point.close) / PIP
        path.append(adverse)
    assert len(path) == count
    return Label(path[-1], max(0.0, *path)), "AVAILABLE"


def _score(
    points: list[WatchPoint],
    windows: list[TradeWindow],
    states: list[WatchBar],
    horizon: int,
) -> tuple[list[Scored], dict[tuple[str, str], dict[str, int]]]:
    """Однакове правило right censoring для warnings і controls."""
    scored: list[Scored] = []
    census: dict[tuple[str, str], dict[str, int]] = {}
    for point in points:
        window = windows[point.trade_index]
        label, reason = _label(point, window, states, horizon)
        key = point.side, point.group
        counts = census.setdefault(key, {})
        counts[reason] = counts.get(reason, 0) + 1
        if label is None:
            continue
        age = (point.at - window.entry_at).total_seconds() / 60
        remaining = (
            window.exit_signal_at - point.at
        ).total_seconds() / 60
        assert age >= 0 and remaining >= horizon
        scored.append(Scored(
            point, label, int(age), int(remaining),
        ))
    assert len(scored) == sum(
        counts.get("AVAILABLE", 0) for counts in census.values()
    )
    return scored, census


def _mean(values: list[float]) -> str:
    """Виводити NONE, а не удаваний нуль для порожньої групи."""
    return f"{statistics.fmean(values):+.3f}" if values else "NONE"


def _median(values: list[float] | list[int]) -> str:
    """Однакова процедура медіани для warnings і controls."""
    return f"{statistics.median(values):.2f}" if values else "NONE"


def _pct(values: list[float], threshold: float) -> str:
    """Частка подій із несприятливим рухом від порога."""
    if not values:
        return "NONE"
    return f"{100 * sum(v >= threshold for v in values) / len(values):.2f}"


def _report(
    label: str,
    windows: list[TradeWindow],
    points: list[WatchPoint],
    states: list[WatchBar],
) -> None:
    """Звіт WARN vs ALIGNED; окремо кожен горизонт і напрям."""
    for horizon in HORIZONS:
        scored, census = _score(points, windows, states, horizon)
        for side in SIDES:
            parts: dict[str, list[Scored]] = {}
            for group in ("WARNING", "ALIGNED"):
                selected = [
                    s for s in scored
                    if s.point.side == side and s.point.group == group
                ]
                parts[group] = selected
                counts = census.get((side, group), {})
                total = sum(counts.values())
                assert total == sum(
                    p.side == side and p.group == group for p in points
                )
                adverse = [s.label.end_adverse for s in selected]
                worst = [s.label.max_close_adverse for s in selected]
                print(
                    f"GROUP|PERIOD={label}|SIDE={side}|HORIZON={horizon}|"
                    f"TYPE={group}|EVENTS={total}|OBSERVED={len(selected)}|"
                    f"EXIT_CENSORED={counts.get('EXIT_CENSORED', 0)}|"
                    f"GAP_CENSORED={counts.get('GAP_CENSORED', 0)}|"
                    f"DATA_CENSORED={counts.get('DATA_CENSORED', 0)}|"
                    f"TRADES={len({s.point.trade_index for s in selected})}|"
                    f"END_ADVERSE_MEAN={_mean(adverse)}|"
                    f"END_ADVERSE_MEDIAN={_median(adverse)}|"
                    f"END_ADVERSE_GE_5_PCT={_pct(adverse, 5.0)}|"
                    f"WORST_CLOSE_MEAN={_mean(worst)}|"
                    f"WORST_CLOSE_GE_5_PCT={_pct(worst, 5.0)}|"
                    f"AGE_MEDIAN_MIN={_median([
                        s.age_minutes for s in selected
                    ])}|"
                    f"TO_EXIT_MEDIAN_MIN={_median([
                        s.remaining_minutes for s in selected
                    ])}"
                )
            warning = parts["WARNING"]
            aligned = parts["ALIGNED"]
            warn_mean = [s.label.end_adverse for s in warning]
            aligned_mean = [s.label.end_adverse for s in aligned]
            if warn_mean and aligned_mean:
                naive_delta = (
                    statistics.fmean(warn_mean)
                    - statistics.fmean(aligned_mean)
                )
                print(
                    f"POOLED_DIFFERENCE|PERIOD={label}|SIDE={side}|"
                    f"HORIZON={horizon}|WARNING_MINUS_ALIGNED="
                    f"{naive_delta:+.3f}|NOT_INDEPENDENT_EVENTS=True"
                )
            per_trade: dict[int, dict[str, list[float]]] = {}
            for scored_item in warning + aligned:
                by_kind = per_trade.setdefault(
                    scored_item.point.trade_index,
                    {"WARNING": [], "ALIGNED": []},
                )
                by_kind[scored_item.point.group].append(
                    scored_item.label.end_adverse
                )
            deltas = [
                statistics.fmean(kinds["WARNING"])
                - statistics.fmean(kinds["ALIGNED"])
                for kinds in per_trade.values()
                if kinds["WARNING"] and kinds["ALIGNED"]
            ]
            print(
                f"PAIRED_WITHIN_TRADE|PERIOD={label}|SIDE={side}|"
                f"HORIZON={horizon}|PAIRS={len(deltas)}|"
                f"MEAN_DELTA={_mean(deltas)}|"
                f"MEDIAN_DELTA={_median(deltas)}|"
                f"POSITIVE_DELTA_PCT={_pct(deltas, 0.000001)}|"
                f"WARNING_MINUS_ALIGNED=True"
            )
        print(f"OUTCOME_CENSUS_RECONCILIATION={label}:{horizon}:OK")


def _synthetic_predictive() -> None:
    """Не дозволити недоступний H1 horizon або M15 gap."""
    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")
    # Для синтетичного цінового тесту використовуємо ClosedTrade
    # без H1 engine; межа часу є post-hoc attribution.
    trade = ClosedTrade(
        direction=DIRECTION_UP,
        entry_at=origin,
        exit_at=origin + timedelta(minutes=180),
        entry_price=1.1000,
        exit_price=1.0990,
        pips=-10.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )
    window = TradeWindow(trade, origin + timedelta(minutes=120))
    phase = "SYNTHETIC"
    states = [
        WatchBar(
            origin + timedelta(minutes=15 * (i + 1)),
            phase, phase, 1.1000 - 0.0001 * i,
        )
        for i in range(9)
    ]
    start = WatchPoint(
        0, 0, DIRECTION_UP, "WARNING", states[0].at,
        states[0].close,
    )
    label, reason = _label(start, window, states, 60)
    assert reason == "AVAILABLE" and label is not None
    assert math.isclose(label.end_adverse, 4.0, abs_tol=1e-8)
    assert math.isclose(label.max_close_adverse, 4.0, abs_tol=1e-8)
    label, reason = _label(start, window, states, 120)
    assert label is None and reason == "EXIT_CENSORED"
    at_boundary = WatchPoint(
        0, 3, DIRECTION_UP, "ALIGNED", states[3].at,
        states[3].close,
    )
    label, reason = _label(at_boundary, window, states, 60)
    assert reason == "AVAILABLE" and label is not None
    assert math.isclose(label.end_adverse, 4.0, abs_tol=1e-8)
    gap_states = list(states)
    missing = gap_states[2]
    gap_states[2] = WatchBar(
        missing.at + timedelta(minutes=15), missing.phase,
        missing.regime, missing.close,
    )
    label, reason = _label(start, window, gap_states, 60)
    assert label is None and reason == "GAP_CENSORED"
    short_states = states[:4]
    label, reason = _label(start, window, short_states, 60)
    assert label is None and reason == "DATA_CENSORED"
    print("SYNTHETIC_WARNING_VS_ALIGNED_OUTCOME=OK")
    print("SYNTHETIC_H1_EXIT_CENSORING=OK")
    print("SYNTHETIC_M15_GAP_CENSORING=OK")


def main() -> None:
    """Окремий read-only TEST_ONLY дослідницький Replay."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-22|TEST_ONLY|M15_WARNING_PREDICTIVE_VALUE_AUDIT")
    print("H1_ENTRY_EXIT=UNCHANGED|M15=PASSIVE_ONLY")
    print("CONTROL=ALIGNED_ACTIVE_IN_SAME_H1_POSITION")
    print("OUTCOME=FUTURE_COMPLETED_M15_CLOSES_ONLY")
    print("HORIZONS=60,120|CENSOR=H1_EXIT_SIGNAL_OR_M15_GAP")
    print("PAIRED_WITHIN_TRADE=POST_HOC|NO_ORDER_EFFECT=True")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_predictive()
    for label, filename, *_ in PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, bars = _aggregate_all(
            path, int(label[:4]), cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        engine, windows = _trace_h1(bars[H1_MIN])
        expected_closed, expected_open, gross, net = EXPECTED_H1[label]
        assert len(windows) == expected_closed
        assert engine.result.open_at_end == expected_open
        assert math.isclose(
            math.fsum([w.trade.pips for w in windows]),
            gross, abs_tol=1e-6,
        )
        assert math.isclose(
            math.fsum([w.trade.pips - NET_COST_PIPS for w in windows]),
            net, abs_tol=1e-6,
        )
        print(
            f"H1_BASELINE_MATCH={label}:OK|CLOSED={len(windows)}|"
            f"GROSS={gross:+.2f}|NET040={net:+.2f}"
        )
        states = _observe_m15(bars[M15_MIN])
        watch = _watch(windows, states)
        assert len(states) == (23753 if label == "2025" else 15423)
        actual = {
            side: sum(
                warning.side == side
                for item in watch for warning in item.warnings
            ) for side in SIDES
        }
        assert actual == EXPECTED_WARNINGS[label]
        print(
            f"T115_21_WARNINGS_MATCH={label}:OK|"
            f"BUY={actual[DIRECTION_UP]}|SELL={actual[DIRECTION_DOWN]}"
        )
        points = _points(windows, states, watch)
        print(
            f"EVENTS|PERIOD={label}|WARNINGS="
            f"{sum(p.group == 'WARNING' for p in points)}|"
            f"ALIGNED_CONTROLS="
            f"{sum(p.group == 'ALIGNED' for p in points)}"
        )
        _report(label, windows, points, states)
        # Незалежна обчислювальна перевірка без впливу на H1 state.
        again = _watch(windows, states)
        assert watch == again
        assert points == _points(windows, states, again)
        print(f"REPLAY_MIRROR_DETERMINISTIC={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_22_M15_WARNING_PREDICTIVE_VALUE_AUDIT=OK")


if __name__ == "__main__":
    main()
