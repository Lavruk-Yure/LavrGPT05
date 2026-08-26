# -*- coding: utf-8 -*-
"""RoadMap102: full-OOS shadow rescue single-criterion MACD rejects за 2025.

Runner не змінює production MACD Quality thresholds. Для кожного criterion
PROMINENCE / DISTANCE / ANGLE окремий test-only алгоритм пропускає далі лише
ті EXTENDED MACD crosses, які в frozen production quality провалили рівно
один відповідний criterion. Після такого shadow rescue незмінні Alligator,
Candidate F, risk та Historical Replay execution вирішують долю сигналу.

Мета — перевірити near-miss гіпотезу на всьому OOS 2025, а не тільки на вже
відомих strong-trend windows. Немає performance assertions і немає зміни
production trade gate.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen  # noqa: E402

trend = importlib.import_module(
    "run_algorithm_workspace_candidate_f_trend_coverage_2025_check"
)
from core.workspace_algorithm import WorkspaceSignalOutput  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_BUY_ALLOW,
    ALLIGATOR_REASON_BUY_START_REJECT,
    ALLIGATOR_REASON_DEFERRED_ARMED,
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_OVEREXTENDED,
    ALLIGATOR_REASON_SELL_ALLOW,
    ALLIGATOR_REASON_SELL_START_REJECT,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_WEAK_OPENING,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_macd import WorkspaceMacdSignalSource  # noqa: E402
from core.workspace_macd_crossover_quality import (  # noqa: E402
    MACD_QUALITY_REASON_ACCEPTED,
    WorkspaceMacdCrossoverQualityDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)

CRITERION_PROMINENCE = "PROMINENCE"
CRITERION_DISTANCE = "DISTANCE"
CRITERION_ANGLE = "ANGLE"
SHADOW_CRITERIA = (
    CRITERION_PROMINENCE,
    CRITERION_DISTANCE,
    CRITERION_ANGLE,
)

STRUCTURAL_REASONS = {
    ALLIGATOR_REASON_OPENING_COLLAPSE,
    ALLIGATOR_REASON_WEAK_OPENING,
    ALLIGATOR_REASON_VOLATILITY_SPIKE,
    ALLIGATOR_REASON_OVEREXTENDED,
}
DIRECT_ALLIGATOR_ALLOW_REASONS = {
    ALLIGATOR_REASON_BUY_ALLOW,
    ALLIGATOR_REASON_SELL_ALLOW,
}
STARTING_REASONS = {
    ALLIGATOR_REASON_BUY_START_REJECT,
    ALLIGATOR_REASON_SELL_START_REJECT,
}


@dataclass(frozen=True, slots=True)
class ShadowRescuedCross:
    """Один frozen quality reject, пропущений test-only shadow gate."""

    timestamp: datetime
    direction: str
    criterion: str
    source_reason_code: str


@dataclass(frozen=True, slots=True)
class ShadowVariantResult:
    """Підсумок одного criterion-specific full-OOS shadow run."""

    criterion: str
    eligible: int
    strong_aligned: int
    outside_strong: int
    initial_alligator_allow: int
    initial_alligator_starting: int
    initial_alligator_reject_other: int
    candidate_direct_accept: int
    candidate_armed: int
    candidate_structural_reject: int
    deferred_release: int
    accepted_signal_records: int
    trades: int
    wins: int
    losses: int
    break_even: int
    pnl: float
    profit_factor: float | None
    closed_pnl_drawdown: float
    portfolio_trades: int
    portfolio_net_profit: float
    portfolio_profit_factor: float | None
    portfolio_drawdown: float
    broker_execution_attempted: bool


class ShadowRescueMacdSignalSource(WorkspaceMacdSignalSource):
    """Frozen MACD source, що shadow-rescue лише один failed criterion."""

    def __init__(
        self,
        base: WorkspaceMacdSignalSource,
        rescue_criterion: str,
    ) -> None:
        super().__init__(
            enabled=base.enabled,
            mode=base.mode,
            runtime_profile=base.runtime_profile,
            extremum_min_prominence=base.extremum_min_prominence,
            extremum_to_cross_min_distance=base.extremum_to_cross_min_distance,
            cross_min_angle_degrees=base.cross_min_angle_degrees,
            angle_model=base.angle_model,
            cross_min_abc_angle_degrees=base.cross_min_abc_angle_degrees,
            abc_indicator_value_scale=base.abc_indicator_value_scale,
        )
        criterion = str(rescue_criterion or "").strip().upper()
        if criterion not in SHADOW_CRITERIA:
            raise ValueError(f"Unsupported shadow rescue criterion: {criterion}")
        self.rescue_criterion = criterion
        self.rescued_crosses: list[ShadowRescuedCross] = []

    def reset(self) -> None:
        super().reset()
        self.rescued_crosses = []

    def _proposal(
        self,
        direction: str,
        state: str,
        histogram: float,
        *,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal:
        proposal = super()._proposal(
            direction,
            state,
            histogram,
            event=event,
        )
        if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_REJECT:
            return proposal
        diagnostic = self.quality_diagnostics[-1]
        failures = _failed_criteria(diagnostic)
        if failures != (self.rescue_criterion,):
            return proposal
        self.rescued_crosses.append(
            ShadowRescuedCross(
                timestamp=event.timestamp,
                direction=direction,
                criterion=self.rescue_criterion,
                source_reason_code=str(proposal.source_reason_code or ""),
            )
        )
        return replace(
            proposal,
            source_reason_code=MACD_QUALITY_REASON_ACCEPTED,
            filter_decision=WORKSPACE_SIGNAL_FILTER_ALLOW,
            filter_reason_code=None,
            reason=(
                f"{proposal.reason}; "
                f"SHADOW_ORIGINAL_SOURCE_REASON={proposal.source_reason_code}; "
                f"SHADOW_RESCUE_SINGLE_CRITERION={self.rescue_criterion}"
            ),
        )


class ShadowRescueAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Test-only RailAlgorithm з frozen quality single-criterion rescue."""

    def __init__(
        self,
        algorithm_id: str,
        rescue_criterion: str,
    ) -> None:
        super().__init__(algorithm_id)
        self.rescue_criterion = rescue_criterion
        self.rescued_base_reason: dict[datetime, str] = {}

    def configure(
        self,
        context,
        parameters,
    ) -> None:
        super().configure(context, parameters)
        source = self.source
        if source is None:
            raise AssertionError("MACD source must exist after configure")
        self.source = ShadowRescueMacdSignalSource(
            source,
            self.rescue_criterion,
        )

    def start(self) -> None:
        super().start()
        self.rescued_base_reason = {}

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        base_output = self._base_signal_output(event)
        source = self.shadow_source
        if source.rescued_crosses:
            latest = source.rescued_crosses[-1]
            if latest.timestamp == event.timestamp:
                proposal = _single_proposal(base_output)
                if proposal is not None:
                    self.rescued_base_reason[event.timestamp] = (
                        str(proposal.filter_reason_code or "").strip().upper()
                    )
        if not self._candidate_f_active():
            return base_output
        return self._candidate_f_output(event, base_output)

    @property
    def shadow_source(self) -> ShadowRescueMacdSignalSource:
        source = self.source
        if not isinstance(source, ShadowRescueMacdSignalSource):
            raise AssertionError("Shadow MACD source is not configured")
        return source


def _single_proposal(output: WorkspaceSignalOutput) -> WorkspaceSignalProposal | None:
    if output is None:
        return None
    if isinstance(output, WorkspaceSignalProposal):
        return output
    proposals = tuple(output)
    if len(proposals) != 1:
        raise AssertionError("Base MACD output must contain at most one proposal")
    return proposals[0]


def _failed_criteria(
    diagnostic: WorkspaceMacdCrossoverQualityDiagnostic,
) -> tuple[str, ...]:
    failures: list[str] = []
    if not diagnostic.criterion_extremum_pass:
        failures.append("EXTREMUM")
    if not diagnostic.criterion_prominence_pass:
        failures.append(CRITERION_PROMINENCE)
    if not diagnostic.criterion_distance_pass:
        failures.append(CRITERION_DISTANCE)
    if not diagnostic.criterion_angle_pass:
        failures.append(CRITERION_ANGLE)
    return tuple(failures)


def _record_for_timestamp(
    records: tuple[WorkspaceSignalRecord, ...],
    timestamp: datetime,
    direction: str,
) -> WorkspaceSignalRecord:
    matches = tuple(
        record
        for record in records
        if record.timestamp == timestamp and record.direction == direction
    )
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one signal record for {timestamp.isoformat()} {direction}, "
            f"got {len(matches)}"
        )
    return matches[0]


def _strong_aligned_count(
    rescued: tuple[ShadowRescuedCross, ...],
    events: tuple[WorkspaceMarketEvent, ...],
    strong_windows,
) -> int:
    count = 0
    for cross in rescued:
        for window in strong_windows:
            start = events[window.start_index].timestamp
            end = events[window.end_index].timestamp
            if window.direction == cross.direction and start <= cross.timestamp <= end:
                count += 1
                break
    return count


def _profit_factor(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> float | None:
    gross_profit = sum(max(0.0, trade.final_profit) for trade in trades)
    gross_loss = -sum(min(0.0, trade.final_profit) for trade in trades)
    if gross_loss <= 0.0:
        return None
    return gross_profit / gross_loss


def _closed_pnl_drawdown(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> float:
    running = 0.0
    peak = 0.0
    maximum = 0.0
    for trade in sorted(trades, key=lambda item: item.close_timestamp):
        running += trade.final_profit
        peak = max(peak, running)
        maximum = max(maximum, peak - running)
    return maximum


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def _run_variant(criterion: str) -> ShadowVariantResult:
    frozen.assert_frozen_oos_snapshot()
    algorithm = ShadowRescueAlgorithm("RailAlgorithm", criterion)
    runtime = frozen.FrozenOosRuntime(
        frozen.frozen_oos_workspace(),
        algorithm_factory=lambda _algorithm_id: algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    events = session.events
    strong_windows = trend.strongest_non_overlapping(
        trend.price_only_trend_candidates(events)
    )
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    records = runtime.historical_signal_records_for_test()
    rescued = tuple(algorithm.shadow_source.rescued_crosses)
    assert rescued

    initial_allow = 0
    initial_starting = 0
    initial_reject_other = 0
    candidate_direct_accept = 0
    candidate_armed = 0
    candidate_structural_reject = 0
    accepted_record_timestamps: set[datetime] = set()

    for cross in rescued:
        base_reason = algorithm.rescued_base_reason.get(cross.timestamp, "")
        if base_reason in DIRECT_ALLIGATOR_ALLOW_REASONS:
            initial_allow += 1
        elif base_reason in STARTING_REASONS:
            initial_starting += 1
        else:
            initial_reject_other += 1

        record = _record_for_timestamp(records, cross.timestamp, cross.direction)
        reason = str(record.filter_reason_code or "").strip().upper()
        if record.accepted:
            candidate_direct_accept += 1
            accepted_record_timestamps.add(record.timestamp)
        elif reason == ALLIGATOR_REASON_DEFERRED_ARMED:
            candidate_armed += 1
        elif reason in STRUCTURAL_REASONS:
            candidate_structural_reject += 1

    rescued_keys = {(item.timestamp, item.direction) for item in rescued}
    release_timestamps: set[datetime] = set()
    release_count = 0
    for release in algorithm.deferred_releases:
        key = (release.original_signal_timestamp, release.direction)
        if key not in rescued_keys:
            continue
        release_count += 1
        release_timestamps.add(release.release_timestamp)
        release_record = _record_for_timestamp(
            records,
            release.release_timestamp,
            release.direction,
        )
        if release_record.accepted:
            accepted_record_timestamps.add(release.release_timestamp)
        elif (
            str(release_record.filter_reason_code or "").strip().upper()
            in STRUCTURAL_REASONS
        ):
            candidate_structural_reject += 1

    accepted_signal_records = len(accepted_record_timestamps)
    rescue_trade_signal_times = accepted_record_timestamps | release_timestamps
    all_trades = execution.trade_diagnostics()
    rescue_trades = tuple(
        trade
        for trade in all_trades
        if trade.signal_timestamp in rescue_trade_signal_times
    )
    wins = sum(trade.final_profit > 0.0 for trade in rescue_trades)
    losses = sum(trade.final_profit < 0.0 for trade in rescue_trades)
    break_even = len(rescue_trades) - wins - losses
    pnl = sum(trade.final_profit for trade in rescue_trades)
    strong_aligned = _strong_aligned_count(rescued, events, strong_windows)
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert all(cross.criterion == criterion for cross in rescued)
    assert all(cross.source_reason_code for cross in rescued)

    return ShadowVariantResult(
        criterion=criterion,
        eligible=len(rescued),
        strong_aligned=strong_aligned,
        outside_strong=len(rescued) - strong_aligned,
        initial_alligator_allow=initial_allow,
        initial_alligator_starting=initial_starting,
        initial_alligator_reject_other=initial_reject_other,
        candidate_direct_accept=candidate_direct_accept,
        candidate_armed=candidate_armed,
        candidate_structural_reject=candidate_structural_reject,
        deferred_release=release_count,
        accepted_signal_records=accepted_signal_records,
        trades=len(rescue_trades),
        wins=wins,
        losses=losses,
        break_even=break_even,
        pnl=pnl,
        profit_factor=_profit_factor(rescue_trades),
        closed_pnl_drawdown=_closed_pnl_drawdown(rescue_trades),
        portfolio_trades=summary.opened_trades,
        portfolio_net_profit=summary.net_profit,
        portfolio_profit_factor=summary.profit_factor,
        portfolio_drawdown=summary.maximum_drawdown,
        broker_execution_attempted=broker_execution_attempted,
    )


def main() -> None:
    results = tuple(_run_variant(criterion) for criterion in SHADOW_CRITERIA)

    total_eligible = sum(item.eligible for item in results)
    total_strong = sum(item.strong_aligned for item in results)
    total_outside = sum(item.outside_strong for item in results)
    assert total_eligible > 0
    assert total_eligible == total_strong + total_outside
    assert all(not item.broker_execution_attempted for item in results)

    print("Algorithm Workspace Candidate F MACD Shadow Rescue 2025 result")
    print("  mode=TEST_ONLY_SINGLE_CRITERION_SHADOW_RESCUE")
    print("  baseline_candidate_f_frozen=True")
    print("  production_macd_quality_thresholds_changed=False")
    print("  production_candidate_f_thresholds_changed=False")
    print("  frozen_thresholds=" "prominence:0.000015,distance:0.000050,angle:2.25")
    print(f"  total_single_criterion_eligible={total_eligible}")
    print(
        "  strong_trend_membership=" f"aligned:{total_strong},outside:{total_outside}"
    )
    for item in results:
        print(f"  {item.criterion.lower()}:")
        print(
            "    eligible="
            f"{item.eligible},strong_aligned:{item.strong_aligned},"
            f"outside_strong:{item.outside_strong}"
        )
        print(
            "    initial_alligator="
            f"allow:{item.initial_alligator_allow},"
            f"starting:{item.initial_alligator_starting},"
            f"reject_other:{item.initial_alligator_reject_other}"
        )
        print(
            "    candidate_f="
            f"direct_accept:{item.candidate_direct_accept},"
            f"armed:{item.candidate_armed},"
            f"release:{item.deferred_release},"
            f"structural_reject:{item.candidate_structural_reject},"
            f"accepted_records:{item.accepted_signal_records}"
        )
        print(
            "    rescue_trades="
            f"{item.trades},wins:{item.wins},losses:{item.losses},"
            f"break_even:{item.break_even},pnl:{item.pnl:+.2f},"
            f"pf:{_fmt_pf(item.profit_factor)},"
            f"closed_pnl_dd:{item.closed_pnl_drawdown:.2f}"
        )
        print(
            "    full_portfolio="
            f"trades:{item.portfolio_trades},"
            f"net:{item.portfolio_net_profit:+.2f},"
            f"pf:{_fmt_pf(item.portfolio_profit_factor)},"
            f"dd:{item.portfolio_drawdown:.2f}"
        )
    print("  completed_bars_only=True")
    print("  counterfactual_uses_future_trend_as_gate=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_MACD_SHADOW_RESCUE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
