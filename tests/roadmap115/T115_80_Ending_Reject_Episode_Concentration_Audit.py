# -*- coding: utf-8 -*-
"""RoadMap115 / T115-80: ENDING reject episode concentration.

TEST_ONLY / DATA_ONLY.

Групує 104 production ENDING_ALIGNED rejects за епізодами
повної послідовності M15 Alligator observations.

Епізод: послідовні наявні observations із тією самою
ENDING phase та regime. Пропуски часу не розривають
епізод автоматично, але враховуються окремо.

Порядковий номер у момент сигналу обчислюється причинно.
Підсумкова кількість сигналів в епізоді — ретроспективна
описова статистика, не ознака для ENTRY.

Без додаткових угод, outcome labels і production-змін.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from datetime import timedelta
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
        "ACCEPTED": 42,
        "ENDING": 71,
        "FIRST": 11,
        "CONTINUED": 60,
    },
    "2026": {
        "RAW": 1962,
        "QUALIFIED": 183,
        "ACCEPTED": 18,
        "ENDING": 33,
        "FIRST": 5,
        "CONTINUED": 28,
    },
}

ENDING_REASONS = {
    "ALLIGATOR_SAME_TIMEFRAME_BUY_ENDING_REJECT",
    "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT",
}

M15_SPAN = timedelta(minutes=15)


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _episode_index(
    observations: tuple[Any, ...],
    alligator: Any,
) -> dict[Any, tuple[int, int, int]]:
    """Пронумерувати ENDING за вже побаченими observations."""
    index: dict[Any, tuple[int, int, int]] = {}

    previous = None
    episode_id = 0
    ordinal = 0
    gaps = 0

    valid_regimes = {
        alligator.ALLIGATOR_REGIME_TREND_UP,
        alligator.ALLIGATOR_REGIME_TREND_DOWN,
    }

    for observation in observations:
        assert observation.timeframe == "M15"
        assert observation.timestamp <= observation.available_at

        if previous is not None:
            assert observation.timestamp > previous.timestamp
            assert observation.available_at >= previous.available_at

        is_ending = (
            observation.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ENDING
            and observation.regime in valid_regimes
        )

        if is_ending:
            continued = (
                previous is not None
                and previous.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ENDING
                and previous.regime == observation.regime
            )

            if continued:
                ordinal += 1

                if observation.timestamp - previous.timestamp > M15_SPAN:
                    gaps += 1
            else:
                episode_id += 1
                ordinal = 1
                gaps = 0

            assert observation.timestamp not in index

            index[observation.timestamp] = (
                episode_id,
                ordinal,
                gaps,
            )

        previous = observation

    return index


def _is_ending_aligned(
    record: Any,
    alligator: Any,
) -> bool:
    """Відібрати тільки production ENDING_ALIGNED."""
    if record.accepted:
        return False

    if record.source_reason_code != "MACD_CROSS_ACCEPTED":
        return False

    if record.filter_reason_code not in ENDING_REASONS:
        return False

    context = record.filter_context

    if context is None:
        return False

    if context.regime_phase != alligator.ALLIGATOR_REGIME_PHASE_ENDING:
        return False

    return (
        record.direction == "BUY"
        and context.regime == alligator.ALLIGATOR_REGIME_TREND_UP
        or record.direction == "SELL"
        and context.regime == alligator.ALLIGATOR_REGIME_TREND_DOWN
    )


def _ordinal_bucket(ordinal: int) -> str:
    """Статичні діагностичні категорії, не торгові пороги."""
    if ordinal == 1:
        return "BAR_1"

    if ordinal <= 3:
        return "BARS_2_3"

    if ordinal <= 8:
        return "BARS_4_8"

    return "BAR_9_PLUS"


def main() -> None:
    """Порахувати незалежні за епізодом групи reject records."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))
    production_hashes = getattr(
        harness,
        "_production_hashes",
    )
    broker_attempted = getattr(
        harness,
        "_broker_execution_attempted",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "core/workspace_signal.py",
        ROOT / "core/workspace_replay_execution.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    production_before = production_hashes()

    print("T115-80|TEST_ONLY|" "ENDING_REJECT_EPISODE_CONCENTRATION_AUDIT")
    print("SOURCE=CANONICAL_T105_18_PRODUCTION_M15_REPLAY")
    print("EPISODE=CONTIGUOUS_OBSERVED_ENDING_SAME_REGIME")
    print("SIGNAL_TIME_ORDINAL_CAUSAL=True")
    print("EPISODE_REJECT_COUNT_RETROSPECTIVE=True")
    print("NO_FUTURE_PNL_OR_COUNTERFACTUAL=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled_signals = 0
    pooled_episodes = 0
    pooled_first = 0
    pooled_continued = 0
    pooled_repeats = 0

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        assert runtime.replay_session is not None
        assert runtime.replay_session.completed

        algorithm = runtime.algorithm

        assert type(algorithm) is alligator.WorkspaceMacdAlligatorReplayAlgorithm

        signal_filter = algorithm.signal_filter
        assert signal_filter is not None

        observations = signal_filter.observations

        episode_index = _episode_index(
            observations,
            alligator,
        )

        records = runtime.signal_records_for_ui()

        qualified = [
            record
            for record in records
            if record.accepted or record.source_reason_code == "MACD_CROSS_ACCEPTED"
        ]

        ending = [
            record for record in qualified if _is_ending_aligned(record, alligator)
        ]

        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]
        assert len(qualified) == expected["QUALIFIED"]
        assert len(ending) == expected["ENDING"]

        summary = runtime.historical_summary
        assert summary is not None
        assert summary.opened_trades == expected["ACCEPTED"]

        observation_by_time = {
            observation.timestamp: observation for observation in observations
        }

        assert len(observation_by_time) == len(observations)

        signal_counts: Counter[int] = Counter()
        ordinal_counts: Counter[str] = Counter()
        sides: Counter[str] = Counter()

        first = 0
        continued = 0
        signals_with_gap = 0

        unique_signal_keys: set[tuple[Any, str]] = set()

        for record in ending:
            context = record.filter_context
            assert context is not None

            timestamp = context.observation_timestamp
            assert timestamp in episode_index

            observation = observation_by_time[timestamp]

            assert observation.available_at <= record.timestamp
            assert observation.regime == context.regime
            assert observation.regime_phase == context.regime_phase

            assert context.available_at == observation.available_at

            episode_id, ordinal, gaps = episode_index[timestamp]

            assert ordinal >= 1
            assert gaps >= 0

            unique_key = (timestamp, record.direction)
            assert unique_key not in unique_signal_keys
            unique_signal_keys.add(unique_key)

            signal_counts[episode_id] += 1
            ordinal_counts[_ordinal_bucket(ordinal)] += 1
            sides[record.direction] += 1

            if ordinal == 1:
                first += 1
            else:
                continued += 1

            if gaps > 0:
                signals_with_gap += 1

        assert len(unique_signal_keys) == len(ending)
        assert first == expected["FIRST"]
        assert continued == expected["CONTINUED"]

        assert first + continued == len(ending)
        assert sum(ordinal_counts.values()) == len(ending)

        episode_count = len(signal_counts)

        assert 1 <= episode_count <= len(ending)

        repeated_records = len(ending) - episode_count

        episode_sizes = Counter(signal_counts.values())

        assert sum(size * count for size, count in episode_sizes.items()) == len(ending)

        assert sum(episode_sizes.values()) == episode_count

        print(
            f"ENDING_EPISODE_CENSUS|PERIOD={spec.code}|"
            f"SIGNALS={len(ending)}|"
            f"EPISODES_WITH_REJECT={episode_count}|"
            f"BUY={sides['BUY']}|SELL={sides['SELL']}|"
            f"FIRST_OBSERVATION={first}|"
            f"CONTINUED_OBSERVATION={continued}|"
            f"REPEATED_RECORDS_AFTER_FIRST={repeated_records}|"
            f"MAX_SIGNALS_PER_EPISODE={max(signal_counts.values())}|"
            f"SIGNALS_WITH_PRIOR_OBSERVED_GAP={signals_with_gap}"
        )

        for size, count in sorted(episode_sizes.items()):
            print(
                f"EPISODE_SIGNAL_DISTRIBUTION|"
                f"PERIOD={spec.code}|"
                f"SIGNALS_PER_EPISODE={size}|"
                f"EPISODES={count}"
            )

        for bucket, count in sorted(ordinal_counts.items()):
            print(
                f"ENDING_SIGNAL_ORDINAL|"
                f"PERIOD={spec.code}|"
                f"BUCKET={bucket}|COUNT={count}"
            )

        pooled_signals += len(ending)
        pooled_episodes += episode_count
        pooled_first += first
        pooled_continued += continued
        pooled_repeats += repeated_records

        print(f"ENDING_EPISODE_RECONCILIATION={spec.code}:OK")

    assert pooled_signals == 104
    assert pooled_first == 16
    assert pooled_continued == 88
    assert pooled_episodes + pooled_repeats == pooled_signals

    print(
        f"POOLED_ENDING_EPISODES|"
        f"SIGNALS={pooled_signals}|"
        f"EPISODES_WITH_REJECT={pooled_episodes}|"
        f"REPEATED_RECORDS_AFTER_FIRST={pooled_repeats}|"
        f"FIRST_OBSERVATION={pooled_first}|"
        f"CONTINUED_OBSERVATION={pooled_continued}"
    )

    assert before == {path: _sha(path) for path in guarded}

    assert production_before == production_hashes()

    print("T115_79_COUNTS_RECONCILED=OK")
    print("ENDING_ALIGNED_104_OF_104=OK")
    print("ENDING_TRANSITIONS_16_PLUS_88=OK")
    print("EPISODE_ACCOUNTING=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_OUTCOME_LABELS_USED=True")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_80_ENDING_REJECT_EPISODE_CONCENTRATION_AUDIT=OK")


if __name__ == "__main__":
    main()
