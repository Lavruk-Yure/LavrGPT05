# -*- coding: utf-8 -*-
"""RoadMap103 / 7U.1: stable trade identity and capacity attribution 2025.

Runner не змінює production Candidate F 6K. Він повторює baseline Replay двічі,
доводить нестабільність runtime ``signal_uid`` між незалежними WSP та перевіряє
стабільний semantic identity за symbol/timeframe/signal timestamp/direction.

Потім для заморожених 7U thresholds 9/12/15 pip attribution виконується не за
runtime UID, а за semantic signal/trade keys. Це відокремлює прямий gate reject,
реальне displacement через capacity path та genuinely new entry.
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

_full_replay = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_entry_proximity_full_replay_2025_check"
)
_run_baseline = getattr(_full_replay, "_run_baseline")
_run_gated = getattr(_full_replay, "_run_gated")
_summary_performance = getattr(_full_replay, "_summary_performance")
_subset_performance = getattr(_full_replay, "_subset_performance")
THRESHOLDS_PIPS = tuple(_full_replay.THRESHOLDS_PIPS)
EPSILON = float(_full_replay.EPSILON)


@dataclass(frozen=True, slots=True)
class SignalSemanticKey:
    """Stable signal identity independent of workspace/runtime UID."""

    symbol: str
    timeframe: str
    signal_timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class TradeSemanticKey:
    """Stable executed-trade identity with deterministic entry timestamp."""

    signal: SignalSemanticKey
    entry_timestamp: datetime


@dataclass(frozen=True, slots=True)
class CapacityAttribution:
    """Semantic partition of one gated full Replay against baseline."""

    threshold_pips: float
    full_trades: tuple[Any, ...]
    gate_rejections: tuple[Any, ...]
    retained_keys: frozenset[SignalSemanticKey]
    direct_reject_keys: frozenset[SignalSemanticKey]
    displaced_keys: frozenset[SignalSemanticKey]
    new_keys: frozenset[SignalSemanticKey]
    nonbaseline_reject_keys: frozenset[SignalSemanticKey]
    retained_trade_key_matches: int
    retained_trade_key_changes: int
    new_entry_net: float
    broker_execution_attempted: bool


@dataclass(frozen=True, slots=True)
class BaselineDeterminism:
    """Independent baseline replay identity comparison."""

    uid_overlap: int
    semantic_signal_overlap: int
    semantic_trade_overlap: int
    economically_identical: int


def _context_symbol(runtime: Any) -> str:
    return str(runtime.context.symbol).strip().upper()


def _context_timeframe(runtime: Any) -> str:
    return str(runtime.context.timeframe).strip().upper()


def _signal_key(
    runtime: Any,
    *,
    timestamp: datetime,
    direction: str,
) -> SignalSemanticKey:
    return SignalSemanticKey(
        symbol=_context_symbol(runtime),
        timeframe=_context_timeframe(runtime),
        signal_timestamp=timestamp,
        direction=str(direction).strip().upper(),
    )


def _trade_signal_key(runtime: Any, trade: Any) -> SignalSemanticKey:
    return _signal_key(
        runtime,
        timestamp=trade.signal_timestamp,
        direction=trade.direction,
    )


def _trade_key(runtime: Any, trade: Any) -> TradeSemanticKey:
    return TradeSemanticKey(
        signal=_trade_signal_key(runtime, trade),
        entry_timestamp=trade.entry_timestamp,
    )


def _rejection_key(runtime: Any, rejection: Any) -> SignalSemanticKey:
    return _signal_key(
        runtime,
        timestamp=rejection.timestamp,
        direction=rejection.direction,
    )


def _unique_trade_map(runtime: Any, trades: tuple[Any, ...]) -> dict:
    result = {_trade_signal_key(runtime, trade): trade for trade in trades}
    assert len(result) == len(trades), "semantic signal key must be unique"
    return result


def _economically_same(left: Any, right: Any) -> bool:
    if _trade_key_fields(left) != _trade_key_fields(right):
        return False
    numeric_pairs = (
        (left.entry_price, right.entry_price),
        (left.close_price, right.close_price),
        (left.stop_loss_distance, right.stop_loss_distance),
        (left.take_profit_distance, right.take_profit_distance),
        (left.final_profit, right.final_profit),
    )
    return all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=EPSILON) for a, b in numeric_pairs
    )


def _trade_key_fields(trade: Any) -> tuple:
    return (
        trade.signal_timestamp,
        trade.entry_timestamp,
        trade.close_timestamp,
        trade.direction,
        trade.close_reason,
    )


def _baseline_determinism() -> tuple[Any, tuple[Any, ...], BaselineDeterminism]:
    runtime_a, trades_a = _run_baseline()
    runtime_b, trades_b = _run_baseline()
    assert len(trades_a) == len(trades_b) == 59
    assert _context_symbol(runtime_a) == _context_symbol(runtime_b)
    assert _context_timeframe(runtime_a) == _context_timeframe(runtime_b)

    uid_a = {trade.signal_uid for trade in trades_a}
    uid_b = {trade.signal_uid for trade in trades_b}
    signals_a = {_trade_signal_key(runtime_a, trade) for trade in trades_a}
    signals_b = {_trade_signal_key(runtime_b, trade) for trade in trades_b}
    trade_keys_a = {_trade_key(runtime_a, trade) for trade in trades_a}
    trade_keys_b = {_trade_key(runtime_b, trade) for trade in trades_b}

    map_a = _unique_trade_map(runtime_a, trades_a)
    map_b = _unique_trade_map(runtime_b, trades_b)
    common_signals = signals_a & signals_b
    economically_identical = sum(
        _economically_same(map_a[key], map_b[key]) for key in common_signals
    )

    result = BaselineDeterminism(
        uid_overlap=len(uid_a & uid_b),
        semantic_signal_overlap=len(common_signals),
        semantic_trade_overlap=len(trade_keys_a & trade_keys_b),
        economically_identical=economically_identical,
    )
    assert result.semantic_signal_overlap == 59
    assert result.semantic_trade_overlap == 59
    assert result.economically_identical == 59
    return runtime_a, trades_a, result


def _attribution(
    baseline_runtime: Any,
    baseline_trades: tuple[Any, ...],
    threshold_pips: float,
) -> CapacityAttribution:
    gated_runtime = _run_gated(threshold_pips)
    execution = gated_runtime.replay_execution
    assert execution is not None
    full_trades = tuple(execution.trade_diagnostics())
    gate_rejections = tuple(gated_runtime.gate_rejections)

    baseline_map = _unique_trade_map(baseline_runtime, baseline_trades)
    full_map = _unique_trade_map(gated_runtime, full_trades)
    baseline_keys = frozenset(baseline_map)
    full_keys = frozenset(full_map)

    rejection_keys = tuple(
        _rejection_key(gated_runtime, item) for item in gate_rejections
    )
    assert len(set(rejection_keys)) == len(
        rejection_keys
    ), "gate rejection semantic key must be unique"
    rejection_set = frozenset(rejection_keys)

    retained_keys = baseline_keys & full_keys
    direct_reject_keys = baseline_keys & rejection_set
    displaced_keys = baseline_keys - retained_keys - direct_reject_keys
    new_keys = full_keys - baseline_keys
    nonbaseline_reject_keys = rejection_set - baseline_keys

    assert not retained_keys & direct_reject_keys
    assert not retained_keys & displaced_keys
    assert not direct_reject_keys & displaced_keys
    assert len(baseline_keys) == (
        len(retained_keys) + len(direct_reject_keys) + len(displaced_keys)
    )
    assert len(full_keys) == len(retained_keys) + len(new_keys)

    retained_trade_key_matches = sum(
        _trade_key(baseline_runtime, baseline_map[key])
        == _trade_key(gated_runtime, full_map[key])
        for key in retained_keys
    )
    retained_trade_key_changes = len(retained_keys) - retained_trade_key_matches

    new_entries = tuple(full_map[key] for key in new_keys)
    new_performance = _subset_performance(new_entries)
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in gated_runtime.journal
        if isinstance(entry.details, dict)
    )

    return CapacityAttribution(
        threshold_pips=threshold_pips,
        full_trades=full_trades,
        gate_rejections=gate_rejections,
        retained_keys=frozenset(retained_keys),
        direct_reject_keys=frozenset(direct_reject_keys),
        displaced_keys=frozenset(displaced_keys),
        new_keys=frozenset(new_keys),
        nonbaseline_reject_keys=frozenset(nonbaseline_reject_keys),
        retained_trade_key_matches=retained_trade_key_matches,
        retained_trade_key_changes=retained_trade_key_changes,
        new_entry_net=new_performance.net,
        broker_execution_attempted=broker_execution_attempted,
    )


def _attribution_line(item: CapacityAttribution) -> str:
    threshold = f"{item.threshold_pips:g}"
    return (
        f"    ANY_LE_{threshold}P "
        f"retained:{len(item.retained_keys)} "
        f"directReject:{len(item.direct_reject_keys)} "
        f"displaced:{len(item.displaced_keys)} "
        f"new:{len(item.new_keys)} "
        f"nonbaselineGateReject:{len(item.nonbaseline_reject_keys)} "
        f"retainedTradeKeyMatch:{item.retained_trade_key_matches} "
        f"retainedTradeKeyChanged:{item.retained_trade_key_changes} "
        f"newEntryNet:{item.new_entry_net:+.2f}"
    )


def main() -> None:
    """Verify stable identity and correct full-Replay capacity attribution."""
    baseline_runtime, baseline_trades, determinism = _baseline_determinism()
    baseline_performance = _summary_performance(baseline_runtime)

    attributions = tuple(
        _attribution(baseline_runtime, baseline_trades, threshold)
        for threshold in THRESHOLDS_PIPS
    )
    assert len(attributions) == 3

    semantic_identity_stable_across_replays = bool(
        determinism.semantic_signal_overlap == 59
        and determinism.semantic_trade_overlap == 59
        and determinism.economically_identical == 59
    )
    runtime_uid_not_used_for_cross_replay_identity = True
    baseline_partition_invariant = all(
        len(baseline_trades)
        == len(item.retained_keys)
        + len(item.direct_reject_keys)
        + len(item.displaced_keys)
        for item in attributions
    )
    full_partition_invariant = all(
        len(item.full_trades) == len(item.retained_keys) + len(item.new_keys)
        for item in attributions
    )
    retained_trade_identity_stable = all(
        item.retained_trade_key_changes == 0 for item in attributions
    )

    assert semantic_identity_stable_across_replays
    assert baseline_partition_invariant
    assert full_partition_invariant
    assert retained_trade_identity_stable

    broker_execution_attempted = any(
        item.broker_execution_attempted for item in attributions
    )
    assert not broker_execution_attempted

    print(
        "Algorithm Workspace Candidate F S/R Entry Proximity Capacity "
        "Identity 2025 result"
    )
    print("  mode=PRODUCTION_6K_SR_ENTRY_PROXIMITY_CAPACITY_IDENTITY_INVARIANT_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  production_entry_gate_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  full_replay_capacity_attribution_only=True")
    print("  future_price_used=False")
    print("  semantic_signal_key=" "SYMBOL|TIMEFRAME|SIGNAL_TIMESTAMP|DIRECTION")
    print("  semantic_trade_key=" "SEMANTIC_SIGNAL_KEY|ENTRY_TIMESTAMP")
    print(
        "  baseline="
        f"trades:{baseline_performance.trades},"
        f"wins:{baseline_performance.wins},"
        f"losses:{baseline_performance.losses},"
        f"break_even:{baseline_performance.break_even},"
        f"net:{baseline_performance.net:+.2f}"
    )
    print("  independent_baseline_replay_identity:")
    print(f"    runtime_uid_overlap={determinism.uid_overlap}/59")
    print("    semantic_signal_overlap=" f"{determinism.semantic_signal_overlap}/59")
    print("    semantic_trade_overlap=" f"{determinism.semantic_trade_overlap}/59")
    print("    economically_identical=" f"{determinism.economically_identical}/59")
    print("  semantic_capacity_attribution:")
    for item in attributions:
        print(_attribution_line(item))

    print(
        "  semantic_identity_stable_across_replays="
        f"{semantic_identity_stable_across_replays}"
    )
    print(
        "  runtime_uid_not_used_for_cross_replay_identity="
        f"{runtime_uid_not_used_for_cross_replay_identity}"
    )
    print("  baseline_partition_invariant=" f"{baseline_partition_invariant}")
    print(f"  full_partition_invariant={full_partition_invariant}")
    print("  retained_trade_identity_stable=" f"{retained_trade_identity_stable}")
    print("  completed_bars_only=True")
    print("  causal_survival_role_zones_only=True")
    print("  entry_gate_applied_to_production=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ENTRY_PROXIMITY_"
        "CAPACITY_IDENTITY_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
