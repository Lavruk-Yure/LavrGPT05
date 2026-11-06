# -*- coding: utf-8 -*-
"""RoadMap115 / T115-40: causal H1 profit-to-loss transition.

TEST_ONLY / DATA_ONLY.

Чотири незмінні baseline-вікна T115-32, усі 333 угоди.

Подія:
1. Попередній завершений H1-close дав понад +0.40 pip.
2. Новий завершений H1-close показав від'ємний рух.
3. Обидва close належать безперервному відрізку H1.
4. Подія відбулася строго раніше штатного виходу.

Максимум оновлюється лише минулими завершеними H1.
Після прогалини H1 локальний максимум скидається.
Майбутній Net використовується тільки як outcome label.

Жодних нових exit, entry, SL/TP або оптимізації.
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
class Observation:
    """Причинна подія та результат незмінної baseline-угоди."""

    trade: ClosedTrade
    event_at: datetime | None
    prior_best_pips: float | None
    event_close_pips: float | None
    completed_before_exit: int
    adjacent_pairs: int
    favorable_seen: bool
    missing_h1: int

    @property
    def eligible(self) -> bool:
        """Мінімум два суміжні завершені H1 до виходу."""
        return self.adjacent_pairs > 0

    @property
    def triggered(self) -> bool:
        return self.event_at is not None

    @property
    def net(self) -> float:
        return float(self.trade.pips) - COST

    @property
    def loss(self) -> bool:
        return self.net < -EPS


def _sha(path: Path) -> str:
    """Контроль SHA256 без завантаження файлу в RAM."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _scan(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
) -> Observation:
    """Знайти перший перехід із прибутку в мінус причинно."""
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

    duration = trade.exit_at - trade.entry_at
    expected_count = duration // H1

    assert duration == expected_count * H1
    assert expected_count >= len(observed)

    missing_h1 = expected_count - len(observed)

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

    event_at: datetime | None = None
    prior_best: float | None = None
    event_close: float | None = None

    previous_at: datetime | None = None
    segment_best = 0.0
    favorable_seen = False

    completed_count = 0
    adjacent_pairs = 0

    for bar in observed:
        completed_at = bar.timestamp + H1

        assert completed_at <= trade.exit_at

        # У момент штатного виходу нове рішення не створюємо.
        if completed_at >= trade.exit_at:
            continue

        assert completed_at > trade.entry_at

        contiguous = previous_at is not None and bar.timestamp == previous_at + H1

        if contiguous:
            adjacent_pairs += 1
        else:
            # Не порівнюємо close через відсутню H1.
            segment_best = 0.0

        signed = direction * (bar.close - trade.entry_price) / PIP

        assert math.isfinite(signed)

        # Весь segment_best отриманий до поточної H1.
        if (
            event_at is None
            and contiguous
            and segment_best > COST + EPS
            and signed < -EPS
        ):
            event_at = completed_at
            prior_best = segment_best
            event_close = signed

        if signed > COST + EPS:
            favorable_seen = True

        segment_best = max(
            segment_best,
            signed,
        )

        previous_at = bar.timestamp
        completed_count += 1

    assert completed_count <= len(observed)

    if event_at is not None:
        assert prior_best is not None
        assert event_close is not None
        assert event_at < trade.exit_at
        assert prior_best > COST + EPS
        assert event_close < -EPS
        assert adjacent_pairs > 0
        assert favorable_seen

    return Observation(
        trade=trade,
        event_at=event_at,
        prior_best_pips=prior_best,
        event_close_pips=event_close,
        completed_before_exit=completed_count,
        adjacent_pairs=adjacent_pairs,
        favorable_seen=favorable_seen,
        missing_h1=missing_h1,
    )


def _synthetic() -> None:
    """Контроль часу, прогалин і переходу BUY/SELL."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    bars = [
        make_bar(
            at,
            1.1000,
            1.1020,
            1.0990,
            1.1010,
        ),
        make_bar(
            at + H1,
            1.1010,
            1.1020,
            1.0990,
            1.0995,
        ),
        make_bar(
            at + 2 * H1,
            1.0995,
            1.1000,
            1.0980,
            1.0990,
        ),
        make_bar(
            at + 3 * H1,
            1.0990,
            1.1000,
            1.0970,
            1.0980,
        ),
        make_bar(
            at + 4 * H1,
            1.0980,
            1.1500,
            1.0500,
            1.1200,
        ),
    ]

    times = [bar.timestamp for bar in bars]

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 4 * H1,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=-20.0,
        holding_bars=4,
        holding_minutes=240,
        exit_reason="ENDING",
        exit_gap=False,
    )

    result = _scan(
        buy,
        bars,
        times,
    )

    assert result.eligible
    assert result.triggered
    assert result.event_at == at + 2 * H1

    assert math.isclose(
        result.prior_best_pips,
        10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        result.event_close_pips,
        -5.0,
        abs_tol=EPS,
    )

    assert result.missing_h1 == 0

    changed = [
        *bars[:4],
        make_bar(
            at + 4 * H1,
            1.0980,
            1.3000,
            1.0100,
            1.2500,
        ),
    ]

    assert result == _scan(
        buy,
        changed,
        times,
    )

    # Прогалина після позитивного close обриває порівняння.
    gap_bars = [
        bars[0],
        bars[2],
        bars[3],
        bars[4],
    ]

    gap_times = [bar.timestamp for bar in gap_bars]

    gap_trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 4 * H1,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=-20.0,
        holding_bars=3,
        holding_minutes=240,
        exit_reason="ENDING",
        exit_gap=False,
    )

    gap_result = _scan(
        gap_trade,
        gap_bars,
        gap_times,
    )

    assert gap_result.missing_h1 == 1
    assert gap_result.favorable_seen
    assert not gap_result.triggered

    # Close одночасно з baseline exit — не сигнал.
    short = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 2 * H1,
        entry_price=1.1000,
        exit_price=1.0995,
        pips=-5.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    short_result = _scan(
        short,
        bars,
        times,
    )

    assert not short_result.triggered
    assert not short_result.eligible

    # Майбутній переможець теж може мати таку подію.
    winner_bars = [
        *bars[:4],
        make_bar(
            at + 4 * H1,
            1.1020,
            1.1030,
            1.1010,
            1.1020,
        ),
    ]

    winner = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 4 * H1,
        entry_price=1.1000,
        exit_price=1.1020,
        pips=20.0,
        holding_bars=4,
        holding_minutes=240,
        exit_reason="ENDING",
        exit_gap=False,
    )

    winner_result = _scan(
        winner,
        winner_bars,
        times,
    )

    assert winner_result.triggered
    assert not winner_result.loss

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
            1.1020,
            1.0980,
            1.1005,
        ),
        make_bar(
            at + 2 * H1,
            1.1005,
            1.1020,
            1.0990,
            1.1010,
        ),
        make_bar(
            at + 3 * H1,
            1.1010,
            1.1030,
            1.1000,
            1.1020,
        ),
        make_bar(
            at + 4 * H1,
            1.1020,
            1.1030,
            1.1010,
            1.1020,
        ),
    ]

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + 4 * H1,
        entry_price=1.1000,
        exit_price=1.1020,
        pips=-20.0,
        holding_bars=4,
        holding_minutes=240,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell_result = _scan(
        sell,
        sell_bars,
        times,
    )

    assert sell_result.event_at == at + 2 * H1

    assert math.isclose(
        sell_result.prior_best_pips,
        10.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        sell_result.event_close_pips,
        -5.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_RUNNING_CLOSE_PEAK_CAUSALITY=OK")
    print("SYNTHETIC_STRICT_PRE_EXIT_EVENT=OK")
    print("SYNTHETIC_H1_GAP_RESETS_PEAK=OK")
    print("SYNTHETIC_FUTURE_BAR_ISOLATION=OK")
    print("SYNTHETIC_EVENT_CAN_PRECEDE_WINNER=OK")
    print("SYNTHETIC_BUY_SELL_DIRECTION=OK")


def _fmt(value: float | None) -> str:
    """Показати число або NA без вигадування значень."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _describe(
    period: str,
    side: str,
    rows: list[Observation],
) -> None:
    """Порівняти однакові baseline-угоди без exit-симуляції."""
    eligible = [row for row in rows if row.eligible]

    ineligible = len(rows) - len(eligible)

    triggered = [row for row in eligible if row.triggered]

    not_triggered = [row for row in eligible if not row.triggered]

    assert len(triggered) + len(not_triggered) == len(eligible)

    total_net = math.fsum(row.net for row in rows)

    missing = sum(row.missing_h1 for row in rows)

    print(
        f"EVENT_COVERAGE|PERIOD={period}|"
        f"SIDE={side}|TOTAL={len(rows)}|"
        f"ELIGIBLE={len(eligible)}|"
        f"INELIGIBLE={ineligible}|"
        f"TRIGGERED={len(triggered)}|"
        f"NOT_TRIGGERED={len(not_triggered)}|"
        f"MISSING_H1_SLOTS={missing}|"
        f"BASE_NET040={total_net:+.2f}"
    )

    for label, cohort in (
        ("TRIGGERED", triggered),
        ("NOT_TRIGGERED", not_triggered),
    ):
        count = len(cohort)

        losses = sum(row.loss for row in cohort)

        rate = 100 * losses / count if count else None

        net = math.fsum(row.net for row in cohort)

        mean = net / count if count else None

        lead_hours = [
            (row.trade.exit_at - row.event_at) / H1
            for row in cohort
            if row.event_at is not None
        ]

        median_lead = statistics.median(lead_hours) if lead_hours else None

        print(
            f"EVENT_GROUP|PERIOD={period}|"
            f"SIDE={side}|GROUP={label}|"
            f"COUNT={count}|LOSSES={losses}|"
            f"NONLOSSES={count - losses}|"
            f"LOSS_RATE_PCT={_fmt(rate)}|"
            f"NET040={net:+.2f}|"
            f"MEAN_NET040={_fmt(mean)}|"
            f"MEDIAN_LEAD_H1={_fmt(median_lead)}"
        )

    loss_triggered = sum(row.loss for row in triggered)

    loss_not = sum(row.loss for row in not_triggered)

    if triggered and not_triggered:
        risk_diff = 100 * (
            loss_triggered / len(triggered) - loss_not / len(not_triggered)
        )
    else:
        risk_diff = None

    print(
        f"EVENT_COMPARISON|PERIOD={period}|"
        f"SIDE={side}|"
        f"RISK_DIFF_PP={_fmt(risk_diff)}|"
        "EXPOSURE_TIME_NOT_MATCHED=True|"
        "CAUSAL_EXIT_VALUE_UNPROVEN=True"
    )

    worst_events = sorted(
        triggered,
        key=lambda row: (
            row.net,
            row.trade.entry_at,
        ),
    )[:3]

    for rank, row in enumerate(
        worst_events,
        start=1,
    ):
        assert row.event_at is not None

        print(
            f"EVENT_EXAMPLE|PERIOD={period}|"
            f"SIDE={side}|RANK={rank}|"
            f"ENTRY={row.trade.entry_at.isoformat()}|"
            f"EVENT={row.event_at.isoformat()}|"
            f"EXIT={row.trade.exit_at.isoformat()}|"
            f"PRIOR_BEST={_fmt(row.prior_best_pips)}|"
            f"EVENT_CLOSE={_fmt(row.event_close_pips)}|"
            f"BASE_NET040={row.net:+.2f}|"
            f"LOSS={row.loss}"
        )

    print(f"EVENT_PARTITION_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Перевірити всі чотири періоди на незмінному baseline."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: dict[str, list[Observation]] = {
        BUY: [],
        SELL: [],
    }

    for window in windows:
        bars = history[window.name]

        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(window.entries) == expected_count
        assert window.open_end == open_end

        rows = [
            _scan(
                item.trade,
                bars,
                times,
            )
            for item in window.entries
        ]

        actual_net = math.fsum(row.net for row in rows)

        assert math.isclose(
            actual_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE_MATCH={window.name}:OK|"
            f"CLOSED={len(rows)}|"
            f"NET040={actual_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            side_rows = [row for row in rows if row.trade.direction == side]

            _describe(
                window.name,
                side,
                side_rows,
            )

            pooled[side].extend(side_rows)

        print(f"PERIOD_TRANSITION_RECONCILIATION=" f"{window.name}:OK")

    all_rows = pooled[BUY] + pooled[SELL]

    assert len(all_rows) == 333

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

    print("FOUR_PERIOD_TRANSITION_RECONCILIATION=OK")
    print("HISTORICAL_PEAK_LOOKAHEAD=False")
    print("EVENT_BEFORE_BASELINE_EXIT=True")
    print("EARLY_EXIT_SIMULATED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Виконати причинний аудит без змін production."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_39_Observed_H1_Close_Coverage_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-40|TEST_ONLY|" "H1_CAUSAL_PROFIT_TO_LOSS_TRANSITION_AUDIT")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("RUNNING_PEAK=PAST_COMPLETED_H1_ONLY")
    print("PREVIOUS_PROFIT_GT_COST040=True")
    print("CURRENT_CLOSE_NEGATIVE=True|THRESHOLD_TUNING=False")
    print("GAP_CROSSED_FOR_SIGNAL=False")
    print("SIGNAL_AT_BASELINE_EXIT_ALLOWED=False")

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
    print("T115_40_H1_CAUSAL_PROFIT_TO_LOSS_TRANSITION_AUDIT=OK")


if __name__ == "__main__":
    main()
