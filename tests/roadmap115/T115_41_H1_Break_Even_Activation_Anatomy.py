# -*- coding: utf-8 -*-
"""RoadMap115 / T115-41: H1 break-even activation anatomy.

TEST_ONLY / DATA_ONLY.

Незмінні H1 baseline з T115-32 у чотирьох періодах.

Активація:
- лише завершений H1-close;
- напрямлений прибуток > 0.40 пункту;
- позиція ще відкрита після завершення H1.

Після активації перевіряється фактичний H1 OHLC-діапазон.
Це лише можливий контакт ціни з умовним рівнем BE.

Реальні Bid/Ask, slippage, stop fill і broker order
не моделюються. Прогалини не заповнюються.

Жодних нових торгових правил або production-змін.
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

NOT_ACTIVATED = "NOT_ACTIVATED"
RANGE_TOUCH = "OBSERVED_MID_RANGE_TOUCH"
UNKNOWN_GAP = "UNKNOWN_WITH_H1_GAP"
NO_TOUCH = "NO_OBSERVED_MID_RANGE_TOUCH"

EXPECTED = audit_mod.EXPECTED

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(loss_mod, "_history")


@dataclass(frozen=True, slots=True)
class BEObservation:
    """Активація BE та майбутнє спостереження OHLC."""

    trade: ClosedTrade
    activation_at: datetime | None
    activation_pips: float | None
    touch_bar_at: datetime | None
    observed_after: int
    missing_after: int

    @property
    def activated(self) -> bool:
        return self.activation_at is not None

    @property
    def status(self) -> str:
        if not self.activated:
            return NOT_ACTIVATED

        if self.touch_bar_at is not None:
            return RANGE_TOUCH

        if self.missing_after > 0:
            return UNKNOWN_GAP

        return NO_TOUCH

    @property
    def net(self) -> float:
        return float(self.trade.pips) - COST

    @property
    def loss(self) -> bool:
        return self.net < -EPS


def _sha(path: Path) -> str:
    """Обчислити SHA256 для контролю незмінності."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _scan(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
) -> BEObservation:
    """Визначити причинну активацію та спостережений контакт."""
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
    total_hours = duration // H1

    assert duration == total_hours * H1
    assert total_hours >= len(observed)

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

    activation_at: datetime | None = None
    activation_pips: float | None = None

    for bar in observed:
        completed_at = bar.timestamp + H1

        assert completed_at <= trade.exit_at

        # Одночасно з baseline exit стоп уже не активуємо.
        if completed_at >= trade.exit_at:
            continue

        signed_close = direction * (bar.close - trade.entry_price) / PIP

        assert math.isfinite(signed_close)

        if signed_close > COST + EPS:
            activation_at = completed_at
            activation_pips = signed_close
            break

    if activation_at is None:
        return BEObservation(
            trade=trade,
            activation_at=None,
            activation_pips=None,
            touch_bar_at=None,
            observed_after=0,
            missing_after=0,
        )

    assert activation_pips is not None
    assert activation_at < trade.exit_at

    # Ціна умовного нульового Net у mid-price моделі.
    be_mid_price = trade.entry_price + direction * COST * PIP

    post_bars = [
        bar for bar in observed if activation_at <= bar.timestamp < trade.exit_at
    ]

    expected_after = (trade.exit_at - activation_at) // H1

    assert trade.exit_at - activation_at == expected_after * H1

    assert len(post_bars) <= expected_after

    missing_after = expected_after - len(post_bars)

    touch_bar_at: datetime | None = None

    for bar in post_bars:
        if trade.direction == BUY:
            touches = bar.low <= be_mid_price + EPS * PIP
        else:
            touches = bar.high >= be_mid_price - EPS * PIP

        if touches:
            touch_bar_at = bar.timestamp
            break

    if touch_bar_at is not None:
        assert touch_bar_at >= activation_at
        assert touch_bar_at < trade.exit_at

    return BEObservation(
        trade=trade,
        activation_at=activation_at,
        activation_pips=activation_pips,
        touch_bar_at=touch_bar_at,
        observed_after=len(post_bars),
        missing_after=missing_after,
    )


def _synthetic() -> None:
    """Перевірити час активації, контакт і прогалини."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    bars = [
        make_bar(
            at,
            1.1000,
            1.1015,
            1.0990,
            1.1010,
        ),
        make_bar(
            at + H1,
            1.1010,
            1.1020,
            1.0995,
            1.1015,
        ),
        make_bar(
            at + 2 * H1,
            1.1015,
            1.1020,
            1.1010,
            1.1020,
        ),
        make_bar(
            at + 3 * H1,
            1.1020,
            1.1500,
            1.0500,
            1.1200,
        ),
    ]

    times = [bar.timestamp for bar in bars]

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.1020,
        pips=20.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    result = _scan(
        buy,
        bars,
        times,
    )

    assert result.activated
    assert result.activation_at == at + H1
    assert result.touch_bar_at == at + H1
    assert result.status == RANGE_TOUCH
    assert result.missing_after == 0
    assert not result.loss

    assert math.isclose(
        result.activation_pips,
        10.0,
        abs_tol=EPS,
    )

    # Зміна свічки після baseline exit нічого не змінює.
    changed = [
        *bars[:3],
        make_bar(
            at + 3 * H1,
            1.1020,
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

    # Якщо після активації діапазон не торкався BE.
    no_touch_bars = [
        bars[0],
        make_bar(
            at + H1,
            1.1010,
            1.1020,
            1.1008,
            1.1015,
        ),
        bars[2],
        bars[3],
    ]

    no_touch = _scan(
        buy,
        no_touch_bars,
        times,
    )

    assert no_touch.status == NO_TOUCH
    assert no_touch.missing_after == 0

    # Якщо H1 відсутня, не можна заявляти NO_TOUCH.
    sparse_bars = [
        bars[0],
        bars[2],
        bars[3],
    ]

    sparse_times = [bar.timestamp for bar in sparse_bars]

    sparse_buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.1020,
        pips=20.0,
        holding_bars=2,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sparse_result = _scan(
        sparse_buy,
        sparse_bars,
        sparse_times,
    )

    assert sparse_result.activated
    assert sparse_result.missing_after == 1
    assert sparse_result.status == UNKNOWN_GAP

    # Завершення першої H1 одночасно з exit не активує BE.
    short = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + H1,
        entry_price=1.1000,
        exit_price=1.1010,
        pips=10.0,
        holding_bars=1,
        holding_minutes=60,
        exit_reason="ENDING",
        exit_gap=False,
    )

    short_result = _scan(
        short,
        bars,
        times,
    )

    assert short_result.status == NOT_ACTIVATED

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
            1.1005,
            1.0970,
            1.0985,
        ),
        make_bar(
            at + 2 * H1,
            1.0985,
            1.0990,
            1.0975,
            1.0980,
        ),
        make_bar(
            at + 3 * H1,
            1.0980,
            1.1000,
            1.0970,
            1.0980,
        ),
    ]

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + 3 * H1,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=20.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell_result = _scan(
        sell,
        sell_bars,
        times,
    )

    assert sell_result.activated
    assert sell_result.activation_at == at + H1
    assert sell_result.touch_bar_at == at + H1
    assert sell_result.status == RANGE_TOUCH

    print("SYNTHETIC_COMPLETED_H1_BE_ACTIVATION=OK")
    print("SYNTHETIC_STRICT_PRE_EXIT_ACTIVATION=OK")
    print("SYNTHETIC_POST_ACTIVATION_RANGE_ONLY=OK")
    print("SYNTHETIC_H1_GAP_UNKNOWN_CLASSIFICATION=OK")
    print("SYNTHETIC_FUTURE_BAR_ISOLATION=OK")
    print("SYNTHETIC_WINNER_CAN_TOUCH_BE=OK")
    print("SYNTHETIC_BUY_SELL_DIRECTION=OK")


def _fmt(value: float | None) -> str:
    """Форматувати відсутнє значення як NA."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _describe(
    period: str,
    side: str,
    rows: list[BEObservation],
) -> None:
    """Зіставити активацію BE з незмінним baseline."""
    activated = [row for row in rows if row.activated]

    inactive = [row for row in rows if not row.activated]

    assert len(activated) + len(inactive) == len(rows)

    baseline_net = math.fsum(row.net for row in rows)

    activation_pips = [
        row.activation_pips for row in activated if row.activation_pips is not None
    ]

    activation_median = statistics.median(activation_pips) if activation_pips else None

    activation_delay = [
        (row.activation_at - row.trade.entry_at) / H1
        for row in activated
        if row.activation_at is not None
    ]

    delay_median = statistics.median(activation_delay) if activation_delay else None

    print(
        f"BE_COVERAGE|PERIOD={period}|"
        f"SIDE={side}|TOTAL={len(rows)}|"
        f"ACTIVATED={len(activated)}|"
        f"NOT_ACTIVATED={len(inactive)}|"
        f"MEDIAN_ACTIVATION_PIPS="
        f"{_fmt(activation_median)}|"
        f"MEDIAN_ACTIVATION_H1={_fmt(delay_median)}|"
        f"BASE_NET040={baseline_net:+.2f}"
    )

    for status in (
        NOT_ACTIVATED,
        RANGE_TOUCH,
        UNKNOWN_GAP,
        NO_TOUCH,
    ):
        selected = [row for row in rows if row.status == status]

        losses = sum(row.loss for row in selected)

        net = math.fsum(row.net for row in selected)

        print(
            f"BE_GROUP|PERIOD={period}|SIDE={side}|"
            f"STATUS={status}|"
            f"COUNT={len(selected)}|"
            f"BASE_LOSS={losses}|"
            f"BASE_NONLOSS={len(selected) - losses}|"
            f"BASE_NET040={net:+.2f}"
        )

    touched = [row for row in activated if row.status == RANGE_TOUCH]

    touch_losers = sum(row.loss for row in touched)

    touch_winners = len(touched) - touch_losers

    missing_post = sum(row.missing_after for row in activated)

    print(
        f"BE_TRADEOFF|PERIOD={period}|"
        f"SIDE={side}|"
        f"OBSERVED_TOUCH_LOSS={touch_losers}|"
        f"OBSERVED_TOUCH_NONLOSS={touch_winners}|"
        f"POST_ACTIVATION_MISSING_H1={missing_post}|"
        "REAL_STOP_FILL_UNKNOWN=True"
    )

    print(f"BE_PARTITION_RECONCILIATION=" f"{period}:{side}:OK")


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Дослідити всі чотири періоди на frozen baseline."""
    assert len(windows) == 4
    assert len(history) == 4

    pooled: dict[str, list[BEObservation]] = {
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
            f"CLOSED={expected_count}|"
            f"NET040={actual_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            selected = [row for row in rows if row.trade.direction == side]

            _describe(
                window.name,
                side,
                selected,
            )

            pooled[side].extend(selected)

        print(f"PERIOD_BE_RECONCILIATION={window.name}:OK")

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

    print("FOUR_PERIOD_BE_ACTIVATION_RECONCILIATION=OK")
    print("BE_ACTIVATION_CAUSAL=True")
    print("H1_RANGE_TOUCH_IS_OUTCOME_LABEL=True")
    print("REAL_BE_STOP_FILL_SIMULATED=False")
    print("POSITION_OCCUPANCY_REPLAYED=False")
    print("NEW_TRADING_RULE_CREATED=False")


def main() -> None:
    """Виконати BE-аудит без змін production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/"
        "T115_40_H1_Causal_Profit_To_Loss_Transition_Audit.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-41|TEST_ONLY|" "H1_BREAK_EVEN_ACTIVATION_ANATOMY")

    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("ACTIVATION=COMPLETED_H1_CLOSE_GT_COST040")
    print("BE_LEVEL=ENTRY_PLUS_DIRECTIONAL_COST040_MID")
    print("AFTER_ACTIVATION_H1_OHLC=OBSERVATION_ONLY")
    print("SPREAD_SLIPPAGE_BROKER_STOPS=NOT_MODELLED")
    print("THRESHOLD_OPTIMIZATION=False")

    _synthetic()

    windows = load_windows()
    history = load_history()

    _report(
        windows,
        history,
    )

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("future_ranges_used_only_as_outcome_labels=True")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_41_H1_BREAK_EVEN_ACTIVATION_ANATOMY=OK")


if __name__ == "__main__":
    main()
