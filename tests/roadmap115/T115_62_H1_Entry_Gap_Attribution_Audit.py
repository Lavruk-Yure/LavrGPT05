# -*- coding: utf-8 -*-
"""RoadMap115 / T115-62: H1 entry gap attribution.

TEST_ONLY / DATA_ONLY.

Спостерігати за незмінним Engine.on_bar через
тимчасовий Python profiler та встановити причини
18 пропущених входів.

Жодних повторних входів чи торгових правил
не створюється. Наступний час бару використовується
лише для ретроспективної діагностики розриву.

Production, Replay-логіка та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


EXPECTED_SKIPPED = 18
EXPECTED_CLOSED = 333
EXPECTED_NET = -680.30
EPS = 0.000001


def _sha(path: Path) -> str:
    """Повернути SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weekend_in_gap(
    expected: datetime,
    actual: datetime,
) -> bool:
    """Визначити, чи охоплює розрив вихідний день."""
    day = expected.date()
    last = actual.date()

    while day <= last:
        if day.weekday() >= 5:
            return True

        day += timedelta(days=1)

    return False


def main() -> None:
    """Зібрати фактичні часові пропуски H1 ENTRY."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

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

    # Зберігаємо посилання на Engine, щоб ID не повторювалися.
    observed_engines: dict[int, Any] = {}

    # ID Engine -> (очікуваний час, фактичний час, напрям).
    gaps: dict[int, list[tuple[datetime, datetime, str]]] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Зафіксувати pending ENTRY перед on_bar."""
        if event != "call" or frame.f_code is not on_bar_code:
            return

        observed_engine = frame.f_locals.get("self")
        bar = frame.f_locals.get("bar")

        if observed_engine is None or bar is None:
            return

        pending = observed_engine.pending

        if pending is None or pending.action != "ENTRY":
            return

        pending_at = pending.available_at
        bar_at = bar.timestamp

        if bar_at <= pending_at:
            return

        identity = id(observed_engine)
        observed_engines[identity] = observed_engine

        gaps.setdefault(identity, []).append((pending_at, bar_at, pending.direction))

    print("T115-62|TEST_ONLY|" "H1_ENTRY_GAP_ATTRIBUTION_AUDIT")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("ENGINE_CODE_MODIFIED=False")
    print("EX_POST_GAP_DIAGNOSTIC_ONLY=True")

    previous_profiler = sys.getprofile()

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4

    pooled: Counter[str] = Counter()
    all_net: list[float] = []

    for name, engine in engines:
        result = engine.result

        records = gaps.get(id(engine), [])

        expected_count, expected_net, expected_open = funnel.EXPECTED[name]

        net = math.fsum(trade.pips - funnel.NET_COST_PIPS for trade in result.trades)

        assert len(result.trades) == expected_count
        assert result.open_at_end == expected_open
        assert math.isclose(
            net,
            expected_net,
            abs_tol=EPS,
        )

        assert len(records) == result.entry_skipped_gap

        weekend = 0
        other = 0

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"CLOSED={len(result.trades)}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={result.open_at_end}"
        )

        for number, (expected, actual, side) in enumerate(
            records,
            start=1,
        ):
            delay = actual - expected

            assert delay > timedelta(0)

            crosses_weekend = _weekend_in_gap(
                expected,
                actual,
            )

            if crosses_weekend:
                weekend += 1
                kind = "INCLUDES_WEEKEND"
            else:
                other += 1
                kind = "OTHER_TIME_GAP"

            print(
                f"ENTRY_GAP|PERIOD={name}|"
                f"NUMBER={number}|"
                f"SIDE={side}|"
                f"EXPECTED={expected.isoformat()}|"
                f"NEXT_BAR={actual.isoformat()}|"
                f"DELAY_MIN={int(delay.total_seconds() // 60)}|"
                f"KIND={kind}"
            )

        assert weekend + other == len(records)

        print(
            f"ENTRY_GAP_SUMMARY|PERIOD={name}|"
            f"SKIPPED={len(records)}|"
            f"INCLUDES_WEEKEND={weekend}|"
            f"OTHER_TIME_GAP={other}"
        )

        pooled.update(
            {
                "skipped": len(records),
                "weekend": weekend,
                "other": other,
                "signals": result.entry_signals,
                "executed": result.entries,
                "occupied": result.ignored_while_occupied,
                "pending_end": result.entry_unfilled_at_end,
                "closed": len(result.trades),
                "open": result.open_at_end,
            }
        )

        all_net.append(net)

    assert pooled["skipped"] == EXPECTED_SKIPPED
    assert pooled["closed"] == EXPECTED_CLOSED
    assert pooled["open"] == 1
    assert pooled["executed"] == 334
    assert pooled["signals"] == 353
    assert pooled["occupied"] == 0
    assert pooled["pending_end"] == 1

    assert pooled["weekend"] + pooled["other"] == (pooled["skipped"])

    assert math.isclose(
        math.fsum(all_net),
        EXPECTED_NET,
        abs_tol=EPS,
    )

    print(
        f"POOLED_ENTRY_GAP_SUMMARY|"
        f"SKIPPED={pooled['skipped']}|"
        f"INCLUDES_WEEKEND={pooled['weekend']}|"
        f"OTHER_TIME_GAP={pooled['other']}"
    )

    print(
        f"POOLED_BASELINE|"
        f"CLOSED={pooled['closed']}|"
        f"OPEN_END={pooled['open']}|"
        f"NET040={math.fsum(all_net):+.2f}"
    )

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ENTRY_GAP_EVENTS_18_OF_18=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("NO_GAP_RECOVERY_SIMULATED=True")
    print("FUTURE_PNL_NOT_USED_FOR_ENTRY=True")
    print("PRODUCTION_EQUIVALENCE_NOT_ASSERTED=True")
    print("NO_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_62_H1_ENTRY_GAP_ATTRIBUTION_AUDIT=OK")


if __name__ == "__main__":
    main()
