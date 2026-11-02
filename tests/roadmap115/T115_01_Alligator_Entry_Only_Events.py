# -*- coding: utf-8 -*-
"""RoadMap115 / T115-01 — події входу лише за Alligator.

TEST_ONLY / DATA_ONLY. Це НЕ торговий Replay, не симуляція позицій,
не розрахунок прибутку й не зміна production-алгоритму.

Джерело: локальні cTrader EURUSD M1, 2025 і 2026 до 25.08.
Для 2026 діє канонічний cutoff T112-14: 2026-08-25 15:07 UTC.
M15 формується лише з 15 послідовних завершених M1. Час M15 —
початок свічки UTC, стан доступний після її закриття (timestamp + 15 хв).

Сигнал: перший завершений M15 зі зміною фази Alligator на ACTIVE
після не-ACTIVE. Напрямок визначає поточний TREND_UP/TREND_DOWN.
Профіль: штатний immutable built-in LGE Candidate F Alligator (4 bars),
але БЕЗ MACD, без його trade gates та без інших entry-фільтрів.

Наступний open — лише для підрахунку наявності сусіднього завершеного
M15 в історії, НЕ ціна входу і НЕ використовується для прийняття сигналу.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorRuntimeProfile,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_LOGIC_MODE_CANDIDATE_F,
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
)

ONE_MINUTE = timedelta(minutes=1)
M15 = timedelta(minutes=15)
CANONICAL_2026_END = datetime.fromisoformat("2026-08-25T15:07:00+00:00")
HEADER = ("timestamp", "open", "high", "low", "close", "volume")
PERIODS = (
    (
        "2025",
        "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv",
        23753, 809, 395, 414, 800,
    ),
    (
        "2026_TO_2026_08_25",
        "2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv",
        15423, 516, 233, 283, 506,
    ),
)


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


def _bucket_start(timestamp: datetime) -> datetime:
    """M15 із UTC timestamp M1 без локального часовoго поясу."""
    return timestamp.replace(minute=timestamp.minute // 15 * 15, second=0)


def _completed_bar(bucket: datetime, items: list[Bar]) -> Bar | None:
    """Не створювати M15, якщо відсутня хоч одна з 15 хвилин."""
    if len(items) != 15:
        return None
    if any(item.timestamp != bucket + i * ONE_MINUTE
           for i, item in enumerate(items)):
        return None
    return Bar(
        timestamp=bucket,
        open=items[0].open,
        high=max(item.high for item in items),
        low=min(item.low for item in items),
        close=items[-1].close,
    )


def _aggregate_m1(
    path: Path, year: int, cutoff: datetime | None
) -> tuple[int, int, list[Bar]]:
    """Інкрементальна агрегація; ні forward-fill, ні future M1."""
    assert path.is_file(), f"MISSING_HISTORY: {path}"
    rows = 0
    included_rows = 0
    previous: datetime | None = None
    bucket: datetime | None = None
    pending: list[Bar] = []
    completed: list[Bar] = []

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        assert tuple(next(reader)) == HEADER, path
        for cells in reader:
            assert len(cells) == 6, f"INVALID_CSV_ROW: {path.name}:{rows + 2}"
            timestamp = datetime.fromisoformat(cells[0].replace("Z", "+00:00"))
            assert timestamp.tzinfo is not None
            timestamp = timestamp.astimezone(UTC)
            assert timestamp.year == year, timestamp
            assert timestamp.second == timestamp.microsecond == 0
            assert previous is None or timestamp > previous, timestamp
            o, h, l, c = map(float, cells[1:5])
            assert all(math.isfinite(p) and p > 0 for p in (o, h, l, c))
            assert l <= min(o, c) <= max(o, c) <= h

            rows += 1
            previous = timestamp
            if cutoff is not None and timestamp > cutoff:
                continue
            included_rows += 1
            current_bucket = _bucket_start(timestamp)
            if bucket is not None and current_bucket != bucket:
                finished = _completed_bar(bucket, pending)
                if finished is not None:
                    completed.append(finished)
                pending = []
            bucket = current_bucket
            pending.append(Bar(timestamp, o, h, l, c))

    if bucket is not None:
        finished = _completed_bar(bucket, pending)
        if finished is not None:
            completed.append(finished)

    assert completed, f"NO_COMPLETE_M15: {path}"
    assert all(b.timestamp < next_b.timestamp
               for b, next_b in zip(completed, completed[1:]))
    return rows, included_rows, completed


def _profile() -> WorkspaceAlligatorRuntimeProfile:
    """Взяти штатні параметри з коду проєкту, а не переписати MA."""
    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
    runtime = WorkspaceAlligatorRuntimeProfile.from_binding(binding)
    assert runtime.logic_mode == ALLIGATOR_LOGIC_MODE_CANDIDATE_F
    assert runtime.effective_trend_start_confirmation_bars == 4
    assert (runtime.jaw_period, runtime.jaw_shift) == (13, 8)
    assert (runtime.teeth_period, runtime.teeth_shift) == (8, 5)
    assert (runtime.lips_period, runtime.lips_shift) == (5, 3)
    assert runtime.source == "MEDIAN_PRICE" and runtime.ma_type == "SMOOTHED"
    return runtime


def _fingerprint(path: Path) -> str | None:
    """Контроль незмінності файлів під час TEST_ONLY, якщо вони існують."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_causality_check() -> None:
    """Неповні й непослідовні M1 не можуть утворити завершений M15."""
    start = datetime(2025, 2, 3, 12, tzinfo=UTC)
    data = [Bar(start + i * ONE_MINUTE, 1.1, 1.2, 1.0, 1.15)
            for i in range(15)]
    assert _completed_bar(start, data) is not None
    assert _completed_bar(start, data[:-1]) is None
    with_gap = data.copy()
    with_gap[6] = Bar(start + 7 * ONE_MINUTE, 1.1, 1.2, 1.0, 1.15)
    assert _completed_bar(start, with_gap) is None
    print("SYNTHETIC_COMPLETED_M15_CAUSALITY=OK")


def _run_period(label: str, filename: str, expected: tuple[int, ...],
                profile: WorkspaceAlligatorRuntimeProfile) -> None:
    """Фіксувати тільки переходи не-ACTIVE → ACTIVE на закритому барі."""
    path = ROOT / "data" / "history" / "CTRADER" / "EURUSD" / "M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    m1_count, included_m1, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    signal_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=profile,
        timeframe="M15",
    )
    count = buys = sells = next_open_available = 0
    previous_phase: str | None = None
    for index, bar in enumerate(bars):
        available_at = bar.timestamp + M15
        event = WorkspaceMarketEvent(
            timestamp=bar.timestamp,
            broker="CTRADER",
            symbol="EURUSD",
            timeframe="M15",
            bid=bar.close,
            ask=bar.close,
            spread=0.0,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=0.0,
            source_mode="REPLAY",
        )
        observation = signal_filter.on_market_event(event, available_at=available_at)
        assert observation.timestamp == bar.timestamp
        assert observation.available_at == available_at
        if (
            observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
            and previous_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
        ):
            assert observation.warmed_up
            assert observation.regime in {
                ALLIGATOR_REGIME_TREND_UP,
                ALLIGATOR_REGIME_TREND_DOWN,
            }
            count += 1
            buys += observation.regime == ALLIGATOR_REGIME_TREND_UP
            sells += observation.regime == ALLIGATOR_REGIME_TREND_DOWN
            # Лише перевірка наявності; майбутнє НЕ впливає на сигнал.
            if index + 1 < len(bars) and bars[index + 1].timestamp == available_at:
                next_open_available += 1
        previous_phase = observation.regime_phase

    assert buys + sells == count
    observed = (len(bars), count, buys, sells, next_open_available)
    print(
        f"PERIOD={label}|SOURCE_M1={m1_count}|SELECTED_M1={included_m1}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}|"
        f"COMPLETED_M15={len(bars)}|"
        f"ACTIVE_TRANSITIONS={count}|BUY={buys}|SELL={sells}|"
        f"NEXT_M15_OPEN_AVAILABLE={next_open_available}"
    )
    assert observed == expected, f"{label}: OBSERVED={observed}; EXPECTED={expected}"


def main() -> None:
    """Детерміновано відтворити T115-01 без звернення до брокера."""
    guarded = (
        ROOT / "core" / "workspace_alligator.py",
        ROOT / "core" / "workspace_indicator_profile.py",
        ROOT / "doc" / "LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-01|TEST_ONLY|ALLIGATOR_ENTRY_ONLY|EURUSD_CTRADER_M15")
    _synthetic_causality_check()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|look_ahead=False|broker_requests=0")
    print("production_changed=False|md7_changed=False")
    print("T115_01_ALLIGATOR_ENTRY_ONLY_EVENTS=OK")


if __name__ == "__main__":
    main()
