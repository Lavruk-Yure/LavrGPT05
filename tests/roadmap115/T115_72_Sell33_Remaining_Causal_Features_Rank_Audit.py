# -*- coding: utf-8 -*-
"""RoadMap115 / T115-72: remaining causal EXIT features.

TEST_ONLY / DATA_ONLY.

Перевірити безпороговий rank AUC для:
- close_pips;
- giveback_ratio;
- age_hours.

Повторно використовуються 105 причинних знімків T115-70.
peak_pips слугує контролем результатів T115-71.

Майбутній результат використовується лише як outcome-мітка.
Нові правила, пороги, production та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import io
import math
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


EXPECTED_COUNTS = {
    "2024_NOV_DEC": (7, 1),
    "2025": (32, 19),
    "2026_TO_2026_08_25": (23, 13),
    "2026_AUG_OCT": (4, 6),
}

POSITIVE = "SELL33_BETTER"
NEGATIVE = "ZERO33_BETTER"

FEATURES = (
    "peak_pips",
    "close_pips",
    "giveback_ratio",
    "age_hours",
)


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _auc(
    positive: list[Any],
    negative: list[Any],
    feature: str,
) -> tuple[float, int, int, int]:
    """Обчислити exact pairwise AUC без порогів."""
    assert positive and negative

    positive_values = [float(getattr(item, feature)) for item in positive]

    negative_values = [float(getattr(item, feature)) for item in negative]

    assert all(math.isfinite(value) for value in positive_values + negative_values)

    wins = 0
    ties = 0
    losses = 0

    for good in positive_values:
        for bad in negative_values:
            if good > bad:
                wins += 1
            elif good < bad:
                losses += 1
            else:
                ties += 1

    pairs = len(positive) * len(negative)

    assert wins + ties + losses == pairs

    auc = (wins + 0.5 * ties) / pairs

    assert 0 <= auc <= 1

    return auc, wins, ties, losses


def _report(
    period_name: str,
    positive: list[Any],
    negative: list[Any],
) -> dict[str, float]:
    """Вивести AUC усіх зафіксованих ознак."""
    result: dict[str, float] = {}

    for feature in FEATURES:
        auc, wins, ties, losses = _auc(
            positive,
            negative,
            feature,
        )

        pairs = len(positive) * len(negative)

        print(
            f"CAUSAL_FEATURE_AUC|PERIOD={period_name}|"
            f"FEATURE={feature}|"
            f"POSITIVE={len(positive)}|"
            f"NEGATIVE={len(negative)}|"
            f"PAIRS={pairs}|"
            f"WINS={wins}|TIES={ties}|LOSSES={losses}|"
            f"AUC={auc:.4f}|"
            f"INVERSE_AUC={1 - auc:.4f}"
        )

        result[feature] = auc

    return result


def main() -> None:
    """Перевірити ознаки без підбору торгових умов."""
    source = import_module("T115_70_Sell33_Causal_Exit_Signal_Anatomy")

    source_main: Callable[[], None] = getattr(
        source,
        "main",
    )

    original_report: Callable[[str, str, list[Any]], None] = getattr(
        source,
        "_group_report",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_70_Sell33_Causal_Exit_Signal_Anatomy.py",
        TEST_DIR / "T115_71_Sell33_Peak_Profit_Rank_Separation_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    snapshots: dict[tuple[str, str], list[Any]] = {}

    def capture_report(
        source_period: str,
        source_label: str,
        source_records: list[Any],
    ) -> None:
        """Перехопити незмінні знімки T115-70."""
        key = (source_period, source_label)

        assert key not in snapshots
        snapshots[key] = list(source_records)

        original_report(
            source_period,
            source_label,
            source_records,
        )

    print("T115-72|TEST_ONLY|" "SELL33_REMAINING_CAUSAL_FEATURES_RANK_AUDIT")
    print("SOURCE=REPRODUCED_T115_70")
    print("OUTCOME_LABELS_ARE_EX_POST_ONLY=True")
    print("FEATURE_POLARITY=HIGHER_VALUE_PREDICTS_SELL33_BETTER")
    print("NO_THRESHOLD_OPTIMIZATION=True")
    print("NO_NEW_TRADING_RULE=True")

    output_buffer = io.StringIO()

    try:
        setattr(
            source,
            "_group_report",
            capture_report,
        )

        with redirect_stdout(output_buffer):
            source_main()
    finally:
        setattr(
            source,
            "_group_report",
            original_report,
        )

    assert (
        getattr(
            source,
            "_group_report",
        )
        is original_report
    )

    output = output_buffer.getvalue()

    assert "T115_70_SELL33_CAUSAL_EXIT_SIGNAL_ANATOMY=OK" in output

    print("T115_70_FULL_REPRODUCTION=OK")
    print("DIAGNOSTIC_REPORT_HOOK_RESTORED=OK")

    positive_all: list[Any] = []
    negative_all: list[Any] = []

    for period_name, expected in EXPECTED_COUNTS.items():
        positive = snapshots[(period_name, POSITIVE)]
        negative = snapshots[(period_name, NEGATIVE)]

        assert (len(positive), len(negative)) == expected

        results = _report(
            period_name,
            positive,
            negative,
        )

        if period_name == "2025":
            assert math.isclose(
                results["peak_pips"],
                0.6735,
                abs_tol=0.00005,
            )

        positive_all.extend(positive)
        negative_all.extend(negative)

    assert len(positive_all) == 66
    assert len(negative_all) == 39

    positive_2026 = [
        item
        for period_name in (
            "2026_TO_2026_08_25",
            "2026_AUG_OCT",
        )
        for item in snapshots[(period_name, POSITIVE)]
    ]

    negative_2026 = [
        item
        for period_name in (
            "2026_TO_2026_08_25",
            "2026_AUG_OCT",
        )
        for item in snapshots[(period_name, NEGATIVE)]
    ]

    assert len(positive_2026) == 27
    assert len(negative_2026) == 19

    results_2026 = _report(
        "2026_COMBINED",
        positive_2026,
        negative_2026,
    )

    pooled_results = _report(
        "POOLED",
        positive_all,
        negative_all,
    )

    assert math.isclose(
        results_2026["peak_pips"],
        0.4474,
        abs_tol=0.00005,
    )

    assert math.isclose(
        pooled_results["peak_pips"],
        0.5874,
        abs_tol=0.00005,
    )

    assert len(snapshots[("POOLED", POSITIVE)]) == 66
    assert len(snapshots[("POOLED", NEGATIVE)]) == 39

    print("T115_71_PEAK_AUC_REFERENCE=OK")

    assert before == {path: _sha(path) for path in guarded}

    print("FOUR_PERIOD_OUTCOME_COUNTS=OK")
    print("ALL_CAUSAL_FEATURE_PAIR_COUNTS=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("FUTURE_OUTCOME_NOT_USED_AS_FEATURE=True")
    print("AUC_IS_NOT_ECONOMIC_PROOF=True")
    print("NO_THRESHOLD_OPTIMIZATION=True")
    print("NO_NEW_ENTRY_EXIT_OR_REENTRY_RULE=True")
    print("NO_PRODUCTION_OR_REPLAY_LOGIC_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_72_SELL33_REMAINING_CAUSAL_FEATURES_RANK_AUDIT=OK")


if __name__ == "__main__":
    main()
