# -*- coding: utf-8 -*-
"""RoadMap115 / T115-38: H1 gap coverage and selection bias.

TEST_ONLY / DATA_ONLY.

Ті самі чотири вікна та baseline-угоди T115-32.
Аудит виключень із T115-37 через несуцільні H1.

Відсутні H1 позначаються за календарем UTC.
Saturday/Sunday не означає доведений market-close.
Weekday не означає доведений збій постачальника даних.

Ціни в прогалинах не відновлюються.
Нових entry/exit, SL/TP і оптимізації немає.
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
    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window

entry_mod = import_module("T115_01_Alligator_Entry_Only_Events")

exit_mod = import_module("T115_02_Alligator_Exit_Only_Trades")

audit_mod = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

loss_mod = import_module("T115_33_H1_Large_Loss_Anatomy")

peak_mod = import_module("T115_37_H1_Completed_Close_Giveback_Anatomy")

make_bar = entry_mod.Bar
make_trade = exit_mod.ClosedTrade

BUY = exit_mod.DIRECTION_UP
SELL = exit_mod.DIRECTION_DOWN

COST = loss_mod.COST
EPS = 1e-6
H1 = timedelta(hours=1)

EXPECTED = audit_mod.EXPECTED

# Очікувана кількість включень із локального PASS T115-37.
EXPECTED_COVERAGE = {
    "2024_NOV_DEC": {
        BUY: (8, 6),
        SELL: (10, 2),
    },
    "2025": {
        BUY: (31, 53),
        SELL: (61, 22),
    },
    "2026_TO_2026_08_25": {
        BUY: (32, 27),
        SELL: (44, 11),
    },
    "2026_AUG_OCT": {
        BUY: (4, 5),
        SELL: (13, 4),
    },
}

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(loss_mod, "_history")
strict_close_peak = getattr(peak_mod, "_measure")


@dataclass(frozen=True, slots=True)
class GapInfo:
    """Фактична повнота H1 протягом завершеної позиції."""

    expected_h1: int
    observed_h1: int
    missing_h1: int
    weekend_missing: int
    weekday_missing: int
    gap_runs: int


@dataclass(frozen=True, slots=True)
class Record:
    """Baseline-угода з діагностикою відсутніх H1."""

    trade: ClosedTrade
    gap: GapInfo

    @property
    def net(self) -> float:
        return float(self.trade.pips) - COST

    @property
    def included(self) -> bool:
        return self.gap.missing_h1 == 0


def _sha(path: Path) -> str:
    """Контроль незмінності файлів SHA256."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _gaps(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
) -> GapInfo:
    """Порахувати відсутні H1 без відновлення їхнього вмісту."""
    assert len(bars) == len(times)
    assert trade.entry_at < trade.exit_at

    left = bisect.bisect_left(
        times,
        trade.entry_at,
    )

    right = bisect.bisect_left(
        times,
        trade.exit_at,
    )

    assert left < right < len(times)
    assert times[left] == trade.entry_at
    assert times[right] == trade.exit_at

    duration = trade.exit_at - trade.entry_at

    expected_h1 = int(duration.total_seconds() // 3600)

    assert expected_h1 > 0
    assert duration == expected_h1 * H1

    observed = bars[left:right]

    assert len(observed) == trade.holding_bars
    assert len(observed) <= expected_h1

    observed_times = {bar.timestamp for bar in observed}

    assert len(observed_times) == len(observed)

    weekend_missing = 0
    weekday_missing = 0
    gap_runs = 0

    previous_missing = False

    for index in range(expected_h1):
        at = trade.entry_at + index * H1

        missing = at not in observed_times

        if missing:
            if not previous_missing:
                gap_runs += 1

            if at.weekday() >= 5:
                weekend_missing += 1
            else:
                weekday_missing += 1

        previous_missing = missing

    missing_h1 = expected_h1 - len(observed)

    assert missing_h1 >= 0

    assert weekend_missing + weekday_missing == missing_h1

    assert gap_runs == 0 if missing_h1 == 0 else gap_runs > 0

    return GapInfo(
        expected_h1=expected_h1,
        observed_h1=len(observed),
        missing_h1=missing_h1,
        weekend_missing=weekend_missing,
        weekday_missing=weekday_missing,
        gap_runs=gap_runs,
    )


def _synthetic() -> None:
    """Перевірити послідовні H1 і вихідні UTC."""
    friday = datetime(2026, 10, 23, 21, tzinfo=UTC)

    monday = datetime(2026, 10, 26, 0, tzinfo=UTC)

    bars = [
        make_bar(
            friday,
            1.1000,
            1.1015,
            1.0990,
            1.1010,
        ),
        make_bar(
            monday,
            1.1010,
            1.1020,
            1.1000,
            1.1015,
        ),
        make_bar(
            monday + H1,
            1.1015,
            1.1020,
            1.1005,
            1.1010,
        ),
        make_bar(
            monday + 2 * H1,
            1.1010,
            1.1030,
            1.1000,
            1.1020,
        ),
    ]

    times = [bar.timestamp for bar in bars]

    trade = make_trade(
        direction=BUY,
        entry_at=friday,
        exit_at=monday + 2 * H1,
        entry_price=1.1000,
        exit_price=1.1010,
        pips=10.0,
        holding_bars=3,
        holding_minutes=3180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    result = _gaps(
        trade,
        bars,
        times,
    )

    assert result.expected_h1 == 53
    assert result.observed_h1 == 3
    assert result.missing_h1 == 50

    assert result.weekend_missing == 48
    assert result.weekday_missing == 2
    assert result.gap_runs == 1

    assert (
        strict_close_peak(
            trade,
            bars,
            times,
        )
        is None
    )

    contiguous_bars = [
        make_bar(
            friday,
            1.1000,
            1.1015,
            1.0990,
            1.1010,
        ),
        make_bar(
            friday + H1,
            1.1010,
            1.1020,
            1.1000,
            1.1015,
        ),
        make_bar(
            friday + 2 * H1,
            1.1015,
            1.1020,
            1.1005,
            1.1010,
        ),
        make_bar(
            friday + 3 * H1,
            1.1010,
            1.1030,
            1.1000,
            1.1020,
        ),
    ]

    contiguous_times = [bar.timestamp for bar in contiguous_bars]

    contiguous_trade = make_trade(
        direction=BUY,
        entry_at=friday,
        exit_at=friday + 3 * H1,
        entry_price=1.1000,
        exit_price=1.1010,
        pips=10.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    complete = _gaps(
        contiguous_trade,
        contiguous_bars,
        contiguous_times,
    )

    assert complete.expected_h1 == 3
    assert complete.observed_h1 == 3
    assert complete.missing_h1 == 0
    assert complete.gap_runs == 0

    assert (
        strict_close_peak(
            contiguous_trade,
            contiguous_bars,
            contiguous_times,
        )
        is not None
    )

    # Додавання майбутнього бару не змінює діагностику.
    extended = [
        *contiguous_bars,
        make_bar(
            friday + 4 * H1,
            1.1020,
            1.3000,
            1.0100,
            1.2500,
        ),
    ]

    extended_times = [bar.timestamp for bar in extended]

    assert complete == _gaps(
        contiguous_trade,
        extended,
        extended_times,
    )

    print("SYNTHETIC_WEEKEND_WEEKDAY_GAP_COUNTS=OK")
    print("SYNTHETIC_CONTIGUOUS_H1_CLASSIFICATION=OK")
    print("SYNTHETIC_T115_37_COVERAGE_MIRROR=OK")
    print("SYNTHETIC_FUTURE_BAR_ISOLATION=OK")


def _fmt(value: float | None) -> str:
    """Форматувати числові оцінки або NA."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _summary(
    period: str,
    side: str,
    rows: list[Record],
) -> None:
    """Порівняти включену й виключену частини baseline."""
    included = [row for row in rows if row.included]

    excluded = [row for row in rows if not row.included]

    assert len(included) + len(excluded) == len(rows)

    included_losses = sum(row.net < -EPS for row in included)

    excluded_losses = sum(row.net < -EPS for row in excluded)

    included_nonloss = len(included) - included_losses
    excluded_nonloss = len(excluded) - excluded_losses

    included_net = math.fsum(row.net for row in included)

    excluded_net = math.fsum(row.net for row in excluded)

    total_net = math.fsum(row.net for row in rows)

    assert math.isclose(
        included_net + excluded_net,
        total_net,
        abs_tol=EPS,
    )

    excluded_pct = 100 * len(excluded) / len(rows) if rows else None

    included_loss_rate = 100 * included_losses / len(included) if included else None

    excluded_loss_rate = 100 * excluded_losses / len(excluded) if excluded else None

    median_included_hours = (
        statistics.median([row.gap.expected_h1 for row in included])
        if included
        else None
    )

    median_excluded_hours = (
        statistics.median([row.gap.expected_h1 for row in excluded])
        if excluded
        else None
    )

    print(
        f"GAP_COVERAGE|PERIOD={period}|"
        f"SIDE={side}|TOTAL={len(rows)}|"
        f"INCLUDED={len(included)}|"
        f"EXCLUDED={len(excluded)}|"
        f"EXCLUDED_PCT={_fmt(excluded_pct)}|"
        f"INCLUDED_LOSS={included_losses}|"
        f"EXCLUDED_LOSS={excluded_losses}|"
        f"INCLUDED_NONLOSS={included_nonloss}|"
        f"EXCLUDED_NONLOSS={excluded_nonloss}"
    )

    print(
        f"GAP_NET|PERIOD={period}|SIDE={side}|"
        f"INCLUDED_NET040={included_net:+.2f}|"
        f"EXCLUDED_NET040={excluded_net:+.2f}|"
        f"TOTAL_NET040={total_net:+.2f}"
    )

    print(
        f"GAP_SELECTION|PERIOD={period}|SIDE={side}|"
        f"INCLUDED_LOSS_RATE={_fmt(included_loss_rate)}|"
        f"EXCLUDED_LOSS_RATE={_fmt(excluded_loss_rate)}|"
        f"INCLUDED_MEDIAN_HOURS="
        f"{_fmt(median_included_hours)}|"
        f"EXCLUDED_MEDIAN_HOURS="
        f"{_fmt(median_excluded_hours)}"
    )

    missing = sum(row.gap.missing_h1 for row in excluded)

    weekend = sum(row.gap.weekend_missing for row in excluded)

    weekday = sum(row.gap.weekday_missing for row in excluded)

    runs = sum(row.gap.gap_runs for row in excluded)

    assert missing == weekend + weekday

    print(
        f"GAP_CALENDAR|PERIOD={period}|SIDE={side}|"
        f"MISSING_H1={missing}|"
        f"WEEKEND_UTC={weekend}|"
        f"WEEKDAY_UTC={weekday}|"
        f"GAP_RUNS={runs}|"
        "MISSING_PRICE_IMPUTED=False"
    )

    worst_excluded = sorted(
        [row for row in excluded if row.net < -EPS],
        key=lambda row: (
            row.net,
            row.trade.entry_at,
        ),
    )[:3]

    for rank, row in enumerate(
        worst_excluded,
        start=1,
    ):
        print(
            f"EXCLUDED_LOSS|PERIOD={period}|"
            f"SIDE={side}|RANK={rank}|"
            f"ENTRY={row.trade.entry_at.isoformat()}|"
            f"NET040={row.net:+.2f}|"
            f"MISSING_H1={row.gap.missing_h1}|"
            f"WEEKEND={row.gap.weekend_missing}|"
            f"WEEKDAY={row.gap.weekday_missing}|"
            f"GAP_RUNS={row.gap.gap_runs}"
        )

    print(f"GAP_PARTITION_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Підтвердити пропуски T115-37 на тих самих угодах."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: dict[str, list[Record]] = {
        BUY: [],
        SELL: [],
    }

    total_rows = 0

    for window in windows:
        bars = history[window.name]

        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(window.entries) == count
        assert window.open_end == open_end

        period_net = math.fsum(float(item.trade.pips) - COST for item in window.entries)

        assert math.isclose(
            period_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={count}|"
            f"NET040={period_net:+.2f}"
        )

        for side in (BUY, SELL):
            rows: list[Record] = []

            for item in window.entries:
                trade = item.trade

                if trade.direction != side:
                    continue

                info = _gaps(
                    trade,
                    bars,
                    times,
                )

                # Дзеркальна перевірка включень T115-37.
                original_peak = strict_close_peak(
                    trade,
                    bars,
                    times,
                )

                if info.missing_h1 == 0:
                    assert original_peak is not None
                else:
                    assert original_peak is None

                rows.append(
                    Record(
                        trade=trade,
                        gap=info,
                    )
                )

            included = sum(row.included for row in rows)

            excluded = len(rows) - included

            assert (included, excluded) == (EXPECTED_COVERAGE[window.name][side])

            _summary(
                window.name,
                side,
                rows,
            )

            pooled[side].extend(rows)
            total_rows += len(rows)

        print(f"PERIOD_H1_GAP_RECONCILIATION=" f"{window.name}:OK")

    assert total_rows == 333

    all_rows = pooled[BUY] + pooled[SELL]

    assert sum(row.included for row in all_rows) == 203

    assert sum(not row.included for row in all_rows) == 130

    for side in (BUY, SELL):
        _summary(
            "POOLED",
            side,
            pooled[side],
        )

    _summary(
        "POOLED",
        "ALL",
        all_rows,
    )

    print("T115_37_COVERAGE_EXACT_MIRROR=OK")
    print("FOUR_PERIOD_H1_GAP_RECONCILIATION=OK")
    print("GAP_CAUSE_INFERRED=False")
    print("NONCONTIGUOUS_PEAK_RECONSTRUCTED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Виконати аудит без зміни production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_37_H1_Completed_Close_Giveback_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-38|TEST_ONLY|" "H1_GAP_COVERAGE_SELECTION_BIAS_AUDIT")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("COVERAGE_REFERENCE=T115_37|EXCLUDED=130")
    print("GAPS=UTC_CALENDAR_ONLY|NO_MARKET_CAUSE_ASSUMPTION")
    print("NO_FORWARD_FILL=True|NO_PARAMETER_SEARCH=True")

    _synthetic()

    windows = load_windows()
    history = load_history()

    _report(
        windows,
        history,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("outcome_labels_use_future=True|future_used_for_entry=False")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_38_H1_GAP_COVERAGE_SELECTION_BIAS_AUDIT=OK")


if __name__ == "__main__":
    main()
