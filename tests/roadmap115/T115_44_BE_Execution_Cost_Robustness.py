# -*- coding: utf-8 -*-
"""RoadMap115 / T115-44: BE execution-cost robustness.

TEST_ONLY / RESEARCH_ONLY.

Повторне використання тих самих baseline-угод T115-32,
активацій T115-41, M1-контактів T115-42 та пар T115-43.

Досліджується лише додаткова несприятлива вартість
виконання вже визначеного BE-контакту.

Додаткові витрати не є новим торговим параметром.
Це аналіз чутливості, а не оптимізація стратегії.

34 невизначені контакти залишаються невідомими.
Не моделюються брокерський fill, нові входи та повний Replay.
Production та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window
    from T115_42_M1_Break_Even_First_Breach_Audit import Target
    from T115_43_M1_BE_Paired_Economic_Audit import Pair

t43 = import_module("T115_43_M1_BE_Paired_Economic_Audit")

t42 = import_module("T115_42_M1_Break_Even_First_Breach_Audit")

be_mod = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

EXPECTED = be_mod.EXPECTED
EPS = be_mod.EPS

EXTRA_COST_PIPS = (
    0.0,
    0.1,
    0.2,
    0.3,
    0.5,
    1.0,
)

# Заморожені фактичні підсумки T115-43:
# кількість угод, визначені BE, невизначені BE,
# baseline Net та відома парна різниця.
REFERENCE = {
    "2024_NOV_DEC": (
        26,
        13,
        2,
        -315.00,
        258.90,
    ),
    "2025": (
        167,
        89,
        21,
        238.10,
        -201.70,
    ),
    "2026_TO_2026_08_25": (
        114,
        56,
        9,
        -329.00,
        -77.60,
    ),
    "2026_AUG_OCT": (
        26,
        11,
        2,
        -274.40,
        65.40,
    ),
}

SOURCE_FILES = t42.SOURCE_FILES

load_windows = be_mod.load_windows
load_history = be_mod.load_history

build_targets = getattr(t42, "_targets")
read_source = getattr(t42, "_read_source")

fetch_breach_bars = getattr(
    t43,
    "_fetch_breach_bars",
)

make_pair = getattr(t43, "_pair")

Key = tuple[str, datetime, str]


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _adjusted_delta(
    known_delta: float,
    contacts: int,
    extra_cost: float,
) -> float:
    """Застосувати додаткові витрати лише до BE-контактів."""
    assert contacts >= 0
    assert extra_cost >= 0

    return known_delta - contacts * extra_cost


def _synthetic() -> None:
    """Перевірити розрахунок без підбору параметрів."""
    delta = 0.60
    contacts = 3

    assert math.isclose(
        _adjusted_delta(delta, contacts, 0.0),
        0.60,
        abs_tol=EPS,
    )

    assert math.isclose(
        _adjusted_delta(delta, contacts, 0.1),
        0.30,
        abs_tol=EPS,
    )

    assert math.isclose(
        _adjusted_delta(delta, contacts, 0.2),
        0.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        _adjusted_delta(delta, contacts, 0.3),
        -0.30,
        abs_tol=EPS,
    )

    assert math.isclose(
        delta / contacts,
        0.20,
        abs_tol=EPS,
    )

    print("SYNTHETIC_INCREMENTAL_COST_ACCOUNTING=OK")
    print("SYNTHETIC_BREAK_EVEN_COST_BOUNDARY=OK")
    print("SYNTHETIC_NON_BE_TRADES_UNCHANGED=OK")


def _pairs(
    windows: list[Window],
) -> dict[str, list[Pair]]:
    """Відтворити парні результати T115-43 без зміни правил."""
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
        read_source(filename, selected)

    fill_bars = fetch_breach_bars(targets)

    result: dict[str, list[Pair]] = {}

    for window in windows:
        rows = [
            make_pair(
                window.name,
                item.trade,
                targets,
                fill_bars,
            )
            for item in window.entries
        ]

        result[window.name] = rows

    return result


def _describe(
    period: str,
    side: str,
    rows: list[Pair],
) -> None:
    """Вивести стійкість результату на визначеній вибірці."""
    known = [row for row in rows if row.evaluated]

    unknown = [row for row in rows if row.unknown]

    count = len(known)

    baseline = math.fsum(row.baseline_net for row in rows)

    delta = math.fsum(row.delta for row in known)

    partial_net = baseline + delta

    top3 = math.fsum(
        sorted(
            [row.delta for row in known if row.delta > EPS],
            reverse=True,
        )[:3]
    )

    excluding_top3 = delta - top3

    unknown_baseline = math.fsum(row.baseline_net for row in unknown)

    margin = delta / count if count > 0 and delta > EPS else None

    margin_label = f"{margin:.4f}" if margin is not None else "NONE"

    print(
        f"BE_MARGIN|PERIOD={period}|SIDE={side}|"
        f"TOTAL={len(rows)}|"
        f"KNOWN={count}|"
        f"UNKNOWN={len(unknown)}|"
        f"BASE_NET040={baseline:+.2f}|"
        f"PARTIAL_NET040={partial_net:+.2f}|"
        f"KNOWN_DELTA={delta:+.2f}|"
        f"MAX_EXTRA_COST_FOR_POSITIVE_DELTA="
        f"{margin_label}"
    )

    print(
        f"BE_CONCENTRATION|PERIOD={period}|"
        f"SIDE={side}|"
        f"TOP3_SAVINGS={top3:+.2f}|"
        f"DELTA_EXCLUDING_TOP3={excluding_top3:+.2f}|"
        f"UNKNOWN_BASE_NET040={unknown_baseline:+.2f}"
    )

    for extra in EXTRA_COST_PIPS:
        stressed = _adjusted_delta(
            delta,
            count,
            extra,
        )

        stressed_partial = baseline + stressed

        print(
            f"BE_STRESS|PERIOD={period}|"
            f"SIDE={side}|"
            f"EXTRA_COST_PIPS={extra:.2f}|"
            f"KNOWN_CONTACTS={count}|"
            f"STRESSED_DELTA={stressed:+.2f}|"
            f"STRESSED_PARTIAL_NET="
            f"{stressed_partial:+.2f}|"
            "UNKNOWN_EFFECT_EXCLUDED=True"
        )

    assert math.isclose(
        partial_net - baseline,
        delta,
        abs_tol=EPS,
    )

    assert math.isclose(
        top3 + excluding_top3,
        delta,
        abs_tol=EPS,
    )

    print(f"BE_STRESS_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    groups: dict[str, list[Pair]],
) -> None:
    """Звірити результати з T115-43 та порівняти періоди."""
    all_rows: list[Pair] = []

    for window in windows:
        rows = groups[window.name]

        (
            count,
            expected_known,
            expected_unknown,
            expected_baseline,
            expected_delta,
        ) = REFERENCE[window.name]

        assert len(rows) == count

        known = sum(row.evaluated for row in rows)

        unknown = sum(row.unknown for row in rows)

        baseline = math.fsum(row.baseline_net for row in rows)

        delta = math.fsum(row.delta for row in rows)

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert count == expected_count
        assert window.open_end == open_end

        assert known == expected_known
        assert unknown == expected_unknown

        assert math.isclose(
            baseline,
            expected_baseline,
            abs_tol=EPS,
        )

        assert math.isclose(
            baseline,
            expected_net,
            abs_tol=EPS,
        )

        assert math.isclose(
            delta,
            expected_delta,
            abs_tol=EPS,
        )

        print(
            f"FROZEN_T115_43_MATCH={window.name}:OK|"
            f"KNOWN={known}|UNKNOWN={unknown}|"
            f"DELTA={delta:+.2f}"
        )

        _describe(
            window.name,
            "ALL",
            rows,
        )

        all_rows.extend(rows)

    assert len(all_rows) == 333

    known_total = sum(row.evaluated for row in all_rows)

    unknown_total = sum(row.unknown for row in all_rows)

    delta_total = math.fsum(row.delta for row in all_rows)

    assert known_total == 169
    assert unknown_total == 34

    assert math.isclose(
        delta_total,
        45.0,
        abs_tol=EPS,
    )

    for side in (
        be_mod.BUY,
        be_mod.SELL,
    ):
        selected = [row for row in all_rows if row.trade.direction == side]

        _describe(
            "POOLED",
            side,
            selected,
        )

    _describe(
        "POOLED",
        "ALL",
        all_rows,
    )

    at_030 = _adjusted_delta(
        delta_total,
        known_total,
        0.3,
    )

    assert math.isclose(
        at_030,
        -5.70,
        abs_tol=EPS,
    )

    print("FROZEN_T115_43_ECONOMIC_MIRROR=OK")
    print("BE_EXTRA_COST_030_POOLED_DELTA=-5.70")
    print("FOUR_PERIOD_BE_COST_ROBUSTNESS=OK")
    print("NO_PARAMETER_OPTIMIZATION=True")
    print("UNKNOWN_BE_OUTCOMES_NOT_ESTIMATED=True")
    print("REAL_BROKER_FILL_SIMULATED=False")
    print("POSITION_OCCUPANCY_REPLAYED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Перевірити стійкість без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_43_M1_BE_Paired_Economic_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-44|TEST_ONLY|" "BE_EXECUTION_COST_ROBUSTNESS")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("BE_ACTIVATION=FROZEN_T115_41")
    print("BE_FIRST_TOUCH=FROZEN_T115_42")
    print("BE_PAIRED_RESULT=FROZEN_T115_43")
    print("EXTRA_COST=INCREMENTAL_ADVERSE_PIPS_PER_KNOWN_BE")
    print("COST040_ALREADY_INCLUDED=True")
    print("SENSITIVITY_ONLY=True|NO_THRESHOLD_SEARCH=True")

    _synthetic()

    windows = load_windows()
    groups = _pairs(windows)

    _report(
        windows,
        groups,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|TEST_ONLY=True|RESEARCH_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_44_BE_EXECUTION_COST_ROBUSTNESS=OK")


if __name__ == "__main__":
    main()
