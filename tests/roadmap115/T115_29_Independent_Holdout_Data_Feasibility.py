# -*- coding: utf-8 -*-
"""RoadMap115 / T115-29: перевірка holdout-історії.

TEST_ONLY / DATA_ONLY.

Зіставлення канонічних CSV із довгим архівом EURUSD M1.
Перевірка UTC, OHLC, повноти M15/H1 та прогріву індикаторів.

Торгові сигнали, ордери та результати PnL не обчислюються.
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data/history/CTRADER/EURUSD/M1"

LONG_NAME = "2024-10-22_2026-10-21_CTRADER_EURUSD_M1.csv"

REF_2025 = "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv"

REF_2026 = "2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv"

CUTOFF = datetime.fromisoformat("2026-08-25T15:07:00+00:00")

HOLDOUT_START = datetime.fromisoformat("2026-08-26T00:00:00+00:00")

HOLDOUT_END = datetime.fromisoformat("2026-10-22T00:00:00+00:00")

WARMUP_START = datetime.fromisoformat("2026-08-01T00:00:00+00:00")

HEADER = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

ONE_MINUTE = timedelta(minutes=1)


@dataclass(slots=True)
class FileStats:
    """Метадані CSV без обчислення індикаторів."""

    name: str
    rows: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    before_cutoff: int = 0
    after_cutoff: int = 0


@dataclass(slots=True)
class BucketCount:
    """Лічильник повних TF-свічок із M1."""

    minutes: int
    start_at: datetime | None = None
    first_at: datetime | None = None
    last_at: datetime | None = None
    seen: int = 0
    complete: int = 0
    incomplete: int = 0

    def add(self, at: datetime) -> None:
        """Додати M1 до відповідного UTC-інтервалу."""
        assert 1440 % self.minutes == 0

        day = at.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        minute = at.hour * 60 + at.minute

        bucket_start = day + timedelta(minutes=minute // self.minutes * self.minutes)

        if self.start_at != bucket_start:
            self.finish()
            self.start_at = bucket_start

        if self.seen == 0:
            self.first_at = at

        self.last_at = at
        self.seen += 1

    def finish(self) -> None:
        """Зарахувати тільки повністю завершену свічку."""
        if self.start_at is None:
            return

        expected_last = self.start_at + timedelta(minutes=self.minutes - 1)

        valid = (
            self.seen == self.minutes
            and self.first_at == self.start_at
            and self.last_at == expected_last
        )

        if valid:
            self.complete += 1
        else:
            self.incomplete += 1

        self.start_at = None
        self.first_at = None
        self.last_at = None
        self.seen = 0


def _timestamp(raw: str) -> datetime:
    """Приймати лише UTC із хвилинною точністю."""
    at = datetime.fromisoformat(raw.replace("Z", "+00:00"))

    assert at.tzinfo is not None
    assert at.utcoffset() == timedelta(0)
    assert at.second == 0
    assert at.microsecond == 0

    return at.astimezone(UTC)


def _check_row(
    cells: list[str],
    previous_at: datetime | None,
) -> datetime:
    """Перевірити схему, час і коректність OHLC."""
    assert len(cells) == len(HEADER)

    at = _timestamp(cells[0])

    if previous_at is not None:
        assert at > previous_at

    open_price = float(cells[1])
    high_price = float(cells[2])
    low_price = float(cells[3])
    close_price = float(cells[4])
    volume = float(cells[5])

    prices = (
        open_price,
        high_price,
        low_price,
        close_price,
    )

    assert all(math.isfinite(value) and value > 0 for value in prices)

    assert low_price <= min(open_price, close_price)
    assert max(open_price, close_price) <= high_price

    assert math.isfinite(volume)
    assert volume >= 0

    return at


def _reader(stream: TextIO) -> Iterator[list[str]]:
    """Відкрити CSV зі строгою схемою колонок."""
    rows = csv.reader(stream)

    header = next(rows, None)

    assert header is not None
    assert tuple(header) == HEADER

    return rows


def _sha(path: Path) -> str:
    """Обчислити SHA256 без завантаження файлу в RAM."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _reference(path: Path) -> FileStats:
    """Перевірити окремий канонічний CSV."""
    stats = FileStats(name=path.name)

    previous_at: datetime | None = None

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        for cells in _reader(stream):
            at = _check_row(cells, previous_at)

            if stats.first_at is None:
                stats.first_at = at

            stats.last_at = at
            stats.rows += 1

            if at <= CUTOFF:
                stats.before_cutoff += 1
            else:
                stats.after_cutoff += 1

            previous_at = at

    assert stats.rows > 0

    return stats


def _required_bounds(
    stats: FileStats,
) -> tuple[datetime, datetime]:
    """Повернути гарантовано визначені межі CSV."""
    start_at = stats.first_at
    end_at = stats.last_at

    if start_at is None or end_at is None:
        raise AssertionError(f"EMPTY_OR_INVALID_FILE: {stats.name}")

    assert start_at <= end_at

    return start_at, end_at


def _synthetic() -> None:
    """Контроль причинності UTC та повноти свічок."""
    assert CUTOFF < HOLDOUT_START
    assert WARMUP_START < HOLDOUT_START
    assert HOLDOUT_START < HOLDOUT_END

    origin = datetime.fromisoformat("2026-08-26T00:00:00+00:00")

    assert _timestamp("2026-08-26T00:00:00Z") == origin

    assert _timestamp("2026-08-26T00:01:00Z") > origin

    complete = BucketCount(minutes=15)

    for index in range(15):
        complete.add(origin + timedelta(minutes=index))

    complete.finish()

    assert complete.complete == 1
    assert complete.incomplete == 0

    incomplete = BucketCount(minutes=15)

    for index in range(15):
        if index == 7:
            continue

        incomplete.add(origin + timedelta(minutes=index))

    incomplete.finish()

    assert incomplete.complete == 0
    assert incomplete.incomplete == 1

    boundary = BucketCount(minutes=60)

    for index in range(1, 60):
        boundary.add(origin + timedelta(minutes=index))

    boundary.finish()

    assert boundary.complete == 0
    assert boundary.incomplete == 1

    print("SYNTHETIC_UTC_CUTOFF_ISOLATION=OK")
    print("SYNTHETIC_COMPLETE_TF_BUCKETS_ONLY=OK")


def _audit() -> None:
    """Звірити джерела та придатність holdout."""
    archive_path = DATA / LONG_NAME
    ref_2025_path = DATA / REF_2025
    ref_2026_path = DATA / REF_2026

    paths = (
        archive_path,
        ref_2025_path,
        ref_2026_path,
    )

    assert all(path.is_file() for path in paths)

    stats_2025 = _reference(ref_2025_path)
    stats_2026 = _reference(ref_2026_path)

    assert stats_2025.rows == 370481
    assert stats_2026.rows == 239867
    assert stats_2026.before_cutoff == 239750

    start_2025, end_2025 = _required_bounds(stats_2025)

    start_2026, end_2026 = _required_bounds(stats_2026)

    assert end_2025 < start_2026
    assert end_2026 < HOLDOUT_START

    print(
        f"CANONICAL|YEAR=2025|ROWS={stats_2025.rows}|"
        f"FIRST={start_2025.isoformat()}|"
        f"LAST={end_2025.isoformat()}"
    )

    print(
        f"CANONICAL|YEAR=2026|ROWS={stats_2026.rows}|"
        f"REPLAY_ROWS={stats_2026.before_cutoff}|"
        f"POST_CUTOFF_ROWS={stats_2026.after_cutoff}|"
        f"LAST={end_2026.isoformat()}"
    )

    warm = {
        15: BucketCount(minutes=15),
        60: BucketCount(minutes=60),
    }

    hold = {
        15: BucketCount(minutes=15),
        60: BucketCount(minutes=60),
    }

    archive_stats = FileStats(name=archive_path.name)

    match_2025 = 0
    match_2026 = 0
    replay_2026 = 0

    hold_rows = 0
    hold_gaps = 0
    max_gap = 0

    previous_hold_at: datetime | None = None
    hold_first_at: datetime | None = None
    hold_last_at: datetime | None = None

    observed_days: set[str] = set()
    observed_weeks: set[str] = set()

    with (
        archive_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as archive_stream,
        ref_2025_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream_2025,
        ref_2026_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream_2026,
    ):
        rows_archive = _reader(archive_stream)
        rows_2025 = _reader(stream_2025)
        rows_2026 = _reader(stream_2026)

        next_2025 = next(rows_2025, None)
        next_2026 = next(rows_2026, None)

        previous_at: datetime | None = None

        for cells in rows_archive:
            at = _check_row(cells, previous_at)

            if archive_stats.first_at is None:
                archive_stats.first_at = at

            archive_stats.last_at = at
            archive_stats.rows += 1

            if start_2025 <= at <= end_2025:
                assert next_2025 is not None
                assert cells == next_2025, "2025_OVERLAP_MISMATCH"

                match_2025 += 1
                next_2025 = next(rows_2025, None)

            if start_2026 <= at <= end_2026:
                assert next_2026 is not None
                assert cells == next_2026, "2026_OVERLAP_MISMATCH"

                match_2026 += 1

                if at <= CUTOFF:
                    replay_2026 += 1

                next_2026 = next(rows_2026, None)

            if WARMUP_START <= at < HOLDOUT_START:
                for meter in warm.values():
                    meter.add(at)

            if HOLDOUT_START <= at < HOLDOUT_END:
                if hold_first_at is None:
                    hold_first_at = at

                hold_last_at = at
                hold_rows += 1

                if previous_hold_at is not None:
                    delta = int((at - previous_hold_at) / ONE_MINUTE)

                    assert delta > 0

                    if delta > 1:
                        hold_gaps += 1
                        max_gap = max(
                            max_gap,
                            delta - 1,
                        )

                previous_hold_at = at

                observed_days.add(at.date().isoformat())

                iso = at.isocalendar()

                observed_weeks.add(f"{iso.year}-W{iso.week:02d}")

                for meter in hold.values():
                    meter.add(at)

            previous_at = at

        assert next_2025 is None
        assert next_2026 is None

    for meter in warm.values():
        meter.finish()

    for meter in hold.values():
        meter.finish()

    assert match_2025 == stats_2025.rows
    assert match_2026 == stats_2026.rows

    assert replay_2026 == (stats_2026.before_cutoff)

    assert archive_stats.rows == 740705

    archive_start, archive_end = _required_bounds(archive_stats)

    assert hold_first_at is not None
    assert hold_last_at is not None

    assert hold_first_at >= HOLDOUT_START
    assert hold_last_at < HOLDOUT_END

    assert hold_rows > 0
    assert hold[15].complete > 100
    assert hold[60].complete > 100
    assert warm[60].complete > 100

    print(
        f"ARCHIVE|ROWS={archive_stats.rows}|"
        f"FIRST={archive_start.isoformat()}|"
        f"LAST={archive_end.isoformat()}"
    )

    print(
        f"OVERLAP|2025_EXACT_ROWS={match_2025}|"
        f"2026_EXACT_ROWS={match_2026}|"
        f"2026_REPLAY_EXACT_ROWS={replay_2026}|"
        "MISMATCH=0"
    )

    print(
        f"HOLDOUT|START={HOLDOUT_START.isoformat()}|"
        f"FIRST_M1={hold_first_at.isoformat()}|"
        f"LAST_M1={hold_last_at.isoformat()}|"
        f"ROWS={hold_rows}|"
        f"ACTIVE_DAYS={len(observed_days)}|"
        f"CALENDAR_WEEKS={len(observed_weeks)}"
    )

    print(
        f"HOLDOUT_GAPS|COUNT={hold_gaps}|"
        f"LARGEST_MISSING_MIN={max_gap}|"
        "FORWARD_FILL=False"
    )

    for minutes, name in (
        (15, "M15"),
        (60, "H1"),
    ):
        meter = hold[minutes]

        print(
            f"HOLDOUT_TF|TF={name}|"
            f"COMPLETE={meter.complete}|"
            f"INCOMPLETE={meter.incomplete}|"
            "COMPLETED_ONLY=True"
        )

        print(
            f"WARMUP_TF|TF={name}|"
            f"COMPLETE={warm[minutes].complete}|"
            f"WINDOW_FROM={WARMUP_START.isoformat()}"
        )

    print(
        f"ISOLATION|REPLAY_CUTOFF={CUTOFF.isoformat()}|"
        f"HOLDOUT_START={HOLDOUT_START.isoformat()}|"
        "TIME_OVERLAP=False"
    )

    print("HOLDOUT_FEASIBILITY=" "DATA_AVAILABLE_NOT_STATISTICALLY_VALIDATED")

    print("HOLDOUT_PNL_COMPUTED=False|" "PARAMETER_TUNING=False")

    for path in paths:
        print(f"SOURCE_SHA256|FILE={path.name}|" f"VALUE={_sha(path)}")


def main() -> None:
    """Виконати аудит, не змінюючи production."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-29|TEST_ONLY|" "INDEPENDENT_HOLDOUT_DATA_FEASIBILITY")

    print("HISTORY=CTRADER_EURUSD_M1|" "NO_TRADING_LOGIC=True")

    print("TIME_FORWARD_CANDIDATE=True|" "TRUE_OOS_UNPROVEN=True")

    _synthetic()
    _audit()

    after = [_sha(path) for path in guarded]

    assert before == after

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")

    print("broker_requests=0|" "TEST_ONLY=True|DATA_ONLY=True")

    print("production_changed=False|" "md7_changed=False")

    print("T115_29_INDEPENDENT_" "HOLDOUT_DATA_FEASIBILITY=OK")


if __name__ == "__main__":
    main()
