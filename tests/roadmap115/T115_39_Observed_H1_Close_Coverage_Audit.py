# -*- coding: utf-8 -*-
"""RoadMap115 / T115-39: observed H1 close coverage audit.

TEST_ONLY / DATA_ONLY.

Чотири незмінні baseline-вікна з T115-32.
Вимірювання виконується для всіх 333 завершених угод.

Використовуються лише фактично наявні H1-close.
Відсутні H1 не відновлюються й не заповнюються.

Для угод із прогалинами observed peak є нижньою межею
невідомого повного максимуму завершених H1-close.

Історичний максимум — outcome label, не сигнал виходу.
Жодних нових entry, exit, SL/TP або оптимізації.
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

gap_mod = import_module("T115_38_H1_Gap_Coverage_Selection_Bias_Audit")

make_bar = entry_mod.Bar
make_trade = exit_mod.ClosedTrade

BUY = exit_mod.DIRECTION_UP
SELL = exit_mod.DIRECTION_DOWN

PIP = 0.0001
COST = loss_mod.COST
EPS = 1e-6
H1 = timedelta(hours=1)

EXPECTED = audit_mod.EXPECTED
EXPECTED_COVERAGE = gap_mod.EXPECTED_COVERAGE

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(loss_mod, "_history")
strict_peak = getattr(peak_mod, "_measure")
measure_gaps = getattr(gap_mod, "_gaps")


@dataclass(frozen=True, slots=True)
class ObservedPeak:
    """Найкращий close серед фактично наявних H1."""

    best_pips: float
    best_at: datetime | None
    observed_h1: int


@dataclass(frozen=True, slots=True)
class Record:
    """Baseline-угода з фактично доступним close-піком."""

    trade: ClosedTrade
    peak: ObservedPeak
    missing_h1: int

    @property
    def net(self) -> float:
        return float(self.trade.pips) - COST

    @property
    def coverage(self) -> str:
        if self.missing_h1 == 0:
            return "CONTIGUOUS"
        return "GAPPED"

    @property
    def outcome(self) -> str:
        if self.net < -EPS:
            return "LOSS"
        return "NONLOSS"


def _sha(path: Path) -> str:
    """Контроль незмінності production та MD7."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _observed_peak(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
) -> ObservedPeak:
    """Знайти максимум лише серед наявних завершених H1."""
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

    assert left < right < len(bars)
    assert times[left] == trade.entry_at
    assert times[right] == trade.exit_at

    assert math.isclose(
        bars[left].open,
        trade.entry_price,
        abs_tol=1e-9,
    )

    assert math.isclose(
        bars[right].open,
        trade.exit_price,
        abs_tol=1e-9,
    )

    observed = bars[left:right]

    assert len(observed) == trade.holding_bars

    if trade.direction == BUY:
        direction = 1
    else:
        assert trade.direction == SELL
        direction = -1

    best = 0.0
    best_at: datetime | None = None

    for bar in observed:
        completed_at = bar.timestamp + H1

        assert trade.entry_at < completed_at
        assert completed_at <= trade.exit_at

        signed = direction * (bar.close - trade.entry_price) / PIP

        assert math.isfinite(signed)

        if signed > best + EPS:
            best = signed
            best_at = completed_at

    return ObservedPeak(
        best_pips=best,
        best_at=best_at,
        observed_h1=len(observed),
    )


def _synthetic() -> None:
    """Перевірити прогалини, напрямки та майбутні дані."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    first = make_bar(
        at,
        1.1000,
        1.1030,
        1.0990,
        1.1010,
    )

    middle = make_bar(
        at + H1,
        1.1010,
        1.1050,
        1.1000,
        1.1040,
    )

    third = make_bar(
        at + 2 * H1,
        1.1005,
        1.1010,
        1.0970,
        1.0980,
    )

    exit_bar = make_bar(
        at + 3 * H1,
        1.0990,
        1.1500,
        1.0500,
        1.1200,
    )

    complete_bars = [
        first,
        middle,
        third,
        exit_bar,
    ]

    complete_times = [bar.timestamp for bar in complete_bars]

    complete_trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.0990,
        pips=-10.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    complete = _observed_peak(
        complete_trade,
        complete_bars,
        complete_times,
    )

    assert math.isclose(
        complete.best_pips,
        40.0,
        abs_tol=EPS,
    )

    assert complete.best_at == at + 2 * H1

    original = strict_peak(
        complete_trade,
        complete_bars,
        complete_times,
    )

    assert original is not None

    assert math.isclose(
        complete.best_pips,
        original.peak_pips,
        abs_tol=EPS,
    )

    assert complete.best_at == original.peak_at

    sparse_bars = [
        first,
        third,
        exit_bar,
    ]

    sparse_times = [bar.timestamp for bar in sparse_bars]

    sparse_trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.0990,
        pips=-10.0,
        holding_bars=2,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    info = measure_gaps(
        sparse_trade,
        sparse_bars,
        sparse_times,
    )

    assert info.missing_h1 == 1

    assert (
        strict_peak(
            sparse_trade,
            sparse_bars,
            sparse_times,
        )
        is None
    )

    sparse = _observed_peak(
        sparse_trade,
        sparse_bars,
        sparse_times,
    )

    assert math.isclose(
        sparse.best_pips,
        10.0,
        abs_tol=EPS,
    )

    assert sparse.best_at == at + H1

    assert sparse.best_pips <= complete.best_pips

    future_changed = [
        first,
        third,
        make_bar(
            at + 3 * H1,
            1.0990,
            1.3000,
            1.0100,
            1.2500,
        ),
    ]

    assert sparse == _observed_peak(
        sparse_trade,
        future_changed,
        sparse_times,
    )

    sell_trade = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.0990,
        pips=10.0,
        holding_bars=2,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell_peak = _observed_peak(
        sell_trade,
        sparse_bars,
        sparse_times,
    )

    assert math.isclose(
        sell_peak.best_pips,
        20.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_CONTIGUOUS_STRICT_PEAK_MIRROR=OK")
    print("SYNTHETIC_GAPPED_OBSERVED_LOWER_BOUND=OK")
    print("SYNTHETIC_NO_MISSING_PRICE_IMPUTATION=OK")
    print("SYNTHETIC_FUTURE_BAR_ISOLATION=OK")
    print("SYNTHETIC_BUY_SELL_DIRECTION=OK")


def _records(
    window: Window,
    bars: list[Bar],
) -> list[Record]:
    """Зібрати всі baseline-угоди без виключень."""
    times = [bar.timestamp for bar in bars]

    assert times == sorted(set(times))

    result: list[Record] = []

    for item in window.entries:
        trade = item.trade

        gap = measure_gaps(
            trade,
            bars,
            times,
        )

        observed = _observed_peak(
            trade,
            bars,
            times,
        )

        original = strict_peak(
            trade,
            bars,
            times,
        )

        if gap.missing_h1 == 0:
            assert original is not None

            assert math.isclose(
                observed.best_pips,
                original.peak_pips,
                abs_tol=EPS,
            )

            assert observed.best_at == original.peak_at

        else:
            assert original is None

        assert observed.observed_h1 == gap.observed_h1

        result.append(
            Record(
                trade=trade,
                peak=observed,
                missing_h1=gap.missing_h1,
            )
        )

    assert len(result) == len(window.entries)

    return result


def _fmt(value: float | None) -> str:
    """Позначити відсутню оцінку як NA."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _describe(
    period: str,
    side: str,
    rows: list[Record],
) -> None:
    """Зіставити включені й раніше виключені угоди."""
    contiguous = [row for row in rows if row.coverage == "CONTIGUOUS"]

    gapped = [row for row in rows if row.coverage == "GAPPED"]

    assert len(contiguous) + len(gapped) == len(rows)

    baseline_net = math.fsum(row.net for row in rows)

    print(
        f"OBSERVED_COVERAGE|PERIOD={period}|"
        f"SIDE={side}|TOTAL={len(rows)}|"
        f"CONTIGUOUS={len(contiguous)}|"
        f"GAPPED={len(gapped)}|"
        f"BASE_NET040={baseline_net:+.2f}"
    )

    for coverage, selected in (
        ("CONTIGUOUS", contiguous),
        ("GAPPED", gapped),
    ):
        for outcome in ("LOSS", "NONLOSS"):
            cohort = [row for row in selected if row.outcome == outcome]

            peaks = [row.peak.best_pips for row in cohort]

            positive = sum(value > EPS for value in peaks)

            above_cost = sum(value > COST + EPS for value in peaks)

            median_peak = statistics.median(peaks) if peaks else None

            cohort_net = math.fsum(row.net for row in cohort)

            print(
                f"OBSERVED_COHORT|PERIOD={period}|"
                f"SIDE={side}|COVERAGE={coverage}|"
                f"OUTCOME={outcome}|COUNT={len(cohort)}|"
                f"POSITIVE_PEAK={positive}|"
                f"PEAK_GT_COST={above_cost}|"
                f"MEDIAN_OBSERVED_PEAK={_fmt(median_peak)}|"
                f"NET040={cohort_net:+.2f}|"
                f"LOWER_BOUND_ONLY={coverage == 'GAPPED'}"
            )

    gapped_losses = [
        row
        for row in gapped
        if row.outcome == "LOSS" and row.peak.best_pips > COST + EPS
    ]

    ranked = sorted(
        gapped_losses,
        key=lambda row: (
            -(row.peak.best_pips - float(row.trade.pips)),
            row.trade.entry_at,
        ),
    )

    for rank, row in enumerate(
        ranked[:3],
        start=1,
    ):
        assert row.peak.best_at is not None

        print(
            f"GAPPED_LOSS_EXAMPLE|PERIOD={period}|"
            f"SIDE={side}|RANK={rank}|"
            f"ENTRY={row.trade.entry_at.isoformat()}|"
            f"NET040={row.net:+.2f}|"
            f"OBSERVED_PEAK={row.peak.best_pips:+.2f}|"
            f"OBSERVED_AT={row.peak.best_at.isoformat()}|"
            f"MISSING_H1={row.missing_h1}|"
            "TRUE_MAX_UNKNOWN=True"
        )

    print(f"OBSERVED_PARTITION_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Звірити всі 333 угоди з T115-37 і T115-38."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: dict[str, list[Record]] = {
        BUY: [],
        SELL: [],
    }

    for window in windows:
        rows = _records(
            window,
            history[window.name],
        )

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(rows) == expected_count
        assert window.open_end == open_end

        period_net = math.fsum(row.net for row in rows)

        assert math.isclose(
            period_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={len(rows)}|"
            f"NET040={period_net:+.2f}"
        )

        for side in (BUY, SELL):
            side_rows = [row for row in rows if row.trade.direction == side]

            included = sum(row.coverage == "CONTIGUOUS" for row in side_rows)

            excluded = len(side_rows) - included

            assert (included, excluded) == (EXPECTED_COVERAGE[window.name][side])

            _describe(
                window.name,
                side,
                side_rows,
            )

            pooled[side].extend(side_rows)

        print(f"PERIOD_OBSERVED_PEAK_RECONCILIATION=" f"{window.name}:OK")

    all_rows = pooled[BUY] + pooled[SELL]

    assert len(all_rows) == 333

    contiguous = [row for row in all_rows if row.coverage == "CONTIGUOUS"]

    gapped = [row for row in all_rows if row.coverage == "GAPPED"]

    assert len(contiguous) == 203
    assert len(gapped) == 130

    strict_loss_above_cost = sum(
        row.outcome == "LOSS" and row.peak.best_pips > COST + EPS for row in contiguous
    )

    assert strict_loss_above_cost == 64

    for side in (BUY, SELL):
        _describe(
            "POOLED",
            side,
            pooled[side],
        )

    _describe(
        "POOLED",
        "ALL",
        all_rows,
    )

    print("T115_37_STRICT_LOSS_PEAK_MIRROR=OK")
    print("T115_38_COVERAGE_EXACT_MIRROR=OK")
    print("FOUR_PERIOD_OBSERVED_PEAK_RECONCILIATION=OK")
    print("GAPPED_TRUE_PEAK_UNKNOWN=True")
    print("MISSING_H1_FILLED=False")
    print("PEAK_EXIT_EXECUTION_SIMULATED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Виконати аудит без зміни production і MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_38_H1_Gap_Coverage_Selection_Bias_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-39|TEST_ONLY|" "OBSERVED_H1_CLOSE_COVERAGE_AUDIT")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("OBSERVED_COMPLETED_H1_ONLY=True")
    print("INCLUDE_GAPPED_TRADES=True|TOTAL_TRADES=333")
    print("GAPPED_PEAK=LOWER_BOUND|NO_FORWARD_FILL=True")
    print("COST040_HYPOTHETICAL=True|NO_PARAMETER_SEARCH=True")

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
    print("T115_39_OBSERVED_H1_CLOSE_COVERAGE_AUDIT=OK")


if __name__ == "__main__":
    main()
