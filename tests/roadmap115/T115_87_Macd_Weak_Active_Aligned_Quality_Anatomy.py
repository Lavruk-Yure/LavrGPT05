# -*- coding: utf-8 -*-
"""RoadMap115 / T115-87: MACD weak + Alligator ACTIVE_ALIGNED anatomy.

TEST_ONLY / DATA_ONLY.

Зіставляє відхилені MACD_EXTREMUM_TOO_WEAK зі штатними
MACD quality diagnostics на тих самих завершених M15-барах.
Порівнює ACTIVE_ALIGNED з рештою цих відхилень і рахує,
які інші MACD-критерії також не пройдені.

Параметри, сигнали, торгові правила та MD7 не змінюються.
Немає майбутніх цін, контрфактичних входів або PnL.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter, defaultdict
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_DIR = ROOT / "tests" / "roadmap115"

for import_dir in (ROOT, ROADMAP_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))


REASON = "MACD_EXTREMUM_TOO_WEAK"

EXPECTED = {
    "2025": {
        "RAW": 3042,
        "WEAK": 1679,
        "ACTIVE_ALIGNED": 356,
        "ACCEPTED": 42,
    },
    "2026": {
        "RAW": 1962,
        "WEAK": 1209,
        "ACTIVE_ALIGNED": 255,
        "ACCEPTED": 18,
    },
}

GROUPS = (
    "ACTIVE_ALIGNED",
    "OTHER_CONTEXT",
)


def _sha(source_file: Path) -> str:
    """Повернути SHA256 без зміни джерела."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _active_aligned(
    record: Any,
    observation: Any,
    alligator: Any,
) -> bool:
    """Перевірити діагностичний стан на завершеному барі."""
    if observation.regime_phase != alligator.ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False

    return (
        record.direction == "BUY"
        and observation.regime == alligator.ALLIGATOR_REGIME_TREND_UP
        or record.direction == "SELL"
        and observation.regime == alligator.ALLIGATOR_REGIME_TREND_DOWN
    )


def _report(
    period: str,
    group: str,
    entries: list[tuple[Any, Any]],
    cutoff: float,
) -> None:
    """Показати causal quality-факти без підбору порогів."""
    assert entries

    ratio_values: list[float] = []
    sides: Counter[str] = Counter()
    secondary: Counter[str] = Counter()

    for record, diagnostic in entries:
        prominence = diagnostic.extremum_prominence

        assert prominence is not None
        assert math.isfinite(prominence)
        assert 0.0 <= prominence < cutoff

        ratio = prominence / cutoff
        assert 0.0 <= ratio < 1.0

        ratio_values.append(ratio)
        sides[record.direction] += 1

        distance_pass = diagnostic.criterion_distance_pass
        angle_pass = diagnostic.criterion_angle_pass

        secondary["DISTANCE_PASS" if distance_pass else "DISTANCE_FAIL"] += 1

        secondary["ANGLE_PASS" if angle_pass else "ANGLE_FAIL"] += 1

        if distance_pass and angle_pass:
            secondary["ONLY_PROMINENCE_FAILED"] += 1
        else:
            secondary["MULTIPLE_CRITERIA_FAILED"] += 1

    assert sides["BUY"] + sides["SELL"] == len(entries)

    assert secondary["ONLY_PROMINENCE_FAILED"] + secondary[
        "MULTIPLE_CRITERIA_FAILED"
    ] == len(entries)

    assert secondary["DISTANCE_PASS"] + secondary["DISTANCE_FAIL"] == len(entries)

    assert secondary["ANGLE_PASS"] + secondary["ANGLE_FAIL"] == len(entries)

    print(
        f"WEAK_DIAGNOSTIC|PERIOD={period}|"
        f"GROUP={group}|N={len(entries)}|"
        f"BUY={sides['BUY']}|SELL={sides['SELL']}|"
        f"PROMINENCE_TO_PRODUCTION_MIN_MIN={min(ratio_values):.4f}|"
        f"MEDIAN={statistics.median(ratio_values):.4f}|"
        f"MAX={max(ratio_values):.4f}"
    )

    print(
        f"WEAK_SECONDARY_CRITERIA|PERIOD={period}|"
        f"GROUP={group}|"
        f"ONLY_PROMINENCE_FAILED="
        f"{secondary['ONLY_PROMINENCE_FAILED']}|"
        f"MULTIPLE_CRITERIA_FAILED="
        f"{secondary['MULTIPLE_CRITERIA_FAILED']}|"
        f"DISTANCE_FAIL={secondary['DISTANCE_FAIL']}|"
        f"ANGLE_FAIL={secondary['ANGLE_FAIL']}"
    )


def main() -> None:
    """Виконати незмінний Replay і звірити всі weak diagnostics."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))
    production_hashes = getattr(harness, "_production_hashes")
    broker_attempted = getattr(
        harness,
        "_broker_execution_attempted",
    )

    guarded = (
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_macd_crossover_quality.py",
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(source_file.is_file() for source_file in guarded)

    before = {source_file: _sha(source_file) for source_file in guarded}

    production_before = production_hashes()

    print("T115-87|TEST_ONLY|" "MACD_WEAK_ACTIVE_ALIGNED_QUALITY_ANATOMY")
    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("QUALITY_DIAGNOSTICS=ACTUAL_MACD_SOURCE|" "COMPLETED_BARS_ONLY=True")
    print("ALLIGATOR_CONTEXT=SHADOW_ONLY|NOT_PRODUCTION_GATE=True")
    print("NO_NEW_THRESHOLDS_OR_OUTCOME_LABELS=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled: dict[
        str,
        list[tuple[Any, Any]],
    ] = defaultdict(list)

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        assert runtime.replay_session is not None
        assert runtime.replay_session.completed

        algorithm = runtime.algorithm

        assert type(algorithm) is alligator.WorkspaceMacdAlligatorReplayAlgorithm

        source = algorithm.source
        signal_filter = algorithm.signal_filter

        assert source is not None
        assert signal_filter is not None

        cutoff = float(source.extremum_min_prominence)

        assert math.isfinite(cutoff)
        assert cutoff > 0

        diagnostics = tuple(source.quality_diagnostics)

        diagnostic_by_key = {
            (item.timestamp, item.direction): item for item in diagnostics
        }

        assert len(diagnostic_by_key) == len(diagnostics)

        observations = tuple(signal_filter.observations)

        observation_by_time = {item.timestamp: item for item in observations}

        assert len(observation_by_time) == len(observations)

        records = runtime.signal_records_for_ui()

        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]

        assert sum(record.accepted for record in records) == expected["ACCEPTED"]

        weak_records = [
            record for record in records if record.source_reason_code == REASON
        ]

        assert len(weak_records) == expected["WEAK"]

        groups: dict[
            str,
            list[tuple[Any, Any]],
        ] = {name: [] for name in GROUPS}

        for record in weak_records:
            assert not record.accepted
            assert record.filter_reason_code == REASON
            assert record.timeframe == "M15"
            assert record.direction in ("BUY", "SELL")

            key = record.timestamp, record.direction

            assert key in diagnostic_by_key

            diagnostic = diagnostic_by_key[key]

            assert diagnostic.reason_code == REASON
            assert diagnostic.extremum_found
            assert diagnostic.criterion_extremum_pass
            assert not diagnostic.criterion_prominence_pass
            assert not diagnostic.final_quality_pass

            assert diagnostic.extremum_timestamp is not None
            assert diagnostic.extremum_timestamp < diagnostic.timestamp

            observation = observation_by_time[record.timestamp]

            assert observation.timestamp <= observation.available_at <= record.timestamp

            group = (
                "ACTIVE_ALIGNED"
                if _active_aligned(
                    record,
                    observation,
                    alligator,
                )
                else "OTHER_CONTEXT"
            )

            groups[group].append((record, diagnostic))

        assert len(groups["ACTIVE_ALIGNED"]) == expected["ACTIVE_ALIGNED"]

        assert sum(len(group) for group in groups.values()) == expected["WEAK"]

        print(
            f"MACD_WEAK_BASELINE|PERIOD={spec.code}|"
            f"RAW={len(records)}|"
            f"WEAK={len(weak_records)}|"
            f"ACTIVE_ALIGNED={len(groups['ACTIVE_ALIGNED'])}|"
            f"PRODUCTION_PROMINENCE_MIN={cutoff:.10g}"
        )

        for name in GROUPS:
            _report(
                spec.code,
                name,
                groups[name],
                cutoff,
            )

            pooled[name].extend(groups[name])

        print(f"WEAK_DIAGNOSTIC_RECONCILIATION=" f"{spec.code}:OK")

    assert len(pooled["ACTIVE_ALIGNED"]) == 611
    assert len(pooled["OTHER_CONTEXT"]) == 2277

    assert sum(len(group) for group in pooled.values()) == 2888

    for name in GROUPS:
        entries = pooled[name]

        # Для pooled використовуємо тільки логічні прапорці.
        # Однакового prominence cutoff між роками не припускаємо.
        only_prominence = sum(
            item.criterion_distance_pass and item.criterion_angle_pass
            for _, item in entries
        )

        print(
            f"POOLED_WEAK_CRITERIA|GROUP={name}|"
            f"N={len(entries)}|"
            f"ONLY_PROMINENCE_FAILED={only_prominence}|"
            f"MULTIPLE_CRITERIA_FAILED="
            f"{len(entries) - only_prominence}"
        )

    assert before == {source_file: _sha(source_file) for source_file in guarded}

    assert production_before == production_hashes()

    print("MACD_WEAK_2888_OF_2888=OK")
    print("WEAK_ACTIVE_ALIGNED_611_OF_611=OK")
    print("QUALITY_DIAGNOSTIC_SOURCE_PARITY=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_THRESHOLD_OPTIMIZATION_OR_COUNTERFACTUAL_TRADING=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_87_MACD_WEAK_ACTIVE_ALIGNED_QUALITY_ANATOMY=OK")


if __name__ == "__main__":
    main()
