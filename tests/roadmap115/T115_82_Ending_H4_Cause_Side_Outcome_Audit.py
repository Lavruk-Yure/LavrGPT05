# -*- coding: utf-8 -*-
"""RoadMap115 / T115-82: ENDING H4 cause/side outcome audit.

TEST_ONLY / DATA_ONLY.

Повторює перевірений H4 outcome label із T115-81 і causal cause
із T115-79. Розділяє ENDING на FLAT_HYSTERESIS / STATE_MISMATCH
та BUY / SELL у двох production періодах.

H4 вибрано після попереднього exploratory результату T115-81:
це дослідницька деталізація, не незалежна валідація.
Немає нових торгових правил, counterfactual fills або PnL.
"""

from __future__ import annotations

import hashlib
import statistics
import sys
from collections import Counter, defaultdict
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_DIR = ROOT / "tests" / "roadmap115"

for import_dir in (ROOT, ROADMAP_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))


HORIZON = 4
GROUPS = ("ENDING", "ACCEPTED")
CAUSES = ("FLAT_HYSTERESIS", "STATE_MISMATCH")

EXPECTED = {
    "2025": {
        "RAW": 3042,
        "ENDING": 71,
        "ACCEPTED": 42,
        "FLAT_HYSTERESIS": 8,
        "STATE_MISMATCH": 63,
        "ENDING_VALID": 69,
        "ENDING_GAP": 2,
        "ACCEPTED_VALID": 42,
        "ACCEPTED_GAP": 0,
    },
    "2026": {
        "RAW": 1962,
        "ENDING": 33,
        "ACCEPTED": 18,
        "FLAT_HYSTERESIS": 4,
        "STATE_MISMATCH": 29,
        "ENDING_VALID": 33,
        "ENDING_GAP": 0,
        "ACCEPTED_VALID": 17,
        "ACCEPTED_GAP": 1,
    },
}

Label = tuple[str, float | None]
Bucket = tuple[str, str, str]


def _sha(source_file: Path) -> str:
    """Контрольний хеш без зміни джерела."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _report(
    period: str,
    key: Bucket,
    rows: list[Label],
) -> None:
    """Вивести coverage і H4 рух в однакових одиницях."""
    group, cause, side = key

    coverage = Counter(status for status, _ in rows)

    assert not set(coverage) - {
        "VALID",
        "TIME_GAP",
        "END_OF_DATA",
    }

    assert sum(coverage.values()) == len(rows)

    assert all((status == "VALID") == (pips is not None) for status, pips in rows)

    valid = [float(pips) for status, pips in rows if status == "VALID"]

    positive = sum(value > 1e-8 for value in valid)

    negative = sum(value < -1e-8 for value in valid)

    zero = len(valid) - positive - negative

    mean = f"{statistics.fmean(valid):+.2f}" if valid else "NA"

    median = f"{statistics.median(valid):+.2f}" if valid else "NA"

    print(
        f"H4_CAUSE_SIDE|PERIOD={period}|"
        f"GROUP={group}|CAUSE={cause}|SIDE={side}|"
        f"N={len(rows)}|VALID={len(valid)}|"
        f"TIME_GAP={coverage['TIME_GAP']}|"
        f"END_OF_DATA={coverage['END_OF_DATA']}|"
        f"POS={positive}|NEG={negative}|ZERO={zero}|"
        f"MEAN_PIPS={mean}|MEDIAN_PIPS={median}"
    )


def main() -> None:
    """Звірити causal підгрупи та єдиний H4 outcome."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    cause_audit = import_module(
        "T115_79_Production_Ending_Causal_Cause_And_Transition_Audit"
    )

    label_audit = import_module("T115_81_Ending_Fixed_Horizon_Price_Label_Audit")

    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))

    production_hashes = getattr(
        harness,
        "_production_hashes",
    )

    check_context = getattr(
        cause_audit,
        "_check_context",
    )

    cause_of = getattr(
        cause_audit,
        "_cause",
    )

    group_of = getattr(
        label_audit,
        "_group",
    )

    label_at = getattr(
        label_audit,
        "_label",
    )

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "core/workspace_replay_execution.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
        ROADMAP_DIR / "T115_79_Production_Ending_Causal_Cause_And_Transition_Audit.py",
        ROADMAP_DIR / "T115_81_Ending_Fixed_Horizon_Price_Label_Audit.py",
    )

    assert all(source_file.is_file() for source_file in guarded)

    before = {source_file: _sha(source_file) for source_file in guarded}

    production_before = production_hashes()

    print("T115-82|TEST_ONLY|" "ENDING_H4_CAUSE_SIDE_OUTCOME_AUDIT")

    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("H_M15=4|REFERENCE=SIGNAL_BAR_CLOSE|UNIT=PIPS")
    print("HORIZON_SELECTED_AFTER_T115_81=True|EXPLORATORY_ONLY=True")
    print("FUTURE_PRICE_USED_AS_OUTCOME_ONLY=True")
    print("NO_FILL_NO_COST_NO_PNL_NO_NEW_GATE=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled_bins: dict[Bucket, list[Label]] = defaultdict(list)

    pooled_groups: dict[str, list[Label]] = defaultdict(list)

    pooled_causes: Counter[str] = Counter()

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0

        session = runtime.replay_session
        assert session is not None
        assert session.completed

        events = tuple(session.events)

        event_index = {event.timestamp: index for index, event in enumerate(events)}

        assert len(event_index) == len(events)

        records = runtime.signal_records_for_ui()
        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]

        bins: dict[Bucket, list[Label]] = defaultdict(list)

        grouped: dict[str, list[Label]] = defaultdict(list)

        cause_counts: Counter[str] = Counter()

        for record in records:
            group = group_of(record, alligator)

            if group is None:
                continue

            assert group in GROUPS
            assert record.timestamp in event_index

            assert record.filter_context.available_at <= record.timestamp

            assert record.direction in {"BUY", "SELL"}

            if group == "ENDING":
                current, _ = check_context(record)

                cause, line_order = cause_of(
                    record,
                    current,
                    alligator,
                )

                assert cause in CAUSES
                assert line_order == "MISALIGNED"

                cause_counts[cause] += 1
            else:
                cause = "PRODUCTION_ACCEPTED"

            label = label_at(
                events,
                event_index[record.timestamp],
                HORIZON,
                record.direction,
            )

            key = group, cause, record.direction

            bins[key].append(label)
            grouped[group].append(label)

        for group in GROUPS:
            assert len(grouped[group]) == expected[group]

            coverage = Counter(status for status, _ in grouped[group])

            assert coverage["VALID"] == expected[f"{group}_VALID"]

            assert coverage["TIME_GAP"] == expected[f"{group}_GAP"]

            assert coverage["END_OF_DATA"] == 0

            _report(
                spec.code,
                (group, "ALL", "ALL"),
                grouped[group],
            )

            pooled_groups[group].extend(grouped[group])

        for cause in CAUSES:
            assert cause_counts[cause] == expected[cause]

        assert sum(cause_counts.values()) == expected["ENDING"]

        pooled_causes.update(cause_counts)

        for key in sorted(bins):
            _report(
                spec.code,
                key,
                bins[key],
            )

            pooled_bins[key].extend(bins[key])

        print(f"H4_CAUSE_SIDE_RECONCILIATION={spec.code}:OK")

    assert len(pooled_groups["ENDING"]) == 104
    assert len(pooled_groups["ACCEPTED"]) == 60

    assert pooled_causes == Counter(
        {
            "STATE_MISMATCH": 92,
            "FLAT_HYSTERESIS": 12,
        }
    )

    assert sum(status == "VALID" for status, _ in pooled_groups["ENDING"]) == 102

    assert sum(status == "VALID" for status, _ in pooled_groups["ACCEPTED"]) == 59

    for group in GROUPS:
        _report(
            "POOLED",
            (group, "ALL", "ALL"),
            pooled_groups[group],
        )

    for key in sorted(pooled_bins):
        _report(
            "POOLED",
            key,
            pooled_bins[key],
        )

    assert before == {source_file: _sha(source_file) for source_file in guarded}

    assert production_before == production_hashes()

    print("T115_79_CAUSES_92_PLUS_12=OK")
    print("T115_81_H4_ENDING_VALID_102=OK")
    print("T115_81_H4_ACCEPTED_VALID_59=OK")
    print("H4_CAUSE_SIDE_ACCOUNTING=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("OUTCOME_NOT_ENTRY_FEATURE=True|EXPLORATORY_ONLY=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_82_ENDING_H4_CAUSE_SIDE_OUTCOME_AUDIT=OK")


if __name__ == "__main__":
    main()
