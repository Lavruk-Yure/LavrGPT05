# -*- coding: utf-8 -*-
"""RoadMap115 / T115-85: ENDING ENTRY no-change regression audit.

TEST_ONLY / DATA_ONLY.

Повторно запускає GREEN T115-84 через canonical production
Replay harness T105-18 і перевіряє контрольні значення
за 2025, 2026 та об'єднаною вибіркою.

Фіксує дослідницьке рішення NO_CHANGE для гілки
ENDING / STATE_MISMATCH.

Не створює додаткових ордерів, не підбирає параметри,
не змінює production, Replay або MD7.
"""

from __future__ import annotations

import hashlib
import io
import runpy
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_DIR = ROOT / "tests" / "roadmap115"

HORIZONS = (1, 4, 8, 16)

# N, VALID, QUOTE_MEAN у порядку HORIZONS.
# Незмінні результати GREEN T115-84.
EXPECTED = {
    ("2025", "STATE_MISMATCH"): (
        (63, 63, -1.452),
        (63, 61, +0.990),
        (63, 61, +0.528),
        (63, 57, -3.981),
    ),
    ("2026", "STATE_MISMATCH"): (
        (29, 29, -1.938),
        (29, 29, -0.014),
        (29, 29, -1.621),
        (29, 26, +0.388),
    ),
    ("POOLED", "STATE_MISMATCH"): (
        (92, 92, -1.605),
        (92, 90, +0.667),
        (92, 90, -0.164),
        (92, 83, -2.612),
    ),
    ("2025", "ACCEPTED"): (
        (42, 42, +0.193),
        (42, 42, -0.898),
        (42, 42, -0.990),
        (42, 35, -0.080),
    ),
    ("2026", "ACCEPTED"): (
        (18, 18, +2.206),
        (18, 17, +5.518),
        (18, 16, -0.175),
        (18, 13, -5.046),
    ),
    ("POOLED", "ACCEPTED"): (
        (60, 60, +0.797),
        (60, 59, +0.951),
        (60, 58, -0.766),
        (60, 48, -1.425),
    ),
}


REQUIRED_MARKERS = (
    "QUOTE_ADJUSTED_RECONCILIATION=2025:OK",
    "QUOTE_ADJUSTED_RECONCILIATION=2026:OK",
    "STATE_MISMATCH_92_OF_92=OK",
    "ACCEPTED_60_OF_60=OK",
    "H4_STATE_MISMATCH_VALID_90=OK",
    "H4_ACCEPTED_VALID_59=OK",
    "QUOTE_ARITHMETIC_PARITY=OK",
    "SOURCE_FILES_SHA_UNCHANGED=OK",
    "NO_NEW_ENTRY_OR_EXIT_RULE=True",
    "broker_requests=0|TEST_ONLY=True|DATA_ONLY=True",
    "production_changed=False|md7_changed=False",
    "T115_84_STATE_MISMATCH_QUOTE_ADJUSTED_HORIZON_AUDIT=OK",
)


def _sha(source_file: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _parse_results(
    output: str,
) -> dict[tuple[str, str, int], tuple[int, int, float]]:
    """Прочитати фактичні результати повторного T115-84."""
    results: dict[
        tuple[str, str, int],
        tuple[int, int, float],
    ] = {}

    for line in output.splitlines():
        if not line.startswith("QUOTE_ADJUSTED_LABEL|"):
            continue

        fields = {}

        for chunk in line.split("|")[1:]:
            if "=" in chunk:
                name, value = chunk.split("=", 1)
                fields[name] = value

        if fields["SIDE"] != "ALL":
            continue

        period = fields["PERIOD"]
        group = fields["GROUP"]
        horizon = int(fields["H_M15"])

        key = period, group, horizon

        assert key not in results, (
            "DUPLICATE_RESULT",
            key,
        )

        total = int(fields["N"])
        valid = int(fields["VALID"])
        gaps = int(fields["TIME_GAP"])
        end_of_data = int(fields["END_OF_DATA"])

        assert valid + gaps + end_of_data == total

        positive = int(fields["ADJUSTED_POS"])
        negative = int(fields["ADJUSTED_NEG"])
        neutral = int(fields["ADJUSTED_ZERO"])

        assert positive + negative + neutral == valid

        results[key] = (
            total,
            valid,
            float(fields["QUOTE_MEAN"]),
        )

    return results


def _check_expected(
    results: dict[
        tuple[str, str, int],
        tuple[int, int, float],
    ],
) -> None:
    """Звірити всі 24 контрольні агреговані результати."""
    assert len(results) == 24, len(results)

    checked = 0

    for (period, group), rows in EXPECTED.items():
        for horizon, expected in zip(HORIZONS, rows):
            key = period, group, horizon

            assert key in results, (
                "MISSING_RESULT",
                key,
            )

            actual = results[key]

            assert actual == expected, (
                "BASELINE_MISMATCH",
                key,
                actual,
                expected,
            )

            checked += 1

    assert checked == 24

    print("T115_84_QUOTE_RESULT_ROWS_24_OF_24=OK")


def _verify_pooled(
    results: dict[
        tuple[str, str, int],
        tuple[int, int, float],
    ],
) -> None:
    """Звірити чисельність pooled із двома періодами."""
    for group in ("STATE_MISMATCH", "ACCEPTED"):
        for horizon in HORIZONS:
            first = results["2025", group, horizon]
            second = results["2026", group, horizon]
            pooled = results["POOLED", group, horizon]

            assert pooled[0] == first[0] + second[0]
            assert pooled[1] == first[1] + second[1]

            weighted_mean = (first[1] * first[2] + second[1] * second[2]) / pooled[1]

            # Попередній тест друкує середні з округленням до 0.001.
            assert abs(weighted_mean - pooled[2]) <= 0.0011, (
                group,
                horizon,
                weighted_mean,
                pooled[2],
            )

    print("POOLED_WEIGHTED_MEANS_RECONCILED=OK")


def _decision(
    results: dict[
        tuple[str, str, int],
        tuple[int, int, float],
    ],
) -> None:
    """Зафіксувати висновок без зміни торгових правил."""
    consistent_positive = []

    for horizon in HORIZONS:
        mean_2025 = results["2025", "STATE_MISMATCH", horizon][2]

        mean_2026 = results["2026", "STATE_MISMATCH", horizon][2]

        if mean_2025 > 0 and mean_2026 > 0:
            consistent_positive.append(horizon)

        print(
            f"CROSS_PERIOD_OUTCOME|H_M15={horizon}|"
            f"2025_QUOTE_MEAN={mean_2025:+.3f}|"
            f"2026_QUOTE_MEAN={mean_2026:+.3f}"
        )

    assert not consistent_positive

    mismatch_h4 = results["POOLED", "STATE_MISMATCH", 4][2]

    accepted_h4 = results["POOLED", "ACCEPTED", 4][2]

    assert mismatch_h4 == 0.667
    assert accepted_h4 == 0.951
    assert mismatch_h4 < accepted_h4

    print("CONSISTENT_POSITIVE_HORIZONS=0_OF_4")

    print(
        "POOLED_H4_COMPARISON|"
        f"STATE_MISMATCH={mismatch_h4:+.3f}|"
        f"ACCEPTED={accepted_h4:+.3f}"
    )

    print("ENDING_STATE_MISMATCH_RESEARCH_DECISION=NO_CHANGE")
    print("TRADING_EDGE_NOT_ESTABLISHED=True")
    print("H4_SELECTION_EXPLORATORY=True")
    print("PRODUCTION_ENTRY_CHANGE_AUTHORIZED=False")


def main() -> None:
    """Повторити регресію та зафіксувати підсумок RoadMap115."""
    audit_file = ROADMAP_DIR / "T115_84_State_Mismatch_Quote_Adjusted_Horizon_Audit.py"

    prerequisite_files = (
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
        ROADMAP_DIR / "T115_79_Production_Ending_Causal_Cause_And_Transition_Audit.py",
        ROADMAP_DIR / "T115_81_Ending_Fixed_Horizon_Price_Label_Audit.py",
        ROADMAP_DIR / "T115_83_State_Mismatch_Next_Bar_Feasibility_Audit.py",
        audit_file,
    )

    core_files = tuple(sorted((ROOT / "core").rglob("*.py")))

    md7 = ROOT / "doc" / "LGE_Runtime_07.md"

    guarded = core_files + prerequisite_files + (md7,)

    assert core_files
    assert all(source_file.is_file() for source_file in guarded)

    before = {source_file: _sha(source_file) for source_file in guarded}

    print("T115-85|TEST_ONLY|" "ENDING_ENTRY_NO_CHANGE_REGRESSION_AUDIT")
    print("SOURCE=ACTUAL_T115_84_CANONICAL_REPLAY")
    print("PERIODS=2025,2026|TIMEFRAME=M15")
    print("NEW_TRADING_RULES=False")
    print("COUNTERFACTUAL_EXECUTION=False")

    captured = io.StringIO()

    try:
        with redirect_stdout(captured):
            runpy.run_path(
                str(audit_file),
                run_name="__main__",
            )
    except Exception:
        print("T115_84_RERUN_FAILED=True")
        print(captured.getvalue()[-4000:])
        raise

    output = captured.getvalue()

    for marker in REQUIRED_MARKERS:
        assert marker in output, (
            "MISSING_AUDIT_MARKER",
            marker,
        )

    print("T115_84_CANONICAL_REPLAY_RERUN=OK")

    results = _parse_results(output)

    _check_expected(results)
    _verify_pooled(results)
    _decision(results)

    assert before == {source_file: _sha(source_file) for source_file in guarded}

    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("PRODUCTION_AND_MD7_UNCHANGED=True")
    print("NO_NEW_ENTRY_EXIT_OR_REENTRY_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_85_ENDING_ENTRY_NO_CHANGE_REGRESSION_AUDIT=OK")


if __name__ == "__main__":
    main()
