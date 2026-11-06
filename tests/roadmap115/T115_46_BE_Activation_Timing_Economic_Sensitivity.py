# -*- coding: utf-8 -*-
"""RoadMap115 / T115-46: BE activation timing sensitivity.

TEST_ONLY / RESEARCH_ONLY.

Порівнюються дві часові моделі одного BE-кандидата:

LAGGED: перший контроль M1 на activation_at + 1 хвилина.
IMMEDIATE: перший контроль M1 на activation_at.

Активація BE, ціна BE, витрати 0.40 та baseline незмінні.
Використовуються T115-41, T115-42, T115-43, T115-45.

IMMEDIATE припускає нульову затримку розміщення стопа.
Це не підтверджене брокером виконання.

34 невизначені контакти не отримують вигаданого PnL.
Зайнятість позицій та наступні входи не перераховуються.
Production та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window
    from T115_42_M1_Break_Even_First_Breach_Audit import Target
    from T115_43_M1_BE_Paired_Economic_Audit import Pair
    from T115_45_BE_First_Post_Activation_M1_Audit import FirstMinute

t41 = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

t42 = import_module("T115_42_M1_Break_Even_First_Breach_Audit")

t43 = import_module("T115_43_M1_BE_Paired_Economic_Audit")

t44 = import_module("T115_44_BE_Execution_Cost_Robustness")

t45 = import_module("T115_45_BE_First_Post_Activation_M1_Audit")

BUY = t41.BUY
SELL = t41.SELL

COST = t41.COST
EPS = t41.EPS

KNOWN = t43.KNOWN
UNKNOWN = t43.UNCERTAIN

REFERENCE = t44.REFERENCE
SOURCE_FILES = t42.SOURCE_FILES

EXPECTED_RETIMED = {
    "2024_NOV_DEC": 3,
    "2025": 16,
    "2026_TO_2026_08_25": 9,
    "2026_AUG_OCT": 2,
}

Key = tuple[str, datetime, str]

load_windows = t41.load_windows
load_history = t41.load_history

build_targets = getattr(t42, "_targets")
read_source = getattr(t42, "_read_source")

fetch_old_bars = getattr(
    t43,
    "_fetch_breach_bars",
)

make_old_pair = getattr(
    t43,
    "_pair",
)

proxy_net = getattr(
    t43,
    "_proxy_net",
)

read_first_minutes = getattr(
    t45,
    "_read_first_minutes",
)


@dataclass(frozen=True, slots=True)
class Comparison:
    """Ті самі baseline-угоди у двох моделях затримки."""

    old: Pair
    immediate_partial_net: float
    retimed: bool
    immediate_adverse_open: bool

    @property
    def old_delta(self) -> float:
        return self.old.delta

    @property
    def new_delta(self) -> float:
        return self.immediate_partial_net - self.old.baseline_net

    @property
    def timing_delta(self) -> float:
        return self.new_delta - self.old_delta


def _sha(path: Path) -> str:
    """Контроль SHA256 опорних файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _synthetic() -> None:
    """Перевірити позитивний і негативний ефект часу."""
    make_trade = t41.make_trade

    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + timedelta(hours=2),
        entry_price=1.1000,
        exit_price=1.0980,
        pips=-20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    regular = t43.FillBar(
        at=at + timedelta(hours=1),
        open=1.1005,
        high=1.1008,
        low=1.1000,
    )

    adverse = t43.FillBar(
        at=at + timedelta(hours=1, minutes=1),
        open=1.0990,
        high=1.0992,
        low=1.0988,
    )

    regular_net, regular_gap = proxy_net(
        buy,
        regular,
    )

    adverse_net, adverse_gap = proxy_net(
        buy,
        adverse,
    )

    assert not regular_gap
    assert adverse_gap

    assert math.isclose(
        regular_net,
        0.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        adverse_net,
        -10.4,
        abs_tol=EPS,
    )

    # Раніше виконання може поліпшити результат.
    assert math.isclose(
        regular_net - adverse_net,
        10.4,
        abs_tol=EPS,
    )

    # А може погіршити, якщо перша M1 відкрилася
    # вже за захисним рівнем.
    assert math.isclose(
        adverse_net - regular_net,
        -10.4,
        abs_tol=EPS,
    )

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + timedelta(hours=2),
        entry_price=1.1000,
        exit_price=1.1020,
        pips=-20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell_regular = t43.FillBar(
        at=regular.at,
        open=1.0995,
        high=1.1001,
        low=1.0990,
    )

    sell_net, sell_gap = proxy_net(
        sell,
        sell_regular,
    )

    assert not sell_gap

    assert math.isclose(
        sell_net,
        0.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_IMMEDIATE_BE_MID_PROXY=OK")
    print("SYNTHETIC_TIMING_CAN_IMPROVE_OR_HARM=OK")
    print("SYNTHETIC_BUY_SELL_ACCOUNTING=OK")
    print("SYNTHETIC_BASELINE_UNCHANGED=OK")


def _make_comparison(
    period: str,
    trade: ClosedTrade,
    targets: dict[Key, Target],
    old_bars: dict,
    first_minutes: dict[Key, FirstMinute],
) -> Comparison:
    """Переоцінити тільки контакт у першій M1."""
    key = (
        period,
        trade.entry_at,
        trade.direction,
    )

    old = make_old_pair(
        period,
        trade,
        targets,
        old_bars,
    )

    target = targets.get(key)

    if target is None:
        assert not old.evaluated
        assert not old.unknown

        return Comparison(
            old=old,
            immediate_partial_net=old.partial_net,
            retimed=False,
            immediate_adverse_open=False,
        )

    first = first_minutes.get(key)

    if first is None:
        # За підтвердженим T115-45 відсутня одна M1.
        # Вона належить до вже невизначеної групи.
        assert target.status in UNKNOWN
        assert old.unknown

        return Comparison(
            old=old,
            immediate_partial_net=old.partial_net,
            retimed=False,
            immediate_adverse_open=False,
        )

    assert first.at == target.activation_at

    if not first.touches_be:
        return Comparison(
            old=old,
            immediate_partial_net=old.partial_net,
            retimed=False,
            immediate_adverse_open=False,
        )

    # Дзеркало T115-45: усі 30 нових за часом
    # контактів уже входили до 169 відомих T115-42.
    assert old.evaluated
    assert target.status in KNOWN
    assert target.first_breach_at is not None
    assert first.at < target.first_breach_at

    bar = t43.FillBar(
        at=first.at,
        open=first.opening,
        high=first.high,
        low=first.low,
    )

    immediate_net, adverse = proxy_net(
        trade,
        bar,
    )

    assert adverse == first.adverse_open

    return Comparison(
        old=old,
        immediate_partial_net=immediate_net,
        retimed=True,
        immediate_adverse_open=adverse,
    )


def _fmt(value: float) -> str:
    """Форматувати результат зі знаком."""
    return f"{value:+.2f}"


def _describe(
    period: str,
    side: str,
    rows: list[Comparison],
) -> None:
    """Порівняти дві часові моделі на тих самих угодах."""
    known = [row for row in rows if row.old.evaluated]

    unknown = [row for row in rows if row.old.unknown]

    retimed = [row for row in rows if row.retimed]

    assert all(row.old.evaluated for row in retimed)

    baseline = math.fsum(row.old.baseline_net for row in rows)

    lagged_net = math.fsum(row.old.partial_net for row in rows)

    immediate_net = math.fsum(row.immediate_partial_net for row in rows)

    lagged_delta = math.fsum(row.old_delta for row in known)

    immediate_delta = math.fsum(row.new_delta for row in known)

    timing_delta = math.fsum(row.timing_delta for row in rows)

    assert math.isclose(
        lagged_net - baseline,
        lagged_delta,
        abs_tol=EPS,
    )

    assert math.isclose(
        immediate_net - baseline,
        immediate_delta,
        abs_tol=EPS,
    )

    assert math.isclose(
        immediate_delta - lagged_delta,
        timing_delta,
        abs_tol=EPS,
    )

    assert math.isclose(
        timing_delta,
        math.fsum(row.timing_delta for row in retimed),
        abs_tol=EPS,
    )

    improved = [row for row in retimed if row.timing_delta > EPS]

    harmed = [row for row in retimed if row.timing_delta < -EPS]

    neutral = len(retimed) - len(improved) - len(harmed)

    benefit = math.fsum(row.timing_delta for row in improved)

    harm = math.fsum(row.timing_delta for row in harmed)

    assert math.isclose(
        benefit + harm,
        timing_delta,
        abs_tol=EPS,
    )

    adverse = sum(row.immediate_adverse_open for row in retimed)

    base_losses = sum(row.old.baseline_net < -EPS for row in retimed)

    base_nonlosses = len(retimed) - base_losses

    print(
        f"TIMING_PAIRED|PERIOD={period}|SIDE={side}|"
        f"TRADES={len(rows)}|"
        f"KNOWN={len(known)}|"
        f"UNKNOWN={len(unknown)}|"
        f"FIRST_M1_RETIMED={len(retimed)}|"
        f"BASE_NET040={_fmt(baseline)}|"
        f"LAGGED_PARTIAL_NET={_fmt(lagged_net)}|"
        f"IMMEDIATE_PARTIAL_NET={_fmt(immediate_net)}"
    )

    print(
        f"TIMING_DELTA|PERIOD={period}|SIDE={side}|"
        f"LAGGED_KNOWN_DELTA={_fmt(lagged_delta)}|"
        f"IMMEDIATE_KNOWN_DELTA={_fmt(immediate_delta)}|"
        f"TIMING_DIFFERENCE={_fmt(timing_delta)}"
    )

    print(
        f"TIMING_IMPACT|PERIOD={period}|SIDE={side}|"
        f"RETIME_IMPROVED={len(improved)}|"
        f"RETIME_HARMED={len(harmed)}|"
        f"RETIME_NEUTRAL={neutral}|"
        f"BENEFIT={_fmt(benefit)}|"
        f"HARM={_fmt(harm)}|"
        f"BASE_LOSSES_RETIMED={base_losses}|"
        f"BASE_NONLOSSES_RETIMED={base_nonlosses}|"
        f"FIRST_M1_ADVERSE_OPEN={adverse}"
    )

    print(f"TIMING_RECONCILIATION={period}:{side}:OK")


def _report(
    windows: list[Window],
    targets: dict[Key, Target],
    old_bars: dict,
    first_minutes: dict[Key, FirstMinute],
) -> None:
    """Звірити два варіанти з T115-43/44/45."""
    pooled: list[Comparison] = []

    for window in windows:
        rows = [
            _make_comparison(
                window.name,
                item.trade,
                targets,
                old_bars,
                first_minutes,
            )
            for item in window.entries
        ]

        (
            count,
            expected_known,
            expected_unknown,
            expected_baseline,
            expected_delta,
        ) = REFERENCE[window.name]

        assert len(rows) == count

        known = sum(row.old.evaluated for row in rows)

        unknown = sum(row.old.unknown for row in rows)

        retimed = sum(row.retimed for row in rows)

        baseline = math.fsum(row.old.baseline_net for row in rows)

        lagged_delta = math.fsum(row.old_delta for row in rows)

        assert known == expected_known
        assert unknown == expected_unknown

        assert retimed == EXPECTED_RETIMED[window.name]

        assert math.isclose(
            baseline,
            expected_baseline,
            abs_tol=EPS,
        )

        assert math.isclose(
            lagged_delta,
            expected_delta,
            abs_tol=EPS,
        )

        print(
            f"FROZEN_T115_43_MATCH={window.name}:OK|"
            f"KNOWN={known}|UNKNOWN={unknown}|"
            f"DELTA={_fmt(lagged_delta)}"
        )

        for side in (BUY, SELL):
            selected = [row for row in rows if row.old.trade.direction == side]

            _describe(
                window.name,
                side,
                selected,
            )

        _describe(
            window.name,
            "ALL",
            rows,
        )

        print(f"PERIOD_BE_TIMING_RECONCILIATION=" f"{window.name}:OK")

        pooled.extend(rows)

    assert len(pooled) == 333

    assert sum(row.old.evaluated for row in pooled) == 169

    assert sum(row.old.unknown for row in pooled) == 34

    assert sum(row.retimed for row in pooled) == 30

    assert sum(row.immediate_adverse_open for row in pooled) == 2

    assert sum(row.old.baseline_net < -EPS for row in pooled if row.retimed) == 21

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.old.trade.direction == side]

        expected_retimed = 19 if side == BUY else 11

        assert sum(row.retimed for row in selected) == expected_retimed

        _describe(
            "POOLED",
            side,
            selected,
        )

    _describe(
        "POOLED",
        "ALL",
        pooled,
    )

    assert math.isclose(
        math.fsum(row.old_delta for row in pooled),
        45.0,
        abs_tol=EPS,
    )

    print("FROZEN_T115_43_ECONOMIC_MIRROR=OK")
    print("FROZEN_T115_45_FIRST_M1_COUNTS_MIRROR=OK")
    print("FIRST_M1_RETIMED_EXISTING_CONTACTS=30")
    print("NEWLY_RESOLVED_UNCERTAIN_CONTACTS=0")
    print("UNKNOWN_BE_OUTCOMES=34")
    print("FOUR_PERIOD_BE_TIMING_SENSITIVITY=OK")
    print("IMMEDIATE_ORDER_LATENCY_ASSUMED_ZERO=True")
    print("REAL_BROKER_STOP_FILL_VERIFIED=False")
    print("POSITION_OCCUPANCY_REPLAYED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Перевірити часову чутливість без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_43_M1_BE_Paired_Economic_Audit.py",
        ROOT / "tests/roadmap115/" "T115_45_BE_First_Post_Activation_M1_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-46|TEST_ONLY|" "BE_ACTIVATION_TIMING_ECONOMIC_SENSITIVITY")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("BE_ACTIVATION=FROZEN_T115_41")
    print("BE_LEVEL_AND_COSTS=UNCHANGED_T115_43")
    print("LAGGED_M1=ACTIVATION_PLUS_1_MINUTE")
    print("IMMEDIATE_M1=ACTIVATION_TIMESTAMP")
    print("ZERO_LATENCY_IS_HYPOTHETICAL=True")
    print("THRESHOLD_OPTIMIZATION=False")

    _synthetic()

    windows = load_windows()
    history = load_history()

    targets: dict[Key, Target] = build_targets(
        windows,
        history,
    )

    grouped: dict[str, list[Target]] = {}

    for target in targets.values():
        filename = SOURCE_FILES[target.period]

        grouped.setdefault(
            filename,
            [],
        ).append(target)

    for filename, selected in grouped.items():
        read_source(
            filename,
            selected,
        )

    old_bars = fetch_old_bars(targets)
    first_minutes = read_first_minutes(targets)

    assert len(first_minutes) == 237

    assert sum(first.touches_be for first in first_minutes.values()) == 30

    assert sum(first.adverse_open for first in first_minutes.values()) == 2

    _report(
        windows,
        targets,
        old_bars,
        first_minutes,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("M1_OHLC_USED_AS_OUTCOME_PROXY_ONLY=True")
    print("broker_requests=0|" "TEST_ONLY=True|RESEARCH_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_46_BE_ACTIVATION_TIMING_" "ECONOMIC_SENSITIVITY=OK")


if __name__ == "__main__":
    main()
