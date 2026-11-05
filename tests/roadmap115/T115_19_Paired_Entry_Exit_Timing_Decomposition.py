# -*- coding: utf-8 -*-
"""RoadMap115 / T115-19 — paired entry/exit price decomposition.

TEST_ONLY. Перевіряємо M30 (4→2 bars) і H1 (4→1 bar), 2025/2026.

Спільний episode визначається causal regime/state із T115-18.
Для ДВОХ закритих позицій того самого напрямку зміна Net точно
дорівнює зміні ціни входу плюс зміні ціни виходу. Це арифметична
post-hoc декомпозиція, НЕ доказ причинної переваги early entry.
Для епізоду, де завершилася тільки одна позиція, повна різниця Net
відноситься до EXECUTION_STATUS, а не приписується входу/виходу.
Нереалізовані позиції на cutoff не оцінюються за майбутніми цінами.

Симулятори, правила виходу та профілі — без змін щодо T115-18.
OHLC mid; умовні round-trip витрати 0.40 pip; без broker fills.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    PERIODS,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    ClosedTrade,
    DIRECTION_DOWN,
    DIRECTION_UP,
    PIP,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    TF_NAMES,
    _aggregate_all,
    _summary,
    _synthetic_check,
)
from T115_17_Equal_Clock_Time_Confirmation_Audit import (  # noqa: E402
    _net,
    _regression,
    _synthetic_confirmation,
)
from T115_18_Confirmation_Signal_Attribution import (  # noqa: E402
    EPS,
    EXPECTED_NET,
    TIMEFRAMES,
    Attribution,
    Trace,
    _attribute,
    _run_pair,
    _synthetic_attribution,
    _synthetic_episode_link,
    _trade_lookup,
)


@dataclass(frozen=True, slots=True)
class Decomposition:
    """Взаємовиключні компоненти зміни закритого Net одного episode."""

    episode: int
    direction: str
    signal_class: str
    closed_class: str
    entry_price_part: float
    exit_price_part: float
    status_part: float
    observed_delta: float
    entry_shift_min: int | None
    exit_shift_min: int | None
    same_exit_reason: bool | None
    same_exit_at: bool | None

    @property
    def total(self) -> float:
        return math.fsum([
            self.entry_price_part,
            self.exit_price_part,
            self.status_part,
        ])


def _signed_direction(direction: str) -> int:
    """Коефіцієнт PnL у пунктах для BUY або SELL."""
    if direction == DIRECTION_UP:
        return 1
    assert direction == DIRECTION_DOWN
    return -1


def _components(
    baseline: ClosedTrade,
    trial: ClosedTrade,
) -> tuple[float, float]:
    """Точна пара компонентів без переоцінювання торгової логіки."""
    assert baseline.direction == trial.direction
    sign = _signed_direction(baseline.direction)
    base_gross = sign * (
        baseline.exit_price - baseline.entry_price
    ) / PIP
    trial_gross = sign * (
        trial.exit_price - trial.entry_price
    ) / PIP
    assert math.isclose(base_gross, baseline.pips, abs_tol=EPS)
    assert math.isclose(trial_gross, trial.pips, abs_tol=EPS)
    entry_part = sign * (
        baseline.entry_price - trial.entry_price
    ) / PIP
    exit_part = sign * (
        trial.exit_price - baseline.exit_price
    ) / PIP
    assert math.isclose(
        math.fsum([entry_part, exit_part]),
        trial.pips - baseline.pips,
        abs_tol=EPS,
    )
    return entry_part, exit_part


def _decompose(
    baseline_closed: dict[int, ClosedTrade],
    trial_closed: dict[int, ClosedTrade],
    trace: Trace,
    outcomes: list[Attribution],
) -> list[Decomposition]:
    """Після Replay розкласти ΔNet на взаємовиключні складові."""
    result: list[Decomposition] = []
    for item in outcomes:
        old = baseline_closed.get(item.episode)
        new = trial_closed.get(item.episode)
        entry_part = 0.0
        exit_part = 0.0
        status_part = 0.0
        entry_shift = None
        exit_shift = None
        same_reason = None
        same_exit = None
        if old is not None and new is not None:
            assert item.base_closed == item.trial_closed == 1
            assert item.base_open == item.trial_open == 0
            closed_class = "BOTH_CLOSED"
            entry_part, exit_part = _components(old, new)
            entry_shift = int(
                (old.entry_at - new.entry_at).total_seconds() // 60
            )
            exit_shift = int(
                (old.exit_at - new.exit_at).total_seconds() // 60
            )
            same_reason = old.exit_reason == new.exit_reason
            same_exit = old.exit_at == new.exit_at
            assert old.entry_at > trace.baseline[item.episode].signal_at
            assert new.entry_at > trace.trial[item.episode].signal_at
        elif old is not None:
            assert item.base_closed == 1 and item.trial_closed == 0
            closed_class = "BASE_CLOSED_ONLY"
            status_part = -old.pips + NET_COST_PIPS
        elif new is not None:
            assert item.trial_closed == 1 and item.base_closed == 0
            closed_class = "TRIAL_CLOSED_ONLY"
            status_part = new.pips - NET_COST_PIPS
        else:
            assert item.base_closed == item.trial_closed == 0
            closed_class = "NEITHER_CLOSED"
        row = Decomposition(
            episode=item.episode,
            direction=item.direction,
            signal_class=item.category,
            closed_class=closed_class,
            entry_price_part=entry_part,
            exit_price_part=exit_part,
            status_part=status_part,
            observed_delta=item.delta,
            entry_shift_min=entry_shift,
            exit_shift_min=exit_shift,
            same_exit_reason=same_reason,
            same_exit_at=same_exit,
        )
        assert math.isclose(row.total, row.observed_delta, abs_tol=EPS)
        result.append(row)
    assert len(result) == len(outcomes)
    return result


def _synthetic_prices() -> None:
    """BUY/SELL: перевірити знаки, cancellation та статусні внески."""
    start = datetime(2025, 1, 6, tzinfo=UTC)

    def trade(
        direction: str, entry: float, exit_price: float,
        entry_min: int, exit_min: int,
    ) -> ClosedTrade:
        sign = _signed_direction(direction)
        return ClosedTrade(
            direction=direction,
            entry_at=start + timedelta(minutes=entry_min),
            exit_at=start + timedelta(minutes=exit_min),
            entry_price=entry,
            exit_price=exit_price,
            pips=sign * (exit_price - entry) / PIP,
            holding_bars=exit_min - entry_min,
            holding_minutes=exit_min - entry_min,
            exit_reason="ENDING",
            exit_gap=False,
        )

    old_buy = trade(DIRECTION_UP, 1.1000, 1.1030, 60, 300)
    new_buy = trade(DIRECTION_UP, 1.0990, 1.1020, 30, 270)
    entry_part, exit_part = _components(old_buy, new_buy)
    assert math.isclose(entry_part, 10.0, abs_tol=EPS)
    assert math.isclose(exit_part, -10.0, abs_tol=EPS)
    assert math.isclose(entry_part + exit_part, 0, abs_tol=EPS)
    old_sell = trade(DIRECTION_DOWN, 1.2000, 1.1980, 60, 300)
    new_sell = trade(DIRECTION_DOWN, 1.1990, 1.1970, 30, 270)
    entry_part, exit_part = _components(old_sell, new_sell)
    assert math.isclose(entry_part, -10.0, abs_tol=EPS)
    assert math.isclose(exit_part, 10.0, abs_tol=EPS)
    assert math.isclose(entry_part + exit_part, 0, abs_tol=EPS)
    old_net = old_buy.pips - NET_COST_PIPS
    new_net = new_buy.pips - NET_COST_PIPS
    entry_part, exit_part = _components(old_buy, new_buy)
    assert math.isclose(
        new_net - old_net,
        math.fsum([entry_part, exit_part]),
        abs_tol=EPS,
    )
    print("SYNTHETIC_PAIRED_PRICE_DECOMPOSITION=OK")


def _f(value: float) -> str:
    """Стабільний формат пунктів для звіряння логів."""
    return f"{value:+.2f}"


def _report(
    label: str, minutes: int, rows: list[Decomposition],
    base_net: float, trial_net: float,
    base_closed: int, trial_closed: int,
    base_open: int, trial_open: int,
) -> None:
    """Net, matched pricing та unmatched execution без змішування."""
    name = TF_NAMES[minutes]
    entry_total = math.fsum([r.entry_price_part for r in rows])
    exit_total = math.fsum([r.exit_price_part for r in rows])
    status_total = math.fsum([r.status_part for r in rows])
    delta = trial_net - base_net
    assert math.isclose(
        math.fsum([entry_total, exit_total, status_total]),
        delta,
        abs_tol=EPS,
    )
    paired = [r for r in rows if r.closed_class == "BOTH_CLOSED"]
    base_only = [
        r for r in rows if r.closed_class == "BASE_CLOSED_ONLY"
    ]
    trial_only = [
        r for r in rows if r.closed_class == "TRIAL_CLOSED_ONLY"
    ]
    neither = [r for r in rows if r.closed_class == "NEITHER_CLOSED"]
    assert len(paired) + len(base_only) == base_closed
    assert len(paired) + len(trial_only) == trial_closed
    print(
        f"DECOMPOSITION|TF={name}|PERIOD={label}|"
        f"EPISODES={len(rows)}|BASE_CLOSED={base_closed}|"
        f"TRIAL_CLOSED={trial_closed}|BASE_OPEN={base_open}|"
        f"TRIAL_OPEN={trial_open}|BOTH_CLOSED={len(paired)}|"
        f"BASE_CLOSED_ONLY={len(base_only)}|"
        f"TRIAL_CLOSED_ONLY={len(trial_only)}|"
        f"NEITHER_CLOSED={len(neither)}"
    )
    print(
        f"NET_BRIDGE|TF={name}|PERIOD={label}|"
        f"BASE_NET040={_f(base_net)}|"
        f"ENTRY_PRICE_PART={_f(entry_total)}|"
        f"EXIT_PRICE_PART={_f(exit_total)}|"
        f"EXECUTION_STATUS_PART={_f(status_total)}|"
        f"TRIAL_NET040={_f(trial_net)}|"
        f"DELTA_NET040={_f(delta)}"
    )
    for direction in (DIRECTION_UP, DIRECTION_DOWN):
        group = [row for row in rows if row.direction == direction]
        values = [
            math.fsum([r.entry_price_part for r in group]),
            math.fsum([r.exit_price_part for r in group]),
            math.fsum([r.status_part for r in group]),
        ]
        total = math.fsum(values)
        assert math.isclose(
            total, math.fsum([r.observed_delta for r in group]),
            abs_tol=EPS,
        )
        paired_count = sum(
            r.closed_class == "BOTH_CLOSED" for r in group
        )
        print(
            f"DIRECTION|TF={name}|PERIOD={label}|"
            f"SIDE={direction}|EPISODES={len(group)}|"
            f"PAIRED_CLOSED={paired_count}|"
            f"ENTRY={_f(values[0])}|EXIT={_f(values[1])}|"
            f"STATUS={_f(values[2])}|DELTA={_f(total)}"
        )
    for signal_class in ("BOTH_EARLIER", "TRIAL_ONLY"):
        group = [r for r in rows if r.signal_class == signal_class]
        print(
            f"SIGNAL_CLASS|TF={name}|PERIOD={label}|"
            f"CLASS={signal_class}|EPISODES={len(group)}|"
            f"ENTRY={_f(math.fsum([r.entry_price_part for r in group]))}|"
            f"EXIT={_f(math.fsum([r.exit_price_part for r in group]))}|"
            f"STATUS={_f(math.fsum([r.status_part for r in group]))}|"
            f"DELTA={_f(math.fsum([r.observed_delta for r in group]))}"
        )
    entry_shifts = [
        r.entry_shift_min for r in paired
        if r.entry_shift_min is not None
    ]
    exit_shifts = [
        r.exit_shift_min for r in paired
        if r.exit_shift_min is not None
    ]
    same_exit = sum(r.same_exit_at is True for r in paired)
    same_reason = sum(r.same_exit_reason is True for r in paired)
    assert len(entry_shifts) == len(exit_shifts) == len(paired)
    median_entry = statistics.median(entry_shifts) if paired else None
    median_exit = statistics.median(exit_shifts) if paired else None
    print(
        f"PAIRED_TIMING|TF={name}|PERIOD={label}|"
        f"PAIRED={len(paired)}|"
        f"MEDIAN_BASE_MINUS_TRIAL_ENTRY_MIN={median_entry}|"
        f"MEDIAN_BASE_MINUS_TRIAL_EXIT_MIN={median_exit}|"
        f"SAME_EXIT_TIMESTAMP={same_exit}|"
        f"SAME_EXIT_REASON={same_reason}"
    )
    ranked = sorted(
        rows, key=lambda r: (-abs(r.observed_delta), r.episode)
    )
    for rank, item in enumerate(ranked[:3], 1):
        print(
            f"CASE|TF={name}|PERIOD={label}|RANK={rank}|"
            f"EPISODE={item.episode}|SIDE={item.direction}|"
            f"CLASS={item.closed_class}|"
            f"ENTRY={_f(item.entry_price_part)}|"
            f"EXIT={_f(item.exit_price_part)}|"
            f"STATUS={_f(item.status_part)}|"
            f"DELTA={_f(item.observed_delta)}"
        )
    print(f"PAIRED_NET_RECONCILIATION={name}:{label}:OK")


def main() -> None:
    """Незалежно звірити обидва періоди без production-змін."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-19|TEST_ONLY|PAIRED_ENTRY_EXIT_TIMING_DECOMPOSITION")
    print("TIMEFRAMES=M30,H1|BASE=4_BARS|TRIAL_M30=2|TRIAL_H1=1")
    print("PRICE_BRIDGE=POST_HOC_ALGEBRA|NOT_CAUSAL_ENTRY_EFFECT=True")
    print("UNMATCHED_CLOSED=EXECUTION_STATUS|UNREALIZED_EXCLUDED=True")
    print("NET040=HYPOTHETICAL|ENTRY_EXIT_SIM_UNCHANGED=True")
    _synthetic_check()
    _synthetic_confirmation()
    _synthetic_attribution()
    _synthetic_episode_link()
    _synthetic_prices()
    for label, filename, *expected in PERIODS:
        path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            path, int(label[:4]), cutoff,
        )
        assert len(aggregated[15]) == expected[0]
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        for minutes in TIMEFRAMES:
            baseline, trial, trace = _run_pair(
                aggregated[minutes], minutes,
            )
            _regression(label, minutes, baseline)
            assert math.isclose(
                _net(baseline), EXPECTED_NET[label][minutes][0],
                abs_tol=EPS,
            )
            assert math.isclose(
                _net(trial), EXPECTED_NET[label][minutes][1],
                abs_tol=EPS,
            )
            old, _ = _trade_lookup(baseline, trace.baseline)
            new, _ = _trade_lookup(trial, trace.trial)
            openings = {
                bar.timestamp: bar.open for bar in aggregated[minutes]
            }
            for trade in (*old.values(), *new.values()):
                assert trade.entry_at < trade.exit_at
                assert math.isclose(
                    trade.entry_price, openings[trade.entry_at],
                    abs_tol=EPS,
                )
                assert math.isclose(
                    trade.exit_price, openings[trade.exit_at],
                    abs_tol=EPS,
                )
            observed = _attribute(baseline, trial, trace)
            rows = _decompose(old, new, trace, observed)
            print(
                f"BASE|TF={TF_NAMES[minutes]}|PERIOD={label}|"
                f"{_summary(baseline, NET_COST_PIPS)}"
            )
            print(
                f"TRIAL|TF={TF_NAMES[minutes]}|PERIOD={label}|"
                f"{_summary(trial, NET_COST_PIPS)}"
            )
            _report(
                label, minutes, rows,
                _net(baseline), _net(trial),
                len(baseline.result.trades), len(trial.result.trades),
                baseline.result.open_at_end, trial.result.open_at_end,
            )
            print(
                f"REPLAY_MIRROR_DETERMINISTIC={TF_NAMES[minutes]}:"
                f"{label}:OK"
            )
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_19_PAIRED_ENTRY_EXIT_TIMING_DECOMPOSITION=OK")


if __name__ == "__main__":
    main()
