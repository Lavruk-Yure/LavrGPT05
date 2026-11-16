# -*- coding: utf-8 -*-
"""RoadMap115 / T115-88: MACD weak ACTIVE trend episode coverage.

TEST_ONLY / DATA_ONLY.

Порівнює weak MACD rejects та accepted production-сигнали
в епізодах ACTIVE Alligator на завершених M15-барах.

Порядковий номер бара обчислюється причинно.
Підсумкове покриття епізодів є ретроспективною статистикою,
не ознакою для ENTRY.

Без нових угод, outcome PnL і production-змін.
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

for import_dir in (ROOT, ROADMAP_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))


EXPECTED = {
    "2025": {
        "RAW": 3042,
        "WEAK_ALL": 1679,
        "WEAK_ACTIVE": 356,
        "ACCEPTED": 42,
    },
    "2026": {
        "RAW": 1962,
        "WEAK_ALL": 1209,
        "WEAK_ACTIVE": 255,
        "ACCEPTED": 18,
    },
}

WEAK_REASON = "MACD_EXTREMUM_TOO_WEAK"
M15 = timedelta(minutes=15)


def _sha(source_file: Path) -> str:
    """Обчислити хеш контрольного файлу."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _active_aligned(
    observation: Any,
    direction: str,
    alligator: Any,
) -> bool:
    """Перевірити ACTIVE і відповідність напрямку без запуску gate."""
    if observation.regime_phase != alligator.ALLIGATOR_REGIME_PHASE_ACTIVE:
        return False

    return (
        direction == "BUY"
        and observation.regime == alligator.ALLIGATOR_REGIME_TREND_UP
        or direction == "SELL"
        and observation.regime == alligator.ALLIGATOR_REGIME_TREND_DOWN
    )


def _index_episodes(
    observations: tuple[Any, ...],
    alligator: Any,
) -> tuple[dict[Any, tuple[int, int, int]], int]:
    """Побудувати причинний порядковий номер ACTIVE."""
    episodes: dict[Any, tuple[int, int, int]] = {}

    previous = None
    episode_id = 0
    ordinal = 0
    gap_count = 0

    eligible = {
        alligator.ALLIGATOR_REGIME_TREND_UP,
        alligator.ALLIGATOR_REGIME_TREND_DOWN,
    }

    for item in observations:
        assert item.timeframe == "M15"
        assert item.timestamp <= item.available_at

        if previous is not None:
            assert item.timestamp > previous.timestamp
            assert item.available_at >= previous.available_at

        active = (
            item.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ACTIVE
            and item.regime in eligible
        )

        if active:
            continuation = (
                previous is not None
                and previous.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ACTIVE
                and previous.regime == item.regime
            )

            if continuation:
                ordinal += 1

                if item.timestamp - previous.timestamp > M15:
                    gap_count += 1
            else:
                episode_id += 1
                ordinal = 1
                gap_count = 0

            assert item.timestamp not in episodes

            episodes[item.timestamp] = (
                episode_id,
                ordinal,
                gap_count,
            )

        previous = item

    return episodes, episode_id


def _bucket(ordinal: int) -> str:
    """Згрупувати причинний порядковий номер."""
    if ordinal == 1:
        return "BAR_1"

    if ordinal <= 3:
        return "BARS_2_3"

    if ordinal <= 8:
        return "BARS_4_8"

    return "BAR_9_PLUS"


def main() -> None:
    """Порахувати покриття ACTIVE-епізодів сигналами."""
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
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_signal.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(source_file.is_file() for source_file in guarded)

    before = {source_file: _sha(source_file) for source_file in guarded}

    production_before = production_hashes()

    print("T115-88|TEST_ONLY|" "MACD_WEAK_ACTIVE_TREND_EPISODE_COVERAGE")
    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("EPISODE=CONTIGUOUS_OBSERVED_ACTIVE_SAME_REGIME")
    print("SIGNAL_ORDINAL=CAUSAL|EPISODE_COVERAGE=RETROSPECTIVE")
    print("NO_FUTURE_PRICE_OR_PNL=True|NO_NEW_ORDERS=True")

    assert tuple(spec.code for spec in periods) == (
        "2025",
        "2026",
    )

    pooled: Counter[str] = Counter()

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        assert runtime.replay_session is not None
        assert runtime.replay_session.completed

        signal_filter = runtime.algorithm.signal_filter
        assert signal_filter is not None

        observations = tuple(signal_filter.observations)

        by_timestamp = {item.timestamp: item for item in observations}

        assert len(by_timestamp) == len(observations)

        indexed, episode_total = _index_episodes(
            observations,
            alligator,
        )

        records = runtime.signal_records_for_ui()
        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]

        assert (
            sum(record.source_reason_code == WEAK_REASON for record in records)
            == expected["WEAK_ALL"]
        )

        assert sum(record.accepted for record in records) == expected["ACCEPTED"]

        assert runtime.historical_summary is not None
        assert runtime.historical_summary.opened_trades == expected["ACCEPTED"]

        weak_by_episode: Counter[int] = Counter()
        accepted_by_episode: Counter[int] = Counter()
        weak_ordinals: Counter[str] = Counter()
        weak_sides: Counter[str] = Counter()

        weak_with_prior_gap = 0

        for record in records:
            weak = record.source_reason_code == WEAK_REASON
            accepted = record.accepted

            if not weak and not accepted:
                continue

            assert record.timestamp in by_timestamp

            obs = by_timestamp[record.timestamp]

            assert obs.available_at <= record.timestamp
            assert record.direction in ("BUY", "SELL")

            if not _active_aligned(
                obs,
                record.direction,
                alligator,
            ):
                if accepted:
                    raise AssertionError(
                        (
                            "ACCEPTED_NOT_ACTIVE_ALIGNED",
                            spec.code,
                            record.timestamp,
                        )
                    )
                continue

            episode_id, ordinal, prior_gaps = indexed[record.timestamp]

            if weak:
                assert not accepted

                weak_by_episode[episode_id] += 1
                weak_ordinals[_bucket(ordinal)] += 1
                weak_sides[record.direction] += 1

                if prior_gaps:
                    weak_with_prior_gap += 1
            else:
                accepted_by_episode[episode_id] += 1

        weak_count = sum(weak_by_episode.values())
        accepted_count = sum(accepted_by_episode.values())

        assert weak_count == expected["WEAK_ACTIVE"]
        assert accepted_count == expected["ACCEPTED"]
        assert sum(weak_ordinals.values()) == weak_count
        assert sum(weak_sides.values()) == weak_count

        weak_ids = set(weak_by_episode)
        accepted_ids = set(accepted_by_episode)

        both = len(weak_ids & accepted_ids)
        weak_only = len(weak_ids - accepted_ids)
        accepted_only = len(accepted_ids - weak_ids)
        neither = episode_total - len(weak_ids | accepted_ids)

        assert (
            min(
                both,
                weak_only,
                accepted_only,
                neither,
            )
            >= 0
        )

        assert both + weak_only + accepted_only + neither == episode_total

        weak_in_accepted_episodes = sum(
            count
            for episode_id, count in weak_by_episode.items()
            if episode_id in accepted_ids
        )

        weak_in_no_accepted_episodes = weak_count - weak_in_accepted_episodes

        print(
            f"ACTIVE_EPISODE_CENSUS|PERIOD={spec.code}|"
            f"TOTAL={episode_total}|"
            f"WITH_WEAK={len(weak_ids)}|"
            f"WITH_ACCEPTED={len(accepted_ids)}|"
            f"BOTH={both}|"
            f"WEAK_ONLY={weak_only}|"
            f"ACCEPTED_ONLY={accepted_only}|"
            f"NEITHER={neither}"
        )

        print(
            f"MACD_WEAK_EPISODE_COVERAGE|PERIOD={spec.code}|"
            f"WEAK_ACTIVE={weak_count}|"
            f"BUY={weak_sides['BUY']}|"
            f"SELL={weak_sides['SELL']}|"
            f"IN_EPISODES_WITH_ACCEPTED="
            f"{weak_in_accepted_episodes}|"
            f"IN_EPISODES_WITHOUT_ACCEPTED="
            f"{weak_in_no_accepted_episodes}|"
            f"PRIOR_OBSERVED_GAP={weak_with_prior_gap}"
        )

        for ordinal_bucket, count in sorted(weak_ordinals.items()):
            print(
                f"WEAK_SIGNAL_ORDINAL|PERIOD={spec.code}|"
                f"BUCKET={ordinal_bucket}|COUNT={count}"
            )

        distribution = Counter(weak_by_episode.values())

        for size, count in sorted(distribution.items()):
            print(
                f"WEAK_EPISODE_DISTRIBUTION|"
                f"PERIOD={spec.code}|"
                f"REJECTS_PER_EPISODE={size}|EPISODES={count}"
            )

        print(f"MACD_WEAK_EPISODE_RECONCILIATION=" f"{spec.code}:OK")

        pooled.update(
            {
                "weak": weak_count,
                "accepted": accepted_count,
                "episodes": episode_total,
                "weak_only_episodes": weak_only,
                "episodes_with_weak": len(weak_ids),
                "weak_in_no_accepted_episodes": (weak_in_no_accepted_episodes),
            }
        )

    assert pooled["weak"] == 611
    assert pooled["accepted"] == 60

    print(
        "POOLED_MACD_WEAK_EPISODE_COVERAGE|"
        + "|".join(f"{name.upper()}={value}" for name, value in sorted(pooled.items()))
    )

    assert before == {source_file: _sha(source_file) for source_file in guarded}

    assert production_before == production_hashes()

    print("T115_87_ACTIVE_ALIGNED_611_OF_611=OK")
    print("PRODUCTION_ACCEPTED_60_OF_60=OK")
    print("ACTIVE_EPISODE_ACCOUNTING=OK")
    print("EPISODE_WITHOUT_ACCEPTED_IS_NOT_POSITION_FLAT=True")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_PATTERN_OR_NEW_ENTRY_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_88_MACD_WEAK_ACTIVE_TREND_EPISODE_COVERAGE=OK")


if __name__ == "__main__":
    main()
