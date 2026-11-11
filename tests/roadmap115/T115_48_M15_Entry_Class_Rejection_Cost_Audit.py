# -*- coding: utf-8 -*-
"""RoadMap115 / T115-48: M15 entry-class rejection cost.

TEST_ONLY / DATA_ONLY.

Для кожного причинного M15-класу вимірюється:
- скільки збиткових угод без BE він містить;
- скільки всіх збиткових і незбиткових угод містить;
- сумарний виграш та збиток baseline-угод;
- статична вартість виключення всього класу;
- зміна результату класу між чотирма періодами.

Статичне виключення — лише арифметична діагностика.
Нові входи, зайнятість позиції та Replay не моделюються.

BE activation і фінальний PnL — тільки outcome labels.
Класи M15 беруться з незмінного T115-47.

Production, MD7 та торгові правила не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_47_Pre_Entry_Non_BE_Loss_Anatomy import Record

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

BUY = t47.BUY
SELL = t47.SELL
EPS = t47.EPS
EXPECTED = t47.EXPECTED

CLASSES = (
    "ACTIVE_ALIGNED",
    "ACTIVE_OPPOSITE",
    "ENDING_ALIGNED",
    "ENDING_OPPOSITE",
    "NONE_NO_DIRECTION",
    "STARTING_ALIGNED",
    "STARTING_OPPOSITE",
)

# Заморожені факти з успішного T115-47:
# class -> (кількість, збиткові без BE, Net).
FROZEN_POOLED = {
    "ACTIVE_ALIGNED": (135, 29, -509.80),
    "ACTIVE_OPPOSITE": (35, 11, -103.20),
    "ENDING_ALIGNED": (72, 17, -31.00),
    "ENDING_OPPOSITE": (15, 4, -142.20),
    "NONE_NO_DIRECTION": (34, 9, 158.50),
    "STARTING_ALIGNED": (20, 4, -63.50),
    "STARTING_OPPOSITE": (22, 9, 10.90),
}

PERIODS = (
    "2024_NOV_DEC",
    "2025",
    "2026_TO_2026_08_25",
    "2026_AUG_OCT",
)


@dataclass(frozen=True, slots=True)
class Metrics:
    """Агрегати незмінних baseline-угод."""

    total: int
    no_be_losses: int
    all_losses: int
    net: float
    loss_net: float
    nonloss_net: float


def _sha(path: Path) -> str:
    """Обчислити контрольний SHA256."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _metrics(rows: list[Record]) -> Metrics:
    """Порахувати витрати і прибутки без нової торгової логіки."""
    losses = [row for row in rows if row.loss]

    nonlosses = [row for row in rows if not row.loss]

    loss_net = math.fsum(row.net for row in losses)

    nonloss_net = math.fsum(row.net for row in nonlosses)

    net = math.fsum(row.net for row in rows)

    assert math.isclose(
        loss_net + nonloss_net,
        net,
        abs_tol=EPS,
    )

    return Metrics(
        total=len(rows),
        no_be_losses=sum(row.cohort == "NO_BE_LOSS" for row in rows),
        all_losses=len(losses),
        net=net,
        loss_net=loss_net,
        nonloss_net=nonloss_net,
    )


def _synthetic() -> None:
    """Контроль ціни відхилення всього класу."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    samples = [
        t47.Record(
            "TEST",
            BUY,
            at,
            "CLASS_A",
            False,
            -20.0,
        ),
        t47.Record(
            "TEST",
            BUY,
            at,
            "CLASS_A",
            True,
            50.0,
        ),
        t47.Record(
            "TEST",
            BUY,
            at,
            "CLASS_B",
            False,
            -3.0,
        ),
        t47.Record(
            "TEST",
            BUY,
            at,
            "CLASS_B",
            True,
            8.0,
        ),
    ]

    group_a = _metrics([row for row in samples if row.m15_class == "CLASS_A"])

    group_b = _metrics([row for row in samples if row.m15_class == "CLASS_B"])

    whole = _metrics(samples)

    assert group_a.total == 2
    assert group_a.no_be_losses == 1
    assert group_a.all_losses == 1

    assert math.isclose(
        group_a.net,
        30.0,
        abs_tol=EPS,
    )

    # Відхилення класу A прибирає збиток 20,
    # але втрачає прибуток 50.
    assert math.isclose(
        -group_a.net,
        -30.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        group_b.net,
        5.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        group_a.net + group_b.net,
        whole.net,
        abs_tol=EPS,
    )

    print("SYNTHETIC_LOSS_PROFIT_ACCOUNTING=OK")
    print("SYNTHETIC_REJECTION_OPPORTUNITY_COST=OK")
    print("SYNTHETIC_CLASS_PARTITION=OK")


def _fmt_rate(
    numerator: int,
    denominator: int,
) -> str:
    """Відсоток без ділення на нуль."""
    if denominator == 0:
        return "NA"

    return f"{100.0 * numerator / denominator:.2f}"


def _fmt_lift(
    group: Metrics,
    other: Metrics,
) -> str:
    """Відносна частота NO_BE_LOSS щодо інших класів."""
    if group.total == 0 or other.total == 0:
        return "NA"

    other_rate = other.no_be_losses / other.total

    if other_rate == 0:
        return "NA"

    group_rate = group.no_be_losses / group.total

    return f"{group_rate / other_rate:.3f}"


def _describe(
    period: str,
    side: str,
    rows: list[Record],
) -> None:
    """Виміряти статистичну ціну відхилення M15-класу."""
    total = _metrics(rows)

    print(
        f"CLASS_BASE|PERIOD={period}|SIDE={side}|"
        f"TOTAL={total.total}|"
        f"NO_BE_LOSSES={total.no_be_losses}|"
        f"ALL_LOSSES={total.all_losses}|"
        f"NET040={total.net:+.2f}"
    )

    class_totals: list[Metrics] = []

    for name in CLASSES:
        selected = [row for row in rows if row.m15_class == name]

        other = [row for row in rows if row.m15_class != name]

        group = _metrics(selected)
        complement = _metrics(other)

        assert group.total + complement.total == total.total

        assert group.no_be_losses + complement.no_be_losses == total.no_be_losses

        assert math.isclose(
            group.net + complement.net,
            total.net,
            abs_tol=EPS,
        )

        class_totals.append(group)

        print(
            f"CLASS_COST|PERIOD={period}|SIDE={side}|"
            f"CLASS={name}|"
            f"COUNT={group.total}|"
            f"NO_BE_LOSS={group.no_be_losses}|"
            f"ALL_LOSS={group.all_losses}|"
            f"NO_BE_LOSS_RATE_PCT="
            f"{_fmt_rate(group.no_be_losses, group.total)}|"
            f"REST_NO_BE_LOSS_RATE_PCT="
            f"{_fmt_rate(complement.no_be_losses, complement.total)}|"
            f"RELATIVE_RISK={_fmt_lift(group, complement)}|"
            f"LOSS_NET040={group.loss_net:+.2f}|"
            f"NONLOSS_NET040={group.nonloss_net:+.2f}|"
            f"CLASS_NET040={group.net:+.2f}|"
            f"STATIC_REJECT_DELTA={-group.net:+.2f}"
        )

    assert sum(group.total for group in class_totals) == total.total

    assert sum(group.no_be_losses for group in class_totals) == total.no_be_losses

    assert math.isclose(
        math.fsum(group.net for group in class_totals),
        total.net,
        abs_tol=EPS,
    )

    print(f"CLASS_COST_RECONCILIATION=" f"{period}:{side}:OK")


def _cross_period(
    by_period: dict[str, list[Record]],
    side: str,
) -> None:
    """Перевірити стабільність знака Net у чотирьох періодах."""
    for name in CLASSES:
        positive = 0
        negative = 0
        zero = 0
        absent = 0

        fragments: list[str] = []

        for period in PERIODS:
            selected = [
                row
                for row in by_period[period]
                if row.m15_class == name and (side == "ALL" or row.direction == side)
            ]

            result = _metrics(selected)

            if result.total == 0:
                absent += 1
                sign = "ABSENT"
            elif result.net > EPS:
                positive += 1
                sign = "POSITIVE"
            elif result.net < -EPS:
                negative += 1
                sign = "NEGATIVE"
            else:
                zero += 1
                sign = "ZERO"

            fragments.append(f"{period}:{result.total}:" f"{result.net:+.2f}:{sign}")

        assert positive + negative + zero + absent == len(PERIODS)

        print(
            f"CROSS_PERIOD_CLASS|SIDE={side}|"
            f"CLASS={name}|POSITIVE={positive}|"
            f"NEGATIVE={negative}|ZERO={zero}|"
            f"ABSENT={absent}|"
            f"PERIODS={';'.join(fragments)}"
        )

    print(f"CROSS_PERIOD_CLASS_RECONCILIATION=" f"{side}:OK")


def _report() -> None:
    """Повторити frozen baseline і перевірити всі M15-класи."""
    windows = t47.load_windows()
    history = t47.load_history()

    assert len(windows) == 4
    assert len(history) == 4

    by_period: dict[str, list[Record]] = {}
    pooled: list[Record] = []

    for window in windows:
        rows = t47._collect(
            window,
            history[window.name],
        )

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        actual = _metrics(rows)

        assert actual.total == expected_count
        assert window.open_end == open_end

        assert math.isclose(
            actual.net,
            expected_net,
            abs_tol=EPS,
        )

        by_period[window.name] = rows
        pooled.extend(rows)

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={actual.total}|"
            f"NET040={actual.net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            selected = [row for row in rows if row.direction == side]

            _describe(
                window.name,
                side,
                selected,
            )

        print(f"PERIOD_CLASS_COST_RECONCILIATION=" f"{window.name}:OK")

    assert set(by_period) == set(PERIODS)

    overall = _metrics(pooled)

    assert overall.total == 333
    assert overall.no_be_losses == 83
    assert overall.all_losses == 200

    assert math.isclose(
        overall.net,
        -680.30,
        abs_tol=EPS,
    )

    for name, expected in FROZEN_POOLED.items():
        selected = [row for row in pooled if row.m15_class == name]

        observed = _metrics(selected)

        expected_count, expected_bad, expected_net = expected

        assert observed.total == expected_count
        assert observed.no_be_losses == expected_bad

        assert math.isclose(
            observed.net,
            expected_net,
            abs_tol=EPS,
        )

    assert all(row.m15_class in CLASSES for row in pooled)

    print("T115_47_M15_CLASS_EXACT_MIRROR=OK")

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.direction == side]

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

    for side in (BUY, SELL, "ALL"):
        _cross_period(
            by_period,
            side,
        )

    no_be_loss_net = math.fsum(row.net for row in pooled if row.cohort == "NO_BE_LOSS")

    no_be_nonloss_net = math.fsum(
        row.net for row in pooled if row.cohort == "NO_BE_NONLOSS"
    )

    assert math.isclose(
        no_be_loss_net,
        -1947.10,
        abs_tol=EPS,
    )

    assert math.isclose(
        no_be_nonloss_net,
        91.10,
        abs_tol=EPS,
    )

    print("FROZEN_NO_BE_COHORT_RECONCILIATION=OK")
    print("FOUR_PERIOD_M15_CLASS_COST_AUDIT=OK")
    print("STATIC_REJECTION_IS_NOT_REPLAY=True")
    print("NO_ENTRY_GATE_CREATED=True")
    print("NO_THRESHOLD_SEARCH=True")
    print("FUTURE_LABELS_FOR_ANALYSIS_ONLY=True")


def main() -> None:
    """Дослідити вартість відхилення без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-48|TEST_ONLY|" "M15_ENTRY_CLASS_REJECTION_COST_AUDIT")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("M15_ENTRY_CLASS=FROZEN_T115_47")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("STATIC_REJECT_ACCOUNTING_ONLY=True")
    print("POSITION_OCCUPANCY_NOT_REPLAYED=True")

    _synthetic()
    _report()

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_48_M15_ENTRY_CLASS_" "REJECTION_COST_AUDIT=OK")


if __name__ == "__main__":
    main()
