# -*- coding: utf-8 -*-
"""RoadMap115 / T115-61: H1 entry signal funnel.

TEST_ONLY / DATA_ONLY.

Відтворити незмінний дослідницький H1 Engine
для чотирьох контрольних періодів.

Виміряти:
- кількість сигналів ENTRY;
- виконані входи;
- відхилення через зайнятість;
- пропуски через часові розриви;
- невиконані сигнали наприкінці періоду.

Не змінює Engine, production, Replay чи MD7.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


EXPECTED = {
    "2024_NOV_DEC": (26, -315.00, 1),
    "2025": (167, 238.10, 0),
    "2026_TO_2026_08_25": (114, -329.00, 0),
    "2026_AUG_OCT": (26, -274.40, 0),
}

NET_COST_PIPS = 0.40
EPS = 0.000001


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _engines() -> list[tuple[str, Any]]:
    """Відтворити H1 Engine за джерелами T115-32."""
    audit = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

    loader = getattr(audit, "_load_windows")
    scope = loader.__globals__

    output: list[tuple[str, Any]] = []

    old_data = scope["_load_2024"]()
    old_base, _ = scope["_run_2024"](old_data)

    output.append(("2024_NOV_DEC", old_base))

    for label, filename, *_ in scope["PERIODS"]:
        source = ROOT / "data/history/CTRADER/EURUSD/M1" / filename

        cutoff = scope["CANONICAL_2026_END"] if label.startswith("2026") else None

        _, _, aggregated = scope["_aggregate_all"](
            source,
            int(label[:4]),
            cutoff,
        )

        engine, _ = scope["_trace_h1"](aggregated[scope["H1_MIN"]])

        output.append((label, engine))

    late_data = scope["_load_holdout"]()
    late_base, _ = scope["_run_holdout"](late_data)

    output.append(("2026_AUG_OCT", late_base))

    assert [name for name, _ in output] == list(EXPECTED)

    return output


def _report(
    name: str,
    engine: Any,
    totals: Counter[str],
) -> float:
    """Звірити baseline та фактичну воронку входів."""
    result = engine.result

    expected_count, expected_net, expected_open = EXPECTED[name]

    net = math.fsum(trade.pips - NET_COST_PIPS for trade in result.trades)

    assert len(result.trades) == expected_count
    assert result.open_at_end == expected_open
    assert math.isclose(
        net,
        expected_net,
        abs_tol=EPS,
    )

    signals = result.entry_signals
    executed = result.entries
    occupied = result.ignored_while_occupied
    gaps = result.entry_skipped_gap
    end_pending = result.entry_unfilled_at_end

    assert signals == (executed + occupied + gaps + end_pending)

    assert result.buy_signals + result.sell_signals == signals

    assert executed == len(result.trades) + result.open_at_end

    print(
        f"BASELINE_MATCH={name}:OK|"
        f"CLOSED={len(result.trades)}|"
        f"NET040={net:+.2f}|"
        f"OPEN_END={result.open_at_end}"
    )

    print(
        f"H1_ENTRY_FUNNEL|PERIOD={name}|"
        f"SIGNALS={signals}|"
        f"EXECUTED={executed}|"
        f"IGNORED_OCCUPIED={occupied}|"
        f"SKIPPED_GAP={gaps}|"
        f"UNFILLED_END={end_pending}"
    )

    print(
        f"H1_ENTRY_SIGNAL_SIDE|PERIOD={name}|"
        f"BUY={result.buy_signals}|"
        f"SELL={result.sell_signals}"
    )

    assert signals >= executed

    totals.update(
        {
            "signals": signals,
            "executed": executed,
            "occupied": occupied,
            "gaps": gaps,
            "end_pending": end_pending,
            "buy_signals": result.buy_signals,
            "sell_signals": result.sell_signals,
            "closed": len(result.trades),
            "open": result.open_at_end,
        }
    )

    print(f"H1_ENTRY_ACCOUNTING={name}:OK")

    return net


def main() -> None:
    """Виміряти втрати сигналів без зміни правил."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_60_H1_Engine_Entry_Decision_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-61|TEST_ONLY|" "H1_ENTRY_SIGNAL_FUNNEL_AUDIT")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("PRODUCTION_EQUIVALENCE_NOT_ASSUMED=True")
    print("NO_ENTRY_RULE_CHANGE=True")

    engines = _engines()

    assert len(engines) == 4

    totals: Counter[str] = Counter()
    nets: list[float] = []

    for name, engine in engines:
        nets.append(_report(name, engine, totals))

    assert totals["closed"] == 333
    assert totals["open"] == 1
    assert totals["executed"] == 334

    assert totals["signals"] == (
        totals["executed"] + totals["occupied"] + totals["gaps"] + totals["end_pending"]
    )

    net_total = math.fsum(nets)

    assert math.isclose(
        net_total,
        -680.30,
        abs_tol=EPS,
    )

    print(
        f"POOLED_H1_ENTRY_FUNNEL|"
        f"SIGNALS={totals['signals']}|"
        f"EXECUTED={totals['executed']}|"
        f"IGNORED_OCCUPIED={totals['occupied']}|"
        f"SKIPPED_GAP={totals['gaps']}|"
        f"UNFILLED_END={totals['end_pending']}|"
        f"BUY_SIGNALS={totals['buy_signals']}|"
        f"SELL_SIGNALS={totals['sell_signals']}"
    )

    print(
        f"POOLED_BASELINE|"
        f"CLOSED={totals['closed']}|"
        f"OPEN_END={totals['open']}|"
        f"NET040={net_total:+.2f}"
    )

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("H1_ENTRY_SIGNAL_ACCOUNTING=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("IGNORED_SIGNALS_ARE_NOT_PROVEN_MISSED_PROFITS=True")
    print("NO_NEW_ENTRY_GATE=True")
    print("NO_REPLAY_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_61_H1_ENTRY_SIGNAL_FUNNEL_AUDIT=OK")


if __name__ == "__main__":
    main()
