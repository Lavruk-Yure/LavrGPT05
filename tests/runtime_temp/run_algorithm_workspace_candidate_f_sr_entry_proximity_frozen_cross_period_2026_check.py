# -*- coding: utf-8 -*-
"""RoadMap103 / 7V: frozen S/R entry-proximity cross-period check 2026.

Runner не змінює production Candidate F 6K. Повністю заморожена після 7U.1
модель S/R proximity перевіряється на трьох уже відомих EURUSD M15 вікнах
2026: Development, Validation і Holdout. Пороги 9/12/15 pip, lookback 160,
zone half-width +/-3 pip, minimum pivots 2, survival/role semantics та causal
reference price COMPLETED_SIGNAL_BAR_CLOSE не підбираються на 2026.

Це robustness/cross-period check нового gate, а не blind OOS для Candidate F:
ці 2026 windows вже використовувалися раніше під час розробки алгоритму.
"""

from __future__ import annotations

import importlib
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

_cross_period = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sl_regime_age_cross_period_check"
)
HISTORY_2026 = _cross_period.HISTORY_2026
WINDOWS_2026 = tuple(_cross_period.WINDOWS_2026)
EXPECTED_BASELINES = dict(_cross_period.EXPECTED_BASELINES)
_workspace_2026 = getattr(_cross_period, "_workspace_2026")

_full_replay = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_entry_proximity_full_replay_2025_check"
)
EntryExitContextRuntime = _full_replay.EntryExitContextRuntime
SrEntryProximityGateRuntime = _full_replay.SrEntryProximityGateRuntime
SubsetPerformance = _full_replay.SubsetPerformance
_summary_performance = getattr(_full_replay, "_summary_performance")
_subset_performance = getattr(_full_replay, "_subset_performance")
THRESHOLDS_PIPS = tuple(_full_replay.THRESHOLDS_PIPS)
EPSILON = float(_full_replay.EPSILON)

_survival = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)
FOCUS_LOOKBACK_BARS = int(_survival.FOCUS_LOOKBACK_BARS)
FOCUS_ZONE_HALF_WIDTH_PIPS = float(_survival.FOCUS_ZONE_HALF_WIDTH_PIPS)
MINIMUM_PIVOTS = int(_survival.MINIMUM_PIVOTS)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

EURUSD_PIP_SIZE = 0.0001


@dataclass(frozen=True, slots=True)
class SignalKey:
    """Stable semantic signal identity across independent Replay runs."""

    symbol: str
    timeframe: str
    timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class WindowVariant:
    """One frozen threshold result inside one 2026 window."""

    threshold_pips: float
    performance: SubsetPerformance
    gate_rejections: int
    baseline_rejected: SubsetPerformance
    retained: int
    direct_rejected: int
    displaced: int
    new_entries: int
    new_entry_performance: SubsetPerformance
    nonbaseline_gate_rejections: int
    baseline_reject_keys: frozenset[SignalKey]
    all_reject_keys: frozenset[SignalKey]


@dataclass(frozen=True, slots=True)
class WindowResult:
    """Baseline plus 9/12/15 pip variants for one frozen window."""

    name: str
    baseline: SubsetPerformance
    variants: tuple[WindowVariant, ...]


def _context_symbol(runtime: Any) -> str:
    return str(runtime.context.symbol).strip().upper()


def _context_timeframe(runtime: Any) -> str:
    return str(runtime.context.timeframe).strip().upper()


def _signal_key(
    runtime: Any,
    *,
    timestamp: datetime,
    direction: str,
) -> SignalKey:
    return SignalKey(
        symbol=_context_symbol(runtime),
        timeframe=_context_timeframe(runtime),
        timestamp=timestamp,
        direction=str(direction).strip().upper(),
    )


def _trade_key(runtime: Any, trade: Any) -> SignalKey:
    return _signal_key(
        runtime,
        timestamp=trade.signal_timestamp,
        direction=trade.direction,
    )


def _rejection_key(runtime: Any, rejection: Any) -> SignalKey:
    return _signal_key(
        runtime,
        timestamp=rejection.timestamp,
        direction=rejection.direction,
    )


def _run_runtime(
    start_utc: str,
    end_utc: str,
    threshold_pips: float | None,
) -> Any:
    workspace = _workspace_2026(start_utc, end_utc)
    if threshold_pips is None:
        runtime = EntryExitContextRuntime(
            workspace,
            algorithm_factory=create_registered_workspace_algorithm,
        )
    else:
        runtime = SrEntryProximityGateRuntime(
            workspace,
            algorithm_factory=create_registered_workspace_algorithm,
            threshold_pips=threshold_pips,
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
    return runtime


def _trades(runtime: Any) -> tuple[Any, ...]:
    execution = runtime.replay_execution
    assert execution is not None
    return tuple(execution.trade_diagnostics())


def _unique_trade_map(runtime: Any, trades: tuple[Any, ...]) -> dict:
    result = {_trade_key(runtime, trade): trade for trade in trades}
    assert len(result) == len(trades), "semantic signal key must be unique"
    return result


def _assert_expected_baseline(name: str, performance: SubsetPerformance) -> None:
    expected = EXPECTED_BASELINES[name]
    (
        trades,
        wins,
        losses,
        break_even,
        _stop_losses,
        net,
        profit_factor,
        maximum_drawdown,
    ) = expected
    assert performance.trades == trades
    assert performance.wins == wins
    assert performance.losses == losses
    assert performance.break_even == break_even
    assert math.isclose(performance.net, float(net), abs_tol=0.005)
    assert math.isclose(
        performance.profit_factor,
        float(profit_factor),
        abs_tol=0.00005,
    )
    assert math.isclose(
        performance.maximum_drawdown,
        float(maximum_drawdown),
        abs_tol=0.005,
    )


def _variant(
    baseline_runtime: Any,
    baseline_trades: tuple[Any, ...],
    *,
    start_utc: str,
    end_utc: str,
    threshold_pips: float,
) -> WindowVariant:
    gated_runtime = _run_runtime(start_utc, end_utc, threshold_pips)
    gated_trades = _trades(gated_runtime)
    performance = _summary_performance(gated_runtime)
    assert performance.trades == len(gated_trades)

    baseline_map = _unique_trade_map(baseline_runtime, baseline_trades)
    gated_map = _unique_trade_map(gated_runtime, gated_trades)
    baseline_keys = frozenset(baseline_map)
    gated_keys = frozenset(gated_map)

    rejection_keys = tuple(
        _rejection_key(gated_runtime, rejection)
        for rejection in gated_runtime.gate_rejections
    )
    assert len(rejection_keys) == len(set(rejection_keys))
    rejection_set = frozenset(rejection_keys)

    retained_keys = baseline_keys & gated_keys
    direct_reject_keys = baseline_keys & rejection_set
    displaced_keys = baseline_keys - retained_keys - direct_reject_keys
    new_keys = gated_keys - baseline_keys
    nonbaseline_reject_keys = rejection_set - baseline_keys

    assert not retained_keys & direct_reject_keys
    assert not retained_keys & displaced_keys
    assert not direct_reject_keys & displaced_keys
    assert len(baseline_keys) == (
        len(retained_keys) + len(direct_reject_keys) + len(displaced_keys)
    )
    assert len(gated_keys) == len(retained_keys) + len(new_keys)

    baseline_rejected_trades = tuple(baseline_map[key] for key in direct_reject_keys)
    new_trades = tuple(gated_map[key] for key in new_keys)

    return WindowVariant(
        threshold_pips=threshold_pips,
        performance=performance,
        gate_rejections=len(rejection_set),
        baseline_rejected=_subset_performance(baseline_rejected_trades),
        retained=len(retained_keys),
        direct_rejected=len(direct_reject_keys),
        displaced=len(displaced_keys),
        new_entries=len(new_keys),
        new_entry_performance=_subset_performance(new_trades),
        nonbaseline_gate_rejections=len(nonbaseline_reject_keys),
        baseline_reject_keys=frozenset(direct_reject_keys),
        all_reject_keys=frozenset(rejection_set),
    )


def _window(name: str, start_utc: str, end_utc: str) -> WindowResult:
    baseline_runtime = _run_runtime(start_utc, end_utc, None)
    baseline_trades = _trades(baseline_runtime)
    baseline = _summary_performance(baseline_runtime)
    assert baseline.trades == len(baseline_trades)
    _assert_expected_baseline(name, baseline)

    variants = tuple(
        _variant(
            baseline_runtime,
            baseline_trades,
            start_utc=start_utc,
            end_utc=end_utc,
            threshold_pips=threshold,
        )
        for threshold in THRESHOLDS_PIPS
    )
    return WindowResult(name=name, baseline=baseline, variants=variants)


def _pf_text(value: float) -> str:
    return "INF" if math.isinf(value) else f"{value:.4f}"


def _performance_text(item: SubsetPerformance) -> str:
    return (
        f"trades:{item.trades},wins:{item.wins},losses:{item.losses},"
        f"break_even:{item.break_even},net:{item.net:+.2f},"
        f"pf:{_pf_text(item.profit_factor)},dd:{item.maximum_drawdown:.2f}"
    )


def _capture_text(rejected: int, total: int) -> str:
    if total <= 0:
        return "0.000"
    return f"{rejected / total:.3f}"


def _variant_line(baseline: SubsetPerformance, item: WindowVariant) -> str:
    rejected = item.baseline_rejected
    threshold = f"{item.threshold_pips:g}"
    return (
        f"      ANY_LE_{threshold}P {_performance_text(item.performance)} "
        f"| deltaNet:{item.performance.net - baseline.net:+.2f} "
        f"gateReject:{item.gate_rejections} "
        f"baselineRejected:{item.direct_rejected} "
        f"rejW/L/BE:{rejected.wins}/{rejected.losses}/{rejected.break_even} "
        f"rejNet:{rejected.net:+.2f} "
        f"lossCapture:{_capture_text(rejected.losses, baseline.losses)} "
        f"winCapture:{_capture_text(rejected.wins, baseline.wins)} "
        f"retained:{item.retained} displaced:{item.displaced} "
        f"new:{item.new_entries} newNet:{item.new_entry_performance.net:+.2f}"
    )


def _variant_map(window: WindowResult) -> dict[float, WindowVariant]:
    return {item.threshold_pips: item for item in window.variants}


def _decision_difference(
    left: WindowVariant,
    right: WindowVariant,
) -> tuple[int, int]:
    baseline_diff = len(left.baseline_reject_keys ^ right.baseline_reject_keys)
    all_diff = len(left.all_reject_keys ^ right.all_reject_keys)
    return baseline_diff, all_diff


def _pooled_trades(
    windows: tuple[WindowResult, ...],
    threshold_pips: float | None,
) -> tuple[int, int, int, int, float]:
    trades = wins = losses = break_even = 0
    net = 0.0
    for window in windows:
        if threshold_pips is None:
            performance = window.baseline
        else:
            performance = _variant_map(window)[threshold_pips].performance
        trades += performance.trades
        wins += performance.wins
        losses += performance.losses
        break_even += performance.break_even
        net += performance.net
    return trades, wins, losses, break_even, net


def _pooled_line(
    windows: tuple[WindowResult, ...],
    threshold_pips: float | None,
) -> str:
    trades, wins, losses, break_even, net = _pooled_trades(
        windows,
        threshold_pips,
    )
    label = "BASELINE" if threshold_pips is None else f"ANY_LE_{threshold_pips:g}P"
    return (
        f"    {label} trades:{trades},wins:{wins},losses:{losses},"
        f"break_even:{break_even},net:{net:+.2f}"
    )


def main() -> None:
    """Run frozen 9/12/15 pip gate across three known 2026 windows."""
    assert HISTORY_2026.is_file(), HISTORY_2026
    assert THRESHOLDS_PIPS == (9.0, 12.0, 15.0)
    assert FOCUS_LOOKBACK_BARS == 160
    assert math.isclose(FOCUS_ZONE_HALF_WIDTH_PIPS, 3.0)
    assert MINIMUM_PIVOTS == 2

    windows = tuple(_window(*window) for window in WINDOWS_2026)
    assert len(windows) == 3

    broker_execution_attempted = False
    for window in windows:
        assert len(window.variants) == 3
        for item in window.variants:
            assert item.performance.trades == item.retained + item.new_entries
            assert window.baseline.trades == (
                item.retained + item.direct_rejected + item.displaced
            )

    print(
        "Algorithm Workspace Candidate F S/R Entry Proximity Frozen "
        "Cross-Period 2026 result"
    )
    print("  mode=PRODUCTION_6K_SR_ENTRY_PROXIMITY_FROZEN_CROSS_PERIOD_TEST_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  production_entry_gate_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  thresholds_frozen_from_2025=9|12|15")
    print("  threshold_search_on_2026=False")
    print("  symbol=EURUSD")
    print("  pip_size=0.0001")
    print("  timeframe=M15")
    print("  source_timeframe=M1")
    print("  zone_lookback_bars=160")
    print("  zone_half_width_pips=3.0")
    print("  minimum_pivots=2")
    print("  survival_role_semantics_frozen=True")
    print("  gate_scope=ANY_VALID_SURVIVAL_ROLE_AWARE_ZONE")
    print("  causal_gate_reference_price=COMPLETED_SIGNAL_BAR_CLOSE")
    print("  future_price_used_as_gate=False")
    print("  known_2026_windows_not_blind_candidate_f_oos=True")
    print("  windows:")

    for window in windows:
        print(f"    {window.name} baseline:{_performance_text(window.baseline)}")
        for item in window.variants:
            print(_variant_line(window.baseline, item))

        variants = _variant_map(window)
        diff_9_12 = _decision_difference(variants[9.0], variants[12.0])
        diff_12_15 = _decision_difference(variants[12.0], variants[15.0])
        print(
            "      decision_disagreement "
            f"9_vs_12:baseline:{diff_9_12[0]},allGate:{diff_9_12[1]} "
            f"12_vs_15:baseline:{diff_12_15[0]},allGate:{diff_12_15[1]}"
        )

    print("  pooled_independent_windows_counts_and_net:")
    print(_pooled_line(windows, None))
    for threshold in THRESHOLDS_PIPS:
        print(_pooled_line(windows, threshold))

    print("  thresholds_frozen_without_2026_tuning=True")
    print("  zone_model_frozen_from_2025=True")
    print("  signal_close_reference_frozen=True")
    print("  semantic_capacity_attribution=True")
    print("  entry_gate_applied_to_production=False")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ENTRY_PROXIMITY_"
        "FROZEN_CROSS_PERIOD_2026_CHECK=OK"
    )


if __name__ == "__main__":
    main()
