# -*- coding: utf-8 -*-
"""RoadMap115 / T115-51: completed H1 pre-entry rank audit.

TEST_ONLY / DATA_ONLY.

Досліджується остання завершена H1 перед entry_at.
Жодна H1, яка закривається після входу, не використовується.

Ознаки:
- напрямлене тіло H1;
- діапазон H1;
- напрямлене положення close у діапазоні.

Майбутні BE-activation і фінальний PnL використовуються
лише як outcome labels із незмінного T115-47.

Рангову методику беремо з перевіреного T115-50.
Немає нового gate, порогів, параметрів або Replay-змін.
Production та MD7 не змінюються.
"""

from __future__ import annotations

import bisect
import hashlib
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if TYPE_CHECKING:
    from T115_01_Alligator_Entry_Only_Events import Bar
    from T115_47_Pre_Entry_Non_BE_Loss_Anatomy import Record

t41 = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

t47 = import_module("T115_47_Pre_Entry_Non_BE_Loss_Anatomy")

t50 = import_module("T115_50_M15_Pre_Entry_Rank_Separation_Audit")

BUY = t47.BUY
SELL = t47.SELL
EPS = t47.EPS
PIP = t41.PIP
EXPECTED = t47.EXPECTED

H1 = timedelta(hours=1)

PERIODS = (
    "2024_NOV_DEC",
    "2025",
    "2026_TO_2026_08_25",
    "2026_AUG_OCT",
)

FEATURES = (
    "directional_body",
    "range_pips",
    "directional_close_location",
)

FRESH = "FRESH_COMPLETED_H1"
STALE = "STALE_PREVIOUS_H1"
MISSING = "NO_PREVIOUS_H1"

collect_records = getattr(t47, "_collect")
rank_auc = getattr(t50, "_auc")

Key = tuple[str, datetime, str]


@dataclass(frozen=True, slots=True)
class H1Features:
    """Причинні ознаки останньої завершеної H1."""

    directional_body: float
    range_pips: float
    directional_close_location: float | None


def _sha(path: Path) -> str:
    """Обчислити SHA256 контрольного файлу."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _key(row: Record) -> Key:
    """Стабільний ідентифікатор baseline-угоди."""
    return (
        row.period,
        row.entry_at,
        row.direction,
    )


def _features(
    bar: Bar,
    direction: str,
) -> H1Features:
    """Визначити безпорогові спрямований H1-ознаки."""
    assert all(
        math.isfinite(value) and value > 0
        for value in (
            bar.open,
            bar.high,
            bar.low,
            bar.close,
        )
    )

    assert bar.low <= min(bar.open, bar.close)
    assert max(bar.open, bar.close) <= bar.high

    if direction == BUY:
        sign = 1
    else:
        assert direction == SELL
        sign = -1

    body = sign * (bar.close - bar.open) / PIP
    range_pips = (bar.high - bar.low) / PIP

    if range_pips <= EPS:
        location = None
    elif direction == BUY:
        location = (bar.close - bar.low) / (bar.high - bar.low)
    else:
        location = (bar.high - bar.close) / (bar.high - bar.low)

    assert math.isfinite(body)
    assert math.isfinite(range_pips)

    if location is not None:
        assert -EPS <= location <= 1.0 + EPS

    return H1Features(
        directional_body=body,
        range_pips=range_pips,
        directional_close_location=location,
    )


def _at_entry(
    entry_at: datetime,
    direction: str,
    bars: list[Bar],
    close_times: list[datetime],
) -> tuple[H1Features | None, str]:
    """Брати тільки H1-close, відомий до входу."""
    assert len(bars) == len(close_times)

    index = (
        bisect.bisect_right(
            close_times,
            entry_at,
        )
        - 1
    )

    if index < 0:
        return None, MISSING

    completed_at = close_times[index]

    assert completed_at <= entry_at
    assert bars[index].timestamp + H1 == completed_at

    age = entry_at - completed_at

    assert age >= timedelta(0)

    # Не підміняємо актуальний стан давньою H1.
    if age >= H1:
        return None, STALE

    result = _features(
        bars[index],
        direction,
    )

    return result, FRESH


def _synthetic() -> None:
    """Перевірити completed H1, майбутнє та прогалини."""
    make_bar = t41.make_bar

    entry = datetime(2025, 4, 7, 12, tzinfo=UTC)

    prior = make_bar(
        entry - H1,
        1.1000,
        1.1020,
        1.0990,
        1.1010,
    )

    future = make_bar(
        entry,
        1.1010,
        1.3000,
        1.0100,
        1.2500,
    )

    bars = [prior, future]

    ends = [bar.timestamp + H1 for bar in bars]

    buy, status = _at_entry(
        entry,
        BUY,
        bars,
        ends,
    )

    assert status == FRESH
    assert buy is not None

    assert math.isclose(
        buy.directional_body,
        10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        buy.range_pips,
        30.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        buy.directional_close_location,
        2.0 / 3.0,
        abs_tol=EPS,
    )

    sell, status = _at_entry(
        entry,
        SELL,
        bars,
        ends,
    )

    assert status == FRESH
    assert sell is not None

    assert math.isclose(
        sell.directional_body,
        -10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        sell.directional_close_location,
        1.0 / 3.0,
        abs_tol=EPS,
    )

    # Майбутня H1 не впливає на pre-entry-ознаку.
    changed = [
        prior,
        make_bar(
            entry,
            1.1010,
            1.5000,
            1.0010,
            1.4000,
        ),
    ]

    changed_result, changed_status = _at_entry(
        entry,
        BUY,
        changed,
        ends,
    )

    assert changed_status == FRESH
    assert changed_result == buy

    # Для входу всередині H1 попередня H1 незмінна.
    inside, status = _at_entry(
        entry + timedelta(minutes=30),
        BUY,
        bars,
        ends,
    )

    assert status == FRESH
    assert inside == buy

    # Після довгої прогалини стару H1 не використовуємо.
    stale, status = _at_entry(
        entry + 2 * H1,
        BUY,
        [prior],
        [entry],
    )

    assert stale is None
    assert status == STALE

    missing, status = _at_entry(
        entry - H1,
        BUY,
        [prior],
        [entry],
    )

    assert missing is None
    assert status == MISSING

    print("SYNTHETIC_COMPLETED_H1_ONLY=OK")
    print("SYNTHETIC_FUTURE_H1_ISOLATION=OK")
    print("SYNTHETIC_BUY_SELL_DIRECTION=OK")
    print("SYNTHETIC_INTRAHOUR_ENTRY_BOUNDARY=OK")
    print("SYNTHETIC_STALE_H1_NOT_IMPUTED=OK")


def _collect_features(
    by_period: dict[str, list[Record]],
    history: dict[str, list[Bar]],
) -> tuple[
    dict[Key, H1Features | None],
    dict[Key, str],
]:
    """Зіставити угоди з їхньою останньою завершеною H1."""
    values: dict[Key, H1Features | None] = {}
    statuses: dict[Key, str] = {}

    for period in PERIODS:
        bars = history[period]

        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        ends = [timestamp + H1 for timestamp in times]

        period_counts = {
            FRESH: 0,
            STALE: 0,
            MISSING: 0,
        }

        for row in by_period[period]:
            key = _key(row)

            assert key not in values

            feature, status = _at_entry(
                row.entry_at,
                row.direction,
                bars,
                ends,
            )

            values[key] = feature
            statuses[key] = status

            period_counts[status] += 1

        total = len(by_period[period])

        assert sum(period_counts.values()) == total

        print(
            f"H1_PRE_ENTRY_COVERAGE|PERIOD={period}|"
            f"TRADES={total}|"
            f"FRESH={period_counts[FRESH]}|"
            f"STALE={period_counts[STALE]}|"
            f"MISSING={period_counts[MISSING]}|"
            "FORWARD_FILL=False"
        )

    return values, statuses


def _fmt(value: float | None) -> str:
    """Форматування метрики або NA."""
    if value is None:
        return "NA"

    return f"{value:+.4f}"


def _median(values: list[float]) -> float | None:
    """Медіана лише наявних значень."""
    if not values:
        return None

    return float(statistics.median(values))


def _describe(
    period: str,
    side: str,
    records: list[Record],
    values: dict[Key, H1Features | None],
) -> dict[str, float | None]:
    """Порівняти цільову групу з рештою за H1-рангом."""
    loss_rows = [row for row in records if row.cohort == "NO_BE_LOSS"]

    other_rows = [row for row in records if row.cohort != "NO_BE_LOSS"]

    assert len(loss_rows) + len(other_rows) == len(records)

    print(
        f"H1_RANK_BASE|PERIOD={period}|SIDE={side}|"
        f"TOTAL={len(records)}|"
        f"NO_BE_LOSS={len(loss_rows)}|"
        f"OTHER={len(other_rows)}|"
        f"BASE_NET040={math.fsum(
            row.net for row in records
        ):+.2f}"
    )

    result: dict[str, float | None] = {}

    for name in FEATURES:
        loss_values: list[float] = []
        other_values: list[float] = []

        for row in loss_rows:
            feature = values[_key(row)]

            if feature is None:
                continue

            value = getattr(feature, name)

            if value is not None:
                loss_values.append(float(value))

        for row in other_rows:
            feature = values[_key(row)]

            if feature is None:
                continue

            value = getattr(feature, name)

            if value is not None:
                other_values.append(float(value))

        auc = rank_auc(
            loss_values,
            other_values,
        )

        result[name] = auc

        cliff = 2.0 * auc - 1.0 if auc is not None else None

        print(
            f"H1_RANK_FEATURE|PERIOD={period}|"
            f"SIDE={side}|FEATURE={name}|"
            f"LOSS_N={len(loss_values)}|"
            f"OTHER_N={len(other_values)}|"
            f"LOSS_MISSING={len(loss_rows) - len(loss_values)}|"
            f"OTHER_MISSING={len(other_rows) - len(other_values)}|"
            f"LOSS_MEDIAN={_fmt(_median(loss_values))}|"
            f"OTHER_MEDIAN={_fmt(_median(other_values))}|"
            f"AUC_LOSS_HIGH={_fmt(auc)}|"
            f"CLIFF_DELTA={_fmt(cliff)}"
        )

    print(f"H1_RANK_RECONCILIATION={period}:{side}:OK")

    return result


def _report(
    by_period: dict[str, list[Record]],
    values: dict[Key, H1Features | None],
    statuses: dict[Key, str],
) -> None:
    """Перевірити baseline, H1-охоплення і рангові метрики."""
    pooled: list[Record] = []

    directions: dict[str, dict[str, list[float | None]]] = {
        BUY: {name: [] for name in FEATURES},
        SELL: {name: [] for name in FEATURES},
    }

    for period in PERIODS:
        rows = by_period[period]

        expected_count, expected_net, _, _ = EXPECTED[period]

        assert len(rows) == expected_count

        actual_net = math.fsum(row.net for row in rows)

        assert math.isclose(
            actual_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={period}:OK|"
            f"CLOSED={len(rows)}|"
            f"NET040={actual_net:+.2f}"
        )

        for side in (BUY, SELL):
            selected = [row for row in rows if row.direction == side]

            metrics = _describe(
                period,
                side,
                selected,
                values,
            )

            for name in FEATURES:
                directions[side][name].append(metrics[name])

        pooled.extend(rows)

        print(f"PERIOD_H1_RANK_RECONCILIATION={period}:OK")

    assert len(pooled) == 333
    assert len(values) == 333
    assert len(statuses) == 333

    assert sum(row.cohort == "NO_BE_LOSS" for row in pooled) == 83

    assert sum(row.cohort != "NO_BE_LOSS" for row in pooled) == 250

    for side in (BUY, SELL):
        selected = [row for row in pooled if row.direction == side]

        _describe(
            "POOLED",
            side,
            selected,
            values,
        )

    _describe(
        "POOLED",
        "ALL",
        pooled,
        values,
    )

    for side in (BUY, SELL):
        for name in FEATURES:
            observed = [auc for auc in directions[side][name] if auc is not None]

            higher = sum(auc > 0.5 for auc in observed)

            lower = sum(auc < 0.5 for auc in observed)

            equal = sum(math.isclose(auc, 0.5, abs_tol=1e-12) for auc in observed)

            print(
                f"H1_CROSS_PERIOD_DIRECTION|"
                f"SIDE={side}|FEATURE={name}|"
                f"AVAILABLE={len(observed)}|"
                f"AUC_ABOVE_050={higher}|"
                f"AUC_BELOW_050={lower}|"
                f"AUC_EQUAL_050={equal}"
            )

    print("FROZEN_T115_47_OUTCOMES_MIRROR=OK")
    print("LAST_COMPLETED_H1_ONLY=True")
    print("STALE_H1_NOT_IMPUTED=True")
    print("FOUR_PERIOD_H1_RANK_ANATOMY=OK")
    print("RANK_METRIC_FOR_RESEARCH_ONLY=True")
    print("NO_ENTRY_GATE_CREATED=True")
    print("NO_PARAMETER_OPTIMIZATION=True")


def main() -> None:
    """Виконати H1-аудит без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_47_Pre_Entry_Non_BE_Loss_Anatomy.py",
        ROOT / "tests/roadmap115/" "T115_50_M15_Pre_Entry_Rank_Separation_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-51|TEST_ONLY|" "COMPLETED_H1_PRE_ENTRY_RANK_AUDIT")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("ENTRY_FEATURE=LAST_COMPLETED_H1")
    print("OUTCOME_LABEL=FROZEN_T115_47_NO_BE_LOSS")
    print("RANK_METHOD=FROZEN_T115_50_AUC")
    print("NO_GATE_SEARCH=True|NO_REPLAY_CHANGE=True")

    _synthetic()

    windows = t47.load_windows()
    history = t47.load_history()

    assert len(windows) == 4
    assert len(history) == 4

    by_period: dict[str, list[Record]] = {}

    for window in windows:
        assert window.name not in by_period

        rows = collect_records(
            window,
            history[window.name],
        )

        by_period[window.name] = rows

    assert set(by_period) == set(PERIODS)

    values, statuses = _collect_features(
        by_period,
        history,
    )

    _report(
        by_period,
        values,
        statuses,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|" "trade_decisions_look_ahead=False")
    print("future_outcome_labels_for_research_only=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_51_COMPLETED_H1_PRE_ENTRY_RANK_AUDIT=OK")


if __name__ == "__main__":
    main()
