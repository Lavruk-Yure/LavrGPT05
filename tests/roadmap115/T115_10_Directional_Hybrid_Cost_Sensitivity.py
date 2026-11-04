# -*- coding: utf-8 -*-
"""RoadMap115 / T115-10 — вплив витрат на гібридний вихід.

TEST_ONLY. Входи, виходи та причини закриття взято БЕЗ ЗМІН із
T115-02/03/09: Alligator; Alligator + гіпотеза 33%; гібрид
BUY до ENDING, SELL до ENDING або 33%.

Дані — OHLC mid. Фактичних котирувань Bid/Ask, комісії брокера,
обсягу позиції та реалізованого прослизання у цьому досліді немає.
Усі числові витрати — умовні фіксовані сценарії на одну ЗАКРИТУ
угоду, не оцінки реальних тарифів і не production execution model.

Спред: повна ширина Bid-Ask у пунктах, однакова на вході й виході;
від mid віднімаємо по пів спреду на кожному боці угоди.
Комісія: обидві сторони разом, у pip-equivalent для EURUSD.
Прослизання: окремо на вході та виході, несприятливе для угоди.
Сигнали 33% залишаються обчисленими за mid completed M15 close.
Жодних додаткових брокерських запитів, look-ahead чи production-змін.

Відкриту наприкінці 2026 позицію не включено до closed PnL і
не віднесено на неї неповні витрати входу. Порівняння є closed-only.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    CANONICAL_2026_END,
    PERIODS,
    _aggregate_m1,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    DIRECTION_DOWN,
    DIRECTION_UP,
    ClosedTrade,
    PIP,
    Result,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    _simulate_variant,
)
from T115_09_Directional_Hybrid_Exit_Replay import (  # noqa: E402
    HYBRID_33_DIRECTIONS,
    _check_trade_selection,
    _simulate_directional,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-6


@dataclass(frozen=True, slots=True)
class CostScenario:
    """Фіксовані гіпотетичні витрати на одну завершену round-trip угоду."""

    name: str
    spread_pips: float
    commission_roundtrip_pips: float
    slippage_entry_pips: float
    slippage_exit_pips: float

    @property
    def total_pips(self) -> float:
        """Вартість входу та виходу разом у пунктах EURUSD."""
        return math.fsum((
            self.spread_pips,
            self.commission_roundtrip_pips,
            self.slippage_entry_pips,
            self.slippage_exit_pips,
        ))


SCENARIOS = (
    CostScenario("ZERO", 0.00, 0.00, 0.00, 0.00),
    CostScenario("LOW_020", 0.10, 0.04, 0.03, 0.03),
    CostScenario("MID_040", 0.20, 0.08, 0.06, 0.06),
    CostScenario("MED_060", 0.30, 0.12, 0.09, 0.09),
    CostScenario("HIGH_100", 0.50, 0.20, 0.15, 0.15),
    CostScenario("STRESS_150", 0.80, 0.30, 0.20, 0.20),
)

VARIANTS = (
    "ALLIGATOR_ONLY",
    "ALLIGATOR_PLUS_33",
    "HYBRID_BUY_ALLIGATOR_SELL_33",
)


@dataclass(frozen=True, slots=True)
class NetMetrics:
    """Однакові метрики для всіх варіантів та сценаріїв."""

    closed: int
    wins: int
    losses: int
    flat: int
    win_rate_pct: float
    gross_pips: float
    costs_pips: float
    net_pips: float
    avg_net_pips: float
    median_net_pips: float
    profit_factor_net: float
    max_closed_dd_net_pips: float


def _effective_prices(
    trade: ClosedTrade,
    scenario: CostScenario,
) -> tuple[float, float]:
    """Модель Bid/Ask з несприятливими поправками для BUY/SELL."""
    half_spread = scenario.spread_pips * PIP / 2
    entry_slip = scenario.slippage_entry_pips * PIP
    exit_slip = scenario.slippage_exit_pips * PIP
    if trade.direction == DIRECTION_UP:
        return (
            trade.entry_price + half_spread + entry_slip,
            trade.exit_price - half_spread - exit_slip,
        )
    assert trade.direction == DIRECTION_DOWN
    return (
        trade.entry_price - half_spread - entry_slip,
        trade.exit_price + half_spread + exit_slip,
    )


def _net_pips(trade: ClosedTrade, scenario: CostScenario) -> float:
    """Від брутто відняти один round-trip, не змінюючи рішення Replay."""
    assert trade.direction in (DIRECTION_UP, DIRECTION_DOWN)
    gross = trade.pips
    net = gross - scenario.total_pips
    entry, exit_price = _effective_prices(trade, scenario)
    signed = 1 if trade.direction == DIRECTION_UP else -1
    check = signed * (exit_price - entry) / PIP
    check -= scenario.commission_roundtrip_pips
    assert math.isclose(check, net, abs_tol=EPS)
    return net


def _metrics(
    trades: list[ClosedTrade],
    scenario: CostScenario,
) -> NetMetrics:
    """Closed-only net PF, WR, avg та абсолютна closed-equity DD."""
    values = [_net_pips(trade, scenario) for trade in trades]
    count = len(values)
    wins = sum(value > EPS for value in values)
    losses = sum(value < -EPS for value in values)
    flat = count - wins - losses
    positive = math.fsum(value for value in values if value > EPS)
    negative = -math.fsum(value for value in values if value < -EPS)
    profit_factor = positive / negative if negative else math.inf
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    gross = math.fsum(trade.pips for trade in trades)
    costs = count * scenario.total_pips
    net = math.fsum(values)
    assert math.isclose(net, gross - costs, abs_tol=EPS)
    return NetMetrics(
        closed=count,
        wins=wins,
        losses=losses,
        flat=flat,
        win_rate_pct=100 * wins / count if count else 0.0,
        gross_pips=gross,
        costs_pips=costs,
        net_pips=net,
        avg_net_pips=net / count if count else 0.0,
        median_net_pips=statistics.median(values) if values else 0.0,
        profit_factor_net=profit_factor,
        max_closed_dd_net_pips=drawdown,
    )


def _synthetic_cost_checks() -> None:
    """Перевірити знак BUY/SELL, нульові витрати та поріг витрат."""
    from datetime import UTC, datetime, timedelta

    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    sample = [
        ClosedTrade(
            direction=direction,
            entry_at=start,
            exit_at=start + timedelta(minutes=15),
            entry_price=entry_price,
            exit_price=exit_price,
            pips=10.0,
            holding_bars=1,
            holding_minutes=15,
            exit_reason="ENDING",
            exit_gap=False,
        )
        for direction, entry_price, exit_price in (
            (DIRECTION_UP, 1.1000, 1.1010),
            (DIRECTION_DOWN, 1.1010, 1.1000),
        )
    ]
    for trade in sample:
        assert math.isclose(_net_pips(trade, SCENARIOS[0]), 10.0)
        assert math.isclose(_net_pips(trade, SCENARIOS[2]), 9.6)
    summary = _metrics(sample, SCENARIOS[2])
    assert summary.closed == 2
    assert math.isclose(summary.net_pips, 19.2, abs_tol=EPS)
    assert math.isclose(summary.costs_pips, 0.8, abs_tol=EPS)
    assert math.isclose(summary.profit_factor_net, math.inf)

    # Рівно нульове net: жодної вигаданої прибутковості.
    threshold = CostScenario("BREAK_EVEN", 10.0, 0.0, 0.0, 0.0)
    assert _metrics(sample, threshold).flat == 2
    assert _metrics(sample, threshold).net_pips == 0.0

    # У сценаріях немає від'ємних/нечислових або прихованих витрат.
    assert len({item.name for item in SCENARIOS}) == len(SCENARIOS)
    for scenario in SCENARIOS:
        parts = (
            scenario.spread_pips,
            scenario.commission_roundtrip_pips,
            scenario.slippage_entry_pips,
            scenario.slippage_exit_pips,
        )
        assert all(math.isfinite(v) and v >= 0 for v in parts)
        assert math.isclose(scenario.total_pips, sum(parts), abs_tol=EPS)
    print("SYNTHETIC_BID_ASK_COST_MODEL=OK")


def _fingerprint(path: Path) -> str | None:
    """Тільки читання контрольних production-файлів."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline_assertions(
    label: str,
    baseline: Result,
    full33: Result,
    hybrid: Result,
) -> None:
    """Не дозволити непомітно змінити trade population або gross."""
    expected = {
        "2025": (800, -722.70, -670.50, -214.80, 0),
        "2026_TO_2026_08_25": (505, -6.30, -111.30, 190.90, 1),
    }
    count, gross_base, gross_33, gross_hybrid, open_end = expected[label]
    assert len(baseline.trades) == len(full33.trades) == count
    assert len(hybrid.trades) == count
    assert baseline.open_at_end == full33.open_at_end == open_end
    assert hybrid.open_at_end == open_end
    _check_trade_selection(baseline, full33, hybrid)
    for result, gross in (
        (baseline, gross_base),
        (full33, gross_33),
        (hybrid, gross_hybrid),
    ):
        assert math.isclose(
            math.fsum(trade.pips for trade in result.trades),
            gross,
            abs_tol=0.005,
        ), f"GROSS_CHANGED: {label}"


def _print_metrics(
    label: str,
    scenario: CostScenario,
    variant: str,
    item: NetMetrics,
) -> None:
    """Однакова схема виходу для кожного Replay."""
    print(
        f"NET|PERIOD={label}|SCENARIO={scenario.name}|VARIANT={variant}|"
        f"CLOSED={item.closed}|WINS={item.wins}|LOSSES={item.losses}|"
        f"FLAT={item.flat}|WIN_RATE_PCT={item.win_rate_pct:.2f}|"
        f"GROSS_PIPS={item.gross_pips:.2f}|"
        f"COST_PIPS={item.costs_pips:.2f}|"
        f"NET_PIPS={item.net_pips:.2f}|"
        f"AVG_NET_PIPS={item.avg_net_pips:.3f}|"
        f"MEDIAN_NET_PIPS={item.median_net_pips:.2f}|"
        f"PF_NET={item.profit_factor_net:.3f}|"
        f"MAX_CLOSED_DD_NET_PIPS={item.max_closed_dd_net_pips:.2f}"
    )


def _run_period(
    label: str,
    filename: str,
    expected: tuple[int, ...],
    profile,
) -> None:
    """Незмінні угоди трьох стратегій; витрати накладаються після Replay."""
    path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source_count, selected_count, bars = _aggregate_m1(
        path, int(label[:4]), cutoff,
    )
    steps = list(_states(bars, profile))
    baseline = _simulate(steps)
    full33 = _simulate_variant(steps, use_33=True)
    hybrid = _simulate_directional(
        steps, use_33_for=HYBRID_33_DIRECTIONS,
    )
    hybrid_again = _simulate_directional(
        steps, use_33_for=HYBRID_33_DIRECTIONS,
    )
    assert hybrid == hybrid_again
    assert (
        len(bars), baseline.entry_signals, baseline.buy_signals,
        baseline.sell_signals, baseline.next_open_available,
    ) == expected, f"ENTRY_POPULATION_MISMATCH: {label}"
    _baseline_assertions(label, baseline, full33, hybrid)

    variants = {
        VARIANTS[0]: baseline,
        VARIANTS[1]: full33,
        VARIANTS[2]: hybrid,
    }
    gross = {
        name: math.fsum(trade.pips for trade in result.trades)
        for name, result in variants.items()
    }
    print(
        f"PERIOD={label}|SOURCE_M1={source_count}|"
        f"SELECTED_M1={selected_count}|COMPLETED_M15={len(bars)}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"ORDERS|ACTIVE={baseline.entry_signals}|"
        f"ENTRY_EXECUTED={hybrid.entries}|CLOSED={len(hybrid.trades)}|"
        f"OPEN_AT_END={hybrid.open_at_end}|"
        f"GAP_EXIT_FILLS={hybrid.exit_gap_fills}"
    )
    break_even = gross[VARIANTS[2]] / len(hybrid.trades)
    status = (
        f"{break_even:.6f}" if break_even > 0 else "NONE_NONNEGATIVE"
    )
    print(
        f"HYBRID_BREAK_EVEN_ALL_IN_PIPS_ROUNDTRIP={status}|"
        "ASSUMES_CONSTANT_COST_PER_CLOSED_TRADE=True"
    )
    for scenario in SCENARIOS:
        print(
            f"COST_SCENARIO={scenario.name}|"
            f"SPREAD_PIPS={scenario.spread_pips:.2f}|"
            f"COMMISSION_ROUNDTRIP_PIPS="
            f"{scenario.commission_roundtrip_pips:.2f}|"
            f"SLIPPAGE_ENTRY_PIPS={scenario.slippage_entry_pips:.2f}|"
            f"SLIPPAGE_EXIT_PIPS={scenario.slippage_exit_pips:.2f}|"
            f"ALL_IN_PIPS={scenario.total_pips:.2f}"
        )
        measured = {
            name: _metrics(result.trades, scenario)
            for name, result in variants.items()
        }
        for name, item in measured.items():
            _print_metrics(label, scenario, name, item)

        # Розклад гібрида за напрямками без нового Replay або selection.
        directional = {}
        for direction in (DIRECTION_UP, DIRECTION_DOWN):
            subset = [
                trade for trade in hybrid.trades
                if trade.direction == direction
            ]
            item = _metrics(subset, scenario)
            directional[direction] = item
            print(
                f"HYBRID_DIRECTION_NET|PERIOD={label}|"
                f"SCENARIO={scenario.name}|DIRECTION={direction}|"
                f"CLOSED={item.closed}|GROSS_PIPS={item.gross_pips:.2f}|"
                f"COST_PIPS={item.costs_pips:.2f}|"
                f"NET_PIPS={item.net_pips:.2f}|"
                f"PF_NET={item.profit_factor_net:.3f}"
            )
        assert math.isclose(
            math.fsum(item.net_pips for item in directional.values()),
            measured[VARIANTS[2]].net_pips,
            abs_tol=EPS,
        )
        hybrid_net = measured[VARIANTS[2]].net_pips
        base_net = measured[VARIANTS[0]].net_pips
        full_net = measured[VARIANTS[1]].net_pips
        assert math.isclose(
            hybrid_net - base_net,
            gross[VARIANTS[2]] - gross[VARIANTS[0]],
            abs_tol=EPS,
        )
        assert math.isclose(
            hybrid_net - full_net,
            gross[VARIANTS[2]] - gross[VARIANTS[1]],
            abs_tol=EPS,
        )
        if break_even > 0:
            assert (hybrid_net > EPS) == (
                scenario.total_pips < break_even - EPS
            )
        else:
            assert hybrid_net < 0
        print(
            f"NET_DELTA|PERIOD={label}|SCENARIO={scenario.name}|"
            f"HYBRID_MINUS_ALLIGATOR={hybrid_net - base_net:.2f}|"
            f"HYBRID_MINUS_ALL33={hybrid_net - full_net:.2f}"
        )
    print(
        f"T115_09_BASELINE_IDENTICAL={label}:OK|"
        f"HYBRID_TWICE_DETERMINISTIC={label}:OK|"
        f"COST_ACCOUNTING={label}:OK"
    )


def main() -> None:
    """Один TEST_ONLY контроль; ніяких змін у робочому коді."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(p): _fingerprint(p) for p in guarded}
    print("T115-10|TEST_ONLY|DIRECTIONAL_HYBRID_COST_SENSITIVITY")
    print("SOURCE=MID_OHLC_ONLY|COSTS=HYPOTHETICAL_NOT_BROKER_QUOTED")
    print("POST_HOC_HYBRID=True|33_PERCENT=HYPOTHESIS_ONLY")
    print("PRICES=UNCHANGED_MID_REPLAY|COSTS_APPLIED_AFTER_CLOSE")
    _synthetic_cost_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|"
        f"REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS="
        f"{profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {str(p): _fingerprint(p) for p in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|open_position_costs_excluded=True")
    print("costs_hypothetical=True|actual_bid_ask_quotes_used=False")
    print("production_changed=False|md7_changed=False")
    print("T115_10_DIRECTIONAL_HYBRID_COST_SENSITIVITY=OK")


if __name__ == "__main__":
    main()
