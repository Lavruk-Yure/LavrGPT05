# -*- coding: utf-8 -*-
"""RoadMap115 / T115-45: BE first post-activation M1 audit.

TEST_ONLY / DATA_ONLY.

Аудит першої M1 з timestamp == BE activation_at.
Саме ця хвилина не перевірялася в T115-42.

Активації та подальші M1-контакти не змінюються.
Використовується заморожений baseline T115-32.

M1 OHLC після активації — лише outcome label.
Немає припущення про миттєве розміщення SL,
послідовність intrabar-подій або broker fill.

Без змін production, MD7 чи параметрів торгівлі.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_42_M1_Break_Even_First_Breach_Audit import Target

t41 = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

t42 = import_module("T115_42_M1_Break_Even_First_Breach_Audit")

t36 = import_module("T115_36_First_H1_Negative_Early_Exit_Counterfactual")

BUY = t41.BUY
SELL = t41.SELL
COST = t41.COST
PIP = t41.PIP
EPS = t41.EPS

SOURCE_FILES = t42.SOURCE_FILES
M1_DIRECTORY = t42.M1_DIRECTORY
M1_HEADER = t42.M1_HEADER

KNOWN = (
    t42.BREACH_NO_GAP,
    t42.BREACH_BEFORE_GAP,
)

UNKNOWN = (
    t42.GAP_BEFORE_BREACH,
    t42.GAP_NO_BREACH,
)

NO_TOUCH = t42.NO_BREACH

parse_timestamp = getattr(t36, "_timestamp")
build_targets = getattr(t42, "_targets")
read_source = getattr(t42, "_read_source")

load_windows = t41.load_windows
load_history = t41.load_history

Key = tuple[str, datetime, str]


@dataclass(frozen=True, slots=True)
class FirstMinute:
    """Фактично наявна перша M1 після завершення H1."""

    at: datetime
    opening: float
    high: float
    low: float
    touches_be: bool
    adverse_open: bool


def _sha(path: Path) -> str:
    """Контроль незмінності опорних файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _classify(
    direction: str,
    entry_price: float,
    opening: float,
    high: float,
    low: float,
) -> tuple[bool, bool]:
    """Визначити контакт BE без симуляції виконання."""
    assert all(
        math.isfinite(value) and value > 0
        for value in (
            entry_price,
            opening,
            high,
            low,
        )
    )

    assert low <= opening <= high

    if direction == BUY:
        level = entry_price + COST * PIP

        touch = low <= level + EPS * PIP
        adverse = opening < level - EPS * PIP

    else:
        assert direction == SELL

        level = entry_price - COST * PIP

        touch = high >= level - EPS * PIP
        adverse = opening > level + EPS * PIP

    assert not adverse or touch

    return touch, adverse


def _synthetic() -> None:
    """Перевірити BUY, SELL та відкриття за BE-рівнем."""
    touch, adverse = _classify(
        BUY,
        1.1000,
        1.1005,
        1.1008,
        1.1000,
    )

    assert touch
    assert not adverse

    touch, adverse = _classify(
        BUY,
        1.1000,
        1.0995,
        1.0998,
        1.0992,
    )

    assert touch
    assert adverse

    touch, adverse = _classify(
        BUY,
        1.1000,
        1.1010,
        1.1015,
        1.1005,
    )

    assert not touch
    assert not adverse

    touch, adverse = _classify(
        SELL,
        1.1000,
        1.0995,
        1.1001,
        1.0990,
    )

    assert touch
    assert not adverse

    touch, adverse = _classify(
        SELL,
        1.1000,
        1.1005,
        1.1010,
        1.1002,
    )

    assert touch
    assert adverse

    touch, adverse = _classify(
        SELL,
        1.1000,
        1.0985,
        1.0990,
        1.0980,
    )

    assert not touch
    assert not adverse

    print("SYNTHETIC_FIRST_M1_BUY_SELL_CONTACT=OK")
    print("SYNTHETIC_ADVERSE_M1_OPEN_CLASSIFICATION=OK")
    print("SYNTHETIC_NO_CONTACT_CLASSIFICATION=OK")


def _read_first_minutes(
    targets: dict[Key, Target],
) -> dict[Key, FirstMinute]:
    """Знайти тільки M1 з точним часом завершення H1."""
    grouped: dict[str, dict[datetime, list[Target]]] = {}

    for target in targets.values():
        filename = SOURCE_FILES[target.period]

        requested = grouped.setdefault(
            filename,
            {},
        )

        requested.setdefault(
            target.activation_at,
            [],
        ).append(target)

    results: dict[Key, FirstMinute] = {}

    for filename, requested in grouped.items():
        path = M1_DIRECTORY / filename

        assert path.is_file()

        seen: set[datetime] = set()

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            reader = csv.reader(stream)

            assert tuple(next(reader)) == M1_HEADER

            for cells in reader:
                assert len(cells) == len(M1_HEADER)

                at = parse_timestamp(cells[0])
                matching = requested.get(at)

                if matching is None:
                    continue

                assert at not in seen
                seen.add(at)

                opening = float(cells[1])
                high = float(cells[2])
                low = float(cells[3])

                for target in matching:
                    assert target.activation_at == at
                    assert at < target.start_at
                    assert at < target.exit_at

                    touch, adverse = _classify(
                        target.trade.direction,
                        target.trade.entry_price,
                        opening,
                        high,
                        low,
                    )

                    assert target.key not in results

                    results[target.key] = FirstMinute(
                        at=at,
                        opening=opening,
                        high=high,
                        low=low,
                        touches_be=touch,
                        adverse_open=adverse,
                    )

        missing = len(requested) - len(seen)

        assert missing >= 0

        print(
            f"FIRST_M1_SOURCE|FILE={filename}|"
            f"REQUESTED_TIMESTAMPS={len(requested)}|"
            f"FOUND_TIMESTAMPS={len(seen)}|"
            f"MISSING_TIMESTAMPS={missing}|"
            "FORWARD_FILL=False"
        )

    assert len(results) <= len(targets)

    return results


def _describe(
    period: str,
    side: str,
    selected: list[Target],
    first: dict[Key, FirstMinute],
) -> None:
    """Зіставити першу хвилину з результатами T115-42."""
    present = [item for item in selected if item.key in first]

    missing = len(selected) - len(present)

    touches = [item for item in present if first[item.key].touches_be]

    no_touches = len(present) - len(touches)

    adverse = sum(first[item.key].adverse_open for item in present)

    touch_losses = sum(float(item.trade.pips) - COST < -EPS for item in touches)

    touch_nonlosses = len(touches) - touch_losses

    known = [item for item in selected if item.status in KNOWN]

    uncertain = [item for item in selected if item.status in UNKNOWN]

    no_touch_old = [item for item in selected if item.status == NO_TOUCH]

    assert len(known) + len(uncertain) + len(no_touch_old) == len(selected)

    assert len(present) + missing == len(selected)

    print(
        f"FIRST_M1_COVERAGE|PERIOD={period}|"
        f"SIDE={side}|"
        f"ACTIVATED={len(selected)}|"
        f"PRESENT={len(present)}|"
        f"MISSING={missing}|"
        f"TOUCH={len(touches)}|"
        f"NO_TOUCH={no_touches}|"
        f"ADVERSE_OPEN={adverse}"
    )

    print(
        f"FIRST_M1_OUTCOME|PERIOD={period}|"
        f"SIDE={side}|"
        f"TOUCH_BASE_LOSS={touch_losses}|"
        f"TOUCH_BASE_NONLOSS={touch_nonlosses}|"
        "STOP_FILL_VERIFIED=False"
    )

    for label, cohort in (
        ("OLD_KNOWN", known),
        ("OLD_UNCERTAIN", uncertain),
        ("OLD_NO_TOUCH", no_touch_old),
    ):
        first_touch = sum(
            item.key in first and first[item.key].touches_be for item in cohort
        )

        first_missing = sum(item.key not in first for item in cohort)

        first_clean = len(cohort) - first_touch - first_missing

        assert first_touch + first_missing + first_clean == len(cohort)

        print(
            f"FIRST_M1_CROSS_TAB|PERIOD={period}|"
            f"SIDE={side}|OLD={label}|"
            f"COUNT={len(cohort)}|"
            f"FIRST_TOUCH={first_touch}|"
            f"FIRST_MISSING={first_missing}|"
            f"FIRST_CLEAN={first_clean}"
        )

    known_retimed = sum(
        first[item.key].touches_be for item in known if item.key in first
    )

    known_with_missing_first = sum(item.key not in first for item in known)

    print(
        f"FIRST_M1_IMPACT|PERIOD={period}|"
        f"SIDE={side}|"
        f"OLD_KNOWN_RETIMED={known_retimed}|"
        f"OLD_KNOWN_FIRST_MINUTE_UNKNOWN="
        f"{known_with_missing_first}|"
        "OLD_BE_ECONOMIC_RESULT_NOT_RECALCULATED=True"
    )

    print(f"FIRST_M1_RECONCILIATION={period}:{side}:OK")


def _report(
    targets: dict[Key, Target],
    first: dict[Key, FirstMinute],
) -> None:
    """Звірити всі 238 активацій і класи T115-42."""
    assert len(targets) == 238

    items = list(targets.values())

    expected_counts = {
        "2024_NOV_DEC": (9, 10),
        "2025": (69, 58),
        "2026_TO_2026_08_25": (35, 39),
        "2026_AUG_OCT": (6, 12),
    }

    for period, (buy_count, sell_count) in expected_counts.items():
        for side, expected in (
            (BUY, buy_count),
            (SELL, sell_count),
        ):
            selected = [
                item
                for item in items
                if item.period == period and item.trade.direction == side
            ]

            assert len(selected) == expected

            _describe(
                period,
                side,
                selected,
                first,
            )

        print(f"PERIOD_FIRST_M1_RECONCILIATION={period}:OK")

    for side in (BUY, SELL):
        selected = [item for item in items if item.trade.direction == side]

        assert len(selected) == 119

        _describe(
            "POOLED",
            side,
            selected,
            first,
        )

    _describe(
        "POOLED",
        "ALL",
        items,
        first,
    )

    known = sum(item.status in KNOWN for item in items)

    unknown = sum(item.status in UNKNOWN for item in items)

    no_touch = sum(item.status == NO_TOUCH for item in items)

    assert (known, unknown, no_touch) == (169, 34, 35)

    print("T115_42_FROZEN_COUNTS=169,34,35")
    print("FOUR_PERIOD_FIRST_M1_BOUNDARY_AUDIT=OK")
    print("FIRST_M1_OUTCOME_ONLY=True")
    print("INTRAMINUTE_STOP_ORDER_UNVERIFIED=True")
    print("PRIOR_T115_43_RESULT_UNCHANGED=True")
    print("NEW_BE_RULE_CREATED=False")


def main() -> None:
    """Виконати незалежний аудит часової межі BE."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_42_M1_Break_Even_First_Breach_Audit.py",
        ROOT / "tests/roadmap115/" "T115_43_M1_BE_Paired_Economic_Audit.py",
        ROOT / "tests/roadmap115/" "T115_44_BE_Execution_Cost_Robustness.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-45|TEST_ONLY|" "BE_FIRST_POST_ACTIVATION_M1_AUDIT")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("ACTIVATION=FROZEN_T115_41")
    print("LATER_M1=FROZEN_T115_42")
    print("FIRST_M1_TIMESTAMP=ACTIVATION_AT")
    print("M1_PRICES_USED_ONLY_AS_OUTCOME_LABELS=True")
    print("NO_BROKER_EXECUTION_ASSUMPTION=True")

    _synthetic()

    windows = load_windows()
    history = load_history()

    targets = build_targets(
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

    first = _read_first_minutes(targets)

    _report(
        targets,
        first,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("broker_requests=0|" "TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_45_BE_FIRST_POST_ACTIVATION_M1_AUDIT=OK")


if __name__ == "__main__":
    main()
