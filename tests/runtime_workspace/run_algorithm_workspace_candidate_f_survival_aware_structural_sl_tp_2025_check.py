# -*- coding: utf-8 -*-
"""RoadMap103 / 7R: survival-aware Structural SL/TP counterfactual 2025.

Runner повторює production Candidate F після 6K без змін і для тих самих
59 baseline entries запускає paired counterfactual protection на causal
horizontal S/R zones з 7Q.

7R використовує тільки zone role/survival, уже доступні на signal timestamp.
INVALIDATED zones не використовуються. Для STOP і TAKE застосовуються окремі
практичні distance windows; відстань рахується до фактичної protection price
після 1 pip buffer за/перед усією зоною. Якщо придатної зони немає, відповідна
production SL/TP лишається без змін. Немає 2R fallback, quality score, age gate
чи нової entry policy.

Це paired diagnostic: signal/entry timestamp, entry price і volume фіксуються
за production baseline. Змінена тривалість counterfactual position не створює
і не блокує інші baseline entries через capacity.
"""

from __future__ import annotations

import csv
import importlib
import math
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

_structural = importlib.import_module(
    "run_algorithm_workspace_candidate_f_structural_sl_tp_2025_check"
)
FOCUS_CASES = _structural.FOCUS_CASES
PIP = _structural.PIP
STRUCTURE_BUFFER_PIPS = _structural.STRUCTURE_BUFFER_PIPS
StructuralProtectionPlan = _structural.StructuralProtectionPlan
StructuralSlTpRuntime = _structural.StructuralSlTpRuntime
_assert_baseline = getattr(_structural, "_assert_baseline")
_directional_price = getattr(_structural, "_directional_price")
_flatten_execution_events = getattr(_structural, "_flatten_execution_events")
_simulate_one = getattr(_structural, "_simulate_one")
_summary_text = getattr(_structural, "_summary_text")
_variant_summary = getattr(_structural, "_variant_summary")

_survival = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)
_all_observations = getattr(_survival, "_all_observations")
_zone_text = getattr(_survival, "_zone_text")

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
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7R_Survival_Aware_Structural_SL_TP_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_survival_aware_structural_sl_tp_2025.csv"

SL_WINDOWS = (
    ("SL_12_24", 12.0, 24.0),
    ("SL_12_36", 12.0, 36.0),
    ("SL_18_36", 18.0, 36.0),
)
TP_WINDOWS = (
    ("TP_24_36", 24.0, 36.0),
    ("TP_24_48", 24.0, 48.0),
    ("TP_24_72", 24.0, 72.0),
)
BOTH_WINDOWS = (
    ("BOTH_NARROW", (12.0, 24.0), (24.0, 36.0)),
    ("BOTH_MEDIUM", (12.0, 36.0), (24.0, 48.0)),
    ("BOTH_WIDE_TARGET", (18.0, 36.0), (24.0, 72.0)),
)


@dataclass(frozen=True, slots=True)
class CounterfactualPlan:
    """Protection plan плюс вибрані survival-aware zones."""

    protection: Any
    stop_zone: Any | None
    take_zone: Any | None
    stop_source: str
    take_source: str
    stop_distance_pips: float
    take_distance_pips: float


@dataclass(frozen=True, slots=True)
class VariantResult:
    """Один paired variant та його performance/change diagnostics."""

    name: str
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    summary: WorkspaceHistoricalReplaySummary
    plans: dict[str, CounterfactualPlan]
    changed_trades: int
    improved_trades: int
    worsened_trades: int
    unchanged_trades: int
    sl_saved: int
    sl_made_worse: int
    tp_added: int
    tp_lost_existing_profit: int


def _zone_stop_price(trade: WorkspaceHistoricalTradeDiagnostic, item: Any) -> float:
    zone = item.zone
    buffer_distance = STRUCTURE_BUFFER_PIPS * PIP
    if trade.direction == "BUY":
        return zone.low - buffer_distance
    return zone.high + buffer_distance


def _zone_take_price(trade: WorkspaceHistoricalTradeDiagnostic, item: Any) -> float:
    zone = item.zone
    buffer_distance = STRUCTURE_BUFFER_PIPS * PIP
    if trade.direction == "BUY":
        return zone.low - buffer_distance
    return zone.high + buffer_distance


def _actual_distance_pips(entry_price: float, price: float) -> float:
    return abs(price - entry_price) / PIP


def _candidate_sort_key(item: Any, distance_pips: float) -> tuple[float, int, int]:
    interaction_age = item.last_interaction_age_bars
    return (
        distance_pips,
        interaction_age if interaction_age is not None else 1_000_000,
        -item.zone.pivot_count,
    )


def _select_zone(
    trade: WorkspaceHistoricalTradeDiagnostic,
    observations: tuple[Any, ...],
    *,
    role: str,
    minimum_pips: float,
    maximum_pips: float,
) -> tuple[Any | None, float | None, float | None]:
    candidates: list[tuple[tuple[float, int, int], Any, float, float]] = []
    for item in observations:
        if item.signal_timestamp != trade.signal_timestamp:
            continue
        if item.distance_role != role or item.effective_role == "INVALIDATED":
            continue
        price = (
            _zone_stop_price(trade, item)
            if role == "STOP"
            else _zone_take_price(trade, item)
        )
        distance_pips = _actual_distance_pips(trade.entry_price, price)
        if not minimum_pips <= distance_pips <= maximum_pips:
            continue
        if trade.direction == "BUY":
            usable = (
                price < trade.entry_price
                if role == "STOP"
                else price > trade.entry_price
            )
        else:
            usable = (
                price > trade.entry_price
                if role == "STOP"
                else price < trade.entry_price
            )
        if not usable:
            continue
        candidates.append(
            (
                _candidate_sort_key(item, distance_pips),
                item,
                price,
                distance_pips,
            )
        )
    if not candidates:
        return None, None, None
    _, item, price, distance_pips = min(candidates, key=lambda row: row[0])
    return item, price, distance_pips


def _production_price(
    trade: WorkspaceHistoricalTradeDiagnostic,
    *,
    role: str,
) -> tuple[float, float]:
    if role == "STOP":
        distance = trade.stop_loss_distance
        favorable = False
    else:
        distance = trade.take_profit_distance
        favorable = True
    price = _directional_price(
        trade.direction,
        trade.entry_price,
        distance,
        favorable=favorable,
    )
    return price, distance / PIP


def _build_plan(
    trade: WorkspaceHistoricalTradeDiagnostic,
    observations: tuple[Any, ...],
    *,
    stop_window: tuple[float, float] | None,
    take_window: tuple[float, float] | None,
) -> CounterfactualPlan:
    stop_zone = None
    take_zone = None
    stop_price, stop_distance_pips = _production_price(trade, role="STOP")
    take_price, take_distance_pips = _production_price(trade, role="TAKE")
    stop_source = "PRODUCTION"
    take_source = "PRODUCTION"

    if stop_window is not None:
        stop_zone, selected_price, selected_distance = _select_zone(
            trade,
            observations,
            role="STOP",
            minimum_pips=stop_window[0],
            maximum_pips=stop_window[1],
        )
        if stop_zone is not None:
            assert selected_price is not None
            assert selected_distance is not None
            stop_price = selected_price
            stop_distance_pips = selected_distance
            stop_source = "SURVIVAL_ZONE"

    if take_window is not None:
        take_zone, selected_price, selected_distance = _select_zone(
            trade,
            observations,
            role="TAKE",
            minimum_pips=take_window[0],
            maximum_pips=take_window[1],
        )
        if take_zone is not None:
            assert selected_price is not None
            assert selected_distance is not None
            take_price = selected_price
            take_distance_pips = selected_distance
            take_source = "SURVIVAL_ZONE"

    stop_distance = stop_distance_pips * PIP
    take_distance = take_distance_pips * PIP
    if trade.direction == "BUY":
        assert stop_price < trade.entry_price < take_price
    else:
        assert take_price < trade.entry_price < stop_price

    protection = StructuralProtectionPlan(
        floor_pips=0.0,
        entry_price=trade.entry_price,
        support=None,
        resistance=None,
        stop_loss=stop_price,
        take_profit=take_price,
        stop_distance=stop_distance,
        take_distance=take_distance,
        stop_source=stop_source,
        take_source=take_source,
        fallback_used=(
            stop_source == "PRODUCTION" or take_source == "PRODUCTION"
        ),
    )
    return CounterfactualPlan(
        protection=protection,
        stop_zone=stop_zone,
        take_zone=take_zone,
        stop_source=stop_source,
        take_source=take_source,
        stop_distance_pips=stop_distance_pips,
        take_distance_pips=take_distance_pips,
    )


def _change_metrics(
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    plans: dict[str, CounterfactualPlan],
) -> tuple[int, int, int, int, int, int, int, int]:
    changed = improved = worsened = unchanged = 0
    sl_saved = sl_made_worse = tp_added = tp_lost_existing_profit = 0
    for baseline, result in zip(baseline_trades, trades, strict=True):
        plan = plans[baseline.signal_uid]
        sl_changed = plan.stop_source == "SURVIVAL_ZONE"
        tp_changed = plan.take_source == "SURVIVAL_ZONE"
        if sl_changed or tp_changed:
            changed += 1
        delta = result.final_profit - baseline.final_profit
        if delta > 1e-9:
            improved += 1
        elif delta < -1e-9:
            worsened += 1
        else:
            unchanged += 1
        if (
            sl_changed
            and baseline.close_reason == "STOP_LOSS"
            and result.close_reason != "STOP_LOSS"
            and delta > 1e-9
        ):
            sl_saved += 1
        if sl_changed and delta < -1e-9:
            sl_made_worse += 1
        if (
            tp_changed
            and baseline.close_reason != "TAKE_PROFIT"
            and result.close_reason == "TAKE_PROFIT"
            and delta > 1e-9
        ):
            tp_added += 1
        if (
            tp_changed
            and baseline.final_profit > 0.0
            and delta < -1e-9
        ):
            tp_lost_existing_profit += 1
    return (
        changed,
        improved,
        worsened,
        unchanged,
        sl_saved,
        sl_made_worse,
        tp_added,
        tp_lost_existing_profit,
    )


def _run_variant(
    *,
    name: str,
    runtime: Any,
    baseline_summary: WorkspaceHistoricalReplaySummary,
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    observations: tuple[Any, ...],
    execution_events: tuple[WorkspaceMarketEvent, ...],
    execution_index: dict[datetime, int],
    records_by_uid: dict[str, WorkspaceSignalRecord],
    stop_window: tuple[float, float] | None,
    take_window: tuple[float, float] | None,
) -> VariantResult:
    trades: list[WorkspaceHistoricalTradeDiagnostic] = []
    plans: dict[str, CounterfactualPlan] = {}
    for trade in baseline_trades:
        record = records_by_uid[trade.signal_uid]
        signal_event = runtime.strategy_events[trade.signal_timestamp]
        plan = _build_plan(
            trade,
            observations,
            stop_window=stop_window,
            take_window=take_window,
        )
        plans[trade.signal_uid] = plan
        trades.append(
            _simulate_one(
                runtime,
                trade,
                record,
                signal_event,
                execution_events,
                execution_index,
                plan.protection,
            )
        )
    trade_tuple = tuple(trades)
    metrics = _change_metrics(baseline_trades, trade_tuple, plans)
    return VariantResult(
        name=name,
        trades=trade_tuple,
        summary=_variant_summary(baseline_summary, trade_tuple),
        plans=plans,
        changed_trades=metrics[0],
        improved_trades=metrics[1],
        worsened_trades=metrics[2],
        unchanged_trades=metrics[3],
        sl_saved=metrics[4],
        sl_made_worse=metrics[5],
        tp_added=metrics[6],
        tp_lost_existing_profit=metrics[7],
    )


def _metrics_text(result: VariantResult) -> str:
    return (
        f"changed:{result.changed_trades},improved:{result.improved_trades},"
        f"worsened:{result.worsened_trades},unchanged:{result.unchanged_trades},"
        f"sl_saved:{result.sl_saved},sl_worse:{result.sl_made_worse},"
        f"tp_added:{result.tp_added},"
        f"tp_lost_profit:{result.tp_lost_existing_profit}"
    )


def _trade_for_uid(
    result: VariantResult,
    signal_uid: str,
) -> WorkspaceHistoricalTradeDiagnostic:
    for trade in result.trades:
        if trade.signal_uid == signal_uid:
            return trade
    raise AssertionError(signal_uid)


def _compact_trade(
    result: VariantResult,
    baseline: WorkspaceHistoricalTradeDiagnostic,
) -> str:
    trade = _trade_for_uid(result, baseline.signal_uid)
    plan = result.plans[baseline.signal_uid]
    changed = (
        ("S" if plan.stop_source == "SURVIVAL_ZONE" else "-")
        + ("T" if plan.take_source == "SURVIVAL_ZONE" else "-")
    )
    return f"{trade.close_reason}/{trade.final_profit:+.2f}/{changed}"


def _zone_short(item: Any | None) -> str:
    if item is None:
        return "NONE"
    return _zone_text(item)


def _write_csv(
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    variants: tuple[VariantResult, ...],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "variant",
        "signal_utc",
        "direction",
        "entry_price",
        "production_reason",
        "production_pnl",
        "stop_source",
        "stop_distance_pips",
        "stop_zone",
        "take_source",
        "take_distance_pips",
        "take_zone",
        "counterfactual_reason",
        "counterfactual_pnl",
        "delta_pnl",
        "focus_case",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for variant in variants:
            for baseline in baseline_trades:
                result = _trade_for_uid(variant, baseline.signal_uid)
                plan = variant.plans[baseline.signal_uid]
                writer.writerow(
                    {
                        "variant": variant.name,
                        "signal_utc": baseline.signal_timestamp.isoformat(),
                        "direction": baseline.direction,
                        "entry_price": f"{baseline.entry_price:.5f}",
                        "production_reason": baseline.close_reason,
                        "production_pnl": f"{baseline.final_profit:.4f}",
                        "stop_source": plan.stop_source,
                        "stop_distance_pips": f"{plan.stop_distance_pips:.2f}",
                        "stop_zone": _zone_short(plan.stop_zone),
                        "take_source": plan.take_source,
                        "take_distance_pips": f"{plan.take_distance_pips:.2f}",
                        "take_zone": _zone_short(plan.take_zone),
                        "counterfactual_reason": result.close_reason,
                        "counterfactual_pnl": f"{result.final_profit:.4f}",
                        "delta_pnl": (
                            f"{result.final_profit - baseline.final_profit:+.4f}"
                        ),
                        "focus_case": (
                            "YES"
                            if baseline.signal_timestamp in FOCUS_CASES
                            else "NO"
                        ),
                    }
                )
    return OUTPUT_CSV


def _assert_variant_contracts(variants: tuple[VariantResult, ...]) -> None:
    for result in variants:
        assert len(result.trades) == 59
        assert result.changed_trades <= 59
        assert (
            result.improved_trades
            + result.worsened_trades
            + result.unchanged_trades
            == 59
        )
        for plan in result.plans.values():
            assert plan.stop_distance_pips > 0.0
            assert plan.take_distance_pips > 0.0
            assert math.isfinite(plan.stop_distance_pips)
            assert math.isfinite(plan.take_distance_pips)
            if result.name.startswith("SL_"):
                assert plan.take_source == "PRODUCTION"
            if result.name.startswith("TP_"):
                assert plan.stop_source == "PRODUCTION"


def main() -> None:
    """Run survival-aware paired SL_ONLY, TP_ONLY and BOTH variants."""
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
    observations = _all_observations(
        baseline_trades,
        strategy_events,
        strategy_index,
    )
    assert observations

    execution_events = _flatten_execution_events(runtime)
    execution_index = {
        event.timestamp: index for index, event in enumerate(execution_events)
    }
    records_by_uid = {
        record.signal_uid: record for record in runtime.historical_signal_records
    }

    variants: list[VariantResult] = []
    sl_results: dict[str, VariantResult] = {}
    tp_results: dict[str, VariantResult] = {}
    both_results: dict[str, VariantResult] = {}

    for name, minimum, maximum in SL_WINDOWS:
        result = _run_variant(
            name=name,
            runtime=runtime,
            baseline_summary=baseline_summary,
            baseline_trades=baseline_trades,
            observations=observations,
            execution_events=execution_events,
            execution_index=execution_index,
            records_by_uid=records_by_uid,
            stop_window=(minimum, maximum),
            take_window=None,
        )
        variants.append(result)
        sl_results[name] = result

    for name, minimum, maximum in TP_WINDOWS:
        result = _run_variant(
            name=name,
            runtime=runtime,
            baseline_summary=baseline_summary,
            baseline_trades=baseline_trades,
            observations=observations,
            execution_events=execution_events,
            execution_index=execution_index,
            records_by_uid=records_by_uid,
            stop_window=None,
            take_window=(minimum, maximum),
        )
        variants.append(result)
        tp_results[name] = result

    for name, stop_window, take_window in BOTH_WINDOWS:
        result = _run_variant(
            name=name,
            runtime=runtime,
            baseline_summary=baseline_summary,
            baseline_trades=baseline_trades,
            observations=observations,
            execution_events=execution_events,
            execution_index=execution_index,
            records_by_uid=records_by_uid,
            stop_window=stop_window,
            take_window=take_window,
        )
        variants.append(result)
        both_results[name] = result

    variant_tuple = tuple(variants)
    _assert_variant_contracts(variant_tuple)
    output_csv = _write_csv(baseline_trades, variant_tuple)

    focus_trades = tuple(
        trade
        for trade in baseline_trades
        if trade.signal_timestamp in FOCUS_CASES
    )
    assert len(focus_trades) == len(FOCUS_CASES)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print(
        "Algorithm Workspace Candidate F Survival-aware Structural SL/TP "
        "2025 result"
    )
    print("  mode=PRODUCTION_6K_SURVIVAL_AWARE_STRUCTURAL_SL_TP_COUNTERFACTUAL_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  paired_trade_counterfactual_only=True")
    print("  paired_entries_fixed_to_production=True")
    print("  changed_capacity_does_not_create_or_block_entries=True")
    print("  future_price_used_to_define_or_select_zones=False")
    print("  zone_model=CAUSAL_HORIZONTAL_PRICE_BAND_SURVIVAL_ROLE_AWARE")
    print(f"  structure_buffer_pips={STRUCTURE_BUFFER_PIPS:.1f}")
    print("  distance_window_basis=ACTUAL_PROTECTION_PRICE_AFTER_ZONE_BUFFER")
    print("  no_quality_score=True")
    print("  no_age_gate=True")
    print("  no_2R_fallback=True")
    print(f"  baseline={_summary_text(baseline_summary)}")
    print("  SL_ONLY_variants:")
    for name, minimum, maximum in SL_WINDOWS:
        result = sl_results[name]
        print(
            f"    {name}[{minimum:.0f}-{maximum:.0f}p]="
            f"{_summary_text(result.summary)} | {_metrics_text(result)}"
        )
    print("  TP_ONLY_variants:")
    for name, minimum, maximum in TP_WINDOWS:
        result = tp_results[name]
        print(
            f"    {name}[{minimum:.0f}-{maximum:.0f}p]="
            f"{_summary_text(result.summary)} | {_metrics_text(result)}"
        )
    print("  BOTH_variants:")
    for name, stop_window, take_window in BOTH_WINDOWS:
        result = both_results[name]
        print(
            f"    {name}[SL:{stop_window[0]:.0f}-{stop_window[1]:.0f}p;"
            f"TP:{take_window[0]:.0f}-{take_window[1]:.0f}p]="
            f"{_summary_text(result.summary)} | {_metrics_text(result)}"
        )

    print("  chronological_focus_cases:")
    for index, trade in enumerate(focus_trades, start=1):
        print(
            f"    {index:02d}. {trade.signal_timestamp.isoformat()} "
            f"{trade.direction} base:{trade.close_reason}/"
            f"{trade.final_profit:+.2f}"
        )
        print(
            "        SL="
            f"12-24:{_compact_trade(sl_results['SL_12_24'], trade)} | "
            f"12-36:{_compact_trade(sl_results['SL_12_36'], trade)} | "
            f"18-36:{_compact_trade(sl_results['SL_18_36'], trade)}"
        )
        print(
            "        TP="
            f"24-36:{_compact_trade(tp_results['TP_24_36'], trade)} | "
            f"24-48:{_compact_trade(tp_results['TP_24_48'], trade)} | "
            f"24-72:{_compact_trade(tp_results['TP_24_72'], trade)}"
        )
        print(
            "        BOTH="
            f"N:{_compact_trade(both_results['BOTH_NARROW'], trade)} | "
            f"M:{_compact_trade(both_results['BOTH_MEDIUM'], trade)} | "
            f"W:{_compact_trade(both_results['BOTH_WIDE_TARGET'], trade)}"
        )

    print(f"  output_csv={output_csv}")
    print("  survival_role_filter_applied=True")
    print("  invalidated_zones_never_used=True")
    print("  sl_tp_effects_decoupled=True")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  production_6k_profit_drawdown_recovery_preserved_per_trade=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_SURVIVAL_AWARE_STRUCTURAL_SL_TP_"
        "2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
