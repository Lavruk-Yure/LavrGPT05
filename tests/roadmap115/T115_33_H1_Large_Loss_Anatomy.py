# -*- coding: utf-8 -*-
"""RoadMap115 / T115-33: H1 large-loss factual anatomy.

TEST_ONLY. Чотири незмінні вікна baseline з T115-32.
Лише завершені H1, без нових фільтрів, SL/TP та оптимізації.

PRE3 — рух від open трьох попередніх H1 до entry open.
MAE/MFE — outcome label лише ПІСЛЯ закриття угоди.
Екстремуми вимірюються за OHLC H1 протягом позиції.
Порядок high/low усередині H1 невідомий і не виводиться.
"""

from __future__ import annotations

import bisect
import hashlib
import math
import sys
from collections import Counter
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
tf_mod = import_module("T115_15_Extended_Timeframe_Plateau_Audit")

pre_mod = import_module("T115_31_Frozen_SELL_Gate_Pre_2025_Backward_Replay")

hold_mod = import_module("T115_30_Frozen_SELL_Gate_Holdout_Replay")

audit_mod = import_module("T115_32_Cross_Period_M15_Entry_State_Audit")

make_bar = entry_mod.Bar
make_trade = exit_mod.ClosedTrade

BUY = exit_mod.DIRECTION_UP
SELL = exit_mod.DIRECTION_DOWN

H1_MIN = 60
H1_SPAN = timedelta(hours=1)
PIP = 0.0001
COST = tf_mod.NET_COST_PIPS

TOP_N = 3
EPS = 1e-6

EXPECTED = audit_mod.EXPECTED

# Доступ до тестових допоміжних функцій без E402 і protected access.
load_2024 = getattr(pre_mod, "_load")
load_holdout = getattr(hold_mod, "_load_holdout")
aggregate_all = getattr(tf_mod, "_aggregate_all")
load_windows = getattr(audit_mod, "_load_windows")


@dataclass(frozen=True, slots=True)
class Excursion:
    """Післяугодний діапазон без припущення intrabar-порядку."""

    pre3_pips: float | None
    mae_pips: float
    mfe_pips: float
    giveback_pips: float
    observed_h1: int
    missing_h1_intervals: int


def _sha(path: Path) -> str:
    """Контроль SHA256 файлу без завантаження в пам'ять."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1048576),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _net(trade: ClosedTrade) -> float:
    """Умовний Net завершеної угоди."""
    return float(trade.pips) - COST


def _measure(
    trade: ClosedTrade,
    bars: list[Bar],
    times: list[datetime],
) -> Excursion:
    """Виміряти MAE/MFE між entry open і exit open."""
    assert trade.entry_at < trade.exit_at
    assert len(times) == len(bars)

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

    observed = [bars[index] for index in range(left, right)]

    assert len(observed) == trade.holding_bars

    assert all(trade.entry_at <= bar.timestamp < trade.exit_at for bar in observed)

    points = [
        trade.entry_price,
        trade.exit_price,
    ]

    highs = points + [bar.high for bar in observed]

    lows = points + [bar.low for bar in observed]

    if trade.direction == BUY:
        mfe = (max(highs) - trade.entry_price) / PIP

        mae = (trade.entry_price - min(lows)) / PIP

        pre_sign = 1

    else:
        assert trade.direction == SELL

        mfe = (trade.entry_price - min(lows)) / PIP

        mae = (max(highs) - trade.entry_price) / PIP

        pre_sign = -1

    pre3: float | None = None

    if left >= 3:
        previous = [bars[index] for index in range(left - 3, left)]

        expected_times = [
            trade.entry_at - 3 * H1_SPAN,
            trade.entry_at - 2 * H1_SPAN,
            trade.entry_at - H1_SPAN,
        ]

        actual_times = [bar.timestamp for bar in previous]

        if actual_times == expected_times:
            pre3 = pre_sign * (trade.entry_price - previous[0].open) / PIP

    gap_count = sum(
        later.timestamp != earlier.timestamp + H1_SPAN
        for earlier, later in zip(
            observed,
            observed[1:],
        )
    )

    gap_count += int(trade.exit_at != observed[-1].timestamp + H1_SPAN)

    if trade.direction == BUY:
        gross = (trade.exit_price - trade.entry_price) / PIP
    else:
        gross = (trade.entry_price - trade.exit_price) / PIP

    assert math.isclose(
        gross,
        trade.pips,
        abs_tol=EPS,
    )

    assert mae >= -EPS
    assert mfe >= -EPS

    assert mae + EPS >= max(
        0.0,
        -gross,
    )

    assert mfe + EPS >= max(
        0.0,
        gross,
    )

    return Excursion(
        pre3_pips=pre3,
        mae_pips=max(0.0, mae),
        mfe_pips=max(0.0, mfe),
        giveback_pips=max(0.0, mfe - gross),
        observed_h1=len(observed),
        missing_h1_intervals=gap_count,
    )


def _synthetic() -> None:
    """Контроль causal PRE3 і межі післяугодних вимірювань."""
    at = datetime(
        2025,
        4,
        7,
        12,
        tzinfo=UTC,
    )

    bars = [
        make_bar(
            at - 3 * H1_SPAN,
            1.0960,
            1.0965,
            1.0955,
            1.0960,
        ),
        make_bar(
            at - 2 * H1_SPAN,
            1.0970,
            1.0975,
            1.0965,
            1.0970,
        ),
        make_bar(
            at - H1_SPAN,
            1.0980,
            1.0985,
            1.0975,
            1.0980,
        ),
        make_bar(
            at,
            1.1000,
            1.1020,
            1.0990,
            1.1010,
        ),
        make_bar(
            at + H1_SPAN,
            1.1010,
            1.1015,
            1.0970,
            1.0980,
        ),
        make_bar(
            at + 2 * H1_SPAN,
            1.0980,
            1.1500,
            1.0500,
            1.1000,
        ),
        make_bar(
            at + 3 * H1_SPAN,
            1.1000,
            1.2000,
            1.0000,
            1.1000,
        ),
    ]

    times = [bar.timestamp for bar in bars]

    trade = make_trade(
        direction=BUY,
        entry_at=at,
        exit_at=at + 2 * H1_SPAN,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=-20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    measured = _measure(
        trade,
        bars,
        times,
    )

    assert math.isclose(
        measured.pre3_pips,
        40.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        measured.mfe_pips,
        20.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        measured.mae_pips,
        30.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        measured.giveback_pips,
        40.0,
        abs_tol=EPS,
    )

    assert measured.missing_h1_intervals == 0

    shortened_bars = [bars[index] for index in range(len(bars) - 1)]

    shortened_times = [bar.timestamp for bar in shortened_bars]

    assert measured == _measure(
        trade,
        shortened_bars,
        shortened_times,
    )

    sell = make_trade(
        direction=SELL,
        entry_at=trade.entry_at,
        exit_at=trade.exit_at,
        entry_price=1.1000,
        exit_price=1.0980,
        pips=20.0,
        holding_bars=2,
        holding_minutes=120,
        exit_reason="ENDING",
        exit_gap=False,
    )

    short = _measure(
        sell,
        bars,
        times,
    )

    assert math.isclose(
        short.mae_pips,
        20.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        short.mfe_pips,
        30.0,
        abs_tol=EPS,
    )

    assert math.isclose(
        short.pre3_pips,
        -40.0,
        abs_tol=EPS,
    )

    print("SYNTHETIC_PRE_ENTRY_H1_CAUSALITY=OK")
    print("SYNTHETIC_MAE_MFE_OUTCOME_BOUNDARY=OK")
    print("SYNTHETIC_BUY_SELL_SYMMETRY=OK")


def _history() -> dict[str, list[Bar]]:
    """Використати ті самі complete H1, що й у T115-32."""
    history: dict[str, list[Bar]] = {
        "2024_NOV_DEC": load_2024().h1,
    }

    for label, filename, *_ in entry_mod.PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename

        cutoff = entry_mod.CANONICAL_2026_END if label.startswith("2026") else None

        _, _, aggregated = aggregate_all(
            path,
            int(label[:4]),
            cutoff,
        )

        history[label] = aggregated[H1_MIN]

    history["2026_AUG_OCT"] = load_holdout().h1

    assert list(history) == list(EXPECTED)
    assert all(history.values())

    return history


def _fmt(value: float | None) -> str:
    """Форматування необов'язкового числового поля."""
    if value is None:
        return "NA"

    return f"{value:+.2f}"


def _report(
    windows: list[Window],
    history: dict[str, list[Bar]],
) -> None:
    """Три найбільші втрати для кожного напрямку та періоду."""
    assert len(windows) == 4

    for window in windows:
        bars = history[window.name]

        times = [bar.timestamp for bar in bars]

        assert times == sorted(set(times))

        entries = window.entries

        trades = [item.trade for item in entries]

        count, expected_net, _, open_end = EXPECTED[window.name]

        assert len(trades) == count
        assert window.open_end == open_end

        assert math.isclose(
            math.fsum(_net(trade) for trade in trades),
            expected_net,
            abs_tol=EPS,
        )

        print(
            f"PERIOD|ID={window.name}|"
            f"CLOSED={count}|"
            f"NET040={expected_net:+.2f}|"
            f"OPEN_END={open_end}"
        )

        for side in (BUY, SELL):
            selected = [entry for entry in entries if entry.trade.direction == side]

            side_net = math.fsum(_net(entry.trade) for entry in selected)

            losses = [entry for entry in selected if _net(entry.trade) < -EPS]

            ordered = sorted(
                losses,
                key=lambda entry: (
                    _net(entry.trade),
                    entry.trade.entry_at,
                ),
            )

            worst = ordered[:TOP_N]

            loss_total = -math.fsum(_net(entry.trade) for entry in losses)

            worst_total = -math.fsum(_net(entry.trade) for entry in worst)

            concentration = 100 * worst_total / loss_total if loss_total > EPS else 0.0

            assert worst_total <= loss_total + EPS

            print(
                f"LOSS_SIDE|PERIOD={window.name}|"
                f"SIDE={side}|"
                f"CLOSED={len(selected)}|"
                f"LOSSES={len(losses)}|"
                f"SIDE_NET040={side_net:+.2f}|"
                f"LOSS_MAGNITUDE={loss_total:.2f}|"
                f"WORST3_LOSS={worst_total:.2f}|"
                f"WORST3_SHARE_PCT={concentration:.2f}"
            )

            exit_reasons: Counter[str] = Counter()
            m15_classes: Counter[str] = Counter()

            favorable = 0
            with_gaps = 0

            for rank, item in enumerate(
                worst,
                start=1,
            ):
                trade = item.trade

                metric = _measure(
                    trade,
                    bars,
                    times,
                )

                exit_reasons[trade.exit_reason] += 1
                m15_classes[item.strict_class] += 1

                favorable += int(metric.mfe_pips > COST + EPS)

                with_gaps += int(metric.missing_h1_intervals > 0)

                assert (
                    item.strict_state is None or item.strict_state.at < trade.entry_at
                )

                print(
                    f"LOSS_TRADE|PERIOD={window.name}|"
                    f"SIDE={side}|RANK={rank}|"
                    f"ENTRY={trade.entry_at.isoformat()}|"
                    f"EXIT={trade.exit_at.isoformat()}|"
                    f"NET040={_net(trade):+.2f}|"
                    f"M15={item.strict_class}|"
                    f"PRE3={_fmt(metric.pre3_pips)}|"
                    f"MAE={metric.mae_pips:.2f}|"
                    f"MFE={metric.mfe_pips:.2f}|"
                    f"GIVEBACK={metric.giveback_pips:.2f}|"
                    f"HOLD_MIN={trade.holding_minutes}|"
                    f"OBS_H1={metric.observed_h1}|"
                    f"GAPS={metric.missing_h1_intervals}|"
                    f"EXIT_REASON={trade.exit_reason}|"
                    f"EXIT_GAP={trade.exit_gap}"
                )

            reasons = (
                ",".join(
                    f"{name}:{count}" for name, count in sorted(exit_reasons.items())
                )
                or "NONE"
            )

            states = (
                ",".join(
                    f"{name}:{count}" for name, count in sorted(m15_classes.items())
                )
                or "NONE"
            )

            print(
                f"LOSS_SUMMARY|PERIOD={window.name}|"
                f"SIDE={side}|"
                f"TOP={len(worst)}|"
                f"EXIT_REASONS={reasons}|"
                f"M15_STATES={states}|"
                f"MFE_GT_COST={favorable}|"
                f"WITH_H1_GAPS={with_gaps}|"
                "CAUSAL_ATTRIBUTION=False"
            )

        print(f"PERIOD_LARGE_LOSS_RECONCILIATION=" f"{window.name}:OK")

    print("FOUR_PERIOD_LARGE_LOSS_RECONCILIATION=OK")
    print("NO_NEW_GATE_OR_EXIT_RULE=True")


def main() -> None:
    """Виконати аудит без зміни production та MD7."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
        ROOT / "tests/roadmap115/" "T115_27_H1_SELL_M15_Causal_Entry_Gate_Replay.py",
    )

    assert all(path.is_file() for path in guarded)

    before = [_sha(path) for path in guarded]

    print("T115-33|TEST_ONLY|H1_LARGE_LOSS_ANATOMY")
    print("BASELINE=T115_32_FROZEN_H1_HYBRID|WINDOWS=4")
    print("TOP3_PER_PERIOD_AND_SIDE=True|COST040_HYPOTHETICAL=True")
    print("PRE3=CAUSAL_ENTRY_CONTEXT|MAE_MFE=POST_TRADE_LABELS")

    _synthetic()

    windows = load_windows()
    history = _history()

    _report(
        windows,
        history,
    )

    after = [_sha(path) for path in guarded]

    assert before == after

    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("outcome_labels_use_future=True|future_used_for_entry=False")
    print("broker_requests=0|TEST_ONLY=True|DATA_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_33_H1_LARGE_LOSS_ANATOMY=OK")


if __name__ == "__main__":
    main()
