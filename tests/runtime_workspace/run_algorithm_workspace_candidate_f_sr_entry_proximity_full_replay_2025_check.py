# -*- coding: utf-8 -*-
"""RoadMap103 / 7U: full Replay S/R proximity gate capacity check 2025.

Runner не змінює production Candidate F 6K. Три заморожені 7T thresholds
9/12/15 pip перевіряються у повному Historical Replay, де TEST_ONLY gate
працює до risk/execution queue і тому реально звільняє position capacity.

На відміну від paired 7T, повний causal gate не має права читати фактичний
NEXT_BAR_OPEN entry з майбутнього. Тому рішення 7U використовує завершений
signal-bar close як доступну на signal timestamp reference price. Окремо
друкується agreement з 7T NEXT_BAR_OPEN fixed-entry classification, щоб не
змішувати causal implementation із ретроспективним paired diagnostic.
"""

from __future__ import annotations

import csv
import importlib
import math
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

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
_assert_baseline = getattr(_entry_context, "_assert_baseline")

_survival = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_zone_survival_relevance_2025_check"
)
FOCUS_LOOKBACK_BARS = _survival.FOCUS_LOOKBACK_BARS
FOCUS_ZONE_HALF_WIDTH_PIPS = _survival.FOCUS_ZONE_HALF_WIDTH_PIPS
MINIMUM_PIVOTS = _survival.MINIMUM_PIVOTS
_build_zones = getattr(_survival, "_build_zones")
_break_episodes = getattr(_survival, "_break_episodes")
_role_and_survival = getattr(_survival, "_role_and_survival")

_proximity = importlib.import_module(
    "run_algorithm_workspace_candidate_f_sr_entry_proximity_gate_2025_check"
)
_build_fixed_rows = getattr(_proximity, "_build_rows")
_distance_within = getattr(_proximity, "_distance_within")
_fixed_performance = getattr(_proximity, "_performance")

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)

EPSILON = 1e-12
PIP = 0.0001
THRESHOLDS_PIPS = (9.0, 12.0, 15.0)

OUTPUT_DIR = (
    Path(tempfile.gettempdir())
    / "LavrGPT05"
    / "RM103_7U_SR_Entry_Proximity_Full_Replay_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_sr_entry_proximity_full_replay_2025.csv"


@dataclass(frozen=True, slots=True)
class GateRejection:
    """Один causal TEST_ONLY reject до risk/execution queue."""

    signal_uid: str
    timestamp: datetime
    direction: str
    threshold_pips: float
    reference_price: float
    any_valid_zone_distance_pips: float


@dataclass(frozen=True, slots=True)
class SubsetPerformance:
    """Performance довільного subset Historical Replay trades."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float
    maximum_drawdown: float


@dataclass(frozen=True, slots=True)
class ReplayVariant:
    """Один повний Replay для замороженого proximity threshold."""

    threshold_pips: float
    runtime: Any
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    performance: SubsetPerformance
    fixed_next_open_expected: SubsetPerformance
    fixed_signal_close_expected: SubsetPerformance
    gate_rejections: tuple[GateRejection, ...]
    baseline_entries_retained: int
    baseline_entries_directly_rejected: int
    baseline_entries_displaced: int
    new_entries: tuple[WorkspaceHistoricalTradeDiagnostic, ...]
    new_entry_performance: SubsetPerformance
    decision_agreement: int
    decision_disagreement: int
    next_open_only_rejects: int
    signal_close_only_rejects: int

    @property
    def capacity_delta_vs_signal_close(self) -> float:
        return self.performance.net - self.fixed_signal_close_expected.net

    @property
    def capacity_delta_vs_next_open(self) -> float:
        return self.performance.net - self.fixed_next_open_expected.net


class SrEntryProximityGateRuntime(EntryExitContextRuntime):
    """Full Replay Runtime з causal S/R proximity gate до queue_signal."""

    def __init__(self, *args, threshold_pips: float, **kwargs) -> None:
        self.threshold_pips = float(threshold_pips)
        self.gate_rejections: list[GateRejection] = []
        super().__init__(*args, **kwargs)

    def _record_signal(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalRecord:
        gated, distance = self._apply_test_only_gate(event, proposal)
        record = getattr(super(), "_record_signal")(event, gated)
        if distance is not None and gated is not proposal:
            self.gate_rejections.append(
                GateRejection(
                    signal_uid=record.signal_uid,
                    timestamp=event.timestamp,
                    direction=proposal.direction,
                    threshold_pips=self.threshold_pips,
                    reference_price=event.close,
                    any_valid_zone_distance_pips=distance,
                )
            )
        return record

    def _apply_test_only_gate(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> tuple[WorkspaceSignalProposal, float | None]:
        if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
            return proposal, None
        if not self.can_form_signal():
            return proposal, None
        distance = _causal_any_zone_distance(
            self.strategy_events,
            signal_event=event,
            reference_price=event.close,
        )
        if distance is None or distance > self.threshold_pips + EPSILON:
            return proposal, None
        threshold_label = f"{self.threshold_pips:g}"
        return (
            replace(
                proposal,
                filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
                filter_reason_code=(
                    f"TEST_ONLY_SR_ANY_ZONE_PROXIMITY_LE_{threshold_label}P"
                ),
                reason=(
                    f"{proposal.reason}; TEST_ONLY_SR_ANY_ZONE_PROXIMITY: "
                    f"signal_close_distance={distance:.3f}p, "
                    f"threshold={self.threshold_pips:.1f}p"
                ).strip("; "),
            ),
            distance,
        )


def _edge_distance_pips(reference_price: float, zone: Any) -> float:
    if zone.low <= reference_price <= zone.high:
        return 0.0
    return (
        min(
            abs(reference_price - zone.low),
            abs(reference_price - zone.high),
        )
        / PIP
    )


def _causal_any_zone_distance(
    strategy_events: dict[datetime, WorkspaceMarketEvent],
    *,
    signal_event: WorkspaceMarketEvent,
    reference_price: float,
) -> float | None:
    """Nearest live S/R band using only completed bars through signal_event."""
    events = tuple(
        strategy_events[timestamp]
        for timestamp in sorted(strategy_events)
        if timestamp <= signal_event.timestamp
    )
    if not events or events[-1].timestamp != signal_event.timestamp:
        return None
    signal_index = len(events) - 1
    distances: list[float] = []
    for kind in ("SUPPORT", "RESISTANCE"):
        zones = _build_zones(
            events,
            signal_index,
            kind=kind,
            lookback_bars=FOCUS_LOOKBACK_BARS,
            half_width_pips=FOCUS_ZONE_HALF_WIDTH_PIPS,
        )
        for zone in zones:
            if zone.pivot_count < MINIMUM_PIVOTS:
                continue
            episodes = _break_episodes(events, signal_index, zone)
            effective_role, _, _, _ = _role_and_survival(
                events,
                signal_index,
                zone,
                episodes,
            )
            if effective_role == "INVALIDATED":
                continue
            distances.append(_edge_distance_pips(reference_price, zone))
    return min(distances) if distances else None


def _trade_outcome(trade: WorkspaceHistoricalTradeDiagnostic) -> str:
    if trade.final_profit > EPSILON:
        return "WIN"
    if trade.final_profit < -EPSILON:
        return "LOSS"
    return "BREAK_EVEN"


def _subset_performance(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> SubsetPerformance:
    ordered = tuple(sorted(trades, key=lambda item: item.signal_timestamp))
    gross_profit = sum(max(trade.final_profit, 0.0) for trade in ordered)
    gross_loss = abs(sum(min(trade.final_profit, 0.0) for trade in ordered))
    if gross_loss <= EPSILON:
        profit_factor = math.inf if gross_profit > EPSILON else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    for trade in ordered:
        cumulative += trade.final_profit
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)

    return SubsetPerformance(
        trades=len(ordered),
        wins=sum(_trade_outcome(trade) == "WIN" for trade in ordered),
        losses=sum(_trade_outcome(trade) == "LOSS" for trade in ordered),
        break_even=sum(_trade_outcome(trade) == "BREAK_EVEN" for trade in ordered),
        net=sum(trade.final_profit for trade in ordered),
        profit_factor=profit_factor,
        maximum_drawdown=maximum_drawdown,
    )


def _summary_performance(runtime: Any) -> SubsetPerformance:
    summary = runtime.historical_summary
    assert summary is not None
    return SubsetPerformance(
        trades=summary.opened_trades,
        wins=summary.winning_trades,
        losses=summary.losing_trades,
        break_even=summary.break_even_trades,
        net=summary.net_profit,
        profit_factor=(
            float(summary.profit_factor)
            if summary.profit_factor is not None
            else (math.inf if summary.gross_profit > EPSILON else 0.0)
        ),
        maximum_drawdown=summary.maximum_drawdown,
    )


def _fixed_performance_to_subset(item: Any) -> SubsetPerformance:
    return SubsetPerformance(
        trades=item.trades,
        wins=item.wins,
        losses=item.losses,
        break_even=item.break_even,
        net=item.net,
        profit_factor=item.profit_factor,
        maximum_drawdown=item.maximum_drawdown,
    )


def _run_baseline() -> tuple[Any, tuple[WorkspaceHistoricalTradeDiagnostic, ...]]:
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
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    assert len(trades) == 59
    return runtime, trades


def _run_gated(threshold_pips: float) -> SrEntryProximityGateRuntime:
    runtime = SrEntryProximityGateRuntime(
        _entry_context.frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
        threshold_pips=threshold_pips,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert runtime.risk_policy.maximum_open_positions == 2
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    return runtime


def _signal_close_distances_for_baseline(
    runtime: Any,
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for trade in baseline_trades:
        event = runtime.strategy_events[trade.signal_timestamp]
        result[trade.signal_uid] = _causal_any_zone_distance(
            runtime.strategy_events,
            signal_event=event,
            reference_price=event.close,
        )
    return result


def _fixed_signal_close_performance(
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    distances: dict[str, float | None],
    threshold_pips: float,
) -> SubsetPerformance:
    remaining = tuple(
        trade
        for trade in baseline_trades
        if not _distance_within(distances[trade.signal_uid], threshold_pips)
    )
    return _subset_performance(remaining)


def _decision_agreement(
    baseline_rows: tuple[Any, ...],
    signal_close_distances: dict[str, float | None],
    threshold_pips: float,
) -> tuple[int, int, int, int]:
    agreement = 0
    disagreement = 0
    next_open_only = 0
    signal_close_only = 0
    for row in baseline_rows:
        signal_uid = row.trade.signal_uid
        next_open_reject = _distance_within(
            row.any_valid_zone_distance_pips,
            threshold_pips,
        )
        signal_close_reject = _distance_within(
            signal_close_distances[signal_uid],
            threshold_pips,
        )
        if next_open_reject == signal_close_reject:
            agreement += 1
            continue
        disagreement += 1
        if next_open_reject:
            next_open_only += 1
        else:
            signal_close_only += 1
    return agreement, disagreement, next_open_only, signal_close_only


def _variant(
    threshold_pips: float,
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    baseline_rows: tuple[Any, ...],
    signal_close_distances: dict[str, float | None],
) -> ReplayVariant:
    runtime = _run_gated(threshold_pips)
    execution = runtime.replay_execution
    assert execution is not None
    trades = execution.trade_diagnostics()
    performance = _summary_performance(runtime)
    assert performance.trades == len(trades)

    next_open_remaining = tuple(
        row
        for row in baseline_rows
        if not _distance_within(
            row.any_valid_zone_distance_pips,
            threshold_pips,
        )
    )
    fixed_next_open = _fixed_performance(next_open_remaining)
    fixed_signal_close = _fixed_signal_close_performance(
        baseline_trades,
        signal_close_distances,
        threshold_pips,
    )

    baseline_uids = {trade.signal_uid for trade in baseline_trades}
    gated_uids = {trade.signal_uid for trade in trades}
    rejected_uids = {item.signal_uid for item in runtime.gate_rejections}

    retained = len(baseline_uids & gated_uids)
    directly_rejected = len(baseline_uids & rejected_uids)
    displaced_uids = baseline_uids - gated_uids - rejected_uids
    new_entries = tuple(
        trade for trade in trades if trade.signal_uid not in baseline_uids
    )

    agreement, disagreement, next_only, signal_only = _decision_agreement(
        baseline_rows,
        signal_close_distances,
        threshold_pips,
    )
    return ReplayVariant(
        threshold_pips=threshold_pips,
        runtime=runtime,
        trades=trades,
        performance=performance,
        fixed_next_open_expected=_fixed_performance_to_subset(fixed_next_open),
        fixed_signal_close_expected=fixed_signal_close,
        gate_rejections=tuple(runtime.gate_rejections),
        baseline_entries_retained=retained,
        baseline_entries_directly_rejected=directly_rejected,
        baseline_entries_displaced=len(displaced_uids),
        new_entries=new_entries,
        new_entry_performance=_subset_performance(new_entries),
        decision_agreement=agreement,
        decision_disagreement=disagreement,
        next_open_only_rejects=next_only,
        signal_close_only_rejects=signal_only,
    )


def _pf_text(value: float) -> str:
    return "INF" if math.isinf(value) else f"{value:.4f}"


def _performance_text(item: SubsetPerformance) -> str:
    return (
        f"trades:{item.trades},wins:{item.wins},losses:{item.losses},"
        f"break_even:{item.break_even},net:{item.net:+.2f},"
        f"pf:{_pf_text(item.profit_factor)},dd:{item.maximum_drawdown:.2f}"
    )


def _variant_line(item: ReplayVariant) -> str:
    threshold = f"{item.threshold_pips:g}"
    return (
        f"    ANY_LE_{threshold}P full:{_performance_text(item.performance)} "
        f"| fixedSignalClose:{item.fixed_signal_close_expected.net:+.2f} "
        f"| fixedNextOpen7T:{item.fixed_next_open_expected.net:+.2f} "
        f"| capacityDeltaSignal:{item.capacity_delta_vs_signal_close:+.2f} "
        f"| capacityDelta7T:{item.capacity_delta_vs_next_open:+.2f}"
    )


def _capacity_line(item: ReplayVariant) -> str:
    threshold = f"{item.threshold_pips:g}"
    new = item.new_entry_performance
    return (
        f"    ANY_LE_{threshold}P gateReject:{len(item.gate_rejections)} "
        f"baselineRetained:{item.baseline_entries_retained} "
        f"baselineDirectReject:{item.baseline_entries_directly_rejected} "
        f"baselineDisplaced:{item.baseline_entries_displaced} "
        f"newEntries:{len(item.new_entries)} "
        f"newEntryW/L/BE:{new.wins}/{new.losses}/{new.break_even} "
        f"newEntryNet:{new.net:+.2f}"
    )


def _agreement_line(item: ReplayVariant) -> str:
    threshold = f"{item.threshold_pips:g}"
    return (
        f"    ANY_LE_{threshold}P agreement:{item.decision_agreement}/59 "
        f"disagreement:{item.decision_disagreement}/59 "
        f"nextOpenOnly:{item.next_open_only_rejects} "
        f"signalCloseOnly:{item.signal_close_only_rejects}"
    )


def _focus_status(
    trade: WorkspaceHistoricalTradeDiagnostic,
    variant: ReplayVariant,
) -> str:
    gated_uids = {item.signal_uid for item in variant.trades}
    rejected_uids = {item.signal_uid for item in variant.gate_rejections}
    if trade.signal_uid in gated_uids:
        return "RETAINED"
    if trade.signal_uid in rejected_uids:
        return "DIRECT_GATE_REJECT"
    return "DISPLACED_CAPACITY_PATH"


def _distance_text(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.1f}p"


def _write_csv(variants: tuple[ReplayVariant, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "threshold_pips",
        "full_trades",
        "full_wins",
        "full_losses",
        "full_break_even",
        "full_net",
        "full_profit_factor",
        "full_maximum_drawdown",
        "fixed_signal_close_net",
        "fixed_next_open_7t_net",
        "capacity_delta_signal_close",
        "capacity_delta_next_open_7t",
        "gate_rejections",
        "baseline_entries_retained",
        "baseline_entries_directly_rejected",
        "baseline_entries_displaced",
        "new_entries",
        "new_entry_wins",
        "new_entry_losses",
        "new_entry_break_even",
        "new_entry_net",
        "decision_agreement",
        "decision_disagreement",
        "next_open_only_rejects",
        "signal_close_only_rejects",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for item in variants:
            performance = item.performance
            new = item.new_entry_performance
            writer.writerow(
                {
                    "threshold_pips": f"{item.threshold_pips:.1f}",
                    "full_trades": performance.trades,
                    "full_wins": performance.wins,
                    "full_losses": performance.losses,
                    "full_break_even": performance.break_even,
                    "full_net": f"{performance.net:.6f}",
                    "full_profit_factor": _pf_text(performance.profit_factor),
                    "full_maximum_drawdown": f"{performance.maximum_drawdown:.6f}",
                    "fixed_signal_close_net": (
                        f"{item.fixed_signal_close_expected.net:.6f}"
                    ),
                    "fixed_next_open_7t_net": (
                        f"{item.fixed_next_open_expected.net:.6f}"
                    ),
                    "capacity_delta_signal_close": (
                        f"{item.capacity_delta_vs_signal_close:.6f}"
                    ),
                    "capacity_delta_next_open_7t": (
                        f"{item.capacity_delta_vs_next_open:.6f}"
                    ),
                    "gate_rejections": len(item.gate_rejections),
                    "baseline_entries_retained": item.baseline_entries_retained,
                    "baseline_entries_directly_rejected": (
                        item.baseline_entries_directly_rejected
                    ),
                    "baseline_entries_displaced": item.baseline_entries_displaced,
                    "new_entries": len(item.new_entries),
                    "new_entry_wins": new.wins,
                    "new_entry_losses": new.losses,
                    "new_entry_break_even": new.break_even,
                    "new_entry_net": f"{new.net:.6f}",
                    "decision_agreement": item.decision_agreement,
                    "decision_disagreement": item.decision_disagreement,
                    "next_open_only_rejects": item.next_open_only_rejects,
                    "signal_close_only_rejects": item.signal_close_only_rejects,
                }
            )
    return OUTPUT_CSV


def main() -> None:
    """Run baseline and three full causal Replay proximity-gate variants."""
    baseline_runtime, baseline_trades = _run_baseline()
    baseline_performance = _summary_performance(baseline_runtime)
    baseline_rows = _build_fixed_rows(baseline_runtime)
    assert len(baseline_rows) == len(baseline_trades) == 59

    signal_close_distances = _signal_close_distances_for_baseline(
        baseline_runtime,
        baseline_trades,
    )
    assert set(signal_close_distances) == {
        trade.signal_uid for trade in baseline_trades
    }

    variants = tuple(
        _variant(
            threshold,
            baseline_trades,
            baseline_rows,
            signal_close_distances,
        )
        for threshold in THRESHOLDS_PIPS
    )
    assert len(variants) == 3

    for item in variants:
        assert item.performance.trades == len(item.trades)
        assert (
            item.baseline_entries_retained
            + item.baseline_entries_directly_rejected
            + item.baseline_entries_displaced
            == len(baseline_trades)
        )
        assert item.decision_agreement + item.decision_disagreement == 59
        assert (
            item.next_open_only_rejects + item.signal_close_only_rejects
            == item.decision_disagreement
        )
        assert all(
            rejection.any_valid_zone_distance_pips <= item.threshold_pips + EPSILON
            for rejection in item.gate_rejections
        )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for item in variants
        for entry in item.runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    output_csv = _write_csv(variants)

    print(
        "Algorithm Workspace Candidate F S/R Entry Proximity Full Replay " "2025 result"
    )
    print("  mode=PRODUCTION_6K_SR_ENTRY_PROXIMITY_FULL_REPLAY_TEST_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  production_entry_gate_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  test_only_gate_simulation=True")
    print("  paired_entries_fixed_to_production=False")
    print("  full_replay_capacity_check=True")
    print("  freed_capacity_can_generate_new_entries=True")
    print("  thresholds_frozen_from_7T=9|12|15")
    print("  gate_scope=ANY_VALID_SURVIVAL_ROLE_AWARE_ZONE")
    print("  gate_application_point=SIGNAL_RECORD_BEFORE_RISK_AND_EXECUTION_QUEUE")
    print("  causal_gate_reference_price=COMPLETED_SIGNAL_BAR_CLOSE")
    print("  next_bar_open_price_used_by_full_replay_gate=False")
    print("  7T_next_bar_open_distance_used_for_comparison_only=True")
    print("  future_price_used_as_gate=False")
    print(f"  baseline={_performance_text(baseline_performance)}")
    print("  full_replay_variants:")
    for item in variants:
        print(_variant_line(item))

    print("  capacity_path:")
    for item in variants:
        print(_capacity_line(item))

    print("  signal_close_vs_7T_next_bar_open_gate_agreement:")
    for item in variants:
        print(_agreement_line(item))

    baseline_by_timestamp = {trade.signal_timestamp: trade for trade in baseline_trades}
    fixed_by_uid = {row.trade.signal_uid: row for row in baseline_rows}
    print("  chronological_focus_cases:")
    for index, timestamp in enumerate(FOCUS_CASES, start=1):
        trade = baseline_by_timestamp[timestamp]
        fixed_row = fixed_by_uid[trade.signal_uid]
        signal_distance = signal_close_distances[trade.signal_uid]
        statuses = " | ".join(
            f"{item.threshold_pips:g}p:{_focus_status(trade, item)}"
            for item in variants
        )
        print(
            f"    {index:02d}. {timestamp.isoformat()} {trade.direction} "
            f"{_trade_outcome(trade)}/{trade.final_profit:+.2f} "
            f"signalCloseD:{_distance_text(signal_distance)} "
            f"nextOpen7TD:{_distance_text(fixed_row.any_valid_zone_distance_pips)} "
            f"{statuses}"
        )

    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_survival_role_zones_only=True")
    print("  gate_runs_before_capacity_queue=True")
    print("  replacement_entries_measured=True")
    print("  capacity_delta_measured=True")
    print("  entry_gate_applied_to_production=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_SR_ENTRY_PROXIMITY_"
        "FULL_REPLAY_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
