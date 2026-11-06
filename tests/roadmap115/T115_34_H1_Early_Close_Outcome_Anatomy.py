# -*- coding: utf-8 -*-
"""RoadMap115 / T115-34: H1 early-close outcome anatomy.

TEST_ONLY. Незмінний baseline чотирьох періодів T115-32.
Перевіряються close після 1 та 3 завершених H1 від входу.

Між entry і вимірюванням потрібні суцільні H1 без прогалин.
Майбутній результат угоди є лише міткою для дослідження.
Нових entry/exit, SL/TP та оптимізації немає.
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

COST = loss_mod.COST
PIP = 0.0001
EPS = 1e-6

H1_SPAN = timedelta(hours=1)
HORIZONS = (1, 3)

GROUPS = (
    "TOP3_LOSS",
    "OTHER_LOSS",
    "NONLOSS",
)

EXPECTED = audit_mod.EXPECTED

load_windows = getattr(audit_mod, "_load_windows")
load_history = getattr(loss_mod, "_history")


@dataclass(frozen=True, slots=True)
class Observation:
    """Рух close, доступний після завершення відповідної H1."""

    item: EntryState
    close_1: float | None
    close_3: float | None


def _sha(path: Path) -> str:
    """Контроль незмінності production та опорного тесту."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _net(trade: ClosedTrade) -> float:
    """Умовний Net угоди після витрат 0.40 пункту."""
    return float(trade.pips) - COST


def _early_close(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
    horizon: int,
) -> float | None:
    """Рух close від entry після N завершених суцільних H1."""
    assert horizon in HORIZONS
    assert len(bars) == len(times)
    assert trade.entry_at < trade.exit_at

    available_at = trade.entry_at + horizon * H1_SPAN

    if available_at > trade.exit_at:
        return None

    left = bisect.bisect_left(
        times,
        trade.entry_at,
    )

    assert left < len(times)
    assert times[left] == trade.entry_at

    last_index = left + horizon - 1

    if last_index >= len(bars):
        return None

    for offset in range(horizon):
        expected_at = trade.entry_at + offset * H1_SPAN

        if times[left + offset] != expected_at:
            return None

    price = bars[last_index].close

    if trade.direction == BUY:
        signed_pips = (price - trade.entry_price) / PIP
    else:
        assert trade.direction == SELL

        signed_pips = (trade.entry_price - price) / PIP

    assert math.isfinite(signed_pips)

    return signed_pips


def _synthetic() -> None:
    """Перевірити напрямок, завершеність і відсутність look-ahead."""
    at = datetime(2025, 4, 7, 12, tzinfo=UTC)

    bars = [
        make_bar(
            at,
            1.1000,
            1.1010,
            1.0970,
            1.0990,
        ),
        make_bar(
            at + H1_SPAN,
            1.0990,
            1.1020,
            1.0960,
            1.1010,
        ),
        make_bar(
            at + 2 * H1_SPAN,
            1.1010,
            1.1020,
            1.0950,
            1.0980,
        ),
        make_bar(
            at + 3 * H1_SPAN,
            1.0980,
            1.2000,
            1.0500,
            1.1500,
        ),
    ]

    times = [bar.timestamp for bar in bars]

    buy = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 3 * H1_SPAN,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=-20.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    sell = make_trade(
        direction=SELL,
        entry_at=at,
        exit_at=at + 3 * H1_SPAN,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=20.0,
        holding_bars=3,
        holding_minutes=180,
        exit_reason="ENDING",
        exit_gap=False,
    )

    buy_1 = _early_close(buy, bars, times, 1)
    buy_3 = _early_close(buy, bars, times, 3)

    sell_1 = _early_close(sell, bars, times, 1)
    sell_3 = _early_close(sell, bars, times, 3)

    assert buy_1 is not None
    assert buy_3 is not None
    assert sell_1 is not None
    assert sell_3 is not None

    assert math.isclose(buy_1, -10.0, abs_tol=EPS)
    assert math.isclose(buy_3, -20.0, abs_tol=EPS)
    assert math.isclose(sell_1, 10.0, abs_tol=EPS)
    assert math.isclose(sell_3, 20.0, abs_tol=EPS)

    # Зміна даних після exit не впливає на вимірювання.
    future_changed = bars[:3] + [
        make_bar(
            at + 3 * H1_SPAN,
            1.0980,
            1.3000,
            1.0100,
            1.2500,
        )
    ]

    assert buy_3 == _early_close(
        buy,
        future_changed,
        times,
        3,
    )

    # Пропущена H1 забороняє 3-барне вимірювання.
    gap_bars = [
        bars[0],
        bars[2],
        bars[3],
    ]

    gap_times = [bar.timestamp for bar in gap_bars]

    assert _early_close(buy, gap_bars, gap_times, 1) == buy_1

    assert _early_close(buy, gap_bars, gap_times, 3) is None

    short_trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + H1_SPAN,
        entry_price=1.1000,
        exit_price=1.0990,
        pips=-10.0,
        holding_bars=1,
        holding_minutes=60,
        exit_reason="ENDING",
        exit_gap=False,
    )

    assert _early_close(short_trade, bars, times, 3) is None

    print("SYNTHETIC_COMPLETED_H1_CLOSE_CAUSALITY=OK")
    print("SYNTHETIC_BUY_SELL_SIGN_SYMMETRY=OK")
    print("SYNTHETIC_FUTURE_BAR_ISOLATION=OK")
    print("SYNTHETIC_H1_GAP_EXCLUSION=OK")
    print("SYNTHETIC_SHORT_HOLD_EXCLUSION=OK")


def _fmt(value: float | None) -> str:
    """Форматувати наявне або відсутнє спостереження."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _observations(
    entries: list[EntryState],
    bars: list[Bar],
    times: list[datetime],
) -> list[Observation]:
    """Виміряти перші H1 без використання майбутніх сигналів."""
    result: list[Observation] = []

    for item in entries:
        trade = item.trade

        close_1 = _early_close(trade, bars, times, 1)

        close_3 = _early_close(trade, bars, times, 3)

        if close_3 is not None:
            assert close_1 is not None

        result.append(
            Observation(
                item=item,
                close_1=close_1,
                close_3=close_3,
            )
        )

    assert len(result) == len(entries)

    return result


def _print_group(
    period: str,
    side: str,
    group: str,
    records: list[Observation],
) -> None:
    """Порівняти ранні close без нового exit-правила."""
    count = len(records)

    for horizon in HORIZONS:
        values = [
            record.close_1 if horizon == 1 else record.close_3 for record in records
        ]

        valid = [value for value in values if value is not None]

        eligible = len(valid)
        excluded = count - eligible

        negative = sum(value < -EPS for value in valid)

        nonnegative = eligible - negative

        median = statistics.median(valid) if valid else None

        average = math.fsum(valid) / eligible if eligible else None

        print(
            f"EARLY_CLOSE|PERIOD={period}|"
            f"SIDE={side}|GROUP={group}|"
            f"H1={horizon}|TOTAL={count}|"
            f"ELIGIBLE={eligible}|EXCLUDED={excluded}|"
            f"NEGATIVE={negative}|"
            f"NONNEGATIVE={nonnegative}|"
            f"MEDIAN_PIPS={_fmt(median)}|"
            f"MEAN_PIPS={_fmt(average)}"
        )

    pairs = [record for record in records if record.close_3 is not None]

    assert all(record.close_1 is not None for record in pairs)

    worsening = sum(record.close_3 < record.close_1 - EPS for record in pairs)

    improving = sum(record.close_3 > record.close_1 + EPS for record in pairs)

    unchanged = len(pairs) - worsening - improving

    print(
        f"EARLY_CHANGE|PERIOD={period}|"
        f"SIDE={side}|GROUP={group}|"
        f"PAIRED={len(pairs)}|"
        f"WORSENING={worsening}|"
        f"IMPROVING={improving}|"
        f"UNCHANGED={unchanged}"
    )


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Зіставити великі втрати з іншими baseline-угодами."""
    assert len(windows) == 4
    assert len(history) == 4

    for window in windows:
        bars = history[window.name]

        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        expected_count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(window.entries) == expected_count
        assert window.open_end == open_end

        baseline_net = math.fsum(_net(item.trade) for item in window.entries)

        assert math.isclose(
            baseline_net,
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"BASELINE|PERIOD={window.name}|"
            f"CLOSED={expected_count}|"
            f"NET040={baseline_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            entries = [item for item in window.entries if item.trade.direction == side]

            losses = sorted(
                [item for item in entries if _net(item.trade) < -EPS],
                key=lambda item: (
                    _net(item.trade),
                    item.trade.entry_at,
                ),
            )

            worst = losses[:3]

            worst_times = {item.trade.entry_at for item in worst}

            groups: dict[str, list[EntryState]] = {name: [] for name in GROUPS}

            for item in entries:
                if item.trade.entry_at in worst_times:
                    group = "TOP3_LOSS"
                elif _net(item.trade) < -EPS:
                    group = "OTHER_LOSS"
                else:
                    group = "NONLOSS"

                groups[group].append(item)

            assert sum(len(items) for items in groups.values()) == len(entries)

            group_net = math.fsum(
                _net(item.trade) for items in groups.values() for item in items
            )

            side_net = math.fsum(_net(item.trade) for item in entries)

            assert math.isclose(
                group_net,
                side_net,
                abs_tol=EPS,
            )

            print(
                f"SIDE|PERIOD={window.name}|"
                f"SIDE={side}|CLOSED={len(entries)}|"
                f"NET040={side_net:+.2f}|"
                f"LOSSES={len(losses)}"
            )

            for group in GROUPS:
                records = _observations(
                    groups[group],
                    bars,
                    times,
                )

                _print_group(
                    window.name,
                    side,
                    group,
                    records,
                )

                if group == "TOP3_LOSS":
                    for rank, record in enumerate(
                        records,
                        start=1,
                    ):
                        trade = record.item.trade

                        print(
                            f"TOP3_EARLY|PERIOD={window.name}|"
                            f"SIDE={side}|RANK={rank}|"
                            f"ENTRY={trade.entry_at.isoformat()}|"
                            f"NET040={_net(trade):+.2f}|"
                            f"CLOSE_H1={_fmt(record.close_1)}|"
                            f"CLOSE_H3={_fmt(record.close_3)}"
                        )

            print(f"SIDE_EARLY_CLOSE_RECONCILIATION=" f"{window.name}:{side}:OK")

        print(f"PERIOD_EARLY_CLOSE_RECONCILIATION=" f"{window.name}:OK")

    print("FOUR_PERIOD_EARLY_CLOSE_RECONCILIATION=OK")
    print("NO_NEW_ENTRY_OR_EXIT_RULE=True")
    print("OUTCOME_LABELS_ARE_NOT_ENTRY_INFORMATION=True")


def main() -> None:
    """Дослідити ранній рух без змін production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_33_H1_Large_Loss_Anatomy.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-34|TEST_ONLY|H1_EARLY_CLOSE_OUTCOME_ANATOMY")
    print("BASELINE=UNCHANGED_T115_32|WINDOWS=4")
    print("HORIZONS=1,3_COMPLETED_CONTIGUOUS_H1")
    print("GROUPS=TOP3_LOSS,OTHER_LOSS,NONLOSS")
    print("COST040_HYPOTHETICAL=True|PARAMETER_SEARCH=False")

    _synthetic()

    windows = load_windows()
    history = load_history()

    _report(windows, history)

    assert before == [_sha(path) for path in guarded]

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("outcome_labels_use_future=True|future_used_for_entry=False")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_34_H1_EARLY_CLOSE_OUTCOME_ANATOMY=OK")


if __name__ == "__main__":
    main()
