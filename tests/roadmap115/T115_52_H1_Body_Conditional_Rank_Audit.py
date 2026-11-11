# -*- coding: utf-8 -*-
"""RoadMap115 / T115-52: H1 body conditional rank audit.

TEST_ONLY / DATA_ONLY.

Мета: перевірити, чи зберігається слабке рангове
розділення NO_BE_LOSS за напрямленим тілом останньої
завершеної H1 після контролю періоду, напрямку угоди
та причинного M15 entry-класу.

Порівнюються три рівні:
- усі угоди разом;
- тільки пари всередині period + side;
- тільки пари всередині period + side + M15 class.

Умовний AUC зважується на кількість порівнюваних пар,
а не на кількість груп.

Групи з одним типом outcome не отримують вигаданий AUC.
Для них окремо звітується втрата охоплення.

Тільки завершені H1, без look-ahead.
Жодних нових entry-gates, порогів або Replay-змін.

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
    from T115_47_Pre_Entry_Non_BE_Loss_Anatomy import Record
    from T115_51_Completed_H1_Pre_Entry_Rank_Audit import H1Features

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

t50 = import_module("T115_50_M15_Pre_Entry_Rank_Separation_Audit")

t51 = import_module("T115_51_Completed_H1_Pre_Entry_Rank_Audit")

BUY = t47.BUY
SELL = t47.SELL

EPS = t47.EPS
EXPECTED = t47.EXPECTED
PERIODS = t51.PERIODS

collect_records = getattr(t47, "_collect")
collect_h1 = getattr(t51, "_collect_features")
rank_auc = getattr(t50, "_auc")

GLOBAL = "GLOBAL"
PERIOD_SIDE = "PERIOD_SIDE"
PERIOD_SIDE_CLASS = "PERIOD_SIDE_CLASS"

PARTITIONS = (
    GLOBAL,
    PERIOD_SIDE,
    PERIOD_SIDE_CLASS,
)

Key = tuple[str, datetime, str]
GroupKey = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankSummary:
    """Умовна рангова метрика з явним охопленням."""

    total: int
    losses: int
    others: int
    strata: int
    eligible_strata: int
    comparable_pairs: int
    covered_losses: int
    covered_others: int
    auc: float | None


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _key(row: Record) -> Key:
    """Стабільний ключ baseline-угоди."""
    return row.period, row.entry_at, row.direction


def _group_key(
    row: Record,
    partition: str,
) -> GroupKey:
    """Сформувати групу тільки за pre-entry-ознаками."""
    if partition == GLOBAL:
        return ("ALL",)

    if partition == PERIOD_SIDE:
        return row.period, row.direction

    assert partition == PERIOD_SIDE_CLASS

    return (
        row.period,
        row.direction,
        row.m15_class,
    )


def _calculate(
    rows: list[Record],
    values: dict[Key, H1Features | None],
    partition: str,
    show_strata: bool = False,
) -> RankSummary:
    """Обчислити AUC лише всередині дозволених груп."""
    assert partition in PARTITIONS

    grouped: dict[GroupKey, list[Record]] = {}

    for row in rows:
        assert _key(row) in values

        grouped.setdefault(
            _group_key(row, partition),
            [],
        ).append(row)

    total_losses = sum(row.cohort == "NO_BE_LOSS" for row in rows)

    total_others = len(rows) - total_losses

    weighted_wins: list[float] = []

    comparable_pairs = 0
    eligible_strata = 0
    covered_losses = 0
    covered_others = 0

    for group_key, members in sorted(grouped.items()):
        losses: list[float] = []
        others: list[float] = []

        for row in members:
            feature = values[_key(row)]

            # За замороженим T115-51 усі 333 H1 свіжі.
            assert feature is not None

            body = feature.directional_body

            assert math.isfinite(body)

            if row.cohort == "NO_BE_LOSS":
                losses.append(body)
            else:
                others.append(body)

        pairs = len(losses) * len(others)

        if pairs == 0:
            if show_strata:
                print(
                    f"BODY_STRATUM|PARTITION={partition}|"
                    f"KEY={':'.join(group_key)}|"
                    f"LOSS={len(losses)}|"
                    f"OTHER={len(others)}|"
                    "PAIRS=0|AUC=NA"
                )

            continue

        auc = rank_auc(losses, others)

        assert auc is not None
        assert 0.0 <= auc <= 1.0

        weighted_wins.append(auc * pairs)

        comparable_pairs += pairs
        eligible_strata += 1

        covered_losses += len(losses)
        covered_others += len(others)

        if show_strata:
            print(
                f"BODY_STRATUM|PARTITION={partition}|"
                f"KEY={':'.join(group_key)}|"
                f"LOSS={len(losses)}|"
                f"OTHER={len(others)}|"
                f"PAIRS={pairs}|"
                f"AUC_LOSS_HIGH={auc:.4f}"
            )

    assert covered_losses <= total_losses
    assert covered_others <= total_others

    if comparable_pairs == 0:
        assert not weighted_wins
        combined_auc = None
    else:
        combined_auc = math.fsum(weighted_wins) / comparable_pairs

        assert 0.0 <= combined_auc <= 1.0

    return RankSummary(
        total=len(rows),
        losses=total_losses,
        others=total_others,
        strata=len(grouped),
        eligible_strata=eligible_strata,
        comparable_pairs=comparable_pairs,
        covered_losses=covered_losses,
        covered_others=covered_others,
        auc=combined_auc,
    )


def _synthetic() -> None:
    """Перевірити змішування груп і зважування пар."""
    start = datetime(2025, 4, 7, 12, tzinfo=UTC)

    rows: list[Record] = []
    values: dict[Key, H1Features | None] = {}

    def add(
        m15_class: str,
        loss: bool,
        body: float,
    ) -> None:
        """Додати синтетичну угоду та її pre-entry H1."""
        at = start + timedelta(minutes=15 * len(rows))

        row = t47.Record(
            period="SYNTHETIC",
            direction=BUY,
            entry_at=at,
            m15_class=m15_class,
            activated=not loss,
            net=-20.0 if loss else 20.0,
        )

        rows.append(row)

        values[_key(row)] = t51.H1Features(
            directional_body=body,
            range_pips=10.0,
            directional_close_location=0.5,
        )

    # У HIGH усі збиткові мають менше тіло,
    # ніж інші угоди цього самого класу.
    for _ in range(5):
        add("HIGH", True, 100.0)

    add("HIGH", False, 101.0)

    # У LOW ситуація така сама.
    add("LOW", True, 0.0)

    for _ in range(5):
        add("LOW", False, 1.0)

    global_result = _calculate(
        rows,
        values,
        GLOBAL,
    )

    conditional = _calculate(
        rows,
        values,
        PERIOD_SIDE_CLASS,
    )

    assert global_result.total == 12
    assert global_result.losses == 6
    assert global_result.others == 6

    assert global_result.comparable_pairs == 36

    assert global_result.auc is not None

    # Міжкласове змішування перевертає результат.
    assert math.isclose(
        global_result.auc,
        25.0 / 36.0,
        abs_tol=EPS,
    )

    assert conditional.auc is not None

    assert math.isclose(
        conditional.auc,
        0.0,
        abs_tol=EPS,
    )

    assert conditional.comparable_pairs == 10
    assert conditional.eligible_strata == 2

    # Клас без другого типу outcome не має AUC.
    add("ONLY_LOSS", True, 3.0)

    with_sparse = _calculate(
        rows,
        values,
        PERIOD_SIDE_CLASS,
    )

    assert with_sparse.auc is not None

    assert math.isclose(
        with_sparse.auc,
        conditional.auc,
        abs_tol=EPS,
    )

    assert with_sparse.covered_losses == 6
    assert with_sparse.losses == 7
    assert with_sparse.strata == 3
    assert with_sparse.eligible_strata == 2

    print("SYNTHETIC_CONDITIONAL_AUC_WEIGHTING=OK")
    print("SYNTHETIC_CROSS_CLASS_CONFOUNDING=OK")
    print("SYNTHETIC_SINGLE_LABEL_STRATUM_EXCLUDED=OK")
    print("SYNTHETIC_COVERAGE_ACCOUNTING=OK")


def _fmt(value: float | None) -> str:
    """Вивести рангову метрику або NA."""
    if value is None:
        return "NA"

    return f"{value:.4f}"


def _describe(
    scope: str,
    rows: list[Record],
    values: dict[Key, H1Features | None],
    partition: str,
    show_strata: bool = False,
) -> RankSummary:
    """Вивести AUC та знаменники порівняння."""
    summary = _calculate(
        rows,
        values,
        partition,
        show_strata,
    )

    reversed_auc = 1.0 - summary.auc if summary.auc is not None else None

    print(
        f"H1_BODY_CONDITIONAL|SCOPE={scope}|"
        f"PARTITION={partition}|"
        f"TOTAL={summary.total}|"
        f"LOSS={summary.losses}|"
        f"OTHER={summary.others}|"
        f"STRATA={summary.strata}|"
        f"ELIGIBLE_STRATA={summary.eligible_strata}|"
        f"PAIRS={summary.comparable_pairs}|"
        f"COVERED_LOSS={summary.covered_losses}|"
        f"COVERED_OTHER={summary.covered_others}|"
        f"EXCLUDED_LOSS="
        f"{summary.losses - summary.covered_losses}|"
        f"EXCLUDED_OTHER="
        f"{summary.others - summary.covered_others}|"
        f"AUC_LOSS_HIGH={_fmt(summary.auc)}|"
        f"AUC_LOSS_LOW={_fmt(reversed_auc)}"
    )

    return summary


def _report(
    by_period: dict[str, list[Record]],
    values: dict[Key, H1Features | None],
    statuses: dict[Key, str],
) -> None:
    """Зіставити загальний та умовний H1 AUC."""
    assert set(by_period) == set(PERIODS)

    pooled: list[Record] = []

    for period in PERIODS:
        records = by_period[period]

        expected_count, expected_net, _, _ = EXPECTED[period]

        assert len(records) == expected_count

        net = math.fsum(row.net for row in records)

        assert math.isclose(
            net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={period}:OK|"
            f"CLOSED={len(records)}|"
            f"NET040={net:+.2f}"
        )

        for side in (BUY, SELL):
            selected = [row for row in records if row.direction == side]

            _describe(
                f"{period}:{side}",
                selected,
                values,
                GLOBAL,
            )

            _describe(
                f"{period}:{side}",
                selected,
                values,
                PERIOD_SIDE_CLASS,
            )

        pooled.extend(records)

        print(f"PERIOD_H1_BODY_CONDITIONAL=" f"{period}:OK")

    assert len(pooled) == 333
    assert len(values) == 333
    assert len(statuses) == 333

    assert all(status == t51.FRESH for status in statuses.values())

    assert sum(row.cohort == "NO_BE_LOSS" for row in pooled) == 83

    assert sum(row.cohort != "NO_BE_LOSS" for row in pooled) == 250

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.direction == side]

        for partition in PARTITIONS:
            _describe(
                f"POOLED:{side}",
                selected,
                values,
                partition,
            )

    global_summary = _describe(
        "POOLED:ALL",
        pooled,
        values,
        GLOBAL,
    )

    period_summary = _describe(
        "POOLED:ALL",
        pooled,
        values,
        PERIOD_SIDE,
    )

    conditional_summary = _describe(
        "POOLED:ALL",
        pooled,
        values,
        PERIOD_SIDE_CLASS,
        show_strata=True,
    )

    assert global_summary.auc is not None

    assert math.isclose(
        global_summary.auc,
        0.4195,
        abs_tol=0.0001,
    )

    assert period_summary.auc is not None

    assert conditional_summary.comparable_pairs <= period_summary.comparable_pairs

    assert period_summary.comparable_pairs <= global_summary.comparable_pairs

    assert global_summary.comparable_pairs == 83 * 250

    assert math.isclose(
        math.fsum(row.net for row in pooled),
        -680.30,
        abs_tol=EPS,
    )

    print("FROZEN_T115_51_GLOBAL_H1_BODY_AUC_MIRROR=OK")
    print("H1_CONDITIONAL_PAIR_WEIGHTING=OK")
    print("M15_CLASS_USED_AS_CAUSAL_STRATIFICATION_ONLY=True")
    print("SINGLE_LABEL_STRATA_NOT_IMPUTED=True")
    print("FOUR_PERIOD_H1_BODY_CONDITIONAL_AUDIT=OK")
    print("AUC_IS_NOT_TRADING_RULE=True")
    print("NO_ENTRY_GATE_CREATED=True")
    print("NO_THRESHOLD_OPTIMIZATION=True")


def main() -> None:
    """Виконати умовний H1-аудит без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        ROOT / "tests/roadmap115/" "T115_50_M15_Pre_Entry_Rank_Separation_Audit.py",
        ROOT / "tests/roadmap115/" "T115_51_Completed_H1_Pre_Entry_Rank_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-52|TEST_ONLY|" "H1_BODY_CONDITIONAL_RANK_AUDIT")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("FEATURE=FROZEN_T115_51_H1_DIRECTIONAL_BODY")
    print("OUTCOME=FROZEN_T115_47_NO_BE_LOSS")
    print("CONDITIONS=PERIOD_SIDE_M15_CLASS")
    print("NO_THRESHOLD_SEARCH=True|NO_REPLAY_CHANGE=True")

    _synthetic()

    windows = t47.load_windows()
    history = t47.load_history()

    assert len(windows) == 4
    assert len(history) == 4

    by_period: dict[str, list[Record]] = {}

    for window in windows:
        assert window.name not in by_period

        records = collect_records(
            window,
            history[window.name],
        )

        assert len(records) == EXPECTED[window.name][0]

        by_period[window.name] = records

    values, statuses = collect_h1(
        by_period,
        history,
    )

    _report(
        by_period,
        values,
        statuses,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("future_outcomes_used_for_research_only=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_52_H1_BODY_CONDITIONAL_RANK_AUDIT=OK")


if __name__ == "__main__":
    main()
