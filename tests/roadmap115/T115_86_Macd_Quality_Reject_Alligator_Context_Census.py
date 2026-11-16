# -*- coding: utf-8 -*-
"""RoadMap115 / T115-86: MACD Quality reject / Alligator context census.

TEST_ONLY / DATA_ONLY.

Зіставляє фактичні MACD Quality rejects із завершеними
Alligator observations того самого M15-бара.

Alligator context для відхиленого MACD — лише діагностика.
Production Alligator gate для такого кандидата не виконувався.

Майбутні ціни, PnL та counterfactual orders не використовуються.
Параметри MACD, Candidate F, Replay та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_DIR = ROOT / "tests" / "roadmap115"

for import_dir in (ROOT, ROADMAP_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))


MACD_REASONS = (
    "MACD_CROSS_TOO_FLAT",
    "MACD_EXTREMUM_DISTANCE_TOO_SMALL",
    "MACD_EXTREMUM_NOT_FOUND",
    "MACD_EXTREMUM_TOO_WEAK",
)

EXPECTED = {
    "2025": {
        "RAW": 3042,
        "REJECTED": 2626,
        "QUALIFIED": 416,
        "ACCEPTED": 42,
        "REASONS": (295, 404, 248, 1679),
    },
    "2026": {
        "RAW": 1962,
        "REJECTED": 1779,
        "QUALIFIED": 183,
        "ACCEPTED": 18,
        "REASONS": (185, 225, 160, 1209),
    },
}


def _sha(source_file: Path) -> str:
    """Повернути контрольний SHA256 файлу."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _context_bucket(
    observation: Any,
    direction: str,
    alligator: Any,
) -> str:
    """Класифікувати збережений стан без повторного gate."""
    assert direction in ("BUY", "SELL")

    regime = observation.regime
    phase = observation.regime_phase

    if regime == alligator.ALLIGATOR_REGIME_FLAT:
        return "FLAT"

    aligned_regime = (
        alligator.ALLIGATOR_REGIME_TREND_UP
        if direction == "BUY"
        else alligator.ALLIGATOR_REGIME_TREND_DOWN
    )

    opposite_regime = (
        alligator.ALLIGATOR_REGIME_TREND_DOWN
        if direction == "BUY"
        else alligator.ALLIGATOR_REGIME_TREND_UP
    )

    if regime == aligned_regime:
        alignment = "ALIGNED"
    elif regime == opposite_regime:
        alignment = "OPPOSITE"
    else:
        return "OTHER_REGIME"

    phases = {
        alligator.ALLIGATOR_REGIME_PHASE_ACTIVE: "ACTIVE",
        alligator.ALLIGATOR_REGIME_PHASE_STARTING: "STARTING",
        alligator.ALLIGATOR_REGIME_PHASE_ENDING: "ENDING",
    }

    phase_name = phases.get(phase, "OTHER_PHASE")

    return f"{phase_name}_{alignment}"


def main() -> None:
    """Виконати factual census відхилень MACD Quality."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")
    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))
    production_hashes = getattr(harness, "_production_hashes")
    broker_attempted = getattr(harness, "_broker_execution_attempted")

    guarded = (
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_macd_crossover_quality.py",
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_signal.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(source_file.is_file() for source_file in guarded)

    before = {source_file: _sha(source_file) for source_file in guarded}

    production_before = production_hashes()

    print("T115-86|TEST_ONLY|" "MACD_QUALITY_REJECT_ALLIGATOR_CONTEXT_CENSUS")
    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("MACD_REJECT_GATE=BEFORE_ALLIGATOR")
    print("ALLIGATOR_CONTEXT=SHADOW_DIAGNOSTIC_ONLY")
    print("COMPLETED_BAR_ONLY=True")
    print("FUTURE_PRICE_OR_PNL_USED=False")
    print("NEW_ENTRY_RULE=False")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled_reasons: Counter[str] = Counter()
    pooled_buckets: Counter[str] = Counter()
    pooled_reason_buckets: Counter[tuple[str, str]] = Counter()

    total_records = 0
    total_rejected = 0
    total_qualified = 0
    total_accepted = 0

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        session = runtime.replay_session
        assert session is not None
        assert session.completed

        signal_filter = runtime.algorithm.signal_filter
        assert signal_filter is not None

        observations = tuple(signal_filter.observations)

        observation_by_time = {item.timestamp: item for item in observations}

        assert len(observation_by_time) == len(observations)

        records = runtime.signal_records_for_ui()
        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]

        rejected = [
            record for record in records if record.source_reason_code in MACD_REASONS
        ]

        assert len(rejected) == expected["REJECTED"]

        qualified_count = len(records) - len(rejected)
        accepted_count = sum(record.accepted for record in records)

        assert qualified_count == expected["QUALIFIED"]
        assert accepted_count == expected["ACCEPTED"]

        reason_counts: Counter[str] = Counter()
        bucket_counts: Counter[str] = Counter()
        reason_buckets: Counter[tuple[str, str]] = Counter()
        side_buckets: Counter[tuple[str, str]] = Counter()

        for record in rejected:
            reason = record.source_reason_code

            assert reason in MACD_REASONS
            assert not record.accepted
            assert record.filter_reason_code == reason
            assert record.timeframe == "M15"
            assert record.direction in ("BUY", "SELL")

            assert record.timestamp in observation_by_time
            observation = observation_by_time[record.timestamp]

            assert observation.timeframe == "M15"
            assert observation.timestamp == record.timestamp

            # Спостереження сформовано не пізніше рішення MACD.
            assert observation.timestamp <= observation.available_at
            assert observation.available_at <= record.timestamp

            bucket = _context_bucket(
                observation,
                record.direction,
                alligator,
            )

            reason_counts[reason] += 1
            bucket_counts[bucket] += 1
            reason_buckets[reason, bucket] += 1
            side_buckets[record.direction, bucket] += 1

        assert sum(reason_counts.values()) == len(rejected)
        assert sum(bucket_counts.values()) == len(rejected)
        assert sum(reason_buckets.values()) == len(rejected)
        assert sum(side_buckets.values()) == len(rejected)

        for reason, expected_count in zip(
            MACD_REASONS,
            expected["REASONS"],
        ):
            assert reason_counts[reason] == expected_count, (
                spec.code,
                reason,
                reason_counts[reason],
                expected_count,
            )

        summary = runtime.historical_summary
        assert summary is not None
        assert summary.opened_trades == accepted_count

        print(
            f"MACD_CENSUS|PERIOD={spec.code}|"
            f"RAW={len(records)}|"
            f"MACD_REJECTED={len(rejected)}|"
            f"MACD_QUALIFIED={qualified_count}|"
            f"ACCEPTED={accepted_count}"
        )

        for reason in MACD_REASONS:
            print(
                f"MACD_REJECT_REASON|PERIOD={spec.code}|"
                f"REASON={reason}|COUNT={reason_counts[reason]}"
            )

        for bucket, count in sorted(bucket_counts.items()):
            print(
                f"SHADOW_ALLIGATOR_CONTEXT|"
                f"PERIOD={spec.code}|"
                f"BUCKET={bucket}|COUNT={count}"
            )

        for (reason, bucket), count in sorted(reason_buckets.items()):
            print(
                f"MACD_REASON_CONTEXT|PERIOD={spec.code}|"
                f"REASON={reason}|BUCKET={bucket}|COUNT={count}"
            )

        for (side, bucket), count in sorted(side_buckets.items()):
            if bucket != "ACTIVE_ALIGNED":
                continue

            print(
                f"ACTIVE_ALIGNED_BY_SIDE|"
                f"PERIOD={spec.code}|"
                f"SIDE={side}|COUNT={count}"
            )

        pooled_reasons.update(reason_counts)
        pooled_buckets.update(bucket_counts)
        pooled_reason_buckets.update(reason_buckets)

        total_records += len(records)
        total_rejected += len(rejected)
        total_qualified += qualified_count
        total_accepted += accepted_count

        print(f"MACD_CONTEXT_RECONCILIATION={spec.code}:OK")

    assert total_records == 5004
    assert total_rejected == 4405
    assert total_qualified == 599
    assert total_accepted == 60

    assert pooled_reasons == Counter(
        {
            "MACD_CROSS_TOO_FLAT": 480,
            "MACD_EXTREMUM_DISTANCE_TOO_SMALL": 629,
            "MACD_EXTREMUM_NOT_FOUND": 408,
            "MACD_EXTREMUM_TOO_WEAK": 2888,
        }
    )

    assert sum(pooled_buckets.values()) == 4405
    assert sum(pooled_reason_buckets.values()) == 4405

    print(
        "POOLED_MACD_CENSUS|"
        f"RAW={total_records}|"
        f"MACD_REJECTED={total_rejected}|"
        f"MACD_QUALIFIED={total_qualified}|"
        f"ACCEPTED={total_accepted}"
    )

    for bucket, count in sorted(pooled_buckets.items()):
        print(f"POOLED_SHADOW_CONTEXT|" f"BUCKET={bucket}|COUNT={count}")

    for reason in MACD_REASONS:
        print(f"POOLED_MACD_REASON|" f"REASON={reason}|COUNT={pooled_reasons[reason]}")

    assert before == {source_file: _sha(source_file) for source_file in guarded}

    assert production_before == production_hashes()

    print("T115_75_MACD_REJECT_4405_OF_4405=OK")
    print("PRODUCTION_ACCEPTED_60_OF_60=OK")
    print("SHADOW_CONTEXT_ACCOUNTING=OK")
    print("ALLIGATOR_GATE_NOT_BYPASSED=True")
    print("REJECT_IS_NOT_MISSED_TRADE=True")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_FUTURE_OUTCOME_OR_NEW_ENTRY_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_86_MACD_QUALITY_REJECT_ALLIGATOR_CONTEXT_CENSUS=OK")


if __name__ == "__main__":
    main()
