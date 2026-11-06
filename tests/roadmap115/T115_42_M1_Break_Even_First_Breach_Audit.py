# -*- coding: utf-8 -*-
"""RoadMap115 / T115-42: M1 break-even first-breach audit.

TEST_ONLY / DATA_ONLY.

Активація BE незмінна від T115-41:
завершений H1-close > 0.40 пункту в напрямку позиції.

Спостереження M1 починається через одну хвилину
після завершення H1, строго до baseline exit.

Визначається перше спостережене порушення BE-рівня
та порядок цього порушення відносно першої прогалини M1.

M1 OHLC є mid-price proxy, не Bid/Ask та не broker fill.
M1 після активації використовується лише як outcome label.
Нові торгові рішення й замінні входи не моделюються.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
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
    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade
    from T115_32_Cross_Period_M15_Entry_State_Audit import Window

be_mod = import_module("T115_41_H1_Break_Even_Activation_Anatomy")

m1_mod = import_module("T115_36_First_H1_Negative_Early_Exit_Counterfactual")

BUY = be_mod.BUY
SELL = be_mod.SELL
COST = be_mod.COST
PIP = be_mod.PIP
EPS = be_mod.EPS

MINUTE = timedelta(minutes=1)

EXPECTED = be_mod.EXPECTED

EXPECTED_ACTIVATIONS = {
    "2024_NOV_DEC": {BUY: 9, SELL: 10},
    "2025": {BUY: 69, SELL: 58},
    "2026_TO_2026_08_25": {BUY: 35, SELL: 39},
    "2026_AUG_OCT": {BUY: 6, SELL: 12},
}

SOURCE_FILES = m1_mod.SOURCES
M1_DIRECTORY = m1_mod.HISTORY
M1_HEADER = m1_mod.HEADER

parse_timestamp = getattr(m1_mod, "_timestamp")
scan_be = getattr(be_mod, "_scan")
load_windows = be_mod.load_windows
load_history = be_mod.load_history

BREACH_NO_GAP = "BREACH_NO_PRIOR_GAP"
BREACH_BEFORE_GAP = "BREACH_BEFORE_FIRST_GAP"
GAP_BEFORE_BREACH = "GAP_BEFORE_OBSERVED_BREACH"
GAP_NO_BREACH = "GAP_WITHOUT_OBSERVED_BREACH"
NO_BREACH = "NO_GAP_NO_OBSERVED_BREACH"
NOT_ACTIVATED = "NOT_ACTIVATED"

STATUSES = (
    BREACH_NO_GAP,
    BREACH_BEFORE_GAP,
    GAP_BEFORE_BREACH,
    GAP_NO_BREACH,
    NO_BREACH,
    NOT_ACTIVATED,
)


@dataclass(slots=True)
class Target:
    """Часова послідовність M1 для одного BE-кандидата."""

    period: str
    trade: ClosedTrade
    activation_at: datetime
    activation_pips: float
    start_at: datetime
    previous_at: datetime | None = None
    first_gap_at: datetime | None = None
    first_breach_at: datetime | None = None
    observed_m1: int = 0
    missing_m1: int = 0

    @property
    def exit_at(self) -> datetime:
        return self.trade.exit_at

    @property
    def key(self) -> tuple[str, datetime, str]:
        return (
            self.period,
            self.trade.entry_at,
            self.trade.direction,
        )

    @property
    def net(self) -> float:
        return float(self.trade.pips) - COST

    @property
    def status(self) -> str:
        if self.first_breach_at is not None:
            if self.first_gap_at is None:
                return BREACH_NO_GAP

            if self.first_breach_at < self.first_gap_at:
                return BREACH_BEFORE_GAP

            return GAP_BEFORE_BREACH

        if self.first_gap_at is not None:
            return GAP_NO_BREACH

        return NO_BREACH

    def _record_missing(
        self,
        next_expected: datetime,
        actual: datetime,
    ) -> None:
        """Зафіксувати пропущені M1 без відновлення цін."""
        assert actual >= next_expected

        difference = actual - next_expected

        assert difference % MINUTE == timedelta(0)

        missing = difference // MINUTE

        if missing:
            if self.first_gap_at is None:
                self.first_gap_at = next_expected

            self.missing_m1 += missing

    def consume(
        self,
        at: datetime,
        high: float,
        low: float,
    ) -> None:
        """Опрацювати наявний M1-бар за часовим порядком."""
        assert self.start_at <= at < self.exit_at
        assert low <= high

        expected = (
            self.start_at if self.previous_at is None else self.previous_at + MINUTE
        )

        self._record_missing(expected, at)

        if self.trade.direction == BUY:
            be_level = self.trade.entry_price + COST * PIP

            breached = low <= be_level + EPS * PIP
        else:
            assert self.trade.direction == SELL

            be_level = self.trade.entry_price - COST * PIP

            breached = high >= be_level - EPS * PIP

        if breached and self.first_breach_at is None:
            self.first_breach_at = at

        self.previous_at = at
        self.observed_m1 += 1

    def finish(self) -> None:
        """Облікувати також прогалину наприкінці інтервалу."""
        expected = (
            self.start_at if self.previous_at is None else self.previous_at + MINUTE
        )

        self._record_missing(expected, self.exit_at)

        total = (self.exit_at - self.start_at) // MINUTE

        assert total > 0
        assert total == self.observed_m1 + self.missing_m1

        if self.first_breach_at is not None:
            assert self.start_at <= self.first_breach_at
            assert self.first_breach_at < self.exit_at

    @property
    def breach_delay_min(self) -> int | None:
        if self.first_breach_at is None:
            return None

        return (self.first_breach_at - self.activation_at) // MINUTE


def _sha(path: Path) -> str:
    """Контроль незмінності production та опорного тесту."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _synthetic() -> None:
    """Перевірити перший контакт та порядок M1-прогалин."""
    make_trade = be_mod.make_trade

    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    activation = at + timedelta(hours=1)
    start = activation + MINUTE
    end = activation + timedelta(hours=1)

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=end,
        entry_price=1.1000,
        exit_price=1.1020,
        pips=20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=end,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    def target(trade: ClosedTrade) -> Target:
        return Target(
            period="SYNTHETIC",
            trade=trade,
            activation_at=activation,
            activation_pips=10.0,
            start_at=start,
        )

    # Без пропусків: перший контакт на другій M1.
    continuous = target(buy)

    for offset in range(59):
        current = start + offset * MINUTE
        low = 1.10002 if offset == 1 else 1.10050

        continuous.consume(
            current,
            high=1.10100,
            low=low,
        )

    continuous.finish()

    assert continuous.status == BREACH_NO_GAP
    assert continuous.breach_delay_min == 2
    assert continuous.missing_m1 == 0

    # Спочатку пропуск M1, потім спостережений контакт.
    uncertain = target(buy)

    uncertain.consume(
        start,
        high=1.1010,
        low=1.1005,
    )

    uncertain.consume(
        start + 3 * MINUTE,
        high=1.1010,
        low=1.10002,
    )

    uncertain.finish()

    assert uncertain.status == GAP_BEFORE_BREACH
    assert uncertain.first_gap_at == start + MINUTE
    assert uncertain.breach_delay_min == 4

    # Контакт відомий раніше за першу прогалину.
    early = target(buy)

    early.consume(
        start,
        high=1.1010,
        low=1.10002,
    )

    early.consume(
        start + 3 * MINUTE,
        high=1.1010,
        low=1.1005,
    )

    early.finish()

    assert early.status == BREACH_BEFORE_GAP
    assert early.first_breach_at < early.first_gap_at

    # Без контакту, але з прогалинами.
    gap_only = target(buy)

    gap_only.consume(
        start,
        high=1.1010,
        low=1.1005,
    )

    gap_only.finish()

    assert gap_only.status == GAP_NO_BREACH

    # Повний M1-інтервал без контакту.
    untouched = target(buy)

    for offset in range(59):
        untouched.consume(
            start + offset * MINUTE,
            high=1.1010,
            low=1.1005,
        )

    untouched.finish()

    assert untouched.status == NO_BREACH

    # SELL: контакт визначається через high.
    short = target(sell)

    for offset in range(59):
        high = 1.09998 if offset == 2 else 1.09900

        short.consume(
            start + offset * MINUTE,
            high=high,
            low=1.09850,
        )

    short.finish()

    assert short.status == BREACH_NO_GAP
    assert short.breach_delay_min == 3

    print("SYNTHETIC_M1_FIRST_BREACH_CAUSAL_ORDER=OK")
    print("SYNTHETIC_GAP_BEFORE_BREACH_UNKNOWN=OK")
    print("SYNTHETIC_BREACH_BEFORE_GAP=OK")
    print("SYNTHETIC_NO_BREACH_AND_GAP_CASES=OK")
    print("SYNTHETIC_BUY_SELL_BE_DIRECTION=OK")
    print("SYNTHETIC_M1_COVERAGE_RECONCILIATION=OK")


def _targets(
    windows: list[Window],
    history: dict,
) -> dict[tuple[str, datetime, str], Target]:
    """Сформувати кандидати лише після завершеного H1."""
    targets: dict[tuple[str, datetime, str], Target] = {}

    for window in windows:
        bars = history[window.name]
        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        activations = {BUY: 0, SELL: 0}

        for item in window.entries:
            trade = item.trade

            observed = scan_be(
                trade,
                bars,
                times,
            )

            if not observed.activated:
                continue

            assert observed.activation_at is not None
            assert observed.activation_pips is not None

            activations[trade.direction] += 1

            start_at = observed.activation_at + MINUTE

            # Одна повна H1 між активацією та exit
            # гарантує наявність M1-контрольного вікна.
            assert start_at < trade.exit_at

            candidate = Target(
                period=window.name,
                trade=trade,
                activation_at=observed.activation_at,
                activation_pips=observed.activation_pips,
                start_at=start_at,
            )

            assert candidate.key not in targets
            targets[candidate.key] = candidate

        assert activations == EXPECTED_ACTIVATIONS[window.name]

        print(
            f"BE_ACTIVATION_MATCH={window.name}:OK|"
            f"BUY={activations[BUY]}|"
            f"SELL={activations[SELL]}"
        )

    assert len(targets) == 238

    print("T115_41_BE_ACTIVATION_EXACT_MIRROR=OK")

    return targets


def _read_source(
    filename: str,
    selected: list[Target],
) -> None:
    """Пройти M1 один раз, зіставляючи активні інтервали."""
    path = M1_DIRECTORY / filename
    assert path.is_file()

    ordered = sorted(
        selected,
        key=lambda target: (
            target.start_at,
            target.exit_at,
        ),
    )

    # Heap містить інтервали, які ще не завершені.
    active: list[tuple[datetime, int, Target]] = []

    next_target = 0
    source_rows = 0
    matched_rows = 0

    previous_source_at: datetime | None = None

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

            if previous_source_at is not None:
                assert previous_source_at < at

            previous_source_at = at

            while next_target < len(ordered) and ordered[next_target].start_at <= at:
                candidate = ordered[next_target]

                heapq.heappush(
                    active,
                    (
                        candidate.exit_at,
                        next_target,
                        candidate,
                    ),
                )

                next_target += 1

            while active and active[0][0] <= at:
                heapq.heappop(active)

            if not active:
                continue

            high = float(cells[2])
            low = float(cells[3])

            assert math.isfinite(high)
            assert math.isfinite(low)
            assert low <= high

            for _, _, candidate in active:
                candidate.consume(
                    at,
                    high,
                    low,
                )

                matched_rows += 1

    for candidate in selected:
        candidate.finish()

    print(
        f"M1_SOURCE|FILE={filename}|"
        f"ROWS={source_rows}|"
        f"TARGETS={len(selected)}|"
        f"MATCHED_TARGET_MINUTES={matched_rows}|"
        "FORWARD_FILL=False"
    )


def _fmt(value: float | None) -> str:
    """Вивести число або NA."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _describe(
    period: str,
    side: str,
    trades: list[ClosedTrade],
    targets: dict[tuple[str, datetime, str], Target],
) -> None:
    """Показати різницю між контактами та невідомими M1."""
    selected = [
        targets.get(
            (
                period,
                trade.entry_at,
                trade.direction,
            )
        )
        for trade in trades
    ]

    activated = [item for item in selected if item is not None]

    inactive_count = len(selected) - len(activated)

    baseline = math.fsum(float(trade.pips) - COST for trade in trades)

    print(
        f"M1_BE_COVERAGE|PERIOD={period}|"
        f"SIDE={side}|TOTAL={len(trades)}|"
        f"ACTIVATED={len(activated)}|"
        f"NOT_ACTIVATED={inactive_count}|"
        f"BASE_NET040={baseline:+.2f}"
    )

    for status in STATUSES:
        if status == NOT_ACTIVATED:
            group = [trade for trade, item in zip(trades, selected) if item is None]
        else:
            group = [item.trade for item in activated if item.status == status]

        losses = sum(float(trade.pips) - COST < -EPS for trade in group)

        net = math.fsum(float(trade.pips) - COST for trade in group)

        delays = [
            item.breach_delay_min
            for item in activated
            if item.status == status and item.breach_delay_min is not None
        ]

        median_delay = statistics.median(delays) if delays else None

        print(
            f"M1_BE_GROUP|PERIOD={period}|"
            f"SIDE={side}|STATUS={status}|"
            f"COUNT={len(group)}|"
            f"BASE_LOSSES={losses}|"
            f"BASE_NONLOSSES={len(group) - losses}|"
            f"BASE_NET040={net:+.2f}|"
            f"MEDIAN_BREACH_DELAY_MIN="
            f"{_fmt(median_delay)}"
        )

    assert sum(
        sum(item.status == status for item in activated)
        for status in STATUSES
        if status != NOT_ACTIVATED
    ) == len(activated)

    missing = sum(item.missing_m1 for item in activated)

    unambiguous_breach = sum(
        item.status
        in (
            BREACH_NO_GAP,
            BREACH_BEFORE_GAP,
        )
        for item in activated
    )

    uncertain = sum(
        item.status
        in (
            GAP_BEFORE_BREACH,
            GAP_NO_BREACH,
        )
        for item in activated
    )

    print(
        f"M1_BE_SUMMARY|PERIOD={period}|"
        f"SIDE={side}|"
        f"BREACH_WITHOUT_PRIOR_GAP="
        f"{unambiguous_breach}|"
        f"UNCERTAIN_FIRST_BREACH={uncertain}|"
        f"MISSING_TARGET_MINUTES={missing}|"
        "STOP_FILL_VERIFIED=False"
    )

    print(f"M1_BE_PARTITION_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    targets: dict[tuple[str, datetime, str], Target],
) -> None:
    """Звірити незмінні baseline і всі M1-класи."""
    pooled_trades: dict[str, list[ClosedTrade]] = {
        BUY: [],
        SELL: [],
    }

    for window in windows:
        count, expected_net, _, open_end = EXPECTED[window.name]

        trades = [item.trade for item in window.entries]

        assert len(trades) == count
        assert window.open_end == open_end

        actual_net = math.fsum(float(trade.pips) - COST for trade in trades)

        assert math.isclose(
            actual_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={count}|NET040={actual_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            side_trades = [trade for trade in trades if trade.direction == side]

            _describe(
                window.name,
                side,
                side_trades,
                targets,
            )

            pooled_trades[side].extend(side_trades)

        print(f"PERIOD_M1_BE_RECONCILIATION={window.name}:OK")

    assert sum(len(items) for items in pooled_trades.values()) == 333

    for side in (BUY, SELL):
        # У pooled-підсумку залишаємо первісні period key.
        pooled_items = [
            item for item in targets.values() if item.trade.direction == side
        ]

        print(
            f"POOLED_M1_BE|SIDE={side}|"
            f"TOTAL={len(pooled_trades[side])}|"
            f"ACTIVATED={len(pooled_items)}|"
            f"BREACH_BEFORE_GAP={sum(
                item.status in (
                    BREACH_NO_GAP,
                    BREACH_BEFORE_GAP,
                )
                for item in pooled_items
            )}|"
            f"UNCERTAIN={sum(
                item.status in (
                    GAP_BEFORE_BREACH,
                    GAP_NO_BREACH,
                )
                for item in pooled_items
            )}"
        )

    print("FOUR_PERIOD_M1_BE_RECONCILIATION=OK")
    print("M1_FIRST_BREACH_IS_NOT_BROKER_FILL=True")
    print("EXECUTION_PROXY_START=ACTIVATION_PLUS_1_MINUTE")
    print("INITIAL_POST_ACTIVATION_MINUTE_EXCLUDED=True")
    print("BASELINE_TRADES_UNCHANGED=True")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Виконати аудит без змін production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_41_H1_Break_Even_Activation_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-42|TEST_ONLY|M1_BE_FIRST_BREACH_AUDIT")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("BE_ACTIVATION=FROZEN_T115_41")
    print("M1_SCAN_START=H1_COMPLETION_PLUS_1_MINUTE")
    print("M1_MID_OHLC_ONLY=True|STOP_FILL_NOT_MODELLED=True")
    print("GAP_ORDER_AUDIT=True|NO_FORWARD_FILL=True")

    _synthetic()

    windows = load_windows()
    history = load_history()
    targets = _targets(windows, history)

    grouped_sources: dict[str, list[Target]] = {}

    for candidate in targets.values():
        filename = SOURCE_FILES[candidate.period]

        grouped_sources.setdefault(
            filename,
            [],
        ).append(candidate)

    for filename, selected in grouped_sources.items():
        _read_source(filename, selected)

    _report(windows, targets)

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("M1_future_ranges_as_outcome_labels_only=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_42_M1_BE_FIRST_BREACH_AUDIT=OK")


if __name__ == "__main__":
    main()
