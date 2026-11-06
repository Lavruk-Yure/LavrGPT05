# -*- coding: utf-8 -*-
"""RoadMap115 / T115-36: first-H1 early-exit counterfactual.

TEST_ONLY / RESEARCH_ONLY.

Незмінні H1 baseline з T115-32, чотири періоди.
Одна умова: напрямлений close першої завершеної H1 < 0.
Умовне виконання: open M1 через хвилину після checkpoint.

Це парний контрфактичний розрахунок, НЕ повний Replay.
Нові входи та зміна зайнятості позиції не моделюються.
Витрати 0.40 пункту round-trip застосовуються один раз.
"""

from __future__ import annotations

import csv
import hashlib
import math
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

early_mod = import_module("T115_34_H1_Early_Close_Outcome_Anatomy")

audit_mod = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

make_bar = entry_mod.Bar
make_trade = exit_mod.ClosedTrade

BUY = exit_mod.DIRECTION_UP
SELL = exit_mod.DIRECTION_DOWN

PIP = 0.0001
COST = early_mod.COST
EPS = 1e-6

H1_SPAN = timedelta(hours=1)
ONE_MINUTE = timedelta(minutes=1)

EXPECTED = audit_mod.EXPECTED

HISTORY = ROOT / "data/history/CTRADER/EURUSD/M1"

LONG_FILE = "2024-10-22_2026-10-21_CTRADER_EURUSD_M1.csv"

FILE_2025 = "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv"

FILE_2026 = "2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv"

SOURCES = {
    "2024_NOV_DEC": LONG_FILE,
    "2025": FILE_2025,
    "2026_TO_2026_08_25": FILE_2026,
    "2026_AUG_OCT": LONG_FILE,
}

HEADER = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

CLOSED = "CLOSED_BY_CHECKPOINT"
NO_FIRST = "MISSING_FIRST_H1"
NONNEGATIVE = "NONNEGATIVE_FIRST_H1"
NO_TIME = "EXIT_BEFORE_EXECUTION"
NO_M1 = "MISSING_EXECUTION_M1"
EARLY_EXIT = "EARLY_EXIT"

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(early_mod, "load_history")
early_close = getattr(early_mod, "_early_close")


@dataclass(frozen=True, slots=True)
class Result:
    """Результат одного baseline-trade без нових входів."""

    trade: ClosedTrade
    baseline_net: float
    scenario_net: float
    status: str
    first_h1: float | None
    execution_at: datetime | None

    @property
    def delta(self) -> float:
        return self.scenario_net - self.baseline_net


def _sha(path: Path) -> str:
    """SHA256 для контролю незмінності production."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _timestamp(value: str) -> datetime:
    """Зчитати часову мітку M1 у UTC."""
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))

    assert at.tzinfo is not None
    assert at.utcoffset() == timedelta(0)

    return at.astimezone(UTC)


def _baseline_net(trade: ClosedTrade) -> float:
    """Baseline Net із гіпотетичними витратами."""
    return float(trade.pips) - COST


def _checkpoint(trade: ClosedTrade) -> datetime:
    return trade.entry_at + H1_SPAN


def _execution_time(trade: ClosedTrade) -> datetime:
    return _checkpoint(trade) + ONE_MINUTE


def _required_prices(
    windows: list[Window],
) -> dict[str, dict[datetime, float]]:
    """Зчитати лише потрібні M1 open за точними timestamp."""
    targets: dict[str, set[datetime]] = {name: set() for name in EXPECTED}

    for window in windows:
        for item in window.entries:
            trade = item.trade
            at = _execution_time(trade)

            if at < trade.exit_at:
                targets[window.name].add(at)

    output: dict[str, dict[datetime, float]] = {name: {} for name in EXPECTED}

    source_targets: dict[str, set[datetime]] = {}

    for name, filename in SOURCES.items():
        source_targets.setdefault(
            filename,
            set(),
        ).update(targets[name])

    source_prices: dict[str, dict[datetime, float]] = {}

    for filename, requested in source_targets.items():
        path = HISTORY / filename
        assert path.is_file()

        found: dict[datetime, float] = {}

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            reader = csv.reader(stream)

            header = next(reader, None)
            assert header is not None
            assert tuple(header) == HEADER

            for cells in reader:
                assert len(cells) == len(HEADER)

                at = _timestamp(cells[0])

                if at not in requested:
                    continue

                assert at not in found

                price = float(cells[1])

                assert math.isfinite(price)
                assert price > 0

                found[at] = price

        source_prices[filename] = found

        print(
            f"M1_SOURCE|FILE={filename}|"
            f"REQUESTED={len(requested)}|"
            f"FOUND={len(found)}|"
            f"MISSING={len(requested) - len(found)}"
        )

    for name, filename in SOURCES.items():
        prices = source_prices[filename]

        output[name] = {at: prices[at] for at in targets[name] if at in prices}

    return output


def _simulate(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
    prices: dict[datetime, float],
) -> Result:
    """Оцінити ранній вихід лише з доступної на той час ціни."""
    baseline = _baseline_net(trade)

    if trade.exit_at <= _checkpoint(trade):
        return Result(
            trade,
            baseline,
            baseline,
            CLOSED,
            None,
            None,
        )

    first = early_close(
        trade,
        bars,
        times,
        1,
    )

    if first is None:
        return Result(
            trade,
            baseline,
            baseline,
            NO_FIRST,
            None,
            None,
        )

    if first >= -EPS:
        return Result(
            trade,
            baseline,
            baseline,
            NONNEGATIVE,
            first,
            None,
        )

    execution_at = _execution_time(trade)

    if execution_at >= trade.exit_at:
        return Result(
            trade,
            baseline,
            baseline,
            NO_TIME,
            first,
            None,
        )

    price = prices.get(execution_at)

    if price is None:
        return Result(
            trade,
            baseline,
            baseline,
            NO_M1,
            first,
            None,
        )

    if trade.direction == BUY:
        gross = (price - trade.entry_price) / PIP
    else:
        assert trade.direction == SELL

        gross = (trade.entry_price - price) / PIP

    scenario = gross - COST

    assert math.isfinite(scenario)
    assert execution_at > _checkpoint(trade)
    assert execution_at < trade.exit_at

    return Result(
        trade=trade,
        baseline_net=baseline,
        scenario_net=scenario,
        status=EARLY_EXIT,
        first_h1=first,
        execution_at=execution_at,
    )


def _synthetic() -> None:
    """Контроль знака, часу виконання та одного списання витрат."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    bars = [
        make_bar(
            at,
            1.1000,
            1.1005,
            1.0980,
            1.0990,
        ),
        make_bar(
            at + H1_SPAN,
            1.0992,
            1.1000,
            1.0980,
            1.0990,
        ),
        make_bar(
            at + 2 * H1_SPAN,
            1.0990,
            1.0995,
            1.0960,
            1.0970,
        ),
        make_bar(
            at + 3 * H1_SPAN,
            1.0950,
            1.0960,
            1.0940,
            1.0950,
        ),
    ]

    times = [bar.timestamp for bar in bars]

    trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1_SPAN,
        entry_price=1.1000,
        exit_price=1.0950,
        pips=-50.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    fill_time = at + H1_SPAN + ONE_MINUTE

    result = _simulate(
        trade,
        bars,
        times,
        {fill_time: 1.0992},
    )

    assert result.status == EARLY_EXIT
    assert result.execution_at == fill_time

    assert math.isclose(
        result.first_h1,
        -10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        result.baseline_net,
        -50.4,
        abs_tol=EPS,
    )

    assert math.isclose(
        result.scenario_net,
        -8.4,
        abs_tol=EPS,
    )

    assert math.isclose(
        result.delta,
        42.0,
        abs_tol=EPS,
    )

    # Після checkpoint майбутні high/low/close не впливають.
    changed = [
        bars[0],
        make_bar(
            at + H1_SPAN,
            1.0992,
            1.2000,
            1.0500,
            1.1500,
        ),
        bars[2],
        bars[3],
    ]

    assert result == _simulate(
        trade,
        changed,
        times,
        {fill_time: 1.0992},
    )

    missing = _simulate(
        trade,
        bars,
        times,
        {},
    )

    assert missing.status == NO_M1
    assert missing.delta == 0.0

    nonnegative_bars = [
        make_bar(
            at,
            1.1000,
            1.1020,
            1.0990,
            1.1010,
        ),
        *bars[1:],
    ]

    unchanged = _simulate(
        trade,
        nonnegative_bars,
        times,
        {fill_time: 1.0992},
    )

    assert unchanged.status == NONNEGATIVE
    assert unchanged.delta == 0.0

    short = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + H1_SPAN,
        entry_price=1.1000,
        exit_price=1.0992,
        pips=-8.0,
        holding_bars=1,
        holding_minutes=60,
        exit_reason="ENDING",
        exit_gap=False,
    )

    closed = _simulate(
        short,
        bars,
        times,
        {fill_time: 1.0992},
    )

    assert closed.status == CLOSED
    assert closed.delta == 0.0

    sell_bars = [
        make_bar(
            at,
            1.1000,
            1.1020,
            1.0990,
            1.1010,
        ),
        make_bar(
            at + H1_SPAN,
            1.1012,
            1.1030,
            1.1000,
            1.1020,
        ),
        make_bar(
            at + 2 * H1_SPAN,
            1.1020,
            1.1040,
            1.1010,
            1.1030,
        ),
        make_bar(
            at + 3 * H1_SPAN,
            1.1050,
            1.1060,
            1.1040,
            1.1050,
        ),
    ]

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + 3 * H1_SPAN,
        entry_price=1.1000,
        exit_price=1.1050,
        pips=-50.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell_result = _simulate(
        sell,
        sell_bars,
        times,
        {fill_time: 1.1012},
    )

    assert sell_result.status == EARLY_EXIT

    assert math.isclose(
        sell_result.first_h1,
        -10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        sell_result.scenario_net,
        -12.4,
        abs_tol=EPS,
    )

    print("SYNTHETIC_COMPLETED_H1_DECISION=OK")
    print("SYNTHETIC_DELAYED_M1_EXECUTION=OK")
    print("SYNTHETIC_FUTURE_OHLC_ISOLATION=OK")
    print("SYNTHETIC_BUY_SELL_EXIT_ACCOUNTING=OK")
    print("SYNTHETIC_NO_M1_NO_FORWARD_FILL=OK")
    print("SYNTHETIC_ALREADY_CLOSED_PRESERVATION=OK")


def _summarize(
    period: str,
    side: str,
    rows: list[Result],
) -> None:
    """Показати виграш і шкоду на однакових угодах."""
    baseline = math.fsum(row.baseline_net for row in rows)

    scenario = math.fsum(row.scenario_net for row in rows)

    delta = math.fsum(row.delta for row in rows)

    assert math.isclose(
        scenario - baseline,
        delta,
        abs_tol=EPS,
    )

    executed = [row for row in rows if row.status == EARLY_EXIT]

    saved = [row.delta for row in executed if row.delta > EPS]

    harmed = [row.delta for row in executed if row.delta < -EPS]

    originally_nonloss = sum(row.baseline_net >= -EPS for row in executed)

    positive = math.fsum(saved)
    negative = math.fsum(harmed)

    assert math.isclose(
        positive + negative,
        delta,
        abs_tol=EPS,
    )

    statuses = {
        status: sum(row.status == status for row in rows)
        for status in (
            CLOSED,
            NO_FIRST,
            NONNEGATIVE,
            NO_TIME,
            NO_M1,
            EARLY_EXIT,
        )
    }

    assert sum(statuses.values()) == len(rows)

    print(
        f"PAIRED|PERIOD={period}|SIDE={side}|"
        f"TRADES={len(rows)}|"
        f"EARLY_EXITS={len(executed)}|"
        f"BASE_NET040={baseline:+.2f}|"
        f"SCENARIO_NET040={scenario:+.2f}|"
        f"DELTA={delta:+.2f}"
    )

    print(
        f"IMPACT|PERIOD={period}|SIDE={side}|"
        f"IMPROVED={len(saved)}|"
        f"HARMED={len(harmed)}|"
        f"SAVINGS={positive:+.2f}|"
        f"HARM={negative:+.2f}|"
        f"ORIGINAL_NONLOSS_EXITED={originally_nonloss}"
    )

    print(
        f"COVERAGE|PERIOD={period}|SIDE={side}|"
        f"ALREADY_CLOSED={statuses[CLOSED]}|"
        f"MISSING_FIRST_H1={statuses[NO_FIRST]}|"
        f"NONNEGATIVE={statuses[NONNEGATIVE]}|"
        f"EXIT_BEFORE_EXEC={statuses[NO_TIME]}|"
        f"MISSING_M1={statuses[NO_M1]}|"
        f"EXECUTED={statuses[EARLY_EXIT]}"
    )

    top = sorted(
        saved,
        reverse=True,
    )[:3]

    top_sum = math.fsum(top)

    print(
        f"TAIL|PERIOD={period}|SIDE={side}|"
        f"TOP3_SAVINGS={top_sum:+.2f}|"
        f"DELTA_EXCLUDING_TOP3={delta - top_sum:+.2f}"
    )


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
    prices: dict[str, dict[datetime, float]],
) -> None:
    """Звірити результати всіх незмінних baseline-угод."""
    all_rows: list[Result] = []

    for window in windows:
        bars = history[window.name]
        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        rows = [
            _simulate(
                item.trade,
                bars,
                times,
                prices[window.name],
            )
            for item in window.entries
        ]

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(rows) == expected_count
        assert window.open_end == open_end

        baseline = math.fsum(row.baseline_net for row in rows)

        assert math.isclose(
            baseline,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={expected_count}|"
            f"NET040={baseline:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            side_rows = [row for row in rows if row.trade.direction == side]

            _summarize(
                window.name,
                side,
                side_rows,
            )

        _summarize(
            window.name,
            "ALL",
            rows,
        )

        print(f"PERIOD_PAIRED_RECONCILIATION=" f"{window.name}:OK")

        all_rows.extend(rows)

    _summarize(
        "POOLED",
        "ALL",
        all_rows,
    )

    print("FOUR_PERIOD_PAIRED_RECONCILIATION=OK")
    print("REPLACEMENT_ENTRIES_MODELLED=False")
    print("POSITION_OCCUPANCY_REPLAYED=False")
    print("BROKER_FILL_CONFIRMED=False")


def main() -> None:
    """Перевірити правило без зміни production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_35_First_H1_Risk_Separation_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-36|TEST_ONLY|" "FIRST_H1_NEGATIVE_EARLY_EXIT_COUNTERFACTUAL")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("DECISION=FIRST_COMPLETED_H1_NEGATIVE")
    print("EXECUTION=CHECKPOINT_PLUS_1M_M1_OPEN_MID")
    print("COST040_HYPOTHETICAL=True|THRESHOLD_TUNING=False")
    print("PAIRED_ONLY=True|NOT_FULL_TRADING_REPLAY=True")

    _synthetic()

    windows = load_windows()
    history = load_history()
    prices = _required_prices(windows)

    _report(
        windows,
        history,
        prices,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("M1_EXECUTION_PROXY=True|REAL_FILL_VERIFIED=False")
    print("broker_requests=0|TEST_ONLY=True|RESEARCH_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_36_FIRST_H1_EARLY_EXIT_COUNTERFACTUAL=OK")


if __name__ == "__main__":
    main()
