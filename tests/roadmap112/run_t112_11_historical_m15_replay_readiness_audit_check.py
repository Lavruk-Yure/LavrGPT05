# -*- coding: utf-8 -*-
"""T112-11 — контроль готовності історичних M15 до Replay."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

from run_t112_10_historical_m1_to_m15_aggregation_integrity_check import (
    EXPECTED,
    FIRST_DATES,
    HEADER,
    HISTORY,
    LAST_DATES,
    SYMBOLS,
    Bar,
    CompletedM15,
    IntegrityError,
    M15Counter,
)

STEP = timedelta(minutes=15)
EXPECTED_COMPLETE = {"EURUSD": 140731, "GBPUSD": 142429, "USDJPY": 142377}


@dataclass(frozen=True, slots=True)
class DirectCoverage:
    count: int
    minute_mask: int
    observed_equal_price: bool | None
    observed_equal_volume: bool | None


@dataclass(slots=True)
class RunAudit:
    """Сегменти суміжних повних M15 без штучного заповнення."""

    last: datetime | None = None
    first_in_run: datetime | None = None
    count_in_run: int = 0
    completed: int = 0
    run_count: int = 0
    max_run: int = 0
    max_run_start: datetime | None = None
    max_run_end: datetime | None = None
    anchors_with_32: int = 0
    anchors_with_64: int = 0
    bars_in_runs_ge_32: int = 0
    bars_in_runs_ge_64: int = 0
    gaps: int = 0
    missing_slots: int = 0
    weekend_gaps: int = 0
    weekday_gaps: int = 0
    missing_weekend_slots: int = 0
    missing_weekday_slots: int = 0
    longest_weekday_gap: tuple[int, datetime, datetime] | None = None
    longest_weekend_gap: tuple[int, datetime, datetime] | None = None
    run_lengths: Counter[str] = field(default_factory=Counter)
    years: Counter[int] = field(default_factory=Counter)

    def add(self, bar: CompletedM15) -> None:
        if bar.available_at != bar.timestamp + STEP:
            raise IntegrityError("M15 availability must follow completed bucket")
        if self.last is not None:
            difference = bar.timestamp - self.last
            if difference <= timedelta(0) or difference % STEP:
                raise IntegrityError("M15 grid is not strictly ordered")
            if difference != STEP:
                missing = int(difference // STEP) - 1
                self.gaps += 1
                self.missing_slots += missing
                touches_weekend = _touches_weekend(self.last + STEP, bar.timestamp)
                if touches_weekend:
                    self.weekend_gaps += 1
                    self.missing_weekend_slots += missing
                    current = self.longest_weekend_gap
                    if current is None or missing > current[0]:
                        self.longest_weekend_gap = (missing, self.last, bar.timestamp)
                else:
                    self.weekday_gaps += 1
                    self.missing_weekday_slots += missing
                    current = self.longest_weekday_gap
                    if current is None or missing > current[0]:
                        self.longest_weekday_gap = (missing, self.last, bar.timestamp)
                self._close_run()
        if self.count_in_run == 0:
            self.first_in_run = bar.timestamp
        self.count_in_run += 1
        self.completed += 1
        self.years[bar.timestamp.year] += 1
        self.last = bar.timestamp

    def finish(self) -> None:
        self._close_run()

    def _close_run(self) -> None:
        count = self.count_in_run
        if count == 0:
            return
        self.run_count += 1
        self.anchors_with_32 += max(count - 31, 0)
        self.anchors_with_64 += max(count - 63, 0)
        if count >= 32:
            self.bars_in_runs_ge_32 += count
        if count >= 64:
            self.bars_in_runs_ge_64 += count
        band = "1-7" if count < 8 else "8-31" if count < 32 else "32-63"
        if count >= 64:
            band = "64+"
        self.run_lengths[band] += 1
        if count > self.max_run:
            self.max_run = count
            self.max_run_start = self.first_in_run
            self.max_run_end = self.last
        self.count_in_run = 0
        self.first_in_run = None


def _touches_weekend(start: datetime, end: datetime) -> bool:
    """Перевірити, чи часовий розрив охоплює вихідні."""
    current = start.date()
    last = (end - STEP).date()
    while current <= last:
        if current.weekday() >= 5:
            return True
        current += timedelta(days=1)
    return False


def _read_csv_bars(path: Path, minutes: int = 1) -> Iterator[Bar]:
    """Читати OHLCV потоково та перевіряти часову сітку."""
    if not path.is_file():
        raise IntegrityError(f"Missing history: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if tuple(next(reader, ())) != HEADER:
            raise IntegrityError(f"Invalid CSV header: {path.name}")
        previous: datetime | None = None
        for line_number, row in enumerate(reader, 2):
            if len(row) != 6:
                raise IntegrityError(f"{path.name}:{line_number}: invalid column count")
            try:
                timestamp = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                price_values = tuple(float(text) for text in row[1:])
            except ValueError as parsing_error:
                raise IntegrityError(
                    f"{path.name}:{line_number}: invalid data"
                ) from parsing_error
            if timestamp.utcoffset() != timedelta(0):
                raise IntegrityError(f"{path.name}:{line_number}: non-UTC timestamp")
            if timestamp.second or timestamp.microsecond:
                raise IntegrityError(f"{path.name}:{line_number}: sub-minute timestamp")
            if timestamp.minute % minutes:
                raise IntegrityError(f"{path.name}:{line_number}: wrong grid")
            if previous is not None and timestamp <= previous:
                raise IntegrityError(f"{path.name}:{line_number}: unordered bars")
            if not all(math.isfinite(value) for value in price_values):
                raise IntegrityError(f"{path.name}:{line_number}: non-finite OHLCV")
            op, high, low, close, volume = price_values
            if min(op, high, low, close) <= 0 or volume < 0:
                raise IntegrityError(f"{path.name}:{line_number}: invalid price")
            if high < max(op, low, close) or low > min(op, high, close):
                raise IntegrityError(f"{path.name}:{line_number}: invalid extrema")
            previous = timestamp
            yield Bar(timestamp.astimezone(UTC), *price_values)


def _source_name(symbol: str, part: int) -> str:
    return f"{FIRST_DATES[part]}_{LAST_DATES[part]}_" f"CTRADER_{symbol}_M1.csv"


def _read_direct(root: Path, symbol: str) -> dict[datetime, Bar]:
    directory = root / symbol / "M15"
    result: dict[datetime, Bar] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob(f"*_CTRADER_{symbol}_M15.csv")):
        for bar in _read_csv_bars(path, 15):
            previous = result.get(bar.timestamp)
            if previous is not None and previous != bar:
                raise IntegrityError("Conflicting direct M15 history")
            result[bar.timestamp] = bar
    return result


def _price_equal(bar: Bar, direct: Bar) -> bool:
    return all(
        math.isclose(left, right, abs_tol=1e-10, rel_tol=0.0)
        for left, right in (
            (bar.open, direct.open),
            (bar.high, direct.high),
            (bar.low, direct.low),
            (bar.close, direct.close),
        )
    )


def _coverage_of_bucket(
    counter: M15Counter, minute_mask: int, direct: Bar
) -> DirectCoverage:
    if counter.first is None or counter.last is None:
        raise IntegrityError("Cannot describe an empty M15 bucket")
    observed = Bar(
        direct.timestamp,
        counter.first.open,
        counter.high,
        counter.low,
        counter.last.close,
        counter.volume,
    )
    return DirectCoverage(
        count=counter.count,
        minute_mask=minute_mask,
        observed_equal_price=_price_equal(observed, direct),
        observed_equal_volume=math.isclose(
            observed.volume, direct.volume, abs_tol=1e-7, rel_tol=0.0
        ),
    )


def _format_gap(value: tuple[int, datetime, datetime] | None) -> str:
    if value is None:
        return "NONE"
    count, start, end = value
    return f"{start.isoformat()}->{end.isoformat()}:missing_m15={count}"


def _audit_symbol(root: Path, symbol: str) -> None:
    print(f"SYMBOL={symbol}")
    counter = M15Counter()
    run = RunAudit()
    direct = _read_direct(root, symbol)
    coverage: dict[datetime, DirectCoverage] = {}
    minute_mask = 0
    part_deltas: list[int] = []
    previous_file_last: datetime | None = None
    direct_matched_complete = 0
    direct_complete_difference = 0

    def collect(completed: CompletedM15 | None) -> None:
        nonlocal direct_matched_complete, direct_complete_difference
        if completed is None:
            return
        run.add(completed)
        direct_bar = direct.get(completed.timestamp)
        if direct_bar is not None:
            direct_matched_complete += 1
            derived = Bar(
                completed.timestamp,
                completed.open,
                completed.high,
                completed.low,
                completed.close,
                completed.volume,
            )
            if not _price_equal(derived, ref) or not math.isclose(
                derived.volume, ref.volume, abs_tol=1e-7, rel_tol=0.0
            ):
                direct_complete_difference += 1

    for part in range(3):
        path = root / symbol / "M1" / _source_name(symbol, part)
        rows = 0
        first: datetime | None = None
        last: datetime | None = None
        before = counter.summary.complete_buckets
        for bar in _read_csv_bars(path):
            if first is None:
                first = bar.timestamp
            if previous_file_last is not None and bar.timestamp <= previous_file_last:
                raise IntegrityError(f"{symbol}: duplicate across files")
            last = bar.timestamp
            bucket = bar.timestamp.replace(minute=bar.timestamp.minute // 15 * 15)
            pending = counter.start
            if pending is not None and pending != bucket:
                ref = direct.get(pending)
                if ref is not None:
                    coverage[pending] = _coverage_of_bucket(counter, minute_mask, ref)
                minute_mask = 0
            minute_mask |= 1 << (bar.timestamp.minute % 15)
            collect(counter.add(bar))
            rows += 1
        if rows != EXPECTED[symbol][part]:
            raise IntegrityError(
                f"{symbol}: part {part + 1}: unexpected M1 count {rows}"
            )
        if first is None or last is None:
            raise IntegrityError(f"{symbol}: empty part {part + 1}")
        previous_file_last = last
        delta = counter.summary.complete_buckets - before
        part_deltas.append(delta)
        print(
            f"part={part + 1}|rows={rows}|complete_counted_before_finish={delta}"
            f"|pending_bucket={counter.start.isoformat() if counter.start else 'NONE'}"
            f"|pending_m1={counter.count}"
        )

    if counter.start is not None:
        ref = direct.get(counter.start)
        if ref is not None:
            coverage[counter.start] = _coverage_of_bucket(counter, minute_mask, ref)
    before_finish = counter.summary.complete_buckets
    collect(counter.finish())
    flush_delta = counter.summary.complete_buckets - before_finish
    run.finish()
    summary = counter.summary
    if sum(part_deltas) + flush_delta != summary.complete_buckets:
        raise IntegrityError("Incomplete per-part/final bucket accounting")
    if summary.complete_buckets != EXPECTED_COMPLETE[symbol]:
        raise IntegrityError(f"{symbol}: historic M15 count changed")
    if run.completed != summary.complete_buckets:
        raise IntegrityError("Continuous run counting lost M15 bars")
    if run.completed != sum(run.years.values()):
        raise IntegrityError("Year totals differ from continuous M15 counts")
    if run.missing_slots != run.missing_weekend_slots + run.missing_weekday_slots:
        raise IntegrityError("M15 gap classification is incomplete")
    print(
        f"part_accounting=sum_part_counts:{sum(part_deltas)}"
        f"|pending_final_flush:{flush_delta}"
        f"|final_complete:{summary.complete_buckets}|difference_explained=True"
    )
    print(
        f"m15_readiness=complete:{run.completed}|runs:{run.run_count}"
        f"|max_consecutive:{run.max_run}"
        f"|longest_run_start:{run.max_run_start}"
        f"|longest_run_end:{run.max_run_end}"
    )
    print(
        f"causal_32_completed_m15_windows={run.anchors_with_32}"
        f"|causal_64_completed_m15_windows={run.anchors_with_64}"
        f"|bars_in_runs_ge32={run.bars_in_runs_ge_32}"
        f"|bars_in_runs_ge64={run.bars_in_runs_ge_64}"
    )
    print(f"run_length_bands={sorted(run.run_lengths.items())}")
    print(
        f"m15_discontinuities={run.gaps}|missing_slots={run.missing_slots}"
        f"|weekend_touching_gaps={run.weekend_gaps}"
        f"|other_gaps={run.weekday_gaps}"
    )
    print(
        f"largest_non_weekend_gap={_format_gap(run.longest_weekday_gap)}"
        f"|largest_weekend_gap={_format_gap(run.longest_weekend_gap)}"
    )
    for year in sorted(run.years):
        print(f"year={year}|complete_m15={run.years[year]}")

    counts: Counter[str] = Counter()
    count_histogram: Counter[int] = Counter()
    missing_count = 0
    for timestamp, reference in sorted(direct.items()):
        observed = coverage.get(timestamp)
        if observed is None:
            observed = DirectCoverage(0, 0, None, None)
        count_histogram[observed.count] += 1
        if observed.count == 15:
            counts["COMPLETE_15_OF_15"] += 1
            continue
        missing_count += 1
        reason = "NO_M1_BUCKET" if observed.count == 0 else "PARTIAL_M1_BUCKET"
        counts[reason] += 1
        missing_offsets = ",".join(
            str(index) for index in range(15) if not observed.minute_mask & (1 << index)
        )
        print(
            f"direct_without_complete={timestamp.isoformat()}"
            f"|class={reason}|observed_m1={observed.count}"
            f"|missing_offsets={missing_offsets}"
            f"|partial_ohlc_equal={observed.observed_equal_price}"
            f"|partial_volume_equal={observed.observed_equal_volume}"
            f"|direct_volume={reference.volume:g}"
        )
    if direct:
        if direct_matched_complete != counts["COMPLETE_15_OF_15"]:
            raise IntegrityError("M15 complete/direct coverage mismatch")
        if direct_complete_difference:
            raise IntegrityError("Direct full M15 prices differ from source M1")
        if len(direct) != sum(count_histogram.values()):
            raise IntegrityError("Direct M15 count accounting mismatch")
        print(
            f"direct_m15_rows={len(direct)}"
            f"|matched_complete={direct_matched_complete}"
            f"|without_complete_15_m1={missing_count}"
            f"|partial={counts['PARTIAL_M1_BUCKET']}"
            f"|absent={counts['NO_M1_BUCKET']}"
            f"|full_price_mismatches={direct_complete_difference}"
        )
        print(f"direct_m1_count_histogram={sorted(count_histogram.items())}")
        if symbol == "EURUSD" and len(direct) == 2155 and missing_count != 97:
            raise IntegrityError("EURUSD direct M15 discrepancy with T112-10")
    else:
        print("direct_m15=NOT_AVAILABLE|coverage_analysis=NOT_APPLICABLE")
    print(f"symbol={symbol}|replay_readiness_audit=PASS")


def _synthetic_contract() -> None:
    """Контроль фінального bucket, розривів та M1-повноти."""
    base = datetime(2025, 1, 6, 10, tzinfo=UTC)
    counter = M15Counter()
    runs = RunAudit()
    mask = 0
    for minute in range(30):
        if minute == 16:
            continue
        bar = Bar(
            base + timedelta(minutes=minute),
            1.1,
            1.2,
            1.0,
            1.15,
            1.0,
        )
        if minute >= 15:
            mask |= 1 << (minute % 15)
        result = counter.add(bar)
        if result is not None:
            runs.add(result)
    assert counter.summary.complete_buckets == 1
    assert counter.summary.incomplete_buckets == 0
    reference = Bar(base + STEP, 1.1, 1.2, 1.0, 1.15, 15.0)
    coverage = _coverage_of_bucket(counter, mask, reference)
    assert coverage.count == 14
    assert not coverage.minute_mask & (1 << 1)
    assert coverage.observed_equal_price is True
    assert coverage.observed_equal_volume is False
    assert counter.finish() is None
    assert counter.summary.incomplete_buckets == 1
    runs.finish()
    assert runs.completed == 1 and runs.run_count == 1

    final = M15Counter()
    for minute in range(15):
        bar = Bar(
            base + timedelta(minutes=minute),
            1.1,
            1.2,
            1.0,
            1.15,
            1.0,
        )
        assert final.add(bar) is None
    before_finish = final.summary.complete_buckets
    assert before_finish == 0
    assert final.finish() is not None
    assert final.summary.complete_buckets - before_finish == 1
    assert _touches_weekend(
        datetime(2025, 1, 10, 23, tzinfo=UTC),
        datetime(2025, 1, 12, 23, tzinfo=UTC),
    )
    assert not _touches_weekend(base + STEP, base + STEP * 3)
    print("SYNTHETIC_READINESS_AND_FINAL_FLUSH_CONTRACT=OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, default=HISTORY)
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    print("T112_11_HISTORICAL_M15_REPLAY_READINESS_AUDIT")
    print("mode=DATA_ONLY_READ_ONLY|source=CTRADER_M1|strict_m15=15_OF_15")
    print("causal=COMPLETED_M15_ONLY|no_missing_minutes_filled=True")
    _synthetic_contract()
    if not args.synthetic_only:
        print(f"history_root={args.history_root}")
        for symbol in SYMBOLS:
            _audit_symbol(args.history_root, symbol)
    print("market_calendar_completeness=NOT_ASSERTED")
    print("new_replay_run=False")
    print("historical_files_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_11_HISTORICAL_M15_REPLAY_READINESS_AUDIT=OK")


if __name__ == "__main__":
    try:
        main()
    except (IntegrityError, OSError, UnicodeError, csv.Error) as run_error:
        raise SystemExit(f"T112-11 FAILED: {run_error}") from run_error
