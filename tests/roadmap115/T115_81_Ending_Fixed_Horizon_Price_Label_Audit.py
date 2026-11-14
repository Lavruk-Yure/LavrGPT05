# -*- coding: utf-8 -*-
"""RoadMap115 / T115-81: fixed-horizon M15 price follow-through.

TEST_ONLY / DATA_ONLY. Майбутні close — лише outcome labels,
ніколи не ознаки входу. Пропуски M15 не зшиваються.
Production, Replay, MD7 та торгові правила не змінюються.
"""

from __future__ import annotations

import hashlib
import statistics
import sys
from collections import Counter, defaultdict
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
    "2025": {"ENDING": 71, "ACCEPTED": 42, "RAW": 3042},
    "2026": {"ENDING": 33, "ACCEPTED": 18, "RAW": 1962},
}

GROUPS = ("ENDING", "ACCEPTED")
HORIZONS = (1, 4, 8, 16)
BAR_SPAN = timedelta(minutes=15)
PIP_SIZE = 0.0001

ENDING_REASONS = {
    "ALLIGATOR_SAME_TIMEFRAME_BUY_ENDING_REJECT",
    "ALLIGATOR_SAME_TIMEFRAME_SELL_ENDING_REJECT",
}


def _sha(path: Path) -> str:
    """Контрольний SHA256 файлу."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _group(record: Any, alligator: Any) -> str | None:
    """Вибрати сигнал за фактичним причинним контекстом."""
    context = record.filter_context

    if context is None:
        return None

    direction = record.direction
    assert direction in {"BUY", "SELL"}

    aligned_regime = (
        alligator.ALLIGATOR_REGIME_TREND_UP
        if direction == "BUY"
        else alligator.ALLIGATOR_REGIME_TREND_DOWN
    )

    if record.accepted:
        assert context.regime == aligned_regime
        assert context.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ACTIVE
        return "ACCEPTED"

    if record.filter_reason_code not in ENDING_REASONS:
        return None

    assert record.source_reason_code == "MACD_CROSS_ACCEPTED"

    if context.regime != aligned_regime:
        return None

    assert context.regime_phase == alligator.ALLIGATOR_REGIME_PHASE_ENDING

    return "ENDING"


def _label(
    events: tuple[Any, ...],
    start: int,
    horizon: int,
    direction: str,
) -> tuple[str, float | None]:
    """Оцінити рух після сигналу, не моделюючи нової угоди."""
    end = start + horizon

    if end >= len(events):
        return "END_OF_DATA", None

    for i in range(start, end):
        if events[i + 1].timestamp - events[i].timestamp != BAR_SPAN:
            return "TIME_GAP", None

    multiplier = 1.0 if direction == "BUY" else -1.0

    movement = multiplier * (events[end].close - events[start].close) / PIP_SIZE

    return "VALID", movement


def _report(
    period: str,
    group: str,
    horizon: int,
    coverage: Counter[str],
    values: list[float],
    expected_count: int,
) -> None:
    """Показати вибірку, пропуски та розподіл outcome labels."""
    assert sum(coverage.values()) == expected_count
    assert coverage["VALID"] == len(values)

    assert (
        sum(coverage[name] for name in ("VALID", "TIME_GAP", "END_OF_DATA"))
        == expected_count
    )

    positive = sum(value > 1e-8 for value in values)
    negative = sum(value < -1e-8 for value in values)
    neutral = len(values) - positive - negative

    mean = f"{statistics.fmean(values):+.2f}" if values else "NA"

    median = f"{statistics.median(values):+.2f}" if values else "NA"

    print(
        f"PRICE_LABEL|PERIOD={period}|GROUP={group}|"
        f"H_M15={horizon}|N={expected_count}|"
        f"VALID={len(values)}|"
        f"TIME_GAP={coverage['TIME_GAP']}|"
        f"END_OF_DATA={coverage['END_OF_DATA']}|"
        f"POS={positive}|NEG={negative}|ZERO={neutral}|"
        f"MEAN_PIPS={mean}|MEDIAN_PIPS={median}"
    )


def main() -> None:
    """Порівняти ENDING rejects із accepted на однакових горизонтах."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))
    hashes = getattr(harness, "_production_hashes")

    broker_attempted = getattr(
        harness,
        "_broker_execution_attempted",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "core/workspace_signal.py",
        ROOT / "core/workspace_replay_execution.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
    )

    assert all(path.is_file() for path in guarded)

    before = {path: _sha(path) for path in guarded}

    production_before = hashes()

    print("T115-81|TEST_ONLY|" "ENDING_FIXED_HORIZON_PRICE_LABEL_AUDIT")
    print("SOURCE=CANONICAL_T105_18_PRODUCTION_M15_REPLAY")
    print("REFERENCE=SIGNAL_BAR_CLOSE|UNIT=EURUSD_PIPS")
    print("H_M15=1,4,8,16|CONTIGUOUS_BARS_ONLY=True")
    print("FUTURE_PRICE=OUTCOME_LABEL_ONLY|NOT_ENTRY_FEATURE=True")
    print("NO_EXECUTION_FILL_OR_TRADING_PNL=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled_coverage: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)

    pooled_values: dict[tuple[str, int], list[float]] = defaultdict(list)

    pooled_population: Counter[str] = Counter()

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        session = runtime.replay_session
        assert session is not None and session.completed

        events = tuple(session.events)

        assert events
        assert all(event.timeframe == "M15" for event in events)

        assert all(
            events[i].timestamp < events[i + 1].timestamp
            for i in range(len(events) - 1)
        )

        event_index = {event.timestamp: i for i, event in enumerate(events)}

        assert len(event_index) == len(events)

        records = runtime.signal_records_for_ui()
        assert len(records) == EXPECTED[spec.code]["RAW"]

        groups: dict[str, list[Any]] = {name: [] for name in GROUPS}

        for record in records:
            group = _group(record, alligator)

            if group is None:
                continue

            context = record.filter_context
            assert context is not None
            assert context.available_at <= record.timestamp
            assert record.timestamp in event_index

            groups[group].append(record)

        assert all(len(groups[name]) == EXPECTED[spec.code][name] for name in GROUPS)

        assert runtime.historical_summary is not None

        assert runtime.historical_summary.opened_trades == len(groups["ACCEPTED"])

        assert len(
            {(record.timestamp, record.direction) for record in groups["ENDING"]}
        ) == len(groups["ENDING"])

        for group in GROUPS:
            for horizon in HORIZONS:
                coverage: Counter[str] = Counter()
                values: list[float] = []

                for record in groups[group]:
                    status, pips = _label(
                        events,
                        event_index[record.timestamp],
                        horizon,
                        record.direction,
                    )

                    coverage[status] += 1

                    if pips is not None:
                        assert status == "VALID"
                        values.append(pips)

                _report(
                    spec.code,
                    group,
                    horizon,
                    coverage,
                    values,
                    len(groups[group]),
                )

                key = group, horizon

                pooled_coverage[key].update(coverage)
                pooled_values[key].extend(values)

            pooled_population[group] += len(groups[group])

        print(f"FIXED_HORIZON_RECONCILIATION={spec.code}:OK")

    assert pooled_population == Counter(
        {
            "ENDING": 104,
            "ACCEPTED": 60,
        }
    )

    for group in GROUPS:
        for horizon in HORIZONS:
            key = group, horizon

            _report(
                "POOLED",
                group,
                horizon,
                pooled_coverage[key],
                pooled_values[key],
                pooled_population[group],
            )

    assert before == {path: _sha(path) for path in guarded}

    assert production_before == hashes()

    print("T115_80_ENDING_104_OF_104=OK")
    print("PRODUCTION_ACCEPTED_60_OF_60=OK")
    print("FIXED_HORIZON_COVERAGE_RECONCILED=OK")
    print("FUTURE_LABELS_NEVER_USED_FOR_ENTRY=True")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_COUNTERFACTUAL_TRADES_OR_NEW_ENTRY_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_81_ENDING_FIXED_HORIZON_PRICE_LABEL_AUDIT=OK")


if __name__ == "__main__":
    main()
