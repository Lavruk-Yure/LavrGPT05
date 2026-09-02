# -*- coding: utf-8 -*-
"""RoadMap103 / 7N: qualified Structural SL/TP decoupling diagnostic 2025.

Runner повторює production Candidate F після 6K без змін і для тих самих
59 baseline entries окремо перевіряє три paired counterfactual сімейства:
1) тільки qualified Structural SL, production TP;
2) production SL, тільки qualified Structural TP;
3) qualified Structural SL + TP разом.

На відміну від 7M, structural TP не може бути ближчим за 24 pips. Якщо
найближчий pivot занадто близький, runner шукає інший causal підтверджений
рівень у 40-bar lookback. Для основного qualified варіанта рівень повинен
мати не менше двох touch у tolerance 1 pip. Для SL так само пропускається
одноразовий pivot і береться останній causal рівень з >=2 touch; якщо такого
немає, лишається production SL. Мінімальна SL distance тестується 12/24 pips.

Це paired diagnostic: fixed baseline entries, без portfolio-capacity ефектів.
Жоден результат не є production gate або production backtest.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)
from run_algorithm_workspace_candidate_f_structural_sl_tp_2025_check import (  # noqa: E402,E501
    FOCUS_CASES,
    PIP,
    STRUCTURE_BUFFER_PIPS,
    STRUCTURE_TOUCH_TOLERANCE_PIPS,
    StructuralLevel,
    StructuralProtectionPlan,
    StructuralSlTpRuntime,
    _assert_baseline,
    _directional_price,
    _flatten_execution_events,
    _simulate_one,
    _summary_text,
    _variant_summary,
)
from run_algorithm_workspace_candidate_f_trend_lifecycle_entry_quality_2025_check import (  # noqa: E402,E501
    PIVOT_LOOKBACK_BARS,
    PIVOT_SIDE_BARS,
    _is_pivot_high,
    _is_pivot_low,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalReplaySummary,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

MIN_STRUCTURAL_TP_PIPS = 24.0
QUALIFIED_MIN_TOUCHES = 2
SL_FLOORS_PIPS = (12.0, 24.0)


@dataclass(frozen=True, slots=True)
class QualifiedVariantResult:
    """Один paired counterfactual variant."""

    name: str
    floor_pips: float
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    summary: WorkspaceHistoricalReplaySummary


def _touch_count(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    *,
    kind: str,
    price: float,
) -> int:
    start = max(0, signal_index - PIVOT_LOOKBACK_BARS)
    tolerance = STRUCTURE_TOUCH_TOLERANCE_PIPS * PIP
    if kind == "SUPPORT":
        return sum(
            abs(event.low - price) <= tolerance
            for event in events[start : signal_index + 1]  # noqa: E203
        )
    assert kind == "RESISTANCE"
    return sum(
        abs(event.high - price) <= tolerance
        for event in events[start : signal_index + 1]  # noqa: E203
    )


def _candidate_levels(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    *,
    kind: str,
    entry_price: float,
) -> tuple[StructuralLevel, ...]:
    earliest = max(PIVOT_SIDE_BARS, signal_index - PIVOT_LOOKBACK_BARS)
    latest = signal_index - PIVOT_SIDE_BARS
    if latest < earliest:
        return ()
    levels: list[StructuralLevel] = []
    for pivot_index in range(earliest, latest + 1):
        event = events[pivot_index]
        if kind == "SUPPORT":
            if not _is_pivot_low(events, pivot_index):
                continue
            price = event.low
            if price >= entry_price:
                continue
        else:
            assert kind == "RESISTANCE"
            if not _is_pivot_high(events, pivot_index):
                continue
            price = event.high
            if price <= entry_price:
                continue
        levels.append(
            StructuralLevel(
                kind=kind,
                timestamp=event.timestamp,
                price=price,
                age_bars=signal_index - pivot_index,
                touches=_touch_count(
                    events,
                    signal_index,
                    kind=kind,
                    price=price,
                ),
            )
        )
    return tuple(levels)


def _last_qualified_stop_level(
    levels: tuple[StructuralLevel, ...],
) -> StructuralLevel | None:
    qualified = tuple(
        level for level in levels if level.touches >= QUALIFIED_MIN_TOUCHES
    )
    if not qualified:
        return None
    return min(qualified, key=lambda level: level.age_bars)


def _nearest_qualified_take_level(
    levels: tuple[StructuralLevel, ...],
    entry_price: float,
) -> StructuralLevel | None:
    minimum_distance = MIN_STRUCTURAL_TP_PIPS * PIP
    qualified = tuple(
        level
        for level in levels
        if level.touches >= QUALIFIED_MIN_TOUCHES
        and abs(level.price - entry_price) >= minimum_distance
    )
    if not qualified:
        return None
    return min(qualified, key=lambda level: abs(level.price - entry_price))


def _build_qualified_plan(
    trade: WorkspaceHistoricalTradeDiagnostic,
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
    *,
    floor_pips: float,
    structural_stop_enabled: bool,
    structural_take_enabled: bool,
) -> StructuralProtectionPlan:
    signal_index = event_index.get(trade.signal_timestamp)
    assert signal_index is not None
    entry = trade.entry_price
    supports = _candidate_levels(
        strategy_events,
        signal_index,
        kind="SUPPORT",
        entry_price=entry,
    )
    resistances = _candidate_levels(
        strategy_events,
        signal_index,
        kind="RESISTANCE",
        entry_price=entry,
    )

    stop_candidates = supports if trade.direction == "BUY" else resistances
    take_candidates = resistances if trade.direction == "BUY" else supports
    stop_level = _last_qualified_stop_level(stop_candidates)
    take_level = _nearest_qualified_take_level(take_candidates, entry)

    buffer_distance = STRUCTURE_BUFFER_PIPS * PIP
    floor_distance = floor_pips * PIP

    if structural_stop_enabled and stop_level is not None:
        structural_stop = (
            stop_level.price - buffer_distance
            if trade.direction == "BUY"
            else stop_level.price + buffer_distance
        )
        structural_distance = abs(entry - structural_stop)
        stop_distance = max(structural_distance, floor_distance)
        stop_loss = _directional_price(
            trade.direction,
            entry,
            stop_distance,
            favorable=False,
        )
        stop_source = "QUALIFIED_STRUCTURE"
    else:
        stop_distance = trade.stop_loss_distance
        stop_loss = _directional_price(
            trade.direction,
            entry,
            stop_distance,
            favorable=False,
        )
        stop_source = "PRODUCTION"

    if structural_take_enabled and take_level is not None:
        structural_take = (
            take_level.price - buffer_distance
            if trade.direction == "BUY"
            else take_level.price + buffer_distance
        )
        take_distance = abs(structural_take - entry)
        if take_distance >= MIN_STRUCTURAL_TP_PIPS * PIP:
            take_profit = structural_take
            take_source = "QUALIFIED_STRUCTURE"
        else:
            take_distance = stop_distance * 2.0
            take_profit = _directional_price(
                trade.direction,
                entry,
                take_distance,
                favorable=True,
            )
            take_source = "FALLBACK_2R"
    elif structural_take_enabled:
        take_distance = stop_distance * 2.0
        take_profit = _directional_price(
            trade.direction,
            entry,
            take_distance,
            favorable=True,
        )
        take_source = "FALLBACK_2R"
    else:
        take_distance = trade.take_profit_distance
        take_profit = _directional_price(
            trade.direction,
            entry,
            take_distance,
            favorable=True,
        )
        take_source = "PRODUCTION"

    if trade.direction == "BUY":
        assert stop_loss < entry < take_profit
    else:
        assert take_profit < entry < stop_loss
    return StructuralProtectionPlan(
        floor_pips=floor_pips,
        entry_price=entry,
        support=_last_qualified_stop_level(supports),
        resistance=_last_qualified_stop_level(resistances),
        stop_loss=stop_loss,
        take_profit=take_profit,
        stop_distance=stop_distance,
        take_distance=take_distance,
        stop_source=stop_source,
        take_source=take_source,
        fallback_used=(
            stop_source != "QUALIFIED_STRUCTURE" or take_source != "QUALIFIED_STRUCTURE"
        ),
    )


def _touch_inventory(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {}
    for minimum_touches in (1, 2, 3):
        counts = {
            "stop_found": 0,
            "take_found_any": 0,
            "take_found_24": 0,
        }
        for trade in trades:
            signal_index = event_index[trade.signal_timestamp]
            entry = trade.entry_price
            supports = _candidate_levels(
                strategy_events,
                signal_index,
                kind="SUPPORT",
                entry_price=entry,
            )
            resistances = _candidate_levels(
                strategy_events,
                signal_index,
                kind="RESISTANCE",
                entry_price=entry,
            )
            stop_levels = supports if trade.direction == "BUY" else resistances
            take_levels = resistances if trade.direction == "BUY" else supports
            if any(level.touches >= minimum_touches for level in stop_levels):
                counts["stop_found"] += 1
            if any(level.touches >= minimum_touches for level in take_levels):
                counts["take_found_any"] += 1
            if any(
                level.touches >= minimum_touches
                and abs(level.price - entry) >= MIN_STRUCTURAL_TP_PIPS * PIP
                for level in take_levels
            ):
                counts["take_found_24"] += 1
        result[minimum_touches] = counts
    return result


def _stop_distance_bins(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
) -> dict[str, int]:
    bins = {"NONE": 0, "<=24": 0, "24-36": 0, "36-48": 0, ">48": 0}
    for trade in trades:
        signal_index = event_index[trade.signal_timestamp]
        entry = trade.entry_price
        levels = _candidate_levels(
            strategy_events,
            signal_index,
            kind="SUPPORT" if trade.direction == "BUY" else "RESISTANCE",
            entry_price=entry,
        )
        level = _last_qualified_stop_level(levels)
        if level is None:
            bins["NONE"] += 1
            continue
        structural_stop = (
            level.price - STRUCTURE_BUFFER_PIPS * PIP
            if trade.direction == "BUY"
            else level.price + STRUCTURE_BUFFER_PIPS * PIP
        )
        distance_pips = abs(entry - structural_stop) / PIP
        if distance_pips <= 24.0:
            bins["<=24"] += 1
        elif distance_pips <= 36.0:
            bins["24-36"] += 1
        elif distance_pips <= 48.0:
            bins["36-48"] += 1
        else:
            bins[">48"] += 1
    return bins


def _run_variant(
    *,
    name: str,
    floor_pips: float,
    runtime: StructuralSlTpRuntime,
    baseline_summary: WorkspaceHistoricalReplaySummary,
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    strategy_index: dict[datetime, int],
    execution_events: tuple[WorkspaceMarketEvent, ...],
    execution_index: dict[datetime, int],
    records_by_uid: dict,
    structural_stop_enabled: bool,
    structural_take_enabled: bool,
) -> QualifiedVariantResult:
    trades: list[WorkspaceHistoricalTradeDiagnostic] = []
    for trade in baseline_trades:
        record = records_by_uid[trade.signal_uid]
        signal_event = runtime.strategy_events[trade.signal_timestamp]
        plan = _build_qualified_plan(
            trade,
            strategy_events,
            strategy_index,
            floor_pips=floor_pips,
            structural_stop_enabled=structural_stop_enabled,
            structural_take_enabled=structural_take_enabled,
        )
        counterfactual = _simulate_one(
            runtime,
            trade,
            record,
            signal_event,
            execution_events,
            execution_index,
            plan,
        )
        trades.append(counterfactual)
    trade_tuple = tuple(trades)
    return QualifiedVariantResult(
        name=name,
        floor_pips=floor_pips,
        trades=trade_tuple,
        summary=_variant_summary(baseline_summary, trade_tuple),
    )


def _focus_line(
    trade: WorkspaceHistoricalTradeDiagnostic,
    *,
    stop_only: QualifiedVariantResult,
    tp_only: QualifiedVariantResult,
    both: QualifiedVariantResult,
) -> str:
    index_by_uid = {item.signal_uid: pos for pos, item in enumerate(stop_only.trades)}
    pos = index_by_uid[trade.signal_uid]
    stop_trade = stop_only.trades[pos]
    tp_trade = tp_only.trades[pos]
    both_trade = both.trades[pos]
    return (
        f"    {trade.signal_timestamp.isoformat()} {trade.direction} "
        f"base:{trade.close_reason}/{trade.final_profit:+.2f} "
        f"SLonly:{stop_trade.close_reason}/{stop_trade.final_profit:+.2f} "
        f"TPonly:{tp_trade.close_reason}/{tp_trade.final_profit:+.2f} "
        f"BOTH:{both_trade.close_reason}/{both_trade.final_profit:+.2f}"
    )


def main() -> None:
    """Run qualified level inventory and paired decoupled variants."""
    assert_frozen_oos_snapshot()
    runtime = StructuralSlTpRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    _assert_baseline(runtime)

    baseline_summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert baseline_summary is not None
    assert execution is not None
    baseline_trades = execution.trade_diagnostics()
    assert len(baseline_trades) == 59

    strategy_events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    strategy_index = {
        event.timestamp: index for index, event in enumerate(strategy_events)
    }
    execution_events = _flatten_execution_events(runtime)
    execution_index = {
        event.timestamp: index for index, event in enumerate(execution_events)
    }
    records_by_uid = {
        record.signal_uid: record for record in runtime.historical_signal_records
    }

    inventory = _touch_inventory(baseline_trades, strategy_events, strategy_index)
    stop_bins = _stop_distance_bins(baseline_trades, strategy_events, strategy_index)

    variants: dict[tuple[float, str], QualifiedVariantResult] = {}
    for floor_pips in SL_FLOORS_PIPS:
        variants[(floor_pips, "SL_ONLY")] = _run_variant(
            name="SL_ONLY",
            floor_pips=floor_pips,
            runtime=runtime,
            baseline_summary=baseline_summary,
            baseline_trades=baseline_trades,
            strategy_events=strategy_events,
            strategy_index=strategy_index,
            execution_events=execution_events,
            execution_index=execution_index,
            records_by_uid=records_by_uid,
            structural_stop_enabled=True,
            structural_take_enabled=False,
        )
        variants[(floor_pips, "TP_ONLY")] = _run_variant(
            name="TP_ONLY",
            floor_pips=floor_pips,
            runtime=runtime,
            baseline_summary=baseline_summary,
            baseline_trades=baseline_trades,
            strategy_events=strategy_events,
            strategy_index=strategy_index,
            execution_events=execution_events,
            execution_index=execution_index,
            records_by_uid=records_by_uid,
            structural_stop_enabled=False,
            structural_take_enabled=True,
        )
        variants[(floor_pips, "BOTH")] = _run_variant(
            name="BOTH",
            floor_pips=floor_pips,
            runtime=runtime,
            baseline_summary=baseline_summary,
            baseline_trades=baseline_trades,
            strategy_events=strategy_events,
            strategy_index=strategy_index,
            execution_events=execution_events,
            execution_index=execution_index,
            records_by_uid=records_by_uid,
            structural_stop_enabled=True,
            structural_take_enabled=True,
        )

    print("Algorithm Workspace Candidate F Qualified Structural SL/TP 2025 result")
    print("  mode=PRODUCTION_6K_QUALIFIED_STRUCTURAL_SL_TP_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  paired_entries_fixed_to_production=True")
    print("  future_price_used_to_define_levels=False")
    print(f"  qualified_min_touches={QUALIFIED_MIN_TOUCHES}")
    print(f"  minimum_structural_tp_pips={MIN_STRUCTURAL_TP_PIPS:.1f}")
    print(f"  baseline={_summary_text(baseline_summary)}")
    print("  level_qualification_inventory:")
    for touches in (1, 2, 3):
        row = inventory[touches]
        print(
            f"    touches>={touches}: stop:{row['stop_found']}/59,"
            f"take_any:{row['take_found_any']}/59,"
            f"take_24plus:{row['take_found_24']}/59"
        )
    print(
        "  qualified_structural_stop_distance_bins_pips="
        f"NONE:{stop_bins['NONE']},<=24:{stop_bins['<=24']},"
        f"24-36:{stop_bins['24-36']},36-48:{stop_bins['36-48']},"
        f">48:{stop_bins['>48']}"
    )
    for floor_pips in SL_FLOORS_PIPS:
        print(f"  floor_{floor_pips:.0f}pip_variants:")
        for name in ("SL_ONLY", "TP_ONLY", "BOTH"):
            result = variants[(floor_pips, name)]
            print(f"    {name}={_summary_text(result.summary)}")
    print("  focus_cases_floor12:")
    focus = tuple(
        trade for trade in baseline_trades if trade.signal_timestamp in FOCUS_CASES
    )
    for trade in focus:
        print(
            _focus_line(
                trade,
                stop_only=variants[(12.0, "SL_ONLY")],
                tp_only=variants[(12.0, "TP_ONLY")],
                both=variants[(12.0, "BOTH")],
            )
        )
    print("  tp_nearer_than_24pips_is_never_used=True")
    print("  sl_tp_effects_decoupled=True")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_QUALIFIED_STRUCTURAL_SL_TP_2025_CHECK=OK")


if __name__ == "__main__":
    main()
