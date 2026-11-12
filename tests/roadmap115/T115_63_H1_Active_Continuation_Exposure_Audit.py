# -*- coding: utf-8 -*-
"""RoadMap115 / T115-63: H1 ACTIVE continuation exposure.

TEST_ONLY / DATA_ONLY.

Використати незмінні лічильники дослідницького Engine:
- active_bars;
- post_signal_active_bars;
- exposed_active_bars.

Виміряти продовження ACTIVE без відкритої позиції.
Такі бари не вважаються доведеними торговими
можливостями. Майбутній PnL для них не оцінюється.

Production, Replay-логіка та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Звірити базові результати та лічильники ACTIVE."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_61_H1_Entry_Signal_Funnel_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-63|TEST_ONLY|" "H1_ACTIVE_CONTINUATION_EXPOSURE_AUDIT")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("NO_NEW_ENTRY_SIGNAL=True")
    print("FUTURE_OUTCOME_NOT_EVALUATED=True")

    engines = load_engines()

    assert len(engines) == 4

    totals = {
        "active": 0,
        "signals": 0,
        "continuation": 0,
        "exposed": 0,
        "flat": 0,
        "closed": 0,
        "open": 0,
    }

    net_values: list[float] = []

    for name, engine in engines:
        result = engine.result

        expected_count, expected_net, expected_open = funnel.EXPECTED[name]

        net = math.fsum(trade.pips - funnel.NET_COST_PIPS for trade in result.trades)

        assert len(result.trades) == expected_count
        assert result.open_at_end == expected_open

        assert math.isclose(
            net,
            expected_net,
            abs_tol=funnel.EPS,
        )

        active = engine.active_bars
        signals = result.entry_signals
        continuation = engine.post_signal_active_bars
        exposed = engine.exposed_active_bars

        assert active == signals + continuation
        assert 0 <= exposed <= continuation

        flat = continuation - exposed

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"CLOSED={len(result.trades)}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={result.open_at_end}"
        )

        print(
            f"H1_ACTIVE_EXPOSURE|PERIOD={name}|"
            f"ACTIVE_BARS={active}|"
            f"ACTIVE_START_SIGNALS={signals}|"
            f"CONTINUATION_BARS={continuation}|"
            f"CONTINUATION_WITH_POSITION={exposed}|"
            f"CONTINUATION_FLAT={flat}"
        )

        for key, value in (
            ("active", active),
            ("signals", signals),
            ("continuation", continuation),
            ("exposed", exposed),
            ("flat", flat),
            ("closed", len(result.trades)),
            ("open", result.open_at_end),
        ):
            totals[key] += value

        net_values.append(net)

    assert totals["closed"] == 333
    assert totals["open"] == 1
    assert totals["signals"] == 353

    assert totals["active"] == totals["signals"] + totals["continuation"]

    assert totals["continuation"] == totals["exposed"] + totals["flat"]

    pooled_net = math.fsum(net_values)

    assert math.isclose(
        pooled_net,
        -680.30,
        abs_tol=funnel.EPS,
    )

    print(
        "POOLED_H1_ACTIVE_EXPOSURE|"
        f"ACTIVE_BARS={totals['active']}|"
        f"ACTIVE_START_SIGNALS={totals['signals']}|"
        f"CONTINUATION_BARS={totals['continuation']}|"
        f"CONTINUATION_WITH_POSITION={totals['exposed']}|"
        f"CONTINUATION_FLAT={totals['flat']}"
    )

    print(
        f"POOLED_BASELINE|"
        f"CLOSED={totals['closed']}|"
        f"OPEN_END={totals['open']}|"
        f"NET040={pooled_net:+.2f}"
    )

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ACTIVE_BAR_ACCOUNTING=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("FLAT_CONTINUATION_IS_NOT_PROVEN_ENTRY=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("NO_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_63_H1_ACTIVE_" "CONTINUATION_EXPOSURE_AUDIT=OK")


if __name__ == "__main__":
    main()
