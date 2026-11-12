# -*- coding: utf-8 -*-
"""RoadMap115 / T115-68: SELL33/ZERO33 pair and exit audit.

TEST_ONLY / DATA_ONLY.

Перевірити тотожність входів двох існуючих сценаріїв.
Розкласти різницю закритого PnL за BUY/SELL і
за зіставленими та незбіглими входами.

Зіставлення відбувається за фактичними entry_at,
direction та entry_price, а не за порядком угод.

Жодного нового ENTRY або EXIT.
Production, основний Replay та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from collections.abc import Callable
from copy import deepcopy
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


EXPECTED_ZERO = {
    "2024_NOV_DEC": -326.20,
    "2025": -31.40,
    "2026_TO_2026_08_25": -173.90,
    "2026_AUG_OCT": -175.50,
}

EXPECTED_GIVEBACK = {
    "2024_NOV_DEC": 8,
    "2025": 51,
    "2026_TO_2026_08_25": 36,
    "2026_AUG_OCT": 10,
}


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(trade: Any) -> tuple[datetime, str, float]:
    """Повернути точний ключ входу."""
    return trade.entry_at, trade.direction, trade.entry_price


def _net(trades: list[Any], cost: float) -> float:
    """Повернути результат закритих угод із витратами."""
    return math.fsum(trade.pips - cost for trade in trades)


def _index(trades: list[Any]) -> dict[tuple[datetime, str, float], Any]:
    """Побудувати індекс без повторюваних ключів."""
    output = {_key(trade): trade for trade in trades}

    assert len(output) == len(trades), "DUPLICATE_ENTRY_KEY"
    return output


def main() -> None:
    """Зіставити входи та причинно окремі результати EXIT."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")
    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

    buy_direction = getattr(engine_module, "DIRECTION_UP")
    sell_direction = getattr(engine_module, "DIRECTION_DOWN")
    giveback_reason = getattr(engine_module, "EXIT_33_REASON")

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_61_H1_Entry_Signal_Funnel_Audit.py",
        TEST_DIR / "T115_67_Sell33_Exit_Ablation_Audit.py",
    )

    assert all(path.is_file() for path in guarded)
    before = [_sha(path) for path in guarded]

    observed_engines: dict[int, Any] = {}
    initial_states: dict[int, Any] = {}
    streams: dict[int, list[tuple[int, Any, Any]]] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Зберегти початковий стан та H1-події Engine."""
        if event != "call" or frame.f_code is not on_bar_code:
            return

        captured_engine = frame.f_locals.get("self")
        captured_index = frame.f_locals.get("index")
        captured_bar = frame.f_locals.get("bar")
        captured_observation = frame.f_locals.get("observation")

        if (
            captured_engine is None
            or captured_index is None
            or captured_bar is None
            or captured_observation is None
        ):
            raise AssertionError("INCOMPLETE_ENGINE_CALL")

        captured_id = id(captured_engine)
        observed_engines[captured_id] = captured_engine

        if captured_id not in initial_states:
            initial_states[captured_id] = deepcopy(captured_engine)

        streams.setdefault(captured_id, []).append(
            (captured_index, captured_bar, captured_observation)
        )

    print("T115-68|TEST_ONLY|SELL33_ZERO33_ENTRY_PAIR_EXIT_DELTA")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("ENTRY_MATCH_KEY=TIME_DIRECTION_PRICE")
    print("NO_NEW_TRADING_RULE=True")
    print("CLOSED_PNL_ONLY=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4

    sell_totals: list[float] = []
    zero_totals: list[float] = []
    pooled_matched = 0
    pooled_sell_only = 0
    pooled_zero_only = 0
    pooled_different_exits = 0

    for name, original in engines:
        source_id = id(original)

        assert source_id in initial_states
        assert source_id in streams

        initial = initial_states[source_id]
        records = streams[source_id]

        mirror_sell = deepcopy(initial)
        mirror_zero = deepcopy(initial)
        mirror_zero.use_33_for = frozenset()

        for bar_index, source_bar, source_observation in records:
            mirror_sell.on_bar(bar_index, source_bar, source_observation)
            mirror_zero.on_bar(bar_index, source_bar, source_observation)

        mirror_sell.finish()
        mirror_zero.finish()

        assert mirror_sell == original
        print(f"SELL33_MIRROR={name}:OK")

        sell_trades = mirror_sell.result.trades
        zero_trades = mirror_zero.result.trades

        expected_count, expected_sell, expected_open = funnel.EXPECTED[name]

        sell_net = _net(sell_trades, funnel.NET_COST_PIPS)
        zero_net = _net(zero_trades, funnel.NET_COST_PIPS)

        assert len(sell_trades) == expected_count
        assert len(zero_trades) == expected_count
        assert mirror_sell.result.open_at_end == expected_open
        assert mirror_zero.result.open_at_end == expected_open

        assert math.isclose(sell_net, expected_sell, abs_tol=funnel.EPS)
        assert math.isclose(zero_net, EXPECTED_ZERO[name], abs_tol=funnel.EPS)

        giveback_count = sum(
            trade.exit_reason == giveback_reason for trade in sell_trades
        )

        assert giveback_count == EXPECTED_GIVEBACK[name]

        sell_index = _index(sell_trades)
        zero_index = _index(zero_trades)

        matched_keys = sell_index.keys() & zero_index.keys()
        sell_only_keys = sell_index.keys() - zero_index.keys()
        zero_only_keys = zero_index.keys() - sell_index.keys()

        assert len(matched_keys) + len(sell_only_keys) == len(sell_trades)
        assert len(matched_keys) + len(zero_only_keys) == len(zero_trades)

        different_exits = sum(
            sell_index[key].exit_at != zero_index[key].exit_at
            or sell_index[key].exit_price != zero_index[key].exit_price
            or sell_index[key].exit_reason != zero_index[key].exit_reason
            for key in matched_keys
        )

        paired_delta = math.fsum(
            sell_index[key].pips - zero_index[key].pips for key in matched_keys
        )

        unpaired_delta = _net(
            [sell_index[key] for key in sell_only_keys],
            funnel.NET_COST_PIPS,
        ) - _net(
            [zero_index[key] for key in zero_only_keys],
            funnel.NET_COST_PIPS,
        )

        assert math.isclose(
            paired_delta + unpaired_delta,
            sell_net - zero_net,
            abs_tol=funnel.EPS,
        )

        print(
            f"BASELINE_MATCH={name}:OK|"
            f"SELL33_NET040={sell_net:+.2f}|"
            f"ZERO33_NET040={zero_net:+.2f}|"
            f"GIVEBACK_EXITS={giveback_count}"
        )

        print(
            f"ENTRY_PAIRING|PERIOD={name}|"
            f"MATCHED={len(matched_keys)}|"
            f"SELL33_ONLY={len(sell_only_keys)}|"
            f"ZERO33_ONLY={len(zero_only_keys)}|"
            f"DIFFERENT_EXITS={different_exits}"
        )

        for direction, label in (
            (buy_direction, "BUY"),
            (sell_direction, "SELL"),
        ):
            sell_side = [trade for trade in sell_trades if trade.direction == direction]
            zero_side = [trade for trade in zero_trades if trade.direction == direction]

            sell_side_net = _net(sell_side, funnel.NET_COST_PIPS)
            zero_side_net = _net(zero_side, funnel.NET_COST_PIPS)

            print(
                f"EXIT_DELTA_SIDE|PERIOD={name}|"
                f"SIDE={label}|"
                f"SELL33_TRADES={len(sell_side)}|"
                f"ZERO33_TRADES={len(zero_side)}|"
                f"SELL33_NET040={sell_side_net:+.2f}|"
                f"ZERO33_NET040={zero_side_net:+.2f}|"
                f"DELTA_SELL_MINUS_ZERO="
                f"{sell_side_net - zero_side_net:+.2f}"
            )

        print(
            f"EXIT_DELTA_ACCOUNTING|PERIOD={name}|"
            f"MATCHED_DELTA={paired_delta:+.2f}|"
            f"UNPAIRED_DELTA={unpaired_delta:+.2f}|"
            f"FULL_DELTA={sell_net - zero_net:+.2f}|"
            f"RECONCILED=True"
        )

        pooled_matched += len(matched_keys)
        pooled_sell_only += len(sell_only_keys)
        pooled_zero_only += len(zero_only_keys)
        pooled_different_exits += different_exits
        sell_totals.append(sell_net)
        zero_totals.append(zero_net)

    total_sell = math.fsum(sell_totals)
    total_zero = math.fsum(zero_totals)

    assert math.isclose(total_sell, -680.30, abs_tol=funnel.EPS)
    assert math.isclose(total_zero, -707.00, abs_tol=funnel.EPS)

    assert pooled_matched + pooled_sell_only == 333
    assert pooled_matched + pooled_zero_only == 333

    print(
        f"POOLED_ENTRY_PAIRING|"
        f"MATCHED={pooled_matched}|"
        f"SELL33_ONLY={pooled_sell_only}|"
        f"ZERO33_ONLY={pooled_zero_only}|"
        f"DIFFERENT_EXITS={pooled_different_exits}"
    )

    print(
        f"POOLED_EXIT_DELTA|"
        f"SELL33_NET040={total_sell:+.2f}|"
        f"ZERO33_NET040={total_zero:+.2f}|"
        f"DELTA_SELL_MINUS_ZERO={total_sell - total_zero:+.2f}"
    )

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ENTRY_PAIR_AND_EXIT_DELTA_ACCOUNTING=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("OPEN_POSITIONS_NOT_MARKED_TO_MARKET=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("PRODUCTION_EQUIVALENCE_NOT_ASSERTED=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_68_SELL33_ZERO33_ENTRY_PAIR_EXIT_DELTA=OK")


if __name__ == "__main__":
    main()
