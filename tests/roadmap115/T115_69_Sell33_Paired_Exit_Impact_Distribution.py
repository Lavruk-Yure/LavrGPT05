# -*- coding: utf-8 -*-
"""RoadMap115 / T115-69: paired SELL_33 exit impact.

TEST_ONLY / DATA_ONLY.

Порівняти 105 змінених SELL EXIT у SELL_33 та ZERO_33.
Входи обох сценаріїв мають збігатися повністю.

Результати EXIT використовуються лише як outcome.
Торгові правила, production та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
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


EXPECTED_CHANGED = {
    "2024_NOV_DEC": 8,
    "2025": 51,
    "2026_TO_2026_08_25": 36,
    "2026_AUG_OCT": 10,
}

EXPECTED_ZERO_NET = {
    "2024_NOV_DEC": -326.20,
    "2025": -31.40,
    "2026_TO_2026_08_25": -173.90,
    "2026_AUG_OCT": -175.50,
}

EPS = 0.000001


def _sha(path: Path) -> str:
    """Обчислити SHA256 файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _net(trades: list[Any], cost: float) -> float:
    """Результат лише закритих угод."""
    return math.fsum(trade.pips - cost for trade in trades)


def _index(
    trades: list[Any],
) -> dict[tuple[datetime, str, float], Any]:
    """Побудувати індекс фактичних входів."""
    result = {
        (trade.entry_at, trade.direction, trade.entry_price): trade for trade in trades
    }

    assert len(result) == len(trades)
    return result


def _report(
    period: str,
    deltas: list[float],
    delays: list[float],
) -> None:
    """Показати розподіл ефектів без оптимізації."""
    assert deltas
    assert len(deltas) == len(delays)

    positive = [value for value in deltas if value > EPS]

    negative = [value for value in deltas if value < -EPS]

    tied = len(deltas) - len(positive) - len(negative)

    positive_sum = math.fsum(positive)
    negative_sum = math.fsum(negative)
    total = math.fsum(deltas)

    later = sum(delay > 0 for delay in delays)
    earlier = sum(delay < 0 for delay in delays)
    same = len(delays) - later - earlier

    print(
        f"PAIRED_EXIT_IMPACT|PERIOD={period}|"
        f"AFFECTED={len(deltas)}|"
        f"SELL33_BETTER={len(positive)}|"
        f"ZERO33_BETTER={len(negative)}|"
        f"TIED={tied}|"
        f"POSITIVE_SUM={positive_sum:+.2f}|"
        f"NEGATIVE_SUM={negative_sum:+.2f}|"
        f"NET_DELTA={total:+.2f}"
    )

    print(
        f"PAIRED_EXIT_DISTRIBUTION|PERIOD={period}|"
        f"MIN_DELTA={min(deltas):+.2f}|"
        f"MEDIAN_DELTA={statistics.median(deltas):+.2f}|"
        f"MAX_DELTA={max(deltas):+.2f}"
    )

    print(
        f"PAIRED_EXIT_TIMING|PERIOD={period}|"
        f"ZERO_LATER={later}|"
        f"ZERO_EARLIER={earlier}|"
        f"SAME_TIME={same}|"
        f"MEDIAN_DELAY_H={statistics.median(delays):+.2f}"
    )


def main() -> None:
    """Виміряти фактичний розподіл 105 EXIT-відмінностей."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

    sell_direction = getattr(
        engine_module,
        "DIRECTION_DOWN",
    )

    giveback_reason = getattr(
        engine_module,
        "EXIT_33_REASON",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_61_H1_Entry_Signal_Funnel_Audit.py",
        TEST_DIR / "T115_67_Sell33_Exit_Ablation_Audit.py",
        TEST_DIR / "T115_68_Sell33_Zero33_Entry_Pair_Exit_Delta_Audit.py",
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
        """Зберегти вхідний стан і завершені H1-події."""
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

    print("T115-69|TEST_ONLY|" "SELL33_PAIRED_EXIT_IMPACT_DISTRIBUTION")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("ENTRY_PAIRING_REQUIRED=True")
    print("EXIT_OUTCOME_ONLY=True")
    print("NO_PARAMETER_OPTIMIZATION=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4

    all_deltas: list[float] = []
    all_delays: list[float] = []
    sell_nets: list[float] = []
    zero_nets: list[float] = []

    for period, original in engines:
        source_id = id(original)

        assert source_id in initial_states
        assert source_id in streams

        initial = initial_states[source_id]
        records = streams[source_id]

        mirror_sell = deepcopy(initial)
        mirror_zero = deepcopy(initial)

        mirror_zero.use_33_for = frozenset()

        for bar_index, source_bar, source_observation in records:
            mirror_sell.on_bar(
                bar_index,
                source_bar,
                source_observation,
            )

            mirror_zero.on_bar(
                bar_index,
                source_bar,
                source_observation,
            )

        mirror_sell.finish()
        mirror_zero.finish()

        assert mirror_sell == original
        print(f"SELL33_MIRROR={period}:OK")

        sell_result = mirror_sell.result
        zero_result = mirror_zero.result

        expected_count, expected_sell, expected_open = funnel.EXPECTED[period]

        sell_trades = sell_result.trades
        zero_trades = zero_result.trades

        assert len(sell_trades) == expected_count
        assert len(zero_trades) == expected_count
        assert sell_result.open_at_end == expected_open
        assert zero_result.open_at_end == expected_open

        sell_net = _net(
            sell_trades,
            funnel.NET_COST_PIPS,
        )

        zero_net = _net(
            zero_trades,
            funnel.NET_COST_PIPS,
        )

        assert math.isclose(
            sell_net,
            expected_sell,
            abs_tol=EPS,
        )

        assert math.isclose(
            zero_net,
            EXPECTED_ZERO_NET[period],
            abs_tol=EPS,
        )

        sell_index = _index(sell_trades)
        zero_index = _index(zero_trades)

        assert sell_index.keys() == zero_index.keys()

        deltas: list[float] = []
        delays: list[float] = []

        for key, sell_trade in sell_index.items():
            zero_trade = zero_index[key]

            changed = (
                sell_trade.exit_at != zero_trade.exit_at
                or sell_trade.exit_price != zero_trade.exit_price
                or sell_trade.exit_reason != zero_trade.exit_reason
            )

            if not changed:
                assert math.isclose(
                    sell_trade.pips,
                    zero_trade.pips,
                    abs_tol=EPS,
                )
                continue

            assert sell_trade.direction == sell_direction
            assert sell_trade.exit_reason == giveback_reason

            delta = sell_trade.pips - zero_trade.pips

            delay_hours = (
                zero_trade.exit_at - sell_trade.exit_at
            ).total_seconds() / 3600

            deltas.append(delta)
            delays.append(delay_hours)

        assert len(deltas) == EXPECTED_CHANGED[period]

        assert math.isclose(
            math.fsum(deltas),
            sell_net - zero_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={period}:OK|"
            f"SELL33_NET040={sell_net:+.2f}|"
            f"ZERO33_NET040={zero_net:+.2f}|"
            f"AFFECTED={len(deltas)}"
        )

        _report(period, deltas, delays)

        all_deltas.extend(deltas)
        all_delays.extend(delays)
        sell_nets.append(sell_net)
        zero_nets.append(zero_net)

    assert len(all_deltas) == 105

    sell_total = math.fsum(sell_nets)
    zero_total = math.fsum(zero_nets)

    assert math.isclose(sell_total, -680.30, abs_tol=EPS)
    assert math.isclose(zero_total, -707.00, abs_tol=EPS)

    assert math.isclose(
        math.fsum(all_deltas),
        sell_total - zero_total,
        abs_tol=EPS,
    )

    _report("POOLED", all_deltas, all_delays)

    print(
        f"POOLED_BASELINE|"
        f"SELL33_NET040={sell_total:+.2f}|"
        f"ZERO33_NET040={zero_total:+.2f}|"
        f"DELTA_SELL_MINUS_ZERO={sell_total - zero_total:+.2f}"
    )

    assert before == [_sha(path) for path in guarded]

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ENTRY_PAIRING_333_OF_333=OK")
    print("AFFECTED_SELL_EXITS_105_OF_105=OK")
    print("PAIRED_EXIT_DELTA_ACCOUNTING=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("OUTCOME_NOT_USED_AS_ENTRY_FEATURE=True")
    print("NO_REENTRY_SIMULATED=True")
    print("PRODUCTION_EQUIVALENCE_NOT_ASSERTED=True")
    print("NO_PRODUCTION_OR_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_69_SELL33_PAIRED_EXIT_IMPACT_DISTRIBUTION=OK")


if __name__ == "__main__":
    main()
