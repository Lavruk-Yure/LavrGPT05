# -*- coding: utf-8 -*-
"""T112-09 — аудит дев'яти CSV M1 без зміни даних і production."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TextIO

HEADER = ("timestamp", "open", "high", "low", "close", "volume")
ONE_MINUTE = timedelta(minutes=1)
SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
REQUESTED_PERIODS = (
    (date(2020, 10, 22), date(2022, 10, 21)),
    (date(2022, 10, 22), date(2024, 10, 21)),
    (date(2024, 10, 22), date(2026, 10, 21)),
)

# Контрольні кількості з повідомлень LGE, а не припущення про календар Forex.
EXPECTED_COUNTS = {
    "EURUSD": (740943, 739343, 740705),
    "GBPUSD": (741655, 739855, 740323),
    "USDJPY": (741436, 740653, 739841),
}

# У назві CSV LGE використовує дати перших і останніх фактичних барів.
EXPECTED_FIRST_DATES = (
    date(2020, 10, 22),
    date(2022, 10, 23),
    date(2024, 10, 22),
)


class AuditError(ValueError):
    """Порушено контракт CSV або часової послідовності."""


@dataclass(frozen=True, slots=True)
class CsvAudit:
    path: Path
    rows: int
    first: datetime
    last: datetime
    gap_count: int
    weekend_gaps: int
    weekday_gaps: int
    missing_minutes: int
    longest_weekday_gap: tuple[datetime, datetime, int] | None


def _parse_time(value: str, *, path: Path, line: int) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError(f"{path.name}:{line}: invalid timestamp={value!r}") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise AuditError(f"{path.name}:{line}: timestamp is not UTC")
    if timestamp.second != 0 or timestamp.microsecond != 0:
        raise AuditError(f"{path.name}:{line}: timestamp not aligned to M1")
    return timestamp.astimezone(UTC)


def _parse_ohlcv(row: list[str], *, path: Path, line: int) -> None:
    if len(row) != len(HEADER):
        raise AuditError(f"{path.name}:{line}: expected 6 columns, got {len(row)}")
    try:
        values = [float(value) for value in row[1:]]
    except ValueError as exc:
        raise AuditError(f"{path.name}:{line}: invalid OHLCV number") from exc
    if not all(math.isfinite(value) for value in values):
        raise AuditError(f"{path.name}:{line}: NaN/Inf in OHLCV")
    open_price, high, low, close, volume = values
    if min(open_price, high, low, close) <= 0 or volume < 0:
        raise AuditError(f"{path.name}:{line}: non-positive price or negative volume")
    if high < max(open_price, low, close) - 1e-10:
        raise AuditError(f"{path.name}:{line}: high violates OHLC")
    if low > min(open_price, high, close) + 1e-10:
        raise AuditError(f"{path.name}:{line}: low violates OHLC")


def _touches_weekend(previous: datetime, current: datetime) -> bool:
    """Позначає прогалину, що перетинає суботу або неділю UTC."""
    day = previous.date()
    end_day = current.date()
    while day <= end_day:
        if day.weekday() in (5, 6):
            return True
        day += timedelta(days=1)
    return False


def _read_audit(
    handle: TextIO,
    path: Path,
    start: date,
    end: date,
    expected_rows: int,
) -> CsvAudit:
    reader = csv.reader(handle, strict=True)
    header = next(reader, None)
    if header is None or tuple(header) != HEADER:
        raise AuditError(f"{path.name}: unexpected CSV header={header!r}")

    rows = 0
    first: datetime | None = None
    previous: datetime | None = None
    gap_count = 0
    weekend_gaps = 0
    weekday_gaps = 0
    missing_minutes = 0
    longest: tuple[datetime, datetime, int] | None = None

    for line, row in enumerate(reader, start=2):
        if len(row) != len(HEADER):
            raise AuditError(f"{path.name}:{line}: expected 6 columns, got {len(row)}")
        timestamp = _parse_time(row[0], path=path, line=line)
        _parse_ohlcv(row, path=path, line=line)
        if timestamp.date() < start or timestamp.date() > end:
            raise AuditError(f"{path.name}:{line}: timestamp outside requested period")
        if first is None:
            first = timestamp
        if previous is not None:
            difference = timestamp - previous
            if difference <= timedelta(0):
                raise AuditError(
                    f"{path.name}:{line}: duplicate/out-of-order timestamp "
                    f"{timestamp.isoformat()}"
                )
            if difference > ONE_MINUTE:
                missing = int(difference.total_seconds() // 60) - 1
                gap_count += 1
                missing_minutes += missing
                if _touches_weekend(previous, timestamp):
                    weekend_gaps += 1
                else:
                    weekday_gaps += 1
                    if longest is None or missing > longest[2]:
                        longest = (previous, timestamp, missing)
        previous = timestamp
        rows += 1

    if first is None or previous is None:
        raise AuditError(f"{path.name}: CSV has no bars")
    if rows != expected_rows:
        raise AuditError(
            f"{path.name}: rows={rows}, screenshot_expected={expected_rows}"
        )
    return CsvAudit(
        path=path,
        rows=rows,
        first=first,
        last=previous,
        gap_count=gap_count,
        weekend_gaps=weekend_gaps,
        weekday_gaps=weekday_gaps,
        missing_minutes=missing_minutes,
        longest_weekday_gap=longest,
    )


def _audit_file(
    root: Path,
    symbol: str,
    period_index: int,
) -> CsvAudit:
    start, end = REQUESTED_PERIODS[period_index]
    first_date = EXPECTED_FIRST_DATES[period_index]
    filename = (
        f"{first_date:%Y-%m-%d}_{end:%Y-%m-%d}_"
        f"CTRADER_{symbol}_M1.csv"
    )
    path = root / symbol / "M1" / filename
    if not path.is_file():
        raise AuditError(f"Missing CSV: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            result = _read_audit(
                handle,
                path,
                start,
                end,
                EXPECTED_COUNTS[symbol][period_index],
            )
    except (OSError, UnicodeError, csv.Error) as exc:
        raise AuditError(f"Cannot read {path}: {exc}") from exc
    if result.first.date() != first_date:
        raise AuditError(f"{path.name}: unexpected first bar={result.first}")
    if result.last.date() != end:
        raise AuditError(f"{path.name}: unexpected last bar={result.last}")
    return result


def _print_csv(result: CsvAudit, part: int) -> None:
    print(
        f"part={part}|file={result.path.name}|rows={result.rows}"
        f"|first={result.first.isoformat()}|last={result.last.isoformat()}"
    )
    print(
        f"part={part}|gaps={result.gap_count}"
        f"|weekend_touching={result.weekend_gaps}"
        f"|without_weekend={result.weekday_gaps}"
        f"|missing_calendar_minutes={result.missing_minutes}"
    )
    if result.longest_weekday_gap is not None:
        previous, current, missing = result.longest_weekday_gap
        print(
            f"part={part}|largest_no_weekend_gap="
            f"{previous.isoformat()} -> {current.isoformat()}"
            f"|missing_minutes={missing}"
        )


def _audit_symbol(root: Path, symbol: str) -> int:
    print(f"SYMBOL={symbol}")
    results: list[CsvAudit] = []
    for index in range(len(REQUESTED_PERIODS)):
        result = _audit_file(root, symbol, index)
        results.append(result)
        _print_csv(result, index + 1)
        if len(results) < 2:
            continue
        previous = results[-2]
        if result.first <= previous.last:
            raise AuditError(
                f"{symbol}: overlapping blocks: "
                f"{previous.path.name} / {result.path.name}"
            )
        missing = int((result.first - previous.last).total_seconds() // 60) - 1
        weekend = _touches_weekend(previous.last, result.first)
        print(
            f"boundary={index}|previous={previous.last.isoformat()}"
            f"|next={result.first.isoformat()}|missing_minutes={missing}"
            f"|weekend_touching={weekend}"
        )
    total = sum(result.rows for result in results)
    expected = sum(EXPECTED_COUNTS[symbol])
    if total != expected:
        raise AuditError(f"{symbol}: total={total}, expected={expected}")
    print(f"symbol={symbol}|total_rows={total}|expected_rows={expected}|status=PASS")
    return total


def _synthetic_contract() -> None:
    """Перевіряє базову валідацію без файлів брокера."""
    from io import StringIO

    fake = Path("synthetic.csv")
    source = (
        "timestamp,open,high,low,close,volume\n"
        "2026-01-05T10:00:00Z,1.2,1.3,1.1,1.25,0\n"
        "2026-01-05T10:02:00Z,1.2,1.3,1.1,1.25,2\n"
    )
    checked = _read_audit(
        StringIO(source), fake, date(2026, 1, 5), date(2026, 1, 5), 2
    )
    assert checked.rows == 2
    assert checked.weekday_gaps == 1
    assert checked.missing_minutes == 1
    invalid = source.replace("10:02:00Z", "10:00:00Z")
    try:
        _read_audit(
            StringIO(invalid), fake, date(2026, 1, 5), date(2026, 1, 5), 2
        )
    except AuditError:
        pass
    else:
        raise AssertionError("Duplicate timestamps must be rejected")
    print("SYNTHETIC_M1_INTEGRITY_CONTRACT=OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    project_root = Path(__file__).resolve().parents[2]
    default_root = project_root / "data" / "history" / "CTRADER"
    parser.add_argument("--history-root", type=Path, default=default_root)
    args = parser.parse_args()
    print("T112_09_HISTORICAL_M1_DATA_INTEGRITY")
    print("mode=DATA_ONLY_READ_ONLY")
    print("timeframe=M1|broker=CTRADER|timezone=UTC")
    print(f"history_root={args.history_root.resolve()}")
    _synthetic_contract()
    try:
        total = 0
        for symbol in SYMBOLS:
            total += _audit_symbol(args.history_root, symbol)
    except AuditError as exc:
        print(f"DATA_INTEGRITY=FAIL|reason={exc}")
        print("production_logic_changed=False|broker_requests=0")
        return 1
    expected_total = sum(sum(EXPECTED_COUNTS[s]) for s in SYMBOLS)
    assert total == expected_total
    print(f"all_symbols_total_rows={total}|expected={expected_total}")
    print("market_calendar_completeness=NOT_ASSERTED")
    print("minute_gaps=REPORTED_NOT_AUTOMATICALLY_CORRUPTION")
    print("file_contents_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_09_HISTORICAL_M1_DATA_INTEGRITY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
