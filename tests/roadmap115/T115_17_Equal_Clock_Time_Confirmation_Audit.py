# -*- coding: utf-8 -*-
"""RoadMap115 / T115-17 — однакова номінальна тривалість підтвердження.

TEST_ONLY. Порівнюємо з незмінним baseline T115-15 (4 бари для всіх TF):
M15=4, M30=2, H1=1 — номінально по 60 хвилин на підтвердження.
H4=1 — окремий мінімально можливий контроль (240 хв), НЕ 60 хв.

Зміна кількості барів стосується ЛИШЕ копії runtime-профілю в тесті.
Решта параметрів Alligator, виходи й умови виконання без змін.
Перевіряємо Alligator-only, Alligator+33% і гібрид BUY/SELL.
Правило 33% залишається непідтвердженою TEST_ONLY гіпотезою.

При n=1 ACTIVE може настати без проміжної STARTING; рівна тривалість
барів не означає однакової інформаційної затримки різних TF.
Немає look-ahead у рішеннях. Розриви не заповнюються. OHLC mid;
0,40 pip round-trip — умовні, а не фактичні брокерські витрати.
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
from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    Bar,
    CANONICAL_2026_END,
    PERIODS,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
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
    _summary,
    _synthetic_check,
)

FIXED_BASELINE_BARS = 4
NOMINAL_TARGET_MINUTES = 60
EQUAL_CLOCK_BARS = {15: 4, 30: 2, 60: 1, 240: 1}

# Зафіксовані раніше результати T115-15, щоб виявити регресію.
REFERENCE_BASELINE = {
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


@dataclass(slots=True)
class PhaseAudit:
    """Вимірювати STARTING→ACTIVE, не впливаючи на рішення."""

    previous_phase: str | None = None
    first_starting: datetime | None = None
    starting_regime: str | None = None
    active_transitions: int = 0
    active_with_starting: int = 0
    active_without_starting: int = 0
    starting_to_active_minutes: list[int] = field(default_factory=list)

    def see(self, obs: WorkspaceAlligatorObservation) -> None:
        """Прочитати лише щойно завершене спостереження."""
        phase = obs.regime_phase
        if phase == ALLIGATOR_REGIME_PHASE_STARTING:
            if (
                self.previous_phase != ALLIGATOR_REGIME_PHASE_STARTING
                or self.starting_regime != obs.regime
            ):
                self.first_starting = obs.available_at
                self.starting_regime = obs.regime
        elif (
            phase == ALLIGATOR_REGIME_PHASE_ACTIVE
            and self.previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
        ):
            self.active_transitions += 1
            if (
                self.first_starting is not None
                and self.starting_regime == obs.regime
            ):
                delta = obs.available_at - self.first_starting
                minutes = int(delta.total_seconds() // 60)
                assert minutes >= 0
                self.starting_to_active_minutes.append(minutes)
                self.active_with_starting += 1
            else:
                self.active_without_starting += 1
            self.first_starting = None
            self.starting_regime = None
        elif phase != ALLIGATOR_REGIME_PHASE_STARTING:
            self.first_starting = None
            self.starting_regime = None
        self.previous_phase = phase

    def describe(self) -> str:
        """Показати фактичне, а не лише номінальне підтвердження."""
        lags = self.starting_to_active_minutes
        median = f"{statistics.median(lags):.2f}" if lags else "NONE"
        assert self.active_transitions == (
            self.active_with_starting + self.active_without_starting
        )
        return (
            f"ACTIVE={self.active_transitions}|"
            f"WITH_STARTING={self.active_with_starting}|"
            f"WITHOUT_STARTING={self.active_without_starting}|"
            f"STARTING_TO_ACTIVE_MEDIAN_MIN={median}"
        )


def _replay(
    bars: list[Bar],
    minutes: int,
    profile: WorkspaceAlligatorRuntimeProfile,
) -> tuple[tuple[Engine, Engine, Engine], PhaseAudit]:
    """Незмінний Engine T115-15, інший лише тестовий profile."""
    step = timedelta(minutes=minutes)
    variants = (
        Engine(step, ZERO_33),
        Engine(step, ALL_33),
        Engine(step, SELL_33),
    )
    mirrors = (
        Engine(step, ZERO_33),
        Engine(step, ALL_33),
        Engine(step, SELL_33),
    )
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=profile,
        timeframe=TF_NAMES[minutes],
    )
    clock = PhaseAudit()
    for index, bar in enumerate(bars):
        obs = signal_filter.on_market_event(
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
            available_at=bar.timestamp + step,
        )
        assert obs.timestamp == bar.timestamp
        assert obs.available_at == bar.timestamp + step
        clock.see(obs)
        for engine in (*variants, *mirrors):
            engine.on_bar(index, bar, obs)
    for engine in (*variants, *mirrors):
        engine.finish()
    assert all(a == b for a, b in zip(variants, mirrors))
    _check_paired(variants)
    assert clock.active_transitions == variants[2].result.entry_signals
    return variants, clock


def _gross(engine: Engine) -> float:
    """Підсумок без витрат лише по завершених угодах."""
    values: list[float] = [float(t.pips) for t in engine.result.trades]
    return math.fsum(values)


def _net(engine: Engine) -> float:
    """Однакові умовні витрати для всіх порівнянь."""
    return _gross(engine) - NET_COST_PIPS * len(engine.result.trades)


def _regression(
    label: str, minutes: int, hybrid: Engine,
) -> None:
    """Baseline з 4 барами мусить відтворити T115-15."""
    count, open_end, gross = REFERENCE_BASELINE[label][minutes]
    assert len(hybrid.result.trades) == count
    assert hybrid.result.open_at_end == open_end
    assert math.isclose(_gross(hybrid), gross, abs_tol=1e-5)


def _synthetic_confirmation() -> None:
    """Окремо перевірити ефект 1/2/4 на причинному тренді."""
    profile = _profile()
    start = datetime.fromisoformat("2025-01-06T00:00:00+00:00")
    bars: list[Bar] = []
    for index in range(120):
        price = 1.1000 + index * 0.0001
        bars.append(Bar(
            start + timedelta(minutes=15 * index),
            price,
            price + 0.0002,
            price - 0.0002,
            price + 0.0001,
        ))
    entries: dict[int, datetime] = {}
    for count in (1, 2, 4):
        trial = replace(profile, trend_start_confirmation_bars=count)
        assert trial.effective_trend_start_confirmation_bars == count
        engines, trace = _replay(bars, 15, trial)
        hybrid = engines[2]
        assert hybrid.result.entry_signals == 1
        assert hybrid.result.entries == 1
        assert hybrid.result.open_at_end == 1
        assert not hybrid.result.trades
        assert hybrid.position is not None
        entries[count] = hybrid.position.entry_at
        assert trace.active_transitions == 1
        if count == 1:
            assert trace.active_without_starting == 1
        else:
            assert trace.active_with_starting == 1
            assert trace.starting_to_active_minutes == [15 * (count - 1)]
    assert entries[2] - entries[1] == timedelta(minutes=15)
    assert entries[4] - entries[1] == timedelta(minutes=45)
    print("SYNTHETIC_CONFIRMATION_PROFILE_ISOLATION=OK")


def main() -> None:
    """Порівняти часову нормалізацію без зміни production."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-17|TEST_ONLY|EQUAL_CLOCK_TIME_CONFIRMATION_AUDIT")
    print("TARGET_NOMINAL_CONFIRMATION_MIN=60|H4_NOT_EQUALIZABLE=True")
    print("PROFILE_CHANGE=TEST_ONLY_CONFIRMATION_BARS_ONLY")
    print("ENTRY_EXIT=UNCHANGED_T115_15|33_PERCENT=HYPOTHESIS_ONLY")
    _synthetic_check()
    _synthetic_confirmation()
    standard = _profile()
    assert standard.effective_trend_start_confirmation_bars == 4
    print(
        f"PROFILE={standard.profile_uid}|REVISION={standard.profile_revision}|"
        f"BASE_CONFIRMATION_BARS={FIXED_BASELINE_BARS}"
    )
    collected: dict[int, dict[str, tuple[float, float]]] = {
        minutes: {} for minutes in TF_MINUTES
    }
    for label, filename, *expected in PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            path, int(label[:4]), cutoff,
        )
        assert len(aggregated[15]) == expected[0]
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        for minutes in TF_MINUTES:
            name = TF_NAMES[minutes]
            proposed_bars = EQUAL_CLOCK_BARS[minutes]
            assert proposed_bars >= 1
            assert proposed_bars * minutes == (
                240 if minutes == 240 else NOMINAL_TARGET_MINUTES
            )
            old, old_phase = _replay(aggregated[minutes], minutes, standard)
            _regression(label, minutes, old[2])
            if proposed_bars == FIXED_BASELINE_BARS:
                new, new_phase = old, old_phase
            else:
                trial_profile = replace(
                    standard, trend_start_confirmation_bars=proposed_bars,
                )
                new, new_phase = _replay(
                    aggregated[minutes], minutes, trial_profile,
                )
            old_hybrid, new_hybrid = old[2], new[2]
            old_net, new_net = _net(old_hybrid), _net(new_hybrid)
            collected[minutes][label] = (old_net, new_net)
            print(
                f"TF={name}|PERIOD={label}|"
                f"COMPLETED={len(aggregated[minutes])}|"
                f"BASE_BARS=4|TRIAL_BARS={proposed_bars}|"
                f"BASE_NOMINAL_MIN={4 * minutes}|"
                f"TRIAL_NOMINAL_MIN={proposed_bars * minutes}|"
                f"EQUAL_60_MIN={minutes != 240}"
            )
            print(
                f"PHASE_BASE|TF={name}|PERIOD={label}|"
                f"{old_phase.describe()}"
            )
            print(
                f"PHASE_TRIAL|TF={name}|PERIOD={label}|"
                f"{new_phase.describe()}"
            )
            for variant, a, b in zip(
                ("ALLIGATOR_ONLY", "ALLIGATOR_PLUS_33", "HYBRID"),
                old,
                new,
            ):
                print(
                    f"BASE|TF={name}|PERIOD={label}|VARIANT={variant}|"
                    f"{_summary(a, NET_COST_PIPS)}"
                )
                print(
                    f"TRIAL|TF={name}|PERIOD={label}|VARIANT={variant}|"
                    f"{_summary(b, NET_COST_PIPS)}"
                )
            print(
                f"HYBRID_CHANGE|TF={name}|PERIOD={label}|"
                f"BASE_ACTIVE={old_hybrid.result.entry_signals}|"
                f"TRIAL_ACTIVE={new_hybrid.result.entry_signals}|"
                f"BASE_CLOSED={len(old_hybrid.result.trades)}|"
                f"TRIAL_CLOSED={len(new_hybrid.result.trades)}|"
                f"BASE_OPEN_END={old_hybrid.result.open_at_end}|"
                f"TRIAL_OPEN_END={new_hybrid.result.open_at_end}|"
                f"BASE_NET040={old_net:.2f}|TRIAL_NET040={new_net:.2f}|"
                f"DELTA_NET040={new_net - old_net:.2f}"
            )
            print(f"REPLAY_MIRROR_DETERMINISTIC={name}:{label}:OK")
        print(f"T115_15_BASELINE_MATCH={label}:OK")
    for minutes in TF_MINUTES:
        name = TF_NAMES[minutes]
        first = collected[minutes]["2025"]
        second = collected[minutes]["2026_TO_2026_08_25"]
        positive_both = first[1] > 0 and second[1] > 0
        print(
            f"CROSS_PERIOD|TF={name}|"
            f"TRIAL_NET040_2025={first[1]:.2f}|"
            f"TRIAL_NET040_2026={second[1]:.2f}|"
            f"POSITIVE_BOTH={positive_both}"
        )
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_17_EQUAL_CLOCK_TIME_CONFIRMATION_AUDIT=OK")


if __name__ == "__main__":
    main()
