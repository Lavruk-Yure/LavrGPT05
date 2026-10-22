# -*- coding: utf-8 -*-
"""T112-10 — перевірка M1→M15 без змін історії чи production."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "data" / "history" / "CTRADER"
SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
FIRST_DATES = ("2020-10-22", "2022-10-23", "2024-10-22")
LAST_DATES = ("2022-10-21", "2024-10-21", "2026-10-21")
EXPECTED = {
    "EURUSD": (740943, 739343, 740705),
    "GBPUSD": (741655, 739855, 740323),
    "USDJPY": (741436, 740653, 739841),
}
HEADER = ("timestamp", "open", "high", "low", "close", "volume")
M15_DELTA = timedelta(minutes=15)


class IntegrityError(ValueError):
    """Файл або порядок барів порушує перевірюваний контракт."""


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class CompletedM15:
    timestamp: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Summary:
    source_rows: int = 0
    observed_buckets: int = 0
    complete_buckets: int = 0
    incomplete_buckets: int = 0
    absent_buckets_between_observations: int = 0
    incomplete_missing_m1: int = 0
    incomplete_by_count: Counter[int] = field(default_factory=Counter)
    complete_by_year: Counter[int] = field(default_factory=Counter)
    incomplete_by_year: Counter[int] = field(default_factory=Counter)
    absent_by_year: Counter[int] = field(default_factory=Counter)
    first_complete: datetime | None = None
    last_complete: datetime | None = None


@dataclass(slots=True)
class DirectCompare:
    reference_count: int = 0
    matched_complete: int = 0
    missing_in_aggregation: int = 0
    price_mismatches: int = 0
    volume_mismatches: int = 0
    first_price_mismatch: str | None = None
    max_close_delta: float = 0.0
    seen: set[datetime] = field(default_factory=set)


@dataclass(slots=True)
class LegacyCompare:
    old_rows: int = 0
    matched_timestamps: int = 0
    only_old: int = 0
    only_new: int = 0
    price_mismatches: int = 0
    volume_mismatches: int = 0
    max_close_delta: float = 0.0
    first_price_mismatch: str | None = None


def _parse_bar(row: list[str], path: Path, line: int, minutes: int) -> Bar:
    if len(row) != 6:
        raise IntegrityError(f"{path.name}:{line}: expected six columns")
    try:
        timestamp = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        values = tuple(float(item) for item in row[1:])
    except ValueError as parse_error:
        raise IntegrityError(f"{path.name}:{line}: invalid bar") from parse_error
    if timestamp.utcoffset() != timedelta(0):
        raise IntegrityError(f"{path.name}:{line}: timestamp must be UTC")
    if timestamp.second or timestamp.microsecond or timestamp.minute % minutes:
        raise IntegrityError(f"{path.name}:{line}: invalid timeframe grid")
    if not all(math.isfinite(value) for value in values):
        raise IntegrityError(f"{path.name}:{line}: non-finite OHLCV")
    op, high, low, close, volume = values
    if min(op, high, low, close) <= 0 or volume < 0:
        raise IntegrityError(f"{path.name}:{line}: invalid price or volume")
    if high < max(op, low, close) or low > min(op, high, close):
        raise IntegrityError(f"{path.name}:{line}: invalid OHLC extremes")
    return Bar(timestamp.astimezone(UTC), *values)


def _read_bars(path: Path, *, minutes: int = 1) -> Iterator[Bar]:
    if not path.is_file():
        raise IntegrityError(f"Missing CSV: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        header = next(reader, None)
        if header is None or tuple(header) != HEADER:
            raise IntegrityError(f"{path.name}: unexpected CSV header")
        previous: datetime | None = None
        for line, row in enumerate(reader, 2):
            bar = _parse_bar(row, path, line, minutes)
            if previous is not None and bar.timestamp <= previous:
                raise IntegrityError(f"{path.name}:{line}: duplicate or unsorted")
            previous = bar.timestamp
            yield bar


def _bucket_start(timestamp: datetime) -> datetime:
    return timestamp.replace(minute=timestamp.minute // 15 * 15)


class M15Counter:
    """Потокова перевірка контракту WorkspaceTimeframeAggregator M1→M15."""

    def __init__(self) -> None:
        self.summary = Summary()
        self.start: datetime | None = None
        self.first: Bar | None = None
        self.last: Bar | None = None
        self.count = 0
        self.high = 0.0
        self.low = 0.0
        self.volume = 0.0
        self.previous_source: datetime | None = None

    def add(self, bar: Bar) -> CompletedM15 | None:
        timestamp = bar.timestamp
        if self.previous_source is not None and timestamp <= self.previous_source:
            raise IntegrityError("M1 timestamps are not strictly increasing")
        current_start = _bucket_start(timestamp)
        completed: CompletedM15 | None = None
        if self.start is not None and current_start != self.start:
            missed = int((current_start - self.start) // M15_DELTA) - 1
            if missed < 0:
                raise IntegrityError("M15 buckets are not ordered")
            self.summary.absent_buckets_between_observations += missed
            for index in range(1, missed + 1):
                absent_start = self.start + M15_DELTA * index
                self.summary.absent_by_year[absent_start.year] += 1
            completed = self._finish()
            self._clear()
        if self.start is None:
            self.start = current_start
            self.first = bar
            self.high = bar.high
            self.low = bar.low
        else:
            self.high = max(self.high, bar.high)
            self.low = min(self.low, bar.low)
        self.last = bar
        self.count += 1
        self.volume += bar.volume
        self.previous_source = timestamp
        self.summary.source_rows += 1
        return completed

    def finish(self) -> CompletedM15 | None:
        completed = self._finish()
        self._clear()
        return completed

    def _finish(self) -> CompletedM15 | None:
        if self.start is None or self.first is None or self.last is None:
            return None
        summary = self.summary
        summary.observed_buckets += 1
        complete = (
            self.count == 15
            and self.first.timestamp == self.start
            and self.last.timestamp == self.start + timedelta(minutes=14)
        )
        if not complete:
            summary.incomplete_buckets += 1
            summary.incomplete_by_count[self.count] += 1
            summary.incomplete_by_year[self.start.year] += 1
            summary.incomplete_missing_m1 += 15 - self.count
            return None
        summary.complete_buckets += 1
        summary.complete_by_year[self.start.year] += 1
        if summary.first_complete is None:
            summary.first_complete = self.start
        summary.last_complete = self.start
        return CompletedM15(
            timestamp=self.start,
            available_at=self.start + M15_DELTA,
            open=self.first.open,
            high=self.high,
            low=self.low,
            close=self.last.close,
            volume=self.volume,
        )

    def _clear(self) -> None:
        self.start = None
        self.first = None
        self.last = None
        self.count = 0
        self.high = 0.0
        self.low = 0.0
        self.volume = 0.0


def _filename(symbol: str, part: int) -> str:
    return f"{FIRST_DATES[part]}_{LAST_DATES[part]}_" f"CTRADER_{symbol}_M1.csv"


def _read_direct_m15(root: Path, symbol: str) -> dict[datetime, Bar]:
    folder = root / symbol / "M15"
    if not folder.is_dir():
        return {}
    matches = sorted(folder.glob("*_CTRADER_" + symbol + "_M15.csv"))
    if not matches:
        return {}
    catalog: dict[datetime, Bar] = {}
    for path in matches:
        for bar in _read_bars(path, minutes=15):
            prior = catalog.get(bar.timestamp)
            if prior is not None and prior != bar:
                raise IntegrityError("Conflicting broker M15 reference duplicates")
            catalog[bar.timestamp] = bar
    return catalog


def _compare_direct(
    derived: CompletedM15,
    catalog: dict[datetime, Bar],
    stats: DirectCompare,
) -> None:
    reference = catalog.get(derived.timestamp)
    if reference is None:
        return
    stats.seen.add(derived.timestamp)
    stats.matched_complete += 1
    differences = (
        abs(derived.open - reference.open),
        abs(derived.high - reference.high),
        abs(derived.low - reference.low),
        abs(derived.close - reference.close),
    )
    if any(delta > 1e-10 for delta in differences):
        stats.price_mismatches += 1
        if stats.first_price_mismatch is None:
            stats.first_price_mismatch = derived.timestamp.isoformat()
    stats.max_close_delta = max(stats.max_close_delta, differences[3])
    if not math.isclose(derived.volume, reference.volume, abs_tol=1e-7):
        stats.volume_mismatches += 1


def _next_or_none(iterator: Iterator[Bar]) -> Bar | None:
    return next(iterator, None)


def _compare_legacy(
    new_path: Path,
    old_path: Path,
    year: int,
    end_date: str,
) -> LegacyCompare | None:
    if not old_path.is_file():
        print(f"legacy={year}|file={old_path.name}|status=NOT_AVAILABLE")
        return None
    stats = LegacyCompare()
    start = datetime.fromisoformat(f"{year}-01-01T00:00:00+00:00")
    end = datetime.fromisoformat(f"{end_date}T23:59:00+00:00")
    new_iter = _read_bars(new_path)
    old_iter = _read_bars(old_path)
    newest = _next_or_none(new_iter)
    oldest = _next_or_none(old_iter)
    while newest is not None and newest.timestamp < start:
        newest = _next_or_none(new_iter)
    while oldest is not None or (newest is not None and newest.timestamp <= end):
        if oldest is None:
            stats.only_new += 1
            newest = _next_or_none(new_iter)
            continue
        stats.old_rows += 1
        if newest is None or newest.timestamp > end:
            stats.only_old += 1
            oldest = _next_or_none(old_iter)
            continue
        if oldest.timestamp < newest.timestamp:
            stats.only_old += 1
            oldest = _next_or_none(old_iter)
        elif newest.timestamp < oldest.timestamp:
            stats.only_new += 1
            newest = _next_or_none(new_iter)
            stats.old_rows -= 1
        else:
            stats.matched_timestamps += 1
            differences = (
                abs(oldest.open - newest.open),
                abs(oldest.high - newest.high),
                abs(oldest.low - newest.low),
                abs(oldest.close - newest.close),
            )
            if any(delta > 1e-10 for delta in differences):
                stats.price_mismatches += 1
                if stats.first_price_mismatch is None:
                    stats.first_price_mismatch = oldest.timestamp.isoformat()
            if not math.isclose(oldest.volume, newest.volume, abs_tol=1e-7):
                stats.volume_mismatches += 1
            stats.max_close_delta = max(stats.max_close_delta, differences[3])
            newest = _next_or_none(new_iter)
            oldest = _next_or_none(old_iter)
    # Скільки старих рядків перевірено — незалежно від обсягу нового CSV.
    stats.old_rows = stats.matched_timestamps + stats.only_old
    same = (
        stats.only_old == 0
        and stats.only_new == 0
        and stats.price_mismatches == 0
        and stats.volume_mismatches == 0
    )
    status = "MATCH" if same else "DIFFERENCE_REPORTED"
    print(
        f"legacy={year}|status={status}|old_rows={stats.old_rows}"
        f"|matched={stats.matched_timestamps}|only_old={stats.only_old}"
        f"|only_new={stats.only_new}|price_different={stats.price_mismatches}"
        f"|volume_different={stats.volume_mismatches}"
        f"|max_close_delta={stats.max_close_delta:.10f}"
        f"|first_price_difference={stats.first_price_mismatch or 'NONE'}"
    )
    return stats


def _audit_symbol(root: Path, symbol: str) -> int:
    print(f"SYMBOL={symbol}")
    counter = M15Counter()
    direct = _read_direct_m15(root, symbol)
    direct_stats = DirectCompare(reference_count=len(direct))
    previous_part_last: datetime | None = None
    complete_before = 0
    for part in range(3):
        path = root / symbol / "M1" / _filename(symbol, part)
        rows = 0
        first: datetime | None = None
        last: datetime | None = None
        for bar in _read_bars(path):
            if first is None:
                first = bar.timestamp
            last = bar.timestamp
            output = counter.add(bar)
            if output is not None:
                _compare_direct(output, direct, direct_stats)
            rows += 1
        if rows != EXPECTED[symbol][part]:
            raise IntegrityError(
                f"{path.name}: rows={rows}, expected={EXPECTED[symbol][part]}"
            )
        if first is None or last is None:
            raise IntegrityError(f"{path.name}: empty history")
        if previous_part_last is not None:
            if first <= previous_part_last:
                raise IntegrityError(f"{symbol}: overlapping parts")
            print(
                f"boundary={part}|previous={previous_part_last.isoformat()}"
                f"|next={first.isoformat()}"
            )
        previous_part_last = last
        new_complete = counter.summary.complete_buckets - complete_before
        complete_before = counter.summary.complete_buckets
        print(
            f"part={part + 1}|rows={rows}|first={first.isoformat()}"
            f"|last={last.isoformat()}|new_complete_m15={new_complete}"
        )
    last_output = counter.finish()
    if last_output is not None:
        _compare_direct(last_output, direct, direct_stats)
    summary = counter.summary
    if summary.source_rows != sum(EXPECTED[symbol]):
        raise IntegrityError(f"{symbol}: source totals changed")
    if sum(summary.incomplete_by_count.values()) != summary.incomplete_buckets:
        raise IntegrityError(f"{symbol}: incomplete bucket counts differ")
    counted = summary.complete_buckets + summary.incomplete_buckets
    if counted != summary.observed_buckets:
        raise IntegrityError(f"{symbol}: bucket accounting incomplete")
    print(
        f"symbol={symbol}|observed_m15={summary.observed_buckets}"
        f"|complete_m15={summary.complete_buckets}"
        f"|incomplete_m15={summary.incomplete_buckets}"
        f"|absent_m15_between={summary.absent_buckets_between_observations}"
        f"|missing_m1_inside_incomplete={summary.incomplete_missing_m1}"
    )
    print(
        f"symbol={symbol}|incomplete_by_m1_count="
        f"{sorted(summary.incomplete_by_count.items())}"
    )
    print(
        f"symbol={symbol}|first_complete={summary.first_complete}"
        f"|last_complete={summary.last_complete}"
    )
    for year in sorted(set(summary.complete_by_year) | set(summary.incomplete_by_year)):
        print(
            f"symbol={symbol}|year={year}"
            f"|complete={summary.complete_by_year[year]}"
            f"|incomplete={summary.incomplete_by_year[year]}"
            f"|absent_between={summary.absent_by_year[year]}"
        )
    if direct:
        direct_stats.missing_in_aggregation = len(direct) - len(direct_stats.seen)
        print(
            f"symbol={symbol}|direct_M15=AVAILABLE"
            f"|direct_rows={direct_stats.reference_count}"
            f"|matched_complete={direct_stats.matched_complete}"
            f"|direct_without_complete_m1={direct_stats.missing_in_aggregation}"
            f"|price_different={direct_stats.price_mismatches}"
            f"|volume_different={direct_stats.volume_mismatches}"
            f"|max_close_delta={direct_stats.max_close_delta:.10f}"
            "|first_price_difference="
            f"{direct_stats.first_price_mismatch or 'NONE'}"
        )
    else:
        print(f"symbol={symbol}|direct_M15=NOT_AVAILABLE")
    new_path = root / symbol / "M1" / _filename(symbol, 2)
    for year, end_date in ((2025, "2025-12-31"), (2026, "2026-08-25")):
        old_path = (
            root / symbol / "M1" / f"{year}-01-01_{end_date}_CTRADER_{symbol}_M1.csv"
        )
        _compare_legacy(new_path, old_path, year, end_date)
    print(f"symbol={symbol}|aggregation_integrity=PASS")
    return summary.complete_buckets


def _synthetic_contract() -> None:
    """Контроль точного UTC bucket, OHLCV, відкидання неповного M15."""
    counter = M15Counter()
    base = datetime(2025, 1, 6, 10, 0, tzinfo=UTC)
    for minute in range(15):
        bar = Bar(
            base + timedelta(minutes=minute),
            1.1 + minute * 0.001,
            1.2 + minute * 0.001,
            1.0 + minute * 0.001,
            1.15 + minute * 0.001,
            2.0,
        )
        assert counter.add(bar) is None
    result = counter.add(Bar(base + M15_DELTA, 1.2, 1.3, 1.1, 1.25, 3.0))
    assert result is not None
    assert result.timestamp == base
    assert result.available_at == base + M15_DELTA
    assert result.open == 1.1
    assert math.isclose(result.high, 1.214)
    assert result.low == 1.0
    assert math.isclose(result.close, 1.164)
    assert result.volume == 30.0
    # Відсутній M1 усередині наступного bucket — він не видається.
    for minute in range(17, 30):
        counter.add(Bar(base + timedelta(minutes=minute), 1.2, 1.3, 1.1, 1.25, 1))
    final_bar = Bar(base + timedelta(minutes=30), 1.2, 1.3, 1.1, 1.25, 1)
    assert counter.add(final_bar) is None
    # Пропущений цілий M15-інтервал не перетворюється на порожній бар.
    bar_after_gap = Bar(base + timedelta(minutes=60), 1.2, 1.3, 1.1, 1.25, 1)
    assert counter.add(bar_after_gap) is None
    assert counter.finish() is None
    assert counter.summary.complete_buckets == 1
    assert counter.summary.incomplete_buckets == 3
    assert counter.summary.incomplete_by_count[14] == 1
    assert counter.summary.incomplete_by_count[1] == 2
    assert counter.summary.absent_buckets_between_observations == 1
    print("SYNTHETIC_M1_TO_M15_CONTRACT=OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, default=HISTORY)
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    print("T112_10_HISTORICAL_M1_TO_M15_AGGREGATION_INTEGRITY")
    print("mode=DATA_ONLY_READ_ONLY|production_aggregation_semantics=15_OF_15")
    print("m15_grid=UTC_00_15_30_45|incomplete_buckets=NOT_EMITTED")
    _synthetic_contract()
    if not args.synthetic_only:
        print(f"history_root={args.history_root}")
        total = sum(_audit_symbol(args.history_root, symbol) for symbol in SYMBOLS)
        print(f"total_complete_m15={total}")
        print("legacy_csv_comparison=DATA_ONLY_NOT_A_BASELINE_REPLAY")
    print("historical_files_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_10_HISTORICAL_M1_TO_M15_AGGREGATION_INTEGRITY=OK")


if __name__ == "__main__":
    try:
        main()
    except (IntegrityError, OSError, UnicodeError, csv.Error) as exc:
        raise SystemExit(f"T112-10 FAILED: {exc}") from exc
