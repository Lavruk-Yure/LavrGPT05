# -*- coding: utf-8 -*-
"""RoadMap115 / T115-76: production SAME_TIMEFRAME context audit.

TEST_ONLY / DATA_ONLY.

Повторити canonical production Replay із T105-18.
Виділити MACD_CROSS_ACCEPTED і розкласти остаточні
записи за стадією відхилення, напрямком та збереженим
Alligator filter context.

Deferred ARMED враховується окремо: це не доказ
остаточно втраченої торгової можливості.

Майбутній PnL не використовується. Нові умови ENTRY
не створюються. Production, Replay та MD7 незмінні.
"""

from __future__ import annotations

import hashlib
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


STAGES = (
    "ACCEPTED",
    "SAME_TIMEFRAME",
    "STOCHASTIC",
    "DEFERRED_ARMED",
    "STRUCTURAL_OTHER",
)

EXPECTED = {
    "2025": {
        "TOTAL": 3042,
        "MACD_REJECT": 2626,
        "QUALIFIED": 416,
        "ACCEPTED": 42,
        "SAME_TIMEFRAME": 340,
        "STOCHASTIC": 17,
        "DEFERRED_ARMED": 5,
        "STRUCTURAL_OTHER": 12,
    },
    "2026": {
        "TOTAL": 1962,
        "MACD_REJECT": 1779,
        "QUALIFIED": 183,
        "ACCEPTED": 18,
        "SAME_TIMEFRAME": 143,
        "STOCHASTIC": 11,
        "DEFERRED_ARMED": 3,
        "STRUCTURAL_OTHER": 8,
    },
}


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage(record: Any, stochastic_reason: str) -> str:
    """Класифікувати тільки фактичне збережене рішення."""
    if record.accepted:
        return "ACCEPTED"

    reason = record.filter_reason_code or ""

    if reason.startswith("ALLIGATOR_SAME_TIMEFRAME_"):
        return "SAME_TIMEFRAME"

    if reason == stochastic_reason:
        return "STOCHASTIC"

    if reason == "ALLIGATOR_DEFERRED_ARMED":
        return "DEFERRED_ARMED"

    return "STRUCTURAL_OTHER"


def _context(record: Any) -> tuple[str, str, str]:
    """Отримати напрям, phase і regime без реконструкції."""
    context = record.filter_context

    if context is None:
        return record.direction, "NO_CONTEXT", "NO_CONTEXT"

    return (
        record.direction,
        context.regime_phase or "UNKNOWN",
        context.regime or "UNKNOWN",
    )


def main() -> None:
    """Дослідити MACD-qualified production reject context."""
    source = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    run_period: Callable[[Any], tuple[Any, int, int]] = getattr(source, "_run_period")

    periods: tuple[Any, ...] = tuple(getattr(source, "PERIODS"))

    stochastic_reason: str = getattr(
        source,
        "ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "core/workspace_replay_execution.py",
        ROOT / "doc/LGE_Runtime_07.md",
        TEST_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    print("T115-76|TEST_ONLY|" "PRODUCTION_SAME_TIMEFRAME_REJECT_CONTEXT_AUDIT")
    print("SOURCE=CANONICAL_T105_18_PRODUCTION_REPLAY")
    print("TIMEFRAME=M15")
    print("OUTCOME_LABELS_USED=False")
    print("DEFERRED_ARMED_IS_PROVISIONAL=True")
    print("NO_NEW_ENTRY_RULE=True")

    pooled: Counter[str] = Counter()
    pooled_context: Counter[tuple[str, str, str, str]] = Counter()

    assert tuple(spec.code for spec in periods) == (
        "2025",
        "2026",
    )

    for spec in periods:
        runtime, stochastic_rejects, broker_requests = run_period(spec)

        assert broker_requests == 0

        records = runtime.signal_records_for_ui()

        qualified = [
            record
            for record in records
            if record.accepted or record.source_reason_code == "MACD_CROSS_ACCEPTED"
        ]

        macd_rejects = [
            record
            for record in records
            if not record.accepted
            and record.source_reason_code != "MACD_CROSS_ACCEPTED"
        ]

        assert all(not record.accepted for record in macd_rejects)

        expected = EXPECTED[spec.code]

        assert len(records) == expected["TOTAL"]
        assert len(macd_rejects) == expected["MACD_REJECT"]
        assert len(qualified) == expected["QUALIFIED"]

        stage_counts = Counter(
            _stage(record, stochastic_reason) for record in qualified
        )

        assert sum(stage_counts.values()) == len(qualified)

        for stage in STAGES:
            assert stage_counts[stage] == expected[stage], (
                spec.code,
                stage,
                stage_counts[stage],
                expected[stage],
            )

        assert stage_counts["STOCHASTIC"] == stochastic_rejects

        assert all(record.direction in ("BUY", "SELL") for record in qualified)

        accepted = [record for record in qualified if record.accepted]

        summary = runtime.historical_summary
        assert summary is not None
        assert summary.opened_trades == len(accepted)

        print(
            f"MACD_QUALIFIED_FUNNEL|PERIOD={spec.code}|"
            f"RAW_RECORDS={len(records)}|"
            f"MACD_REJECT={len(macd_rejects)}|"
            f"MACD_QUALIFIED={len(qualified)}|"
            f"ACCEPTED={stage_counts['ACCEPTED']}|"
            f"SAME_TIMEFRAME={stage_counts['SAME_TIMEFRAME']}|"
            f"STOCHASTIC={stage_counts['STOCHASTIC']}|"
            f"DEFERRED_ARMED={stage_counts['DEFERRED_ARMED']}|"
            f"STRUCTURAL_OTHER={stage_counts['STRUCTURAL_OTHER']}"
        )

        context_counts: Counter[tuple[str, str, str, str]] = Counter()

        reason_side: Counter[tuple[str, str]] = Counter()

        for record in qualified:
            stage = _stage(record, stochastic_reason)

            direction, phase, regime = _context(record)

            context_counts[
                stage,
                direction,
                phase,
                regime,
            ] += 1

            if stage == "SAME_TIMEFRAME":
                reason_side[
                    record.filter_reason_code or "UNKNOWN",
                    direction,
                ] += 1

        for (reason, direction), count in sorted(reason_side.items()):
            print(
                f"SAME_TIMEFRAME_REASON|PERIOD={spec.code}|"
                f"REASON={reason}|SIDE={direction}|COUNT={count}"
            )

        for (stage, direction, phase, regime), count in sorted(context_counts.items()):
            if stage not in ("SAME_TIMEFRAME", "ACCEPTED"):
                continue

            print(
                f"ALLIGATOR_CONTEXT|PERIOD={spec.code}|"
                f"STAGE={stage}|SIDE={direction}|"
                f"PHASE={phase}|REGIME={regime}|COUNT={count}"
            )

        assert sum(reason_side.values()) == (stage_counts["SAME_TIMEFRAME"])

        assert sum(context_counts.values()) == len(qualified)

        for stage in STAGES:
            pooled[stage] += stage_counts[stage]

        pooled["TOTAL"] += len(records)
        pooled["MACD_REJECT"] += len(macd_rejects)
        pooled["QUALIFIED"] += len(qualified)
        pooled_context.update(context_counts)

        print(f"PRODUCTION_CONTEXT_RECONCILIATION=" f"{spec.code}:OK")

    assert pooled["TOTAL"] == 5004
    assert pooled["MACD_REJECT"] == 4405
    assert pooled["QUALIFIED"] == 599

    assert pooled["ACCEPTED"] == 60
    assert pooled["SAME_TIMEFRAME"] == 483
    assert pooled["STOCHASTIC"] == 28
    assert pooled["DEFERRED_ARMED"] == 8
    assert pooled["STRUCTURAL_OTHER"] == 20

    assert sum(pooled[stage] for stage in STAGES) == pooled["QUALIFIED"]

    assert sum(pooled_context.values()) == 599

    print(
        "POOLED_MACD_QUALIFIED_FUNNEL|"
        + "|".join(f"{stage}={pooled[stage]}" for stage in STAGES)
        + f"|QUALIFIED={pooled['QUALIFIED']}"
    )

    for (stage, direction, phase, regime), count in sorted(pooled_context.items()):
        if stage not in ("SAME_TIMEFRAME", "ACCEPTED"):
            continue

        print(
            f"POOLED_ALLIGATOR_CONTEXT|"
            f"STAGE={stage}|SIDE={direction}|"
            f"PHASE={phase}|REGIME={regime}|COUNT={count}"
        )

    assert before == {path: _sha(path) for path in guarded}

    print("T115_75_COUNTS_RECONCILED=OK")
    print("MACD_QUALIFIED_599_OF_599=OK")
    print("SAME_TIMEFRAME_483_OF_483=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("REJECT_IS_NOT_MISSED_TRADE=True")
    print("NO_HINDSIGHT_OUTCOME_USED=True")
    print("NO_GATE_COUNTERFACTUAL_EXECUTED=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_76_PRODUCTION_SAME_TIMEFRAME_REJECT_CONTEXT_AUDIT=OK")


if __name__ == "__main__":
    main()
