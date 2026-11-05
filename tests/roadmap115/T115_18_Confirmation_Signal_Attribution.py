# -*- coding: utf-8 -*-
"""RoadMap115 / T115-18 — attribution підтвердження Alligator.

TEST_ONLY. M30 (4→2 бари) і H1 (4→1 бар) з T115-17.
Порівняння однакових causal епізодів regime/state, а не довільного
часового вікна. Епізод — послідовність спостережених вирівняних барів
з одним напрямком, яку завершує втрата alignment або фаза ENDING.
Неповні бари НЕ створюються, розриви історії не заповнюються.

Outcome attribution виконується ПІСЛЯ симуляції. Вона не впливає на
торгові рішення та не є доказом прогнозної здатності нових ознак.
Дельти включають як зміну часу входу, так і наслідки правила виходу;
без окремого paired-exit тесту не приписувати їх лише кращому входу.
Витрати 0.40 pip round-trip — умовні, OHLC mid, без broker fills.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass, field, replace
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
    ClosedTrade,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    SELL_33,
    TF_NAMES,
    Engine,
    _aggregate_all,
    _summary,
    _synthetic_check,
)
from T115_17_Equal_Clock_Time_Confirmation_Audit import (  # noqa: E402
    _net,
    _regression,
    _synthetic_confirmation,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

TIMEFRAMES = (30, 60)
TRIAL_BARS = {30: 2, 60: 1}
EPS = 1e-6
EXPECTED_NET = {
    "2025": {
        30: (564.30, 390.40),
        60: (238.10, 953.40),
    },
    "2026_TO_2026_08_25": {
        30: (-194.80, -64.10),
        60: (-329.00, -347.80),
    },
}


@dataclass(frozen=True, slots=True)
class Signal:
    """Тільки causal ACTIVE-перехід на завершеному барі."""

    episode: int
    signal_at: datetime
    available_at: datetime
    direction: str
    episode_start_at: datetime


@dataclass(slots=True)
class Trace:
    """Два незалежні фільтри ідентифікують спільні episodes."""

    previous_key: str | None = None
    previous_base_phase: str | None = None
    previous_trial_phase: str | None = None
    episode: int = 0
    episode_start_at: datetime | None = None
    baseline: dict[int, Signal] = field(default_factory=dict)
    trial: dict[int, Signal] = field(default_factory=dict)

    def see(
        self,
        base: WorkspaceAlligatorObservation,
        trial: WorkspaceAlligatorObservation,
    ) -> None:
        """Зафіксувати episode та ACTIVE без перегляду майбутніх барів."""
        assert base.timestamp == trial.timestamp
        assert base.available_at == trial.available_at
        assert base.regime == trial.regime
        assert base.state == trial.state
        assert (base.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING) == (
            trial.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING
        )
        key: str | None = None
        if base.regime == ALLIGATOR_REGIME_TREND_UP:
            if base.state == ALLIGATOR_STATE_BULLISH:
                key = base.regime
        elif base.regime == ALLIGATOR_REGIME_TREND_DOWN:
            if base.state == ALLIGATOR_STATE_BEARISH:
                key = base.regime
        if base.regime_phase == ALLIGATOR_REGIME_PHASE_ENDING:
            key = None
        if key is not None and key != self.previous_key:
            self.episode += 1
            self.episode_start_at = base.timestamp
        if key is None:
            self.episode_start_at = None
        self.previous_key = key
        for observation, previous_phase, target in (
            (base, self.previous_base_phase, self.baseline),
            (trial, self.previous_trial_phase, self.trial),
        ):
            if (
                observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
                and previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
            ):
                assert key is not None
                assert self.episode_start_at is not None
                assert self.episode not in target
                direction = (
                    DIRECTION_UP if key == ALLIGATOR_REGIME_TREND_UP else DIRECTION_DOWN
                )
                target[self.episode] = Signal(
                    self.episode,
                    observation.timestamp,
                    observation.available_at,
                    direction,
                    self.episode_start_at,
                )
        self.previous_base_phase = base.regime_phase
        self.previous_trial_phase = trial.regime_phase


def _run_pair(
    bars: list[Bar],
    minutes: int,
) -> tuple[Engine, Engine, Trace]:
    """Одні й ті самі завершені OHLC для двох профілів."""
    assert minutes in TIMEFRAMES
    step = timedelta(minutes=minutes)
    standard = _profile()
    trial_profile = replace(
        standard,
        trend_start_confirmation_bars=TRIAL_BARS[minutes],
    )
    filters = [
        WorkspaceAlligatorFilter(
            enabled=True,
            confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            runtime_profile=profile,
            timeframe=TF_NAMES[minutes],
        )
        for profile in (standard, trial_profile)
    ]
    engines = [Engine(step, SELL_33) for _ in range(4)]
    trace = Trace()
    for index, bar in enumerate(bars):
        event = WorkspaceMarketEvent(
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
        )
        current = [
            signal_filter.on_market_event(
                event,
                available_at=bar.timestamp + step,
            )
            for signal_filter in filters
        ]
        trace.see(current[0], current[1])
        for engine, obs in zip(engines, (current * 2)):
            engine.on_bar(index, bar, obs)
    for engine in engines:
        engine.finish()
    assert engines[0] == engines[2]
    assert engines[1] == engines[3]
    assert len(trace.baseline) == engines[0].result.entry_signals
    assert len(trace.trial) == engines[1].result.entry_signals
    return engines[0], engines[1], trace


def _trade_lookup(
    engine: Engine,
    signals: dict[int, Signal],
) -> tuple[dict[int, ClosedTrade], set[int]]:
    """Пов'язати виконані entry з їхнім власним causal сигналом."""
    lookup = {item.available_at: item.episode for item in signals.values()}
    assert len(lookup) == len(signals)
    closed: dict[int, ClosedTrade] = {}
    for trade in engine.result.trades:
        assert trade.entry_at in lookup
        episode = lookup[trade.entry_at]
        assert episode not in closed
        assert trade.entry_at > signals[episode].signal_at
        closed[episode] = trade
    open_episodes: set[int] = set()
    if engine.position is not None:
        assert engine.position.entry_at in lookup
        episode = lookup[engine.position.entry_at]
        assert episode not in closed
        open_episodes.add(episode)
    assert len(closed) + len(open_episodes) == engine.result.entries
    assert len(open_episodes) == engine.result.open_at_end
    return closed, open_episodes


@dataclass(frozen=True, slots=True)
class Attribution:
    """Повний closed-only внесок одного episode у зміну Net."""

    episode: int
    category: str
    direction: str
    event_at: datetime
    baseline_net: float
    trial_net: float
    base_closed: int
    trial_closed: int
    base_open: int
    trial_open: int
    delta_minutes: int | None

    @property
    def delta(self) -> float:
        return self.trial_net - self.baseline_net


def _category(base: Signal | None, trial: Signal | None) -> str:
    """Визначити природу збігу, не дивлячись на результат угоди."""
    if base is None:
        assert trial is not None
        return "TRIAL_ONLY"
    if trial is None:
        return "BASE_ONLY"
    assert base.direction == trial.direction
    if base.signal_at == trial.signal_at:
        return "BOTH_SAME"
    if trial.signal_at < base.signal_at:
        return "BOTH_EARLIER"
    return "BOTH_LATER"


def _attribute(
    base: Engine,
    trial: Engine,
    trace: Trace,
) -> list[Attribution]:
    """Звірити суму епізодних змін із фактичною зміною Replay."""
    old, old_open = _trade_lookup(base, trace.baseline)
    new, new_open = _trade_lookup(trial, trace.trial)
    result: list[Attribution] = []
    for episode in sorted(trace.baseline.keys() | trace.trial.keys()):
        old_event = trace.baseline.get(episode)
        new_event = trace.trial.get(episode)
        event = new_event if new_event is not None else old_event
        assert event is not None
        earlier = None
        if old_event is not None and new_event is not None:
            earlier = int(
                (old_event.signal_at - new_event.signal_at).total_seconds() // 60
            )
        old_trade = old.get(episode)
        new_trade = new.get(episode)
        old_net = old_trade.pips - NET_COST_PIPS if old_trade is not None else 0.0
        new_net = new_trade.pips - NET_COST_PIPS if new_trade is not None else 0.0
        result.append(
            Attribution(
                episode=episode,
                category=_category(old_event, new_event),
                direction=event.direction,
                event_at=event.episode_start_at,
                baseline_net=old_net,
                trial_net=new_net,
                base_closed=int(old_trade is not None),
                trial_closed=int(new_trade is not None),
                base_open=int(episode in old_open),
                trial_open=int(episode in new_open),
                delta_minutes=earlier,
            )
        )
    assert sum(item.base_closed for item in result) == len(base.result.trades)
    assert sum(item.trial_closed for item in result) == len(trial.result.trades)
    assert sum(item.base_open for item in result) == base.result.open_at_end
    assert sum(item.trial_open for item in result) == trial.result.open_at_end
    base_total = math.fsum([item.baseline_net for item in result])
    trial_total = math.fsum([item.trial_net for item in result])
    delta_total = math.fsum([item.delta for item in result])
    assert math.isclose(base_total, _net(base), abs_tol=EPS)
    assert math.isclose(trial_total, _net(trial), abs_tol=EPS)
    assert math.isclose(
        delta_total,
        _net(trial) - _net(base),
        abs_tol=EPS,
    )
    return result


def _synthetic_attribution() -> None:
    """Перевірити класифікацію без ціни або майбутнього результату."""
    at = datetime.fromisoformat("2025-01-06T00:00:00+00:00")
    old = Signal(
        1,
        at + timedelta(minutes=90),
        at + timedelta(minutes=120),
        DIRECTION_UP,
        at,
    )
    new = Signal(
        1,
        at + timedelta(minutes=30),
        at + timedelta(minutes=60),
        DIRECTION_UP,
        at,
    )
    assert _category(old, new) == "BOTH_EARLIER"
    assert _category(new, old) == "BOTH_LATER"
    assert _category(old, old) == "BOTH_SAME"
    assert _category(None, new) == "TRIAL_ONLY"
    assert _category(old, None) == "BASE_ONLY"
    assert _category(
        Signal(
            1,
            at,
            at + timedelta(minutes=30),
            DIRECTION_UP,
            at,
        ),
        new,
    ) == ("BOTH_LATER")
    print("SYNTHETIC_SIGNAL_EPISODE_ATTRIBUTION=OK")


def _describe(
    label: str,
    minutes: int,
    items: list[Attribution],
    base: Engine,
    trial: Engine,
) -> None:
    """Відділити зміни сигналів, виконання та вплив outliers."""
    name = TF_NAMES[minutes]
    base_net = _net(base)
    trial_net = _net(trial)
    delta = trial_net - base_net
    categories = (
        "BOTH_SAME",
        "BOTH_EARLIER",
        "BOTH_LATER",
        "TRIAL_ONLY",
        "BASE_ONLY",
    )
    assert math.isclose(
        math.fsum([item.delta for item in items]),
        delta,
        abs_tol=EPS,
    )
    print(
        f"ATTRIBUTION|TF={name}|PERIOD={label}|"
        f"BASE_CLOSED={len(base.result.trades)}|"
        f"TRIAL_CLOSED={len(trial.result.trades)}|"
        f"BASE_NET040={base_net:.2f}|TRIAL_NET040={trial_net:.2f}|"
        f"DELTA_NET040={delta:.2f}|EPISODES={len(items)}"
    )
    for category in categories:
        group = [item for item in items if item.category == category]
        base_part = math.fsum([item.baseline_net for item in group])
        trial_part = math.fsum([item.trial_net for item in group])
        difference = math.fsum([item.delta for item in group])
        changed = sum(abs(item.delta) > EPS for item in group)
        shifts: list[int] = []
        for item in group:
            if item.delta_minutes is not None:
                shifts.append(item.delta_minutes)
        median_shift = f"{statistics.median(shifts):.1f}" if shifts else "NONE"
        print(
            f"CATEGORY|TF={name}|PERIOD={label}|TYPE={category}|"
            f"EPISODES={len(group)}|"
            f"BASE_CLOSED={sum(i.base_closed for i in group)}|"
            f"TRIAL_CLOSED={sum(i.trial_closed for i in group)}|"
            f"BASE_OPEN={sum(i.base_open for i in group)}|"
            f"TRIAL_OPEN={sum(i.trial_open for i in group)}|"
            f"CHANGED_NET_EPISODES={changed}|"
            f"BASE_NET040={base_part:.2f}|"
            f"TRIAL_NET040={trial_part:.2f}|"
            f"DELTA_NET040={difference:.2f}|"
            f"SHIFT_BASE_MINUS_TRIAL_MEDIAN_MIN={median_shift}"
        )
    for direction in (DIRECTION_UP, DIRECTION_DOWN):
        group = [item for item in items if item.direction == direction]
        print(
            f"DIRECTION|TF={name}|PERIOD={label}|DIRECTION={direction}|"
            f"EPISODES={len(group)}|"
            f"DELTA_NET040={math.fsum([i.delta for i in group]):.2f}"
        )
    most = sorted(items, key=lambda item: (-abs(item.delta), item.episode))
    for amount in (1, 3, 5, 10):
        top = most[:amount]
        rest = most[amount:]
        absolute = math.fsum([abs(item.delta) for item in items])
        share = (
            math.fsum([abs(item.delta) for item in top]) / absolute * 100
            if absolute
            else 0.0
        )
        print(
            f"OUTLIER|TF={name}|PERIOD={label}|TOP_ABS={amount}|"
            f"SHARE_ABS_DELTA_PCT={share:.2f}|"
            f"TOP_SIGNED_DELTA={math.fsum([i.delta for i in top]):.2f}|"
            f"REMAINDER_DELTA={math.fsum([i.delta for i in rest]):.2f}"
        )
    for rank, item in enumerate(most[:3], 1):
        print(
            f"CASE|TF={name}|PERIOD={label}|RANK={rank}|"
            f"EPISODE_START={item.event_at.isoformat()}|"
            f"DIRECTION={item.direction}|CLASS={item.category}|"
            f"BASE_NET040={item.baseline_net:.2f}|"
            f"TRIAL_NET040={item.trial_net:.2f}|"
            f"DELTA_NET040={item.delta:.2f}"
        )
    assert math.isclose(
        math.fsum(
            math.fsum([i.delta for i in items if i.category == category])
            for category in categories
        ),
        delta,
        abs_tol=EPS,
    )
    print(f"EPISODE_NET_RECONCILIATION={name}:{label}:OK")


def _synthetic_episode_link() -> None:
    """Синтетичний BUY має спільний episode та різний ACTIVE."""
    start = datetime.fromisoformat("2025-01-06T00:00:00+00:00")
    bars: list[Bar] = []
    for index in range(120):
        opening = 1.1000 + index * 0.0001
        bars.append(
            Bar(
                start + index * timedelta(minutes=30),
                opening,
                opening + 0.0002,
                opening - 0.0002,
                opening + 0.0001,
            )
        )
    baseline, trial, trace = _run_pair(bars, 30)
    assert len(trace.baseline) == len(trace.trial) == 1
    shared = next(iter(trace.baseline))
    assert shared in trace.trial
    assert _category(trace.baseline[shared], trace.trial[shared]) == ("BOTH_EARLIER")
    assert trace.baseline[shared].signal_at - (
        trace.trial[shared].signal_at
    ) == timedelta(minutes=60)
    records = _attribute(baseline, trial, trace)
    assert len(records) == 1
    assert records[0].base_open == records[0].trial_open == 1
    print("SYNTHETIC_PAIRED_EPISODE_LINK=OK")


def main() -> None:
    """Виконати paired anatomy без production-модифікацій."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-18|TEST_ONLY|CONFIRMATION_SIGNAL_ATTRIBUTION")
    print("TIMEFRAMES=M30,H1|BASE=4_BARS|TRIAL_M30=2|TRIAL_H1=1")
    print("EPISODE_KEY=CAUSAL_ALIGNED_REGIME_STATE|POST_HOC=TRUE")
    print("NET040=HYPOTHETICAL|ENTRY_EXIT_SIM_UNCHANGED=True")
    _synthetic_check()
    _synthetic_confirmation()
    _synthetic_attribution()
    _synthetic_episode_link()
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
        for minutes in TIMEFRAMES:
            baseline, trial, trace = _run_pair(aggregated[minutes], minutes)
            _regression(label, minutes, baseline)
            assert math.isclose(
                _net(baseline),
                EXPECTED_NET[label][minutes][0],
                abs_tol=EPS,
            )
            assert math.isclose(
                _net(trial),
                EXPECTED_NET[label][minutes][1],
                abs_tol=EPS,
            )
            print(
                f"BASE|TF={TF_NAMES[minutes]}|PERIOD={label}|"
                f"{_summary(baseline, NET_COST_PIPS)}"
            )
            print(
                f"TRIAL|TF={TF_NAMES[minutes]}|PERIOD={label}|"
                f"{_summary(trial, NET_COST_PIPS)}"
            )
            outcome = _attribute(baseline, trial, trace)
            _describe(label, minutes, outcome, baseline, trial)
            print(f"REPLAY_MIRROR_DETERMINISTIC={TF_NAMES[minutes]}:" f"{label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_18_CONFIRMATION_SIGNAL_ATTRIBUTION=OK")


if __name__ == "__main__":
    main()
