# -*- coding: utf-8 -*-
"""RoadMap115 / T115-21 — H1 + M15 passive trend watch (TEST_ONLY).

H1 керує входами та виходами без змін від T115-15 (4 completed bars).
M15 тільки спостерігає: після ACTIVE у напрямку H1-позиції
перша втрата M15 ACTIVE-узгодження формує попередження.
Повторне попередження — лише після нового M15 ACTIVE узгодження.

Результат H1-виходу та наступний рух M15 є outcome labels і не
впливають на сигнали. Час рішення M15 — close completed bar.
Жодних broker requests, production edits чи параметричної оптимізації.
Mid OHLC і умовні витрати 0.40 pip; не доказ прибутковості.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    PERIODS,
    Bar,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_DOWN,
    DIRECTION_UP,
    PIP,
    ClosedTrade,
    _direction,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    SELL_33,
    Engine,
    _aggregate_all,
    _run_tf,
    _summary,
    _synthetic_check,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

M15_MIN = 15
H1_MIN = 60
HORIZON_MIN = 120
M15_SPAN = timedelta(minutes=M15_MIN)
H1_SPAN = timedelta(minutes=H1_MIN)
HORIZON = timedelta(minutes=HORIZON_MIN)
EXPECTED_H1 = {
    "2025": (167, 0, 304.90, 238.10),
    "2026_TO_2026_08_25": (114, 0, -283.40, -329.00),
}


@dataclass(frozen=True, slots=True)
class WatchBar:
    """M15-стан, доступний лише після завершення свічки."""

    at: datetime
    phase: str
    regime: str
    close: float


@dataclass(frozen=True, slots=True)
class TradeWindow:
    """H1-позиція та відомий з H1 Replay час exit signal.

    Результат H1 з'єднується з M15 спостереженнями post hoc.
    Час виходу не використовується для формування M15-попередження.
    """

    trade: ClosedTrade
    exit_signal_at: datetime

    @property
    def entry_at(self) -> datetime:
        return self.trade.entry_at


@dataclass(frozen=True, slots=True)
class TrendWarning:
    """Завершений M15 перехід aligned ACTIVE -> not aligned."""

    trade_index: int
    at: datetime
    side: str
    kind: str
    close: float
    m15_index: int


@dataclass(slots=True)
class WatchStats:
    """Стан спостереження за однією позицією H1."""

    armed: bool = False
    aligned_seen: bool = False
    last_at: datetime | None = None
    observations: int = 0
    warnings: list[TrendWarning] = field(default_factory=list)
    rearmed: int = 0
    interrupted_gaps: int = 0


def _event(bar: Bar, tf: str) -> WorkspaceMarketEvent:
    """Повторно використати штатний API події, без broker IO."""
    return WorkspaceMarketEvent(
        timestamp=bar.timestamp,
        broker="CTRADER",
        symbol="EURUSD",
        timeframe=tf,
        bid=bar.close,
        ask=bar.close,
        spread=0.0,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=0.0,
        source_mode="REPLAY",
    )


def _filter(tf: str) -> WorkspaceAlligatorFilter:
    """Однаковий immutable Candidate F profile для H1 та M15."""
    return WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=_profile(),
        timeframe=tf,
    )


def _trace_h1(
    bars: list[Bar],
) -> tuple[Engine, list[TradeWindow]]:
    """Відтворити H1 hybrid і точний causal час сигналів EXIT."""
    engine = Engine(H1_SPAN, SELL_33)
    mirror = Engine(H1_SPAN, SELL_33)
    signal_filter = _filter("H1")
    signals: dict[datetime, datetime] = {}
    for index, bar in enumerate(bars):
        at = bar.timestamp + H1_SPAN
        obs = signal_filter.on_market_event(
            _event(bar, "H1"),
            available_at=at,
        )
        assert obs.available_at == at
        engine.on_bar(index, bar, obs)
        mirror.on_bar(index, bar, obs)
        action = engine.pending
        if action is not None and action.action == "EXIT":
            assert engine.position is not None
            entry = engine.position.entry_at
            assert entry not in signals
            assert action.available_at == at
            signals[entry] = at
    engine.finish()
    mirror.finish()
    assert engine == mirror
    windows: list[TradeWindow] = []
    for trade in engine.result.trades:
        signal_at = signals[trade.entry_at]
        assert trade.entry_at < signal_at <= trade.exit_at
        assert trade.entry_at.minute == trade.exit_at.minute == 0
        windows.append(TradeWindow(trade, signal_at))
    assert windows == sorted(windows, key=lambda w: w.entry_at)
    assert len(windows) == len(engine.result.trades)
    return engine, windows


def _observe_m15(bars: list[Bar]) -> list[WatchBar]:
    """Завершені M15 стани; H1 ці спостереження не отримує."""
    signal_filter = _filter("M15")
    states: list[WatchBar] = []
    for bar in bars:
        at = bar.timestamp + M15_SPAN
        obs: WorkspaceAlligatorObservation = signal_filter.on_market_event(
            _event(bar, "M15"),
            available_at=at,
        )
        assert obs.timestamp == bar.timestamp
        assert obs.available_at == at
        states.append(
            WatchBar(
                at=at,
                phase=obs.regime_phase,
                regime=obs.regime,
                close=bar.close,
            )
        )
    assert all(a.at < b.at for a, b in zip(states, states[1:]))
    return states


def _is_aligned(state: WatchBar, side: str) -> bool:
    """Лише M15 ACTIVE у напрямку наявної позиції H1."""
    if state.phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False
    return _direction(state.regime) == side


def _kind(state: WatchBar, side: str) -> str:
    """Класифікація warning без майбутніх даних."""
    if state.phase == ALLIGATOR_REGIME_PHASE_ENDING:
        return "ENDING"
    if state.phase == ALLIGATOR_REGIME_PHASE_ACTIVE:
        assert _direction(state.regime) != side
        return "OPPOSITE_ACTIVE"
    return state.phase


def _update(
    stats: WatchStats,
    state: WatchBar,
    side: str,
    trade_index: int,
    state_index: int,
) -> None:
    """Одне causal M15 спостереження; без доступу до H1 outcome."""
    stats.observations += 1
    if stats.last_at is not None and state.at != stats.last_at + M15_SPAN:
        stats.armed = False
        stats.interrupted_gaps += 1
    stats.last_at = state.at
    aligned = _is_aligned(state, side)
    if aligned:
        if stats.aligned_seen and not stats.armed:
            stats.rearmed += 1
        stats.aligned_seen = True
        stats.armed = True
    elif stats.armed:
        stats.warnings.append(
            TrendWarning(
                trade_index=trade_index,
                at=state.at,
                side=side,
                kind=_kind(state, side),
                close=state.close,
                m15_index=state_index,
            )
        )
        stats.armed = False


def _watch(
    windows: list[TradeWindow],
    states: list[WatchBar],
) -> list[WatchStats]:
    """Ретроспективно прив'язати causal warnings до H1 позицій."""
    all_stats = [WatchStats() for _ in windows]
    current = 0
    for state_index, state in enumerate(states):
        while current < len(windows) and state.at >= windows[current].exit_signal_at:
            current += 1
        if current == len(windows):
            break
        window = windows[current]
        if state.at < window.entry_at:
            continue
        assert window.entry_at <= state.at < window.exit_signal_at
        _update(
            all_stats[current],
            state,
            window.trade.direction,
            current,
            state_index,
        )
    for index, stats in enumerate(all_stats):
        prev: datetime | None = None
        for warning in stats.warnings:
            assert warning.trade_index == index
            assert windows[index].entry_at <= warning.at
            assert warning.at < windows[index].exit_signal_at
            assert prev is None or prev < warning.at
            prev = warning.at
    return all_stats


def _followthrough(
    states: list[WatchBar],
    warning: TrendWarning,
    minutes: int,
) -> float | None:
    """Outcome-only: ціна після повних суміжних M15 у майбутньому."""
    assert minutes in (60, 120)
    count = minutes // M15_MIN
    base = warning.m15_index
    future = base + count
    if future >= len(states):
        return None
    if any(
        states[base + step].at != warning.at + step * M15_SPAN
        for step in range(1, count + 1)
    ):
        return None
    direction = 1 if warning.side == DIRECTION_UP else -1
    return -direction * (states[future].close - warning.close) / PIP


def _median(values: list[int]) -> str:
    """Чесно відокремити порожню вибірку від нульового часу."""
    return f"{statistics.median(values):.0f}" if values else "NONE"


def _mean(values: list[float]) -> str:
    """Показати NONE, якщо нема доступного outcome label."""
    return f"{statistics.fmean(values):+.2f}" if values else "NONE"


def _synthetic_watch() -> None:
    """Захист сигналу від незавершених барів, gap і повторів."""
    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")

    def state(offset: int, phase: str, regime: str) -> WatchBar:
        return WatchBar(
            origin + timedelta(minutes=offset),
            phase,
            regime,
            1.1000,
        )

    up = ALLIGATOR_REGIME_TREND_UP
    down = ALLIGATOR_REGIME_TREND_DOWN
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    stats = WatchStats()
    _update(stats, state(15, active, up), DIRECTION_UP, 0, 0)
    _update(stats, state(30, ending, up), DIRECTION_UP, 0, 1)
    _update(stats, state(45, ending, up), DIRECTION_UP, 0, 2)
    assert len(stats.warnings) == 1
    assert stats.warnings[0].at == origin + timedelta(minutes=30)
    _update(stats, state(60, active, up), DIRECTION_UP, 0, 3)
    _update(stats, state(75, active, down), DIRECTION_UP, 0, 4)
    assert len(stats.warnings) == 2
    assert stats.warnings[1].kind == "OPPOSITE_ACTIVE"
    assert stats.rearmed == 1
    _update(stats, state(120, ending, up), DIRECTION_UP, 0, 5)
    _update(stats, state(135, ending, up), DIRECTION_UP, 0, 6)
    assert len(stats.warnings) == 2
    assert stats.interrupted_gaps == 1
    # Відсікання стану на точному H1 exit signal і майбутніх M15.
    position = ClosedTrade(
        direction=DIRECTION_UP,
        entry_at=origin,
        exit_at=origin + timedelta(minutes=60),
        entry_price=1.1000,
        exit_price=1.1010,
        pips=10.0,
        holding_bars=1,
        holding_minutes=60,
        exit_reason="ENDING",
        exit_gap=False,
    )
    window = TradeWindow(position, position.exit_at)
    prefix = [
        state(0, active, up),
        state(15, ending, up),
        state(30, ending, up),
    ]
    future = [
        state(60, active, up),
        state(75, ending, up),
    ]
    a = _watch([window], prefix)[0].warnings
    b = _watch([window], prefix + future)[0].warnings
    assert a == b and len(a) == 1
    assert a[0].at == origin + timedelta(minutes=15)
    assert _followthrough(prefix, a[0], 60) is None
    print("SYNTHETIC_M15_H1_EXIT_BOUNDARY=OK")
    print("SYNTHETIC_M15_PASSIVE_WATCH_CAUSALITY=OK")


def _report(
    label: str,
    windows: list[TradeWindow],
    states: list[WatchBar],
    stats: list[WatchStats],
) -> None:
    """Виміряти раннє попередження і його outcome без торгівлі."""
    all_warnings = [warning for item in stats for warning in item.warnings]
    warnings_by_side = {
        side: [w for w in all_warnings if w.side == side]
        for side in (DIRECTION_UP, DIRECTION_DOWN)
    }
    armed_trades = sum(s.aligned_seen for s in stats)
    warned_trades = sum(bool(s.warnings) for s in stats)
    print(
        f"WATCH|PERIOD={label}|H1_CLOSED={len(windows)}|"
        f"M15_COMPLETED={len(states)}|"
        f"H1_WITH_M15_ALIGNMENT={armed_trades}|"
        f"H1_WITH_WARNING={warned_trades}|"
        f"WARNINGS={len(all_warnings)}|"
        f"REARMS={sum(s.rearmed for s in stats)}|"
        f"WATCH_GAPS={sum(s.interrupted_gaps for s in stats)}"
    )
    for side in (DIRECTION_UP, DIRECTION_DOWN):
        selected = warnings_by_side[side]
        within60 = within120 = later120 = 0
        lead: list[int] = []
        move60: list[float] = []
        move120: list[float] = []
        missing60 = missing120 = 0
        kinds: dict[str, int] = {}
        for warning in selected:
            window = windows[warning.trade_index]
            until_signal = (window.exit_signal_at - warning.at).total_seconds() / 60
            assert until_signal > 0
            if until_signal <= 60:
                within60 += 1
            if until_signal <= HORIZON_MIN:
                within120 += 1
                lead.append(int(until_signal))
            else:
                later120 += 1
            kinds[warning.kind] = kinds.get(warning.kind, 0) + 1
            future60 = _followthrough(states, warning, 60)
            future120 = _followthrough(states, warning, 120)
            if future60 is None:
                missing60 += 1
            else:
                move60.append(future60)
            if future120 is None:
                missing120 += 1
            else:
                move120.append(future120)
        assert within120 + later120 == len(selected)
        assert len(move60) + missing60 == len(selected)
        assert len(move120) + missing120 == len(selected)
        print(
            f"WARNING_SIDE|PERIOD={label}|SIDE={side}|"
            f"WARNINGS={len(selected)}|H1_EXIT_WITHIN_60={within60}|"
            f"H1_EXIT_WITHIN_120={within120}|"
            f"NO_H1_EXIT_WITHIN_120={later120}|"
            f"LEAD_120_MEDIAN_MIN={_median(lead)}|"
            f"ADVERSE_CLOSE_60_AVG_PIPS={_mean(move60)}|"
            f"ADVERSE_CLOSE_120_AVG_PIPS={_mean(move120)}|"
            f"MOVE_60_CENSORED={missing60}|"
            f"MOVE_120_CENSORED={missing120}"
        )
        for kind in sorted(kinds):
            print(
                f"WARNING_TYPE|PERIOD={label}|SIDE={side}|"
                f"TYPE={kind}|COUNT={kinds[kind]}"
            )
        for reason in sorted(
            {windows[w.trade_index].trade.exit_reason for w in selected}
        ):
            subset = [
                w
                for w in selected
                if windows[w.trade_index].trade.exit_reason == reason
            ]
            print(
                f"WARNING_TO_H1_EXIT|PERIOD={label}|SIDE={side}|"
                f"H1_REASON={reason}|COUNT={len(subset)}|"
                f"WITHIN_120={sum(
                    (windows[w.trade_index].exit_signal_at - w.at)
                    <= HORIZON for w in subset
                )}"
            )
    for side in (DIRECTION_UP, DIRECTION_DOWN):
        eligible = warned = no_warning = unarmed = 0
        for index, window in enumerate(windows):
            if window.trade.direction != side:
                continue
            lifetime = window.exit_signal_at - window.entry_at
            if lifetime < HORIZON:
                continue
            eligible += 1
            if not stats[index].aligned_seen:
                unarmed += 1
                continue
            late_start = window.exit_signal_at - HORIZON
            has_warning = any(
                late_start <= warning.at < window.exit_signal_at
                for warning in stats[index].warnings
            )
            if has_warning:
                warned += 1
            else:
                no_warning += 1
        assert eligible == warned + no_warning + unarmed
        print(
            f"TRADE_RECALL|PERIOD={label}|SIDE={side}|"
            f"H1_EXIT_ELIGIBLE_120={eligible}|"
            f"M15_WARNED_IN_LAST_120={warned}|"
            f"NO_WARNING_LAST_120={no_warning}|"
            f"NO_M15_ALIGNMENT={unarmed}"
        )


def main() -> None:
    """Запустити read-only H1/M15 Replay та контрольні звірки."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-21|TEST_ONLY|H1_M15_TREND_WATCH_AUDIT")
    print("H1_ENTRY_EXIT=UNCHANGED_4_BARS_HYBRID")
    print("M15=PASSIVE_ONLY|ARM=ALIGNED_ACTIVE|WARN=LOSS_OF_ALIGNMENT")
    print("WARN_HORIZON_MIN=120|FUTURE_PRICES=OUTCOME_LABELS_ONLY")
    print("H1_SIGNAL_AND_M15_OBSERVATIONS=COMPLETED_BARS_ONLY")
    _synthetic_check()
    _synthetic_watch()
    for label, filename, *_ in PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            path,
            int(label[:4]),
            cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        h1, windows = _trace_h1(aggregated[H1_MIN])
        reference = _run_tf(aggregated[H1_MIN], H1_MIN, _profile())[2]
        assert h1 == reference
        expected_closed, expected_open, gross, net = EXPECTED_H1[label]
        assert len(h1.result.trades) == expected_closed
        assert h1.result.open_at_end == expected_open
        values = [t.pips for t in h1.result.trades]
        assert math.isclose(math.fsum(values), gross, abs_tol=1e-6)
        actual_net = math.fsum([t.pips - NET_COST_PIPS for t in h1.result.trades])
        assert math.isclose(actual_net, net, abs_tol=1e-6)
        print(f"H1_UNCHANGED|PERIOD={label}|{_summary(h1, NET_COST_PIPS)}")
        print(f"T115_15_H1_BASELINE_MATCH={label}:OK")
        states = _observe_m15(aggregated[M15_MIN])
        assert len(states) == (23753 if label == "2025" else 15423)
        watch = _watch(windows, states)
        _report(label, windows, states, watch)
        print(f"REPLAY_MIRROR_DETERMINISTIC={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_21_H1_M15_TREND_WATCH_AUDIT=OK")


if __name__ == "__main__":
    main()
