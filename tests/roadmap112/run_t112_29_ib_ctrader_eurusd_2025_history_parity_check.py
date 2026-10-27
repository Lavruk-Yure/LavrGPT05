"""T112-29 — незалежний DATA_ONLY аудит IB і cTrader EURUSD за 2025.

TEST_ONLY: порівнює доступні UTC M1 та повні M15. Жодних broker API,
ордерів, торгового Replay, змін історичних файлів або production-логіки.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = PROJECT_ROOT / "data" / "history"
SYMBOL = "EURUSD"
YEAR = 2025
PIP = 0.0001
COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
CT_FILE = "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv"
IB_FILE = "2025-01-02_2025-12-31_IB_EURUSD_M1.csv"
MINUTE = timedelta(minutes=1)
QUARTER = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class PriceBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class M15Bar:
    timestamp: datetime
    completed_at: datetime
    open: float
    high: float
    low: float
    close: float


class CompletedM15:
    """Використовувати лише 15 послідовних M1 в UTC-сітці."""

    def __init__(self) -> None:
        self.current: list[PriceBar] = []
        self.bucket: datetime | None = None
        self.bars: dict[datetime, M15Bar] = {}
        self.complete = 0
        self.incomplete = 0

    @staticmethod
    def _bucket_start(stamp: datetime) -> datetime:
        return stamp.replace(minute=stamp.minute // 15 * 15, second=0)

    def add(self, bar: PriceBar) -> None:
        start = self._bucket_start(bar.timestamp)
        if self.bucket is not None and start != self.bucket:
            self.finish()
        self.bucket = start
        self.current.append(bar)

    def finish(self) -> None:
        if self.bucket is None or not self.current:
            return
        start = self.bucket
        bars = self.current
        is_complete = len(bars) == 15 and all(
            item.timestamp == start + MINUTE * i for i, item in enumerate(bars)
        )
        if is_complete:
            self.bars[start] = M15Bar(
                timestamp=start,
                completed_at=start + QUARTER,
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
            )
            self.complete += 1
        else:
            self.incomplete += 1
        self.current = []
        self.bucket = None


class HistoryReader:
    """Потокове читання M1 із перевіркою хронології й OHLC."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.m15 = CompletedM15()
        self.rows = 0
        self.first: datetime | None = None
        self.last: datetime | None = None
        self.zero_volume = 0

    def read(self) -> Iterator[PriceBar]:
        assert self.path.is_file(), f"CSV_NOT_FOUND: {self.path}"
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            assert tuple(next(reader)) == COLUMNS, self.path.name
            for row in reader:
                assert len(row) == len(COLUMNS), (self.path, row)
                stamp = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                assert stamp.tzinfo is not None
                stamp = stamp.astimezone(UTC)
                assert stamp.year == YEAR
                assert stamp.second == stamp.microsecond == 0
                assert self.last is None or stamp > self.last
                o, h, l, c = (float(value) for value in row[1:5])
                assert all(math.isfinite(x) and x > 0 for x in (o, h, l, c))
                assert l <= min(o, c) <= max(o, c) <= h
                if float(row[5]) == 0.0:
                    self.zero_volume += 1
                bar = PriceBar(stamp, o, h, l, c)
                self.first = stamp if self.first is None else self.first
                self.last = stamp
                self.rows += 1
                self.m15.add(bar)
                yield bar
        self.m15.finish()
        assert self.rows > 1000, (self.path, self.rows)


def _quantile(values: list[float], q: float) -> float:
    assert 0.0 <= q <= 1.0
    if not values:
        return float("nan")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _describe(name: str, deltas: list[float], exact: int) -> None:
    assert deltas
    absolute = [abs(x) for x in deltas]
    over_half = sum(x >= 0.5 for x in absolute)
    over_one = sum(x >= 1.0 for x in absolute)
    print(
        f"{name}|n:{len(deltas)},exact:{exact},"
        f"mean_signed_pips:{mean(deltas):+.4f},"
        f"median_abs_pips:{median(absolute):.4f},"
        f"p90_abs_pips:{_quantile(absolute, 0.9):.4f},"
        f"p99_abs_pips:{_quantile(absolute, 0.99):.4f},"
        f"max_abs_pips:{max(absolute):.4f},"
        f"abs_ge_0_5_pip:{over_half},abs_ge_1_pip:{over_one}"
    )


def _synthetic_contract() -> None:
    start = datetime(2025, 1, 2, 1, 0, tzinfo=UTC)
    m15 = CompletedM15()
    for i in range(15):
        m15.add(PriceBar(start + i * MINUTE, 1.0, 1.1, 0.9, 1.01))
    m15.add(PriceBar(start + 16 * MINUTE, 1.0, 1.1, 0.9, 1.01))
    m15.finish()
    assert m15.complete == 1
    assert m15.incomplete == 1
    assert m15.bars[start].completed_at == start + QUARTER
    assert math.isclose(_quantile([0, 2, 4], 0.5), 2)
    print("SYNTHETIC_COMPLETED_M15_NO_LOOKAHEAD=OK")


def main() -> None:
    print("T112_29_IB_CTRADER_EURUSD_2025_HISTORY_PARITY")
    print("test_id=T112-29|mode=RM112_T112_29_DATA_ONLY_TEST_ONLY")
    print("symbol=EURUSD|period=2025|source_timeframe=M1|target=M15")
    print("timestamp_basis=UTC|m15=STRICT_15_OF_15_COMPLETED_ONLY")
    print("price_delta=IB_MINUS_CTRADER_IN_PIPS|pip_size=0.0001")
    print("volume=NOT_COMPARED|quote_type=REQUIRES_BROKER_SOURCE_CONTEXT")
    _synthetic_contract()

    ct = HistoryReader(HISTORY_ROOT / "CTRADER" / SYMBOL / "M1" / CT_FILE)
    ib = HistoryReader(HISTORY_ROOT / "IB" / SYMBOL / "M1" / IB_FILE)
    ct_iter = iter(ct.read())
    ib_iter = iter(ib.read())
    ct_bar = next(ct_iter, None)
    ib_bar = next(ib_iter, None)
    overlap = 0
    ct_only: list[datetime] = []
    ib_only: list[datetime] = []
    m1_close: list[float] = []
    m1_exact = 0
    early_pairs: list[str] = []

    while ct_bar is not None or ib_bar is not None:
        if ib_bar is None or (
            ct_bar is not None and ct_bar.timestamp < ib_bar.timestamp
        ):
            ct_only.append(ct_bar.timestamp)
            ct_bar = next(ct_iter, None)
            continue
        if ct_bar is None or ib_bar.timestamp < ct_bar.timestamp:
            ib_only.append(ib_bar.timestamp)
            ib_bar = next(ib_iter, None)
            continue
        delta = (ib_bar.close - ct_bar.close) / PIP
        m1_close.append(delta)
        m1_exact += abs(delta) < 1e-9
        overlap += 1
        if len(early_pairs) < 3:
            early_pairs.append(f"{ct_bar.timestamp.isoformat()}:{delta:+.3f}")
        ct_bar = next(ct_iter, None)
        ib_bar = next(ib_iter, None)

    assert overlap + len(ct_only) == ct.rows
    assert overlap + len(ib_only) == ib.rows
    assert overlap > 1000
    assert ct.first is not None and ib.first is not None
    assert ct.last is not None and ib.last is not None
    lo = max(ct.first, ib.first)
    hi = min(ct.last, ib.last)
    assert lo < hi
    print(
        f"ctrader|m1_rows:{ct.rows},m15_complete:{ct.m15.complete},"
        f"m15_incomplete:{ct.m15.incomplete},volume_zero:{ct.zero_volume},"
        f"first:{ct.first.isoformat()},last:{ct.last.isoformat()}"
    )
    print(
        f"ib|m1_rows:{ib.rows},m15_complete:{ib.m15.complete},"
        f"m15_incomplete:{ib.m15.incomplete},volume_zero:{ib.zero_volume},"
        f"first:{ib.first.isoformat()},last:{ib.last.isoformat()}"
    )
    print(f"common_time_window={lo.isoformat()}..{hi.isoformat()}")
    ct_inside = sum(lo <= t <= hi for t in ct_only)
    ib_inside = sum(lo <= t <= hi for t in ib_only)
    print(
        f"m1_overlap|both:{overlap},"
        f"ctrader_only_in_common_window:{ct_inside},"
        f"ib_only_in_common_window:{ib_inside}"
    )
    print(
        f"m1_outside_common_window|ctrader:{len(ct_only) - ct_inside},"
        f"ib:{len(ib_only) - ib_inside}"
    )
    print("m1_first_matched_close_deltas=" + ";".join(early_pairs))
    _describe("m1_close", m1_close, m1_exact)

    cts = {t for t in ct.m15.bars if lo <= t <= hi}
    ibs = {t for t in ib.m15.bars if lo <= t <= hi}
    common = sorted(cts & ibs)
    assert common, "NO_COMMON_COMPLETE_M15"
    print(
        f"m15_coverage|ctrader_complete_in_window:{len(cts)},"
        f"ib_complete_in_window:{len(ibs)},"
        f"both_complete:{len(common)},ctrader_only:{len(cts - ibs)},"
        f"ib_only:{len(ibs - cts)}"
    )
    print("m15_first_missing_ctrader=" + str(sorted(ibs - cts)[:3]))
    print("m15_first_missing_ib=" + str(sorted(cts - ibs)[:3]))
    for field in ("open", "high", "low", "close"):
        ds = [
            (getattr(ib.m15.bars[t], field) - getattr(ct.m15.bars[t], field)) / PIP
            for t in common
        ]
        exact = sum(abs(x) < 1e-9 for x in ds)
        _describe("m15_" + field, ds, exact)
    print(
        f"m15_timing|first:{common[0].isoformat()},"
        f"last:{common[-1].isoformat()},"
        "completed_at=BAR_START_PLUS_15_MIN"
    )
    print("macd_signal_parity=NOT_TESTED_DIFFERENT_PROFILE_WARMUP_POSSIBLE")
    print("live_2026_10_26_27=NOT_COVERED_BY_2025_HISTORY")
    print("market_calendar_completeness=NOT_ASSERTED")
    print("historical_broker_download=NOT_REQUESTED")
    print("source_history_modified=False")
    print("production_logic_changed=False")
    print("exit_logic_changed=False")
    print("md7_changed=False")
    print("broker_requests=0")
    print("T112_29_IB_CTRADER_EURUSD_2025_HISTORY_PARITY=OK")


if __name__ == "__main__":
    main()
