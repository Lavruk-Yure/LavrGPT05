# -*- coding: utf-8 -*-
"""RoadMap115 / T115-31: frozen SELL-gate on pre-2025 history.

TEST_ONLY. Backward-time validation: November–December 2024 UTC.
October 22–31 is used solely to warm H1 and M15 Alligator.
The H1 four-bar hybrid, SELL 33% and the T115-27 gate are frozen.
Only completed, contiguous M1-derived TF bars are admitted.
Trade simulation starts flat and without pending orders on 01.11.2024.
No look-ahead, real fills, parameter search, or production changes.
This retrospective window is NOT an independent forward OOS test.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
from collections import defaultdict
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
SOURCE_START = datetime.fromisoformat("2024-10-22T00:00:00+00:00")
TRADE_START = datetime.fromisoformat("2024-11-01T00:00:00+00:00")
TRADE_END = datetime.fromisoformat("2025-01-01T00:00:00+00:00")
EXPECTED_SOURCE_M1 = 71516
EXPECTED_TRADE_M1 = 60048
EXPECTED_M15 = 3860
EXPECTED_H1 = 896
EPS = 1e-6


@dataclass(frozen=True, slots=True)
class PreperiodData:
    """Завершені H1 і M15 разом із попередньою історією."""

    source_m1: int
    trading_m1: int
    m15: list[Bar]
    h1: list[Bar]


def _fingerprint(path: Path) -> str:
    """Контроль незмінності файлів через SHA256."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def _synthetic_period() -> None:
    """Контроль неперетину періодів та параметрів gate."""
    assert SOURCE_START < TRADE_START < TRADE_END
    assert TRADE_END <= datetime.fromisoformat(
        "2025-01-01T00:00:00+00:00"
    )
    assert RULE == "SELL_AND_STRICT_PRE_ENTRY_M15_ACTIVE_ALIGNED"
    assert NET_COST_PIPS == 0.40
    assert SELL_33 == frozenset({DIRECTION_DOWN})
    assert H1_SPAN.total_seconds() == 3600
    print("SYNTHETIC_PRE_2025_BOUNDARY_AND_FROZEN_GATE=OK")


def _load() -> PreperiodData:
    """Агрегувати 2024 M1 без проглядання 2025 року."""
    assert ARCHIVE.is_file()
    buckets = {
        M15_MIN: Bucket(M15_MIN),
        H1_MIN: Bucket(H1_MIN),
    }
    previous_at: datetime | None = None
    source_m1 = trading_m1 = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    with ARCHIVE.open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(f)
        assert tuple(next(rows)) == HEADER
        for cells in rows:
            assert len(cells) == len(HEADER)
            at = datetime.fromisoformat(
                cells[0].replace("Z", "+00:00")
            ).astimezone(UTC)
            if at >= TRADE_END:
                break
            assert at.second == at.microsecond == 0
            assert previous_at is None or previous_at < at
            previous_at = at
            if first_at is None:
                first_at = at
            last_at = at
            opening, high, low, closing = map(float, cells[1:5])
            values = (opening, high, low, closing)
            assert all(math.isfinite(v) and v > 0 for v in values)
            assert low <= min(opening, closing)
            assert max(opening, closing) <= high
            source_m1 += 1
            if at >= TRADE_START:
                trading_m1 += 1
            bar = Bar(at, opening, high, low, closing)
            for bucket in buckets.values():
                bucket.add(bar)
    for bucket in buckets.values():
        bucket.finish()
    m15 = buckets[M15_MIN].completed
    h1 = buckets[H1_MIN].completed
    eligible_m15 = [
        bar for bar in m15 if TRADE_START <= bar.timestamp < TRADE_END
    ]
    eligible_h1 = [
        bar for bar in h1 if TRADE_START <= bar.timestamp < TRADE_END
    ]
    warmup_h1 = [bar for bar in h1 if bar.timestamp < TRADE_START]
    assert first_at == SOURCE_START
    assert last_at is not None and last_at < TRADE_END
    assert source_m1 == EXPECTED_SOURCE_M1
    assert trading_m1 == EXPECTED_TRADE_M1
    assert len(eligible_m15) == EXPECTED_M15
    assert len(eligible_h1) == EXPECTED_H1
    assert len(warmup_h1) > 100
    assert all(
        bar.timestamp + H1_SPAN <= TRADE_START for bar in warmup_h1
    )
    assert all(bar.timestamp < TRADE_END for bar in h1)
    assert all(bar.timestamp < TRADE_END for bar in m15)
    print(
        f"DATA|SOURCE_M1={source_m1}|TRADING_M1={trading_m1}|"
        f"TRADING_M15={len(eligible_m15)}|"
        f"TRADING_H1={len(eligible_h1)}|"
        f"WARMUP_H1={len(warmup_h1)}"
    )
    return PreperiodData(source_m1, trading_m1, m15, h1)


def _run(data: PreperiodData) -> tuple[GateEngine, GateEngine]:
    """Три engine на однаковому causal потоці H1/M15."""
    m15_states = _observe_m15(data.m15)
    trade_bars = [
        bar for bar in data.h1
        if TRADE_START <= bar.timestamp < TRADE_END
    ]
    strict = _strict_states(trade_bars, m15_states)
    baseline = GateEngine(H1_SPAN, SELL_33, gate_enabled=False)
    gated = GateEngine(H1_SPAN, SELL_33)
    mirror = GateEngine(H1_SPAN, SELL_33)
    h1_filter = _filter("H1")
    previous_phase: str | None = None
    previous_bar_at: datetime | None = None
    warmup_count = test_count = 0
    for bar in data.h1:
        available_at = bar.timestamp + H1_SPAN
        observation = h1_filter.on_market_event(
            _event(bar, "H1"), available_at=available_at,
        )
        assert observation.available_at == available_at
        if available_at <= TRADE_START:
            previous_phase = observation.regime_phase
            previous_bar_at = bar.timestamp
            warmup_count += 1
            continue
        assert TRADE_START <= bar.timestamp < TRADE_END
        if test_count == 0:
            assert previous_phase is not None
            assert previous_bar_at is not None
            for engine in (baseline, gated, mirror):
                engine.previous_phase = previous_phase
                engine.previous_bar_at = previous_bar_at
                assert engine.position is None and engine.pending is None
        state = strict[test_count]
        baseline.on_bar(test_count, bar, observation, state)
        gated.on_bar(test_count, bar, observation, state)
        mirror.on_bar(test_count, bar, observation, state)
        test_count += 1
    for engine in (baseline, gated, mirror):
        engine.finish()
    assert test_count == EXPECTED_H1
    assert warmup_count > 100
    assert gated == mirror
    assert baseline.rejected == []
    assert all(
        TRADE_START <= item.at < TRADE_END for item in gated.rejected
    )
    print(
        f"REPLAY_BOUNDARY|WARMUP_H1={warmup_count}|"
        f"TRADING_H1={test_count}|FLAT_AT_START=True|"
        "PREVIOUS_PHASE_CARRIED=True|PENDING_CARRIED=False"
    )
    print("GATED_BACKWARD_REPLAY_MIRROR_DETERMINISTIC=OK")
    return baseline, gated


def _net(trade: ClosedTrade) -> float:
    """Умовний Net пунктів однієї завершеної угоди."""
    return float(trade.pips) - NET_COST_PIPS


def _total(trades: list[ClosedTrade]) -> float:
    """Підсумувати тільки завершені угоди, без generator warning."""
    values: list[float] = [_net(trade) for trade in trades]
    return math.fsum(values)


def _report(baseline: GateEngine, gated: GateEngine) -> None:
    """Оцінити PnL, місяці, напрями, статус і концентрацію."""
    base = baseline.result.trades
    trial = gated.result.trades
    for trade in base + trial:
        assert TRADE_START <= trade.entry_at < trade.exit_at < TRADE_END
    before = {trade.entry_at: trade for trade in base}
    after = {trade.entry_at: trade for trade in trial}
    assert len(before) == len(base)
    assert len(after) == len(trial)
    common = set(before) & set(after)
    removed = set(before) - set(after)
    added = set(after) - set(before)
    assert all(before[at] == after[at] for at in common)
    assert all(before[at].direction == DIRECTION_DOWN for at in removed)
    base_buy = [t for t in base if t.direction == DIRECTION_UP]
    trial_buy = [t for t in trial if t.direction == DIRECTION_UP]
    assert base_buy == trial_buy
    net_base = _total(base)
    net_trial = _total(trial)
    net_lost = _total([before[at] for at in sorted(removed)])
    net_added = _total([after[at] for at in sorted(added)])
    assert math.isclose(
        net_trial - net_base, net_added - net_lost, abs_tol=EPS,
    )
    print(
        f"SIGNALS|BASE={baseline.result.entry_signals}|"
        f"GATE={gated.result.entry_signals}|"
        f"REJECTED={len(gated.rejected)}|"
        f"BASE_ENTRY_GAPS={baseline.result.entry_skipped_gap}|"
        f"GATE_ENTRY_GAPS={gated.result.entry_skipped_gap}"
    )
    print(f"SCORE_BASE|{_summary(baseline, NET_COST_PIPS)}")
    print(f"SCORE_GATE|{_summary(gated, NET_COST_PIPS)}")
    print(
        f"DELTA|BASE_NET040={net_base:+.2f}|"
        f"GATE_NET040={net_trial:+.2f}|"
        f"GAIN={net_trial - net_base:+.2f}|"
        f"GATE_POSITIVE={net_trial > 0}"
    )
    for direction in (DIRECTION_UP, DIRECTION_DOWN):
        b = [trade for trade in base if trade.direction == direction]
        g = [trade for trade in trial if trade.direction == direction]
        print(
            f"SIDE|SIDE={direction}|BASE_CLOSED={len(b)}|"
            f"GATE_CLOSED={len(g)}|BASE_NET040={_total(b):+.2f}|"
            f"GATE_NET040={_total(g):+.2f}|"
            f"DELTA={_total(g) - _total(b):+.2f}"
        )
    base_months: dict[str, list[ClosedTrade]] = defaultdict(list)
    gate_months: dict[str, list[ClosedTrade]] = defaultdict(list)
    for trade in base:
        base_months[trade.entry_at.strftime("%Y-%m")].append(trade)
    for trade in trial:
        gate_months[trade.entry_at.strftime("%Y-%m")].append(trade)
    months = sorted(set(base_months) | set(gate_months))
    assert months and set(months) <= {"2024-11", "2024-12"}
    for month in months:
        old, new = base_months[month], gate_months[month]
        print(
            f"MONTH|ID={month}|BASE_CLOSED={len(old)}|"
            f"GATE_CLOSED={len(new)}|BASE_NET040={_total(old):+.2f}|"
            f"GATE_NET040={_total(new):+.2f}|"
            f"DELTA={_total(new) - _total(old):+.2f}"
        )
    assert math.isclose(
        math.fsum([_total(x) for x in base_months.values()]),
        net_base, abs_tol=EPS,
    )
    assert math.isclose(
        math.fsum([_total(x) for x in gate_months.values()]),
        net_trial, abs_tol=EPS,
    )
    dropped = sorted([before[at] for at in removed], key=_net)
    for count in (1, 3):
        selected = dropped[:count]
        biggest_saving = -_total(selected)
        print(
            f"TAIL|DROP_WORST={count}|AVAILABLE={len(selected)}|"
            f"TOP_SAVING={biggest_saving:+.2f}|"
            f"DELTA_REMAINDER={net_trial-net_base-biggest_saving:+.2f}"
        )
    print(
        f"OCCUPANCY|COMMON_CLOSED={len(common)}|"
        f"BASE_ONLY={len(removed)}|GATE_ONLY={len(added)}|"
        f"BASE_IGNORED={baseline.result.ignored_while_occupied}|"
        f"GATE_IGNORED={gated.result.ignored_while_occupied}|"
        f"BASE_OPEN_END={baseline.result.open_at_end}|"
        f"GATE_OPEN_END={gated.result.open_at_end}"
    )
    print("PRE_2025_TRADE_NET_RECONCILIATION=OK")


def main() -> None:
    """Перевірити заморожене правило без production-редагування."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/"
        "T115_27_H1_SELL_M15_Causal_Entry_Gate_Replay.py",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-31|TEST_ONLY|FROZEN_SELL_GATE_PRE_2025_BACKWARD_REPLAY")
    print(f"FROZEN_RULE={RULE}|H1=4_BARS|SELL_33=UNCHANGED")
    print("WARMUP_FROM=2024-10-22|TRADE_START=2024-11-01T00:00:00Z")
    print("TRADE_END_EXCLUSIVE=2025-01-01T00:00:00Z")
    print("RETROSPECTIVE_PREPERIOD=True|TRUE_OOS=False")
    print("MID_ONLY=True|COST_040_HYPOTHETICAL=True")
    _synthetic_period()
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    _synthetic_cost()
    _synthetic_gate()
    _synthetic_gate_execution()
    data = _load()
    baseline, gated = _run(data)
    _report(baseline, gated)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_31_FROZEN_SELL_GATE_PRE_2025_BACKWARD_REPLAY=OK")


if __name__ == "__main__":
    main()
