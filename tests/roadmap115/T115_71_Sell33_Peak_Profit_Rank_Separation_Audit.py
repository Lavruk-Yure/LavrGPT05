# -*- coding: utf-8 -*-
"""RoadMap115 / T115-71: SELL33 peak-profit rank separation.

TEST_ONLY / DATA_ONLY.

Виміряти безпорогову роздільну здатність peak_pips
для 105 SELL33 EXIT з перевіреного T115-70.

Позитивна outcome-мітка: SELL33_BETTER.
AUC > 0.5 означає, що більший peak_pips частіше
належить випадку, де SELL33 був кращим.

Майбутній результат використовується лише як мітка.
Вхідні ознаки взяті зі стану на завершенні H1.

Жодного порога, нового EXIT або production-зміни.
"""

from __future__ import annotations

import hashlib
import io
import math
import statistics
import sys
from collections import Counter
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


def _sha(path: Path) -> str:
    """Порахувати SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rank_report(
    period: str,
    positives: list[Any],
    negatives: list[Any],
) -> None:
    """Обчислити exact pairwise AUC без порогів."""
    assert positives
    assert negatives

    positive_peaks = [float(item.peak_pips) for item in positives]

    negative_peaks = [float(item.peak_pips) for item in negatives]

    assert all(
        math.isfinite(value) and value > 0 for value in positive_peaks + negative_peaks
    )

    wins = 0
    ties = 0
    losses = 0

    for positive_peak in positive_peaks:
        for negative_peak in negative_peaks:
            if positive_peak > negative_peak:
                wins += 1
            elif positive_peak < negative_peak:
                losses += 1
            else:
                ties += 1

    pairs = len(positive_peaks) * len(negative_peaks)

    assert wins + ties + losses == pairs

    auc = (wins + 0.5 * ties) / pairs

    assert 0 <= auc <= 1

    print(
        f"PEAK_RANK_AUC|PERIOD={period}|"
        f"SELL33_BETTER={len(positive_peaks)}|"
        f"ZERO33_BETTER={len(negative_peaks)}|"
        f"PAIRS={pairs}|"
        f"WINS={wins}|TIES={ties}|LOSSES={losses}|"
        f"AUC={auc:.4f}|"
        f"INVERSE_AUC={1 - auc:.4f}"
    )

    print(
        f"PEAK_RANK_MEDIANS|PERIOD={period}|"
        f"SELL33_BETTER={statistics.median(positive_peaks):.2f}|"
        f"ZERO33_BETTER={statistics.median(negative_peaks):.2f}|"
        f"SMALL_GROUP={min(len(positives), len(negatives)) < 10}"
    )


def main() -> None:
    """Перевірити rank separation без торгових змін."""
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
        TEST_DIR / "T115_69_Sell33_Paired_Exit_Impact_Distribution.py",
        TEST_DIR / "T115_70_Sell33_Causal_Exit_Signal_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    snapshots: dict[tuple[str, str], list[Any]] = {}

    def capture_report(
        report_period: str,
        label: str,
        records: list[Any],
    ) -> None:
        """Зберегти незмінні записи діагностики T115-70."""
        key = (report_period, label)

        assert key not in snapshots
        snapshots[key] = list(records)

        original_report(report_period, label, records)

    print("T115-71|TEST_ONLY|" "SELL33_PEAK_PROFIT_RANK_SEPARATION_AUDIT")
    print("SOURCE=REPRODUCED_T115_70")
    print("FEATURE=CAUSAL_PEAK_PIPS_AT_H1_EXIT_SIGNAL")
    print("LABEL=FUTURE_PAIRED_EXIT_OUTCOME_ONLY")
    print("NO_THRESHOLD_SELECTION=True")
    print("NO_NEW_TRADING_RULE=True")

    buffer = io.StringIO()

    try:
        setattr(source, "_group_report", capture_report)

        with redirect_stdout(buffer):
            source_main()
    finally:
        setattr(source, "_group_report", original_report)

    assert getattr(source, "_group_report") is original_report

    source_output = buffer.getvalue()

    assert "T115_70_SELL33_CAUSAL_EXIT_SIGNAL_ANATOMY=OK" in source_output

    for period in EXPECTED_COUNTS:
        assert f"BASELINE_MATCH={period}:OK|" in source_output

    for line in source_output.splitlines():
        if line.startswith(
            (
                "POOLED_BASELINE|",
                "POOLED_EXIT_SIGNAL_RECONCILIATION|",
            )
        ):
            print(line)

    print("T115_70_FULL_REPRODUCTION=OK")
    print("DIAGNOSTIC_REPORT_HOOK_RESTORED=OK")

    all_positive: list[Any] = []
    all_negative: list[Any] = []

    for period, (expected_positive, expected_negative) in EXPECTED_COUNTS.items():
        positive = snapshots[(period, POSITIVE)]
        negative = snapshots[(period, NEGATIVE)]

        assert len(positive) == expected_positive
        assert len(negative) == expected_negative

        _rank_report(period, positive, negative)

        all_positive.extend(positive)
        all_negative.extend(negative)

    assert len(all_positive) == 66
    assert len(all_negative) == 39

    pooled_positive = snapshots[("POOLED", POSITIVE)]
    pooled_negative = snapshots[("POOLED", NEGATIVE)]

    assert Counter(item.peak_pips for item in pooled_positive) == Counter(
        item.peak_pips for item in all_positive
    )

    assert Counter(item.peak_pips for item in pooled_negative) == Counter(
        item.peak_pips for item in all_negative
    )

    periods_2026 = (
        "2026_TO_2026_08_25",
        "2026_AUG_OCT",
    )

    positive_2026 = [
        item for period in periods_2026 for item in snapshots[(period, POSITIVE)]
    ]

    negative_2026 = [
        item for period in periods_2026 for item in snapshots[(period, NEGATIVE)]
    ]

    assert len(positive_2026) == 27
    assert len(negative_2026) == 19

    _rank_report(
        "2026_COMBINED",
        positive_2026,
        negative_2026,
    )

    _rank_report(
        "POOLED",
        all_positive,
        all_negative,
    )

    assert before == {path: _sha(path) for path in guarded}

    print("FOUR_PERIOD_OUTCOME_COUNTS=OK")
    print("PEAK_RANK_PAIRS_RECONCILED=OK")
    print("T115_70_REPORT_HOOK_RESTORED=OK")
    print("SOURCE_FILES_UNCHANGED=OK")
    print("FUTURE_OUTCOME_NOT_USED_AS_FEATURE=True")
    print("AUC_IS_NOT_ECONOMIC_PROOF=True")
    print("NO_PARAMETER_OPTIMIZATION=True")
    print("NO_REENTRY_SIMULATED=True")
    print("NO_PRODUCTION_OR_REPLAY_CHANGE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_71_SELL33_PEAK_PROFIT_RANK_SEPARATION_AUDIT=OK")


if __name__ == "__main__":
    main()
