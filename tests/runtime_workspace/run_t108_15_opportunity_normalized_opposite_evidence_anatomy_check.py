"""run_t108_15_opportunity_normalized_opposite_evidence_anatomy_check.py — T108-15.

TEST_ONLY runner нормалізує factual intratrade opposite evidence GREEN T108-14
на реальну кількість completed-M15 opportunities, causal доступних строго
після production entry та до production exit. Canonical Candidate F Replay
виконується окремо для 2025 і 2026; immutable trades, outcomes і close reasons
використовуються лише як labels.

MACD, Alligator і Stochastic успадковують без змін T108-14 semantics: знак
completed-M15 MACD histogram, completed-M15 ACTIVE Alligator regime/state та
current Stochastic 14/1/3 K/D cross. Availability дорівнює source M15 timestamp
плюс 15 хвилин; higher-timeframe backfill і persistence відсутні. M1 timing
рахується за фактичними completed execution events, а не календарним часом.

Output містить BY_OUTCOME, BY_CLOSE_REASON, fixed 0/1/2/3_PLUS duration bins,
стан кожної family на першій eligible opportunity, усі factual LOSS rows і
консервативний cross-period summary. Runner не моделює exit, reverse або PnL,
не створює score/weights/threshold і не змінює production чи MD7.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-15"
MODE = "RM108_T108_15_OPPORTUNITY_NORMALIZED_OPPOSITE_EVIDENCE_ANATOMY_TEST_ONLY"
SOURCE_SCRIPT = "run_t108_14_intra_trade_m1_opposite_evidence_timing_anatomy_check.py"
PERIOD_CODES = ("2025", "2026")
OUTCOMES = ("WIN", "LOSS", "BE")
FAMILIES = ("MACD", "ALLIGATOR", "STOCHASTIC")
DURATION_BINS = ("0", "1", "2", "3_PLUS")


def _load_source_module() -> ModuleType:
    """Завантажити GREEN T108-14 з canonical runtime_workspace path."""

    file_path = TEST_ROOT / SOURCE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location("rm108_t108_15_source", file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = _load_source_module()
PERIODS = getattr(SOURCE, "PERIODS")
RUN_SOURCE_PERIOD: Callable[..., Any] = getattr(SOURCE, "_period_rows")
FAMILY_DIRECTIONS: Callable[..., dict[datetime, dict[str, str]]] = getattr(
    SOURCE,
    "_family_directions",
)
FACTUAL_TRADES: Callable[..., tuple[Any, ...]] = getattr(SOURCE, "_trades")
OUTCOME: Callable[..., str] = getattr(SOURCE, "_outcome")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    SOURCE,
    "PRODUCTION_HASHES",
)


@dataclass(frozen=True, slots=True)
class FamilyOpportunity:
    """Opposite occurrences однієї family в eligible M15 opportunities."""

    opposite_evidence_opportunities: int
    first_opposite_opportunity_index: int | None
    first_opposite_time: datetime | None
    m1_bars_before_factual_exit: int | None


@dataclass(frozen=True, slots=True)
class OpportunityTradeRow:
    """Одна factual trade з opportunity-normalized family evidence."""

    period: str
    trade: Any
    direction: str
    outcome: str
    duration_m1_bars: int
    eligible_times: tuple[datetime, ...]
    first_relations: dict[str, str]
    family: dict[str, FamilyOpportunity]

    @property
    def eligible_m15_opportunities(self) -> int:
        """Повернути кількість strict intratrade causal decision points."""

        return len(self.eligible_times)

    @property
    def trade_has_any_eligible_opportunity(self) -> bool:
        """Позначити хоча б одну causal M15 opportunity."""

        return bool(self.eligible_times)


def _execution_timestamps(runtime: Any) -> tuple[datetime, ...]:
    """Розгорнути factual completed-M1 execution chronology одного Replay."""

    session = runtime.replay_session
    assert session is not None and session.completed and session.multi_resolution
    events = tuple(event for window in session.execution_windows for event in window)
    assert events
    assert all(event.timeframe == session.source_timeframe == "M1" for event in events)
    timestamps = tuple(event.timestamp for event in events)
    assert all(left < right for left, right in zip(timestamps, timestamps[1:]))
    return timestamps


def _trade_m1_timestamps(
    trade: Any,
    execution_timestamps: tuple[datetime, ...],
) -> tuple[datetime, ...]:
    """Вибрати factual completed M1 bars від entry до exit включно."""

    start = bisect_left(execution_timestamps, trade.entry_timestamp)
    stop = bisect_right(execution_timestamps, trade.close_timestamp)
    selected = execution_timestamps[start:stop]
    assert selected
    assert selected[0] == trade.entry_timestamp
    assert selected[-1] == trade.close_timestamp
    return selected


def _relation(
    family_direction: str | None,
    trade_direction: str,
) -> str:
    """Класифікувати family state відносно factual position."""

    if family_direction is None:
        return "NEUTRAL_OR_NONE"
    if family_direction == trade_direction:
        return "SAME"
    assert {family_direction, trade_direction} == {"BUY", "SELL"}
    return "OPPOSITE"


def _family_opportunity(
    family: str,
    eligible_times: tuple[datetime, ...],
    directions: dict[datetime, dict[str, str]],
    trade_direction: str,
    trade_m1_timestamps: tuple[datetime, ...],
) -> FamilyOpportunity:
    """Порахувати всі opposite opportunities і перший causal index."""

    opposite_indexes = tuple(
        index
        for index, available_at in enumerate(eligible_times, start=1)
        if _relation(directions[available_at].get(family), trade_direction)
        == "OPPOSITE"
    )
    if not opposite_indexes:
        return FamilyOpportunity(0, None, None, None)
    first_index = opposite_indexes[0]
    first_time = eligible_times[first_index - 1]
    m1_index = bisect_left(trade_m1_timestamps, first_time)
    assert m1_index < len(trade_m1_timestamps)
    assert trade_m1_timestamps[m1_index] == first_time
    bars_before_exit = len(trade_m1_timestamps) - m1_index - 1
    assert bars_before_exit >= 1
    return FamilyOpportunity(
        opposite_evidence_opportunities=len(opposite_indexes),
        first_opposite_opportunity_index=first_index,
        first_opposite_time=first_time,
        m1_bars_before_factual_exit=bars_before_exit,
    )


def _trade_row(
    period: str,
    trade: Any,
    directions: dict[datetime, dict[str, str]],
    execution_timestamps: tuple[datetime, ...],
) -> OpportunityTradeRow:
    """Побудувати strict opportunity-normalized anatomy однієї trade."""

    trade_direction = str(trade.direction)
    assert trade_direction in {"BUY", "SELL"}
    eligible_times = tuple(
        available_at
        for available_at in sorted(directions)
        if trade.entry_timestamp < available_at < trade.close_timestamp
    )
    trade_m1_timestamps = _trade_m1_timestamps(trade, execution_timestamps)
    first_relations = {
        family: (
            "NEUTRAL_OR_NONE"
            if not eligible_times
            else _relation(
                directions[eligible_times[0]].get(family),
                trade_direction,
            )
        )
        for family in FAMILIES
    }
    family_rows = {
        family: _family_opportunity(
            family,
            eligible_times,
            directions,
            trade_direction,
            trade_m1_timestamps,
        )
        for family in FAMILIES
    }
    direction = "LONG" if trade_direction == "BUY" else "SHORT"
    return OpportunityTradeRow(
        period=period,
        trade=trade,
        direction=direction,
        outcome=OUTCOME(trade),
        duration_m1_bars=len(trade_m1_timestamps),
        eligible_times=eligible_times,
        first_relations=first_relations,
        family=family_rows,
    )


def _period_rows(spec: Any) -> tuple[Any, tuple[OpportunityTradeRow, ...]]:
    """Запустити GREEN source Replay та побудувати normalized factual rows."""

    replay, runtime, source_rows = RUN_SOURCE_PERIOD(spec)
    assert len(source_rows) == len(FACTUAL_TRADES(runtime))
    directions = FAMILY_DIRECTIONS(replay, runtime)
    execution_timestamps = _execution_timestamps(runtime)
    trades = sorted(
        FACTUAL_TRADES(runtime),
        key=lambda item: item.entry_timestamp,
    )
    rows = tuple(
        _trade_row(spec.code, trade, directions, execution_timestamps)
        for trade in trades
    )
    assert len(rows) == len(source_rows)
    assert all(
        row.trade.entry_timestamp < available_at < row.trade.close_timestamp
        for row in rows
        for available_at in row.eligible_times
    )
    return replay, rows


def _number(value: float | None) -> str:
    """Форматувати descriptive metric або NONE для zero denominator."""

    return "NONE" if value is None else f"{value:.4f}"


def _median(values: Iterable[int]) -> float | None:
    """Повернути deterministic median або NONE для порожнього зрізу."""

    items = tuple(values)
    return None if not items else float(statistics.median(items))


def _percent(numerator: int, denominator: int) -> float | None:
    """Порахувати відсоток або NONE, якщо opportunity denominator нуль."""

    return None if denominator == 0 else 100.0 * numerator / denominator


def _group_fields(rows: tuple[OpportunityTradeRow, ...]) -> str:
    """Сформувати загальну opportunity exposure частину group summary."""

    eligible = tuple(row for row in rows if row.trade_has_any_eligible_opportunity)
    return (
        f"trades={len(rows)}|"
        f"trades_with_eligible_m15_opportunity={len(eligible)}|"
        "total_eligible_m15_opportunities="
        f"{sum(row.eligible_m15_opportunities for row in rows)}|"
        "median_eligible_m15_opportunities_per_trade="
        f"{_number(_median(row.eligible_m15_opportunities for row in rows))}"
    )


def _family_fields(
    rows: tuple[OpportunityTradeRow, ...],
    family: str,
) -> str:
    """Сформувати trade-level і opportunity-level family normalization."""

    eligible_count = sum(row.trade_has_any_eligible_opportunity for row in rows)
    with_evidence = tuple(
        row for row in rows if row.family[family].opposite_evidence_opportunities > 0
    )
    opposite_count = sum(
        row.family[family].opposite_evidence_opportunities for row in rows
    )
    total_opportunities = sum(row.eligible_m15_opportunities for row in rows)
    first_indexes = (
        row.family[family].first_opposite_opportunity_index for row in with_evidence
    )
    return (
        f"family={family}|trades_with_opposite_evidence={len(with_evidence)}|"
        "trade_level_coverage_percent_among_eligible_trades="
        f"{_number(_percent(len(with_evidence), eligible_count))}|"
        f"opposite_opportunity_count={opposite_count}|"
        "opposite_opportunity_rate_percent="
        f"{_number(_percent(opposite_count, total_opportunities))}|"
        "median_first_opposite_opportunity_index="
        f"{_number(_median(first_indexes))}"
    )


def _print_group(
    section: str,
    period: str,
    group_name: str,
    rows: tuple[OpportunityTradeRow, ...],
) -> None:
    """Надрукувати exposure і три family metrics одного factual group."""

    print(f"section={section}|period={period}|group={group_name}|{_group_fields(rows)}")
    for family in FAMILIES:
        print(
            f"section={section}|period={period}|group={group_name}|"
            f"{_family_fields(rows, family)}"
        )


def _print_by_outcome(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> None:
    """Надрукувати opportunity-normalized WIN/LOSS/BE зрізи."""

    print("BY_OUTCOME")
    for period in PERIOD_CODES:
        for outcome in OUTCOMES:
            rows = tuple(
                row for row in rows_by_period[period] if row.outcome == outcome
            )
            _print_group("BY_OUTCOME", period, outcome, rows)


def _print_by_close_reason(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> None:
    """Надрукувати opportunity-normalized factual close-reason зрізи."""

    print("BY_CLOSE_REASON")
    for period in PERIOD_CODES:
        period_rows = rows_by_period[period]
        reasons = sorted({str(row.trade.close_reason) for row in period_rows})
        for reason in reasons:
            rows = tuple(
                row for row in period_rows if str(row.trade.close_reason) == reason
            )
            _print_group("BY_CLOSE_REASON", period, reason, rows)


def _duration_bin(opportunities: int) -> str:
    """Застосувати fixed descriptive 0/1/2/3_PLUS bins без selection."""

    if opportunities >= 3:
        return "3_PLUS"
    return str(opportunities)


def _bin_rows(
    rows: tuple[OpportunityTradeRow, ...],
    duration_bin: str,
    outcome: str,
) -> tuple[OpportunityTradeRow, ...]:
    """Вибрати factual rows одного fixed exposure bin та outcome."""

    return tuple(
        row
        for row in rows
        if _duration_bin(row.eligible_m15_opportunities) == duration_bin
        and row.outcome == outcome
    )


def _stochastic_coverage(rows: tuple[OpportunityTradeRow, ...]) -> float | None:
    """Порахувати trade-level Stochastic opposite coverage у зрізі."""

    found = sum(
        row.family["STOCHASTIC"].opposite_evidence_opportunities > 0 for row in rows
    )
    return _percent(found, len(rows))


def _print_duration_matched(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> None:
    """Надрукувати fixed duration-bin Stochastic anatomy без optimization."""

    print("DURATION_MATCHED_ANATOMY")
    for period in PERIOD_CODES:
        for duration_bin in DURATION_BINS:
            for outcome in OUTCOMES:
                rows = _bin_rows(rows_by_period[period], duration_bin, outcome)
                found = sum(
                    row.family["STOCHASTIC"].opposite_evidence_opportunities > 0
                    for row in rows
                )
                print(
                    f"period={period}|eligible_bin={duration_bin}|"
                    f"outcome={outcome}|trades={len(rows)}|"
                    f"stochastic_trades_with_opposite_evidence={found}|"
                    f"coverage_percent={_number(_percent(found, len(rows)))}"
                )


def _print_first_eligible(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> None:
    """Порівняти family direction лише на першій eligible opportunity."""

    print("FIRST_ELIGIBLE_OPPORTUNITY")
    for period in PERIOD_CODES:
        for outcome in OUTCOMES:
            rows = tuple(
                row
                for row in rows_by_period[period]
                if row.outcome == outcome and row.trade_has_any_eligible_opportunity
            )
            for family in FAMILIES:
                counts = Counter(row.first_relations[family] for row in rows)
                print(
                    f"period={period}|outcome={outcome}|family={family}|"
                    f"eligible_trades={len(rows)}|SAME={counts['SAME']}|"
                    f"OPPOSITE={counts['OPPOSITE']}|"
                    f"NEUTRAL_OR_NONE={counts['NEUTRAL_OR_NONE']}"
                )


def _value(value: Any) -> str:
    """Форматувати nullable LOSS detail field."""

    if value is None:
        return "NONE"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _print_loss_detail(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> None:
    """Надрукувати factual opportunity timing усіх 13 LOSS trades."""

    print("LOSS_DETAIL")
    for period in PERIOD_CODES:
        for row in rows_by_period[period]:
            if row.outcome != "LOSS":
                continue
            fields = [
                f"period={period}",
                f"trade_id={row.trade.position_id}",
                f"direction={row.direction}",
                f"close_reason={row.trade.close_reason}",
                f"duration_m1_bars={row.duration_m1_bars}",
                f"eligible_m15_opportunities={row.eligible_m15_opportunities}",
            ]
            for family in FAMILIES:
                item = row.family[family]
                prefix = family.lower()
                fields.extend(
                    (
                        f"{prefix}_first_opposite_opportunity_index="
                        f"{_value(item.first_opposite_opportunity_index)}",
                        f"{prefix}_first_opposite_time="
                        f"{_value(item.first_opposite_time)}",
                        f"{prefix}_m1_bars_before_factual_exit="
                        f"{_value(item.m1_bars_before_factual_exit)}",
                    )
                )
            print("|".join(fields))


def _eligible_coverage(
    rows: tuple[OpportunityTradeRow, ...],
    family: str,
) -> float | None:
    """Порахувати family coverage лише серед opportunity-eligible trades."""

    eligible = tuple(row for row in rows if row.trade_has_any_eligible_opportunity)
    found = sum(
        row.family[family].opposite_evidence_opportunities > 0 for row in eligible
    )
    return _percent(found, len(eligible))


def _direction(left: float | None, right: float | None) -> str:
    """Описати factual LOSS coverage відносно WIN без threshold."""

    if left is None or right is None:
        return "NOT_COMPARABLE"
    if left > right:
        return "LOSS_HIGHER"
    if left < right:
        return "LOSS_LOWER"
    return "EQUAL"


def _cross_period_family_enrichment(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
    family: str,
) -> tuple[dict[str, str], bool]:
    """Порівняти eligible LOSS/WIN coverage однаково в обох періодах."""

    directions: dict[str, str] = {}
    for period in PERIOD_CODES:
        rows = rows_by_period[period]
        loss = _eligible_coverage(
            tuple(row for row in rows if row.outcome == "LOSS"),
            family,
        )
        win = _eligible_coverage(
            tuple(row for row in rows if row.outcome == "WIN"),
            family,
        )
        directions[period] = _direction(loss, win)
    stable = all(directions[period] == "LOSS_HIGHER" for period in PERIOD_CODES)
    return directions, stable


def _duration_bin_summary(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> tuple[dict[str, tuple[int, int, int]], bool]:
    """Оцінити fixed-bin direction лише там, де є WIN і LOSS."""

    summaries: dict[str, tuple[int, int, int]] = {}
    for period in PERIOD_CODES:
        supported = 0
        contradicted = 0
        tied = 0
        for duration_bin in DURATION_BINS:
            loss_rows = _bin_rows(rows_by_period[period], duration_bin, "LOSS")
            win_rows = _bin_rows(rows_by_period[period], duration_bin, "WIN")
            if not loss_rows or not win_rows:
                continue
            direction = _direction(
                _stochastic_coverage(loss_rows),
                _stochastic_coverage(win_rows),
            )
            supported += direction == "LOSS_HIGHER"
            contradicted += direction == "LOSS_LOWER"
            tied += direction == "EQUAL"
        summaries[period] = (supported, contradicted, tied)
    preserved = all(
        summaries[period][0] > 0 and summaries[period][1] == 0
        for period in PERIOD_CODES
    )
    return summaries, preserved


def _first_opportunity_enrichment(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> tuple[dict[str, str], bool]:
    """Порівняти Stochastic first-opportunity opposite rate LOSS/WIN."""

    directions: dict[str, str] = {}
    for period in PERIOD_CODES:
        rates: dict[str, float | None] = {}
        for outcome in ("LOSS", "WIN"):
            rows = tuple(
                row
                for row in rows_by_period[period]
                if row.outcome == outcome and row.trade_has_any_eligible_opportunity
            )
            opposite = sum(
                row.first_relations["STOCHASTIC"] == "OPPOSITE" for row in rows
            )
            rates[outcome] = _percent(opposite, len(rows))
        directions[period] = _direction(rates["LOSS"], rates["WIN"])
    stable = all(directions[period] == "LOSS_HIGHER" for period in PERIOD_CODES)
    return directions, stable


def _print_cross_period_summary(
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]],
) -> None:
    """Надрукувати factual cross-period checks без production verdict."""

    print("CROSS_PERIOD_SUMMARY")
    stochastic, stochastic_stable = _cross_period_family_enrichment(
        rows_by_period,
        "STOCHASTIC",
    )
    print(
        "stochastic_loss_enrichment_among_eligible_trades="
        f"{stochastic_stable}|2025_direction={stochastic['2025']}|"
        f"2026_direction={stochastic['2026']}"
    )
    bins, bins_preserved = _duration_bin_summary(rows_by_period)
    print(
        "stochastic_loss_enrichment_preserved_in_fixed_duration_bins="
        f"{bins_preserved}|2025_supported={bins['2025'][0]}|"
        f"2025_contradicted={bins['2025'][1]}|2025_tied={bins['2025'][2]}|"
        f"2026_supported={bins['2026'][0]}|"
        f"2026_contradicted={bins['2026'][1]}|2026_tied={bins['2026'][2]}"
    )
    first, first_stable = _first_opportunity_enrichment(rows_by_period)
    print(
        "stochastic_loss_enrichment_on_first_eligible_opportunity="
        f"{first_stable}|2025_direction={first['2025']}|"
        f"2026_direction={first['2026']}"
    )
    macd, macd_stable = _cross_period_family_enrichment(rows_by_period, "MACD")
    print(
        f"macd_cross_period_stable_loss_pattern={macd_stable}|"
        f"2025_direction={macd['2025']}|2026_direction={macd['2026']}"
    )
    alligator_total = sum(
        row.family["ALLIGATOR"].opposite_evidence_opportunities
        for rows in rows_by_period.values()
        for row in rows
    )
    print(
        f"alligator_remains_zero_opposite={alligator_total == 0}|"
        f"alligator_opposite_opportunities={alligator_total}"
    )
    print("production_exit_reverse_conclusion_made=False")


def main() -> int:
    """Виконати T108-15 factual opportunity-normalized anatomy."""

    before_hashes = PRODUCTION_HASHES()
    print("T108_15_OPPORTUNITY_NORMALIZED_OPPOSITE_EVIDENCE_ANATOMY")
    replays: dict[str, Any] = {}
    rows_by_period: dict[str, tuple[OpportunityTradeRow, ...]] = {}
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        replay, rows = _period_rows(spec)
        replays[spec.code] = replay
        rows_by_period[spec.code] = rows
    assert tuple(rows_by_period) == PERIOD_CODES
    assert PRODUCTION_HASHES() == before_hashes

    _print_by_outcome(rows_by_period)
    _print_by_close_reason(rows_by_period)
    _print_duration_matched(rows_by_period)
    _print_first_eligible(rows_by_period)
    _print_loss_detail(rows_by_period)
    _print_cross_period_summary(rows_by_period)

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=FACTUAL_CURRENT_PRODUCTION_TRADES_ONLY")
    print("timeline=FACTUAL_ENTRY_TO_FACTUAL_EXIT")
    print("families=MACD_ALLIGATOR_STOCHASTIC")
    print("opportunity_unit=CAUSAL_COMPLETED_M15_AVAILABLE_DURING_FACTUAL_TRADE")
    print("duration_bins_fixed=True")
    print("production_actions_used_as_labels_only=True")
    print("counterfactual_exit_simulated=False")
    print("alternative_exit_simulated=False")
    print("reverse_logic_created=False")
    print("weights_used=False")
    print("score_model_created=False")
    print("score_threshold_selected=False")
    print("best_timing_window_selected=False")
    print("persistence_selected=False")
    print("completed_bars_only=True")
    print("higher_timeframe_backfill_used=False")
    print("lookahead_used=False")
    print("optimization_performed=False")
    print("threshold_sweep_performed=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={sum(item.broker_requests for item in replays.values())}")
    print(
        "broker_execution_attempted="
        f"{any(item.broker_execution_attempted for item in replays.values())}"
    )
    print("T108_15_OPPORTUNITY_NORMALIZED_OPPOSITE_EVIDENCE_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
