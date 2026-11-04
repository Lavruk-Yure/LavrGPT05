# -*- coding: utf-8 -*-
"""RoadMap115 / T115-14 — однакова логіка на M1, M5, M15 та H1.

TEST_ONLY. Порівняння чутливості до таймфрейму, НЕ оптимізація.
Джерело — ті самі EURUSD cTrader M1 і cutoff T115-01/09.
Завершений бар потребує всіх суміжних M1 у своєму UTC bucket.
Жодного заповнення прогалин; у розриві не вигадується open.

Штатний профіль Candidate F (4 completed bars) ЗБЕРЕЖЕНИЙ для всіх TF.
Це порівняння фіксованих bar-параметрів, не однакового часу:
4 бари на M1 — 4 хвилини, на H1 — 4 години.

Три варіанти T115-09: Alligator, Alligator+33%, hybrid
BUY=ENDING, SELL=33%/ENDING. Гіпотеза 33% — не production PD35.
Вхід — лише next contiguous completed bar open після ACTIVE.
Вихід — next available completed bar open після сигналу ENDING/33.
Ціни OHLC mid, без bid/ask; витрати 0.40 pip — лише сценарій T115-10.
Порівняння по роках і TF не є out-of-sample доказом.
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    HEADER,
    ONE_MINUTE,
    PERIODS,
    Bar,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_DOWN,
    DIRECTION_UP,
    PIP,
    ClosedTrade,
    OpenPosition,
    PendingAction,
    Result,
    _direction,
    _exit_reason,
    _fingerprint,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    EXIT_33_THRESHOLD,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

TF_MINUTES = (1, 5, 15, 60)
TF_NAMES = {1: "M1", 5: "M5", 15: "M15", 60: "H1"}
ALL_33 = frozenset({DIRECTION_UP, DIRECTION_DOWN})
SELL_33 = frozenset({DIRECTION_DOWN})
ZERO_33: frozenset[str] = frozenset()
NET_COST_PIPS = 0.40
EPS = 1e-7


@dataclass(slots=True)
class Bucket:
    """Незавершений UTC bucket поточного таймфрейму."""

    minutes: int
    start: datetime | None = None
    items: list[Bar] = field(default_factory=list)
    completed: list[Bar] = field(default_factory=list)

    def add(self, bar: Bar) -> None:
        """Завершити попередній bucket до додавання поточного M1."""
        start = bar.timestamp.replace(
            minute=bar.timestamp.minute // self.minutes * self.minutes,
            second=0,
        )
        if self.start is not None and start != self.start:
            self.finish()
        self.start = start
        self.items.append(bar)

    def finish(self) -> None:
        """Відхилити bucket з пропущеними хвилинами."""
        if self.start is None:
            return
        items = self.items
        if len(items) == self.minutes and all(
            item.timestamp == self.start + index * ONE_MINUTE
            for index, item in enumerate(items)
        ):
            self.completed.append(
                Bar(
                    timestamp=self.start,
                    open=items[0].open,
                    high=max(item.high for item in items),
                    low=min(item.low for item in items),
                    close=items[-1].close,
                )
            )
        self.start = None
        self.items = []


def _aggregate_all(
    path: Path,
    year: int,
    cutoff: datetime | None,
) -> tuple[int, int, dict[int, list[Bar]]]:
    """Один прохід M1 для чотирьох TF без look-ahead."""
    assert path.is_file(), f"MISSING_HISTORY={path}"
    buckets = {minutes: Bucket(minutes) for minutes in TF_MINUTES}
    source = selected = 0
    previous: datetime | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        assert tuple(next(reader)) == HEADER
        for cells in reader:
            assert len(cells) == 6
            timestamp = datetime.fromisoformat(
                cells[0].replace("Z", "+00:00")
            ).astimezone(UTC)
            assert timestamp.year == year
            assert timestamp.second == timestamp.microsecond == 0
            assert previous is None or previous < timestamp
            previous = timestamp
            source += 1
            if cutoff is not None and timestamp > cutoff:
                continue
            opening, high, low, closing = map(float, cells[1:5])
            assert all(
                math.isfinite(value) and value > 0
                for value in (opening, high, low, closing)
            )
            assert low <= min(opening, closing)
            assert max(opening, closing) <= high
            selected += 1
            bar = Bar(timestamp, opening, high, low, closing)
            for bucket in buckets.values():
                bucket.add(bar)
    for bucket in buckets.values():
        bucket.finish()
    result = {minutes: bucket.completed for minutes, bucket in buckets.items()}
    assert len(result[1]) == selected
    for minutes, bars in result.items():
        assert bars, f"NO_COMPLETE_{TF_NAMES[minutes]}"
        assert all(
            previous_bar.timestamp < next_bar.timestamp
            for previous_bar, next_bar in zip(bars, bars[1:])
        )
    return source, selected, result


@dataclass(slots=True)
class Engine:
    """Той самий T115-09 simulator із явним кроком TF."""

    interval: timedelta
    use_33_for: frozenset[str]
    result: Result = field(default_factory=Result)
    previous_bar_at: datetime | None = None
    previous_phase: str | None = None
    candidate_available: datetime | None = None
    pending: PendingAction | None = None
    position: OpenPosition | None = None
    peak_close_pips: float = 0.0
    active_bars: int = 0
    post_signal_active_bars: int = 0
    exposed_active_bars: int = 0

    def on_bar(
        self,
        index: int,
        bar: Bar,
        observation: WorkspaceAlligatorObservation,
    ) -> None:
        """Спершу виконати минулі сигнали, потім оцінити current close."""
        result = self.result
        assert observation.timestamp == bar.timestamp
        assert observation.available_at == bar.timestamp + self.interval
        if self.previous_bar_at is not None:
            assert bar.timestamp > self.previous_bar_at
            if bar.timestamp != self.previous_bar_at + self.interval:
                result.incomplete_time_gaps += 1
        self.previous_bar_at = bar.timestamp

        if self.candidate_available is not None:
            if bar.timestamp == self.candidate_available:
                result.next_open_available += 1
            self.candidate_available = None

        if self.pending is not None:
            action = self.pending
            assert bar.timestamp >= action.available_at
            if action.action == "ENTRY":
                assert self.position is None
                if bar.timestamp == action.available_at:
                    self.position = OpenPosition(
                        direction=action.direction,
                        entry_at=bar.timestamp,
                        entry_price=bar.open,
                        entry_index=index,
                    )
                    result.entries += 1
                    self.peak_close_pips = 0.0
                else:
                    result.entry_skipped_gap += 1
            else:
                assert action.action == "EXIT" and self.position is not None
                opened = self.position
                sign = 1 if opened.direction == DIRECTION_UP else -1
                pips = sign * (bar.open - opened.entry_price) / PIP
                gap = bar.timestamp != action.available_at
                result.trades.append(
                    ClosedTrade(
                        direction=opened.direction,
                        entry_at=opened.entry_at,
                        exit_at=bar.timestamp,
                        entry_price=opened.entry_price,
                        exit_price=bar.open,
                        pips=pips,
                        holding_bars=index - opened.entry_index,
                        holding_minutes=int(
                            (bar.timestamp - opened.entry_at).total_seconds() // 60
                        ),
                        exit_reason=action.reason,
                        exit_gap=gap,
                    )
                )
                result.exited_by_reason[action.reason] = (
                    result.exited_by_reason.get(action.reason, 0) + 1
                )
                result.exit_gap_fills += int(gap)
                self.position = None
                self.peak_close_pips = 0.0
            self.pending = None

        phase = observation.regime_phase
        active = phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        if active:
            self.active_bars += 1
            if self.previous_phase == ALLIGATOR_REGIME_PHASE_ACTIVE:
                self.post_signal_active_bars += 1
                self.exposed_active_bars += int(self.position is not None)

        if self.position is not None:
            opened = self.position
            reason = _exit_reason(phase, observation.regime, opened.direction)
            if opened.direction in self.use_33_for:
                sign = 1 if opened.direction == DIRECTION_UP else -1
                close_pips = sign * (bar.close - opened.entry_price) / PIP
                self.peak_close_pips = max(
                    self.peak_close_pips,
                    close_pips,
                )
                if reason is None and self.peak_close_pips > 0:
                    retained = self.peak_close_pips * (1 - EXIT_33_THRESHOLD)
                    if close_pips <= retained:
                        reason = EXIT_33_REASON
            if reason is not None:
                self.pending = PendingAction(
                    action="EXIT",
                    available_at=observation.available_at,
                    signal_at=observation.timestamp,
                    reason=reason,
                )
                result.exits_signaled += 1

        if active and self.previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
            direction = _direction(observation.regime)
            result.entry_signals += 1
            result.buy_signals += int(direction == DIRECTION_UP)
            result.sell_signals += int(direction == DIRECTION_DOWN)
            self.candidate_available = observation.available_at
            if self.position is None and self.pending is None:
                self.pending = PendingAction(
                    action="ENTRY",
                    available_at=observation.available_at,
                    signal_at=observation.timestamp,
                    direction=direction,
                )
            else:
                result.ignored_while_occupied += 1
        self.previous_phase = phase

    def finish(self) -> None:
        """Перевірити арифметику станів без закриття на cutoff."""
        result = self.result
        if self.pending is not None:
            if self.pending.action == "ENTRY":
                result.entry_unfilled_at_end = 1
            else:
                result.exit_pending_at_end = 1
        result.open_at_end = int(self.position is not None)
        assert result.entries == len(result.trades) + result.open_at_end
        assert result.exits_signaled == (
            len(result.trades) + result.exit_pending_at_end
        )
        assert result.entry_signals == (
            result.entries
            + result.entry_skipped_gap
            + result.entry_unfilled_at_end
            + result.ignored_while_occupied
        )
        assert result.buy_signals + result.sell_signals == result.entry_signals
        assert self.exposed_active_bars <= self.post_signal_active_bars


def _run_tf(
    bars: list[Bar],
    minutes: int,
    profile: WorkspaceAlligatorRuntimeProfile,
) -> tuple[Engine, Engine, Engine]:
    """Три сценарії з однаковими спостереженнями штатного Alligator."""
    name = TF_NAMES[minutes]
    interval = timedelta(minutes=minutes)
    scenarios = (
        Engine(interval, ZERO_33),
        Engine(interval, ALL_33),
        Engine(interval, SELL_33),
    )
    # Другий незалежний стан sim перевіряє повну детермінованість рішень.
    mirrors = (
        Engine(interval, ZERO_33),
        Engine(interval, ALL_33),
        Engine(interval, SELL_33),
    )
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=profile,
        timeframe=name,
    )
    for index, bar in enumerate(bars):
        event = WorkspaceMarketEvent(
            timestamp=bar.timestamp,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe=name,
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
        obs = signal_filter.on_market_event(
            event,
            available_at=bar.timestamp + interval,
        )
        for engine in (*scenarios, *mirrors):
            engine.on_bar(index, bar, obs)
    for engine in (*scenarios, *mirrors):
        engine.finish()
    assert all(a == b for a, b in zip(scenarios, mirrors))
    _check_paired(scenarios)
    return scenarios


def _check_paired(engines: tuple[Engine, Engine, Engine]) -> None:
    """Звірити кожен виконаний hybrid exit, включно з cutoff."""
    baseline, full33, hybrid = engines
    for engine in (full33, hybrid):
        assert engine.result.entry_signals == baseline.result.entry_signals
        assert engine.result.entries == baseline.result.entries
        assert engine.result.entry_skipped_gap == (baseline.result.entry_skipped_gap)
        assert engine.result.next_open_available == (
            baseline.result.next_open_available
        )
        assert engine.result.ignored_while_occupied == (
            baseline.result.ignored_while_occupied
        )
    original = {trade.entry_at: trade for trade in baseline.result.trades}
    all33 = {trade.entry_at: trade for trade in full33.result.trades}
    chosen = {trade.entry_at: trade for trade in hybrid.result.trades}
    assert len(original) == len(baseline.result.trades)
    assert len(all33) == len(full33.result.trades)
    assert len(chosen) == len(hybrid.result.trades)
    for entry_at, trade in chosen.items():
        if trade.direction == DIRECTION_UP:
            assert entry_at in original and trade == original[entry_at]
        else:
            assert entry_at in all33 and trade == all33[entry_at]
    assert hybrid.result.exited_by_reason.get(EXIT_33_REASON, 0) == sum(
        trade.exit_reason == EXIT_33_REASON
        for trade in all33.values()
        if trade.direction == DIRECTION_DOWN
    )


def _summary(engine: Engine, costs: float) -> str:
    """Closed-only: Net за гіпотетичною ціною round-trip."""
    trades = engine.result.trades
    pips = [trade.pips - costs for trade in trades]
    wins = sum(value > EPS for value in pips)
    losses = sum(value < -EPS for value in pips)
    gross_values: list[float] = [float(trade.pips) for trade in trades]
    gross = math.fsum(gross_values)
    net = math.fsum(pips)
    positive = math.fsum(max(value, 0.0) for value in pips)
    negative = -math.fsum(min(value, 0.0) for value in pips)
    pf = positive / negative if negative else float("inf")
    equity = peak = dd = 0.0
    for value in pips:
        equity += value
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return (
        f"CLOSED={len(trades)}|WINS={wins}|LOSSES={losses}|"
        f"GROSS_PIPS={gross:.2f}|NET_PIPS={net:.2f}|"
        f"PF_NET={pf:.3f}|MAX_CLOSED_DD_NET_PIPS={dd:.2f}"
    )


def _synthetic_check() -> None:
    """Неповний M5/H1 не стає завершеним, M1 не втрачається."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    m5 = Bucket(5)
    h1 = Bucket(60)
    one = Bucket(1)
    for offset in range(5):
        stamp = start + offset * ONE_MINUTE
        sample = Bar(stamp, 1.10, 1.11, 1.09, 1.10)
        m5.add(sample)
        h1.add(sample)
        one.add(sample)
    for bucket in (m5, h1, one):
        bucket.finish()
    assert len(m5.completed) == 1
    assert len(one.completed) == 5
    assert len(h1.completed) == 0
    broken = Bucket(5)
    for offset in (0, 1, 2, 4):
        stamp = start + offset * ONE_MINUTE
        broken.add(Bar(stamp, 1.10, 1.11, 1.09, 1.10))
    broken.finish()
    assert not broken.completed
    print("SYNTHETIC_COMPLETED_MULTITF_CAUSALITY=OK")


def main() -> None:
    """Порівняти фіксовані правила без жодної production-зміни."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-14|TEST_ONLY|CROSS_TIMEFRAME_ALLIGATOR_HYBRID")
    print("TIMEFRAMES=M1,M5,M15,H1|PARAMETERS=FIXED_4_BARS_EACH")
    print("GROSS_MID_ONLY=True|COSTS_040_HYPOTHETICAL=True")
    print("H1_VS_M1_NOT_SAME_WALL_CLOCK_HORIZON=True")
    _synthetic_check()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            path,
            int(label[:4]),
            cutoff,
        )
        assert len(aggregated[15]) == expected[0]
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        for minutes in TF_MINUTES:
            name = TF_NAMES[minutes]
            baseline, full33, hybrid = _run_tf(
                aggregated[minutes],
                minutes,
                profile,
            )
            if minutes == 15:
                result = baseline.result
                assert (
                    result.entry_signals,
                    result.buy_signals,
                    result.sell_signals,
                    result.next_open_available,
                ) == tuple(expected[1:])
                gross_expected = {
                    "2025": (-722.70, -670.50, -214.80),
                    "2026_TO_2026_08_25": (-6.30, -111.30, 190.90),
                }[label]
                for engine, gross in zip(
                    (baseline, full33, hybrid),
                    gross_expected,
                ):
                    assert math.isclose(
                        math.fsum(t.pips for t in engine.result.trades),
                        gross,
                        abs_tol=1e-5,
                    ), f"M15_BASELINE_MISMATCH:{label}"
                assert (
                    len(hybrid.result.trades),
                    hybrid.result.exited_by_reason.get(EXIT_33_REASON, 0),
                ) == ((800, 233) if label == "2025" else (505, 180))
            result = hybrid.result
            print(
                f"TF={name}|PERIOD={label}|"
                f"COMPLETED={len(aggregated[minutes])}|"
                f"ACTIVE_TRENDS={result.entry_signals}|"
                f"BUY={result.buy_signals}|"
                f"SELL={result.sell_signals}|ENTRIES={result.entries}|"
                f"ENTRY_GAP_SKIPPED={result.entry_skipped_gap}|"
                f"CLOSED={len(result.trades)}|OPEN_END={result.open_at_end}|"
                f"EARLY_SELL_33="
                f"{result.exited_by_reason.get(EXIT_33_REASON, 0)}|"
                f"EXIT_GAP_FILLS={result.exit_gap_fills}"
            )
            exposure = (
                100.0 * hybrid.exposed_active_bars / hybrid.post_signal_active_bars
                if hybrid.post_signal_active_bars
                else 0.0
            )
            print(
                f"COVERAGE|TF={name}|PERIOD={label}|"
                f"POST_SIGNAL_ACTIVE={hybrid.post_signal_active_bars}|"
                f"HYBRID_EXPOSED={hybrid.exposed_active_bars}|"
                f"HYBRID_COVERAGE_PCT={exposure:.2f}"
            )
            for variant, engine in (
                ("ALLIGATOR_ONLY", baseline),
                ("ALLIGATOR_PLUS_33", full33),
                ("HYBRID", hybrid),
            ):
                print(
                    f"SCORE|TF={name}|PERIOD={label}|VARIANT={variant}|"
                    f"SCENARIO=ZERO|{_summary(engine, 0)}"
                )
                print(
                    f"SCORE|TF={name}|PERIOD={label}|VARIANT={variant}|"
                    f"SCENARIO=MID_040|{_summary(engine, NET_COST_PIPS)}"
                )
            for direction in (DIRECTION_UP, DIRECTION_DOWN):
                trades = [
                    trade
                    for trade in hybrid.result.trades
                    if trade.direction == direction
                ]
                gross = math.fsum(trade.pips for trade in trades)
                net = gross - NET_COST_PIPS * len(trades)
                print(
                    f"HYBRID_DIRECTION|TF={name}|PERIOD={label}|"
                    f"DIRECTION={direction}|CLOSED={len(trades)}|"
                    f"GROSS_PIPS={gross:.2f}|NET040_PIPS={net:.2f}"
                )
            print(f"REPEAT_SIMULATION_DETERMINISTIC={name}:{label}:OK")
        print(f"M15_T115_01_09_BASELINE_MATCH={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_14_CROSS_TIMEFRAME_ALLIGATOR_HYBRID=OK")


if __name__ == "__main__":
    main()
