# -*- coding: utf-8 -*-
"""RoadMap115 / T115-28: квартальна стійкість H1 SELL gate.

TEST_ONLY. Діагностика незмінного causal Replay T115-27.
Групування за UTC кварталом входу; 2026 Q3 є неповним.
Внески завершених угод оцінюються після фактичного виходу.
Future labels не беруть участі в рішеннях, параметри не підбираємо.
Mid OHLC + умовні 0.40 pips; це не реальні брокерські fills.
Production / MD7 не редагуються. Періоди не є out-of-sample.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
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
    ClosedTrade,
    _fingerprint,
)
from T115_15_Extended_Timeframe_Plateau_Audit import (  # noqa: E402
    NET_COST_PIPS,
    _aggregate_all,
    _run_tf,
    _synthetic_check,
)
from T115_21_H1_M15_Trend_Watch_Audit import (  # noqa: E402
    EXPECTED_H1,
    H1_MIN,
    M15_MIN,
    _observe_m15,
    _synthetic_watch,
)
from T115_25_H1_Entry_M15_State_Anatomy import (  # noqa: E402
    _synthetic_entry_boundary,
)
from T115_26_H1_SELL_M15_Aligned_Reject_Cost_Audit import (  # noqa: E402
    EXPECTED_REJECT,
    _synthetic_cost,
)
from T115_27_H1_SELL_M15_Causal_Entry_Gate_Replay import (  # noqa: E402
    REFERENCE_NET,
    GateEngine,
    _run_gated,
    _synthetic_gate,
    _synthetic_gate_execution,
)

EPS = 1e-6
TOP_N = (1, 3, 5)


def _quarter(at: datetime) -> str:
    """UTC квартал часу входу, без інформації про результат."""
    assert at.tzinfo is not None
    utc = at.astimezone(UTC)
    return f"{utc.year}-Q{(utc.month - 1) // 3 + 1}"


def _net(trade: ClosedTrade) -> float:
    """Чисті пункти закритої позиції за умовною вартістю."""
    return float(trade.pips) - NET_COST_PIPS


def _total(trades: list[ClosedTrade]) -> float:
    values: list[float] = [_net(trade) for trade in trades]
    return math.fsum(values)


def _score(trades: list[ClosedTrade]) -> tuple[float, float, float]:
    """Net, PF та закрита просадка; усі угоди вже завершено."""
    ordered = sorted(trades, key=lambda trade: trade.exit_at)
    values: list[float] = [_net(trade) for trade in ordered]
    net = math.fsum(values)
    gains = math.fsum([max(value, 0.0) for value in values])
    losses = -math.fsum([min(value, 0.0) for value in values])
    pf = gains / losses if losses > EPS else float("inf")
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return net, pf, drawdown


def _index(trades: list[ClosedTrade]) -> dict[datetime, ClosedTrade]:
    indexed = {trade.entry_at: trade for trade in trades}
    assert len(indexed) == len(trades)
    return indexed


def _synthetic_quarters() -> None:
    """Перевірка UTC-меж, вартості, знаків і outlier-діагностики."""
    t1 = datetime(2025, 3, 31, 23, 59, tzinfo=UTC)
    t2 = datetime(2025, 4, 1, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
    assert [_quarter(at) for at in (t1, t2, t3)] == [
        "2025-Q1",
        "2025-Q2",
        "2026-Q3",
    ]
    values = [-10.0, +4.0, -2.0, +9.0]
    assert math.isclose(-math.fsum(values), -1.0, abs_tol=EPS)
    remaining_worst = sorted(values)[1:]
    assert math.isclose(math.fsum(remaining_worst), 11.0, abs_tol=EPS)
    remaining_abs = sorted(values, key=lambda value: -abs(value))[1:]
    assert math.isclose(math.fsum(remaining_abs), 11.0, abs_tol=EPS)
    assert abs(_quarter(t2) != _quarter(t1)) == 1
    print("SYNTHETIC_QUARTER_BUCKETS=OK")
    print("SYNTHETIC_TAIL_SIGN_AND_COST_ACCOUNTING=OK")


def _quarter_report(
    label: str,
    raw: GateEngine,
    gated: GateEngine,
) -> None:
    """Звірити квартали, напрямки й вплив найбільших відмов."""
    base = raw.result.trades
    trial = gated.result.trades
    base_at = _index(base)
    trial_at = _index(trial)
    common = set(base_at) & set(trial_at)
    lost_keys = set(base_at) - set(trial_at)
    added_keys = set(trial_at) - set(base_at)
    assert all(base_at[at] == trial_at[at] for at in common)
    baseline_buy = [trade for trade in base if trade.direction == DIRECTION_UP]
    gated_buy = [trade for trade in trial if trade.direction == DIRECTION_UP]
    assert baseline_buy == gated_buy
    rejected = [base_at[at] for at in lost_keys]
    added = [trial_at[at] for at in added_keys]
    assert all(trade.direction == DIRECTION_DOWN for trade in rejected)
    assert len(rejected) == EXPECTED_REJECT[label][0]
    assert len(gated.rejected) == len(rejected)
    assert len(added) == 0
    assert math.isclose(
        _total(rejected),
        EXPECTED_REJECT[label][3],
        abs_tol=EPS,
    )
    net_base = _total(base)
    net_gate = _total(trial)
    assert math.isclose(net_base, REFERENCE_NET[label], abs_tol=EPS)
    assert math.isclose(
        net_gate - net_base,
        _total(added) - _total(rejected),
        abs_tol=EPS,
    )
    print(
        f"CROSS_CHECK|PERIOD={label}|BASE_CLOSED={len(base)}|"
        f"GATE_CLOSED={len(trial)}|REJECTED={len(rejected)}|"
        f"NEW_TRADES={len(added)}|BUY_PRESERVED={len(gated_buy)}|"
        f"NET_BASE={net_base:+.2f}|NET_GATE={net_gate:+.2f}|"
        f"DELTA={net_gate - net_base:+.2f}"
    )

    quarters = sorted({_quarter(trade.entry_at) for trade in base + trial})
    assert quarters
    summed_base = summed_gate = summed_reject = 0.0
    positive = 0
    for quarter in quarters:
        bq = [t for t in base if _quarter(t.entry_at) == quarter]
        gq = [t for t in trial if _quarter(t.entry_at) == quarter]
        rq = [t for t in rejected if _quarter(t.entry_at) == quarter]
        aq = [t for t in added if _quarter(t.entry_at) == quarter]
        b_net, b_pf, b_dd = _score(bq)
        g_net, g_pf, g_dd = _score(gq)
        r_net, _, _ = _score(rq)
        delta = g_net - b_net
        assert math.isclose(delta, _total(aq) - r_net, abs_tol=EPS)
        positive += int(delta > EPS)
        wins_lost = sum(_net(trade) > EPS for trade in rq)
        losers_avoided = sum(_net(trade) < -EPS for trade in rq)
        print(
            f"QUARTER|PERIOD={label}|Q={quarter}|"
            f"BASE_CLOSED={len(bq)}|GATE_CLOSED={len(gq)}|"
            f"REJECTED={len(rq)}|LOST_WINNERS={wins_lost}|"
            f"AVOIDED_LOSERS={losers_avoided}|"
            f"BASE_NET040={b_net:+.2f}|GATE_NET040={g_net:+.2f}|"
            f"DELTA_NET040={delta:+.2f}|"
            f"BASE_PF={b_pf:.3f}|GATE_PF={g_pf:.3f}|"
            f"BASE_DD={b_dd:.2f}|GATE_DD={g_dd:.2f}"
        )
        summed_base += b_net
        summed_gate += g_net
        summed_reject += r_net
    assert math.isclose(summed_base, net_base, abs_tol=EPS)
    assert math.isclose(summed_gate, net_gate, abs_tol=EPS)
    assert math.isclose(summed_reject, _total(rejected), abs_tol=EPS)
    print(
        f"QUARTER_RECONCILIATION={label}:OK|"
        f"POSITIVE_DELTA_QUARTERS={positive}|TOTAL_QUARTERS="
        f"{len(quarters)}"
    )

    # Залишаємо за бортом по одному кварталу: стрес-тест, не OOS.
    for omit in quarters:
        retained = [t for t in rejected if _quarter(t.entry_at) != omit]
        remaining_delta = -_total(retained)
        print(
            f"LEAVE_ONE_QUARTER_OUT|PERIOD={label}|OMIT={omit}|"
            f"REMAINING_REJECTED={len(retained)}|"
            f"REMAINING_DELTA={remaining_delta:+.2f}"
        )

    ordered_loss = sorted(rejected, key=_net)
    ordered_abs = sorted(rejected, key=lambda trade: -abs(_net(trade)))
    for count in TOP_N:
        assert len(rejected) > count
        remaining_loss = -_total(ordered_loss[count:])
        remaining_abs = -_total(ordered_abs[count:])
        print(
            f"TAIL|PERIOD={label}|DROP={count}|"
            f"REMAINING_GAIN_EXCL_WORST={remaining_loss:+.2f}|"
            f"REMAINING_GAIN_EXCL_LARGEST_ABS={remaining_abs:+.2f}"
        )
    top_three = ordered_loss[:3]
    top_three_loss = -_total(top_three)
    full_gain = -_total(rejected)
    print(
        f"CONCENTRATION|PERIOD={label}|TOP3_WORST_SAVING="
        f"{top_three_loss:+.2f}|TOTAL_SAVING={full_gain:+.2f}|"
        f"TOP3_SHARE_PCT={100.0 * top_three_loss / full_gain:.2f}"
    )
    for rank, trade in enumerate(top_three, 1):
        print(
            f"WORST_REJECT|PERIOD={label}|RANK={rank}|"
            f"Q={_quarter(trade.entry_at)}|"
            f"ENTRY={trade.entry_at.isoformat()}|"
            f"EXIT_REASON={trade.exit_reason}|NET040={_net(trade):+.2f}"
        )

    for side in (DIRECTION_UP, DIRECTION_DOWN):
        before = [t for t in base if t.direction == side]
        after = [t for t in trial if t.direction == side]
        print(
            f"SIDE|PERIOD={label}|DIRECTION={side}|"
            f"BASE_CLOSED={len(before)}|GATE_CLOSED={len(after)}|"
            f"BASE_NET040={_total(before):+.2f}|"
            f"GATE_NET040={_total(after):+.2f}|"
            f"DELTA={_total(after) - _total(before):+.2f}"
        )
    print(f"TRADE_AND_QUARTER_ACCOUNTING={label}:OK")


def main() -> None:
    """Здійснити незмінний causal H1 Replay та квартальний аудит."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-28|TEST_ONLY|H1_SELL_GATE_QUARTER_STABILITY_AUDIT")
    print("GATE=UNCHANGED_T115_27|QUARTER=UTC_ENTRY_TIME")
    print("FULL_2025_AND_PARTIAL_2026|IN_SAMPLE_ONLY=True")
    print("TAIL_AND_LEAVE_ONE_QUARTER_OUT=POST_HOC_ONLY")
    print("GROSS_MID_ONLY=True|COST_040_HYPOTHETICAL=True")
    _synthetic_check()
    _synthetic_watch()
    _synthetic_entry_boundary()
    _synthetic_cost()
    _synthetic_gate()
    _synthetic_gate_execution()
    _synthetic_quarters()
    for label, filename, *_ in PERIODS:
        source_path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
        cutoff = CANONICAL_2026_END if label.startswith("2026") else None
        source, selected, aggregated = _aggregate_all(
            source_path,
            int(label[:4]),
            cutoff,
        )
        print(
            f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
            f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
        )
        states = _observe_m15(aggregated[M15_MIN])
        baseline, gated = _run_gated(aggregated[H1_MIN], states)
        expected = _run_tf(
            aggregated[H1_MIN],
            H1_MIN,
            _profile(),
        )[2]
        assert baseline.result == expected.result
        assert len(baseline.result.trades) == EXPECTED_H1[label][0]
        assert math.isclose(
            _total(baseline.result.trades),
            REFERENCE_NET[label],
            abs_tol=EPS,
        )
        print(f"H1_T115_27_BASELINE_MATCH={label}:OK")
        _quarter_report(label, baseline, gated)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_28_H1_SELL_GATE_QUARTER_STABILITY_AUDIT=OK")


if __name__ == "__main__":
    main()
