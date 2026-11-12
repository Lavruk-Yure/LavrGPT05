# -*- coding: utf-8 -*-
"""RoadMap115 / T115-65: ACTIVE post-EXIT episode anatomy.

TEST_ONLY / DATA_ONLY.

Виміряти окремі епізоди ACTIVE без позиції після EXIT:
кількість епізодів, довжину та часові розриви.

Облік ведеться за спостереженнями стану Engine.
Майбутній PnL не використовується, повторний
ENTRY не моделюється.

Production, Replay-логіка та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
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


EXPECTED_POST_EXIT = {
    "2024_NOV_DEC": (8, 134),
    "2025": (49, 715),
    "2026_TO_2026_08_25": (35, 635),
    "2026_AUG_OCT": (10, 174),
}


@dataclass(slots=True)
class Episode:
    """Один після-EXIT епізод без позиції в ACTIVE."""

    first_at: datetime
    last_at: datetime
    direction: str
    bars: int = 1
    discontinuities: int = 0


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _length_bucket(length: int) -> str:
    """Згрупувати кількість спостережених H1-барів."""
    if length == 1:
        return "1"
    if length <= 3:
        return "2_3"
    if length <= 6:
        return "4_6"
    if length <= 12:
        return "7_12"
    if length <= 24:
        return "13_24"
    return "25_PLUS"


def main() -> None:
    """Звірити після-EXIT епізоди з T115-64."""
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
        TEST_DIR / "T115_64_H1_Active_Flat_Continuation_Cause_Audit.py",
    )

    assert all(path.is_file() for path in guarded)
    before = [_sha(path) for path in guarded]

    # Утримуємо посилання на Engine для стабільності ID.
    observed_engines: dict[int, Any] = {}

    # Стан на момент виклику on_bar.
    inflight: dict[
        FrameType,
        tuple[int, bool, bool, str, datetime, str],
    ] = {}

    # Поточний епізод кожного Engine.
    active_episodes: dict[int, Episode] = {}

    # Усі епізоди, включно з незавершеними.
    episodes: dict[int, list[Episode]] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Зібрати після-EXIT епізоди без зміни Engine."""
        if frame.f_code is not on_bar_code:
            return

        if event == "call":
            observed_engine = frame.f_locals.get("self")
            observation = frame.f_locals.get("observation")
            bar = frame.f_locals.get("bar")

            if observed_engine is None or observation is None or bar is None:
                return

            identity = id(observed_engine)
            observed_engines[identity] = observed_engine

            is_continuation = (
                observation.regime_phase == active_phase
                and observed_engine.previous_phase == active_phase
            )

            pending = observed_engine.pending
            pending_action = pending.action if pending is not None else "NONE"

            position = observed_engine.position
            was_open = position is not None

            position_side = position.direction if position is not None else "NONE"

            inflight[frame] = (
                identity,
                is_continuation,
                was_open,
                pending_action,
                bar.timestamp,
                position_side,
            )
            return

        if event != "return":
            return

        state = inflight.pop(frame, None)

        if state is None:
            return

        (
            identity,
            was_continuation,
            was_open,
            pending_action,
            bar_at,
            position_side,
        ) = state

        observed_engine = observed_engines[identity]

        # Епізод закінчується при втраті ACTIVE
        # або появі відкритої позиції.
        if not was_continuation or observed_engine.position is not None:
            active_episodes.pop(identity, None)
            return

        if pending_action == "EXIT" and was_open:
            # Виконано EXIT, але ACTIVE ще триває.
            new_episode = Episode(
                first_at=bar_at,
                last_at=bar_at,
                direction=position_side,
            )

            episodes.setdefault(
                identity,
                [],
            ).append(new_episode)

            active_episodes[identity] = new_episode
            return

        tracked = active_episodes.get(identity)

        if pending_action == "NONE" and not was_open and tracked is not None:
            assert bar_at > tracked.last_at

            if bar_at - tracked.last_at > observed_engine.interval:
                tracked.discontinuities += 1

            tracked.bars += 1
            tracked.last_at = bar_at
            return

        active_episodes.pop(identity, None)

    print("T115-65|TEST_ONLY|" "H1_ACTIVE_POST_EXIT_EPISODE_ANATOMY")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("EPISODE_UNIT=OBSERVED_H1_BARS")
    print("NO_FUTURE_PNL_USED=True")
    print("NO_REENTRY_SIMULATED=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4
    assert not inflight

    pooled_starts = 0
    pooled_following = 0
    pooled_lengths: list[int] = []
    pooled_buckets: Counter[str] = Counter()
    pooled_gapped_episodes = 0
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

        records = episodes.get(
            id(engine),
            [],
        )

        starts = len(records)
        following = sum(item.bars - 1 for item in records)

        expected_starts, expected_following = EXPECTED_POST_EXIT[name]

        assert starts == expected_starts
        assert following == expected_following

        lengths = [item.bars for item in records]

        assert all(length >= 1 for length in lengths)

        buckets = Counter(_length_bucket(length) for length in lengths)

        assert sum(buckets.values()) == starts
        assert sum(lengths) == starts + following

        gapped = sum(item.discontinuities > 0 for item in records)

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"CLOSED={len(result.trades)}|"
            f"NET040={net:+.2f}|"
            f"OPEN_END={result.open_at_end}"
        )

        print(
            f"POST_EXIT_EPISODES|PERIOD={name}|"
            f"EPISODES={starts}|"
            f"EXIT_FILL_BARS={starts}|"
            f"AFTER_EXIT_BARS={following}|"
            f"ALL_BARS={starts + following}|"
            f"MIN_BARS={min(lengths)}|"
            f"MEDIAN_BARS={statistics.median(lengths):.1f}|"
            f"MAX_BARS={max(lengths)}|"
            f"EPISODES_WITH_TIME_GAPS={gapped}"
        )

        for bucket in (
            "1",
            "2_3",
            "4_6",
            "7_12",
            "13_24",
            "25_PLUS",
        ):
            print(
                f"POST_EXIT_LENGTH_BUCKET|PERIOD={name}|"
                f"BUCKET={bucket}|"
                f"EPISODES={buckets[bucket]}"
            )

        longest = sorted(
            records,
            key=lambda item: (
                -item.bars,
                item.first_at,
            ),
        )[:3]

        for number, item in enumerate(
            longest,
            start=1,
        ):
            print(
                f"POST_EXIT_LONGEST|PERIOD={name}|"
                f"RANK={number}|"
                f"SIDE={item.direction}|"
                f"FIRST_BAR={item.first_at.isoformat()}|"
                f"LAST_BAR={item.last_at.isoformat()}|"
                f"OBSERVED_BARS={item.bars}|"
                f"TIME_GAPS={item.discontinuities}"
            )

        print(f"POST_EXIT_EPISODE_RECONCILIATION=" f"{name}:OK")

        pooled_starts += starts
        pooled_following += following
        pooled_lengths.extend(lengths)
        pooled_buckets.update(buckets)
        pooled_gapped_episodes += gapped
        net_values.append(net)

    assert pooled_starts == 102
    assert pooled_following == 1658
    assert sum(pooled_lengths) == 1760

    pooled_net = math.fsum(net_values)

    assert math.isclose(
        pooled_net,
        -680.30,
        abs_tol=funnel.EPS,
    )

    print(
        f"POOLED_POST_EXIT_EPISODES|"
        f"EPISODES={pooled_starts}|"
        f"EXIT_FILL_BARS={pooled_starts}|"
        f"AFTER_EXIT_BARS={pooled_following}|"
        f"ALL_BARS={sum(pooled_lengths)}|"
        f"MIN_BARS={min(pooled_lengths)}|"
        f"MEDIAN_BARS={statistics.median(pooled_lengths):.1f}|"
        f"MAX_BARS={max(pooled_lengths)}|"
        f"EPISODES_WITH_TIME_GAPS={pooled_gapped_episodes}"
    )

    for bucket in (
        "1",
        "2_3",
        "4_6",
        "7_12",
        "13_24",
        "25_PLUS",
    ):
        print(
            f"POOLED_POST_EXIT_LENGTH_BUCKET|"
            f"BUCKET={bucket}|"
            f"EPISODES={pooled_buckets[bucket]}"
        )

    print(f"POOLED_BASELINE|CLOSED=333|" f"OPEN_END=1|NET040={pooled_net:+.2f}")

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("POST_EXIT_EPISODES_102_OF_102=OK")
    print("POST_EXIT_BARS_1760_OF_1760=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("EPISODES_ARE_NOT_PROVEN_TRADING_OPPORTUNITIES=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("NO_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_65_H1_ACTIVE_POST_EXIT_EPISODE_ANATOMY=OK")


if __name__ == "__main__":
    main()
