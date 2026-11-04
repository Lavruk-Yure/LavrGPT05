# -*- coding: utf-8 -*-
"""RoadMap115 / T115-11 — анатомія збиткових SELL (TEST_ONLY).

Не змінює симулятори T115-02/03/09 і не вводить торгових умов.
SELL = гібрид T115-09: 33% від running positive completed-close peak
або ENDING. Усі ціни — M15 mid OHLC, витрати лише в окремій
гіпотетичній колонці 0.40 pip на закриту угоду.

STARTING до входу, MFE за completed close і подальший outcome —
ретроспективні labels, НЕ причинне доведення запізнення входу.
High/low не використовуються. Гепи не заповнюються синтетично.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from T115_01_Alligator_Entry_Only_Events import (  # noqa: E402
    Bar,
    CANONICAL_2026_END,
    M15,
    PERIODS,
    _aggregate_m1,
    _profile,
)
from T115_02_Alligator_Exit_Only_Trades import (  # noqa: E402
    ClosedTrade,
    DIRECTION_DOWN,
    ObservedState,
    PIP,
    _fingerprint,
    _simulate,
    _states,
)
from T115_03_Alligator_Exit_33Pct_Hypothesis import (  # noqa: E402
    EXIT_33_REASON,
    _simulate_variant,
)
from T115_04_Alligator_Trend_Coverage_Audit_FIXED import (  # noqa: E402
    Observation,
    Trend,
    _trade_index,
    _trends,
)
from T115_09_Directional_Hybrid_Exit_Replay import (  # noqa: E402
    HYBRID_33_DIRECTIONS,
    _check_trade_selection,
    _simulate_directional,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_FLAT,
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_ENDING,
    ALLIGATOR_REGIME_PHASE_NONE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-7
COST_STRESS_PIPS = 0.40


@dataclass(frozen=True, slots=True)
class SellRow:
    """Один завершений SELL: торгові результати й outcome мітки."""

    entry_at: datetime
    pips: float
    baseline_pips: float
    reason: str
    exit_gap: bool
    internal_gap: bool
    starting_bars: int
    pre_entry_move_pips: float | None
    active_bars: int
    held_active_bars: int
    best_close_pips: float
    first_close_pips: float
    last_close_pips: float
    early_tail_pips: float
    exit_fill_delta_pips: float


def _starting_run(
    steps: list[tuple[Bar, Observation]],
    active_index: int,
) -> tuple[int, float | None]:
    """Лише суміжні попередні STARTING того самого SELL regime."""
    cursor = active_index - 1
    while cursor >= 0:
        bar, obs = steps[cursor]
        following = steps[cursor + 1][0]
        if following.timestamp != bar.timestamp + M15:
            break
        if obs.regime_phase != ALLIGATOR_REGIME_PHASE_STARTING:
            break
        if obs.regime != ALLIGATOR_REGIME_TREND_DOWN:
            break
        cursor -= 1
    first = cursor + 1
    count = active_index - first
    return count, steps[first][0].close if count else None


def _one_sell(
    steps: list[tuple[Bar, Observation]],
    index: dict[datetime, int],
    trend: Trend,
    hybrid: ClosedTrade,
    baseline: ClosedTrade,
) -> SellRow:
    """Вимірювання completed closes тільки до фактичного fill виходу."""
    assert trend.direction == DIRECTION_DOWN
    assert trend.end_signal_index is not None
    assert hybrid.direction == baseline.direction == DIRECTION_DOWN
    assert hybrid.entry_at == baseline.entry_at
    assert hybrid.entry_price == baseline.entry_price
    assert hybrid.exit_at <= baseline.exit_at
    assert baseline.exit_reason == "ENDING"
    assert hybrid.exit_reason in {EXIT_33_REASON, "ENDING"}
    entry_idx = index[hybrid.entry_at]
    exit_idx = index[hybrid.exit_at]
    assert entry_idx == trend.start_index + 1
    assert exit_idx > entry_idx
    assert steps[trend.start_index][1].available_at == hybrid.entry_at
    assert steps[exit_idx - 1][1].available_at <= hybrid.exit_at
    exit_signal_phase = steps[exit_idx - 1][1].regime_phase
    if hybrid.exit_reason == "ENDING":
        assert exit_signal_phase == ALLIGATOR_REGIME_PHASE_ENDING
    else:
        assert exit_signal_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    before_fill = steps[entry_idx:exit_idx]
    assert before_fill
    assert all(candle.timestamp < hybrid.exit_at for candle, _ in before_fill)
    close_pips = [
        (hybrid.entry_price - candle.close) / PIP
        for candle, _ in before_fill
    ]
    starting_count, starting_close = _starting_run(steps, trend.start_index)
    pre_move = (
        (starting_close - hybrid.entry_price) / PIP
        if starting_close is not None else None
    )
    end_idx = trend.end_signal_index
    active_bars = end_idx - trend.start_index
    held_active_bars = sum(
        obs.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        for _, obs in before_fill
    )
    segment = steps[trend.start_index:end_idx + 1]
    internal_gap = any(
        right[0].timestamp != left[0].timestamp + M15
        for left, right in zip(segment, segment[1:])
    )
    signal_close = steps[exit_idx - 1][0].close
    return SellRow(
        entry_at=hybrid.entry_at,
        pips=hybrid.pips,
        baseline_pips=baseline.pips,
        reason=hybrid.exit_reason,
        exit_gap=hybrid.exit_gap,
        internal_gap=internal_gap,
        starting_bars=starting_count,
        pre_entry_move_pips=pre_move,
        active_bars=active_bars,
        held_active_bars=held_active_bars,
        best_close_pips=max(close_pips),
        first_close_pips=close_pips[0],
        last_close_pips=close_pips[-1],
        early_tail_pips=baseline.pips - hybrid.pips,
        exit_fill_delta_pips=(signal_close - hybrid.exit_price) / PIP,
    )


def _analyze(
    steps: list[tuple[Bar, Observation]],
) -> tuple[list[SellRow], int, int, int]:
    """Повна популяція SELL з незмінних T115-02/03/09 Replay."""
    baseline = _simulate(steps)
    full33 = _simulate_variant(steps, use_33=True)
    hybrid = _simulate_directional(steps, use_33_for=HYBRID_33_DIRECTIONS)
    _check_trade_selection(baseline, full33, hybrid)
    trends = _trends(steps)
    base_index = _trade_index(baseline.trades)
    hybrid_index = _trade_index(hybrid.trades)
    index = {bar.timestamp: i for i, (bar, _) in enumerate(steps)}
    assert len(index) == len(steps)
    assert baseline.entry_signals == len(trends)
    rows: list[SellRow] = []
    no_entry_sell = open_sell = 0
    observed_sell = 0
    for trend in trends:
        if trend.direction != DIRECTION_DOWN:
            continue
        observed_sell += 1
        entry_time = steps[trend.start_index][1].available_at
        next_index = trend.start_index + 1
        can_enter = (
            next_index < len(steps)
            and steps[next_index][0].timestamp == entry_time
        )
        if not can_enter:
            no_entry_sell += 1
            continue
        trade = hybrid_index.get(entry_time)
        base = base_index.get(entry_time)
        if trade is None:
            assert base is None and trend.end_signal_index is None
            open_sell += 1
            continue
        assert base is not None
        rows.append(_one_sell(steps, index, trend, trade, base))
    assert len(rows) + no_entry_sell + open_sell == observed_sell
    assert sum(row.reason == EXIT_33_REASON for row in rows) == sum(
        trade.direction == DIRECTION_DOWN
        and trade.exit_reason == EXIT_33_REASON for trade in hybrid.trades
    )
    assert math.isclose(
        math.fsum(row.pips for row in rows),
        math.fsum(t.pips for t in hybrid.trades
                  if t.direction == DIRECTION_DOWN),
        abs_tol=EPS,
    )
    return rows, observed_sell, no_entry_sell, open_sell


def _sum(rows: list[SellRow]) -> float:
    return math.fsum(row.pips for row in rows)


def _median(values: list[float | int]) -> str:
    return f"{statistics.median(values):.2f}" if values else "NA"


def _report(label: str, rows: list[SellRow]) -> None:
    """Розділити збиткові ордери за ознаками входу й виходу."""
    losses = [row for row in rows if row.pips < -EPS]
    wins = [row for row in rows if row.pips > EPS]
    flats = [row for row in rows if abs(row.pips) <= EPS]
    no_good_close = [
        row for row in losses if row.best_close_pips <= EPS
    ]
    favorable_lost = [
        row for row in losses if row.best_close_pips > EPS
    ]
    assert len(losses) == len(no_good_close) + len(favorable_lost)
    assert len(rows) == len(losses) + len(wins) + len(flats)
    print(
        f"SELL_PNL|PERIOD={label}|CLOSED={len(rows)}|WINS={len(wins)}|"
        f"LOSSES={len(losses)}|FLAT={len(flats)}|GROSS_PIPS={_sum(rows):.2f}|"
        f"NET_AT_040_PIPS={_sum(rows) - len(rows) * COST_STRESS_PIPS:.2f}"
    )
    print(
        f"SELL_LOSS_ANATOMY|PERIOD={label}|"
        f"NO_FAVORABLE_COMPLETED_CLOSE={len(no_good_close)}|"
        f"NO_FAVORABLE_LOSS_PIPS={_sum(no_good_close):.2f}|"
        f"FAVORABLE_THEN_LOSS={len(favorable_lost)}|"
        f"FAVORABLE_THEN_LOSS_PIPS={_sum(favorable_lost):.2f}|"
        f"MEDIAN_BEST_CLOSE_PRIOR_LOSS_PIPS="
        f"{_median([r.best_close_pips for r in favorable_lost])}"
    )
    for reason in (EXIT_33_REASON, "ENDING"):
        subset = [row for row in rows if row.reason == reason]
        lost = [row for row in subset if row.pips < -EPS]
        loss_amount = _sum(lost)
        print(
            f"EXIT_REASON={reason}|PERIOD={label}|"
            f"CLOSED={len(subset)}|LOSSES={len(lost)}|"
            f"LOSS_PIPS={loss_amount:.2f}|GROSS_PIPS={_sum(subset):.2f}|"
            f"FAVORABLE_THEN_LOSS={sum(
                row.best_close_pips > EPS for row in lost
            )}"
        )
    for bucket, predicate in (
        ("1_TO_3", lambda r: r.active_bars <= 3),
        ("4_TO_11", lambda r: 4 <= r.active_bars <= 11),
        ("12_PLUS", lambda r: r.active_bars >= 12),
    ):
        subset = [row for row in rows if predicate(row)]
        lost = [row for row in subset if row.pips < -EPS]
        print(
            f"ACTIVE_TREND_BARS={bucket}|PERIOD={label}|"
            f"CLOSED={len(subset)}|LOSSES={len(lost)}|"
            f"LOSS_PIPS={_sum(lost):.2f}|GROSS_PIPS={_sum(subset):.2f}"
        )
    pre = [row for row in rows if row.pre_entry_move_pips is not None]
    pre_loss = [row for row in losses if row.pre_entry_move_pips is not None]
    pre_entry_moves = [
        row.pre_entry_move_pips
        for row in pre
        if row.pre_entry_move_pips is not None
    ]
    pre_entry_median = _median(pre_entry_moves)
    print(
        f"PRE_ENTRY_STARTING|PERIOD={label}|"
        f"OBSERVED={len(pre)}|NO_CONTIGUOUS_STARTING="
        f"{len(rows) - len(pre)}|"
        f"MEDIAN_STARTING_BARS={_median([r.starting_bars for r in pre])}|"
        f"MEDIAN_PRE_ENTRY_SELL_MOVE_PIPS={pre_entry_median}|"
        f"LOSSES_WITH_STARTING={len(pre_loss)}|"
        f"LOSSES_PRE_MOVE_FAVORABLE={sum(
            row.pre_entry_move_pips is not None
            and row.pre_entry_move_pips > EPS for row in pre_loss
        )}|LOSSES_PRE_MOVE_NOT_FAVORABLE={sum(
            row.pre_entry_move_pips is not None
            and row.pre_entry_move_pips <= EPS for row in pre_loss
        )}"
    )
    early = [row for row in rows if row.reason == EXIT_33_REASON]
    save = [row for row in early if row.early_tail_pips < -EPS]
    hurt = [row for row in early if row.early_tail_pips > EPS]
    same = [row for row in early if abs(row.early_tail_pips) <= EPS]
    print(
        f"EXIT_ATTRIBUTION|PERIOD={label}|EARLY_33={len(early)}|"
        f"EARLY_BETTER={len(save)}|HOLD_BETTER={len(hurt)}|"
        f"SAME={len(same)}|"
        f"SAVED_GROSS_PIPS={-math.fsum(r.early_tail_pips for r in save):.2f}|"
        f"MISSED_GROSS_PIPS={math.fsum(r.early_tail_pips for r in hurt):.2f}|"
        f"GAP_AFFECTED={sum(r.exit_gap for r in rows)}"
    )
    print(
        f"LOSS_EXIT_DIAGNOSTIC|PERIOD={label}|"
        f"MEDIAN_MFE_CLOSE_PIPS="
        f"{_median([r.best_close_pips for r in losses])}|"
        f"FIRST_CLOSE_FAVORABLE={sum(
            r.first_close_pips > EPS for r in losses
        )}|EXIT_FILL_WORSE_THAN_SIGNAL_CLOSE={sum(
            r.exit_fill_delta_pips < -EPS for r in losses
        )}|INTERNAL_GAP_LOSSES={sum(r.internal_gap for r in losses)}"
    )


def _synthetic_checks() -> None:
    """Синтетично: хороший SELL close, віддача прибутку, збитковий fill."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    down = ALLIGATOR_REGIME_TREND_DOWN

    def sample(
        offset: int, opening: float, closing: float,
        phase: str, regime: str = down,
    ) -> tuple[Bar, ObservedState]:
        timestamp = start + offset * M15
        bar = Bar(
            timestamp, opening, max(opening, closing) + PIP,
            min(opening, closing) - PIP, closing,
        )
        return bar, ObservedState(
            timestamp, timestamp + M15, phase, regime,
        )

    steps: list[tuple[Bar, Observation]] = [
        sample(0, 1.1010, 1.1010, ALLIGATOR_REGIME_PHASE_STARTING),
        sample(1, 1.1008, 1.1006, ALLIGATOR_REGIME_PHASE_STARTING),
        sample(2, 1.1006, 1.1005, ALLIGATOR_REGIME_PHASE_ACTIVE),
        sample(3, 1.1004, 1.1002, ALLIGATOR_REGIME_PHASE_ACTIVE),
        sample(4, 1.1002, 1.1009, ALLIGATOR_REGIME_PHASE_ACTIVE),
        sample(5, 1.1008, 1.1008, ALLIGATOR_REGIME_PHASE_ACTIVE),
        sample(6, 1.1009, 1.1009, ALLIGATOR_REGIME_PHASE_ENDING),
        sample(7, 1.1010, 1.1010, ALLIGATOR_REGIME_PHASE_NONE,
               ALLIGATOR_REGIME_FLAT),
    ]
    rows, all_sell, no_entry, open_sell = _analyze(steps)
    assert (all_sell, no_entry, open_sell, len(rows)) == (1, 0, 0, 1)
    row = rows[0]
    assert row.reason == EXIT_33_REASON and row.pips < 0
    assert row.best_close_pips > 0 and row.starting_bars == 2
    assert row.pre_entry_move_pips is not None
    assert row.pre_entry_move_pips > 0
    assert row.early_tail_pips < 0  # У цьому сценарії 33% рятує.

    # Розрив після signal: exit лише на наступному *наявному* open.
    gapped = [*steps[:5], *steps[6:]]
    gap_rows, count, skipped, opened = _analyze(gapped)
    assert (count, skipped, opened) == (1, 0, 0)
    assert len(gap_rows) == 1 and gap_rows[0].exit_gap
    print("SYNTHETIC_SELL_ENTRY_EXIT_CAUSALITY=OK")


def _run_period(label: str, filename: str, expected: tuple, profile) -> None:
    """Два повторення аудиту та жодної зміни популяції входів."""
    path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source, selected, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    steps = list(_states(bars, profile))
    assert len(bars) == expected[0]
    first = _analyze(steps)
    second = _analyze(steps)
    assert first == second, f"NONDETERMINISTIC: {label}"
    rows, signal_sell, no_entry, open_sell = first
    expected_sells = 408 if label == "2025" else 277
    expected_gross = -472.70 if label == "2025" else -130.60
    expected_early = 233 if label == "2025" else 180
    assert len(rows) == expected_sells
    assert math.isclose(_sum(rows), expected_gross, abs_tol=EPS)
    assert sum(r.reason == EXIT_33_REASON for r in rows) == expected_early
    assert signal_sell == expected[3]  # T115-01 SELL signals
    assert no_entry + len(rows) + open_sell == signal_sell
    print(
        f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"SELL_SIGNALS={signal_sell}|WITH_ENTRY={len(rows) + open_sell}|"
        f"WITHOUT_ENTRY={no_entry}|CLOSED={len(rows)}|"
        f"OPEN_AT_END={open_sell}"
    )
    _report(label, rows)
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK|T115_09_BASELINE=OK")


def main() -> None:
    """Виконати тільки дослідницький аудит локальної історії."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-11|TEST_ONLY|SELL_ENTRY_VS_EXIT_LOSS_ANATOMY")
    print("HYBRID=BUY_ENDING_SELL_33_OR_ENDING|OUTCOME_ONLY=True")
    print("NO_LOOK_AHEAD_IN_TRADE_DECISIONS=True|NO_REAL_BID_ASK=True")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|costs_hypothetical=True|TEST_ONLY=True")
    print("production_changed=False|md7_changed=False")
    print("T115_11_SELL_ENTRY_EXIT_LOSS_ANATOMY=OK")


if __name__ == "__main__":
    main()
