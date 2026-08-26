# -*- coding: utf-8 -*-
"""RoadMap103 / 7S: Lifecycle x S/R Entry Context Matrix 2025.

Diagnostic-only runner повторює production Candidate F після 6K без змін і
для тих самих 59 baseline entries поєднує causal lifecycle features з 7L та
survival/role-aware horizontal S/R zones з 7Q.

Мета 7S — перевірити, чи структурний контекст входу концентрує збиткові
угоди краще разом із lifecycle, ніж кожна ознака окремо. Жоден знайдений
поріг не є entry gate: production logic/profile/SL/TP/exit не змінюються.
Retrospective macro position з 7K/7L у матрицях 7S не використовується.
"""

from __future__ import annotations

import csv
import importlib
import math
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

_frozen = importlib.import_module(
    "run_algorithm_workspace_candidate_f_frozen_oos_2025_check"
)
assert_frozen_oos_snapshot = _frozen.assert_frozen_oos_snapshot
frozen_oos_workspace = _frozen.frozen_oos_workspace

_lifecycle = importlib.import_module(
    "run_algorithm_workspace_candidate_f_trend_lifecycle_entry_quality_2025_check"
)
EntryExitContextRuntime = _lifecycle.EntryExitContextRuntime
MANUAL_CASE_LABELS = _lifecycle.MANUAL_CASE_LABELS
_build_evidence = getattr(_lifecycle, "_build_evidence")
_build_lifecycle_evidence = getattr(_lifecycle, "_build_lifecycle_evidence")
_split_active_runs = getattr(_lifecycle, "_split_active_runs")
_split_macro_trends = getattr(_lifecycle, "_split_macro_trends")
_assert_baseline = getattr(_lifecycle, "_assert_baseline")

_survival = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)
_all_observations = getattr(_survival, "_all_observations")
_nearest = getattr(_survival, "_nearest")

_structural = importlib.import_module(
    "run_algorithm_workspace_candidate_f_structural_sl_tp_2025_check"
)
FOCUS_CASES = _structural.FOCUS_CASES

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

EPSILON = 1e-12
MIN_TAKE_DISTANCE_PIPS = 24.0

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7S_Lifecycle_SR_Entry_Context_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_lifecycle_sr_entry_context_2025.csv"

LIFECYCLE_BUCKETS = (
    "TRANSITION",
    "LOW_CONTINUITY",
    "LATE_DECAY",
    "LATE_ACTIVE",
    "CONTINUATION",
)
STOP_BINS = ("NONE", "<12", "12-18", "18-24", "24-36", "36-48", ">48")
TAKE_BINS = ("NONE", "24-36", "36-48", "48-72", ">72")


@dataclass(frozen=True, slots=True)
class EntryContext:
    """Один baseline entry з causal lifecycle та S/R context."""

    lifecycle: Any
    lifecycle_bucket: str
    stop_zone: Any | None
    take_zone: Any | None
    stop_distance_bin: str
    take_room_bin: str
    entry_inside_valid_zone: bool
    entry_within_6p_of_valid_zone: bool
    entry_within_12p_of_valid_zone: bool

    @property
    def trade(self) -> Any:
        return self.lifecycle.base.trade

    @property
    def pnl(self) -> float:
        return float(self.trade.final_profit)

    @property
    def outcome3(self) -> str:
        if self.pnl > EPSILON:
            return "WIN"
        if self.pnl < -EPSILON:
            return "LOSS"
        return "BREAK_EVEN"


@dataclass(frozen=True, slots=True)
class GroupStats:
    """Performance descriptive statistics для одного diagnostic slice."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float
    loss_rate: float
    win_rate: float
    loss_capture: float
    win_capture: float


def _lifecycle_bucket(item: Any) -> str:
    """Transparent descriptive bucket; не production gate і не score."""
    transition = (
        item.regime_changes_8 >= 2
        or item.bars_since_flat_40 <= 2
        or item.bars_since_opposite_40 <= 2
    )
    if transition:
        return "TRANSITION"
    if item.ordering_stability_5 < 0.60 or item.efficiency_5 <= 0.0:
        return "LOW_CONTINUITY"
    late = item.same_regime_age >= 8
    decay = (
        item.efficiency_5 < 0.25
        and item.macd_recovery_from_extreme_20 >= 0.50
    )
    if late and decay:
        return "LATE_DECAY"
    if late:
        return "LATE_ACTIVE"
    return "CONTINUATION"


def _take_room_bin(item: Any | None) -> str:
    if item is None or item.distance_pips is None:
        return "NONE"
    distance = float(item.distance_pips)
    assert distance >= MIN_TAKE_DISTANCE_PIPS
    if distance < 36.0:
        return "24-36"
    if distance < 48.0:
        return "36-48"
    if distance < 72.0:
        return "48-72"
    return ">72"


def _edge_distance_pips(entry_price: float, zone: Any) -> float:
    if zone.low <= entry_price <= zone.high:
        return 0.0
    return min(abs(entry_price - zone.low), abs(entry_price - zone.high)) / 0.0001


def _entry_zone_proximity(
    trade: Any,
    observations: tuple[Any, ...],
) -> tuple[bool, bool, bool]:
    distances = tuple(
        _edge_distance_pips(trade.entry_price, item.zone)
        for item in observations
        if item.signal_timestamp == trade.signal_timestamp
        and item.effective_role != "INVALIDATED"
    )
    if not distances:
        return False, False, False
    minimum = min(distances)
    return minimum <= EPSILON, minimum <= 6.0, minimum <= 12.0


def _build_contexts(runtime: Any) -> tuple[EntryContext, ...]:
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None

    alligator_observations = tuple(signal_filter.observations)
    active_runs = _split_active_runs(alligator_observations)
    macros = _split_macro_trends(alligator_observations, active_runs)
    base_rows = _build_evidence(runtime, macros)
    lifecycle_rows = _build_lifecycle_evidence(runtime, base_rows)

    trades = tuple(item.base.trade for item in lifecycle_rows)
    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    zone_observations = _all_observations(trades, events, event_index)

    contexts: list[EntryContext] = []
    for item in lifecycle_rows:
        trade = item.base.trade
        stop = _nearest(
            zone_observations,
            timestamp=trade.signal_timestamp,
            role="STOP",
        )
        take = _nearest(
            zone_observations,
            timestamp=trade.signal_timestamp,
            role="TAKE",
            minimum_distance_pips=MIN_TAKE_DISTANCE_PIPS,
        )
        inside, within6, within12 = _entry_zone_proximity(
            trade,
            zone_observations,
        )
        contexts.append(
            EntryContext(
                lifecycle=item,
                lifecycle_bucket=_lifecycle_bucket(item),
                stop_zone=stop,
                take_zone=take,
                stop_distance_bin="NONE" if stop is None else stop.distance_bin,
                take_room_bin=_take_room_bin(take),
                entry_inside_valid_zone=inside,
                entry_within_6p_of_valid_zone=within6,
                entry_within_12p_of_valid_zone=within12,
            )
        )
    return tuple(contexts)


def _profit_factor(items: tuple[EntryContext, ...]) -> float:
    gross_profit = sum(max(item.pnl, 0.0) for item in items)
    gross_loss = abs(sum(min(item.pnl, 0.0) for item in items))
    if gross_loss <= EPSILON:
        return math.inf if gross_profit > EPSILON else 0.0
    return gross_profit / gross_loss


def _stats(
    items: tuple[EntryContext, ...],
    *,
    total_losses: int,
    total_wins: int,
) -> GroupStats:
    wins = sum(item.outcome3 == "WIN" for item in items)
    losses = sum(item.outcome3 == "LOSS" for item in items)
    break_even = sum(item.outcome3 == "BREAK_EVEN" for item in items)
    count = len(items)
    return GroupStats(
        trades=count,
        wins=wins,
        losses=losses,
        break_even=break_even,
        net=sum(item.pnl for item in items),
        profit_factor=_profit_factor(items),
        loss_rate=(losses / count) if count else 0.0,
        win_rate=(wins / count) if count else 0.0,
        loss_capture=(losses / total_losses) if total_losses else 0.0,
        win_capture=(wins / total_wins) if total_wins else 0.0,
    )


def _stats_text(stats: GroupStats) -> str:
    pf = "INF" if math.isinf(stats.profit_factor) else f"{stats.profit_factor:.4f}"
    return (
        f"n:{stats.trades},W:{stats.wins},L:{stats.losses},BE:{stats.break_even},"
        f"net:{stats.net:+.2f},pf:{pf},"
        f"lossRate:{stats.loss_rate:.3f},winRate:{stats.win_rate:.3f},"
        f"lossCapture:{stats.loss_capture:.3f},winCapture:{stats.win_capture:.3f}"
    )


def _slice_line(
    name: str,
    items: tuple[EntryContext, ...],
    *,
    total_losses: int,
    total_wins: int,
) -> str:
    stats = _stats(
        items,
        total_losses=total_losses,
        total_wins=total_wins,
    )
    return f"    {name}={_stats_text(stats)}"


def _filter(
    contexts: tuple[EntryContext, ...],
    predicate: Callable[[EntryContext], bool],
) -> tuple[EntryContext, ...]:
    return tuple(item for item in contexts if predicate(item))


def _manual_label(timestamp: datetime) -> str:
    if timestamp in MANUAL_CASE_LABELS:
        return MANUAL_CASE_LABELS[timestamp]
    return "UNLABELED_REFERENCE"


def _zone_brief(item: Any | None) -> str:
    if item is None:
        return "NONE"
    distance = "NONE" if item.distance_pips is None else f"{item.distance_pips:.1f}p"
    return f"{distance}/{item.effective_role}/{item.survival_state}"


def _focus_line(index: int, item: EntryContext) -> str:
    lifecycle = item.lifecycle
    trade = item.trade
    return (
        f"    {index:02d}. {trade.signal_timestamp.isoformat()} {trade.direction} "
        f"{item.outcome3}/{trade.final_profit:+.2f} "
        f"manual:{_manual_label(trade.signal_timestamp)} "
        f"life:{item.lifecycle_bucket} "
        f"age:{lifecycle.same_regime_age} eff5:{lifecycle.efficiency_5:+.2f} "
        f"ord5:{lifecycle.ordering_stability_5:.2f} "
        f"chg8:{lifecycle.regime_changes_8} "
        f"macdRec:{lifecycle.macd_recovery_from_extreme_20:.2f} "
        f"STOP:{_zone_brief(item.stop_zone)} "
        f"TAKE24:{_zone_brief(item.take_zone)} "
        f"inside:{item.entry_inside_valid_zone} "
        f"near6:{item.entry_within_6p_of_valid_zone} "
        f"near12:{item.entry_within_12p_of_valid_zone}"
    )


def _write_csv(contexts: tuple[EntryContext, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_utc",
        "direction",
        "outcome",
        "final_profit",
        "manual_label",
        "lifecycle_bucket_diagnostic",
        "same_regime_age_causal",
        "efficiency_5_causal",
        "ordering_stability_5_causal",
        "regime_changes_8_causal",
        "bars_since_flat_40_causal",
        "bars_since_opposite_40_causal",
        "macd_recovery_from_extreme_20_causal",
        "stop_distance_bin",
        "stop_distance_pips",
        "stop_role",
        "stop_survival_state",
        "take_room_bin",
        "take_distance_pips",
        "take_role",
        "take_survival_state",
        "entry_inside_valid_zone",
        "entry_within_6p_of_valid_zone",
        "entry_within_12p_of_valid_zone",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for item in contexts:
            lifecycle = item.lifecycle
            trade = item.trade
            stop = item.stop_zone
            take = item.take_zone
            writer.writerow(
                {
                    "signal_utc": trade.signal_timestamp.isoformat(),
                    "direction": trade.direction,
                    "outcome": item.outcome3,
                    "final_profit": f"{trade.final_profit:.4f}",
                    "manual_label": _manual_label(trade.signal_timestamp),
                    "lifecycle_bucket_diagnostic": item.lifecycle_bucket,
                    "same_regime_age_causal": lifecycle.same_regime_age,
                    "efficiency_5_causal": f"{lifecycle.efficiency_5:.6f}",
                    "ordering_stability_5_causal": (
                        f"{lifecycle.ordering_stability_5:.6f}"
                    ),
                    "regime_changes_8_causal": lifecycle.regime_changes_8,
                    "bars_since_flat_40_causal": lifecycle.bars_since_flat_40,
                    "bars_since_opposite_40_causal": (
                        lifecycle.bars_since_opposite_40
                    ),
                    "macd_recovery_from_extreme_20_causal": (
                        f"{lifecycle.macd_recovery_from_extreme_20:.6f}"
                    ),
                    "stop_distance_bin": item.stop_distance_bin,
                    "stop_distance_pips": (
                        ""
                        if stop is None or stop.distance_pips is None
                        else f"{stop.distance_pips:.6f}"
                    ),
                    "stop_role": "" if stop is None else stop.effective_role,
                    "stop_survival_state": (
                        "" if stop is None else stop.survival_state
                    ),
                    "take_room_bin": item.take_room_bin,
                    "take_distance_pips": (
                        ""
                        if take is None or take.distance_pips is None
                        else f"{take.distance_pips:.6f}"
                    ),
                    "take_role": "" if take is None else take.effective_role,
                    "take_survival_state": (
                        "" if take is None else take.survival_state
                    ),
                    "entry_inside_valid_zone": item.entry_inside_valid_zone,
                    "entry_within_6p_of_valid_zone": (
                        item.entry_within_6p_of_valid_zone
                    ),
                    "entry_within_12p_of_valid_zone": (
                        item.entry_within_12p_of_valid_zone
                    ),
                }
            )
    return OUTPUT_CSV


def main() -> None:
    """Run production 6K Replay and print 7S entry-context matrices."""
    assert_frozen_oos_snapshot()
    runtime = EntryExitContextRuntime(
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
    contexts = _build_contexts(runtime)
    assert len(contexts) == 59
    assert len({item.trade.signal_uid for item in contexts}) == 59
    assert all(item.lifecycle.base.signal_record.accepted for item in contexts)
    assert all(
        item.lifecycle.base.observation.available_at <= item.trade.signal_timestamp
        for item in contexts
    )

    total_wins = sum(item.outcome3 == "WIN" for item in contexts)
    total_losses = sum(item.outcome3 == "LOSS" for item in contexts)
    total_break_even = sum(item.outcome3 == "BREAK_EVEN" for item in contexts)
    assert (total_wins, total_losses, total_break_even) == (40, 18, 1)

    summary = runtime.historical_summary
    assert summary is not None
    output_csv = _write_csv(contexts)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    bucket_counts = Counter(item.lifecycle_bucket for item in contexts)
    stop_counts = Counter(item.stop_distance_bin for item in contexts)
    take_counts = Counter(item.take_room_bin for item in contexts)

    print("Algorithm Workspace Candidate F Lifecycle x S/R Entry Context 2025 result")
    print("  mode=PRODUCTION_6K_LIFECYCLE_X_SR_ENTRY_CONTEXT_MATRIX_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_gate_applied=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  execution_counterfactual_run=False")
    print("  future_price_used_as_entry_feature=False")
    print("  retrospective_macro_position_used_in_matrix=False")
    print("  single_quality_score_used=False")
    print(
        "  lifecycle_bucket_rule="
        "TRANSITION_if_regimeChanges8>=2_or_sinceFlat<=2_or_sinceOpp<=2;"
        "LOW_CONTINUITY_if_order5<0.60_or_eff5<=0;"
        "LATE_DECAY_if_age>=8_and_eff5<0.25_and_macdRecovery>=0.50;"
        "LATE_ACTIVE_if_age>=8;else_CONTINUATION"
    )
    print("  minimum_take_room_pips=24.0")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(
        "  lifecycle_bucket_inventory="
        + ",".join(f"{key}:{bucket_counts[key]}" for key in LIFECYCLE_BUCKETS)
    )
    print(
        "  stop_distance_inventory="
        + ",".join(f"{key}:{stop_counts[key]}" for key in STOP_BINS)
    )
    print(
        "  take_room_inventory="
        + ",".join(f"{key}:{take_counts[key]}" for key in TAKE_BINS)
    )

    print("  lifecycle_bucket_performance:")
    for bucket in LIFECYCLE_BUCKETS:
        items = _filter(
            contexts,
            lambda row, value=bucket: row.lifecycle_bucket == value,
        )
        if items:
            print(
                _slice_line(
                    bucket,
                    items,
                    total_losses=total_losses,
                    total_wins=total_wins,
                )
            )

    print("  stop_distance_performance:")
    for distance_bin in STOP_BINS:
        items = _filter(
            contexts,
            lambda row, value=distance_bin: row.stop_distance_bin == value,
        )
        if items:
            print(
                _slice_line(
                    distance_bin,
                    items,
                    total_losses=total_losses,
                    total_wins=total_wins,
                )
            )

    print("  take_room_performance:")
    for room_bin in TAKE_BINS:
        items = _filter(
            contexts,
            lambda row, value=room_bin: row.take_room_bin == value,
        )
        if items:
            print(
                _slice_line(
                    room_bin,
                    items,
                    total_losses=total_losses,
                    total_wins=total_wins,
                )
            )

    print("  lifecycle_x_stop_matrix_nonempty:")
    for bucket in LIFECYCLE_BUCKETS:
        for distance_bin in STOP_BINS:
            items = _filter(
                contexts,
                lambda row, b=bucket, d=distance_bin: (
                    row.lifecycle_bucket == b and row.stop_distance_bin == d
                ),
            )
            if items:
                print(
                    _slice_line(
                        f"{bucket}|STOP:{distance_bin}",
                        items,
                        total_losses=total_losses,
                        total_wins=total_wins,
                    )
                )

    print("  lifecycle_x_take_matrix_nonempty:")
    for bucket in LIFECYCLE_BUCKETS:
        for room_bin in TAKE_BINS:
            items = _filter(
                contexts,
                lambda row, b=bucket, r=room_bin: (
                    row.lifecycle_bucket == b and row.take_room_bin == r
                ),
            )
            if items:
                print(
                    _slice_line(
                        f"{bucket}|TAKE:{room_bin}",
                        items,
                        total_losses=total_losses,
                        total_wins=total_wins,
                    )
                )

    combined_slices = (
        (
            "STOP_LT12",
            lambda row: row.stop_distance_bin == "<12",
        ),
        (
            "STOP_LT12_AND_TRANSITION",
            lambda row: (
                row.stop_distance_bin == "<12"
                and row.lifecycle_bucket == "TRANSITION"
            ),
        ),
        (
            "STOP_LT12_AND_LOW_CONTINUITY",
            lambda row: (
                row.stop_distance_bin == "<12"
                and row.lifecycle_bucket == "LOW_CONTINUITY"
            ),
        ),
        (
            "STOP_LT12_AND_LATE",
            lambda row: (
                row.stop_distance_bin == "<12"
                and row.lifecycle_bucket in {"LATE_DECAY", "LATE_ACTIVE"}
            ),
        ),
        (
            "STOP_12_36_AND_CONTINUATION",
            lambda row: (
                row.stop_distance_bin in {"12-18", "18-24", "24-36"}
                and row.lifecycle_bucket == "CONTINUATION"
            ),
        ),
        (
            "STOP_GT48",
            lambda row: row.stop_distance_bin == ">48",
        ),
        (
            "TAKE_NONE",
            lambda row: row.take_room_bin == "NONE",
        ),
        (
            "TAKE_24_36",
            lambda row: row.take_room_bin == "24-36",
        ),
        (
            "LATE_AND_TAKE_NONE",
            lambda row: (
                row.lifecycle_bucket in {"LATE_DECAY", "LATE_ACTIVE"}
                and row.take_room_bin == "NONE"
            ),
        ),
        (
            "TRANSITION_AND_TAKE_NONE",
            lambda row: (
                row.lifecycle_bucket == "TRANSITION"
                and row.take_room_bin == "NONE"
            ),
        ),
        (
            "ENTRY_WITHIN_6P_OF_VALID_ZONE",
            lambda row: row.entry_within_6p_of_valid_zone,
        ),
        (
            "ENTRY_WITHIN_12P_OF_VALID_ZONE",
            lambda row: row.entry_within_12p_of_valid_zone,
        ),
    )
    print("  combined_context_slices_not_gates:")
    for name, predicate in combined_slices:
        items = _filter(contexts, predicate)
        if items:
            print(
                _slice_line(
                    name,
                    items,
                    total_losses=total_losses,
                    total_wins=total_wins,
                )
            )

    focus_rows = tuple(
        item for item in contexts if item.trade.signal_timestamp in FOCUS_CASES
    )
    assert len(focus_rows) == len(FOCUS_CASES)
    print("  chronological_focus_cases:")
    for index, item in enumerate(focus_rows, start=1):
        print(_focus_line(index, item))

    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_lifecycle_features_only=True")
    print("  causal_survival_role_zones_only=True")
    print("  lifecycle_and_sr_features_decoupled=True")
    print("  entry_gate_applied=False")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_LIFECYCLE_SR_ENTRY_CONTEXT_2025_CHECK=OK")


if __name__ == "__main__":
    main()
