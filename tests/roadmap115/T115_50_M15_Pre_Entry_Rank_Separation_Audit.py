# -*- coding: utf-8 -*-
"""RoadMap115 / T115-50: M15 pre-entry rank separation.

TEST_ONLY / DATA_ONLY.

Перевіряється здатність трьох ознак завершеної M15
розділяти NO_BE_LOSS та решту baseline-угод.

Ознаки та їхні значення заморожені за T115-49.
Групи результатів заморожені за T115-47.

Використовуються:
- rank AUC із половинним балом для однакових значень;
- Cliff's delta = 2 * AUC - 1;
- медіани та обсяг обох груп.

Обчислення окремо для BUY/SELL та чотирьох періодів.
Пороги, entry-gates, SL/TP не підбираються.

Майбутній результат використовується тільки як label.
Production, MD7 та Replay-логіка не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_47_Pre_Entry_Non_BE_Loss_Anatomy import Record
    from T115_49_Completed_M15_Pre_Entry_Candle_Anatomy import Features

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

t49 = import_module("T115_49_Completed_M15_Pre_Entry_Candle_Anatomy")

BUY = t47.BUY
SELL = t47.SELL
EPS = t47.EPS
EXPECTED = t47.EXPECTED

FEATURES = (
    "directional_body",
    "range_pips",
    "directional_close_location",
)

PERIODS = (
    "2024_NOV_DEC",
    "2025",
    "2026_TO_2026_08_25",
    "2026_AUG_OCT",
)

collect_records = getattr(t47, "_collect")
load_features = getattr(t49, "_load_m15_features")
make_key = getattr(t49, "_key")


def _sha(path: Path) -> str:
    """Контроль SHA256 без модифікації файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _auc(
    positives: list[float],
    negatives: list[float],
) -> float | None:
    """Частка пар, де ознака в проблемній групі більша."""
    if not positives or not negatives:
        return None

    wins = 0.0

    for positive in positives:
        assert math.isfinite(positive)

        for negative in negatives:
            assert math.isfinite(negative)

            difference = positive - negative

            if difference > EPS:
                wins += 1.0
            elif abs(difference) <= EPS:
                wins += 0.5

    pairs = len(positives) * len(negatives)

    result = wins / pairs

    assert 0.0 <= result <= 1.0

    return result


def _synthetic() -> None:
    """Контроль крайніх випадків та однакових значень."""
    assert math.isclose(
        _auc([3.0, 4.0], [1.0, 2.0]),
        1.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        _auc([1.0, 2.0], [3.0, 4.0]),
        0.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        _auc([1.0, 2.0], [1.0, 2.0]),
        0.5,
        abs_tol=EPS,
    )

    assert math.isclose(
        _auc([1.0], [1.0]),
        0.5,
        abs_tol=EPS,
    )

    assert _auc([], [1.0]) is None
    assert _auc([1.0], []) is None

    sample = _auc(
        [2.0, 4.0],
        [1.0, 3.0],
    )

    assert sample is not None

    reversed_sample = _auc(
        [1.0, 3.0],
        [2.0, 4.0],
    )

    assert reversed_sample is not None

    assert math.isclose(
        sample + reversed_sample,
        1.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_RANK_AUC_EXTREMES=OK")
    print("SYNTHETIC_RANK_AUC_TIES=OK")
    print("SYNTHETIC_RANK_DIRECTION_SYMMETRY=OK")
    print("SYNTHETIC_EMPTY_COHORT_HANDLING=OK")


def _fmt(value: float | None) -> str:
    """Форматувати число або NA."""
    if value is None:
        return "NA"

    return f"{value:+.4f}"


def _median(values: list[float]) -> float | None:
    """Медіана тільки наявних значень."""
    if not values:
        return None

    return float(statistics.median(values))


def _describe(
    period: str,
    side: str,
    records: list[Record],
    values: dict[tuple, Features | None],
) -> None:
    """Оцінити рангове розділення без вибору порогів."""
    positives = [row for row in records if row.cohort == "NO_BE_LOSS"]

    negatives = [row for row in records if row.cohort != "NO_BE_LOSS"]

    assert len(positives) + len(negatives) == len(records)

    total_net = math.fsum(row.net for row in records)

    print(
        f"RANK_BASE|PERIOD={period}|SIDE={side}|"
        f"TOTAL={len(records)}|"
        f"NO_BE_LOSS={len(positives)}|"
        f"OTHER={len(negatives)}|"
        f"BASE_NET040={total_net:+.2f}"
    )

    for feature_name in FEATURES:
        positive_values: list[float] = []
        negative_values: list[float] = []

        positive_missing = 0
        negative_missing = 0

        for row in positives:
            feature = values[make_key(row)]

            value = getattr(feature, feature_name) if feature is not None else None

            if value is None:
                positive_missing += 1
            else:
                positive_values.append(float(value))

        for row in negatives:
            feature = values[make_key(row)]

            value = getattr(feature, feature_name) if feature is not None else None

            if value is None:
                negative_missing += 1
            else:
                negative_values.append(float(value))

        assert len(positive_values) + positive_missing == len(positives)

        assert len(negative_values) + negative_missing == len(negatives)

        auc = _auc(
            positive_values,
            negative_values,
        )

        if auc is None:
            reversed_auc = None
            cliff_delta = None
            separation = None
        else:
            reversed_auc = 1.0 - auc
            cliff_delta = 2.0 * auc - 1.0
            separation = abs(cliff_delta)

        print(
            f"RANK_FEATURE|PERIOD={period}|"
            f"SIDE={side}|FEATURE={feature_name}|"
            f"LOSS_N={len(positive_values)}|"
            f"OTHER_N={len(negative_values)}|"
            f"LOSS_MISSING={positive_missing}|"
            f"OTHER_MISSING={negative_missing}|"
            f"LOSS_MEDIAN={_fmt(_median(positive_values))}|"
            f"OTHER_MEDIAN={_fmt(_median(negative_values))}|"
            f"AUC_LOSS_HIGH={_fmt(auc)}|"
            f"AUC_LOSS_LOW={_fmt(reversed_auc)}|"
            f"CLIFF_DELTA={_fmt(cliff_delta)}|"
            f"ABS_RANK_SEPARATION={_fmt(separation)}"
        )

    print(f"RANK_FEATURE_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    by_period: dict[str, list[Record]],
    values: dict[tuple, Features | None],
) -> None:
    """Порівняти ті самі ознаки у чотирьох періодах."""
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
                period,
                side,
                selected,
                values,
            )

        pooled.extend(records)

        print(f"PERIOD_RANK_RECONCILIATION=" f"{period}:OK")

    assert len(pooled) == 333

    assert sum(row.cohort == "NO_BE_LOSS" for row in pooled) == 83

    assert sum(row.cohort != "NO_BE_LOSS" for row in pooled) == 250

    assert math.isclose(
        math.fsum(row.net for row in pooled),
        -680.30,
        abs_tol=EPS,
    )

    assert math.isclose(
        math.fsum(row.net for row in pooled if row.cohort == "NO_BE_LOSS"),
        -1947.10,
        abs_tol=EPS,
    )

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.direction == side]

        _describe(
            "POOLED",
            side,
            selected,
            values,
        )

    _describe(
        "POOLED",
        "ALL",
        pooled,
        values,
    )

    print("FROZEN_T115_47_OUTCOME_MIRROR=OK")
    print("FROZEN_T115_49_M15_FEATURES_REUSED=OK")
    print("FOUR_PERIOD_M15_RANK_SEPARATION=OK")
    print("AUC_IS_RESEARCH_STATISTIC_ONLY=True")
    print("NO_ENTRY_THRESHOLD_CREATED=True")
    print("NO_ENTRY_GATE_SIMULATED=True")
    print("NO_PARAMETER_OPTIMIZATION=True")


def main() -> None:
    """Дослідити розділення без змін production."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        ROOT / "tests/roadmap115/" "T115_49_Completed_M15_Pre_Entry_Candle_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-50|TEST_ONLY|" "M15_PRE_ENTRY_RANK_SEPARATION_AUDIT")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("FEATURES=FROZEN_T115_49")
    print("OUTCOME_LABELS=FROZEN_T115_47")
    print("RANK_METRIC=AUC_WITH_HALF_CREDIT_FOR_TIES")
    print("NO_THRESHOLD_SEARCH=True|NO_REPLAY_CHANGES=True")

    _synthetic()

    windows = t47.load_windows()
    history = t47.load_history()

    assert len(windows) == 4
    assert len(history) == 4

    by_period: dict[str, list[Record]] = {}

    for window in windows:
        records = collect_records(
            window,
            history[window.name],
        )

        assert window.name not in by_period
        assert len(records) == EXPECTED[window.name][0]

        by_period[window.name] = records

    pooled = [row for records in by_period.values() for row in records]

    assert len(pooled) == 333

    values = load_features(pooled)

    assert len(values) == 333
    assert all(values[make_key(row)] is not None for row in pooled)

    print("COMPLETED_M15_COVERAGE_333_OF_333=OK")

    _report(
        by_period,
        values,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("future_outcome_labels_for_research_only=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_50_M15_PRE_ENTRY_RANK_SEPARATION_AUDIT=OK")


if __name__ == "__main__":
    main()
