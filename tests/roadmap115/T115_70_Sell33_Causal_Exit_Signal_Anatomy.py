# -*- coding: utf-8 -*-
"""RoadMap115 / T115-70: SELL_33 causal exit signal anatomy.

TEST_ONLY / DATA_ONLY.

Порівняти 105 SELL_33 EXIT за фактичними ознаками,
доступними на завершенні H1 сигналу.

Ознаки:
- піковий close-profit у pips;
- close-profit сигнальної H1;
- частка відкату від піку;
- вік позиції на момент сигналу;
- regime_phase та regime Alligator.

Результат ZERO_33 використовується виключно як
ретроспективна outcome-мітка, не як торгова умова.

Production, Replay-логіка та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
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


EPS = 0.000001

EXPECTED = {
    "2024_NOV_DEC": (8, 7, -326.20),
    "2025": (51, 32, -31.40),
    "2026_TO_2026_08_25": (36, 23, -173.90),
    "2026_AUG_OCT": (10, 4, -175.50),
}


@dataclass(frozen=True, slots=True)
class ExitSignal:
    """Причинний стан на завершенні сигнальної H1."""

    at: datetime
    peak_pips: float
    close_pips: float
    giveback_ratio: float
    age_hours: float
    phase: str
    regime: str


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(trade: Any) -> tuple[datetime, str, float]:
    """Повернути незмінний ключ фактичного входу."""
    return (
        trade.entry_at,
        trade.direction,
        trade.entry_price,
    )


def _trade_index(
    trades: list[Any],
) -> dict[tuple[datetime, str, float], Any]:
    """Зіставити угоди без повторюваних ключів."""
    indexed = {_key(trade): trade for trade in trades}

    assert len(indexed) == len(trades)

    return indexed


def _net(trades: list[Any], cost: float) -> float:
    """Порахувати PnL тільки закритих угод."""
    return math.fsum(trade.pips - cost for trade in trades)


def _group_report(
    period: str,
    label: str,
    records: list[ExitSignal],
) -> None:
    """Показати ознаки групи без вибору порогів."""
    assert records

    def median(name: str) -> float:
        return statistics.median(getattr(item, name) for item in records)

    print(
        f"EXIT_SIGNAL_ANATOMY|PERIOD={period}|"
        f"LABEL={label}|COUNT={len(records)}|"
        f"PEAK_MEDIAN={median('peak_pips'):.2f}|"
        f"CLOSE_MEDIAN={median('close_pips'):.2f}|"
        f"GIVEBACK_RATIO_MEDIAN={median('giveback_ratio'):.4f}|"
        f"AGE_H_MEDIAN={median('age_hours'):.2f}"
    )

    phases = Counter(item.phase for item in records)

    regimes = Counter(item.regime for item in records)

    for phase, count in sorted(phases.items()):
        print(
            f"EXIT_SIGNAL_PHASE|PERIOD={period}|"
            f"LABEL={label}|PHASE={phase}|COUNT={count}"
        )

    for regime, count in sorted(regimes.items()):
        print(
            f"EXIT_SIGNAL_REGIME|PERIOD={period}|"
            f"LABEL={label}|REGIME={regime}|COUNT={count}"
        )


def main() -> None:
    """Звірити ознаки на EXIT із двома незмінними сценаріями."""
    funnel = import_module("T115_61_H1_Entry_Signal_Funnel_Audit")

    engine_module = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

    load_engines: Callable[[], list[tuple[str, Any]]] = getattr(funnel, "_engines")

    engine_type = getattr(engine_module, "Engine")
    on_bar_code = engine_type.on_bar.__code__

    sell_direction = getattr(
        engine_module,
        "DIRECTION_DOWN",
    )

    reason_33 = getattr(
        engine_module,
        "EXIT_33_REASON",
    )

    threshold_33 = getattr(
        engine_module,
        "EXIT_33_THRESHOLD",
    )

    pip_size = getattr(engine_module, "PIP")

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_15_Extended_Timeframe_Plateau_Audit.py",
        TEST_DIR / "T115_21_H1_M15_Trend_Watch_Audit.py",
        TEST_DIR / "T115_32_Cross_Period_M15_Entry_State_Audit.py",
        TEST_DIR / "T115_61_H1_Entry_Signal_Funnel_Audit.py",
        TEST_DIR / "T115_67_Sell33_Exit_Ablation_Audit.py",
        TEST_DIR / "T115_69_Sell33_Paired_Exit_Impact_Distribution.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    observed_engines: dict[int, Any] = {}
    initial_states: dict[int, Any] = {}
    streams: dict[int, list[tuple[int, Any, Any]]] = {}

    def capture(
        frame: FrameType,
        event: str,
        _arg: Any,
    ) -> None:
        """Зберегти початковий Engine та завершені H1-події."""
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
            (
                captured_index,
                captured_bar,
                captured_observation,
            )
        )

    print("T115-70|TEST_ONLY|" "SELL33_CAUSAL_EXIT_SIGNAL_ANATOMY")
    print("ENGINE=FROZEN_RESEARCH_H1_ENGINE")
    print("SIGNAL_FEATURE_TIME=COMPLETED_H1_CLOSE")
    print("FUTURE_ZERO33_RESULT=OUTCOME_LABEL_ONLY")
    print("NO_PARAMETER_SEARCH=True")
    print("NO_NEW_EXIT_OR_REENTRY_RULE=True")

    previous_profiler = sys.getprofile()

    try:
        sys.setprofile(capture)
        engines = load_engines()
    finally:
        sys.setprofile(previous_profiler)

    assert len(engines) == 4

    pooled_groups: dict[str, list[ExitSignal]] = {
        "SELL33_BETTER": [],
        "ZERO33_BETTER": [],
    }

    sell_nets: list[float] = []
    zero_nets: list[float] = []
    pooled_changed = 0
    pooled_matched = 0

    for period, original in engines:
        source_id = id(original)

        assert source_id in initial_states
        assert source_id in streams

        mirror_sell = deepcopy(initial_states[source_id])
        mirror_zero = deepcopy(initial_states[source_id])

        mirror_zero.use_33_for = frozenset()

        snapshots: dict[
            tuple[datetime, str, float],
            ExitSignal,
        ] = {}

        for bar_index, source_bar, observation in streams[source_id]:
            exits_before = mirror_sell.result.exits_signaled

            mirror_sell.on_bar(
                bar_index,
                source_bar,
                observation,
            )

            # Визначаємо новий сигнал лише після завершення
            # обробки поточної H1, без наступних свічок.
            exits_after = mirror_sell.result.exits_signaled

            if exits_after > exits_before:
                assert exits_after == exits_before + 1

                pending = mirror_sell.pending

                if (
                    pending is not None
                    and pending.action == "EXIT"
                    and pending.reason == reason_33
                ):
                    position = mirror_sell.position

                    assert position is not None
                    assert position.direction == sell_direction
                    assert pending.available_at == observation.available_at
                    assert observation.available_at == (
                        source_bar.timestamp + mirror_sell.interval
                    )

                    peak_pips = mirror_sell.peak_close_pips

                    close_pips = (position.entry_price - source_bar.close) / pip_size

                    assert peak_pips > 0

                    giveback_ratio = (peak_pips - close_pips) / peak_pips

                    assert giveback_ratio >= threshold_33 - EPS

                    signal_age_hours = (
                        observation.available_at - position.entry_at
                    ).total_seconds() / 3600

                    assert signal_age_hours > 0

                    key = (
                        position.entry_at,
                        position.direction,
                        position.entry_price,
                    )

                    assert key not in snapshots

                    snapshots[key] = ExitSignal(
                        at=observation.available_at,
                        peak_pips=peak_pips,
                        close_pips=close_pips,
                        giveback_ratio=giveback_ratio,
                        age_hours=signal_age_hours,
                        phase=observation.regime_phase,
                        regime=observation.regime,
                    )

            mirror_zero.on_bar(
                bar_index,
                source_bar,
                observation,
            )

        mirror_sell.finish()
        mirror_zero.finish()

        assert mirror_sell == original

        sell_result = mirror_sell.result
        zero_result = mirror_zero.result

        expected_count, expected_sell_net, expected_open = funnel.EXPECTED[period]

        changed_expected, better_expected, expected_zero_net = EXPECTED[period]

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
            expected_sell_net,
            abs_tol=EPS,
        )

        assert math.isclose(
            zero_net,
            expected_zero_net,
            abs_tol=EPS,
        )

        sell_index = _trade_index(sell_trades)
        zero_index = _trade_index(zero_trades)

        assert sell_index.keys() == zero_index.keys()

        groups: dict[str, list[ExitSignal]] = {
            "SELL33_BETTER": [],
            "ZERO33_BETTER": [],
        }

        changed_keys: set[tuple[datetime, str, float]] = set()
        delta_values: list[float] = []

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
            assert sell_trade.exit_reason == reason_33
            assert key in snapshots

            signal = snapshots[key]

            assert signal.at <= sell_trade.exit_at
            assert signal.at > sell_trade.entry_at

            delta = sell_trade.pips - zero_trade.pips

            assert abs(delta) > EPS

            label = "SELL33_BETTER" if delta > 0 else "ZERO33_BETTER"

            groups[label].append(signal)
            changed_keys.add(key)
            delta_values.append(delta)

        assert set(snapshots) == changed_keys
        assert len(changed_keys) == changed_expected
        assert len(groups["SELL33_BETTER"]) == better_expected
        assert len(groups["ZERO33_BETTER"]) == (changed_expected - better_expected)

        assert math.isclose(
            math.fsum(delta_values),
            sell_net - zero_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={period}:OK|"
            f"SELL33_NET040={sell_net:+.2f}|"
            f"ZERO33_NET040={zero_net:+.2f}|"
            f"CLOSED={expected_count}"
        )

        print(
            f"EXIT_SIGNAL_RECONCILIATION|PERIOD={period}|"
            f"PAIRED_ENTRIES={len(sell_index)}|"
            f"SNAPSHOTS={len(snapshots)}|"
            f"CHANGED_EXITS={len(changed_keys)}|"
            f"SELL33_BETTER={len(groups['SELL33_BETTER'])}|"
            f"ZERO33_BETTER={len(groups['ZERO33_BETTER'])}|"
            f"DELTA_SELL_MINUS_ZERO={math.fsum(delta_values):+.2f}"
        )

        for label in ("SELL33_BETTER", "ZERO33_BETTER"):
            _group_report(
                period,
                label,
                groups[label],
            )

            pooled_groups[label].extend(groups[label])

        pooled_changed += len(changed_keys)
        pooled_matched += len(sell_index)
        sell_nets.append(sell_net)
        zero_nets.append(zero_net)

    assert pooled_matched == 333
    assert pooled_changed == 105
    assert len(pooled_groups["SELL33_BETTER"]) == 66
    assert len(pooled_groups["ZERO33_BETTER"]) == 39

    for label in ("SELL33_BETTER", "ZERO33_BETTER"):
        _group_report(
            "POOLED",
            label,
            pooled_groups[label],
        )

    sell_total = math.fsum(sell_nets)
    zero_total = math.fsum(zero_nets)

    assert math.isclose(sell_total, -680.30, abs_tol=EPS)
    assert math.isclose(zero_total, -707.00, abs_tol=EPS)

    print(
        "POOLED_EXIT_SIGNAL_RECONCILIATION|"
        f"PAIRED_ENTRIES={pooled_matched}|"
        f"SIGNALS={pooled_changed}|"
        "SELL33_BETTER=66|ZERO33_BETTER=39"
    )

    print(
        f"POOLED_BASELINE|"
        f"SELL33_NET040={sell_total:+.2f}|"
        f"ZERO33_NET040={zero_total:+.2f}|"
        f"DELTA_SELL_MINUS_ZERO={sell_total - zero_total:+.2f}"
    )

    assert before == {path: _sha(path) for path in guarded}

    print("FOUR_PERIOD_BASELINE_RECONCILIATION=OK")
    print("ENTRY_PAIRING_333_OF_333=OK")
    print("CAUSAL_EXIT_SNAPSHOTS_105_OF_105=OK")
    print("OUTCOME_LABELS_66_AND_39=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("NO_CAUSAL_DISCRIMINATOR_ASSERTED=True")
    print("NO_PARAMETER_OPTIMIZATION=True")
    print("NO_REENTRY_SIMULATED=True")
    print("PRODUCTION_EQUIVALENCE_NOT_ASSERTED=True")
    print("NO_PRODUCTION_OR_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_70_SELL33_CAUSAL_EXIT_SIGNAL_ANATOMY=OK")


if __name__ == "__main__":
    main()
