# -*- coding: utf-8 -*-
"""RoadMap115 / T115-77: production ENDING_ALIGNED context anatomy.

TEST_ONLY / DATA_ONLY.

Повторити canonical M15 production Replay T105-18.
Порівняти ENDING_ALIGNED, ACTIVE_OPPOSITE та ACCEPTED
за збереженими WorkspaceSignalFilterContext.

Майбутній PnL не використовується.
Production, Replay та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "tests" / "roadmap115"

for directory in (ROOT, TEST_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


EXPECTED = {
    "2025": {
        "RAW": 3042,
        "QUALIFIED": 416,
        "SAME_TIMEFRAME": 340,
        "ACCEPTED": 42,
        "ENDING_ALIGNED": 71,
        "ACTIVE_OPPOSITE": 159,
        "ENDING_BUY": 40,
        "ENDING_SELL": 31,
    },
    "2026": {
        "RAW": 1962,
        "QUALIFIED": 183,
        "SAME_TIMEFRAME": 143,
        "ACCEPTED": 18,
        "ENDING_ALIGNED": 33,
        "ACTIVE_OPPOSITE": 69,
        "ENDING_BUY": 17,
        "ENDING_SELL": 16,
    },
}

GROUPS = (
    "ENDING_ALIGNED",
    "ACTIVE_OPPOSITE",
    "ACCEPTED_ACTIVE_ALIGNED",
)

FEATURES = (
    "normalized_slope",
    "normalized_opening",
    "active_age",
)


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aligned(direction: str, regime: str) -> bool:
    """Перевірити відповідність напрямку сигналу тренду."""
    return (
        direction == "BUY"
        and regime == "ALLIGATOR_REGIME_TREND_UP"
        or direction == "SELL"
        and regime == "ALLIGATOR_REGIME_TREND_DOWN"
    )


def _opposite(direction: str, regime: str) -> bool:
    """Перевірити протилежний напрям тренду."""
    return (
        direction == "BUY"
        and regime == "ALLIGATOR_REGIME_TREND_DOWN"
        or direction == "SELL"
        and regime == "ALLIGATOR_REGIME_TREND_UP"
    )


def _group(record: Any) -> str | None:
    """Класифікувати фактичний збережений контекст."""
    context = record.filter_context

    if context is None:
        return None

    phase = context.regime_phase
    regime = context.regime
    direction = record.direction

    if record.accepted:
        assert phase == "ALLIGATOR_REGIME_PHASE_ACTIVE"
        assert _aligned(direction, regime)
        return "ACCEPTED_ACTIVE_ALIGNED"

    reason = record.filter_reason_code or ""

    if not reason.startswith("ALLIGATOR_SAME_TIMEFRAME_"):
        return None

    if phase == "ALLIGATOR_REGIME_PHASE_ENDING" and _aligned(direction, regime):
        assert reason in {
            "ALLIGATOR_SAME_TIMEFRAME_BUY_ENDING_REJECT",
            "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT",
        }
        return "ENDING_ALIGNED"

    if phase == "ALLIGATOR_REGIME_PHASE_ACTIVE" and _opposite(direction, regime):
        return "ACTIVE_OPPOSITE"

    return None


def _metrics(
    label: str,
    period: str,
    records: list[Any],
) -> None:
    """Показати покриття та значення без підбору порогів."""
    assert records

    sides = Counter(record.direction for record in records)

    assert sum(sides.values()) == len(records)

    print(
        f"CONTEXT_GROUP|PERIOD={period}|GROUP={label}|"
        f"TOTAL={len(records)}|"
        f"BUY={sides['BUY']}|SELL={sides['SELL']}"
    )

    for feature in FEATURES:
        values: list[float] = []

        for record in records:
            context = record.filter_context
            assert context is not None

            value = getattr(context, feature)

            if value is not None:
                number = float(value)
                assert math.isfinite(number)
                values.append(number)

        missing = len(records) - len(values)

        if values:
            summary = (
                f"MIN={min(values):.4f}|"
                f"MEDIAN={statistics.median(values):.4f}|"
                f"MAX={max(values):.4f}"
            )
        else:
            summary = "MIN=NA|MEDIAN=NA|MAX=NA"

        print(
            f"CONTEXT_FEATURE|PERIOD={period}|"
            f"GROUP={label}|FEATURE={feature}|"
            f"PRESENT={len(values)}|MISSING={missing}|"
            f"{summary}"
        )

    availability_lags: Counter[float] = Counter()
    history_items = 0

    for record in records:
        context = record.filter_context

        assert context is not None
        assert context.timeframe == "M15"
        assert context.observation_timestamp is not None
        assert context.available_at is not None

        assert context.observation_timestamp <= context.available_at

        lag = (context.available_at - record.timestamp).total_seconds() / 60

        assert math.isfinite(lag)

        availability_lags[lag] += 1

        for observation in context.diagnostic_observations:
            assert observation.available_at <= context.available_at
            assert observation.timestamp <= context.observation_timestamp
            history_items += 1

    assert sum(availability_lags.values()) == len(records)

    for lag, count in sorted(availability_lags.items()):
        print(
            f"CONTEXT_AVAILABILITY_LAG|PERIOD={period}|"
            f"GROUP={label}|LAG_MIN={lag:+.1f}|COUNT={count}"
        )

    print(
        f"CONTEXT_HISTORY|PERIOD={period}|"
        f"GROUP={label}|OBSERVATIONS={history_items}|"
        "NO_FUTURE_RELATIVE_TO_CONTEXT=True"
    )


def main() -> None:
    """Дослідити 104 ENDING_ALIGNED у production Replay."""
    source = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    run_period: Callable[[Any], tuple[Any, int, int]] = getattr(source, "_run_period")

    periods: tuple[Any, ...] = tuple(getattr(source, "PERIODS"))

    hashes: Callable[[], dict[str, str]] = getattr(source, "_production_hashes")

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "core/workspace_signal.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    production_before = hashes()

    print("T115-77|TEST_ONLY|" "PRODUCTION_ENDING_ALIGNED_CONTEXT_ANATOMY")
    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("CONTEXT=FROZEN_SIGNAL_FILTER_CONTEXT")
    print("FUTURE_OUTCOME_USED=False")
    print("NO_GATE_COUNTERFACTUAL=True")
    print("RECORD_TIMESTAMP_NOT_ASSUMED_EXECUTION_TIME=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled: Counter[str] = Counter()

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0

        records = runtime.signal_records_for_ui()

        qualified = [
            record
            for record in records
            if record.accepted or record.source_reason_code == "MACD_CROSS_ACCEPTED"
        ]

        same_tf = [
            record
            for record in qualified
            if not record.accepted
            and (record.filter_reason_code or "").startswith(
                "ALLIGATOR_SAME_TIMEFRAME_"
            )
        ]

        groups: dict[str, list[Any]] = {name: [] for name in GROUPS}

        for record in qualified:
            category = _group(record)

            if category is not None:
                groups[category].append(record)

        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]
        assert len(qualified) == expected["QUALIFIED"]
        assert len(same_tf) == expected["SAME_TIMEFRAME"]

        assert len(groups["ENDING_ALIGNED"]) == expected["ENDING_ALIGNED"]

        assert len(groups["ACTIVE_OPPOSITE"]) == expected["ACTIVE_OPPOSITE"]

        assert len(groups["ACCEPTED_ACTIVE_ALIGNED"]) == expected["ACCEPTED"]

        ending_sides = Counter(record.direction for record in groups["ENDING_ALIGNED"])

        assert ending_sides["BUY"] == expected["ENDING_BUY"]
        assert ending_sides["SELL"] == expected["ENDING_SELL"]

        summary = runtime.historical_summary

        assert summary is not None
        assert summary.opened_trades == expected["ACCEPTED"]

        print(
            f"PERIOD_BASELINE|PERIOD={spec.code}|"
            f"RAW={len(records)}|"
            f"QUALIFIED={len(qualified)}|"
            f"SAME_TIMEFRAME={len(same_tf)}|"
            f"ACCEPTED={summary.opened_trades}"
        )

        for label in GROUPS:
            _metrics(
                label,
                spec.code,
                groups[label],
            )

            pooled[label] += len(groups[label])

        print(f"ENDING_ALIGNED_CONTEXT_RECONCILIATION=" f"{spec.code}:OK")

    assert pooled["ENDING_ALIGNED"] == 104
    assert pooled["ACTIVE_OPPOSITE"] == 228
    assert pooled["ACCEPTED_ACTIVE_ALIGNED"] == 60

    print(
        "POOLED_CONTEXT_GROUPS|"
        + "|".join(f"{label}={pooled[label]}" for label in GROUPS)
    )

    assert before == {path: _sha(path) for path in guarded}

    assert production_before == hashes()

    print("PRODUCTION_BASELINES_2025_2026=OK")
    print("ENDING_ALIGNED_104_OF_104=OK")
    print("ACTIVE_OPPOSITE_228_OF_228=OK")
    print("ACCEPTED_60_OF_60=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("CONTEXT_TIMESTAMPS_NOT_EXECUTION_ORDER_PROOF=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_77_PRODUCTION_ENDING_ALIGNED_CONTEXT_ANATOMY=OK")


if __name__ == "__main__":
    main()
