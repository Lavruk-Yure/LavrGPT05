# -*- coding: utf-8 -*-
"""RoadMap115 / T115-66: H1 post-EXIT reason attribution.

TEST_ONLY / DATA_ONLY.

Встановити причини 102 EXIT, після яких
дослідницький Engine спостерігав продовження ACTIVE.

Причина EXIT відома до виконання закриття.
Стан ACTIVE поточного бару доступний лише на його
закритті, тому використовується тільки для аудиту.

Не створює повторних входів і не використовує PnL
для торгових рішень. Production та MD7 незмінні.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


EXPECTED_EPISODES = {
    "2024_NOV_DEC": 8,
    "2025": 49,
    "2026_TO_2026_08_25": 35,
    "2026_AUG_OCT": 10,
}


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Звірити причини після-EXIT епізодів із ClosedTrade."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

    active_phase = getattr(
        engine_module,
        "ALLIGATOR_REGIME_PHASE_ACTIVE",
    )

    exit_33_reason = getattr(
        engine_module,
        "EXIT_33_REASON",
    )

    assert isinstance(exit_33_reason, str)

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_61_H1_Entry_Signal_Funnel_Audit.py",
        TEST_DIR / "T115_65_H1_Active_Post_Exit_Episode_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    observed_engines: dict[int, Any] = {}

    inflight: dict[
        FrameType,
        tuple[int, datetime, str, str],
    ] = {}

    exit_records: dict[
        int,
        list[tuple[datetime, str, str]],
    ] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Зібрати причину EXIT без втручання в Engine."""
        if frame.f_code is not on_bar_code:
            return

        if event == "call":
            observed_engine = frame.f_locals.get("self")
            observation = frame.f_locals.get("observation")
            bar = frame.f_locals.get("bar")

            if observed_engine is None or observation is None or bar is None:
                return

            is_continuation = (
                observation.regime_phase == active_phase
                and observed_engine.previous_phase == active_phase
            )

            pending = observed_engine.pending
            position = observed_engine.position

            if (
                not is_continuation
                or pending is None
                or pending.action != "EXIT"
                or position is None
            ):
                return

            identity = id(observed_engine)
            observed_engines[identity] = observed_engine

            inflight[frame] = (
                identity,
                bar.timestamp,
                position.direction,
                pending.reason,
            )
            return

        if event != "return":
            return

        state = inflight.pop(frame, None)

        if state is None:
            return

        identity, exit_at, side, reason = state

        observed_engine = observed_engines[identity]

        if observed_engine.position is not None:
            raise AssertionError(f"EXPECTED_EXIT_FILL={exit_at.isoformat()}")

        exit_records.setdefault(
            identity,
            [],
        ).append((exit_at, side, reason))

    print("T115-66|TEST_ONLY|" "H1_POST_EXIT_REASON_ATTRIBUTION")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print(f"EXIT_33_REASON={exit_33_reason}")
    print("ACTIVE_STATE_AT_EXIT_BAR_CLOSE_ONLY=True")
    print("NO_REENTRY_SIMULATED=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4
    assert not inflight

    pooled_groups: Counter[tuple[str, str]] = Counter()
    pooled_33 = 0
    pooled_count = 0
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

        records = exit_records.get(
            id(engine),
            [],
        )

        assert len(records) == EXPECTED_EPISODES[name]

        closed = Counter(
            (
                trade.exit_at,
                trade.direction,
                trade.exit_reason,
            )
            for trade in result.trades
        )

        selected = Counter(records)

        for key, count in selected.items():
            assert count <= closed[key], f"EXIT_REASON_MISMATCH={name}|{key}"

        groups: Counter[tuple[str, str]] = Counter(
            (side, reason) for _, side, reason in records
        )

        count_33 = sum(1 for _, _, reason in records if reason == exit_33_reason)

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"CLOSED={len(result.trades)}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={result.open_at_end}"
        )

        for (side, reason), count in sorted(groups.items()):
            print(
                f"POST_EXIT_REASON|PERIOD={name}|"
                f"SIDE={side}|"
                f"REASON={reason}|"
                f"EPISODES={count}|"
                f"IS_EXIT_33={reason == exit_33_reason}"
            )

        print(
            f"POST_EXIT_REASON_SUMMARY|PERIOD={name}|"
            f"EPISODES={len(records)}|"
            f"EXIT_33={count_33}|"
            f"OTHER={len(records) - count_33}"
        )

        print(f"EXIT_REASON_TRADE_MATCH={name}:OK")

        pooled_groups.update(groups)
        pooled_33 += count_33
        pooled_count += len(records)
        net_values.append(net)

    assert pooled_count == 102
    assert sum(pooled_groups.values()) == 102

    pooled_net = math.fsum(net_values)

    assert math.isclose(
        pooled_net,
        -680.30,
        abs_tol=funnel.EPS,
    )

    for (side, reason), count in sorted(pooled_groups.items()):
        print(
            f"POOLED_POST_EXIT_REASON|"
            f"SIDE={side}|"
            f"REASON={reason}|"
            f"EPISODES={count}|"
            f"IS_EXIT_33={reason == exit_33_reason}"
        )

    print(
        f"POOLED_POST_EXIT_REASON_SUMMARY|"
        f"EPISODES={pooled_count}|"
        f"EXIT_33={pooled_33}|"
        f"OTHER={pooled_count - pooled_33}"
    )

    print(f"POOLED_BASELINE|CLOSED=333|" f"OPEN_END=1|NET040={pooled_net:+.2f}")

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("POST_EXIT_REASONS_102_OF_102=OK")
    print("CLOSED_TRADE_REASONS_RECONCILED=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("EXIT_BAR_CLOSE_NOT_USED_AS_ENTRY_SIGNAL=True")
    print("EPISODES_NOT_PROVEN_PROFITABLE=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("NO_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_66_H1_POST_EXIT_REASON_ATTRIBUTION=OK")


if __name__ == "__main__":
    main()
