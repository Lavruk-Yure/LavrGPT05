# -*- coding: utf-8 -*-
"""RoadMap115 / T115-67: SELL_33 exit ablation.

TEST_ONLY / DATA_ONLY.

Порівняти незмінений SELL_33 з існуючим ZERO_33
на однаковій послідовності завершених H1-спостережень.

Початковий стан Engine копіюється перед першим on_bar.
Окремий SELL_33 mirror повинен точно збігтися
з оригінальним Engine.

Повний торговий шлях після відмінного EXIT може
змінитися; це не paired-trade порівняння.

Production, основний Replay та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections.abc import Callable
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _net(result: Any, cost: float) -> float:
    """Порахувати результат тільки закритих угод."""
    return math.fsum(trade.pips - cost for trade in result.trades)


def _count_33(result: Any, reason: str) -> int:
    """Порахувати закриття за правилом 33%."""
    return sum(trade.exit_reason == reason for trade in result.trades)


def main() -> None:
    """Порівняти два існуючі EXIT-режими."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

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
        TEST_DIR / "T115_66_H1_Post_Exit_Reason_Attribution.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    observed_engines: dict[int, Any] = {}
    initial_states: dict[int, Any] = {}

    streams: dict[
        int,
        list[tuple[int, Any, Any]],
    ] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Запам'ятати виклик Engine і стан до першого бару."""
        if event != "call" or frame.f_code is not on_bar_code:
            return

        observed_engine = frame.f_locals.get("self")
        captured_index = frame.f_locals.get("index")
        captured_bar = frame.f_locals.get("bar")
        captured_observation = frame.f_locals.get("observation")

        if (
            observed_engine is None
            or captured_index is None
            or captured_bar is None
            or captured_observation is None
        ):
            raise AssertionError("INCOMPLETE_ENGINE_CALL")

        engine_id = id(observed_engine)
        observed_engines[engine_id] = observed_engine

        if engine_id not in initial_states:
            initial_states[engine_id] = deepcopy(observed_engine)

        streams.setdefault(engine_id, []).append(
            (captured_index, captured_bar, captured_observation)
        )

    print("T115-67|TEST_ONLY|" "SELL33_EXIT_ABLATION_AUDIT")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("VARIANTS=SELL_33,ZERO_33")
    print("NO_NEW_EXIT_RULE=True")
    print("NO_REENTRY_RULE=True")
    print("COMPARISON=FULL_PATH_ABLATION")
    print("OPEN_POSITIONS_NOT_MARKED_TO_MARKET=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4

    cost = funnel.NET_COST_PIPS
    pooled_sell_net: list[float] = []
    pooled_zero_net: list[float] = []

    pooled_sell_closed = 0
    pooled_zero_closed = 0
    pooled_sell_open = 0
    pooled_zero_open = 0
    pooled_sell_33_exits = 0

    for name, original in engines:
        identity = id(original)

        assert identity in initial_states
        assert identity in streams

        initial = initial_states[identity]
        records = streams[identity]

        assert records
        assert original.use_33_for

        # Дзеркало початкового варіанта перевіряє
        # точність захопленої послідовності H1.
        mirror_sell = deepcopy(initial)

        # Вимикаємо лише існуючий режим giveback.
        mirror_zero = deepcopy(initial)
        mirror_zero.use_33_for = frozenset()

        for index, bar, observation in records:
            mirror_sell.on_bar(
                index,
                bar,
                observation,
            )

            mirror_zero.on_bar(
                index,
                bar,
                observation,
            )

        mirror_sell.finish()
        mirror_zero.finish()

        assert mirror_sell == original, f"SELL33_MIRROR_MISMATCH={name}"

        print(f"SELL33_ENGINE_MIRROR={name}:OK")

        sell_result = mirror_sell.result
        zero_result = mirror_zero.result

        expected_count, expected_net, expected_open = funnel.EXPECTED[name]

        sell_net = _net(sell_result, cost)
        zero_net = _net(zero_result, cost)

        assert len(sell_result.trades) == expected_count
        assert sell_result.open_at_end == expected_open
        assert math.isclose(
            sell_net,
            expected_net,
            abs_tol=funnel.EPS,
        )

        assert zero_result.entries == (
            len(zero_result.trades) + zero_result.open_at_end
        )

        assert zero_result.entry_signals == sell_result.entry_signals

        assert (
            _count_33(
                zero_result,
                exit_33_reason,
            )
            == 0
        )

        sell_33_exits = _count_33(
            sell_result,
            exit_33_reason,
        )

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"CLOSED={expected_count}|"
            f"NET040={sell_net:+.2f}|"
            f"OPEN_END={expected_open}"
        )

        print(
            f"EXIT_ABLATION|PERIOD={name}|"
            f"SELL33_CLOSED={len(sell_result.trades)}|"
            f"SELL33_NET040={sell_net:+.2f}|"
            f"SELL33_OPEN_END={sell_result.open_at_end}|"
            f"SELL33_GIVEBACK_EXITS={sell_33_exits}|"
            f"ZERO33_CLOSED={len(zero_result.trades)}|"
            f"ZERO33_NET040={zero_net:+.2f}|"
            f"ZERO33_OPEN_END={zero_result.open_at_end}|"
            f"DELTA_ZERO_MINUS_SELL={zero_net - sell_net:+.2f}"
        )

        print(f"EXIT_ABLATION_ACCOUNTING={name}:OK")

        pooled_sell_net.append(sell_net)
        pooled_zero_net.append(zero_net)
        pooled_sell_closed += len(sell_result.trades)
        pooled_zero_closed += len(zero_result.trades)
        pooled_sell_open += sell_result.open_at_end
        pooled_zero_open += zero_result.open_at_end
        pooled_sell_33_exits += sell_33_exits

    sell_total = math.fsum(pooled_sell_net)
    zero_total = math.fsum(pooled_zero_net)

    assert pooled_sell_closed == 333
    assert pooled_sell_open == 1

    assert math.isclose(
        sell_total,
        -680.30,
        abs_tol=funnel.EPS,
    )

    # T115-66 встановив щонайменше 102 таких EXIT.
    assert pooled_sell_33_exits >= 102

    print(
        "POOLED_EXIT_ABLATION|"
        f"SELL33_CLOSED={pooled_sell_closed}|"
        f"SELL33_NET040={sell_total:+.2f}|"
        f"SELL33_OPEN_END={pooled_sell_open}|"
        f"SELL33_GIVEBACK_EXITS={pooled_sell_33_exits}|"
        f"ZERO33_CLOSED={pooled_zero_closed}|"
        f"ZERO33_NET040={zero_total:+.2f}|"
        f"ZERO33_OPEN_END={pooled_zero_open}|"
        f"DELTA_ZERO_MINUS_SELL={zero_total - sell_total:+.2f}"
    )

    assert before == {path: _sha(path) for path in guarded}

    print("FOUR_PERIOD_SELL33_BASELINE=OK")
    print("SELL33_REPLAY_MIRROR=OK")
    print("ZERO33_EXISTING_EXIT_MODE_ONLY=True")
    print("CLOSED_ONLY_COMPARISON_WITH_OPEN_END_DISCLOSED=True")
    print("RESULT_IS_NOT_PRODUCTION_PROOF=True")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("NO_REENTRY_SIMULATED=True")
    print("NO_PRODUCTION_OR_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_67_SELL33_EXIT_ABLATION_AUDIT=OK")


if __name__ == "__main__":
    main()
