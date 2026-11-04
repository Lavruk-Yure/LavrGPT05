# -*- coding: utf-8 -*-
"""RoadMap115 / T115-16 — часовий аудит TF без зміни сигналів.

TEST_ONLY: M15, M30, H1, H4 за незмінним профілем Alligator.
Збираємо фактичну затримку STARTING -> ACTIVE, тривалість позицій
у хвилинах і затримку виконання виходів після пропусків історії.

Усі рішення і виконання ідентичні T115-15. 33% — дослідна гіпотеза.
Жодної нормалізації confirmation bars або оптимізації тут немає.
Ніяких запитів до брокера; mid OHLC та умовні витрати 0.40 pip.
Ретроспективні метрики часу НЕ використовуються як trade gates.
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
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    ALL_33,
    NET_COST_PIPS,
    SELL_33,
    TF_MINUTES,
    TF_NAMES,
    ZERO_33,
    Engine,
    _aggregate_all,
    _check_paired,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

# Перевірені базові числа T115-15, а не нові торгові припущення.
REFERENCE = {
    "2025": {
        15: (800, 0, -214.80),
        30: (360, 0, 708.30),
        60: (167, 0, 304.90),
        240: (31, 0, -185.30),
    },
    "2026_TO_2026_08_25": {
        15: (505, 1, 190.90),
        30: (232, 0, -102.00),
        60: (114, 0, -283.40),
        240: (18, 0, -58.90),
    },
}


def _minutes(later: datetime, earlier: datetime) -> int:
    """Різниця двох UTC часових міток, без округлення і DST."""
    delta = (later - earlier).total_seconds()
    assert delta >= 0 and delta % 60 == 0
    return int(delta // 60)


def _median(values: list[int]) -> str:
    """Немає значень — явно позначаємо NONE, а не нуль."""
    return f"{statistics.median(values):.2f}" if values else "NONE"


@dataclass(slots=True)
class PhaseClock:
    """Пасивно читає лише causal observations завершених TF барів."""

    previous_phase: str | None = None
    start_at: datetime | None = None
    start_regime: str | None = None
    active_count: int = 0
    observed_lags: list[int] = field(default_factory=list)
    without_starting: int = 0
    wall_excess: list[int] = field(default_factory=list)

    def on_observation(
        self,
        observation: WorkspaceAlligatorObservation,
        minutes: int,
    ) -> None:
        phase = observation.regime_phase
        if phase == ALLIGATOR_REGIME_PHASE_STARTING:
            if (
                self.previous_phase != ALLIGATOR_REGIME_PHASE_STARTING
                or self.start_regime != observation.regime
            ):
                self.start_at = observation.available_at
                self.start_regime = observation.regime
        elif (
            phase == ALLIGATOR_REGIME_PHASE_ACTIVE
            and self.previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
        ):
            self.active_count += 1
            if self.start_at is not None and self.start_regime == observation.regime:
                lag = _minutes(observation.available_at, self.start_at)
                self.observed_lags.append(lag)
                # Чотири підтверджені бари => мінімум три
                # інтервали між першим STARTING і першим ACTIVE.
                assert lag >= 3 * minutes
                self.wall_excess.append(lag - 3 * minutes)
            else:
                self.without_starting += 1
            self.start_at = None
            self.start_regime = None
        elif phase != ALLIGATOR_REGIME_PHASE_STARTING:
            self.start_at = None
            self.start_regime = None
        self.previous_phase = phase


@dataclass(slots=True)
class TimedResult:
    """Підсумки трьох незмінних симуляторів та часовий trace."""

    baseline: Engine
    all_33: Engine
    hybrid: Engine
    phase_clock: PhaseClock
    filled_exit_lags: list[int]
    exit_gap_delays: list[int]


def _simulate_with_timing(
    bars: list[Bar],
    minutes: int,
    profile: WorkspaceAlligatorRuntimeProfile,
) -> TimedResult:
    """Той самий Engine з T115-15; trace не керує ордерами."""
    interval = timedelta(minutes=minutes)
    scenarios = (
        Engine(interval, ZERO_33),
        Engine(interval, ALL_33),
        Engine(interval, SELL_33),
    )
    mirrors = (
        Engine(interval, ZERO_33),
        Engine(interval, ALL_33),
        Engine(interval, SELL_33),
    )
    filter_state = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=profile,
        timeframe=TF_NAMES[minutes],
    )
    clock = PhaseClock()
    mirror_clock = PhaseClock()
    pending_exits: dict[datetime, datetime] = {}
    entry_opens: set[datetime] = set()
    exit_lags: list[int] = []
    gap_delays: list[int] = []
    prev_count = 0

    for index, bar in enumerate(bars):
        observation = filter_state.on_market_event(
            WorkspaceMarketEvent(
                timestamp=bar.timestamp,
                broker="CTRADER",
                symbol="EURUSD",
                timeframe=TF_NAMES[minutes],
                bid=bar.close,
                ask=bar.close,
                spread=0.0,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=0.0,
                source_mode="REPLAY",
            ),
            available_at=bar.timestamp + interval,
        )
        assert observation.available_at == bar.timestamp + interval
        clock.on_observation(observation, minutes)
        mirror_clock.on_observation(observation, minutes)
        hybrid = scenarios[2]
        for engine in (*scenarios, *mirrors):
            engine.on_bar(index, bar, observation)
        assert len(hybrid.result.trades) in (prev_count, prev_count + 1)
        if len(hybrid.result.trades) != prev_count:
            trade = hybrid.result.trades[-1]
            assert trade.entry_at in entry_opens
            signal = pending_exits.pop(trade.entry_at)
            lag = _minutes(trade.exit_at, signal)
            delay = lag - minutes
            assert delay >= 0
            assert trade.exit_gap == (delay > 0)
            exit_lags.append(lag)
            if delay:
                gap_delays.append(delay)
            prev_count += 1
        if hybrid.pending is not None:
            action = hybrid.pending
            if action.action == "ENTRY":
                entry_opens.add(action.available_at)
            elif action.action == "EXIT":
                assert hybrid.position is not None
                pending_exits[hybrid.position.entry_at] = action.signal_at

    for engine in (*scenarios, *mirrors):
        engine.finish()
    assert all(a == b for a, b in zip(scenarios, mirrors))
    assert clock == mirror_clock
    _check_paired(scenarios)
    assert len(exit_lags) == len(scenarios[2].result.trades)
    assert len(gap_delays) == scenarios[2].result.exit_gap_fills
    assert clock.active_count == scenarios[2].result.entry_signals
    assert len(clock.observed_lags) + clock.without_starting == (clock.active_count)
    return TimedResult(
        baseline=scenarios[0],
        all_33=scenarios[1],
        hybrid=scenarios[2],
        phase_clock=clock,
        filled_exit_lags=exit_lags,
        exit_gap_delays=gap_delays,
    )


def _synthetic_check() -> None:
    """Перевірити часові одиниці, пропуски та медіани без ринку."""
    stamp = datetime.fromisoformat("2025-01-07T00:00:00+00:00")
    interval = timedelta(minutes=30)
    assert _minutes(stamp + interval, stamp) == 30
    assert _minutes(stamp + 3 * interval, stamp) == 90
    assert _minutes(stamp + 5 * interval, stamp) - 30 == 120
    assert _median([15, 45]) == "30.00"
    assert _median([]) == "NONE"
    assert 4 * 15 == 60 and 4 * 30 == 120
    assert 4 * 60 == 240 and 4 * 240 == 960
    print("SYNTHETIC_TF_TEMPORAL_CAUSALITY=OK")


def _print_timing(label: str, minutes: int, run: TimedResult) -> None:
    """Тільки retrospective timing metrics, без вибору кращого TF."""
    hybrid = run.hybrid
    result = hybrid.result
    trades = result.trades
    closed = len(trades)
    target_closed, target_open, target_gross = REFERENCE[label][minutes]
    gross = math.fsum(float(t.pips) for t in trades)
    assert closed == target_closed
    assert result.open_at_end == target_open
    assert math.isclose(gross, target_gross, abs_tol=1e-5)
    assert run.phase_clock.active_count == result.entry_signals
    holding_mins = [t.holding_minutes for t in trades]
    holding_bars = [t.holding_bars for t in trades]
    buys = [t.holding_minutes for t in trades if t.direction == DIRECTION_UP]
    sells = [t.holding_minutes for t in trades if t.direction == DIRECTION_DOWN]
    with_internal_gap = sum(
        t.holding_minutes > t.holding_bars * minutes for t in trades
    )
    cost = closed * NET_COST_PIPS
    net = gross - cost
    clock = run.phase_clock
    name = TF_NAMES[minutes]
    print(
        f"TF={name}|PERIOD={label}|"
        f"CONFIRMATION_BARS=4|NOMINAL_CONFIRMATION_MIN={4 * minutes}|"
        f"SIGNAL_TO_CONTIGUOUS_ENTRY_OPEN_MIN={minutes}"
    )
    print(
        f"PHASE_TIMING|TF={name}|PERIOD={label}|"
        f"ACTIVE={clock.active_count}|"
        f"STARTING_OBSERVED={len(clock.observed_lags)}|"
        f"STARTING_UNMATCHED={clock.without_starting}|"
        f"FIRST_STARTING_TO_ACTIVE_MEDIAN_WALL_MIN="
        f"{_median(clock.observed_lags)}|"
        f"EXCESS_GAP_MEDIAN_MIN={_median(clock.wall_excess)}|"
        f"WITH_EXCESS_GAP={sum(v > 0 for v in clock.wall_excess)}"
    )
    print(
        f"POSITION_TIMING|TF={name}|PERIOD={label}|"
        f"CLOSED={closed}|OPEN_END={result.open_at_end}|"
        f"HOLD_MEDIAN_OBS_BARS={_median(holding_bars)}|"
        f"HOLD_MEDIAN_WALL_MIN={_median(holding_mins)}|"
        f"BUY_HOLD_MEDIAN_WALL_MIN={_median(buys)}|"
        f"SELL_HOLD_MEDIAN_WALL_MIN={_median(sells)}|"
        f"HOLD_WITH_TIME_GAPS={with_internal_gap}"
    )
    print(
        f"EXIT_TIMING|TF={name}|PERIOD={label}|"
        f"EXIT_FILL_LAG_MEDIAN_FROM_SIGNAL_BAR_MIN="
        f"{_median(run.filled_exit_lags)}|"
        f"EXIT_GAP_FILLS={len(run.exit_gap_delays)}|"
        f"EXIT_GAP_EXTRA_MEDIAN_MIN={_median(run.exit_gap_delays)}|"
        f"ENTRY_GAP_SKIPPED={result.entry_skipped_gap}"
    )
    print(
        f"COST_DENSITY|TF={name}|PERIOD={label}|"
        f"CLOSED={closed}|GROSS_PIPS={gross:.2f}|"
        f"COST_040_PIPS={cost:.2f}|NET_040_PIPS={net:.2f}|"
        f"AVG_NET_PER_CLOSED={net / closed:.3f}"
    )


def main() -> None:
    """Підтвердити часові відмінності TF із незмінним Replay."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(p): _fingerprint(p) for p in guarded}
    print("T115-16|TEST_ONLY|CROSS_TF_TEMPORAL_EXPOSURE_AUDIT")
    print("TF=M15,M30,H1,H4|CONFIRMATION_FIXED_4_BARS=True")
    print("TIME_NORMALIZATION_APPLIED=False|POST_HOC_ANALYSIS_ONLY=True")
    _synthetic_check()
    profile = _profile()
    assert profile.effective_trend_start_confirmation_bars == 4
    for label, filename, *expected in PERIODS:
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
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
            run = _simulate_with_timing(aggregated[minutes], minutes, profile)
            _print_timing(label, minutes, run)
            print(f"REPLAY_MIRROR_DETERMINISTIC=" f"{TF_NAMES[minutes]}:{label}:OK")
    assert before == {str(p): _fingerprint(p) for p in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_16_CROSS_TF_TEMPORAL_EXPOSURE_AUDIT=OK")


if __name__ == "__main__":
    main()
