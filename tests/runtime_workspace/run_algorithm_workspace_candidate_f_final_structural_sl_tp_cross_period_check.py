# -*- coding: utf-8 -*-
"""RoadMap103 / 8A: final structural SL/TP geometry cross-period check.

Runner не змінює production Candidate F. Для тих самих production entries
EURUSD 2025 та відомого 2026 window виконується paired counterfactual з
узгодженою bounded protection geometry:

- SL: 12 pip fallback; survival-aware STOP zone дозволена тільки якщо після
  1 pip buffer фактична відстань лежить у межах 12..24 pip;
- TP: спочатку 2R від фактичного SL; survival-aware TAKE zone дозволена лише
  як ближча значуща ціль у межах max(24 pip, 1R)..2R;
- TP не переноситься після пробою; continuation має вимагати нового signal;
- INVALIDATED zones не використовуються, future bars не визначають levels.

Окремо рахуються FIXED_12_2R, ZONE_SL_2R і FINAL_ZONE_SL_TP, щоб не змішувати
вплив bounded structural SL з influence structural TP. Entry timestamps,
prices і volume фіксуються за production baseline; capacity не моделюється
повторно, тому performance є paired diagnostic, а не portfolio backtest.
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
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

_structural = importlib.import_module(
    "run_algorithm_workspace_candidate_f_structural_sl_tp_2025_check"
)
StructuralProtectionPlan = _structural.StructuralProtectionPlan
StructuralSlTpRuntime = _structural.StructuralSlTpRuntime
_flatten_execution_events = getattr(_structural, "_flatten_execution_events")
_simulate_one = getattr(_structural, "_simulate_one")
_summary_text = getattr(_structural, "_summary_text")
_variant_summary = getattr(_structural, "_variant_summary")

_survival = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)
_all_observations = getattr(_survival, "_all_observations")
_zone_text = getattr(_survival, "_zone_text")

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalReplaySummary,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    new_workspace_indicator_profile_bindings,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
    resolve_forex_pip_size,
    resolve_new_workspace_macd_extremum_min_prominence,
    resolve_new_workspace_macd_extremum_to_cross_min_distance,
    resolve_workspace_history_default_spread,
)

SYMBOL = "EURUSD"
SOURCE_BROKER = "CTRADER"
PIP_SIZE = resolve_forex_pip_size(SYMBOL)
SPREAD_LIMIT_PIPS = 2.0
STRUCTURE_BUFFER_PIPS = 1.0
SL_FALLBACK_PIPS = 12.0
SL_MAXIMUM_PIPS = 24.0
TP_MINIMUM_PIPS = 24.0
TP_FALLBACK_R = 2.0
EPSILON = 1e-9

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_8A_Final_Structural_SL_TP_Cross_Period"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_final_structural_sl_tp_cross_period.csv"


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """Один frozen EURUSD Replay period для paired SL/TP diagnostic."""

    label: str
    file_name: str
    start_utc: str
    end_utc: str
    expected_baseline: tuple[int, int, int, int, float, float, float]


@dataclass(frozen=True, slots=True)
class ProtectionPlan:
    """Final protection geometry плюс selected survival-aware zones."""

    protection: Any
    stop_zone: Any | None
    take_zone: Any | None
    stop_source: str
    take_source: str
    stop_distance_pips: float
    take_distance_pips: float


@dataclass(frozen=True, slots=True)
class VariantResult:
    """Paired counterfactual variant одного Replay period."""

    name: str
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    summary: WorkspaceHistoricalReplaySummary
    plans: dict[str, ProtectionPlan]
    improved: int
    worsened: int
    unchanged: int


WINDOWS = (
    ReplayWindow(
        label="2025",
        file_name="2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv",
        start_utc="2025-01-01T22:01:00+00:00",
        end_utc="2025-12-31T21:58:00+00:00",
        expected_baseline=(59, 40, 18, 1, -4.05, 0.7808441558444823, 5.80),
    ),
    ReplayWindow(
        label="2026_TO_2026-08-25_15:07",
        file_name="2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv",
        start_utc="2026-01-01T22:01:00+00:00",
        end_utc="2026-08-25T15:07:00+00:00",
        expected_baseline=(29, 23, 5, 1, 1.37, 1.2518382352948338, 3.53),
    ),
)

VARIANT_FIXED = "FIXED_12_2R"
VARIANT_ZONE_SL = "ZONE_SL_2R"
VARIANT_FINAL = "FINAL_ZONE_SL_TP"
VARIANTS = (VARIANT_FIXED, VARIANT_ZONE_SL, VARIANT_FINAL)


def _candidate_bindings() -> dict[str, dict[str, object]]:
    """Повернути frozen Candidate F Alligator binding."""
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def _workspace(window: ReplayWindow) -> AlgorithmWorkspace:
    """Створити production-equivalent Candidate F EURUSD Replay WSP."""
    history_file = (
        PROJECT_ROOT
        / "data"
        / "history"
        / SOURCE_BROKER
        / SYMBOL
        / "M1"
        / window.file_name
    )
    assert history_file.is_file(), history_file
    return AlgorithmWorkspace.create(
        broker=SOURCE_BROKER,
        account_id=None,
        account_mode=None,
        symbol=SYMBOL,
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=f"RM103 8A Final SL/TP {window.label}",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": (
                WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
            ),
            "spread_limit": SPREAD_LIMIT_PIPS * PIP_SIZE,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": (
                resolve_new_workspace_macd_extremum_min_prominence(SYMBOL)
            ),
            "macd_extremum_to_cross_min_distance": (
                resolve_new_workspace_macd_extremum_to_cross_min_distance(SYMBOL)
            ),
            "macd_cross_min_angle": 45.0,
            "macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "macd_cross_min_abc_angle": 2.25,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(history_file),
            "start_utc": window.start_utc,
            "end_utc": window.end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": resolve_workspace_history_default_spread(SYMBOL),
            "source": history_file.stem,
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=_candidate_bindings(),
    )


def _assert_baseline(
    summary: WorkspaceHistoricalReplaySummary,
    expected: tuple[int, int, int, int, float, float, float],
) -> None:
    """Зафіксувати production baseline для поточного period."""
    trades, wins, losses, break_even, net, pf, dd = expected
    assert summary.opened_trades == trades
    assert summary.winning_trades == wins
    assert summary.losing_trades == losses
    assert summary.break_even_trades == break_even
    assert math.isclose(summary.net_profit, net, abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, pf, abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, dd, abs_tol=0.005)


def _directional_price(
    direction: str,
    entry_price: float,
    distance: float,
    *,
    favorable: bool,
) -> float:
    """Перетворити directional distance на absolute price."""
    sign = 1.0 if direction == "BUY" else -1.0
    if not favorable:
        sign = -sign
    return entry_price + sign * distance


def _stop_price(trade: WorkspaceHistoricalTradeDiagnostic, item: Any) -> float:
    """Поставити SL за дальньою межею zone плюс 1 pip buffer."""
    buffer_distance = STRUCTURE_BUFFER_PIPS * PIP_SIZE
    if trade.direction == "BUY":
        return item.zone.low - buffer_distance
    return item.zone.high + buffer_distance


def _take_price(trade: WorkspaceHistoricalTradeDiagnostic, item: Any) -> float:
    """Поставити TP перед ближньою межею opposite zone на 1 pip."""
    buffer_distance = STRUCTURE_BUFFER_PIPS * PIP_SIZE
    if trade.direction == "BUY":
        return item.zone.low - buffer_distance
    return item.zone.high + buffer_distance


def _distance_pips(entry_price: float, price: float) -> float:
    return abs(price - entry_price) / PIP_SIZE


def _usable_price(
    trade: WorkspaceHistoricalTradeDiagnostic,
    *,
    role: str,
    price: float,
) -> bool:
    if trade.direction == "BUY":
        if role == "STOP":
            return price < trade.entry_price
        return price > trade.entry_price
    if role == "STOP":
        return price > trade.entry_price
    return price < trade.entry_price


def _zone_sort_key(item: Any, distance_pips: float) -> tuple[float, int, int]:
    age = item.last_interaction_age_bars
    return (
        distance_pips,
        age if age is not None else 1_000_000,
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
    """Вибрати nearest causal survival-aware zone у bounded distance window."""
    candidates: list[tuple[tuple[float, int, int], Any, float, float]] = []
    for item in observations:
        if item.signal_timestamp != trade.signal_timestamp:
            continue
        if item.distance_role != role or item.effective_role == "INVALIDATED":
            continue
        price = _stop_price(trade, item) if role == "STOP" else _take_price(trade, item)
        if not _usable_price(trade, role=role, price=price):
            continue
        distance = _distance_pips(trade.entry_price, price)
        if not minimum_pips <= distance <= maximum_pips:
            continue
        candidates.append((_zone_sort_key(item, distance), item, price, distance))
    if not candidates:
        return None, None, None
    _, item, price, distance = min(candidates, key=lambda row: row[0])
    return item, price, distance


def _build_plan(
    trade: WorkspaceHistoricalTradeDiagnostic,
    observations: tuple[Any, ...],
    *,
    variant: str,
) -> ProtectionPlan:
    """Побудувати bounded fixed/zone protection plan для одного trade."""
    assert variant in VARIANTS
    stop_zone = None
    take_zone = None
    stop_distance_pips = SL_FALLBACK_PIPS
    stop_source = "FIXED_12P"
    stop_price = _directional_price(
        trade.direction,
        trade.entry_price,
        stop_distance_pips * PIP_SIZE,
        favorable=False,
    )

    if variant in {VARIANT_ZONE_SL, VARIANT_FINAL}:
        stop_zone, selected_price, selected_distance = _select_zone(
            trade,
            observations,
            role="STOP",
            minimum_pips=SL_FALLBACK_PIPS,
            maximum_pips=SL_MAXIMUM_PIPS,
        )
        if stop_zone is not None:
            assert selected_price is not None
            assert selected_distance is not None
            stop_price = selected_price
            stop_distance_pips = selected_distance
            stop_source = "SURVIVAL_ZONE_12_24"

    fallback_take_pips = stop_distance_pips * TP_FALLBACK_R
    take_distance_pips = fallback_take_pips
    take_source = "FALLBACK_2R"
    take_price = _directional_price(
        trade.direction,
        trade.entry_price,
        take_distance_pips * PIP_SIZE,
        favorable=True,
    )

    if variant == VARIANT_FINAL:
        minimum_take_pips = max(TP_MINIMUM_PIPS, stop_distance_pips)
        take_zone, selected_price, selected_distance = _select_zone(
            trade,
            observations,
            role="TAKE",
            minimum_pips=minimum_take_pips,
            maximum_pips=fallback_take_pips,
        )
        if take_zone is not None:
            assert selected_price is not None
            assert selected_distance is not None
            take_price = selected_price
            take_distance_pips = selected_distance
            take_source = "SURVIVAL_ZONE_BEFORE_2R"

    assert SL_FALLBACK_PIPS <= stop_distance_pips <= SL_MAXIMUM_PIPS
    assert take_distance_pips >= TP_MINIMUM_PIPS
    assert take_distance_pips <= fallback_take_pips + EPSILON
    if trade.direction == "BUY":
        assert stop_price < trade.entry_price < take_price
    else:
        assert take_price < trade.entry_price < stop_price

    protection = StructuralProtectionPlan(
        floor_pips=SL_FALLBACK_PIPS,
        entry_price=trade.entry_price,
        support=None,
        resistance=None,
        stop_loss=stop_price,
        take_profit=take_price,
        stop_distance=stop_distance_pips * PIP_SIZE,
        take_distance=take_distance_pips * PIP_SIZE,
        stop_source=stop_source,
        take_source=take_source,
        fallback_used=stop_zone is None or take_zone is None,
    )
    return ProtectionPlan(
        protection=protection,
        stop_zone=stop_zone,
        take_zone=take_zone,
        stop_source=stop_source,
        take_source=take_source,
        stop_distance_pips=stop_distance_pips,
        take_distance_pips=take_distance_pips,
    )


def _change_counts(
    baseline: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    counterfactual: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> tuple[int, int, int]:
    improved = worsened = unchanged = 0
    for base, result in zip(baseline, counterfactual, strict=True):
        delta = result.final_profit - base.final_profit
        if delta > EPSILON:
            improved += 1
        elif delta < -EPSILON:
            worsened += 1
        else:
            unchanged += 1
    return improved, worsened, unchanged


def _run_variant(
    runtime: Any,
    baseline_summary: WorkspaceHistoricalReplaySummary,
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    observations: tuple[Any, ...],
    execution_events: tuple[WorkspaceMarketEvent, ...],
    execution_index: dict[datetime, int],
    records_by_uid: dict[str, WorkspaceSignalRecord],
    *,
    name: str,
) -> VariantResult:
    trades: list[WorkspaceHistoricalTradeDiagnostic] = []
    plans: dict[str, ProtectionPlan] = {}
    for trade in baseline_trades:
        record = records_by_uid[trade.signal_uid]
        signal_event = runtime.strategy_events[trade.signal_timestamp]
        plan = _build_plan(trade, observations, variant=name)
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
    improved, worsened, unchanged = _change_counts(baseline_trades, trade_tuple)
    return VariantResult(
        name=name,
        trades=trade_tuple,
        summary=_variant_summary(baseline_summary, trade_tuple),
        plans=plans,
        improved=improved,
        worsened=worsened,
        unchanged=unchanged,
    )


def _zone_inventory(result: VariantResult) -> str:
    stop_zones = sum(plan.stop_zone is not None for plan in result.plans.values())
    take_zones = sum(plan.take_zone is not None for plan in result.plans.values())
    return f"stop_zone:{stop_zones},take_zone:{take_zones}"


def _change_text(result: VariantResult) -> str:
    return (
        f"improved:{result.improved},worsened:{result.worsened},"
        f"unchanged:{result.unchanged}"
    )


def _zone_short(item: Any | None) -> str:
    return "NONE" if item is None else _zone_text(item)


def _write_csv(
    window_label: str,
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    variants: tuple[VariantResult, ...],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "window",
        "variant",
        "signal_utc",
        "direction",
        "entry_price",
        "baseline_reason",
        "baseline_pnl",
        "stop_source",
        "stop_distance_pips",
        "stop_zone",
        "take_source",
        "take_distance_pips",
        "take_zone",
        "result_reason",
        "result_pnl",
        "delta_pnl",
    )
    write_header = not OUTPUT_CSV.exists()
    with OUTPUT_CSV.open("a", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        if write_header:
            writer.writeheader()
        for result in variants:
            result_by_uid = {trade.signal_uid: trade for trade in result.trades}
            for baseline in baseline_trades:
                trade = result_by_uid[baseline.signal_uid]
                plan = result.plans[baseline.signal_uid]
                writer.writerow(
                    {
                        "window": window_label,
                        "variant": result.name,
                        "signal_utc": baseline.signal_timestamp.isoformat(),
                        "direction": baseline.direction,
                        "entry_price": f"{baseline.entry_price:.5f}",
                        "baseline_reason": baseline.close_reason,
                        "baseline_pnl": f"{baseline.final_profit:.4f}",
                        "stop_source": plan.stop_source,
                        "stop_distance_pips": f"{plan.stop_distance_pips:.2f}",
                        "stop_zone": _zone_short(plan.stop_zone),
                        "take_source": plan.take_source,
                        "take_distance_pips": f"{plan.take_distance_pips:.2f}",
                        "take_zone": _zone_short(plan.take_zone),
                        "result_reason": trade.close_reason,
                        "result_pnl": f"{trade.final_profit:.4f}",
                        "delta_pnl": (
                            f"{trade.final_profit - baseline.final_profit:+.4f}"
                        ),
                    }
                )


def _run_window(window: ReplayWindow) -> tuple[Any, tuple[VariantResult, ...]]:
    print(f"  running_period={window.label}", flush=True)
    runtime = StructuralSlTpRuntime(
        _workspace(window),
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

    baseline_summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert baseline_summary is not None
    assert execution is not None
    _assert_baseline(baseline_summary, window.expected_baseline)
    baseline_trades = tuple(execution.trade_diagnostics())
    assert len(baseline_trades) == window.expected_baseline[0]

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

    variants = tuple(
        _run_variant(
            runtime,
            baseline_summary,
            baseline_trades,
            observations,
            execution_events,
            execution_index,
            records_by_uid,
            name=name,
        )
        for name in VARIANTS
    )
    _write_csv(window.label, baseline_trades, variants)
    return baseline_summary, variants


def main() -> None:
    """Run agreed bounded structural SL/TP geometry on 2025 and 2026."""
    if OUTPUT_CSV.exists():
        OUTPUT_CSV.unlink()

    results: list[tuple[ReplayWindow, Any, tuple[VariantResult, ...]]] = []
    for window in WINDOWS:
        baseline_summary, variants = _run_window(window)
        results.append((window, baseline_summary, variants))

    for _, _, variants in results:
        fixed, zone_sl, final = variants
        assert fixed.name == VARIANT_FIXED
        assert zone_sl.name == VARIANT_ZONE_SL
        assert final.name == VARIANT_FINAL
        assert all(
            math.isclose(plan.stop_distance_pips, SL_FALLBACK_PIPS, abs_tol=EPSILON)
            for plan in fixed.plans.values()
        )
        assert all(
            math.isclose(
                plan.take_distance_pips,
                TP_FALLBACK_R * SL_FALLBACK_PIPS,
                abs_tol=EPSILON,
            )
            for plan in fixed.plans.values()
        )
        assert all(plan.take_zone is None for plan in zone_sl.plans.values())
        assert all(
            SL_FALLBACK_PIPS <= plan.stop_distance_pips <= SL_MAXIMUM_PIPS
            for plan in final.plans.values()
        )
        assert all(
            TP_MINIMUM_PIPS <= plan.take_distance_pips
            <= TP_FALLBACK_R * plan.stop_distance_pips + EPSILON
            for plan in final.plans.values()
        )

    print("Algorithm Workspace Candidate F Final Structural SL/TP result")
    print("  mode=RM103_8A_FINAL_STRUCTURAL_SL_TP_CROSS_PERIOD_DIAGNOSTIC_ONLY")
    print("  production_candidate_f_logic_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  paired_entries_fixed_to_production=True")
    print("  changed_capacity_does_not_create_or_block_entries=True")
    print("  future_price_used_to_define_levels=False")
    print("  sr_zone_lookback_bars=160")
    print("  sr_zone_half_width_pips=3.0")
    print("  sr_zone_minimum_pivots=2")
    print("  invalidated_zones_used=False")
    print(f"  structure_buffer_pips={STRUCTURE_BUFFER_PIPS:.1f}")
    print(f"  sl_fallback_pips={SL_FALLBACK_PIPS:.1f}")
    print(f"  sl_zone_window_pips={SL_FALLBACK_PIPS:.1f}-{SL_MAXIMUM_PIPS:.1f}")
    print("  sl_rule=NEAREST_VALID_ZONE_12_24_ELSE_FIXED_12")
    print(f"  tp_minimum_pips={TP_MINIMUM_PIPS:.1f}")
    print(f"  tp_fallback_r={TP_FALLBACK_R:.1f}")
    print("  tp_rule=NEAREST_VALID_ZONE_FROM_MAX_24_OR_1R_TO_2R_ELSE_2R")
    print("  tp_trailing=False")
    print("  broken_tp_zone_creates_automatic_reentry=False")
    print("  continuation_requires_new_signal=True")
    for window, baseline, variants in results:
        print(f"  {window.label}/BASELINE={_summary_text(baseline)}")
        for result in variants:
            print(
                f"  {window.label}/{result.name}="
                f"{_summary_text(result.summary)};"
                f"{_zone_inventory(result)};{_change_text(result)}"
            )
    print(f"  output_csv={OUTPUT_CSV}")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_FINAL_STRUCTURAL_SL_TP_CHECK=OK")


if __name__ == "__main__":
    main()
