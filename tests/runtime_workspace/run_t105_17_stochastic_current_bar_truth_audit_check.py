# -*- coding: utf-8 -*-
"""T105-17: TEST_ONLY аудит причинності Stochastic Current-Bar gate.

Один і той самий subclass та actual Candidate F WorkspaceRuntime виконують
control Replay без gate і gate-enabled Replay. Аудит доводить chronology
canonical Stochastic 14/1/3 на completed M15 events і не змінює production.
"""

from __future__ import annotations

import math
import sys
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from functools import partial
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_algorithm_workspace_replay_virtual_execution_check import (  # noqa: E402
    BrokerRequestProbe,
)
from run_t105_10_pd_35_production_regression_check import (  # noqa: E402
    PERIODS,
    PRODUCTION_PD_THRESHOLD,
    PeriodSpec,
    _workspace,
)
from run_t105_15_stochastic_entry_anatomy_check import (  # noqa: E402
    D_LENGTH,
    EPSILON,
    K_LENGTH,
    K_SMOOTHING,
    MIDLINE,
    _production_hashes,
)

from core.workspace_algorithm import (  # noqa: E402
    WorkspaceAlgorithm,
    WorkspaceSignalOutput,
    normalize_signal_output,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
)
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
)

TEST_ID = "T105-17"
FILTER_REASON = "TEST_ONLY_STOCHASTIC_CURRENT_BAR_CROSS"
CROSS_UP = "UP"
CROSS_DOWN = "DOWN"
CROSS_NONE = "NONE"
REFERENCE_REJECTIONS = {"2025": 17, "2026": 11}
EVIDENCE_ROWS_PER_PERIOD = 3


@dataclass(frozen=True, slots=True)
class GateExpectation:
    """Очікувані factual метрики gate-enabled Replay."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float
    drawdown: float


GATE_EXPECTATIONS = {
    "2025": GateExpectation(42, 30, 11, 1, 4.03, 1.5424, 3.58),
    "2026": GateExpectation(18, 15, 2, 1, 3.68, 3.7669, 1.20),
}


@dataclass(frozen=True, slots=True)
class ChronologyEvidence:
    """Незмінний causal snapshot одного factual CURRENT_BAR reject."""

    signal_timestamp: datetime
    direction: str
    previous_timestamp: datetime
    previous_k: float
    previous_d: float
    signal_k: float
    signal_d: float
    cross: str
    production_decision: str
    gate_decision: str
    future_bars_used: bool


class StochasticCurrentBarTruthAuditAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Production Candidate F із коротким TEST_ONLY causal audit gate."""

    def __init__(self, algorithm_id: str, *, gate_enabled: bool) -> None:
        super().__init__(algorithm_id)
        self.gate_enabled = gate_enabled
        self._events: deque[WorkspaceMarketEvent] = deque(maxlen=K_LENGTH)
        self._k_values: deque[float] = deque(maxlen=D_LENGTH)
        self._previous_k: float | None = None
        self._previous_d: float | None = None
        self._previous_indicator_timestamp: datetime | None = None
        self._current_event: WorkspaceMarketEvent | None = None
        self._signal_k: float | None = None
        self._signal_d: float | None = None
        self._cross_previous_k: float | None = None
        self._cross_previous_d: float | None = None
        self._cross_previous_timestamp: datetime | None = None
        self.current_cross = CROSS_NONE
        self.processed_timestamps: list[datetime] = []
        self.evaluated = 0
        self.allows = 0
        self.rejects = 0
        self.current_bar_candidates = 0
        self.evidence: list[ChronologyEvidence] = []

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        """Спочатку спожити один completed M15 bar, потім production logic."""
        assert event.timeframe == "M15"
        assert not self.processed_timestamps or (
            self.processed_timestamps[-1] < event.timestamp
        )
        self.processed_timestamps.append(event.timestamp)
        self._current_event = event
        self._update_stochastic(event)
        proposals = normalize_signal_output(super().on_market_event(event))
        return tuple(self._apply_gate(proposal) for proposal in proposals)

    def _update_stochastic(self, event: WorkspaceMarketEvent) -> None:
        """Оновити 14/1/3 виключно received completed M15 event."""
        self.current_cross = CROSS_NONE
        self._signal_k = None
        self._signal_d = None
        self._cross_previous_k = None
        self._cross_previous_d = None
        self._cross_previous_timestamp = None
        self._events.append(event)
        assert all(item.timestamp <= event.timestamp for item in self._events)
        if len(self._events) < K_LENGTH:
            return

        highest = max(float(item.high) for item in self._events)
        lowest = min(float(item.low) for item in self._events)
        width = highest - lowest
        percent_k = (
            MIDLINE
            if width <= EPSILON
            else 100.0 * (float(event.close) - lowest) / width
        )
        self._k_values.append(percent_k)
        if len(self._k_values) < D_LENGTH:
            self._previous_k = percent_k
            return

        percent_d = math.fsum(self._k_values) / D_LENGTH
        self._signal_k = percent_k
        self._signal_d = percent_d
        previous_k = self._previous_k
        previous_d = self._previous_d
        previous_timestamp = self._previous_indicator_timestamp
        if previous_k is not None and previous_d is not None:
            assert previous_timestamp is not None
            assert previous_timestamp < event.timestamp
            self._cross_previous_k = previous_k
            self._cross_previous_d = previous_d
            self._cross_previous_timestamp = previous_timestamp
            if previous_k <= previous_d + EPSILON and percent_k > percent_d + EPSILON:
                self.current_cross = CROSS_UP
            elif previous_k >= previous_d - EPSILON and percent_k < percent_d - EPSILON:
                self.current_cross = CROSS_DOWN
        self._previous_k = percent_k
        self._previous_d = percent_d
        self._previous_indicator_timestamp = event.timestamp

    def _apply_gate(
        self,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalProposal:
        """Розглядати тільки production Candidate F proposal з ALLOW."""
        if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
            return proposal

        self.evaluated += 1
        if self.current_cross == CROSS_NONE:
            self.allows += 1
            return proposal

        self.current_bar_candidates += 1
        if not self.gate_enabled:
            self.allows += 1
            return proposal

        event = self._current_event
        assert event is not None
        assert self._signal_k is not None and self._signal_d is not None
        assert self._cross_previous_k is not None
        assert self._cross_previous_d is not None
        assert self._cross_previous_timestamp is not None
        assert self.processed_timestamps[-1] == event.timestamp
        self.rejects += 1
        self.evidence.append(
            ChronologyEvidence(
                signal_timestamp=event.timestamp,
                direction=proposal.direction,
                previous_timestamp=self._cross_previous_timestamp,
                previous_k=self._cross_previous_k,
                previous_d=self._cross_previous_d,
                signal_k=self._signal_k,
                signal_d=self._signal_d,
                cross=self.current_cross,
                production_decision=proposal.filter_decision,
                gate_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
                future_bars_used=False,
            )
        )
        reason = (f"{proposal.reason}; " if proposal.reason else "") + (
            f"{FILTER_REASON}: stochastic K/D cross={self.current_cross},"
            "bars_since_cross=0"
        )
        return replace(
            proposal,
            reason=reason,
            filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
            filter_reason_code=FILTER_REASON,
        )


class TruthAuditRuntime(WorkspaceRuntime):
    """Harness, що звіряє received events із completed Replay session."""

    def __init__(self, *args, **kwargs) -> None:
        self.accepted_events: list[WorkspaceMarketEvent] = []
        self.warmup_events: list[WorkspaceMarketEvent] = []
        super().__init__(*args, **kwargs)

    def _accept_market_event(
        self,
        event: WorkspaceMarketEvent,
        *,
        origin: str,
        warmup_only: bool = False,
        advance_replay_execution: bool = True,
    ) -> None:
        session = self.replay_session
        assert session is not None
        index = len(self.accepted_events)
        assert index < len(session.events)
        assert event is session.events[index]
        assert event.timeframe == session.strategy_timeframe == "M15"
        assert not self.accepted_events or (
            self.accepted_events[-1].timestamp < event.timestamp
        )
        if not self.context.warmup_complete:
            self.warmup_events.append(event)
        self.accepted_events.append(event)
        super()._accept_market_event(
            event,
            origin=origin,
            warmup_only=warmup_only,
            advance_replay_execution=advance_replay_execution,
        )


def _algorithm_factory(
    algorithm_id: str,
    *,
    gate_enabled: bool,
) -> WorkspaceAlgorithm:
    """Створити той самий audit subclass з потрібним control switch."""
    return StochasticCurrentBarTruthAuditAlgorithm(
        algorithm_id,
        gate_enabled=gate_enabled,
    )


def _broker_execution_attempted(runtime: WorkspaceRuntime) -> bool:
    """Знайти будь-яку factual позначку broker execution у Journal."""
    return any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )


def _assert_metric(actual: float, expected: float, tolerance: float) -> None:
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance), (
        actual,
        expected,
    )


def _assert_baseline(spec: PeriodSpec, runtime: TruthAuditRuntime) -> None:
    """Звірити control run з production baseline."""
    summary = runtime.historical_summary
    assert summary is not None
    assert (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    ) == (spec.trades, spec.wins, spec.losses, spec.break_even)
    _assert_metric(summary.net_profit, spec.net, 0.005)
    _assert_metric(summary.profit_factor, spec.profit_factor, 0.00005)
    _assert_metric(summary.maximum_drawdown, spec.drawdown, 0.005)


def _assert_gate_result(spec: PeriodSpec, runtime: TruthAuditRuntime) -> None:
    """Звірити gate-enabled run з factual T105-16 result."""
    summary = runtime.historical_summary
    expected = GATE_EXPECTATIONS[spec.code]
    assert summary is not None
    assert (
        summary.opened_trades,
        summary.winning_trades,
        summary.losing_trades,
        summary.break_even_trades,
    ) == (
        expected.trades,
        expected.wins,
        expected.losses,
        expected.break_even,
    )
    _assert_metric(summary.net_profit, expected.net, 0.005)
    _assert_metric(summary.profit_factor, expected.profit_factor, 0.00005)
    _assert_metric(summary.maximum_drawdown, expected.drawdown, 0.005)


def _assert_runtime_truth(
    runtime: TruthAuditRuntime,
    broker_probe: BrokerRequestProbe,
) -> StochasticCurrentBarTruthAuditAlgorithm:
    """Підтвердити type contract, virtual execution і causal event stream."""
    session = runtime.replay_session
    algorithm = runtime.algorithm
    assert session is not None and session.completed
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    assert isinstance(algorithm, StochasticCurrentBarTruthAuditAlgorithm)
    assert runtime.replay_execution is not None
    assert tuple(runtime.accepted_events) == session.events
    assert algorithm.processed_timestamps == [
        event.timestamp for event in session.events
    ]
    assert len(runtime.warmup_events) == runtime.context.warmup_bars_required
    assert tuple(runtime.warmup_events) == session.events[: len(runtime.warmup_events)]
    assert all(
        left.timestamp < right.timestamp
        for left, right in zip(session.events, session.events[1:])
    )
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    return algorithm


def _run(spec: PeriodSpec, *, gate_enabled: bool) -> TruthAuditRuntime:
    """Виконати повний actual Replay одним TEST_ONLY harness."""
    broker_probe = BrokerRequestProbe()
    runtime = TruthAuditRuntime(
        _workspace(spec),
        algorithm_factory=partial(
            _algorithm_factory,
            gate_enabled=gate_enabled,
        ),
        broker_market_provider=broker_probe,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT == 35.0
    assert PRODUCTION_PD_THRESHOLD == 35.0
    _assert_metric(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
        EPSILON,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()
    _assert_runtime_truth(runtime, broker_probe)
    return runtime


def _summary_line(runtime: TruthAuditRuntime) -> str:
    summary = runtime.historical_summary
    assert summary is not None
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )


def _print_evidence(row: ChronologyEvidence) -> None:
    """Надрукувати один компактний chronology evidence block."""
    print(
        "      chronology_evidence="
        f"signal_timestamp:{row.signal_timestamp.isoformat()},"
        f"direction:{row.direction},"
        f"previous_completed_M15_timestamp:{row.previous_timestamp.isoformat()},"
        f"K_prev:{row.previous_k:.10f},D_prev:{row.previous_d:.10f},"
        f"signal_K:{row.signal_k:.10f},signal_D:{row.signal_d:.10f},"
        f"cross:{row.cross},"
        f"production_proposal_decision:{row.production_decision},"
        f"gate_decision:{row.gate_decision},"
        f"future_bars_used:{row.future_bars_used}"
    )


def main() -> None:
    """Запустити незалежний control/gate causality та runtime truth audit."""
    production_before = _production_hashes()
    assert K_LENGTH == 14 and K_SMOOTHING == 1 and D_LENGTH == 3

    print("T105-17 Stochastic Current-Bar Causality & Runtime Truth Audit")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  stochastic_profile=CANONICAL_REFERENCE_14_1_3")
    print("  rule=CURRENT_BAR_K_D_CROSS_REJECT")
    print("  donchian_gate_used=False")
    print("  production_profit_drawdown_threshold=35.0")

    for spec in PERIODS:
        control = _run(spec, gate_enabled=False)
        _assert_baseline(spec, control)
        control_algorithm = control.algorithm
        assert isinstance(
            control_algorithm,
            StochasticCurrentBarTruthAuditAlgorithm,
        )
        assert control_algorithm.evaluated == spec.trades
        assert control_algorithm.allows == spec.trades
        assert control_algorithm.rejects == 0
        assert (
            control_algorithm.current_bar_candidates == REFERENCE_REJECTIONS[spec.code]
        )

        gated = _run(spec, gate_enabled=True)
        _assert_gate_result(spec, gated)
        gate_algorithm = gated.algorithm
        assert isinstance(
            gate_algorithm,
            StochasticCurrentBarTruthAuditAlgorithm,
        )
        assert gate_algorithm.evaluated == spec.trades
        assert gate_algorithm.evaluated == (
            gate_algorithm.allows + gate_algorithm.rejects
        )
        assert gate_algorithm.rejects == REFERENCE_REJECTIONS[spec.code]
        assert gate_algorithm.current_bar_candidates == gate_algorithm.rejects
        assert len(gate_algorithm.evidence) == gate_algorithm.rejects
        assert all(
            row.previous_timestamp < row.signal_timestamp
            and row.production_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
            and row.gate_decision == WORKSPACE_SIGNAL_FILTER_REJECT
            and not row.future_bars_used
            and row.cross in {CROSS_UP, CROSS_DOWN}
            for row in gate_algorithm.evidence
        )

        print(f"  period={spec.code}")
        print(f"    control_gate_disabled={_summary_line(control)}")
        print(f"    gate_enabled={_summary_line(gated)}")
        print(
            f"    factual_population:{gate_algorithm.evaluated},"
            f"allows:{gate_algorithm.allows},rejects:{gate_algorithm.rejects}"
        )
        print(
            f"    warmup_completed_M15_events:"
            f"{len(gated.warmup_events)},chronology_defect:False"
        )
        for row in gate_algorithm.evidence[:EVIDENCE_ROWS_PER_PERIOD]:
            _print_evidence(row)

    assert _production_hashes() == production_before
    print("  stochastic_completed_M15_events_only=True")
    print("  previous_and_signal_bar_kd_only=True")
    print("  current_bar_cross_causal=True")
    print("  warmup_synthetic_or_future_chronology_defect=False")
    print("  production_allow_proposals_only=True")
    print("  same_subclass_control_run=True")
    print("  workspace_algorithm_type_contract=True")
    print("  virtual_replay_execution=True")
    print("  counts_are_regression_evidence_not_gate_logic=True")
    print("  production_hashes_unchanged=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("T105_17_STOCHASTIC_CURRENT_BAR_TRUTH_AUDIT=OK")


if __name__ == "__main__":
    main()
