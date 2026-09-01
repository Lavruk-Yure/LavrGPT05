# -*- coding: utf-8 -*-
"""RoadMap103 / 7T: S/R Entry Proximity Gate 2025, TEST_ONLY.

Runner повторює production Candidate F після 6K без змін і на тих самих
59 production entries перевіряє causal близькість entry до живих S/R zones.
Це paired fixed-entry counterfactual: rejected trade вилучається зі статистики,
але звільнена capacity не створює нових entries. Повний Replay з capacity —
окремий наступний крок лише для перспективного gate-кандидата.
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
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

_entry_context = importlib.import_module(
    "run_algorithm_workspace_candidate_f_lifecycle_sr_entry_context_2025_check"
)
EntryExitContextRuntime = _entry_context.EntryExitContextRuntime
FOCUS_CASES = _entry_context.FOCUS_CASES
_build_contexts = getattr(_entry_context, "_build_contexts")
_assert_baseline = getattr(_entry_context, "_assert_baseline")

_survival = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)
_all_observations = getattr(_survival, "_all_observations")

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

EPSILON = 1e-12
PIP = 0.0001
THRESHOLDS_PIPS = (3.0, 6.0, 9.0, 12.0, 15.0)

OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "LavrGPT05" / "RM103_7T_SR_Entry_Proximity_Gate_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_sr_entry_proximity_gate_2025.csv"


@dataclass(frozen=True, slots=True)
class ProximityRow:
    """Один production entry та causal proximity до живих S/R zones."""

    context: Any
    inside_valid_zone: bool
    stop_side_distance_pips: float | None
    take_side_distance_pips: float | None
    any_valid_zone_distance_pips: float | None

    @property
    def trade(self) -> Any:
        return self.context.trade

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
class Performance:
    """Closed-trade performance для fixed-entry diagnostic subset."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float
    maximum_drawdown: float


@dataclass(frozen=True, slots=True)
class GateResult:
    """Описовий результат одного TEST_ONLY proximity gate."""

    name: str
    rejected: Performance
    remaining: Performance
    loss_capture: float
    win_capture: float


def _edge_distance_pips(entry_price: float, zone: Any) -> float:
    if zone.low <= entry_price <= zone.high:
        return 0.0
    edge_distance = min(
        abs(entry_price - zone.low),
        abs(entry_price - zone.high),
    )
    return edge_distance / PIP


def _minimum_distance(
    observations: tuple[Any, ...],
    *,
    timestamp: datetime,
    role: str,
) -> float | None:
    distances = tuple(
        float(item.distance_pips)
        for item in observations
        if item.signal_timestamp == timestamp
        and item.effective_role != "INVALIDATED"
        and item.distance_role == role
        and item.distance_pips is not None
    )
    return min(distances) if distances else None


def _proximity_for_trade(
    trade: Any,
    observations: tuple[Any, ...],
) -> tuple[bool, float | None, float | None, float | None]:
    valid = tuple(
        item
        for item in observations
        if item.signal_timestamp == trade.signal_timestamp
        and item.effective_role != "INVALIDATED"
    )
    edge_distances = tuple(
        _edge_distance_pips(trade.entry_price, item.zone) for item in valid
    )
    any_distance = min(edge_distances) if edge_distances else None
    inside = any(distance <= EPSILON for distance in edge_distances)
    stop_distance = _minimum_distance(
        observations,
        timestamp=trade.signal_timestamp,
        role="STOP",
    )
    take_distance = _minimum_distance(
        observations,
        timestamp=trade.signal_timestamp,
        role="TAKE",
    )
    return inside, stop_distance, take_distance, any_distance


def _build_rows(runtime: Any) -> tuple[ProximityRow, ...]:
    contexts = _build_contexts(runtime)
    trades = tuple(item.trade for item in contexts)
    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {event.timestamp: index for index, event in enumerate(events)}
    observations = _all_observations(trades, events, event_index)

    rows: list[ProximityRow] = []
    for context in contexts:
        inside, stop_distance, take_distance, any_distance = _proximity_for_trade(
            context.trade, observations
        )
        rows.append(
            ProximityRow(
                context=context,
                inside_valid_zone=inside,
                stop_side_distance_pips=stop_distance,
                take_side_distance_pips=take_distance,
                any_valid_zone_distance_pips=any_distance,
            )
        )
    return tuple(rows)


def _profit_factor(rows: tuple[ProximityRow, ...]) -> float:
    gross_profit = sum(max(row.pnl, 0.0) for row in rows)
    gross_loss = abs(sum(min(row.pnl, 0.0) for row in rows))
    if gross_loss <= EPSILON:
        return math.inf if gross_profit > EPSILON else 0.0
    return gross_profit / gross_loss


def _maximum_drawdown(rows: tuple[ProximityRow, ...]) -> float:
    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    for row in sorted(rows, key=lambda item: item.trade.signal_timestamp):
        cumulative += row.pnl
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)
    return maximum_drawdown


def _performance(rows: tuple[ProximityRow, ...]) -> Performance:
    return Performance(
        trades=len(rows),
        wins=sum(row.outcome3 == "WIN" for row in rows),
        losses=sum(row.outcome3 == "LOSS" for row in rows),
        break_even=sum(row.outcome3 == "BREAK_EVEN" for row in rows),
        net=sum(row.pnl for row in rows),
        profit_factor=_profit_factor(rows),
        maximum_drawdown=_maximum_drawdown(rows),
    )


def _gate_result(
    name: str,
    rows: tuple[ProximityRow, ...],
    predicate: Callable[[ProximityRow], bool],
) -> GateResult:
    rejected = tuple(row for row in rows if predicate(row))
    remaining = tuple(row for row in rows if not predicate(row))
    rejected_performance = _performance(rejected)
    remaining_performance = _performance(remaining)
    total_losses = sum(row.outcome3 == "LOSS" for row in rows)
    total_wins = sum(row.outcome3 == "WIN" for row in rows)
    return GateResult(
        name=name,
        rejected=rejected_performance,
        remaining=remaining_performance,
        loss_capture=(
            rejected_performance.losses / total_losses if total_losses else 0.0
        ),
        win_capture=(rejected_performance.wins / total_wins if total_wins else 0.0),
    )


def _distance_within(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold + EPSILON


def _all_gate_results(
    rows: tuple[ProximityRow, ...],
) -> tuple[GateResult, ...]:
    results = [
        _gate_result(
            "INSIDE_VALID_ZONE",
            rows,
            lambda row: row.inside_valid_zone,
        )
    ]
    for threshold in THRESHOLDS_PIPS:
        label = f"{threshold:g}"
        results.extend(
            (
                _gate_result(
                    f"STOP_SIDE_LE_{label}P",
                    rows,
                    lambda row, value=threshold: _distance_within(
                        row.stop_side_distance_pips,
                        value,
                    ),
                ),
                _gate_result(
                    f"TAKE_SIDE_LE_{label}P",
                    rows,
                    lambda row, value=threshold: _distance_within(
                        row.take_side_distance_pips,
                        value,
                    ),
                ),
                _gate_result(
                    f"ANY_VALID_ZONE_LE_{label}P",
                    rows,
                    lambda row, value=threshold: _distance_within(
                        row.any_valid_zone_distance_pips,
                        value,
                    ),
                ),
            )
        )
    return tuple(results)


def _pf_text(value: float) -> str:
    return "INF" if math.isinf(value) else f"{value:.4f}"


def _performance_text(item: Performance) -> str:
    return (
        f"n:{item.trades},W:{item.wins},L:{item.losses},BE:{item.break_even},"
        f"net:{item.net:+.2f},pf:{_pf_text(item.profit_factor)},"
        f"dd:{item.maximum_drawdown:.2f}"
    )


def _gate_line(item: GateResult) -> str:
    return (
        f"    {item.name} | rejected:{_performance_text(item.rejected)} "
        f"lossCapture:{item.loss_capture:.3f},winCapture:{item.win_capture:.3f} "
        f"| remaining:{_performance_text(item.remaining)}"
    )


def _distance_text(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.1f}p"


def _threshold_mask(value: float | None) -> str:
    if value is None:
        return "NONE"
    hits = tuple(
        f"{threshold:g}"
        for threshold in THRESHOLDS_PIPS
        if value <= threshold + EPSILON
    )
    return ",".join(hits) if hits else "NONE"


def _focus_line(index: int, row: ProximityRow) -> str:
    trade = row.trade
    return (
        f"    {index:02d}. {trade.signal_timestamp.isoformat()} "
        f"{trade.direction} {row.outcome3}/{row.pnl:+.2f} "
        f"inside:{row.inside_valid_zone} "
        f"stopD:{_distance_text(row.stop_side_distance_pips)} "
        f"takeD:{_distance_text(row.take_side_distance_pips)} "
        f"anyD:{_distance_text(row.any_valid_zone_distance_pips)} "
        f"stopRejectAt:{_threshold_mask(row.stop_side_distance_pips)} "
        f"takeRejectAt:{_threshold_mask(row.take_side_distance_pips)} "
        f"anyRejectAt:{_threshold_mask(row.any_valid_zone_distance_pips)}"
    )


def _write_csv(rows: tuple[ProximityRow, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "signal_utc",
        "direction",
        "outcome",
        "final_profit",
        "inside_valid_zone",
        "stop_side_distance_pips",
        "take_side_distance_pips",
        "any_valid_zone_distance_pips",
    ]
    for threshold in THRESHOLDS_PIPS:
        label = f"{threshold:g}p"
        fieldnames.extend(
            (
                f"reject_stop_side_le_{label}",
                f"reject_take_side_le_{label}",
                f"reject_any_valid_zone_le_{label}",
            )
        )

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            record: dict[str, object] = {
                "signal_utc": row.trade.signal_timestamp.isoformat(),
                "direction": row.trade.direction,
                "outcome": row.outcome3,
                "final_profit": f"{row.pnl:.4f}",
                "inside_valid_zone": row.inside_valid_zone,
                "stop_side_distance_pips": (
                    ""
                    if row.stop_side_distance_pips is None
                    else f"{row.stop_side_distance_pips:.6f}"
                ),
                "take_side_distance_pips": (
                    ""
                    if row.take_side_distance_pips is None
                    else f"{row.take_side_distance_pips:.6f}"
                ),
                "any_valid_zone_distance_pips": (
                    ""
                    if row.any_valid_zone_distance_pips is None
                    else f"{row.any_valid_zone_distance_pips:.6f}"
                ),
            }
            for threshold in THRESHOLDS_PIPS:
                label = f"{threshold:g}p"
                record[f"reject_stop_side_le_{label}"] = _distance_within(
                    row.stop_side_distance_pips,
                    threshold,
                )
                record[f"reject_take_side_le_{label}"] = _distance_within(
                    row.take_side_distance_pips,
                    threshold,
                )
                record[f"reject_any_valid_zone_le_{label}"] = _distance_within(
                    row.any_valid_zone_distance_pips,
                    threshold,
                )
            writer.writerow(record)
    return OUTPUT_CSV


def main() -> None:
    """Run production 6K baseline and fixed-entry proximity gate matrix."""
    runtime = EntryExitContextRuntime(
        _entry_context.frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    _entry_context.assert_frozen_oos_snapshot()
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
    rows = _build_rows(runtime)
    assert len(rows) == 59
    assert len({row.trade.signal_uid for row in rows}) == 59

    baseline = _performance(rows)
    summary = runtime.historical_summary
    assert summary is not None
    assert (baseline.trades, baseline.wins, baseline.losses) == (59, 40, 18)
    assert baseline.break_even == 1
    assert abs(baseline.net - summary.net_profit) <= 1e-9
    assert abs(baseline.profit_factor - summary.profit_factor) <= 1e-9
    assert abs(baseline.maximum_drawdown - summary.maximum_drawdown) <= 1e-9

    results = _all_gate_results(rows)
    assert len(results) == 1 + len(THRESHOLDS_PIPS) * 3
    output_csv = _write_csv(rows)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F S/R Entry Proximity Gate 2025 result")
    print("  mode=PRODUCTION_6K_SR_ENTRY_PROXIMITY_GATE_TEST_ONLY_FIXED_ENTRIES")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  production_entry_gate_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  test_only_gate_simulation=True")
    print("  paired_entries_fixed_to_production=True")
    print("  freed_capacity_new_entries_not_generated=True")
    print("  full_replay_capacity_check=False")
    print("  future_price_used_as_entry_feature=False")
    print("  valid_zone_definition=survival_role_aware_and_not_INVALIDATED")
    print("  side_distance_definition=nearest_zone_fully_on_trade_STOP_or_TAKE_side")
    print("  any_distance_definition=nearest_edge_of_any_valid_zone_or_0_if_inside")
    print("  proximity_thresholds_pips=3|6|9|12|15")
    print(f"  baseline={_performance_text(baseline)}")
    print("  gate_matrix_fixed_entries:")
    for result in results:
        print(_gate_line(result))

    ranked = sorted(
        results,
        key=lambda item: (
            -item.remaining.net,
            -item.remaining.profit_factor,
            item.win_capture,
            -item.loss_capture,
        ),
    )
    print("  descriptive_ranking_by_remaining_net:")
    for index, result in enumerate(ranked[:8], start=1):
        print(
            f"    {index:02d}. {result.name} "
            f"remainingNet:{result.remaining.net:+.2f} "
            f"PF:{_pf_text(result.remaining.profit_factor)} "
            f"DD:{result.remaining.maximum_drawdown:.2f} "
            f"lossCapture:{result.loss_capture:.3f} "
            f"winCapture:{result.win_capture:.3f}"
        )

    by_timestamp = {row.trade.signal_timestamp: row for row in rows}
    print("  chronological_focus_cases:")
    for index, timestamp in enumerate(FOCUS_CASES, start=1):
        row = by_timestamp[timestamp]
        print(_focus_line(index, row))

    print(f"  output_csv={output_csv}")
    print("  inside_zone_gate_tested=True")
    print("  stop_side_gate_tested=True")
    print("  take_side_gate_tested=True")
    print("  any_valid_zone_gate_tested=True")
    print("  baseline_fixed_entry_dd_matches_runtime=True")
    print("  completed_bars_only=True")
    print("  causal_survival_role_zones_only=True")
    print("  entry_gate_applied_to_production=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ENTRY_PROXIMITY_GATE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
