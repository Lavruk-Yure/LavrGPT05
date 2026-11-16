# -*- coding: utf-8 -*-
"""RoadMap115 / T115-83: next-bar feasibility of STATE_MISMATCH rejects.

TEST_ONLY / DATA_ONLY.

На незмінному production M15 Replay перевіряє доступність наступного
бара після 92 відхилених STATE_MISMATCH і 60 прийнятих сигналів.

Для доступного наступного бара розраховує довідкову ціну:
BUY = next.open + spread/2
SELL = next.open - spread/2.

Прийняті сигнали звіряє з фактичними Replay trade diagnostics.
Відхилені сигнали не ставить у чергу, не перевіряє для них
capacity, margin, risk, SL/TP або вплив на наступні угоди.

Майбутній бар використовується тільки для дослідницької оцінки.
Production, Replay та MD7 не змінюються.
"""

from __future__ import annotations

import hashlib
import math
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


BAR_SPAN = timedelta(minutes=15)
PIP_SIZE = 0.0001

EXPECTED = {
    "2025": {
        "RAW": 3042,
        "STATE_MISMATCH": 63,
        "ACCEPTED": 42,
    },
    "2026": {
        "RAW": 1962,
        "STATE_MISMATCH": 29,
        "ACCEPTED": 18,
    },
}

GROUPS = ("STATE_MISMATCH", "ACCEPTED")
SIDES = ("ALL", "BUY", "SELL")

STATUSES = (
    "EXACT_NEXT",
    "TIME_GAP",
    "END_OF_DATA",
)


def _sha(source_file: Path) -> str:
    """Обчислити SHA256 без зміни файлу."""
    return hashlib.sha256(source_file.read_bytes()).hexdigest()


def _next_bar_reference(
    events: tuple[Any, ...],
    position: int,
    direction: str,
) -> tuple[
    str,
    tuple[float, float, float] | None,
    float | None,
]:
    """Оцінити доступність наступного бара та довідкову котировку."""
    current = events[position]
    expected_time = current.timestamp + BAR_SPAN

    if position + 1 == len(events):
        return "END_OF_DATA", None, None

    following = events[position + 1]

    assert following.timestamp > current.timestamp

    if following.timestamp != expected_time:
        assert following.timestamp > expected_time

        gap_minutes = (following.timestamp - expected_time).total_seconds() / 60.0

        return "TIME_GAP", None, gap_minutes

    multiplier = 1 if direction == "BUY" else -1

    reference_quote = following.open + multiplier * following.spread / 2.0

    mid_shift = multiplier * (following.open - current.close) / PIP_SIZE

    quote_shift = multiplier * (reference_quote - current.close) / PIP_SIZE

    half_spread = following.spread / (2.0 * PIP_SIZE)

    assert all(math.isfinite(value) for value in (mid_shift, quote_shift, half_spread))

    assert half_spread >= 0.0

    assert math.isclose(
        quote_shift - mid_shift,
        half_spread,
        abs_tol=1e-7,
    )

    return (
        "EXACT_NEXT",
        (mid_shift, quote_shift, half_spread),
        None,
    )


def _fmt(value: float | None) -> str:
    """Відформатувати результат, зберігши порожню вибірку."""
    if value is None:
        return "NA"

    return f"{value:+.3f}"


def _report(
    period: str,
    group: str,
    side: str,
    statuses: Counter[str],
    shifts: list[tuple[float, float, float]],
    delays: list[float],
) -> None:
    """Показати часову доступність та цінове зміщення."""
    total = sum(statuses.values())

    assert set(statuses) <= set(STATUSES)
    assert statuses["EXACT_NEXT"] == len(shifts)
    assert statuses["TIME_GAP"] == len(delays)

    mid_shifts = [item[0] for item in shifts]

    quote_shifts = [item[1] for item in shifts]

    half_spreads = [item[2] for item in shifts]

    def mean(values: list[float]) -> float | None:
        if not values:
            return None

        return statistics.fmean(values)

    def median(values: list[float]) -> float | None:
        if not values:
            return None

        return statistics.median(values)

    adverse = sum(value > 1e-8 for value in quote_shifts)

    favorable = sum(value < -1e-8 for value in quote_shifts)

    neutral = len(shifts) - adverse - favorable

    print(
        f"NEXT_BAR|PERIOD={period}|"
        f"GROUP={group}|SIDE={side}|"
        f"N={total}|"
        f"EXACT_NEXT={statuses['EXACT_NEXT']}|"
        f"TIME_GAP={statuses['TIME_GAP']}|"
        f"END_OF_DATA={statuses['END_OF_DATA']}|"
        f"GAP_EXTRA_MIN_MAX="
        f"{_fmt(max(delays) if delays else None)}"
    )

    print(
        f"REFERENCE_QUOTE_SHIFT|PERIOD={period}|"
        f"GROUP={group}|SIDE={side}|"
        f"VALID={len(shifts)}|"
        f"ADVERSE={adverse}|"
        f"FAVORABLE={favorable}|"
        f"NEUTRAL={neutral}|"
        f"MID_MEAN_PIPS={_fmt(mean(mid_shifts))}|"
        f"MID_MEDIAN_PIPS={_fmt(median(mid_shifts))}|"
        f"QUOTE_MEAN_PIPS={_fmt(mean(quote_shifts))}|"
        f"QUOTE_MEDIAN_PIPS={_fmt(median(quote_shifts))}|"
        f"HALF_SPREAD_MEAN_PIPS="
        f"{_fmt(mean(half_spreads))}"
    )


def main() -> None:
    """Перевірити next-bar feasibility без виконання нових угод."""
    harness = import_module("T115_75_Production_Candidate_F_Signal_Reject_Census")

    cause_audit = import_module(
        "T115_79_Production_Ending_Causal_Cause_And_Transition_Audit"
    )

    label_audit = import_module("T115_81_Ending_Fixed_Horizon_Price_Label_Audit")

    alligator = import_module("core.workspace_alligator")

    run_period = getattr(
        harness,
        "_run_period",
    )

    periods = tuple(getattr(harness, "PERIODS"))

    source_hashes = getattr(
        harness,
        "_production_hashes",
    )

    broker_attempted = getattr(
        harness,
        "_broker_execution_attempted",
    )

    context_of = getattr(
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

    production_before = source_hashes()

    print("T115-83|TEST_ONLY|" "STATE_MISMATCH_NEXT_BAR_FEASIBILITY_AUDIT")

    print("SOURCE=CANONICAL_T105_18_M15_PRODUCTION_REPLAY")
    print("NEXT_BAR=EXACT_SIGNAL_TIMESTAMP_PLUS_15_MINUTES")
    print("QUOTE=NEXT_OPEN_PLUS_MINUS_HALF_SPREAD")
    print("REFERENCE_ONLY=True")
    print("POSITIVE_QUOTE_SHIFT=" "MORE_ADVERSE_ENTRY_PRICE_VS_SIGNAL_CLOSE")
    print("NEXT_EVENT_OPEN_USED_AS_OUTCOME_ONLY=True")
    print("REJECTED_ORDERS_NOT_QUEUED=True")
    print("CAPACITY_MARGIN_RISK_UNTESTED=True")

    assert tuple(spec.code for spec in periods) == ("2025", "2026")

    pooled_statuses: dict[
        tuple[str, str],
        Counter[str],
    ] = defaultdict(Counter)

    pooled_shifts: dict[
        tuple[str, str],
        list[tuple[float, float, float]],
    ] = defaultdict(list)

    pooled_delays: dict[
        tuple[str, str],
        list[float],
    ] = defaultdict(list)

    pooled_population: Counter[str] = Counter()

    checked_fills = 0

    for spec in periods:
        runtime, _, broker_requests = run_period(spec)

        assert broker_requests == 0
        assert not broker_attempted(runtime)

        session = runtime.replay_session
        execution = runtime.replay_execution

        assert session is not None
        assert session.completed
        assert execution is not None

        events = tuple(session.events)

        assert all(event.timeframe == "M15" for event in events)

        assert all(
            events[index].timestamp < events[index + 1].timestamp
            for index in range(len(events) - 1)
        )

        event_indexes = {event.timestamp: index for index, event in enumerate(events)}

        assert len(event_indexes) == len(events)

        diagnostics = execution.trade_diagnostics()

        trade_by_uid = {trade.signal_uid: trade for trade in diagnostics}

        assert len(trade_by_uid) == len(diagnostics)

        records = runtime.signal_records_for_ui()
        expected = EXPECTED[spec.code]

        assert len(records) == expected["RAW"]

        group_records: dict[str, list[Any]] = {name: [] for name in GROUPS}

        for record in records:
            source_group = group_of(record, alligator)

            if source_group == "ACCEPTED":
                group_records["ACCEPTED"].append(record)

            elif source_group == "ENDING":
                current, _ = context_of(record)

                cause, line_order = cause_of(
                    record,
                    current,
                    alligator,
                )

                assert line_order == "MISALIGNED"

                if cause == "STATE_MISMATCH":
                    group_records["STATE_MISMATCH"].append(record)
                else:
                    assert cause == "FLAT_HYSTERESIS"

        for group in GROUPS:
            assert len(group_records[group]) == expected[group]

        summary = runtime.historical_summary

        assert summary is not None
        assert summary.opened_trades == expected["ACCEPTED"]
        assert len(diagnostics) == expected["ACCEPTED"]

        period_statuses: dict[
            tuple[str, str],
            Counter[str],
        ] = defaultdict(Counter)

        period_shifts: dict[
            tuple[str, str],
            list[tuple[float, float, float]],
        ] = defaultdict(list)

        period_delays: dict[
            tuple[str, str],
            list[float],
        ] = defaultdict(list)

        for group in GROUPS:
            seen_keys: set[tuple[Any, str]] = set()

            for record in group_records[group]:
                context = record.filter_context

                assert context is not None
                assert context.available_at <= record.timestamp
                assert record.timestamp in event_indexes
                assert record.direction in ("BUY", "SELL")

                unique_key = (
                    record.timestamp,
                    record.direction,
                )

                if group == "STATE_MISMATCH":
                    assert unique_key not in seen_keys

                seen_keys.add(unique_key)

                position = event_indexes[record.timestamp]

                status, shift, delay = _next_bar_reference(
                    events,
                    position,
                    record.direction,
                )

                for side in ("ALL", record.direction):
                    key = group, side

                    period_statuses[key][status] += 1
                    pooled_statuses[key][status] += 1

                    if shift is not None:
                        period_shifts[key].append(shift)
                        pooled_shifts[key].append(shift)

                    if delay is not None:
                        period_delays[key].append(delay)
                        pooled_delays[key].append(delay)

                if group == "ACCEPTED":
                    assert status == "EXACT_NEXT"
                    assert record.signal_uid in trade_by_uid

                    trade = trade_by_uid[record.signal_uid]
                    next_event = events[position + 1]

                    multiplier = 1 if record.direction == "BUY" else -1

                    expected_price = (
                        next_event.open + multiplier * next_event.spread / 2.0
                    )

                    assert trade.signal_timestamp == record.timestamp
                    assert trade.entry_timestamp == next_event.timestamp
                    assert trade.direction == record.direction

                    assert math.isclose(
                        trade.entry_price,
                        expected_price,
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    )

                    checked_fills += 1

            pooled_population[group] += len(group_records[group])

        for group in GROUPS:
            for side in SIDES:
                key = group, side

                if side == "ALL" or sum(period_statuses[key].values()) > 0:
                    _report(
                        spec.code,
                        group,
                        side,
                        period_statuses[key],
                        period_shifts[key],
                        period_delays[key],
                    )

            assert sum(period_statuses[group, "ALL"].values()) == expected[group]

        print(f"NEXT_BAR_FEASIBILITY_RECONCILIATION=" f"{spec.code}:OK")

    assert pooled_population == Counter(
        {
            "STATE_MISMATCH": 92,
            "ACCEPTED": 60,
        }
    )

    assert checked_fills == 60

    for group in GROUPS:
        for side in SIDES:
            key = group, side

            if side == "ALL" or sum(pooled_statuses[key].values()) > 0:
                _report(
                    "POOLED",
                    group,
                    side,
                    pooled_statuses[key],
                    pooled_shifts[key],
                    pooled_delays[key],
                )

        assert sum(pooled_statuses[group, "ALL"].values()) == pooled_population[group]

    assert before == {source_file: _sha(source_file) for source_file in guarded}

    assert production_before == source_hashes()

    print("STATE_MISMATCH_92_OF_92=OK")
    print("PRODUCTION_ACCEPTED_60_OF_60=OK")
    print("ACCEPTED_FILL_QUOTE_PARITY_60_OF_60=OK")
    print("NEXT_BAR_FEASIBILITY_COVERAGE=OK")
    print("SOURCE_FILES_SHA_UNCHANGED=OK")
    print("NO_REJECTED_ORDER_OR_COUNTERFACTUAL_PNL=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_83_STATE_MISMATCH_NEXT_BAR_FEASIBILITY_AUDIT=OK")


if __name__ == "__main__":
    main()
