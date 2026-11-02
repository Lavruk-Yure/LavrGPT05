# -*- coding: utf-8 -*-
"""RoadMap115 / T115-02 — парні входи й виходи лише за Alligator.

TEST_ONLY. Жодної зміни production, конфігурації, MD7 чи запитів до брокера.

Контрольна популяція входів: T115-01 (перший completed M15 перехід
не-ACTIVE → ACTIVE; BUY/SELL за regime; профіль Candidate F, 4 bars).
Вхід — за open безпосередньо наступного *суміжного* завершеного M15.
Якщо такого bar немає, entry не виконується. Одночасно максимум 1 позиція.

Вихід — перший завершений M15, де фаза вже не ACTIVE або напрямок
regime не збігається з напрямком відкритої позиції. Після сигналу виходу
закриття здійснюється за open наступного доступного M15; виконання після
розриву в даних рахується окремо. Реверс і повторний вхід усередині
безперервної ACTIVE-фази не виконуються.

PnL: лише брутто-пункти EURUSD (1 pip = 0.0001), за OHLC mid,
без spread, commission, slippage, SL/TP, MACD та правила 33%.
Це дослідницька симуляція, а НЕ production Replay або прогноз доходу.
Нереалізований PnL відкритої позиції до підсумку не додається.
"""

from __future__ import annotations

import hashlib
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    M15,
    PERIODS,
    Bar,
    _aggregate_m1,
    _profile,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

PIP = 0.0001
DIRECTION_UP = "BUY"
DIRECTION_DOWN = "SELL"


@dataclass(frozen=True, slots=True)
class ObservedState:
    """Мінімальний контракт causal observation для synthetic-тестів."""

    timestamp: datetime
    available_at: datetime
    regime_phase: str
    regime: str


@dataclass(frozen=True, slots=True)
class PendingAction:
    action: str
    available_at: datetime
    signal_at: datetime
    direction: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class OpenPosition:
    direction: str
    entry_at: datetime
    entry_price: float
    entry_index: int


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    direction: str
    entry_at: datetime
    exit_at: datetime
    entry_price: float
    exit_price: float
    pips: float
    holding_bars: int
    holding_minutes: int
    exit_reason: str
    exit_gap: bool


@dataclass(slots=True)
class Result:
    entry_signals: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    next_open_available: int = 0
    entries: int = 0
    ignored_while_occupied: int = 0
    entry_skipped_gap: int = 0
    entry_unfilled_at_end: int = 0
    exits_signaled: int = 0
    exit_gap_fills: int = 0
    open_at_end: int = 0
    exit_pending_at_end: int = 0
    incomplete_time_gaps: int = 0
    exited_by_reason: dict[str, int] = field(default_factory=dict)
    trades: list[ClosedTrade] = field(default_factory=list)


def _direction(regime: str) -> str:
    """Відображення лише фактично підтвердженого напрямку regime."""
    if regime == ALLIGATOR_REGIME_TREND_UP:
        return DIRECTION_UP
    if regime == ALLIGATOR_REGIME_TREND_DOWN:
        return DIRECTION_DOWN
    raise AssertionError(f"ACTIVE_WITHOUT_DIRECTION: {regime}")


def _exit_reason(phase: str, regime: str, direction: str) -> str | None:
    """Стан тільки поточного завершеного bar; майбутнє не читається."""
    if phase == ALLIGATOR_REGIME_PHASE_ENDING:
        return "ENDING"
    if phase == ALLIGATOR_REGIME_PHASE_STARTING:
        return "STARTING"
    if phase == ALLIGATOR_REGIME_PHASE_NONE:
        return "NONE"
    if phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        raise AssertionError(f"UNKNOWN_PHASE: {phase}")
    if _direction(regime) != direction:
        return "OPPOSITE_ACTIVE"
    return None


def _simulate(
    steps: Iterable[tuple[Bar, WorkspaceAlligatorObservation | ObservedState]],
) -> Result:
    """Диспетчер: рішення після close, виконання лише на майбутньому open."""
    result = Result()
    previous_bar_at: datetime | None = None
    previous_phase: str | None = None
    last_candidate_available_at: datetime | None = None
    pending: PendingAction | None = None
    position: OpenPosition | None = None

    for index, (bar, observation) in enumerate(steps):
        assert observation.timestamp == bar.timestamp
        assert observation.available_at == bar.timestamp + M15
        if previous_bar_at is not None:
            assert bar.timestamp > previous_bar_at
            if bar.timestamp != previous_bar_at + M15:
                result.incomplete_time_gaps += 1
        previous_bar_at = bar.timestamp

        # Поточний open: дозволені тільки сигнали з ПОПЕРЕДНЬОГО close.
        if last_candidate_available_at is not None:
            if bar.timestamp == last_candidate_available_at:
                result.next_open_available += 1
            last_candidate_available_at = None

        if pending is not None:
            assert bar.timestamp >= pending.available_at, "EXECUTION_BEFORE_SIGNAL"
            if pending.action == "ENTRY":
                assert position is None
                if bar.timestamp == pending.available_at:
                    position = OpenPosition(
                        direction=pending.direction,
                        entry_at=bar.timestamp,
                        entry_price=bar.open,
                        entry_index=index,
                    )
                    result.entries += 1
                else:
                    result.entry_skipped_gap += 1
            else:
                assert pending.action == "EXIT" and position is not None
                gap = bar.timestamp != pending.available_at
                pips = (
                    (bar.open - position.entry_price) / PIP
                    if position.direction == DIRECTION_UP
                    else (position.entry_price - bar.open) / PIP
                )
                result.trades.append(
                    ClosedTrade(
                        direction=position.direction,
                        entry_at=position.entry_at,
                        exit_at=bar.timestamp,
                        entry_price=position.entry_price,
                        exit_price=bar.open,
                        pips=pips,
                        holding_bars=index - position.entry_index,
                        holding_minutes=int(
                            (bar.timestamp - position.entry_at).total_seconds() // 60
                        ),
                        exit_reason=pending.reason,
                        exit_gap=gap,
                    )
                )
                result.exited_by_reason[pending.reason] = (
                    result.exited_by_reason.get(pending.reason, 0) + 1
                )
                result.exit_gap_fills += int(gap)
                position = None
            pending = None

        # Лише тепер обробляється стан Alligator поточного completed bar.
        active = observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        if position is not None:
            reason = _exit_reason(
                observation.regime_phase, observation.regime, position.direction
            )
            if reason is not None:
                pending = PendingAction(
                    action="EXIT",
                    available_at=observation.available_at,
                    signal_at=observation.timestamp,
                    reason=reason,
                )
                result.exits_signaled += 1

        if active and previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
            direction = _direction(observation.regime)
            result.entry_signals += 1
            result.buy_signals += int(direction == DIRECTION_UP)
            result.sell_signals += int(direction == DIRECTION_DOWN)
            last_candidate_available_at = observation.available_at
            if position is None and pending is None:
                pending = PendingAction(
                    action="ENTRY",
                    available_at=observation.available_at,
                    signal_at=observation.timestamp,
                    direction=direction,
                )
            else:
                result.ignored_while_occupied += 1
        previous_phase = observation.regime_phase

    if pending is not None:
        if pending.action == "ENTRY":
            result.entry_unfilled_at_end = 1
        else:
            result.exit_pending_at_end = 1
    result.open_at_end = int(position is not None)
    assert result.entries == len(result.trades) + result.open_at_end
    assert result.exits_signaled == len(result.trades) + result.exit_pending_at_end
    assert result.entry_signals == (
        result.entries
        + result.entry_skipped_gap
        + result.entry_unfilled_at_end
        + result.ignored_while_occupied
    )
    assert result.buy_signals + result.sell_signals == result.entry_signals
    return result


def _sample_bar(start: datetime, offset: int, price: float) -> Bar:
    """Штучний M15 для незалежної перевірки часу виконання."""
    return Bar(start + offset * M15, price, price + PIP, price - PIP, price)


def _synthetic_checks() -> None:
    """Покрити open/close, gap та зміну regime без реальної історії."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)

    def steps(items: list[tuple[int, float, str, str]]):
        for offset, price, phase, regime in items:
            bar = _sample_bar(start, offset, price)
            yield bar, ObservedState(
                timestamp=bar.timestamp,
                available_at=bar.timestamp + M15,
                regime_phase=phase,
                regime=regime,
            )

    up = ALLIGATOR_REGIME_TREND_UP
    down = ALLIGATOR_REGIME_TREND_DOWN
    active = ALLIGATOR_REGIME_PHASE_ACTIVE
    ending = ALLIGATOR_REGIME_PHASE_ENDING
    none = ALLIGATOR_REGIME_PHASE_NONE
    demo = _simulate(
        steps(
            [
                (0, 1.1000, active, up),
                (1, 1.1000, active, up),
                (2, 1.1010, ending, up),
                (3, 1.1020, none, ALLIGATOR_REGIME_FLAT),
            ]
        )
    )
    assert demo.entries == len(demo.trades) == demo.exits_signaled == 1
    assert demo.next_open_available == 1
    assert round(demo.trades[0].pips, 6) == 20
    assert demo.trades[0].holding_bars == 2
    assert demo.exited_by_reason == {"ENDING": 1}

    missing_open = _simulate(
        steps(
            [
                (0, 1.1000, active, up),
                (2, 1.1030, active, up),
                (3, 1.1040, ending, up),
            ]
        )
    )
    assert missing_open.entries == 0 and missing_open.entry_skipped_gap == 1
    assert missing_open.next_open_available == 0

    delayed_exit = _simulate(
        steps(
            [
                (0, 1.1000, active, up),
                (1, 1.1000, active, up),
                (2, 1.1005, ending, up),
                (5, 1.1010, none, ALLIGATOR_REGIME_FLAT),
            ]
        )
    )
    assert delayed_exit.exit_gap_fills == 1 and len(delayed_exit.trades) == 1
    assert delayed_exit.trades[0].exit_at == start + 5 * M15

    flip = _simulate(
        steps(
            [
                (0, 1.1000, active, up),
                (1, 1.1000, active, up),
                (2, 1.0990, active, down),
                (3, 1.0980, active, down),
            ]
        )
    )
    assert flip.exited_by_reason == {"OPPOSITE_ACTIVE": 1}
    assert flip.entries == 1 and len(flip.trades) == 1
    assert flip.entry_signals == 1  # Не створювати сигнал без нового ACTIVE.

    last_signal = _simulate(steps([(0, 1.1000, active, up)]))
    assert last_signal.entries == 0 and last_signal.entry_unfilled_at_end == 1
    assert last_signal.next_open_available == 0
    print("SYNTHETIC_ENTRY_EXIT_CAUSALITY=OK")


def _states(bars: list[Bar], profile):
    """Один реальний послідовний прохід Alligator, без look-ahead."""
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=profile,
        timeframe="M15",
    )
    for bar in bars:
        available_at = bar.timestamp + M15
        event = WorkspaceMarketEvent(
            timestamp=bar.timestamp,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
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
        observation = signal_filter.on_market_event(event, available_at=available_at)
        assert observation.available_at == available_at
        yield bar, observation


def _metrics(result: Result) -> str:
    """Однаковий набір брутто-метрик для обох періодів."""
    pips = [trade.pips for trade in result.trades]
    count = len(pips)
    positive = sum(value for value in pips if value > 0)
    negative = -sum(value for value in pips if value < 0)
    wins = sum(value > 0 for value in pips)
    losses = sum(value < 0 for value in pips)
    flats = count - wins - losses
    equity = peak = max_dd = 0.0
    for value in pips:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    profit_factor = positive / negative if negative else float("inf")
    return (
        f"CLOSED={count}|WINS={wins}|LOSSES={losses}|FLAT={flats}|"
        f"WIN_RATE_PCT={100 * wins / count if count else 0:.2f}|"
        f"GROSS_PIPS={sum(pips):.2f}|AVG_PIPS="
        f"{statistics.mean(pips) if pips else 0:.2f}|"
        f"MEDIAN_PIPS={statistics.median(pips) if pips else 0:.2f}|"
        f"PROFIT_FACTOR_GROSS={profit_factor:.3f}|MAX_CLOSED_DD_PIPS={max_dd:.2f}|"
        f"MEDIAN_HOLD_BARS="
        f"{statistics.median([t.holding_bars
                              for t in result.trades]) if count else 0:g}"
    )


def _fingerprint(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_period(label: str, filename: str, expected: tuple[int, ...], profile) -> None:
    """Вимагати ту саму популяцію entry-кандидатів, що й у T115-01."""
    path = ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source_m1, selected_m1, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    first = _simulate(_states(bars, profile))
    second = _simulate(_states(bars, profile))
    assert first == second, f"NONDETERMINISTIC: {label}"
    assert (
        len(bars),
        first.entry_signals,
        first.buy_signals,
        first.sell_signals,
        first.next_open_available,
    ) == expected, f"T115_01_ENTRY_BASELINE_MISMATCH: {label}"
    print(
        f"PERIOD={label}|SOURCE_M1={source_m1}|SELECTED_M1={selected_m1}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}|"
        f"COMPLETED_M15={len(bars)}|"
        f"ENTRY_EVENTS={first.entry_signals}|BUY={first.buy_signals}|"
        f"SELL={first.sell_signals}|NEXT_OPEN_AVAILABLE={first.next_open_available}"
    )
    print(
        f"ENTRY_EXECUTED={first.entries}|ENTRY_IGNORED_OCCUPIED="
        f"{first.ignored_while_occupied}|"
        f"ENTRY_SKIPPED_GAP={first.entry_skipped_gap}|"
        f"ENTRY_UNFILLED_END={first.entry_unfilled_at_end}|"
        f"EXIT_SIGNALED={first.exits_signaled}|EXIT_DELAYED_GAP={first.exit_gap_fills}|"
        f"EXIT_PENDING_END={first.exit_pending_at_end}|"
        f"POSITION_OPEN_END={first.open_at_end}|TIME_GAPS={first.incomplete_time_gaps}|"
        f"EXIT_REASON_COUNTS="
        f"{','.join(f'{reason}:{count}'
                    for reason, count in sorted(first.exited_by_reason.items()))}"
    )
    print(f"TRADES_GROSS|PERIOD={label}|{_metrics(first)}")
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK")


def main() -> None:
    """Залишити лише готовий дослідницький результат без production-змін."""
    guarded = (
        ROOT / "core" / "workspace_alligator.py",
        ROOT / "core" / "workspace_indicator_profile.py",
        ROOT / "doc" / "LGE_Runtime_07.md",
    )
    hashes_before = {_path.as_posix(): _fingerprint(_path) for _path in guarded}
    print("T115-02|TEST_ONLY|ALLIGATOR_ENTRY_EXIT_ONLY|EURUSD_CTRADER_M15")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert hashes_before == {
        path.as_posix(): _fingerprint(path) for path in guarded
    }, "PRODUCTION_OR_MD7_MODIFIED"
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("gross_mid_only=True|spread_commission_slippage_included=False")
    print("production_changed=False|md7_changed=False")
    print("T115_02_ALLIGATOR_ENTRY_EXIT_ONLY=OK")


if __name__ == "__main__":
    main()
