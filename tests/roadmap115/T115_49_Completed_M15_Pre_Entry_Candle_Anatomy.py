# -*- coding: utf-8 -*-
"""RoadMap115 / T115-49: completed M15 pre-entry anatomy.

TEST_ONLY / DATA_ONLY.

Досліджується рівно одна M15, завершена до entry_at:
[entry_at - 15 хвилин, entry_at).

M15 складається тільки з фактичних M1. Якщо хоча б
одна хвилина відсутня, ознаки позначаються UNKNOWN.

Ознаки:
- тіло M15 у напрямку майбутньої угоди, у пунктах;
- повний діапазон M15, у пунктах;
- положення close у напрямку угоди, від 0 до 1.

BE activation і фінальний PnL — лише outcome labels.
Немає нових порогів, фільтрів, entry чи exit.

Production і MD7 не змінюються.
"""

from __future__ import annotations

import csv
import hashlib
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_47_Pre_Entry_Non_BE_Loss_Anatomy import Record

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

t42 = import_module("T115_42_M1_Break_Even_First_Breach_Audit")

t36 = import_module("T115_36_First_H1_Negative_Early_Exit_Counterfactual")

BUY = t47.BUY
SELL = t47.SELL

PIP = 0.0001
EPS = t47.EPS

MINUTE = timedelta(minutes=1)
LOOKBACK = 15

SOURCE_FILES = t42.SOURCE_FILES
M1_DIRECTORY = t42.M1_DIRECTORY
M1_HEADER = t42.M1_HEADER

EXPECTED = t47.EXPECTED

COHORTS = (
    "NO_BE_LOSS",
    "NO_BE_NONLOSS",
    "BE_ACTIVATED_LOSS",
    "BE_ACTIVATED_NONLOSS",
)

parse_timestamp = getattr(t36, "_timestamp")
collect_records = getattr(t47, "_collect")

Key = tuple[str, datetime, str]
OHLC = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Features:
    """Ознаки останньої повної M15 до відкриття позиції."""

    directional_body: float
    range_pips: float
    directional_close_location: float | None


def _sha(path: Path) -> str:
    """Обчислити SHA256 без зміни файлу."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _key(row: Record) -> Key:
    """Ідентифікатор угоди без використання її результату."""
    return row.period, row.entry_at, row.direction


def _minutes(entry_at: datetime) -> list[datetime]:
    """Хвилини попередньої завершеної M15."""
    assert entry_at.second == 0
    assert entry_at.microsecond == 0
    assert entry_at.minute % 15 == 0

    return [entry_at - (LOOKBACK - index) * MINUTE for index in range(LOOKBACK)]


def _features(
    values: list[OHLC],
    direction: str,
) -> Features:
    """Визначити безпорогові M15-ознаки."""
    assert len(values) == LOOKBACK

    opening = values[0][0]
    closing = values[-1][3]

    maximum = max(bar[1] for bar in values)
    minimum = min(bar[2] for bar in values)

    assert maximum >= minimum

    if direction == BUY:
        sign = 1
    else:
        assert direction == SELL
        sign = -1

    body = sign * (closing - opening) / PIP
    span = (maximum - minimum) / PIP

    if span <= EPS:
        location = None
    elif direction == BUY:
        location = (closing - minimum) / (maximum - minimum)
    else:
        location = (maximum - closing) / (maximum - minimum)

    if location is not None:
        assert -EPS <= location <= 1 + EPS

    assert math.isfinite(body)
    assert math.isfinite(span)

    return Features(
        directional_body=body,
        range_pips=span,
        directional_close_location=location,
    )


def _synthetic() -> None:
    """Контроль BUY/SELL, діапазону та часової межі."""
    at = datetime.fromisoformat("2025-04-07T12:00:00+00:00")

    times = _minutes(at)

    assert len(times) == 15
    assert times[0] == at - timedelta(minutes=15)
    assert times[-1] == at - MINUTE
    assert at not in times

    candles: list[OHLC] = [(1.1000, 1.1015, 1.0995, 1.1010) for _ in range(LOOKBACK)]

    buy = _features(candles, BUY)
    sell = _features(candles, SELL)

    assert math.isclose(
        buy.directional_body,
        10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        sell.directional_body,
        -10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        buy.range_pips,
        20.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        buy.directional_close_location,
        0.75,
        abs_tol=EPS,
    )

    assert math.isclose(
        sell.directional_close_location,
        0.25,
        abs_tol=EPS,
    )

    print("SYNTHETIC_COMPLETED_M15_BOUNDARY=OK")
    print("SYNTHETIC_BUY_SELL_DIRECTIONAL_BODY=OK")
    print("SYNTHETIC_M15_RANGE_AND_CLOSE_LOCATION=OK")


def _load_m15_features(
    records: list[Record],
) -> dict[Key, Features | None]:
    """Прочитати M1 один раз для кожного джерела."""
    requested: dict[str, dict[datetime, list[Key]]] = {}

    observed: dict[Key, dict[datetime, OHLC]] = {}

    for row in records:
        key = _key(row)

        assert key not in observed
        observed[key] = {}

        filename = SOURCE_FILES[row.period]

        source_requests = requested.setdefault(
            filename,
            {},
        )

        for minute_at in _minutes(row.entry_at):
            source_requests.setdefault(
                minute_at,
                [],
            ).append(key)

    for filename, source_requests in requested.items():
        path = M1_DIRECTORY / filename

        assert path.is_file()

        source_rows = 0
        matched_minutes = 0
        previous_at: datetime | None = None

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            reader = csv.reader(stream)

            assert tuple(next(reader)) == M1_HEADER

            for cells in reader:
                assert len(cells) == len(M1_HEADER)

                at = parse_timestamp(cells[0])
                source_rows += 1

                if previous_at is not None:
                    assert previous_at < at

                previous_at = at

                matching = source_requests.get(at)

                if matching is None:
                    continue

                opening = float(cells[1])
                high = float(cells[2])
                low = float(cells[3])
                closing = float(cells[4])

                assert all(
                    math.isfinite(value) and value > 0
                    for value in (opening, high, low, closing)
                )

                assert low <= min(opening, closing)
                assert max(opening, closing) <= high

                bar: OHLC = (opening, high, low, closing)

                matched_minutes += 1

                for key in matching:
                    assert at not in observed[key]
                    observed[key][at] = bar

        print(
            f"M15_M1_SOURCE|FILE={filename}|"
            f"SOURCE_ROWS={source_rows}|"
            f"REQUESTED_MINUTES={len(source_requests)}|"
            f"MATCHED_MINUTES={matched_minutes}|"
            "FORWARD_FILL=False"
        )

    output: dict[Key, Features | None] = {}

    complete = 0
    incomplete = 0

    for row in records:
        key = _key(row)
        minutes = _minutes(row.entry_at)

        samples = observed[key]

        assert len(samples) <= LOOKBACK

        if len(samples) != LOOKBACK:
            output[key] = None
            incomplete += 1
            continue

        assert set(samples) == set(minutes)

        values = [samples[minute_at] for minute_at in minutes]

        output[key] = _features(
            values,
            row.direction,
        )

        complete += 1

    assert complete + incomplete == len(records)

    print(
        f"M15_PRE_ENTRY_COVERAGE|TOTAL={len(records)}|"
        f"COMPLETE={complete}|"
        f"INCOMPLETE={incomplete}|"
        "IMPUTATION=False"
    )

    return output


def _median(values: list[float]) -> str:
    """Медіана ознаки без вигаданих значень."""
    if not values:
        return "NA"

    return f"{statistics.median(values):+.3f}"


def _describe(
    period: str,
    side: str,
    records: list[Record],
    features: dict[Key, Features | None],
) -> None:
    """Зіставити pre-entry M15 та майбутні outcomes."""
    groups = (
        *COHORTS,
        "OTHER_THAN_NO_BE_LOSS",
    )

    print(
        f"M15_ENTRY_BASE|PERIOD={period}|SIDE={side}|"
        f"TRADES={len(records)}|"
        f"BASE_NET040={math.fsum(
            row.net for row in records
        ):+.2f}"
    )

    for group in groups:
        if group == "OTHER_THAN_NO_BE_LOSS":
            selected = [row for row in records if row.cohort != "NO_BE_LOSS"]
        else:
            selected = [row for row in records if row.cohort == group]

        available = [
            features[_key(row)] for row in selected if features[_key(row)] is not None
        ]

        bodies = [item.directional_body for item in available]

        ranges = [item.range_pips for item in available]

        locations = [
            item.directional_close_location
            for item in available
            if item.directional_close_location is not None
        ]

        print(
            f"M15_ENTRY_FEATURE|PERIOD={period}|"
            f"SIDE={side}|GROUP={group}|"
            f"TOTAL={len(selected)}|"
            f"COMPLETE={len(available)}|"
            f"UNKNOWN={len(selected) - len(available)}|"
            f"MEDIAN_DIR_BODY_PIPS={_median(bodies)}|"
            f"MEDIAN_RANGE_PIPS={_median(ranges)}|"
            f"MEDIAN_DIR_CLOSE_LOCATION={_median(locations)}"
        )

    print(f"M15_ENTRY_FEATURE_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    by_period: dict[str, list[Record]],
    features: dict[Key, Features | None],
) -> None:
    """Порівняти чотири періоди та зберегти baseline."""
    pooled: list[Record] = []

    for period, records in by_period.items():
        expected_count, expected_net, _, _ = EXPECTED[period]

        assert len(records) == expected_count

        actual_net = math.fsum(row.net for row in records)

        assert math.isclose(
            actual_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={period}:OK|"
            f"CLOSED={len(records)}|"
            f"NET040={actual_net:+.2f}"
        )

        for side in (BUY, SELL):
            _describe(
                period,
                side,
                [row for row in records if row.direction == side],
                features,
            )

        pooled.extend(records)

        print(f"PERIOD_M15_PRE_ENTRY_RECONCILIATION=" f"{period}:OK")

    assert len(pooled) == 333

    assert sum(row.cohort == "NO_BE_LOSS" for row in pooled) == 83

    assert sum(row.cohort == "NO_BE_NONLOSS" for row in pooled) == 12

    assert math.isclose(
        math.fsum(row.net for row in pooled if row.cohort == "NO_BE_LOSS"),
        -1947.10,
        abs_tol=EPS,
    )

    for side in (BUY, SELL):
        _describe(
            "POOLED",
            side,
            [row for row in pooled if row.direction == side],
            features,
        )

    _describe(
        "POOLED",
        "ALL",
        pooled,
        features,
    )

    print("FROZEN_T115_47_OUTCOMES_MIRROR=OK")
    print("FOUR_PERIOD_COMPLETED_M15_ANATOMY=OK")
    print("M15_PRIOR_BAR_ONLY=True")
    print("M1_MISSING_NOT_IMPUTED=True")
    print("NEW_ENTRY_THRESHOLD_CREATED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Виконати TEST_ONLY-аудит без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        ROOT / "tests/roadmap115/" "T115_48_M15_Entry_Class_Rejection_Cost_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-49|TEST_ONLY|" "COMPLETED_M15_PRE_ENTRY_CANDLE_ANATOMY")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("FEATURE_WINDOW=PRECEDING_15_COMPLETE_MINUTES")
    print("FEATURES=DIR_BODY_RANGE_CLOSE_LOCATION")
    print("NO_THRESHOLD_SEARCH=True|NO_GATE_REPLAY=True")

    _synthetic()

    windows = t47.load_windows()
    history = t47.load_history()

    assert len(windows) == 4

    by_period: dict[str, list[Record]] = {}

    for window in windows:
        records = collect_records(
            window,
            history[window.name],
        )

        by_period[window.name] = records

        assert len(records) == EXPECTED[window.name][0]
        assert window.open_end == EXPECTED[window.name][3]

    all_records = [row for records in by_period.values() for row in records]

    assert len(all_records) == 333

    features = _load_m15_features(all_records)

    _report(
        by_period,
        features,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("future_outcomes_used_for_research_only=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_49_COMPLETED_M15_PRE_ENTRY_" "CANDLE_ANATOMY=OK")


if __name__ == "__main__":
    main()
