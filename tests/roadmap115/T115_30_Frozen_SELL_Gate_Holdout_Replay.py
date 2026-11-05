# -*- coding: utf-8 -*-
"""RoadMap115 / T115-30: frozen SELL-gate on a later time window.

TEST_ONLY. Holdout candidate: 26.08–21.10.2026 UTC (EURUSD cTrader M1).
The H1 hybrid and the H1 SELL / M15 ACTIVE_ALIGNED gate are imported
unchanged from T115-27. No optimization, no broker requests.

Only completed M15/H1 bars are used. Pre-holdout bars warm the indicator,
not the position simulator. The holdout starts flat, with no pending order.
An existing pre-holdout Alligator phase is carried across the boundary to
avoid inventing an ACTIVE transition at the start of the holdout.

Closed-only results exclude unfinished positions. All prices are OHLC-mid;
0.40 pip per completed trade is a hypothetical all-in round-trip cost.
This time-forward candidate is NOT proven to be independent true OOS data.
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    Bar,
    HEADER,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    ClosedTrade,
    DIRECTION_DOWN,
    DIRECTION_UP,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    Bucket,
    NET_COST_PIPS,
    SELL_33,
    _summary,
    _synthetic_check,
)
from T115_21_H1_M15_Trend_Watch_Audit import (  # noqa: E402
    H1_MIN,
    H1_SPAN,
    M15_MIN,
    _event,
    _filter,
    _observe_m15,
    _synthetic_watch,
)
from T115_25_H1_Entry_M15_State_Anatomy import (  # noqa: E402
    _synthetic_entry_boundary,
)
from T115_26_H1_SELL_M15_Aligned_Reject_Cost_Audit import (  # noqa: E402
    _synthetic_cost,
)
from T115_27_H1_SELL_M15_Causal_Entry_Gate_Replay import (  # noqa: E402
    RULE,
    GateEngine,
    _strict_states,
    _synthetic_gate,
    _synthetic_gate_execution,
)

ARCHIVE = (
    ROOT / "data/history/CTRADER/EURUSD/M1"
    / "2024-10-22_2026-10-21_CTRADER_EURUSD_M1.csv"
)
HOLDOUT_START = datetime.fromisoformat("2026-08-26T00:00:00+00:00")
HOLDOUT_END = datetime.fromisoformat("2026-10-22T00:00:00+00:00")
YEAR_START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
CANONICAL_CUTOFF = datetime.fromisoformat(
    "2026-08-25T15:07:00+00:00"
)
EXPECTED_M1_HOLDOUT = 58448
EXPECTED_M15_HOLDOUT = 3740
EXPECTED_H1_HOLDOUT = 877
EPS = 1e-7


@dataclass(frozen=True, slots=True)
class HoldoutData:
    """Повна 2026 історія для прогріву і готові бари holdout."""

    year_m1: int
    holdout_m1: int
    m15: list[Bar]
    h1: list[Bar]


def _load_holdout() -> HoldoutData:
    """Формувати H1/M15 тільки із суміжних M1 без forward-fill."""
    assert ARCHIVE.is_file()
    buckets = {
        M15_MIN: Bucket(M15_MIN),
        H1_MIN: Bucket(H1_MIN),
    }
    previous_at: datetime | None = None
    year_rows = holdout_rows = 0
    with ARCHIVE.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream)
        assert tuple(next(rows)) == HEADER
        for cells in rows:
            assert len(cells) == len(HEADER)
            at = datetime.fromisoformat(
                cells[0].replace("Z", "+00:00")
            ).astimezone(UTC)
            assert previous_at is None or at > previous_at
            previous_at = at
            if at < YEAR_START or at >= HOLDOUT_END:
                continue
            opening, high, low, closing = map(float, cells[1:5])
            values = (opening, high, low, closing)
            assert all(math.isfinite(v) and v > 0 for v in values)
            assert low <= min(opening, closing)
            assert max(opening, closing) <= high
            bar = Bar(at, opening, high, low, closing)
            year_rows += 1
            if at >= HOLDOUT_START:
                holdout_rows += 1
            for bucket in buckets.values():
                bucket.add(bar)
    for bucket in buckets.values():
        bucket.finish()
    completed_m15 = buckets[M15_MIN].completed
    completed_h1 = buckets[H1_MIN].completed
    hold_m15 = [
        bar for bar in completed_m15
        if HOLDOUT_START <= bar.timestamp < HOLDOUT_END
    ]
    hold_h1 = [
        bar for bar in completed_h1
        if HOLDOUT_START <= bar.timestamp < HOLDOUT_END
    ]
    assert holdout_rows == EXPECTED_M1_HOLDOUT
    assert len(hold_m15) == EXPECTED_M15_HOLDOUT
    assert len(hold_h1) == EXPECTED_H1_HOLDOUT
    assert len(completed_h1) > len(hold_h1)
    assert len(completed_m15) > len(hold_m15)
    assert all(
        bar.timestamp + H1_SPAN <= HOLDOUT_START
        for bar in completed_h1 if bar.timestamp < HOLDOUT_START
    )
    print(
        f"DATA|YEAR_2026_M1={year_rows}|HOLDOUT_M1={holdout_rows}|"
        f"HOLDOUT_M15={len(hold_m15)}|HOLDOUT_H1={len(hold_h1)}"
    )
    return HoldoutData(
        year_rows, holdout_rows, completed_m15, completed_h1,
    )


def _synthetic_boundary() -> None:
    """Контроль незмінності межі оцінки і допустимих годин."""
    assert CANONICAL_CUTOFF < HOLDOUT_START < HOLDOUT_END
    assert YEAR_START < CANONICAL_CUTOFF
    assert HOLDOUT_START.minute == HOLDOUT_END.minute == 0
    assert HOLDOUT_START.second == HOLDOUT_END.second == 0
    assert RULE == "SELL_AND_STRICT_PRE_ENTRY_M15_ACTIVE_ALIGNED"
    assert NET_COST_PIPS == 0.40
    assert SELL_33 == frozenset({DIRECTION_DOWN})
    print("SYNTHETIC_FROZEN_GATE_AND_HOLDOUT_BOUNDARY=OK")


def _run_holdout(data: HoldoutData) -> tuple[GateEngine, GateEngine]:
    """Спільний causal потік, незалежні baseline/gate/mirror."""
    m15_states = _observe_m15(data.m15)
    hold_bars = [
        bar for bar in data.h1
        if HOLDOUT_START <= bar.timestamp < HOLDOUT_END
    ]
    strict = _strict_states(hold_bars, m15_states)
    raw = GateEngine(H1_SPAN, SELL_33, gate_enabled=False)
    gate = GateEngine(H1_SPAN, SELL_33)
    mirror = GateEngine(H1_SPAN, SELL_33)
    h1_filter = _filter("H1")
    last_pre_phase: str | None = None
    previous_pre_at: datetime | None = None
    warmup_count = 0
    test_count = 0
    for bar in data.h1:
        available_at = bar.timestamp + H1_SPAN
        observation = h1_filter.on_market_event(
            _event(bar, "H1"), available_at=available_at,
        )
        assert observation.available_at == available_at
        if available_at <= HOLDOUT_START:
            last_pre_phase = observation.regime_phase
            previous_pre_at = bar.timestamp
            warmup_count += 1
            continue
        assert bar.timestamp >= HOLDOUT_START
        if test_count == 0:
            assert last_pre_phase is not None
            assert previous_pre_at is not None
            for engine in (raw, gate, mirror):
                engine.previous_phase = last_pre_phase
                engine.previous_bar_at = previous_pre_at
                assert engine.position is None and engine.pending is None
        state = strict[test_count]
        raw.on_bar(test_count, bar, observation, state)
        gate.on_bar(test_count, bar, observation, state)
        mirror.on_bar(test_count, bar, observation, state)
        test_count += 1
    for engine in (raw, gate, mirror):
        engine.finish()
    assert test_count == len(hold_bars) == EXPECTED_H1_HOLDOUT
    assert warmup_count > 100
    assert raw.rejected == []
    assert gate == mirror
    assert raw.result.entry_signals == gate.result.entry_signals
    assert all(item.at >= HOLDOUT_START for item in gate.rejected)
    print(
        f"REPLAY_BOUNDARY|WARMUP_H1={warmup_count}|"
        f"TEST_H1={test_count}|FLAT_AT_START=True|"
        f"PREVIOUS_PHASE_CARRIED=True|PENDING_CARRIED=False"
    )
    print("GATED_HOLDOUT_MIRROR_DETERMINISTIC=OK")
    return raw, gate


def _net(trade: ClosedTrade) -> float:
    """Умовний Net завершеної угоди."""
    return float(trade.pips) - NET_COST_PIPS


def _total(trades: list[ClosedTrade]) -> float:
    """Сума пунктів завершених угод без generator warning."""
    values: list[float] = [_net(trade) for trade in trades]
    return math.fsum(values)


def _side_report(
    side: str,
    raw: GateEngine,
    gate: GateEngine,
) -> None:
    """Показати окремо BUY і SELL, щоб не маскувати збитки."""
    base_trades = [
        trade for trade in raw.result.trades
        if trade.direction == side
    ]
    gate_trades = [
        trade for trade in gate.result.trades
        if trade.direction == side
    ]
    base_net = _total(base_trades)
    gate_net = _total(gate_trades)
    print(
        f"SIDE|SIDE={side}|BASE_CLOSED={len(base_trades)}|"
        f"GATE_CLOSED={len(gate_trades)}|BASE_NET040={base_net:+.2f}|"
        f"GATE_NET040={gate_net:+.2f}|DELTA={gate_net-base_net:+.2f}"
    )


def _tail_report(raw: GateEngine, gate: GateEngine) -> None:
    """Наскільки підсумок залежить від найбільших відхилень."""
    baseline = {item.entry_at: item for item in raw.result.trades}
    trial = {item.entry_at: item for item in gate.result.trades}
    assert len(baseline) == len(raw.result.trades)
    assert len(trial) == len(gate.result.trades)
    base_only = set(baseline) - set(trial)
    gate_only = set(trial) - set(baseline)
    for entry_at in sorted(set(baseline) & set(trial)):
        assert baseline[entry_at] == trial[entry_at]
    lost = [baseline[at] for at in sorted(base_only)]
    added = [trial[at] for at in sorted(gate_only)]
    assert all(trade.direction == DIRECTION_DOWN for trade in lost)
    assert all(trade.entry_at >= HOLDOUT_START for trade in lost + added)
    delta = _total(list(trial.values())) - _total(list(baseline.values()))
    assert math.isclose(
        delta, _total(added) - _total(lost), abs_tol=EPS,
    )
    ordered = sorted(lost, key=_net)
    for n in (1, 3, 5):
        selected = ordered[:n]
        contribution = -_total(selected)
        remaining = delta - contribution
        print(
            f"TAIL|DROP_WORST={n}|AVAILABLE={len(selected)}|"
            f"TOP_SAVING={contribution:+.2f}|"
            f"DELTA_REMAINDER={remaining:+.2f}"
        )
    print(
        f"OCCUPANCY|COMMON_CLOSED={len(set(baseline) & set(trial))}|"
        f"BASE_ONLY_CLOSED={len(base_only)}|"
        f"GATE_ONLY_CLOSED={len(gate_only)}|"
        f"BASE_IGNORED={raw.result.ignored_while_occupied}|"
        f"GATE_IGNORED={gate.result.ignored_while_occupied}|"
        f"BASE_OPEN_END={raw.result.open_at_end}|"
        f"GATE_OPEN_END={gate.result.open_at_end}"
    )
    print("HOLDOUT_TRADE_NET_RECONCILIATION=OK")


def _report(raw: GateEngine, gate: GateEngine) -> None:
    """Без вибіркового налаштування параметрів оцінити holdout."""
    baseline = raw.result.trades
    trial = gate.result.trades
    for trade in baseline + trial:
        assert HOLDOUT_START <= trade.entry_at
        assert trade.entry_at < trade.exit_at < HOLDOUT_END
    assert all(item.direction == DIRECTION_DOWN for item in gate.rejected)
    print(
        f"SIGNALS|BASE={raw.result.entry_signals}|"
        f"GATE={gate.result.entry_signals}|"
        f"REJECTED={len(gate.rejected)}|"
        f"BASE_ENTRY_GAPS={raw.result.entry_skipped_gap}|"
        f"GATE_ENTRY_GAPS={gate.result.entry_skipped_gap}"
    )
    print(f"SCORE_BASE|{_summary(raw, NET_COST_PIPS)}")
    print(f"SCORE_GATE|{_summary(gate, NET_COST_PIPS)}")
    base_net = _total(baseline)
    gate_net = _total(trial)
    print(
        f"DELTA_NET040={gate_net-base_net:+.2f}|"
        f"GATE_BETTER={gate_net > base_net}|"
        f"POSITIVE_GATE_NET={gate_net > 0}|"
        "SHORT_TIME_FORWARD_CANDIDATE=True"
    )
    for side in (DIRECTION_UP, DIRECTION_DOWN):
        _side_report(side, raw, gate)
    _tail_report(raw, gate)
    print(
        "INTERPRETATION=TIME_FORWARD_NOT_TRUE_OOS|"
        "NO_PARAMETER_SEARCH|NO_PRODUCTION_DECISION"
    )


def main() -> None:
    """TEST_ONLY: не редагувати production або MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/"
        "T115_27_H1_SELL_M15_Causal_Entry_Gate_Replay.py",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-30|TEST_ONLY|FROZEN_SELL_GATE_HOLDOUT_REPLAY")
    print(f"FROZEN_RULE={RULE}|H1=4_BARS|M15=STRICT_PRE_ENTRY")
    print(
        "HOLDOUT_START=2026-08-26T00:00:00Z|"
        "HOLDOUT_END_EXCLUSIVE=2026-10-22T00:00:00Z"
    )
    print("ENTRY_EXIT=UNCHANGED_T115_27|SELL_33=UNCHANGED")
    print("MID_ONLY=True|COST_040_HYPOTHETICAL=True")
    _synthetic_boundary()
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    _synthetic_cost()
    _synthetic_gate()
    _synthetic_gate_execution()
    data = _load_holdout()
    raw, gate = _run_holdout(data)
    _report(raw, gate)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_30_FROZEN_SELL_GATE_HOLDOUT_REPLAY=OK")


if __name__ == "__main__":
    main()
