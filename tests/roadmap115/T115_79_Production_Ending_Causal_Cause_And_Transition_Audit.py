# -*- coding: utf-8 -*-
"""RoadMap115 / T115-79: causal anatomy of production ENDING rejects.

TEST_ONLY / DATA_ONLY.

Класифікує 104 ENDING_ALIGNED сигналів із canonical M15 Replay:
1) FLAT_HYSTERESIS: raw FLAT, але попередній TREND ще збережений;
2) STATE_MISMATCH: raw TREND, але порядок ліній не відповідає regime.

Використовує лише вже збережені контексти завершених барів.
Не змінює production gate, не моделює додаткові угоди та не оцінює PnL.
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

for directory in (ROOT, ROADMAP_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


EXPECTED = {
    "2025": {
        "RAW": 3042,
        "QUALIFIED": 416,
        "ENDING": 71,
        "BUY": 40,
        "SELL": 31,
        "ACCEPTED": 42,
    },
    "2026": {
        "RAW": 1962,
        "QUALIFIED": 183,
        "ENDING": 33,
        "BUY": 17,
        "SELL": 16,
        "ACCEPTED": 18,
    },
}


def _hash_file(path: Path) -> str:
    """Повернути контрольний SHA256 без зміни файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_context(record: Any) -> tuple[Any, Any]:
    """Перевірити причинність знімка та отримати поточний/попередній бар."""
    context = record.filter_context
    assert context is not None
    assert context.timeframe == "M15"

    history = context.diagnostic_observations
    assert len(history) == 3, (record.timestamp, len(history))

    current = history[-1]
    previous = history[-2]

    assert current.timestamp == context.observation_timestamp
    assert current.available_at == context.available_at
    assert current.regime == context.regime
    assert current.regime_phase == context.regime_phase
    assert current.normalized_slope == context.normalized_slope
    assert current.normalized_opening == context.normalized_opening
    assert current.available_at <= record.timestamp

    for index, observation in enumerate(history):
        assert observation.timestamp <= observation.available_at
        assert observation.available_at <= context.available_at
        if index:
            assert history[index - 1].timestamp < observation.timestamp
            assert history[index - 1].available_at <= observation.available_at

    return current, previous


def _cause(record: Any, current: Any, alligator: Any) -> tuple[str, str]:
    """Повторити тільки дві фактичні гілки визначення ENDING."""
    assert current.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ENDING

    expected_regime = (
        alligator.ALLIGATOR_REGIME_TREND_UP
        if record.direction == "BUY"
        else alligator.ALLIGATOR_REGIME_TREND_DOWN
    )
    aligned_state = (
        alligator.ALLIGATOR_STATE_BULLISH
        if record.direction == "BUY"
        else alligator.ALLIGATOR_STATE_BEARISH
    )

    assert current.regime == expected_regime
    assert current.normalized_slope is not None
    assert current.normalized_opening is not None

    raw_flat = (
        current.normalized_slope <= alligator.ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_SLOPE
        and current.normalized_opening
        <= alligator.ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING
    )

    if raw_flat:
        # При raw FLAT і збереженому TREND production примусово ставить ENDING.
        cause = "FLAT_HYSTERESIS"
    else:
        # За raw TREND _alligator_regime_phase повертає ENDING лише
        # коли поточний порядок ліній не відповідає regime.
        assert current.state != aligned_state, (record.timestamp, current.state)
        cause = "STATE_MISMATCH"

    line_order = "ALIGNED" if current.state == aligned_state else "MISALIGNED"
    return cause, line_order


def main() -> None:
    """Перевірити причинну класифікацію 104 відхилень ENDING_ALIGNED."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")
    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))
    broker_execution_attempted = getattr(harness, "_broker_execution_attempted")
    production_hashes = getattr(harness, "_production_hashes")

    guarded_paths = (
        ROOT / "core" / "workspace_alligator.py",
        ROOT / "core" / "workspace_signal.py",
        ROOT / "core" / "workspace_runtime.py",
        ROOT / "core" / "workspace_replay_execution.py",
        ROOT / "doc" / "LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )
    assert all(path.is_file() for path in guarded_paths)
    before = {path: _hash_file(path) for path in guarded_paths}
    production_before = production_hashes()

    print("T115-79|TEST_ONLY|PRODUCTION_ENDING_CAUSAL_CAUSE_TRANSITION_AUDIT")
    print("SOURCE=CANONICAL_T105_18_PRODUCTION_M15_REPLAY")
    print("FEATURES=FROZEN_COMPLETED_BAR_CONTEXT_ONLY")
    print("PNL_OUTCOME_USED=False|COUNTERFACTUAL_EXECUTED=False")
    print(
        "PRODUCTION_FLAT_THRESHOLDS|"
        f"SLOPE={alligator.ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_SLOPE}|"
        f"OPENING={alligator.ALLIGATOR_REGIME_FLAT_MAX_NORMALIZED_OPENING}"
    )

    assert tuple(spec.code for spec in periods) == ("2025", "2026")
    pooled_causes: Counter[str] = Counter()
    pooled_transitions: Counter[str] = Counter()
    total_ending = 0

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)
        assert broker_requests == 0
        assert not broker_execution_attempted(runtime)
        assert runtime.replay_session is not None
        assert runtime.replay_session.completed

        records = runtime.signal_records_for_ui()
        qualified = [
            record
            for record in records
            if record.accepted or record.source_reason_code == "MACD_CROSS_ACCEPTED"
        ]
        ending = [
            record
            for record in qualified
            if not record.accepted
            and record.filter_reason_code
            in {
                "ALLIGATOR_SAME_TIMEFRAME_BUY_ENDING_REJECT",
                "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT",
            }
            and record.filter_context is not None
            and record.filter_context.regime_phase
            == alligator.ALLIGATOR_REGIME_PHASE_ENDING
            and (
                record.direction == "BUY"
                and record.filter_context.regime == alligator.ALLIGATOR_REGIME_TREND_UP
                or record.direction == "SELL"
                and record.filter_context.regime
                == alligator.ALLIGATOR_REGIME_TREND_DOWN
            )
        ]

        expected = EXPECTED[spec.code]
        assert len(records) == expected["RAW"]
        assert len(qualified) == expected["QUALIFIED"]
        assert len(ending) == expected["ENDING"]
        assert sum(record.direction == "BUY" for record in ending) == expected["BUY"]
        assert sum(record.direction == "SELL" for record in ending) == expected["SELL"]
        assert runtime.historical_summary is not None
        assert runtime.historical_summary.opened_trades == expected["ACCEPTED"]

        causes: Counter[str] = Counter()
        transitions: Counter[str] = Counter()
        details: Counter[tuple[str, str, str, str]] = Counter()
        unique_observations: set[tuple[Any, str]] = set()

        for record in ending:
            current, previous = _check_context(record)
            cause, line_order = _cause(record, current, alligator)
            transition = (
                "CONTINUED_ENDING_SAME_REGIME"
                if previous.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ENDING
                and previous.regime == current.regime
                else "NEW_ENDING_OR_REGIME_CHANGE"
            )
            causes[cause] += 1
            transitions[transition] += 1
            details[(cause, transition, record.direction, line_order)] += 1
            unique_observations.add((current.timestamp, record.direction))

        assert sum(causes.values()) == len(ending)
        assert sum(transitions.values()) == len(ending)
        assert sum(details.values()) == len(ending)

        print(
            f"ENDING_BASELINE|PERIOD={spec.code}|"
            f"RAW={len(records)}|QUALIFIED={len(qualified)}|"
            f"ENDING_ALIGNED={len(ending)}|"
            f"DISTINCT_TIMESTAMP_SIDE={len(unique_observations)}"
        )
        for cause, count in sorted(causes.items()):
            print(f"ENDING_CAUSE|PERIOD={spec.code}|CAUSE={cause}|COUNT={count}")
        for transition, count in sorted(transitions.items()):
            print(
                f"ENDING_TRANSITION|PERIOD={spec.code}|TYPE={transition}|COUNT={count}"
            )
        for (cause, transition, direction, line_order), count in sorted(
            details.items()
        ):
            print(
                f"ENDING_DETAIL|PERIOD={spec.code}|CAUSE={cause}|"
                f"TRANSITION={transition}|SIDE={direction}|"
                f"STATE_ORDER={line_order}|COUNT={count}"
            )

        pooled_causes.update(causes)
        pooled_transitions.update(transitions)
        total_ending += len(ending)
        print(f"ENDING_CAUSE_RECONCILIATION={spec.code}:OK")

    assert total_ending == 104
    assert sum(pooled_causes.values()) == 104
    assert sum(pooled_transitions.values()) == 104

    for cause, count in sorted(pooled_causes.items()):
        print(f"POOLED_ENDING_CAUSE|CAUSE={cause}|COUNT={count}")
    for transition, count in sorted(pooled_transitions.items()):
        print(f"POOLED_ENDING_TRANSITION|TYPE={transition}|COUNT={count}")

    assert before == {path: _hash_file(path) for path in guarded_paths}
    assert production_before == production_hashes()

    print("ENDING_ALIGNED_104_OF_104=OK")
    print("T115_77_BASELINES_RECONCILED=OK")
    print("COMPLETED_BAR_CONTEXT_CAUSALITY=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("REJECT_IS_NOT_MISSED_TRADE=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_79_PRODUCTION_ENDING_CAUSAL_CAUSE_TRANSITION_AUDIT=OK")


if __name__ == "__main__":
    main()
