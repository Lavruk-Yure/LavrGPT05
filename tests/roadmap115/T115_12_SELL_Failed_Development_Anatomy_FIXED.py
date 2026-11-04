# -*- coding: utf-8 -*-
"""RoadMap115 / T115-12 — анатомія SELL без сприятливого close.

TEST_ONLY. Незмінні сигнал, вхід і вихід гібрида T115-09/11.
Контрольна подія: збитковий SELL без позитивного completed M15 close
до фактичного виходу. Ознаки на сигнальному close й entry open
відокремлено від наступних 1–3 completed M15 close.

Пізніші close та факт збитку — тільки ретроспективні outcome labels,
не торгові фільтри. Результати не доводять причинність чи прогностичну
здатність. Немає MACD, торгових витрат, broker calls або look-ahead
у чинних моделях прийняття рішень. Жодних змін production/MD7.
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
    ObservedState,
    PIP,
    _fingerprint,
    _states,
)
from T115_04_Alligator_Trend_Coverage_Audit_FIXED import (  # noqa: E402
    Observation,
    Trend,
    _trends,
)
from T115_09_Directional_Hybrid_Exit_Replay import (  # noqa: E402
    HYBRID_33_DIRECTIONS,
    _simulate_directional,
)
from T115_11_SELL_Entry_Exit_Loss_Anatomy_FIXED import (  # noqa: E402
    EPS,
    SellRow,
    _analyze,
    _starting_run,
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

FAILED = "FAILED_NO_FAVORABLE_CLOSE"
OTHER_LOSS = "OTHER_LOSS"
NON_LOSS = "NON_LOSS"


@dataclass(frozen=True, slots=True)
class Evidence:
    """Ознаки entry та відкладені мітки того самого завершеного SELL."""

    entry_at: datetime
    group: str
    pips: float
    starting_bars: int
    starting_to_signal_pips: float | None
    signal_body_sell_pips: float
    signal_range_pips: float
    prior_three_to_signal_pips: float | None
    signal_to_entry_open_pips: float
    post_entry_close_pips: tuple[
        float | None, float | None, float | None
    ]
    exit_gap: bool
    internal_gap: bool


def _classify(row: SellRow) -> str:
    """Той самий outcome-критерій, що в T115-11, без змін."""
    if row.pips >= -EPS:
        return NON_LOSS
    if row.best_close_pips <= EPS:
        return FAILED
    return OTHER_LOSS


def _prior_three_move(
    steps: list[tuple[Bar, Observation]], signal: int,
) -> float | None:
    """Три суміжні попередні M15 та сигнальний close, без майбутнього."""
    if signal < 3:
        return None
    for i in range(signal - 2, signal + 1):
        if steps[i][0].timestamp != steps[i - 1][0].timestamp + M15:
            return None
    return (steps[signal - 3][0].close - steps[signal][0].close) / PIP


def _first_three_closes(
    steps: list[tuple[Bar, Observation]],
    row: SellRow,
    entry_index: int,
    entry_price: float,
    exit_at: datetime,
) -> tuple[float | None, float | None, float | None]:
    """Постфактум: лише 1–3 суміжні completed close до exit fill."""
    values: list[float | None] = []
    for offset in range(3):
        index = entry_index + offset
        expected = row.entry_at + offset * M15
        if index >= len(steps):
            break
        candle, obs = steps[index]
        if candle.timestamp != expected:
            break
        if obs.available_at != candle.timestamp + M15:
            raise AssertionError("M15_COMPLETION_MISMATCH")
        if row.entry_at < obs.available_at <= exit_at:
            values.append((entry_price - candle.close) / PIP)
        else:
            break
    values.extend([None] * (3 - len(values)))
    return values[0], values[1], values[2]


def _one_evidence(
    steps: list[tuple[Bar, Observation]],
    index: dict[datetime, int],
    trends: dict[datetime, Trend],
    row: SellRow,
    exit_at: datetime,
) -> Evidence:
    """Розділити entry-time context та наступні outcome labels."""
    trend = trends[row.entry_at]
    signal_index = trend.start_index
    entry_index = index[row.entry_at]
    signal_bar, signal_obs = steps[signal_index]
    entry_bar, _ = steps[entry_index]
    assert entry_index == signal_index + 1
    assert row.entry_at == signal_obs.available_at == entry_bar.timestamp
    assert signal_obs.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
    assert signal_obs.regime == ALLIGATOR_REGIME_TREND_DOWN
    assert row.starting_bars >= 0
    starting_count, starting_close = _starting_run(steps, signal_index)
    assert starting_count == row.starting_bars
    starting_move = (
        (starting_close - signal_bar.close) / PIP
        if starting_close is not None else None
    )
    return Evidence(
        entry_at=row.entry_at,
        group=_classify(row),
        pips=row.pips,
        starting_bars=starting_count,
        starting_to_signal_pips=starting_move,
        signal_body_sell_pips=(signal_bar.open - signal_bar.close) / PIP,
        signal_range_pips=(signal_bar.high - signal_bar.low) / PIP,
        prior_three_to_signal_pips=_prior_three_move(steps, signal_index),
        signal_to_entry_open_pips=(signal_bar.close - entry_bar.open) / PIP,
        post_entry_close_pips=_first_three_closes(
            steps, row, entry_index, entry_bar.open, exit_at,
        ),
        exit_gap=row.exit_gap,
        internal_gap=row.internal_gap,
    )


def _audit(
    steps: list[tuple[Bar, Observation]],
) -> tuple[Evidence, ...]:
    """Лише індексація незмінних завершених модельних SELL T115-11."""
    rows, sell_signals, missing, opened = _analyze(steps)
    index = {candle.timestamp: i for i, (candle, _) in enumerate(steps)}
    assert len(index) == len(steps)
    trends = {
        steps[trend.start_index][1].available_at: trend
        for trend in _trends(steps)
        if trend.direction == "SELL"
    }
    assert len(trends) == sell_signals
    assert sell_signals == len(rows) + missing + opened
    hybrid = _simulate_directional(
        steps, use_33_for=HYBRID_33_DIRECTIONS,
    )
    trades = {
        trade.entry_at: trade
        for trade in hybrid.trades if trade.direction == "SELL"
    }
    assert len(trades) == len(rows)
    assert all(math.isclose(
        row.pips, trades[row.entry_at].pips, abs_tol=EPS,
    ) for row in rows)
    evidence = tuple(
        _one_evidence(
            steps, index, trends, row, trades[row.entry_at].exit_at,
        )
        for row in rows
    )
    assert len(evidence) == len(rows)
    assert sum(item.group == FAILED for item in evidence) == sum(
        row.pips < -EPS and row.best_close_pips <= EPS for row in rows
    )
    assert math.isclose(
        math.fsum(item.pips for item in evidence),
        math.fsum(row.pips for row in rows),
        abs_tol=EPS,
    )
    return evidence


def _median(values: list[float | int]) -> str:
    return f"{statistics.median(values):.2f}" if values else "NA"


def _groups(items: tuple[Evidence, ...]) -> tuple[int, int, int]:
    return (
        sum(item.group == FAILED for item in items),
        sum(item.group == OTHER_LOSS for item in items),
        sum(item.group == NON_LOSS for item in items),
    )


def _cohort(label: str, name: str, items: list[Evidence]) -> None:
    """Показати частоту невдалих SELL у повній популяції."""
    failed = sum(row.group == FAILED for row in items)
    rate = 100 * failed / len(items) if items else 0.0
    print(
        f"COHORT|PERIOD={label}|FEATURE={name}|N={len(items)}|"
        f"FAILED={failed}|FAILED_RATE_PCT={rate:.2f}"
    )


def _report(label: str, items: tuple[Evidence, ...]) -> None:
    """Лише описова стратифікація, без підбору порогів чи правил."""
    failed, other_loss, non_loss = _groups(items)
    losses = [item for item in items if item.group != NON_LOSS]
    assert failed + other_loss == len(losses)
    print(
        f"POPULATION|PERIOD={label}|CLOSED_SELL={len(items)}|"
        f"FAILED_NO_FAVORABLE_CLOSE={failed}|OTHER_LOSS={other_loss}|"
        f"NON_LOSS={non_loss}|GROSS_SELL_PIPS="
        f"{math.fsum(item.pips for item in items):.2f}"
    )
    bad = [item for item in items if item.group == FAILED]
    good_loss = [item for item in items if item.group == OTHER_LOSS]
    other_bodies = [
        item.signal_body_sell_pips
        for item in items if item.group != FAILED
    ]
    print(
        f"LOSS_SPLIT|PERIOD={label}|FAILED_LOSS_PIPS="
        f"{math.fsum(item.pips for item in bad):.2f}|"
        f"OTHER_LOSS_PIPS={math.fsum(item.pips for item in good_loss):.2f}|"
        f"FAILED_EXIT_GAPS={sum(item.exit_gap for item in bad)}|"
        f"FAILED_INTERNAL_GAPS={sum(item.internal_gap for item in bad)}"
    )
    print(
        f"SIGNAL_MEDIANS|PERIOD={label}|"
        f"FAILED_STARTING_BARS={_median([x.starting_bars for x in bad])}|"
        f"OTHERS_STARTING_BARS="
        f"{_median([x.starting_bars for x in items if x.group != FAILED])}|"
        f"FAILED_SIGNAL_SELL_BODY_PIPS="
        f"{_median([x.signal_body_sell_pips for x in bad])}|"
        f"OTHERS_SIGNAL_SELL_BODY_PIPS={_median(other_bodies)}|"
        f"FAILED_SIGNAL_RANGE_PIPS="
        f"{_median([x.signal_range_pips for x in bad])}|"
        f"OTHERS_SIGNAL_RANGE_PIPS="
        f"{_median([x.signal_range_pips for x in items if x.group != FAILED])}"
    )
    # Пороги лише природні: знак руху та фактична кількість STARTING.
    _cohort(label, "STARTING_NONE", [x for x in items if x.starting_bars == 0])
    _cohort(label, "STARTING_1_TO_2", [
        x for x in items if 1 <= x.starting_bars <= 2
    ])
    _cohort(label, "STARTING_3_PLUS", [
        x for x in items if x.starting_bars >= 3
    ])
    _cohort(label, "SIGNAL_BODY_SELL_POS", [
        x for x in items if x.signal_body_sell_pips > EPS
    ])
    _cohort(label, "SIGNAL_BODY_SELL_NONPOS", [
        x for x in items if x.signal_body_sell_pips <= EPS
    ])
    for name, reader in (
        ("STARTING_TO_SIGNAL", lambda row: row.starting_to_signal_pips),
        ("PRIOR3_TO_SIGNAL", lambda row: row.prior_three_to_signal_pips),
        ("SIGNAL_TO_ENTRY_OPEN", lambda row: row.signal_to_entry_open_pips),
    ):
        known: list[tuple[Evidence, float]] = []
        for item in items:
            value = reader(item)
            if value is not None:
                known.append((item, value))
        _cohort(label, f"{name}_AVAILABLE", [item for item, _ in known])
        _cohort(label, f"{name}_FAVORABLE", [
            item for item, value in known if value > EPS
        ])
        _cohort(label, f"{name}_NONFAVORABLE", [
            item for item, value in known if value <= EPS
        ])
    for horizon in range(1, 4):
        horizon_known: list[Evidence] = [
            item for item in items
            if item.post_entry_close_pips[horizon - 1] is not None
        ]
        favorable = [
            item for item in horizon_known
            if any(
                value is not None and value > EPS
                for value in item.post_entry_close_pips[:horizon]
            )
        ]
        nonfav = len(horizon_known) - len(favorable)
        failed_horizon = sum(x.group == FAILED for x in horizon_known)
        print(
            f"POST_ENTRY_HORIZON|PERIOD={label}|BARS={horizon}|"
            f"AVAILABLE_WHILE_OPEN={len(horizon_known)}|"
            f"NO_FAVORABLE_CLOSE_THROUGH_H={nonfav}|"
            f"ANY_FAVORABLE_CLOSE_THROUGH_H={len(favorable)}|"
            f"FAILED_WITH_DATA={failed_horizon}|"
            f"OTHER_LOSS_WITH_DATA="
            f"{sum(x.group == OTHER_LOSS for x in horizon_known)}|"
            f"NON_LOSS_WITH_DATA="
            f"{sum(x.group == NON_LOSS for x in horizon_known)}"
        )
        _cohort(label, f"POST_H{horizon}_NO_FAVORABLE", [
            item for item in horizon_known if item not in favorable
        ])
        _cohort(label, f"POST_H{horizon}_ANY_FAVORABLE", favorable)
    print(
        f"POST_ENTRY_NOTE|PERIOD={label}|"
        "OUTCOME_COMPONENT_NOT_PREDICTOR=True|"
        "HORIZON_CENSORING_BY_EXIT_AND_GAPS=True"
    )


def _sample(
    start: datetime, offset: int, opening: float,
    closing: float, phase: str,
) -> tuple[Bar, ObservedState]:
    """Синтетичний M15 з явним часом доступності."""
    time = start + offset * M15
    candle = Bar(
        time, opening, max(opening, closing) + PIP,
        min(opening, closing) - PIP, closing,
    )
    return candle, ObservedState(
        time, time + M15, phase,
        ALLIGATOR_REGIME_TREND_DOWN
        if phase != ALLIGATOR_REGIME_PHASE_NONE else ALLIGATOR_REGIME_FLAT,
    )


def _synthetic_checks() -> None:
    """Позитивний, збитковий і розірваний SELL без future close."""
    start = datetime(2025, 1, 6, 12, tzinfo=UTC)
    a = ALLIGATOR_REGIME_PHASE_ACTIVE
    e = ALLIGATOR_REGIME_PHASE_ENDING
    n = ALLIGATOR_REGIME_PHASE_NONE
    s = ALLIGATOR_REGIME_PHASE_STARTING
    failed_steps: list[tuple[Bar, Observation]] = [
        _sample(start, 0, 1.1010, 1.1010, s),
        _sample(start, 1, 1.1008, 1.1007, s),
        _sample(start, 2, 1.1008, 1.1005, a),
        _sample(start, 3, 1.1006, 1.1008, a),
        _sample(start, 4, 1.1008, 1.1009, e),
        _sample(start, 5, 1.1010, 1.1010, n),
    ]
    bad = _audit(failed_steps)
    assert len(bad) == 1 and bad[0].group == FAILED
    assert bad[0].starting_bars == 2
    assert bad[0].post_entry_close_pips[0] is not None
    assert bad[0].post_entry_close_pips[0] < 0
    assert bad[0].post_entry_close_pips[1] is not None
    assert bad[0].post_entry_close_pips[2] is None
    assert bad[0].prior_three_to_signal_pips is None
    # Intrabar extreme не змінює outcome за completed close.
    candle, obs = failed_steps[3]
    noisy = list(failed_steps)
    noisy[3] = Bar(
        candle.timestamp, candle.open, 1.1200, 1.0900,
        candle.close,
    ), obs
    assert _audit(noisy)[0].group == bad[0].group
    assert (
        _audit(noisy)[0].post_entry_close_pips
        == bad[0].post_entry_close_pips
    )
    # Розрив після першого M15: наступні horizon не домальовуються.
    gap_steps: list[tuple[Bar, Observation]] = [
        *failed_steps[:4],
        _sample(start, 6, 1.1008, 1.1009, e),
        _sample(start, 7, 1.1010, 1.1010, n),
    ]
    after_gap = _audit(gap_steps)
    assert len(after_gap) == 1
    assert after_gap[0].post_entry_close_pips[0] is not None
    assert after_gap[0].post_entry_close_pips[1] is None
    assert after_gap[0].post_entry_close_pips[2] is None
    # Є сприятливий close -> не може бути FAILED.
    favorable = list(failed_steps)
    candle, obs = favorable[3]
    favorable[3] = Bar(
        candle.timestamp, candle.open, candle.high,
        1.1003, 1.1004,
    ), obs
    assert _audit(favorable)[0].group != FAILED
    print("SYNTHETIC_SELL_FAILED_DEVELOPMENT_CAUSALITY=OK")


def _run_period(label: str, filename: str, expected: tuple, profile) -> None:
    """Два прогони та звірка з незмінним T115-11."""
    path = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source, selected, bars = _aggregate_m1(path, int(label[:4]), cutoff)
    assert len(bars) == expected[0]
    steps = list(_states(bars, profile))
    first = _audit(steps)
    assert first == _audit(steps), f"NONDETERMINISTIC: {label}"
    expected_count, expected_failed, expected_pips = (
        (408, 112, -472.70) if label == "2025"
        else (277, 61, -130.60)
    )
    assert len(first) == expected_count
    assert sum(item.group == FAILED for item in first) == expected_failed
    assert math.isclose(
        math.fsum(item.pips for item in first),
        expected_pips, abs_tol=EPS,
    )
    print(
        f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|"
        f"CUTOFF_UTC={cutoff.isoformat() if cutoff else 'NONE'}"
    )
    _report(label, first)
    print(f"REPLAY_TWICE_DETERMINISTIC={label}:OK|T115_11_BASELINE=OK")


def main() -> None:
    """Вивести аудит без зміни файлів проєкту й без мережі."""
    protected = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in protected}
    print("T115-12|TEST_ONLY|SELL_FAILED_DEVELOPMENT_ANATOMY")
    print("LABEL=LOSS_AND_NO_FAVORABLE_COMPLETED_CLOSE_BEFORE_EXIT")
    print("FEATURES=SIGNAL_CLOSE_AND_ENTRY_OPEN_ONLY")
    print("POST_ENTRY_CLOSES=OUTCOME_LABELS_ONLY|MAX_HORIZON=3")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    for label, filename, *expected in PERIODS:
        _run_period(label, filename, tuple(expected), profile)
    after = {str(path): _fingerprint(path) for path in protected}
    assert before == after, "PRODUCTION_FINGERPRINT_CHANGED"
    print("completed_bars_only=True|trade_decisions_look_ahead=False")
    print("broker_requests=0|TEST_ONLY=True|costs_hypothetical=True")
    print("production_changed=False|md7_changed=False")
    print("T115_12_SELL_FAILED_DEVELOPMENT_ANATOMY=OK")


if __name__ == "__main__":
    main()
