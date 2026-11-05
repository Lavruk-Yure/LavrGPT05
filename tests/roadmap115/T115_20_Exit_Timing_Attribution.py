# -*- coding: utf-8 -*-
"""RoadMap115 / T115-20 — exit timing attribution (TEST_ONLY).

M30 (4→2 bars), H1 (4→1 bar); 2025 та 2026 до 25.08 UTC.
Однаковий replay із T115-19: BUY закривається за Alligator,
SELL — за Alligator або 33% від позитивного peak completed close.

Досліджуємо лише ЗАВЕРШЕНІ парні позиції одного causal episode.
Вимірюємо зміну ціни виходу за переходами причин EXIT_33/ENDING/
інших штатних причин і відокремлюємо її від зміни входу та статусу.
Збіг причини виходу сам собою НЕ означає однакову ціну/час виходу.
Тільки ретроспективна бухгалтерія, НЕ причинний ефект 33% exit.

Mid OHLC, умовні round-trip витрати 0.40 pip, без broker fills.
Нереалізовані відкриті позиції не включено. Без production змін.
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
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    _synthetic_checks as _synthetic_33_checks,
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
    _attribute,
    _run_pair,
    _synthetic_attribution,
    _synthetic_episode_link,
    _trade_lookup,
)
from T115_19_Paired_Entry_Exit_Timing_Decomposition import (  # noqa: E402
    Decomposition,
    _decompose,
    _signed_direction,
    _synthetic_prices,
)

EXIT_REASONS = frozenset({
    EXIT_33_REASON, "ENDING", "STARTING", "NONE", "OPPOSITE_ACTIVE",
})
EXPECTED_EXIT = {
    "2025": {30: -6.70, 60: -44.20},
    "2026_TO_2026_08_25": {30: 112.90, 60: 92.70},
}


@dataclass(frozen=True, slots=True)
class ExitPair:
    """Фактичний вихід пари угод і точний exit-price внесок."""

    episode: int
    direction: str
    base_reason: str
    trial_reason: str
    base_exit_at: datetime
    trial_exit_at: datetime
    base_exit_price: float
    trial_exit_price: float
    exit_part: float
    entry_part: float
    exit_gap_base: bool
    exit_gap_trial: bool

    @property
    def transition(self) -> str:
        return f"{self.base_reason}>{self.trial_reason}"

    @property
    def exit_shift_minutes(self) -> int:
        return int((
            self.base_exit_at - self.trial_exit_at
        ).total_seconds() // 60)


def _exit_pairs(
    old: dict[int, ClosedTrade],
    new: dict[int, ClosedTrade],
    rows: list[Decomposition],
) -> list[ExitPair]:
    """Зіставити вже завершені парні позиції без повторного Replay."""
    pairs: list[ExitPair] = []
    for row in rows:
        if row.closed_class != "BOTH_CLOSED":
            continue
        base = old[row.episode]
        trial = new[row.episode]
        assert base.direction == trial.direction == row.direction
        assert base.exit_reason in EXIT_REASONS
        assert trial.exit_reason in EXIT_REASONS
        if row.direction == DIRECTION_UP:
            assert base.exit_reason != EXIT_33_REASON
            assert trial.exit_reason != EXIT_33_REASON
        factor = _signed_direction(row.direction)
        exit_pips = factor * (
            trial.exit_price - base.exit_price
        ) / PIP
        assert math.isclose(
            exit_pips, row.exit_price_part, abs_tol=EPS,
        )
        assert (base.exit_at == trial.exit_at) == (
            row.same_exit_at is True
        )
        assert (base.exit_reason == trial.exit_reason) == (
            row.same_exit_reason is True
        )
        if base.exit_at == trial.exit_at:
            assert math.isclose(exit_pips, 0.0, abs_tol=EPS)
        pairs.append(ExitPair(
            episode=row.episode,
            direction=row.direction,
            base_reason=base.exit_reason,
            trial_reason=trial.exit_reason,
            base_exit_at=base.exit_at,
            trial_exit_at=trial.exit_at,
            base_exit_price=base.exit_price,
            trial_exit_price=trial.exit_price,
            exit_part=exit_pips,
            entry_part=row.entry_price_part,
            exit_gap_base=base.exit_gap,
            exit_gap_trial=trial.exit_gap,
        ))
    assert len(pairs) == sum(
        row.closed_class == "BOTH_CLOSED" for row in rows
    )
    assert math.isclose(
        math.fsum([p.exit_part for p in pairs]),
        math.fsum([row.exit_price_part for row in rows]),
        abs_tol=EPS,
    )
    return pairs


def _fmt(value: float) -> str:
    return f"{value:+.2f}"


def _median(values: list[int]) -> str:
    return f"{statistics.median(values):.1f}" if values else "NONE"


def _synthetic_reason_bridge() -> None:
    """BUY/SELL і різні причини: знак та часовий зсув."""
    start = datetime(2025, 1, 6, tzinfo=UTC)
    old = ExitPair(
        episode=1,
        direction=DIRECTION_DOWN,
        base_reason="ENDING",
        trial_reason=EXIT_33_REASON,
        base_exit_at=start + timedelta(hours=6),
        trial_exit_at=start + timedelta(hours=4),
        base_exit_price=1.1030,
        trial_exit_price=1.1040,
        exit_part=-10.0,
        entry_part=5.0,
        exit_gap_base=False,
        exit_gap_trial=False,
    )
    assert old.transition == f"ENDING>{EXIT_33_REASON}"
    assert old.exit_shift_minutes == 120
    assert math.isclose(
        _signed_direction(old.direction) * (
            old.trial_exit_price - old.base_exit_price
        ) / PIP, old.exit_part, abs_tol=EPS,
    )
    buy = ExitPair(
        episode=2,
        direction=DIRECTION_UP,
        base_reason="ENDING",
        trial_reason="ENDING",
        base_exit_at=start + timedelta(hours=6),
        trial_exit_at=start + timedelta(hours=6),
        base_exit_price=1.1020,
        trial_exit_price=1.1020,
        exit_part=0.0,
        entry_part=8.0,
        exit_gap_base=False,
        exit_gap_trial=False,
    )
    assert buy.exit_shift_minutes == 0
    assert math.isclose(buy.exit_part, 0.0, abs_tol=EPS)
    assert EXIT_33_REASON not in buy.transition
    print("SYNTHETIC_EXIT_REASON_PRICE_BRIDGE=OK")


def _report(
    label: str, minutes: int,
    old: dict[int, ClosedTrade],
    new: dict[int, ClosedTrade],
    rows: list[Decomposition],
    pairs: list[ExitPair],
    base_net: float, trial_net: float,
) -> None:
    """Повна взаємозвірка exit matrix та T115-19 Net bridge."""
    name = TF_NAMES[minutes]
    entry = math.fsum([row.entry_price_part for row in rows])
    exit_part = math.fsum([row.exit_price_part for row in rows])
    status = math.fsum([row.status_part for row in rows])
    delta = trial_net - base_net
    assert math.isclose(
        math.fsum([entry, exit_part, status]), delta,
        abs_tol=EPS,
    )
    assert math.isclose(
        exit_part, EXPECTED_EXIT[label][minutes], abs_tol=EPS,
    )
    print(
        f"EXIT_BRIDGE|TF={name}|PERIOD={label}|"
        f"PAIRED_CLOSED={len(pairs)}|"
        f"ENTRY={_fmt(entry)}|EXIT={_fmt(exit_part)}|"
        f"STATUS={_fmt(status)}|DELTA_NET040={_fmt(delta)}"
    )
    for case, trades in (("BASE", old), ("TRIAL", new)):
        for direction in (DIRECTION_UP, DIRECTION_DOWN):
            group = [
                trade for trade in trades.values()
                if trade.direction == direction
            ]
            by_reason = sorted({trade.exit_reason for trade in group})
            for reason in by_reason:
                subset = [
                    trade for trade in group if trade.exit_reason == reason
                ]
                assert reason in EXIT_REASONS
                assert direction != DIRECTION_UP or (
                    reason != EXIT_33_REASON
                )
                gross = math.fsum([trade.pips for trade in subset])
                print(
                    f"EXIT_COUNTS|TF={name}|PERIOD={label}|"
                    f"CASE={case}|SIDE={direction}|REASON={reason}|"
                    f"CLOSED={len(subset)}|GROSS={_fmt(gross)}|"
                    f"NET040={_fmt(gross - NET_COST_PIPS * len(subset))}|"
                    f"EXIT_GAP={sum(t.exit_gap for t in subset)}"
                )
    for direction in (DIRECTION_UP, DIRECTION_DOWN):
        selected = [p for p in pairs if p.direction == direction]
        cause_pairs = sorted({p.transition for p in selected})
        sum_by_cause = 0.0
        for cause in cause_pairs:
            subset = [p for p in selected if p.transition == cause]
            contribution = math.fsum([p.exit_part for p in subset])
            sum_by_cause += contribution
            shifts = [p.exit_shift_minutes for p in subset]
            entry_subtotal = math.fsum([
                p.entry_part for p in subset
            ])
            gap_cases = sum(
                p.exit_gap_base or p.exit_gap_trial for p in subset
            )
            print(
                f"PAIRED_EXIT|TF={name}|PERIOD={label}|"
                f"SIDE={direction}|REASONS={cause}|"
                f"COUNT={len(subset)}|EXIT_PART={_fmt(contribution)}|"
                f"ENTRY_PART={_fmt(entry_subtotal)}|"
                f"SAME_EXIT_AT={sum(s == 0 for s in shifts)}|"
                f"MEDIAN_BASE_MINUS_TRIAL_EXIT_MIN={_median(shifts)}|"
                f"GAP_CASES={gap_cases}"
            )
        expected = math.fsum([p.exit_part for p in selected])
        assert math.isclose(sum_by_cause, expected, abs_tol=EPS)
        print(
            f"EXIT_DIRECTION|TF={name}|PERIOD={label}|"
            f"SIDE={direction}|PAIRED={len(selected)}|"
            f"EXIT_PART={_fmt(expected)}"
        )
    transition_total = math.fsum([p.exit_part for p in pairs])
    assert math.isclose(transition_total, exit_part, abs_tol=EPS)
    for rank, item in enumerate(sorted(
        pairs, key=lambda p: (-abs(p.exit_part), p.episode)
    )[:3], 1):
        print(
            f"EXIT_CASE|TF={name}|PERIOD={label}|RANK={rank}|"
            f"EPISODE={item.episode}|SIDE={item.direction}|"
            f"BASE_REASON={item.base_reason}|"
            f"TRIAL_REASON={item.trial_reason}|"
            f"EXIT_PART={_fmt(item.exit_part)}|"
            f"EXIT_SHIFT_MIN={item.exit_shift_minutes}"
        )
    print(f"EXIT_REASON_RECONCILIATION={name}:{label}:OK")


def main() -> None:
    """Не міняти логіку симуляції; аналізувати завершені Replay."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    assert all(path.is_file() for path in guarded)
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-20|TEST_ONLY|EXIT_TIMING_ATTRIBUTION")
    print("TIMEFRAMES=M30,H1|BASE=4_BARS|TRIAL_M30=2|TRIAL_H1=1")
    print("PAIRED_CLOSED_ONLY=True|UNMATCHED_EXCLUDED_FROM_EXIT=True")
    print("EXIT=POST_HOC_PRICE_BRIDGE|NOT_CAUSAL_33_EFFECT=True")
    print("NET040=HYPOTHETICAL|ENTRY_EXIT_SIM_UNCHANGED=True")
    _synthetic_check()
    _synthetic_33_checks()
    _synthetic_confirmation()
    _synthetic_attribution()
    _synthetic_episode_link()
    _synthetic_prices()
    _synthetic_reason_bridge()
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
            base, trial, trace = _run_pair(aggregated[minutes], minutes)
            _regression(label, minutes, base)
            assert math.isclose(
                _net(base), EXPECTED_NET[label][minutes][0],
                abs_tol=EPS,
            )
            assert math.isclose(
                _net(trial), EXPECTED_NET[label][minutes][1],
                abs_tol=EPS,
            )
            old, _ = _trade_lookup(base, trace.baseline)
            new, _ = _trade_lookup(trial, trace.trial)
            outcome = _attribute(base, trial, trace)
            rows = _decompose(old, new, trace, outcome)
            pairs = _exit_pairs(old, new, rows)
            print(
                f"BASE|TF={TF_NAMES[minutes]}|PERIOD={label}|"
                f"{_summary(base, NET_COST_PIPS)}"
            )
            print(
                f"TRIAL|TF={TF_NAMES[minutes]}|PERIOD={label}|"
                f"{_summary(trial, NET_COST_PIPS)}"
            )
            _report(
                label, minutes, old, new, rows, pairs,
                _net(base), _net(trial),
            )
            print(
                f"REPLAY_MIRROR_DETERMINISTIC={TF_NAMES[minutes]}:"
                f"{label}:OK"
            )
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_20_EXIT_TIMING_ATTRIBUTION=OK")


if __name__ == "__main__":
    main()
