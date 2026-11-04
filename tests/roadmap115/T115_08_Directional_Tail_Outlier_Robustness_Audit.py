# -*- coding: utf-8 -*-
"""RoadMap115 / T115-08 — стійкість BUY/SELL до викидів.

TEST_ONLY: аналіз закритих пар T115-02 (Alligator ENDING)
і T115-03 (гіпотеза 33%). Жодних змін угод, сигналів і цін.

PAIR_TAIL_PIPS = Alligator - Alligator+33%.
Позитивне — перевага утримання, від'ємне — виходу за 33%.

Діагностика: квантилі та внесок великих відхилень,
тест вилучення top-|tail| 1/5/10, leave-one-out,
розриви історії й місяці. Це outcome labels, НЕ
каузальні торгові фільтри. Відбори не створюють
нових Replay-угод. Сигнали лише за completed M15.

OHLC mid, gross pips, без витрат. Не змінювати
production/MD7, без брокера та оптимізації 33%.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
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
    _simulate,
    _states,
)
from T115_06_Alligator_Trend_Exposure_Attribution import (  # noqa: E402
    _audit_exposure,
)
from T115_07_Directional_Reaction_Speed_Audit import (  # noqa: E402
    Audit,
    Reaction,
    _audit_speed,
    _quantile,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceAlligatorRuntimeProfile,
)

ROOT = Path(__file__).resolve().parents[2]
EPS = 1e-7
REMOVALS = (1, 5, 10)


@dataclass(frozen=True, slots=True)
class TailRow:
    """Попарна різниця завершеної угоди."""

    direction: str
    entry_at: datetime
    base_pips: float
    rule33_pips: float
    delta_pips: float
    gap_affected: bool


def _tail_rows(rows: tuple[Reaction, ...], direction: str) -> list[TailRow]:
    """Однакові entry, дострокові виходи за 33%."""
    selected: list[TailRow] = []
    for row in rows:
        if row.direction != direction or not row.early_33:
            continue
        selected.append(TailRow(
            direction=row.direction,
            entry_at=row.entry_at,
            base_pips=row.base_pips,
            rule33_pips=row.rule33_pips,
            delta_pips=row.base_pips - row.rule33_pips,
            gap_affected=row.gap_affected_pair,
        ))
    return selected


def _sign(value: float) -> int:
    """Знак переваги з урахуванням шуму float."""
    if value > EPS:
        return 1
    if value < -EPS:
        return -1
    return 0


def _net(rows: list[TailRow]) -> float:
    """Сума tail pips у порядку входів."""
    return math.fsum(row.delta_pips for row in rows)


def _removed_largest_abs(rows: list[TailRow], count: int) -> list[TailRow]:
    """Sensitivity: прибрати top-|tail| без зміни інших пар.

    При рівних |tail| пріоритет у ранішого входу;
    порядок інших пар детермінований.
    """
    assert 0 <= count <= len(rows)
    ranked = sorted(
        range(len(rows)),
        key=lambda index: (
            -abs(rows[index].delta_pips), rows[index].entry_at, index,
        ),
    )
    omitted = set(ranked[:count])
    return [row for index, row in enumerate(rows) if index not in omitted]


def _split(rows: list[TailRow]) -> tuple[int, int, int, float, float]:
    """Кількість та сума додатних і від’ємних tail."""
    positive = [row.delta_pips for row in rows if _sign(row.delta_pips) > 0]
    negative = [row.delta_pips for row in rows if _sign(row.delta_pips) < 0]
    flat = len(rows) - len(positive) - len(negative)
    assert len(positive) + len(negative) + flat == len(rows)
    return (
        len(positive), len(negative), flat,
        math.fsum(positive), -math.fsum(negative),
    )


def _fmt(number: float | None) -> str:
    """Два десяткові знаки або NONE."""
    return "NONE" if number is None else f"{number:.2f}"


def _report_direction(
    label: str, direction: str, audit: Audit,
) -> tuple[int, int, int, float]:
    """Спільні метрики для BUY/SELL обох періодів."""
    all_rows = [row for row in audit.rows if row.direction == direction]
    early = _tail_rows(audit.rows, direction)
    assert all_rows and early
    assert len({row.entry_at for row in early}) == len(early)
    assert all(row.direction == direction for row in early)
    assert all(
        row.delta_pips == row.base_pips - row.rule33_pips
        for row in early
    )

    original_base = math.fsum(row.base_pips for row in all_rows)
    original_33 = math.fsum(row.rule33_pips for row in all_rows)
    net = _net(early)
    assert math.isclose(original_base - original_33, net, abs_tol=EPS)
    positive_n, negative_n, flat_n, gain, loss = _split(early)
    assert math.isclose(gain - loss, net, abs_tol=EPS)
    tails = [row.delta_pips for row in early]
    magnitude = sorted((abs(tail) for tail in tails), reverse=True)
    total_abs = math.fsum(magnitude)
    top1_share = 100 * magnitude[0] / total_abs if total_abs > EPS else 0.0
    top5_share = (
        100 * math.fsum(magnitude[:5]) / total_abs
        if total_abs > EPS else 0.0
    )
    if total_abs > EPS:
        assert math.isclose(
            top1_share, 100 * max(magnitude) / total_abs, abs_tol=EPS,
        )
    else:
        assert top1_share == 0

    print(
        f"DIRECTION={direction}|PERIOD={label}|CLOSED={len(all_rows)}|"
        f"EARLY_33={len(early)}|UNMODIFIED={len(all_rows) - len(early)}|"
        f"GROSS_ALLIGATOR_PIPS={original_base:.2f}|"
        f"GROSS_WITH_33_PIPS={original_33:.2f}|"
        f"TAIL_BASE_MINUS_33_PIPS={net:.2f}"
    )
    print(
        f"DISTRIBUTION={direction}|PERIOD={label}|"
        f"HOLD_BETTER={positive_n}|EARLY_BETTER={negative_n}|SAME={flat_n}|"
        f"HOLD_GAIN_SUM_PIPS={gain:.2f}|"
        f"EARLY_SAVED_SUM_PIPS={loss:.2f}|"
        f"MEAN_PIPS={_fmt(statistics.fmean(tails))}|"
        f"MEDIAN_PIPS={_fmt(statistics.median(tails))}|"
        f"P10={_fmt(_quantile(tails, 0.10))}|"
        f"P25={_fmt(_quantile(tails, 0.25))}|"
        f"P75={_fmt(_quantile(tails, 0.75))}|"
        f"P90={_fmt(_quantile(tails, 0.90))}|"
        f"MIN={min(tails):.2f}|MAX={max(tails):.2f}"
    )
    print(
        f"OUTLIER_CONCENTRATION={direction}|PERIOD={label}|"
        f"TOP1_ABS_SHARE_PCT={top1_share:.2f}|"
        f"TOP5_ABS_SHARE_PCT={top5_share:.2f}|"
        f"MAX_HOLD_ADVANTAGE_PIPS={max(tails):.2f}|"
        f"MAX_EARLY_ADVANTAGE_PIPS={-min(tails):.2f}"
    )

    trimmed_signs: list[int] = []
    for count in REMOVALS:
        trimmed = _removed_largest_abs(early, count)
        remainder = _net(trimmed)
        sign = _sign(remainder)
        trimmed_signs.append(sign)
        print(
            f"REMOVE_TOP_ABS={count}|DIRECTION={direction}|PERIOD={label}|"
            f"LEFT={len(trimmed)}|TAIL_NET_PIPS={remainder:.2f}|"
            f"SIGN={sign}|SIGN_MATCH_FULL={sign == _sign(net)}"
        )
    loo_flips = sum(
        _sign(net - row.delta_pips) != _sign(net)
        for row in early
    )
    print(
        f"ONE_PAIR_SENSITIVITY={direction}|PERIOD={label}|"
        f"REMOVE_ONE_SIGN_FLIPS={loo_flips}|TOTAL_PAIRS={len(early)}"
    )

    no_gap = [row for row in early if not row.gap_affected]
    affected = [row for row in early if row.gap_affected]
    assert len(no_gap) + len(affected) == len(early)
    assert math.isclose(_net(no_gap) + _net(affected), net, abs_tol=EPS)
    print(
        f"GAPS={direction}|PERIOD={label}|"
        f"PAIRS_AFFECTED={len(affected)}|"
        f"TAIL_AFFECTED_PIPS={_net(affected):.2f}|"
        f"PAIRS_NO_GAP={len(no_gap)}|"
        f"TAIL_NO_GAP_PIPS={_net(no_gap):.2f}|"
        f"NO_GAP_SIGN={_sign(_net(no_gap))}"
    )

    months: dict[str, list[TailRow]] = {}
    for row in early:
        month = row.entry_at.strftime("%Y-%m")
        months.setdefault(month, []).append(row)
    positive_months = sum(_sign(_net(items)) > 0 for items in months.values())
    negative_months = sum(_sign(_net(items)) < 0 for items in months.values())
    max_month_share = (
        100 * max(abs(_net(items)) for items in months.values()) / total_abs
        if total_abs > EPS else 0.0
    )
    print(
        f"MONTHS={direction}|PERIOD={label}|"
        f"ACTIVE_MONTHS={len(months)}|HOLD_BETTER_MONTHS={positive_months}|"
        f"EARLY_BETTER_MONTHS={negative_months}|"
        f"FLAT_MONTHS={len(months) - positive_months - negative_months}|"
        f"MAX_MONTH_ABS_SHARE_PCT={max_month_share:.2f}"
    )
    return _sign(net), trimmed_signs[1], _sign(_net(no_gap)), net


def _synthetic_checks() -> None:
    """Перевірити знаки, квантилі, ties, top-|tail| і розриви."""
    from datetime import UTC

    start = datetime(2025, 1, 1, tzinfo=UTC)
    values = (100.0, -20.0, -30.0, 0.0)
    sample = [
        TailRow(DIRECTION_UP, start.replace(day=i + 1),
                value, 0.0, value, i == 1)
        for i, value in enumerate(values)
    ]
    assert math.isclose(_net(sample), 50.0, abs_tol=EPS)
    assert _split(sample) == (1, 2, 1, 100.0, 50.0)
    assert _sign(_net(_removed_largest_abs(sample, 1))) == -1
    assert _removed_largest_abs(sample, 0) == sample
    assert _removed_largest_abs(sample, 4) == []
    assert _quantile(list(values), 0.50) == -10.0
    assert _quantile(list(values), 0.25) == -22.5
    assert len([row for row in sample if row.gap_affected]) == 1
    assert _sign(0.0) == 0 and _sign(EPS / 2) == 0

    stable = [
        TailRow(DIRECTION_DOWN, start.replace(day=i + 1),
                value, 0.0, value, False)
        for i, value in enumerate((30.0, 20.0, -5.0))
    ]
    assert _sign(_net(_removed_largest_abs(stable, 1))) == 1
    tie = [
        TailRow(DIRECTION_UP, start.replace(day=i + 1),
                value, 0.0, value, False)
        for i, value in enumerate((5.0, -5.0, 1.0))
    ]
    assert _removed_largest_abs(tie, 1) == tie[1:]
    print("SYNTHETIC_TAIL_OUTLIER_ROBUSTNESS=OK")


def _fingerprint(path: Path) -> str | None:
    """SHA256 production/MD7 без перезапису."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_period(
    label: str, filename: str, expected: tuple[int, ...],
    profile: WorkspaceAlligatorRuntimeProfile,
) -> tuple[tuple[int, int, int, float], tuple[int, int, int, float]]:
    """Два прогони та звірка з baseline."""
    history = ROOT / "data/history/CTRADER/EURUSD/M1" / filename
    cutoff = CANONICAL_2026_END if label.startswith("2026") else None
    source, selected, bars = _aggregate_m1(history, int(label[:4]), cutoff)
    steps = list(_states(bars, profile))
    baseline = _simulate(steps)
    assert (
        len(bars), baseline.entry_signals, baseline.buy_signals,
        baseline.sell_signals, baseline.next_open_available,
    ) == expected, f"T115_01_POPULATION_CHANGED: {label}"
    first = _audit_speed(steps)
    second = _audit_speed(steps)
    assert first == second, f"NONDETERMINISTIC: {label}"
    preceding = _audit_exposure(steps)
    assert preceding.trends == first.total_trends
    assert preceding.entries == first.entries
    assert preceding.no_entries == first.no_entry
    assert preceding.closed_alligator == first.base_closed
    assert preceding.closed_33 == first.rule33_closed
    assert preceding.open_end == first.open_end
    assert math.isclose(
        preceding.alligator_gross_pips,
        math.fsum(row.base_pips for row in first.rows), abs_tol=EPS,
    )
    assert math.isclose(
        preceding.rule33_gross_pips,
        math.fsum(row.rule33_pips for row in first.rows), abs_tol=EPS,
    )
    print(
        f"PERIOD={label}|SOURCE_M1={source}|SELECTED_M1={selected}|"
        f"COMPLETED_M15={len(bars)}|CUTOFF_UTC="
        f"{cutoff.isoformat() if cutoff else 'NONE'}"
    )
    print(
        f"TREND_ORDERS|TOTAL={first.total_trends}|WITH_ENTRY={first.entries}|"
        f"WITHOUT_ENTRY={first.no_entry}|CLOSED={first.base_closed}|"
        f"OPEN_AT_END={first.open_end}"
    )
    buy = _report_direction(label, DIRECTION_UP, first)
    sell = _report_direction(label, DIRECTION_DOWN, first)
    assert math.isclose(
        buy[3] + sell[3],
        preceding.alligator_gross_pips - preceding.rule33_gross_pips,
        abs_tol=EPS,
    )
    assert (
        len(_tail_rows(first.rows, DIRECTION_UP))
        == preceding.by_direction[0].early
    )
    assert (
        len(_tail_rows(first.rows, DIRECTION_DOWN))
        == preceding.by_direction[1].early
    )
    print(
        f"REPLAY_TWICE_DETERMINISTIC={label}:OK|"
        "BASELINES_T115_01_TO_07=OK"
    )
    return buy, sell


def main() -> None:
    """Незмінні симуляції, постфактум-аналітика."""
    guarded = (
        ROOT / "core/workspace_alligator.py",
        ROOT / "core/workspace_indicator_profile.py",
        ROOT / "doc/LGE_Runtime_07.md",
    )
    before = {str(path): _fingerprint(path) for path in guarded}
    print("T115-08|TEST_ONLY|DIRECTIONAL_TAIL_OUTLIER_ROBUSTNESS")
    print("33_PERCENT=HYPOTHESIS_ONLY|OUTCOME_HINDSIGHT_ONLY=True")
    print("TRIMMING=DIAGNOSTIC_ONLY|REMOVALS=TOP_ABS_1,5,10")
    print("TAIL=ALLIGATOR_MINUS_33|POSITIVE_MEANS_HOLD_BETTER")
    _synthetic_checks()
    profile = _profile()
    print(
        f"PROFILE={profile.profile_uid}|REVISION={profile.profile_revision}|"
        f"CONFIRMATION_BARS={profile.effective_trend_start_confirmation_bars}"
    )
    summaries = {}
    for label, filename, *expected in PERIODS:
        summaries[label] = _run_period(
            label, filename, tuple(expected), profile,
        )
    first_period = summaries["2025"]
    second_period = summaries["2026_TO_2026_08_25"]
    for direction, index in ((DIRECTION_UP, 0), (DIRECTION_DOWN, 1)):
        first = first_period[index]
        second = second_period[index]
        print(
            f"CROSS_PERIOD={direction}|FULL_SIGN_2025={first[0]}|"
            f"FULL_SIGN_2026={second[0]}|"
            f"TOP5_REMOVED_SIGN_2025={first[1]}|"
            f"TOP5_REMOVED_SIGN_2026={second[1]}|"
            f"NO_GAP_SIGN_2025={first[2]}|NO_GAP_SIGN_2026={second[2]}"
        )
    assert before == {str(path): _fingerprint(path) for path in guarded}
    print(
        "completed_bars_only=True|trade_decisions_look_ahead=False|"
        "broker_requests=0"
    )
    print("gross_mid_only=True|spread_commission_slippage_included=False")
    print("production_changed=False|md7_changed=False")
    print("T115_08_DIRECTIONAL_TAIL_OUTLIER_ROBUSTNESS=OK")


if __name__ == "__main__":
    main()
