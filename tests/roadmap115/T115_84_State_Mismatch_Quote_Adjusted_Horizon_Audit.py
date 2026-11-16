# -*- coding: utf-8 -*-
"""RoadMap115 / T115-84: quote-adjusted fixed-horizon outcome audit.

TEST_ONLY / DATA_ONLY.

Порівнює 92 STATE_MISMATCH та 60 ACCEPTED сигналів
на горизонтах 1, 4, 8, 16 завершених M15-барів.

Розраховує дві outcome-мітки:
- напрямлений рух від signal close до future close;
- напрямлений рух від next open execution quote
  до future close exit quote.

Котировки не означають фактичні або дозволені угоди.
Не враховуються SL/TP, margin, capacity, комісії та вплив
нових позицій на production Replay.

Майбутні ціни — тільки outcome labels.
Production, Replay та MD7 незмінні.
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


HORIZONS = (1, 4, 8, 16)
GROUPS = ("STATE_MISMATCH", "ACCEPTED")
SIDES = ("ALL", "BUY", "SELL")
PIP_SIZE = 0.0001

EXPECTED = {
    "2025": {
        "STATE_MISMATCH": 63,
        "ACCEPTED": 42,
        "H4_STATE_MISMATCH_VALID": 61,
        "H4_ACCEPTED_VALID": 42,
    },
    "2026": {
        "STATE_MISMATCH": 29,
        "ACCEPTED": 18,
        "H4_STATE_MISMATCH_VALID": 29,
        "H4_ACCEPTED_VALID": 17,
    },
}


def _sha(source_file: Path) -> str:
    """Обчислити контрольний SHA256."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _format_number(value: float | None) -> str:
    """Відформатувати числовий результат."""
    return "NA" if value is None else f"{value:+.3f}"


def _report(
    period: str,
    group: str,
    side: str,
    horizon: int,
    rows: list[tuple[str, float | None, float | None]],
) -> None:
    """Показати coverage та обидві outcome-мітки."""
    coverage = Counter(status for status, _, _ in rows)

    assert not set(coverage) - {
        "VALID",
        "TIME_GAP",
        "END_OF_DATA",
    }

    gross = [
        float(value)
        for status, value, _ in rows
        if status == "VALID" and value is not None
    ]

    adjusted = [
        float(value)
        for status, _, value in rows
        if status == "VALID" and value is not None
    ]

    assert len(gross) == len(adjusted)
    assert len(gross) == coverage["VALID"]
    assert sum(coverage.values()) == len(rows)

    def mean(values: list[float]) -> float | None:
        return statistics.fmean(values) if values else None

    def median(values: list[float]) -> float | None:
        return statistics.median(values) if values else None

    positive = sum(value > 1e-8 for value in adjusted)

    negative = sum(value < -1e-8 for value in adjusted)

    neutral = len(adjusted) - positive - negative

    print(
        f"QUOTE_ADJUSTED_LABEL|PERIOD={period}|"
        f"GROUP={group}|SIDE={side}|H_M15={horizon}|"
        f"N={len(rows)}|VALID={len(adjusted)}|"
        f"TIME_GAP={coverage['TIME_GAP']}|"
        f"END_OF_DATA={coverage['END_OF_DATA']}|"
        f"ADJUSTED_POS={positive}|"
        f"ADJUSTED_NEG={negative}|"
        f"ADJUSTED_ZERO={neutral}|"
        f"GROSS_MEAN={_format_number(mean(gross))}|"
        f"GROSS_MEDIAN={_format_number(median(gross))}|"
        f"QUOTE_MEAN={_format_number(mean(adjusted))}|"
        f"QUOTE_MEDIAN={_format_number(median(adjusted))}"
    )


def main() -> None:
    """Звірити quote-adjusted outcomes з canonical Replay."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")
    cause_audit = import_module(
        "T115_79_Production_Ending_Causal_Cause_And_Transition_Audit"
    )
    label_audit = import_module("T115_81_Ending_Fixed_Horizon_Price_Label_Audit")
    feasibility = import_module("T115_83_State_Mismatch_Next_Bar_Feasibility_Audit")
    alligator = import_module("core.workspace_alligator")

    run_period = getattr(harness, "_run_period")
    periods = tuple(getattr(harness, "PERIODS"))
    production_hashes = getattr(harness, "_production_hashes")
    broker_attempted = getattr(harness, "_broker_execution_attempted")

    context_of = getattr(cause_audit, "_check_context")
    cause_of = getattr(cause_audit, "_cause")
    group_of = getattr(label_audit, "_group")
    label_at = getattr(label_audit, "_label")
    next_reference = getattr(feasibility, "_next_bar_reference")

    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_macd.py",
        ROOT / "core/workspace_runtime.py",
        ROOT / "core/workspace_replay_execution.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROADMAP_DIR / "T115_75_Production_Candidate_F_Signal_Reject_Census.py",
        ROADMAP_DIR / "T115_79_Production_Ending_Causal_Cause_And_Transition_Audit.py",
        ROADMAP_DIR / "T115_81_Ending_Fixed_Horizon_Price_Label_Audit.py",
        ROADMAP_DIR / "T115_83_State_Mismatch_Next_Bar_Feasibility_Audit.py",
    )

    assert all(source_file.is_file() for source_file in guarded)

    before = {source_file: _sha(source_file) for source_file in guarded}
    production_before = production_hashes()

    print("T115-84|TEST_ONLY|" "STATE_MISMATCH_QUOTE_ADJUSTED_HORIZON_AUDIT")
    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("H_M15=1,4,8,16")
    print("ENTRY_REFERENCE=NEXT_OPEN_PLUS_MINUS_HALF_SPREAD")
    print("EXIT_REFERENCE=FUTURE_CLOSE_MINUS_PLUS_HALF_SPREAD")
    print("FUTURE_PRICES=OUTCOME_LABELS_ONLY")
    print("NO_NEW_ORDERS=True|NO_COUNTERFACTUAL_PNL=True")
    print("H4_PREVIOUSLY_SELECTED_EXPLORATORY=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled: dict[
        tuple[str, str, int],
        list[tuple[str, float | None, float | None]],
    ] = defaultdict(list)

    populations: Counter[str] = Counter()

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        session = runtime.replay_session
        assert session is not None and session.completed

        events = tuple(session.events)
        assert events

        event_index = {event.timestamp: index for index, event in enumerate(events)}
        assert len(event_index) == len(events)

        records = runtime.signal_records_for_ui()

        selections: dict[str, list[Any]] = {group: [] for group in GROUPS}

        for record in records:
            original_group = group_of(record, alligator)

            if original_group == "ACCEPTED":
                selections["ACCEPTED"].append(record)
                continue

            if original_group != "ENDING":
                continue

            current, _ = context_of(record)
            cause, line_order = cause_of(record, current, alligator)

            assert line_order == "MISALIGNED"

            if cause == "STATE_MISMATCH":
                selections["STATE_MISMATCH"].append(record)

        expected = EXPECTED[spec.code]

        for group in GROUPS:
            assert len(selections[group]) == expected[group]
            populations[group] += len(selections[group])

        bins: dict[
            tuple[str, str, int],
            list[tuple[str, float | None, float | None]],
        ] = defaultdict(list)

        for group in GROUPS:
            for record in selections[group]:
                context = record.filter_context
                assert context is not None
                assert context.available_at <= record.timestamp
                assert record.timestamp in event_index
                assert record.direction in ("BUY", "SELL")

                position = event_index[record.timestamp]

                next_status, shifts, delay = next_reference(
                    events, position, record.direction
                )

                # T115-83: усі 92 + 60 мають точний наступний бар.
                assert next_status == "EXACT_NEXT"
                assert shifts is not None
                assert delay is None

                entry_quote_shift = shifts[1]

                for horizon in HORIZONS:
                    status, gross = label_at(
                        events,
                        position,
                        horizon,
                        record.direction,
                    )

                    adjusted: float | None = None

                    if status == "VALID":
                        assert gross is not None

                        final_bar = events[position + horizon]

                        assert math.isfinite(final_bar.spread)
                        assert final_bar.spread >= 0.0

                        exit_half_spread = final_bar.spread / (2.0 * PIP_SIZE)

                        # Арифметика котировок, не торговий PnL.
                        adjusted = gross - entry_quote_shift - exit_half_spread

                        assert math.isfinite(adjusted)

                        multiplier = 1 if record.direction == "BUY" else -1

                        next_bar = events[position + 1]

                        entry_quote = next_bar.open + multiplier * next_bar.spread / 2.0

                        exit_quote = (
                            final_bar.close - multiplier * final_bar.spread / 2.0
                        )

                        direct_adjusted = (
                            multiplier * (exit_quote - entry_quote) / PIP_SIZE
                        )

                        assert math.isclose(
                            adjusted,
                            direct_adjusted,
                            abs_tol=1e-7,
                        )

                    else:
                        assert status in ("TIME_GAP", "END_OF_DATA")
                        assert gross is None

                    result = status, gross, adjusted

                    for side in ("ALL", record.direction):
                        key = group, side, horizon
                        bins[key].append(result)
                        pooled[key].append(result)

        for group in GROUPS:
            for horizon in HORIZONS:
                key = group, "ALL", horizon

                assert len(bins[key]) == expected[group]

                if horizon == 4:
                    valid_count = sum(status == "VALID" for status, _, _ in bins[key])

                    assert valid_count == expected[f"H4_{group}_VALID"]

                for side in SIDES:
                    rows = bins[group, side, horizon]

                    if side == "ALL" or rows:
                        _report(
                            spec.code,
                            group,
                            side,
                            horizon,
                            rows,
                        )

        print(f"QUOTE_ADJUSTED_RECONCILIATION={spec.code}:OK")

    assert populations == Counter(
        {
            "STATE_MISMATCH": 92,
            "ACCEPTED": 60,
        }
    )

    assert (
        sum(status == "VALID" for status, _, _ in pooled["STATE_MISMATCH", "ALL", 4])
        == 90
    )

    assert sum(status == "VALID" for status, _, _ in pooled["ACCEPTED", "ALL", 4]) == 59

    for group in GROUPS:
        for horizon in HORIZONS:
            for side in SIDES:
                rows = pooled[group, side, horizon]

                if side == "ALL" or rows:
                    _report(
                        "POOLED",
                        group,
                        side,
                        horizon,
                        rows,
                    )

    assert before == {source_file: _sha(source_file) for source_file in guarded}
    assert production_before == production_hashes()

    print("STATE_MISMATCH_92_OF_92=OK")
    print("ACCEPTED_60_OF_60=OK")
    print("H4_STATE_MISMATCH_VALID_90=OK")
    print("H4_ACCEPTED_VALID_59=OK")
    print("QUOTE_ARITHMETIC_PARITY=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_84_STATE_MISMATCH_QUOTE_ADJUSTED_HORIZON_AUDIT=OK")


if __name__ == "__main__":
    main()
