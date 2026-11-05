# -*- coding: utf-8 -*-
"""RoadMap115 / T115-26 — вартість M15 ACTIVE_ALIGNED SELL.

TEST_ONLY. Тільки ретроспективне виключення завершених H1-угод.
H1 Alligator hybrid і правила виконання не змінюються.
M15 визначається останнім завершеним баром СТРОГО перед H1 entry.
Оцінка після вилучення не є новим Replay або прибутком gate:
відсутні пропущені/додаткові угоди через зміну стану позиції.
Умовні витрати: 0.40 pip на завершену позицію. Без broker IO.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    PERIODS,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_DOWN,
    DIRECTION_UP,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    _aggregate_all,
    _run_tf,
    _summary,
    _synthetic_check,
)
from T115_21_H1_M15_Trend_Watch_Audit import (  # noqa: E402
    EXPECTED_H1,
    H1_MIN,
    M15_MIN,
    _observe_m15,
    _synthetic_watch,
    _trace_h1,
)
from T115_25_H1_Entry_M15_State_Anatomy import (  # noqa: E402
    EntryState,
    PIP_EPS,
    _entries,
    _synthetic_entry_boundary,
)

RULE = "SELL_AND_PRE_ENTRY_M15_ACTIVE_ALIGNED"
EXPECTED_REJECT = {
    "2025": (26, 10, 16, -181.90),
    "2026_TO_2026_08_25": (22, 7, 15, -152.00),
}


@dataclass(frozen=True, slots=True)
class Score:
    """Метрики завершених угод за умовних витрат."""

    count: int
    wins: int
    losses: int
    flat: int
    gross: float
    net: float
    pf: float
    max_dd: float
    avg_net: float


def _net(entry: EntryState) -> float:
    return float(entry.trade.pips) - NET_COST_PIPS


def _score(entries: list[EntryState]) -> Score:
    """Не змінює Replay; склад позицій задає вхідний список."""
    gross_values: list[float] = [
        float(entry.trade.pips) for entry in entries
    ]
    values: list[float] = [_net(entry) for entry in entries]
    gross = math.fsum(gross_values)
    net = math.fsum(values)
    positive = math.fsum([max(value, 0.0) for value in values])
    negative = -math.fsum([min(value, 0.0) for value in values])
    pf = positive / negative if negative > PIP_EPS else float("inf")
    equity = peak = max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return Score(
        count=len(entries),
        wins=sum(value > PIP_EPS for value in values),
        losses=sum(value < -PIP_EPS for value in values),
        flat=sum(abs(value) <= PIP_EPS for value in values),
        gross=gross,
        net=net,
        pf=pf,
        max_dd=max_dd,
        avg_net=statistics.fmean(values) if values else 0.0,
    )


def _reject(entry: EntryState) -> bool:
    """Критерій за строго попереднім завершеним M15."""
    return (
        entry.trade.direction == DIRECTION_DOWN
        and entry.strict_class == "ACTIVE_ALIGNED"
    )


def _split(
    entries: list[EntryState],
) -> tuple[list[EntryState], list[EntryState]]:
    """Повернути залишені та умовно відхилені closed trades."""
    kept = [entry for entry in entries if not _reject(entry)]
    rejected = [entry for entry in entries if _reject(entry)]
    assert len(kept) + len(rejected) == len(entries)
    assert all(_reject(entry) for entry in rejected)
    assert all(not _reject(entry) for entry in kept)
    return kept, rejected


def _print_score(label: str, name: str, score: Score) -> None:
    print(
        f"SCORE|PERIOD={label}|GROUP={name}|CLOSED={score.count}|"
        f"WINS={score.wins}|LOSSES={score.losses}|FLAT={score.flat}|"
        f"GROSS={score.gross:+.2f}|NET040={score.net:+.2f}|"
        f"AVG_NET040={score.avg_net:+.3f}|PF_NET={score.pf:.3f}|"
        f"MAX_CLOSED_DD_NET040={score.max_dd:.2f}"
    )


def _synthetic_cost() -> None:
    """Захист знаків, вартості втрачених winners і вибору SELL."""
    from datetime import UTC, datetime, timedelta

    from T115_02_Alligator_Exit_Only_Trades import ClosedTrade

    origin = datetime(2025, 1, 6, 12, tzinfo=UTC)

    def sample(side: str, category: str, pnl: float) -> EntryState:
        trade = ClosedTrade(
            direction=side,
            entry_at=origin,
            exit_at=origin + timedelta(hours=1),
            entry_price=1.10,
            exit_price=1.10,
            pips=pnl,
            holding_bars=1,
            holding_minutes=60,
            exit_reason="ENDING",
            exit_gap=False,
        )
        return EntryState(
            trade=trade,
            entry_at=origin,
            strict_state=None,
            boundary_state=None,
            strict_class=category,
            boundary_class=category,
            strict_age_min=None,
        )

    all_entries = [
        sample(DIRECTION_DOWN, "ACTIVE_ALIGNED", -10.0),
        sample(DIRECTION_DOWN, "ACTIVE_ALIGNED", 5.0),
        sample(DIRECTION_DOWN, "ENDING_ALIGNED", -2.0),
        sample(DIRECTION_UP, "ACTIVE_ALIGNED", 20.0),
    ]
    kept, rejected = _split(all_entries)
    a = _score(all_entries)
    b = _score(kept)
    c = _score(rejected)
    assert (c.count, c.wins, c.losses) == (2, 1, 1)
    assert (b.count, b.wins, b.losses) == (2, 1, 1)
    assert math.isclose(a.net, b.net + c.net, abs_tol=1e-9)
    assert math.isclose(b.net - a.net, -c.net, abs_tol=1e-9)
    assert math.isclose(c.net, -5.8, abs_tol=1e-9)
    assert all(entry.strict_class != "ACTIVE_ALIGNED"
               or entry.trade.direction == DIRECTION_UP
               for entry in kept)
    print("SYNTHETIC_REJECT_COST_ACCOUNTING=OK")
    print("SYNTHETIC_WINNER_LOSS_PRESERVATION=OK")
    print("SYNTHETIC_BUY_UNCHANGED=OK")


def _tail(label: str, rejected: list[EntryState]) -> None:
    """Чутливість до великих збитків, без підбору нового правила."""
    losses_first = sorted(rejected, key=_net)
    abs_first = sorted(rejected, key=lambda trade: -abs(_net(trade)))
    for count in (1, 3, 5):
        assert len(rejected) > count
        without_worst = _score(losses_first[count:])
        without_abs = _score(abs_first[count:])
        print(
            f"OUTLIER|PERIOD={label}|DROP={count}|"
            f"REJECT_NET_EXCL_WORST={without_worst.net:+.2f}|"
            f"REJECT_NET_EXCL_LARGEST_ABS={without_abs.net:+.2f}"
        )


def _report(label: str, entries: list[EntryState]) -> None:
    """Тільки closed-only бухгалтерія відхилення SELL."""
    baseline = _score(entries)
    kept, rejected = _split(entries)
    kept_score = _score(kept)
    reject_score = _score(rejected)
    buy = [e for e in entries if e.trade.direction == DIRECTION_UP]
    sell = [e for e in entries if e.trade.direction == DIRECTION_DOWN]
    kept_sell = [e for e in kept if e.trade.direction == DIRECTION_DOWN]
    assert _score(buy) == _score([
        e for e in kept if e.trade.direction == DIRECTION_UP
    ])
    assert math.isclose(
        baseline.net, kept_score.net + reject_score.net,
        abs_tol=1e-7,
    )
    assert math.isclose(
        baseline.gross, kept_score.gross + reject_score.gross,
        abs_tol=1e-7,
    )
    assert kept_score.count == baseline.count - reject_score.count
    assert len(sell) == len(kept_sell) + len(rejected)
    expected = EXPECTED_REJECT[label]
    assert (
        reject_score.count, reject_score.wins, reject_score.losses
    ) == expected[:3]
    assert math.isclose(reject_score.net, expected[3], abs_tol=1e-6)
    assert all(e.strict_state is not None for e in rejected)
    assert all(e.strict_state.at < e.entry_at for e in rejected)
    print(
        f"RULE|PERIOD={label}|REJECTED_SELL={len(rejected)}|"
        f"SELL_TOTAL={len(sell)}|BUY_UNCHANGED={len(buy)}|"
        f"ENTRY_STATE=STRICT_PRE_ENTRY_M15"
    )
    _print_score(label, "H1_BASELINE_ALL", baseline)
    _print_score(label, "REJECTED_SELL", reject_score)
    _print_score(label, "RETAINED_SELL", _score(kept_sell))
    _print_score(label, "H1_KEPT_POST_HOC", kept_score)
    lost_winners = [_net(e) for e in rejected if _net(e) > PIP_EPS]
    avoided_losses = [_net(e) for e in rejected if _net(e) < -PIP_EPS]
    assert len(lost_winners) == reject_score.wins
    assert len(avoided_losses) == reject_score.losses
    saved_pips = -math.fsum(avoided_losses)
    lost_pips = math.fsum(lost_winners)
    assert math.isclose(
        saved_pips - lost_pips, -reject_score.net,
        abs_tol=1e-7,
    )
    print(
        f"REJECT_COST|PERIOD={label}|"
        f"AVOIDED_LOSERS={len(avoided_losses)}|"
        f"AVOIDED_LOSSES_PIPS={saved_pips:+.2f}|"
        f"LOST_WINNERS={len(lost_winners)}|"
        f"LOST_WIN_PIPS={lost_pips:+.2f}|"
        f"NET_SAVING_POST_HOC={-reject_score.net:+.2f}"
    )
    reasons = sorted({e.trade.exit_reason for e in rejected})
    for reason in reasons:
        selected = [e for e in rejected if e.trade.exit_reason == reason]
        _print_score(label, f"REJECTED_REASON_{reason}", _score(selected))
    _tail(label, rejected)
    print(f"CLOSED_ONLY_ACCOUNTING_RECONCILIATION={label}:OK")


def main() -> None:
    """Повторити незмінний H1 Replay та оцінити відхилені SELL."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-26|TEST_ONLY|H1_SELL_M15_ALIGNED_REJECT_COST")
    print("RULE=SELL_AND_PRE_ENTRY_M15_ACTIVE_ALIGNED")
    print("H1_ENTRY_EXIT=UNCHANGED_4_BARS_HYBRID|M15=PASSIVE_ONLY")
    print("REJECTION=POST_HOC_CLOSED_ONLY|NO_GATED_REPLAY=True")
    print("M15_AT_ENTRY=STRICTLY_EARLIER|SAME_TICK_EXCLUDED=True")
    print("NO_OCCUPANCY_EFFECT_MODELED=True|OPEN_POSITIONS_EXCLUDED=True")
    print("NET040=HYPOTHETICAL|NOT_OUT_OF_SAMPLE=True")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    _synthetic_cost()
    for label, filename, *_ in PERIODS:
        data_path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            data_path, int(label[:4]), cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        replay, windows = _trace_h1(aggregated[H1_MIN])
        baseline = _run_tf(aggregated[H1_MIN], H1_MIN, _profile())[2]
        assert replay == baseline
        count, opened, gross, net = EXPECTED_H1[label]
        assert len(windows) == count
        assert replay.result.open_at_end == opened
        trades = replay.result.trades
        assert math.isclose(
            math.fsum([trade.pips for trade in trades]), gross,
            abs_tol=1e-6,
        )
        assert math.isclose(
            math.fsum([trade.pips - NET_COST_PIPS for trade in trades]),
            net, abs_tol=1e-6,
        )
        print(
            f"H1_BASELINE_MATCH={label}:OK|"
            f"{_summary(replay, NET_COST_PIPS)}"
        )
        states = _observe_m15(aggregated[M15_MIN])
        entries = _entries(trades, states)
        assert len(entries) == len(trades)
        _report(label, entries)
        assert entries == _entries(trades, states)
        print(f"REPLAY_MIRROR_DETERMINISTIC={label}:OK")
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_26_H1_SELL_M15_ALIGNED_REJECT_COST_AUDIT=OK")


if __name__ == "__main__":
    main()
