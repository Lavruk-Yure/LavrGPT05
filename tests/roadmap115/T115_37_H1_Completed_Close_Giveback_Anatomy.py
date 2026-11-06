# -*- coding: utf-8 -*-
"""RoadMap115 / T115-37: H1 completed-close giveback anatomy.

TEST_ONLY / DATA_ONLY.

Незмінні baseline-угоди T115-32 у чотирьох періодах.
Досліджується найкращий завершений H1 close під час позиції.

Показники завершених свічок є історичними спостереженнями.
Максимум за всю угоду — outcome label, не торговий сигнал.
Угоди з несуцільними H1 виключаються з цього вимірювання.
Жодних нових entry, exit, SL/TP та оптимізації.
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
    from T115_25_H1_Entry_M15_State_Anatomy import EntryState
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window

entry_mod = import_module("T115_01_Alligator_Entry_Only_Events")

exit_mod = import_module("T115_02_Alligator_Exit_Only_Trades")

audit_mod = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

loss_mod = import_module("T115_33_H1_Large_Loss_Anatomy")

make_bar = entry_mod.Bar
make_trade = exit_mod.ClosedTrade

BUY = exit_mod.DIRECTION_UP
SELL = exit_mod.DIRECTION_DOWN

PIP = 0.0001
COST = loss_mod.COST
EPS = 1e-6
H1 = timedelta(hours=1)

EXPECTED = audit_mod.EXPECTED

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(loss_mod, "_history")


@dataclass(frozen=True, slots=True)
class ClosePeak:
    """Найкращий завершений H1 close за час угоди."""

    peak_pips: float
    peak_at: datetime | None
    final_gross_pips: float
    peak_minus_exit_pips: float
    observed_h1: int


@dataclass(frozen=True, slots=True)
class Measured:
    """Завершена угода з доступним або виключеним виміром."""

    item: EntryState
    peak: ClosePeak | None


def _sha(path: Path) -> str:
    """Контроль незмінності опорних файлів."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _net(trade: ClosedTrade) -> float:
    """Baseline Net після умовних витрат."""
    return float(trade.pips) - COST


def _measure(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
) -> ClosePeak | None:
    """Виміряти close-пік лише на суцільних завершених H1."""
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

    observed = bars[left:right]
    assert len(observed) == trade.holding_bars

    duration = trade.exit_at - trade.entry_at
    expected_count = duration // H1

    assert duration == expected_count * H1

    if len(observed) != expected_count:
        return None

    for index, bar in enumerate(observed):
        expected_at = trade.entry_at + index * H1

        if bar.timestamp != expected_at:
            return None

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

    if trade.direction == BUY:
        direction = 1
    else:
        assert trade.direction == SELL
        direction = -1

    gross = direction * (trade.exit_price - trade.entry_price) / PIP

    assert math.isclose(
        gross,
        trade.pips,
        abs_tol=EPS,
    )

    peak_pips = 0.0
    peak_at: datetime | None = None

    for bar in observed:
        completed_at = bar.timestamp + H1

        assert completed_at <= trade.exit_at

        signed_close = direction * (bar.close - trade.entry_price) / PIP

        if signed_close > peak_pips + EPS:
            peak_pips = signed_close
            peak_at = completed_at

    assert peak_pips >= 0.0

    return ClosePeak(
        peak_pips=peak_pips,
        peak_at=peak_at,
        final_gross_pips=gross,
        peak_minus_exit_pips=peak_pips - gross,
        observed_h1=len(observed),
    )


def _synthetic() -> None:
    """Перевірити BUY/SELL, прогалини та межу майбутніх барів."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    buy_bars = [
        make_bar(
            at,
            1.1000,
            1.1030,
            1.0990,
            1.1010,
        ),
        make_bar(
            at + H1,
            1.1010,
            1.1050,
            1.1000,
            1.1030,
        ),
        make_bar(
            at + 2 * H1,
            1.1030,
            1.1040,
            1.0970,
            1.0980,
        ),
        make_bar(
            at + 3 * H1,
            1.0970,
            1.1500,
            1.0500,
            1.1200,
        ),
    ]

    times = [bar.timestamp for bar in buy_bars]

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.0970,
        pips=-30.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    measured = _measure(
        buy,
        buy_bars,
        times,
    )

    assert measured is not None

    assert math.isclose(
        measured.peak_pips,
        30.0,
        abs_tol=EPS,
    )

    assert measured.peak_at == at + 2 * H1

    assert math.isclose(
        measured.peak_minus_exit_pips,
        60.0,
        abs_tol=EPS,
    )

    changed = [
        *buy_bars[:3],
        make_bar(
            at + 3 * H1,
            1.0970,
            1.3000,
            1.0100,
            1.2500,
        ),
    ]

    assert measured == _measure(
        buy,
        changed,
        times,
    )

    gap_bars = [
        buy_bars[0],
        buy_bars[2],
        buy_bars[3],
    ]

    gap_times = [bar.timestamp for bar in gap_bars]

    # Для синтетичної прогалини змінюється і кількість
    # фактично спостережених свічок у записі угоди.
    gap_trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.0970,
        pips=-30.0,
        holding_bars=2,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    assert (
        _measure(
            gap_trade,
            gap_bars,
            gap_times,
        )
        is None
    )

    sell_bars = [
        make_bar(
            at,
            1.1000,
            1.1010,
            1.0980,
            1.0990,
        ),
        make_bar(
            at + H1,
            1.0990,
            1.1000,
            1.0960,
            1.0970,
        ),
        make_bar(
            at + 2 * H1,
            1.0970,
            1.1010,
            1.0965,
            1.0990,
        ),
        make_bar(
            at + 3 * H1,
            1.1010,
            1.1020,
            1.1000,
            1.1010,
        ),
    ]

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.1010,
        pips=-10.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    short = _measure(
        sell,
        sell_bars,
        times,
    )

    assert short is not None

    assert math.isclose(
        short.peak_pips,
        30.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        short.peak_minus_exit_pips,
        40.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_COMPLETED_CLOSE_PEAK=OK")
    print("SYNTHETIC_BUY_SELL_DIRECTION=OK")
    print("SYNTHETIC_FUTURE_BAR_ISOLATION=OK")
    print("SYNTHETIC_NONCONTIGUOUS_H1_EXCLUSION=OK")


def _fmt(value: float | None) -> str:
    """Форматувати число або позначити його відсутність."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _group(
    period: str,
    side: str,
    outcome: str,
    rows: list[Measured],
) -> None:
    """Порахувати close-пік, не створюючи правил виходу."""
    eligible = [row for row in rows if row.peak is not None]

    excluded = len(rows) - len(eligible)

    peaks = [row.peak.peak_pips for row in eligible if row.peak is not None]

    positive = sum(peak > EPS for peak in peaks)

    above_cost = sum(peak > COST + EPS for peak in peaks)

    median_peak = statistics.median(peaks) if peaks else None

    net = math.fsum(_net(row.item.trade) for row in rows)

    print(
        f"CLOSE_PEAK|PERIOD={period}|"
        f"SIDE={side}|OUTCOME={outcome}|"
        f"TOTAL={len(rows)}|"
        f"ELIGIBLE={len(eligible)}|"
        f"NONCONTIGUOUS={excluded}|"
        f"POSITIVE_CLOSE_PEAK={positive}|"
        f"PEAK_GT_COST={above_cost}|"
        f"MEDIAN_PEAK={_fmt(median_peak)}|"
        f"BASE_NET040={net:+.2f}"
    )


def _report_side(
    period: str,
    side: str,
    rows: list[Measured],
) -> None:
    """Окремо порівняти збиткові та незбиткові угоди."""
    losses = [row for row in rows if _net(row.item.trade) < -EPS]

    nonlosses = [row for row in rows if _net(row.item.trade) >= -EPS]

    assert len(losses) + len(nonlosses) == len(rows)

    _group(
        period,
        side,
        "LOSS",
        losses,
    )

    _group(
        period,
        side,
        "NONLOSS",
        nonlosses,
    )

    candidates = [
        row
        for row in losses
        if row.peak is not None and row.peak.peak_pips > COST + EPS
    ]

    ranked = sorted(
        candidates,
        key=lambda row: (
            -row.peak.peak_minus_exit_pips,
            row.item.trade.entry_at,
        ),
    )

    for rank, row in enumerate(
        ranked[:3],
        start=1,
    ):
        trade = row.item.trade
        peak = row.peak

        assert peak is not None

        print(
            f"LOSS_CLOSE_GIVEBACK|PERIOD={period}|"
            f"SIDE={side}|RANK={rank}|"
            f"ENTRY={trade.entry_at.isoformat()}|"
            f"EXIT={trade.exit_at.isoformat()}|"
            f"M15={row.item.strict_class}|"
            f"NET040={_net(trade):+.2f}|"
            f"BEST_H1_CLOSE={peak.peak_pips:+.2f}|"
            f"PEAK_MINUS_EXIT="
            f"{peak.peak_minus_exit_pips:+.2f}|"
            f"BEST_COMPLETED_AT={peak.peak_at.isoformat()}|"
            f"OBS_H1={peak.observed_h1}"
        )

    print(f"CLOSE_PEAK_SIDE_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Зіставити однакові baseline в усіх чотирьох вікнах."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: dict[str, list[Measured]] = {
        BUY: [],
        SELL: [],
    }

    for window in windows:
        bars = history[window.name]

        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(window.entries) == count
        assert window.open_end == open_end

        actual_net = math.fsum(_net(item.trade) for item in window.entries)

        assert math.isclose(
            actual_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={count}|"
            f"NET040={actual_net:+.2f}"
        )

        for side in (BUY, SELL):
            rows = [
                Measured(
                    item=item,
                    peak=_measure(
                        item.trade,
                        bars,
                        times,
                    ),
                )
                for item in window.entries
                if item.trade.direction == side
            ]

            _report_side(
                window.name,
                side,
                rows,
            )

            pooled[side].extend(rows)

        print(f"PERIOD_CLOSE_PEAK_RECONCILIATION=" f"{window.name}:OK")

    for side in (BUY, SELL):
        _report_side(
            "POOLED",
            side,
            pooled[side],
        )

    print("FOUR_PERIOD_CLOSE_PEAK_RECONCILIATION=OK")
    print("BEST_CLOSE_EXECUTION_SIMULATED=False")
    print("FUTURE_PEAK_USED_FOR_TRADING=False")
    print("NEW_EXIT_RULE_CREATED=False")


def main() -> None:
    """Дослідити exit-результати без зміни production."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/"
        "T115_36_First_H1_Negative_Early_Exit_Counterfactual.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-37|TEST_ONLY|" "H1_COMPLETED_CLOSE_GIVEBACK_ANATOMY")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("OBSERVATION=COMPLETED_H1_CLOSE_ONLY")
    print("NONCONTIGUOUS_H1=EXCLUDED")
    print("COST040_HYPOTHETICAL=True|NO_THRESHOLD_SEARCH=True")

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
    print("T115_37_H1_COMPLETED_CLOSE_GIVEBACK_ANATOMY=OK")


if __name__ == "__main__":
    main()
