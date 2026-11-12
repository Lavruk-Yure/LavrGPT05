# -*- coding: utf-8 -*-
"""RoadMap115 / T115-64: ACTIVE flat continuation causes.

TEST_ONLY / DATA_ONLY.

Спостерігати за незмінним Engine.on_bar і встановити
причини відсутності позиції всередині H1 ACTIVE.

Без нових ENTRY, EXIT, Replay-змін та використання
майбутнього PnL. MD7 і production не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


CATEGORIES = (
    "WITH_POSITION",
    "FLAT_EXIT_FILL",
    "FLAT_AFTER_EXIT",
    "FLAT_ENTRY_GAP",
    "FLAT_AFTER_GAP",
    "FLAT_UNATTRIBUTED",
)

FLAT_CATEGORIES = CATEGORIES[1:]


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Визначити причини порожніх ACTIVE-продовжень."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

    active_phase = getattr(
        engine_module,
        "ALLIGATOR_REGIME_PHASE_ACTIVE",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_61_H1_Entry_Signal_Funnel_Audit.py",
        TEST_DIR / "T115_63_H1_Active_Continuation_Exposure_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    # Утримуємо посилання, щоб ID об'єктів не повторювалися.
    observed_engines: dict[int, Any] = {}

    # Стан на момент входу в Engine.on_bar.
    inflight: dict[
        FrameType,
        tuple[int, bool, bool, bool, str],
    ] = {}

    # Попередня встановлена причина в межах ACTIVE.
    last_cause: dict[int, str] = {}

    # Лічильники для кожного фактичного екземпляра Engine.
    counts: dict[int, Counter[str]] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Спостерігати за станом до та після on_bar."""
        if frame.f_code is not on_bar_code:
            return

        if event == "call":
            observed_engine = frame.f_locals.get("self")
            observation = frame.f_locals.get("observation")

            if observed_engine is None or observation is None:
                return

            identity = id(observed_engine)
            observed_engines[identity] = observed_engine

            active = observation.regime_phase == active_phase
            is_continuation = active and observed_engine.previous_phase == active_phase

            pending = observed_engine.pending
            pending_action = pending.action if pending is not None else "NONE"

            inflight[frame] = (
                identity,
                active,
                is_continuation,
                observed_engine.position is not None,
                pending_action,
            )
            return

        if event != "return":
            return

        state = inflight.pop(frame, None)

        if state is None:
            return

        identity, active, was_continuation, was_open, pending_action = state
        observed_engine = observed_engines[identity]

        if not active or not was_continuation:
            last_cause[identity] = "NONE"
            return

        category_counts = counts.setdefault(
            identity,
            Counter(),
        )

        if observed_engine.position is not None:
            category = "WITH_POSITION"
            last_cause[identity] = "NONE"

        elif pending_action == "EXIT" and was_open:
            category = "FLAT_EXIT_FILL"
            last_cause[identity] = "EXIT"

        elif pending_action == "ENTRY" and not was_open:
            category = "FLAT_ENTRY_GAP"
            last_cause[identity] = "GAP"

        elif not was_open and pending_action == "NONE":
            previous_cause = last_cause.get(identity, "NONE")

            if previous_cause == "EXIT":
                category = "FLAT_AFTER_EXIT"
            elif previous_cause == "GAP":
                category = "FLAT_AFTER_GAP"
            else:
                category = "FLAT_UNATTRIBUTED"

        else:
            category = "FLAT_UNATTRIBUTED"
            last_cause[identity] = "NONE"

        category_counts[category] += 1

    print("T115-64|TEST_ONLY|" "H1_ACTIVE_FLAT_CONTINUATION_CAUSE_AUDIT")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("NO_FUTURE_PNL_USED=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4
    assert not inflight

    pooled: Counter[str] = Counter()
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

        observed = counts.get(id(engine), Counter())

        continuation = sum(observed[category] for category in CATEGORIES)

        flat = sum(observed[category] for category in FLAT_CATEGORIES)

        assert continuation == engine.post_signal_active_bars
        assert observed["WITH_POSITION"] == engine.exposed_active_bars
        assert flat == continuation - observed["WITH_POSITION"]

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"CLOSED={len(result.trades)}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={result.open_at_end}"
        )

        print(
            f"ACTIVE_FLAT_CAUSES|PERIOD={name}|"
            f"CONTINUATION={continuation}|"
            f"WITH_POSITION={observed['WITH_POSITION']}|"
            f"FLAT_TOTAL={flat}|"
            f"EXIT_FILL={observed['FLAT_EXIT_FILL']}|"
            f"AFTER_EXIT={observed['FLAT_AFTER_EXIT']}|"
            f"ENTRY_GAP={observed['FLAT_ENTRY_GAP']}|"
            f"AFTER_GAP={observed['FLAT_AFTER_GAP']}|"
            f"UNATTRIBUTED={observed['FLAT_UNATTRIBUTED']}"
        )

        pooled.update(observed)
        net_values.append(net)

    pooled_continuation = sum(pooled[category] for category in CATEGORIES)

    pooled_flat = sum(pooled[category] for category in FLAT_CATEGORIES)

    assert pooled_continuation == 5504
    assert pooled["WITH_POSITION"] == 3333
    assert pooled_flat == 2171

    pooled_net = math.fsum(net_values)

    assert math.isclose(
        pooled_net,
        -680.30,
        abs_tol=funnel.EPS,
    )

    print(
        f"POOLED_ACTIVE_FLAT_CAUSES|"
        f"CONTINUATION={pooled_continuation}|"
        f"WITH_POSITION={pooled['WITH_POSITION']}|"
        f"FLAT_TOTAL={pooled_flat}|"
        f"EXIT_FILL={pooled['FLAT_EXIT_FILL']}|"
        f"AFTER_EXIT={pooled['FLAT_AFTER_EXIT']}|"
        f"ENTRY_GAP={pooled['FLAT_ENTRY_GAP']}|"
        f"AFTER_GAP={pooled['FLAT_AFTER_GAP']}|"
        f"UNATTRIBUTED={pooled['FLAT_UNATTRIBUTED']}"
    )

    print(f"POOLED_BASELINE|CLOSED=333|" f"OPEN_END=1|NET040={pooled_net:+.2f}")

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ACTIVE_CONTINUATION_5504_OF_5504=OK")
    print("ACTIVE_FLAT_2171_OF_2171=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("FLAT_BARS_ARE_NOT_PROVEN_ENTRY_OPPORTUNITIES=True")
    print("NO_REENTRY_SIMULATED=True")
    print("NO_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_64_H1_ACTIVE_FLAT_CONTINUATION_CAUSE_AUDIT=OK")


if __name__ == "__main__":
    main()
