# -*- coding: utf-8 -*-
"""RoadMap115 / T115-25 — H1 entry vs M15 state (TEST_ONLY).

H1 hybrid (4 bars) залишається без змін.
M15 — пасивний знімок.
Основний знімок доступний СТРОГО до H1 entry open.
M15 на межі H1 entry — лише аналіз чутливості.
Торговий результат — виключно outcome label.
Без M15 фільтра входу, broker IO, production-змін.
"""

from __future__ import annotations

import bisect
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
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_DOWN,
    DIRECTION_UP,
    ClosedTrade,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    _aggregate_all,
    _run_tf,
    _summary,
    _synthetic_check,
)
from T115_21_H1_M15_Trend_Watch_Audit import (  # noqa: E402
    EXPECTED_H1,
    H1_MIN,
    M15_MIN,
    M15_SPAN,
    WatchBar,
    _observe_m15,
    _synthetic_watch,
    _trace_h1,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
)

SIDES = (DIRECTION_UP, DIRECTION_DOWN)
PHASES = {
    ALLIGATOR_REGIME_PHASE_ACTIVE: "ACTIVE",
    ALLIGATOR_REGIME_PHASE_STARTING: "STARTING",
    ALLIGATOR_REGIME_PHASE_ENDING: "ENDING",
    ALLIGATOR_REGIME_PHASE_NONE: "NONE",
}
PIP_EPS = 1e-7


@dataclass(frozen=True, slots=True)
class EntryState:
    """Знімок M15, доступний перед H1-входом."""

    trade: ClosedTrade
    entry_at: datetime
    strict_state: WatchBar | None
    boundary_state: WatchBar | None
    strict_class: str
    boundary_class: str
    strict_age_min: int | None


def _category(state: WatchBar | None, direction: str) -> str:
    """Класифікувати відомі phase і regime."""
    if state is None:
        return "NO_RECENT_M15"
    phase = PHASES.get(state.phase)
    assert phase is not None, f"UNEXPECTED_PHASE={state.phase}"
    if state.regime == ALLIGATOR_REGIME_TREND_UP:
        state_side = DIRECTION_UP
    elif state.regime == ALLIGATOR_REGIME_TREND_DOWN:
        state_side = DIRECTION_DOWN
    else:
        return f"{phase}_NO_DIRECTION"
    relation = "ALIGNED" if state_side == direction else "OPPOSITE"
    return f"{phase}_{relation}"


def _snapshot(
    states: list[WatchBar],
    timestamps: list[datetime],
    trade: ClosedTrade,
) -> EntryState:
    """Знімок лише до часу відкриття H1."""
    at = trade.entry_at
    cursor = bisect.bisect_left(timestamps, at)
    assert 0 <= cursor <= len(states)
    previous = states[cursor - 1] if cursor else None
    if previous is not None:
        assert previous.at < at
    recent = previous if previous is not None and previous.at == at - M15_SPAN else None
    age = (
        int((at - previous.at).total_seconds() // 60)
        if (previous is not None)
        else None
    )
    # На межі T стан окремий, не для основної класифікації.
    coincident = (
        states[cursor] if cursor < len(states) and states[cursor].at == at else None
    )
    boundary = coincident if coincident is not None else recent
    assert recent is None or recent.at == at - M15_SPAN
    assert boundary is None or boundary.at <= at
    return EntryState(
        trade=trade,
        entry_at=at,
        strict_state=recent,
        boundary_state=boundary,
        strict_class=_category(recent, trade.direction),
        boundary_class=_category(boundary, trade.direction),
        strict_age_min=age,
    )


def _entries(
    trades: list[ClosedTrade],
    states: list[WatchBar],
) -> list[EntryState]:
    """Попередній M15 для кожного H1-входу."""
    timestamps = [state.at for state in states]
    assert timestamps == sorted(set(timestamps))
    entries = [_snapshot(states, timestamps, trade) for trade in trades]
    assert len(entries) == len(trades)
    assert all(
        entry.entry_at == trade.entry_at for entry, trade in zip(entries, trades)
    )
    return entries


def _synthetic_entry_boundary() -> None:
    """Майбутні M15 не змінюють стану минулого."""
    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")
    up = ALLIGATOR_REGIME_TREND_UP
    down = ALLIGATOR_REGIME_TREND_DOWN
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    points = [
        WatchBar(origin - timedelta(minutes=30), active, up, 1.10),
        WatchBar(origin - timedelta(minutes=15), active, up, 1.11),
        WatchBar(origin, ending, down, 1.12),
        WatchBar(origin + timedelta(minutes=15), active, down, 1.13),
    ]
    trade = ClosedTrade(
        direction=DIRECTION_UP,
        entry_at=origin,
        exit_at=origin + timedelta(hours=2),
        entry_price=1.11,
        exit_price=1.12,
        pips=100.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )
    before = _entries([trade], points[:2])[0]
    with_boundary = _entries([trade], points[:3])[0]
    with_future = _entries([trade], points)[0]
    assert before.strict_class == "ACTIVE_ALIGNED"
    assert before.strict_class == with_boundary.strict_class
    assert before.strict_class == with_future.strict_class
    assert before.strict_state == with_future.strict_state
    assert before.boundary_class == before.strict_class
    assert with_boundary.boundary_class == "ENDING_OPPOSITE"
    assert with_future.boundary_class == "ENDING_OPPOSITE"
    assert with_future.strict_state is not None
    assert with_future.strict_state.at < origin
    stale = _entries([trade], points[:1])[0]
    assert stale.strict_class == "NO_RECENT_M15"
    assert stale.strict_age_min == 30
    print("SYNTHETIC_STRICT_PRE_ENTRY_M15_CAUSALITY=OK")
    print("SYNTHETIC_SAME_TIMESTAMP_BOUNDARY_ISOLATION=OK")
    print("SYNTHETIC_M15_GAP_STALENESS=OK")


def _mean(values: list[float]) -> str:
    return f"{statistics.fmean(values):+.2f}" if values else "NONE"


def _median(values: list[float]) -> str:
    return f"{statistics.median(values):+.2f}" if values else "NONE"


def _cohort(label: str, side: str, group: str, items: list[EntryState]) -> None:
    """Closed-only labels без зміни Replay."""
    pips = [entry.trade.pips - NET_COST_PIPS for entry in items]
    gross_values: list[float] = [float(entry.trade.pips) for entry in items]
    gross = math.fsum(gross_values)
    net = math.fsum(pips)
    wins = sum(value > PIP_EPS for value in pips)
    losses = sum(value < -PIP_EPS for value in pips)
    positive = math.fsum(max(0.0, value) for value in pips)
    negative = -math.fsum(min(0.0, value) for value in pips)
    pf = positive / negative if negative > PIP_EPS else float("inf")
    print(
        f"COHORT|PERIOD={label}|SIDE={side}|M15={group}|"
        f"CLOSED={len(items)}|WINS={wins}|LOSSES={losses}|"
        f"GROSS_PIPS={gross:+.2f}|NET040_PIPS={net:+.2f}|"
        f"AVG_NET040={_mean(pips)}|MEDIAN_NET040={_median(pips)}|"
        f"PF_NET={pf:.3f}"
    )


def _report(label: str, entries: list[EntryState]) -> None:
    """Групова діагностика зі звіркою Net."""
    strict_ready = [e for e in entries if e.strict_state is not None]
    stale = [e for e in entries if e.strict_state is None]
    boundary_changed = sum(e.strict_class != e.boundary_class for e in entries)
    print(
        f"ENTRY_CENSUS|PERIOD={label}|H1_CLOSED={len(entries)}|"
        f"M15_STRICT_READY={len(strict_ready)}|M15_STALE={len(stale)}|"
        f"BOUNDARY_CLASS_CHANGED={boundary_changed}|"
        f"RULE=LAST_M15_CLOSE_STRICTLY_BEFORE_H1_ENTRY"
    )
    grouped: dict[tuple[str, str], list[EntryState]] = {}
    for entry in entries:
        key = entry.trade.direction, entry.strict_class
        grouped.setdefault(key, []).append(entry)
    for side in SIDES:
        selection = [e for e in entries if e.trade.direction == side]
        _cohort(label, side, "ALL", selection)
        for category in sorted({e.strict_class for e in selection}):
            _cohort(label, side, category, grouped[side, category])
        gross = math.fsum(e.trade.pips for e in selection)
        part_gross = math.fsum(
            math.fsum(e.trade.pips for e in cohort)
            for (direction, _), cohort in grouped.items()
            if direction == side
        )
        part_net = math.fsum(
            math.fsum(e.trade.pips - NET_COST_PIPS for e in cohort)
            for (direction, _), cohort in grouped.items()
            if direction == side
        )
        full_net = math.fsum(e.trade.pips - NET_COST_PIPS for e in selection)
        assert math.isclose(gross, part_gross, abs_tol=1e-7)
        assert math.isclose(full_net, part_net, abs_tol=1e-7)
        print(f"COHORT_RECONCILIATION={label}:{side}:OK")
    for entry in entries:
        assert entry.strict_state is None or (entry.strict_state.at < entry.entry_at)
    print(f"ENTRY_M15_RECONCILIATION={label}:OK")


def main() -> None:
    """Read-only Replay із незалежною звіркою H1 і M15."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-25|TEST_ONLY|H1_ENTRY_M15_STATE_ANATOMY")
    print("H1_ENTRY_EXIT=UNCHANGED_4_BARS_HYBRID|M15=PASSIVE_ONLY")
    print("PRE_ENTRY_M15=STRICTLY_EARLIER|NO_SAME_TICK_ASSUMPTION")
    print("BOUNDARY_AT_ENTRY=POST_HOC_SENSITIVITY_ONLY")
    print("NET040=HYPOTHETICAL|OUTCOMES=CLOSED_TRADES_ONLY")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    for label, filename, *_ in PERIODS:
        data_path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            data_path,
            int(label[:4]),
            cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        replay, windows = _trace_h1(aggregated[H1_MIN])
        baseline = _run_tf(aggregated[H1_MIN], H1_MIN, _profile())[2]
        assert replay == baseline
        count, opened, expected_gross, expected_net = EXPECTED_H1[label]
        assert len(windows) == count
        assert replay.result.open_at_end == opened
        assert math.isclose(
            math.fsum(trade.pips for trade in replay.result.trades),
            expected_gross,
            abs_tol=1e-6,
        )
        assert math.isclose(
            math.fsum(trade.pips - NET_COST_PIPS for trade in replay.result.trades),
            expected_net,
            abs_tol=1e-6,
        )
        print(f"H1_UNCHANGED|PERIOD={label}|" f"{_summary(replay, NET_COST_PIPS)}")
        print(f"T115_15_H1_BASELINE_MATCH={label}:OK")
        states = _observe_m15(aggregated[M15_MIN])
        assert len(states) == (23753 if label == "2025" else 15423)
        entries = _entries(replay.result.trades, states)
        _report(label, entries)
        # Повторюємо діагностичне об'єднання.
        assert entries == _entries(replay.result.trades, states)
        print(f"REPLAY_MIRROR_DETERMINISTIC={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_25_H1_ENTRY_M15_STATE_ANATOMY=OK")


if __name__ == "__main__":
    main()
