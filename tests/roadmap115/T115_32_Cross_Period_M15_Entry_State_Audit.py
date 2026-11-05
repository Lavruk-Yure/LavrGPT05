# -*- coding: utf-8 -*-
"""RoadMap115 / T115-32: cross-period M15 entry-state anatomy.

TEST_ONLY. Незмінний H1 hybrid BUY ENDING / SELL 33% OR ENDING.
M15 є тільки станом строго перед входом, без gate та ордерів.
Чотири часові вікна; ніякого підбору порогів за результатом.
Майбутній PnL використовується тільки як outcome label.
OHLC mid, гіпотетичні витрати 0.40 pip round-trip.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Типи імпортуються для IDE, але не виконуються в Replay.
if TYPE_CHECKING:
    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade
    from T115_25_H1_Entry_M15_State_Anatomy import EntryState

# Динамічний імпорт після встановлення ROOT: жодних E402.
entry_mod = import_module("T115_01_Alligator_Entry_Only_Events")
CANONICAL_2026_END = entry_mod.CANONICAL_2026_END
PERIODS = entry_mod.PERIODS
_profile = getattr(entry_mod, "_profile")

exit_mod = import_module("T115_02_Alligator_Exit_Only_Trades")
DIRECTION_DOWN = exit_mod.DIRECTION_DOWN
DIRECTION_UP = exit_mod.DIRECTION_UP

plateau_mod = import_module("T115_15_Extended_Timeframe_Plateau_Audit")
NET_COST_PIPS = plateau_mod.NET_COST_PIPS
_aggregate_all = getattr(plateau_mod, "_aggregate_all")
_run_tf = getattr(plateau_mod, "_run_tf")
_synthetic_check = getattr(plateau_mod, "_synthetic_check")

watch_mod = import_module("T115_21_H1_M15_Trend_Watch_Audit")
H1_MIN = watch_mod.H1_MIN
M15_MIN = watch_mod.M15_MIN
_observe_m15 = getattr(watch_mod, "_observe_m15")
_synthetic_watch = getattr(watch_mod, "_synthetic_watch")
_trace_h1 = getattr(watch_mod, "_trace_h1")

state_mod = import_module("T115_25_H1_Entry_M15_State_Anatomy")
_entries = getattr(state_mod, "_entries")
_synthetic_entry_boundary = getattr(state_mod, "_synthetic_entry_boundary")

holdout_mod = import_module("T115_30_Frozen_SELL_Gate_Holdout_Replay")
HOLDOUT_END = holdout_mod.HOLDOUT_END
HOLDOUT_START = holdout_mod.HOLDOUT_START
_load_holdout = getattr(holdout_mod, "_load_holdout")
_run_holdout = getattr(holdout_mod, "_run_holdout")

backward_mod = import_module("T115_31_Frozen_SELL_Gate_Pre_2025_Backward_Replay")
TRADE_END = backward_mod.TRADE_END
TRADE_START = backward_mod.TRADE_START
_load_2024 = getattr(backward_mod, "_load")
_run_2024 = getattr(backward_mod, "_run")

EPS = 1e-6
SIDES = (DIRECTION_UP, DIRECTION_DOWN)
GROUPS = ("ACTIVE_ALIGNED", "ENDING_ALIGNED", "OTHER")
EXPECTED = {
    "2024_NOV_DEC": (26, -315.00, -304.60, 1),
    "2025": (167, 238.10, 304.90, 0),
    "2026_TO_2026_08_25": (114, -329.00, -283.40, 0),
    "2026_AUG_OCT": (26, -274.40, -264.00, 0),
}


@dataclass(frozen=True, slots=True)
class Window:
    """Незмінні закриті H1 угоди та causal M15-позначки."""

    name: str
    entries: list[EntryState]
    open_end: int


def _sha(path: Path) -> str:
    """Контроль байтів production-файлів і MD7."""
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            result.update(chunk)
    return result.hexdigest()


def _net(trade: ClosedTrade) -> float:
    """Умовний Net завершеної H1-угоди."""
    return float(trade.pips) - NET_COST_PIPS


def _total(trades: list[ClosedTrade]) -> float:
    values: list[float] = [_net(trade) for trade in trades]
    return math.fsum(values)


def _sum_gross(trades: list[ClosedTrade]) -> float:
    values: list[float] = [float(trade.pips) for trade in trades]
    return math.fsum(values)


def _group(entry: EntryState) -> str:
    """Три групи без підбору параметрів після outcome."""
    if entry.strict_class in GROUPS[:2]:
        return entry.strict_class
    return "OTHER"


def _synthetic_audit() -> None:
    """Контроль часу, бухгалтерії й фіксованих груп."""
    assert TRADE_START < TRADE_END < HOLDOUT_START < HOLDOUT_END
    assert NET_COST_PIPS == 0.40
    assert GROUPS == ("ACTIVE_ALIGNED", "ENDING_ALIGNED", "OTHER")
    assert CANONICAL_2026_END < HOLDOUT_START
    assert len(EXPECTED) == 4
    print("SYNTHETIC_FOUR_DISTINCT_WINDOWS=OK")
    print("SYNTHETIC_FROZEN_M15_GROUPS=OK")


def _make_window(
    name: str,
    trades: list[ClosedTrade],
    m15_states: list,
    open_end: int,
) -> Window:
    """Лише завершені угоди та стани до їхнього входу."""
    assert name in EXPECTED
    entries = _entries(trades, m15_states)
    assert len(entries) == len(trades)
    expected_count, expected_net, expected_gross, expected_open = EXPECTED[name]
    assert len(trades) == expected_count
    assert open_end == expected_open
    assert math.isclose(_total(trades), expected_net, abs_tol=EPS)
    assert math.isclose(_sum_gross(trades), expected_gross, abs_tol=EPS)
    assert all(
        entry.strict_state is None or entry.strict_state.at < entry.entry_at
        for entry in entries
    )
    assert all(
        entry.strict_state is None or entry.strict_state.at.minute % 15 == 0
        for entry in entries
    )
    assert entries == _entries(trades, m15_states)
    print(
        f"BASELINE_MATCH={name}:OK|CLOSED={len(trades)}|"
        f"NET040={expected_net:+.2f}|OPEN_END={open_end}"
    )
    return Window(name, entries, open_end)


def _load_windows() -> list[Window]:
    """Відтворити чотири незмінні H1 Replay без нових правил."""
    output: list[Window] = []

    old_data = _load_2024()
    old_base, old_gate = _run_2024(old_data)
    assert old_gate is not old_base
    old_m15 = _observe_m15(old_data.m15)
    output.append(
        _make_window(
            "2024_NOV_DEC",
            old_base.result.trades,
            old_m15,
            old_base.result.open_at_end,
        )
    )

    for label, filename, *_ in PERIODS:
        source = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        _, _, aggregated = _aggregate_all(
            source,
            int(label[:4]),
            cutoff,
        )
        engine, windows = _trace_h1(aggregated[H1_MIN])
        other = _run_tf(aggregated[H1_MIN], H1_MIN, _profile())[2]
        assert engine == other
        assert len(windows) == len(engine.result.trades)
        states = _observe_m15(aggregated[M15_MIN])
        output.append(
            _make_window(
                label,
                engine.result.trades,
                states,
                engine.result.open_at_end,
            )
        )

    late_data = _load_holdout()
    late_base, late_gate = _run_holdout(late_data)
    assert late_base is not late_gate
    late_m15 = _observe_m15(late_data.m15)
    output.append(
        _make_window(
            "2026_AUG_OCT",
            late_base.result.trades,
            late_m15,
            late_base.result.open_at_end,
        )
    )

    assert len(output) == 4
    assert [window.name for window in output] == list(EXPECTED)
    print("FOUR_WINDOW_REPLAY_BASELINES=OK")
    return output


def _cohort_stats(items: list[EntryState]) -> tuple[int, int, float, float]:
    """Число перемог/поразок, Net та PF без generator-ambiguity."""
    trades = [item.trade for item in items]
    net_values: list[float] = [_net(trade) for trade in trades]
    wins = sum(value > EPS for value in net_values)
    losses = sum(value < -EPS for value in net_values)
    positive = math.fsum([max(value, 0.0) for value in net_values])
    negative = -math.fsum([min(value, 0.0) for value in net_values])
    pf = positive / negative if negative > EPS else float("inf")
    return wins, losses, _total(trades), pf


def _report(windows: list[Window]) -> None:
    """Міжперіодна анатомія без нового gate або optimization."""
    comparison: dict[tuple[str, str], list[tuple[str, int, float]]] = defaultdict(list)
    for window in windows:
        all_trades = [entry.trade for entry in window.entries]
        assert len({item.entry_at for item in all_trades}) == len(all_trades)
        for side in SIDES:
            side_entries = [
                entry for entry in window.entries if entry.trade.direction == side
            ]
            net_all = _total([entry.trade for entry in side_entries])
            print(
                f"SIDE|PERIOD={window.name}|SIDE={side}|"
                f"CLOSED={len(side_entries)}|NET040={net_all:+.2f}"
            )
            partitions: dict[str, list[EntryState]] = {group: [] for group in GROUPS}
            for entry in side_entries:
                partitions[_group(entry)].append(entry)
            assert sum(len(part) for part in partitions.values()) == (len(side_entries))
            groups_total = math.fsum(
                [
                    _total([entry.trade for entry in part])
                    for part in partitions.values()
                ]
            )
            assert math.isclose(groups_total, net_all, abs_tol=EPS)
            for group in GROUPS:
                part = partitions[group]
                wins, losses, net, pf = _cohort_stats(part)
                ending = sum(entry.trade.exit_reason == "ENDING" for entry in part)
                tail = sorted([_net(entry.trade) for entry in part])[:3]
                tail_sum = math.fsum(tail)
                remaining = net - tail_sum
                print(
                    f"COHORT|PERIOD={window.name}|SIDE={side}|"
                    f"M15={group}|CLOSED={len(part)}|WINS={wins}|"
                    f"LOSSES={losses}|NET040={net:+.2f}|PF={pf:.3f}|"
                    f"ENDING={ending}|TOP3_LOSS={tail_sum:+.2f}|"
                    f"NET_EXCL_WORST3={remaining:+.2f}"
                )
                comparison[side, group].append((window.name, len(part), net))
            print(f"SIDE_COHORT_RECONCILIATION={window.name}:{side}:OK")
        print(f"PERIOD_COHORT_RECONCILIATION={window.name}:OK")

    for side in SIDES:
        for group in GROUPS:
            values = comparison[side, group]
            assert len(values) == 4
            positives = sum(net > EPS for _, _, net in values)
            negatives = sum(net < -EPS for _, _, net in values)
            print(
                f"CROSS_PERIOD|SIDE={side}|M15={group}|"
                f"POSITIVE_WINDOWS={positives}|NEGATIVE_WINDOWS={negatives}|"
                f"TOTAL_CLOSED={sum(count for _, count, _ in values)}|"
                f"NO_CAUSAL_GATE_CONCLUSION=True"
            )
    print("CROSS_PERIOD_PARTITION_RECONCILIATION=OK")
    print("HYPOTHESIS_REJECTED_FOR_PRODUCTION=True")


def main() -> None:
    """Незалежна перевірка чотирьох періодів без зміни коду."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_27_H1_SELL_M15_Causal_Entry_Gate_Replay.py",
    )
    assert all(path.is_file() for path in guarded)
    before = [_sha(path) for path in guarded]
    print("T115-32|TEST_ONLY|CROSS_PERIOD_M15_ENTRY_STATE_AUDIT")
    print("H1=UNCHANGED_4_BARS_HYBRID|M15=STRICT_PASSIVE_ONLY")
    print("WINDOWS=2024_PRE,2025,2026_PRE_CUTOFF,2026_POST_CUTOFF")
    print("GATE_DISABLED=True|COST_040_HYPOTHETICAL=True")
    _synthetic_audit()
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    windows = _load_windows()
    _report(windows)
    assert before == [_sha(path) for path in guarded]
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_32_CROSS_PERIOD_M15_ENTRY_STATE_AUDIT=OK")


if __name__ == "__main__":
    main()
