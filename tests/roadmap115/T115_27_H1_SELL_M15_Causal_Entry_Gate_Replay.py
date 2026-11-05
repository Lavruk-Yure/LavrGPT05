# -*- coding: utf-8 -*-
"""RoadMap115 / T115-27 — causal H1 SELL entry gate (TEST_ONLY).

Єдина пробна зміна: відхилення H1 SELL на open виконання, якщо
останній доступний завершений M15 строго до open має ACTIVE_ALIGNED.
H1 Alligator (4 бари), BUY, ENDING та SELL 33% — незмінні.
Використовуються повні суміжні M1, без forward-fill чи look-ahead.
Умовні 0.40 pip round-trip, mid OHLC, без реального брокера.
Результат не є out-of-sample доказом або production-рішенням.
"""

from __future__ import annotations

import math
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
    PendingAction,
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
from T115_21_H1_M15_Trend_Watch_Audit import (  # noqa: E402
    EXPECTED_H1,
    H1_MIN,
    H1_SPAN,
    M15_MIN,
    M15_SPAN,
    WatchBar,
    _event,
    _filter,
    _observe_m15,
    _synthetic_watch,
)
from T115_25_H1_Entry_M15_State_Anatomy import (  # noqa: E402
    _category,
    _entries,
    _synthetic_entry_boundary,
)
from T115_26_H1_SELL_M15_Aligned_Reject_Cost_Audit import (  # noqa: E402
    EXPECTED_REJECT,
    _reject,
    _score,
    _synthetic_cost,
)

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorObservation,
)

RULE = "SELL_AND_STRICT_PRE_ENTRY_M15_ACTIVE_ALIGNED"
REFERENCE_NET = {
    "2025": 238.10,
    "2026_TO_2026_08_25": -329.00,
}


@dataclass(frozen=True, slots=True)
class GateReject:
    """Causal відмова на H1 open без доступу до майбутнього."""

    at: datetime
    signal_at: datetime
    m15_at: datetime
    direction: str


@dataclass(slots=True)
class GateEngine(Engine):
    """Той самий H1 Engine із єдиним блокуванням pending SELL."""

    gate_enabled: bool = True
    rejected: list[GateReject] = field(default_factory=list)

    def on_bar(
        self,
        index: int,
        bar: Bar,
        observation: WorkspaceAlligatorObservation,
        strict_m15: WatchBar | None = None,
    ) -> None:
        """Виконати gate тільки на наступному суміжному H1 open."""
        action = self.pending
        if self.gate_enabled and action is not None:
            if self.must_reject(bar.timestamp, action, strict_m15):
                assert self.position is None
                assert strict_m15 is not None
                assert strict_m15.at == bar.timestamp - M15_SPAN
                assert strict_m15.at < bar.timestamp
                self.rejected.append(
                    GateReject(
                        at=bar.timestamp,
                        signal_at=action.signal_at,
                        m15_at=strict_m15.at,
                        direction=action.direction,
                    )
                )
                self.pending = None
        Engine.on_bar(self, index, bar, observation)

    @staticmethod
    def must_reject(
        at: datetime,
        action: PendingAction,
        strict_m15: WatchBar | None,
    ) -> bool:
        """Gap, BUY, stale M15 та same-tick не запускають gate."""
        return (
            action.action == "ENTRY"
            and action.direction == DIRECTION_DOWN
            and action.available_at == at
            and strict_m15 is not None
            and strict_m15.at == at - M15_SPAN
            and _category(strict_m15, DIRECTION_DOWN) == "ACTIVE_ALIGNED"
        )

    def finish(self) -> None:
        """Штатні інваріанти Engine з окремим лічильником відмов."""
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
            + len(self.rejected)
        )
        assert result.buy_signals + result.sell_signals == result.entry_signals
        assert self.exposed_active_bars <= self.post_signal_active_bars
        assert len({item.at for item in self.rejected}) == len(self.rejected)


def _strict_states(
    bars: list[Bar],
    states: list[WatchBar],
) -> list[WatchBar | None]:
    """Під час руху H1 читати тільки вже завершені M15."""
    points: list[WatchBar | None] = []
    cursor = 0
    latest: WatchBar | None = None
    for bar in bars:
        at = bar.timestamp
        while cursor < len(states) and states[cursor].at < at:
            latest = states[cursor]
            cursor += 1
        current = latest if latest is not None and latest.at == at - M15_SPAN else None
        assert current is None or current.at < at
        points.append(current)
    assert len(points) == len(bars)
    return points


def _synthetic_gate() -> None:
    """Відмова тільки SELL, тільки суміжний open і strict M15."""
    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")
    aligned = WatchBar(
        origin - M15_SPAN,
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        1.101,
    )
    boundary = WatchBar(
        origin,
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        1.102,
    )
    stale = WatchBar(
        origin - timedelta(minutes=30),
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        1.103,
    )
    opposite = WatchBar(
        origin - M15_SPAN,
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_UP,
        1.104,
    )
    action = PendingAction(
        action="ENTRY",
        available_at=origin,
        signal_at=origin - H1_SPAN,
        direction=DIRECTION_DOWN,
    )
    check = GateEngine.must_reject
    assert check(origin, action, aligned)
    assert not check(origin, action, boundary)
    assert not check(origin, action, stale)
    assert not check(origin, action, opposite)
    assert not check(origin + H1_SPAN, action, aligned)
    buy = PendingAction(
        "ENTRY",
        origin,
        origin - H1_SPAN,
        DIRECTION_UP,
    )
    close = PendingAction(
        "EXIT",
        origin,
        origin - H1_SPAN,
        DIRECTION_DOWN,
    )
    assert not check(origin, buy, aligned)
    assert not check(origin, close, aligned)
    assert not check(origin, action, None)
    print("SYNTHETIC_STRICT_M15_ENTRY_GATE=OK")
    print("SYNTHETIC_NO_BUY_EXIT_GAP_OR_SAME_TICK_GATE=OK")


def _synthetic_gate_execution() -> None:
    """Реально скасувати pending SELL без втручання у H1 exit."""
    from core.workspace_alligator import (  # noqa: E402
        ALLIGATOR_REGIME_PHASE_ACTIVE,
    )

    origin = datetime.fromisoformat("2025-02-03T10:00:00+00:00")
    action = PendingAction(
        "ENTRY",
        origin,
        origin - H1_SPAN,
        DIRECTION_DOWN,
    )
    aligned = WatchBar(
        origin - M15_SPAN,
        ALLIGATOR_REGIME_PHASE_ACTIVE,
        ALLIGATOR_REGIME_TREND_DOWN,
        1.101,
    )
    bar = Bar(origin, 1.101, 1.102, 1.100, 1.101)
    profile = _profile()
    observation = WorkspaceAlligatorObservation(
        timestamp=origin,
        median_price=bar.close,
        source_value=bar.close,
        jaw=None,
        teeth=None,
        lips=None,
        state="TEST_ONLY",
        regime=ALLIGATOR_REGIME_TREND_DOWN,
        regime_phase=ALLIGATOR_REGIME_PHASE_ACTIVE,
        center=None,
        opening=None,
        center_slope_per_bar=None,
        range_reference=None,
        normalized_slope=None,
        normalized_opening=None,
        bars_processed=4,
        warmed_up=True,
        profile_uid=profile.profile_uid,
        profile_revision=profile.profile_revision,
        timeframe="H1",
        available_at=origin + H1_SPAN,
    )
    # Штучно відтворити стан одразу після закритого H1 signal.
    raw = GateEngine(
        H1_SPAN,
        SELL_33,
        previous_phase=observation.regime_phase,
        pending=action,
        candidate_available=origin,
        gate_enabled=False,
    )
    gated = GateEngine(
        H1_SPAN,
        SELL_33,
        previous_phase=observation.regime_phase,
        pending=action,
        candidate_available=origin,
    )
    raw.result.entry_signals = gated.result.entry_signals = 1
    raw.result.sell_signals = gated.result.sell_signals = 1
    raw.on_bar(0, bar, observation, aligned)
    gated.on_bar(0, bar, observation, aligned)
    raw.finish()
    gated.finish()
    assert raw.result.entries == 1 and raw.result.open_at_end == 1
    assert gated.result.entries == gated.result.open_at_end == 0
    assert len(gated.rejected) == 1
    assert raw.result.next_open_available == 1
    assert gated.result.next_open_available == 1
    assert gated.pending is None
    print("SYNTHETIC_CAUSAL_REJECT_EXECUTION_AND_ACCOUNTING=OK")


def _run_gated(
    bars: list[Bar],
    states: list[WatchBar],
) -> tuple[GateEngine, GateEngine]:
    """Три незалежні інстанси на одному потоці завершених барів."""
    points = _strict_states(bars, states)
    raw = GateEngine(H1_SPAN, SELL_33, gate_enabled=False)
    gated = GateEngine(H1_SPAN, SELL_33)
    mirror = GateEngine(H1_SPAN, SELL_33)
    signal_filter = _filter("H1")
    for index, (bar, state) in enumerate(zip(bars, points)):
        at = bar.timestamp + H1_SPAN
        obs = signal_filter.on_market_event(
            _event(bar, "H1"),
            available_at=at,
        )
        raw.on_bar(index, bar, obs, state)
        gated.on_bar(index, bar, obs, state)
        mirror.on_bar(index, bar, obs, state)
    for engine in (raw, gated, mirror):
        engine.finish()
    assert raw.rejected == []
    assert gated == mirror
    print("GATED_REPLAY_MIRROR_DETERMINISTIC=OK")
    return raw, gated


def _report(
    label: str,
    raw: GateEngine,
    gated: GateEngine,
    states: list[WatchBar],
) -> None:
    """Звірити gate та результат після реальної зміни зайнятості."""
    baseline = raw.result.trades
    trial = gated.result.trades
    entries = _entries(baseline, states)
    rejected_posthoc = [item for item in entries if _reject(item)]
    expected = EXPECTED_REJECT[label]
    assert len(rejected_posthoc) == expected[0]
    baseline_by_at = {trade.entry_at: trade for trade in baseline}
    trial_by_at = {trade.entry_at: trade for trade in trial}
    assert len(baseline_by_at) == len(baseline)
    assert len(trial_by_at) == len(trial)
    common = set(baseline_by_at) & set(trial_by_at)
    raw_only = set(baseline_by_at) - set(trial_by_at)
    trial_only = set(trial_by_at) - set(baseline_by_at)
    for at in common:
        assert baseline_by_at[at] == trial_by_at[at]
    baseline_buy = {
        at: trade
        for at, trade in baseline_by_at.items()
        if trade.direction == DIRECTION_UP
    }
    trial_buy = {
        at: trade
        for at, trade in trial_by_at.items()
        if trade.direction == DIRECTION_UP
    }
    assert baseline_buy == trial_buy
    print(f"BUY_TRADE_PRESERVATION={label}:OK")
    for item in gated.rejected:
        assert item.direction == DIRECTION_DOWN
        assert item.m15_at == item.at - M15_SPAN
        assert item.signal_at + H1_SPAN == item.at
        assert item.at not in trial_by_at
    net_base = math.fsum([float(trade.pips) - NET_COST_PIPS for trade in baseline])
    net_trial = math.fsum([float(trade.pips) - NET_COST_PIPS for trade in trial])
    assert math.isclose(
        net_base,
        REFERENCE_NET[label],
        abs_tol=1e-6,
    )
    new_net = math.fsum([trial_by_at[at].pips - NET_COST_PIPS for at in trial_only])
    lost_net = math.fsum([baseline_by_at[at].pips - NET_COST_PIPS for at in raw_only])
    assert math.isclose(
        net_trial - net_base,
        new_net - lost_net,
        abs_tol=1e-6,
    )
    posthoc = net_base - _score(rejected_posthoc).net
    assert math.isclose(
        posthoc - net_base,
        -expected[3],
        abs_tol=1e-6,
    )
    print(
        f"REPLAY|PERIOD={label}|BASE_CLOSED={len(baseline)}|"
        f"GATE_CLOSED={len(trial)}|BASE_SIGNALS="
        f"{raw.result.entry_signals}|GATE_SIGNALS="
        f"{gated.result.entry_signals}|GATE_REJECTED="
        f"{len(gated.rejected)}|POSTHOC_REJECTED="
        f"{len(rejected_posthoc)}|GATE_OPEN_END="
        f"{gated.result.open_at_end}"
    )
    print(
        f"OCCUPANCY|PERIOD={label}|COMMON_CLOSED={len(common)}|"
        f"BASE_ONLY_CLOSED={len(raw_only)}|"
        f"GATE_ONLY_CLOSED={len(trial_only)}|"
        f"BASE_IGNORED_OCCUPIED={raw.result.ignored_while_occupied}|"
        f"GATE_IGNORED_OCCUPIED={gated.result.ignored_while_occupied}|"
        f"BASE_ENTRY_GAPS={raw.result.entry_skipped_gap}|"
        f"GATE_ENTRY_GAPS={gated.result.entry_skipped_gap}"
    )
    print(
        f"DELTA|PERIOD={label}|BASE_NET040={net_base:+.2f}|"
        f"POSTHOC_NET040={posthoc:+.2f}|"
        f"GATED_NET040={net_trial:+.2f}|"
        f"GATED_MINUS_BASE={net_trial - net_base:+.2f}|"
        f"GATED_MINUS_POSTHOC={net_trial - posthoc:+.2f}|"
        f"TRIAL_ONLY_NET040={new_net:+.2f}|"
        f"LOST_BASE_NET040={lost_net:+.2f}"
    )
    print(f"SCORE_BASE|PERIOD={label}|{_summary(raw, NET_COST_PIPS)}")
    print(f"SCORE_GATE|PERIOD={label}|{_summary(gated, NET_COST_PIPS)}")
    print(f"TRADE_ACCOUNTING_RECONCILIATION={label}:OK")


def main() -> None:
    """Запустити лише TEST_ONLY симулятор і контроль baseline."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-27|TEST_ONLY|H1_SELL_M15_CAUSAL_ENTRY_GATE_REPLAY")
    print(f"RULE={RULE}")
    print("H1=UNCHANGED_4_BARS_HYBRID|SELL_33=UNCHANGED")
    print("GATE_AT=H1_NEXT_OPEN|M15_STRICTLY_BEFORE_ENTRY=True")
    print("M15_SAME_TIMESTAMP_EXCLUDED=True|NO_FUTURE_GATE=True")
    print("NET040=HYPOTHETICAL|NOT_OUT_OF_SAMPLE=True")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    _synthetic_cost()
    _synthetic_gate()
    _synthetic_gate_execution()
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
        states = _observe_m15(aggregated[M15_MIN])
        raw, gated = _run_gated(aggregated[H1_MIN], states)
        reference = _run_tf(
            aggregated[H1_MIN],
            H1_MIN,
            _profile(),
        )[2]
        assert raw.result == reference.result
        count, opened, gross, net = EXPECTED_H1[label]
        assert len(raw.result.trades) == count
        assert raw.result.open_at_end == opened
        gross_calc = math.fsum([float(t.pips) for t in raw.result.trades])
        assert math.isclose(gross_calc, gross, abs_tol=1e-6)
        assert math.isclose(REFERENCE_NET[label], net, abs_tol=1e-6)
        print(f"H1_UNGATED_BASELINE_MATCH={label}:OK")
        _report(label, raw, gated, states)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_27_H1_SELL_M15_CAUSAL_ENTRY_GATE_REPLAY=OK")


if __name__ == "__main__":
    main()
