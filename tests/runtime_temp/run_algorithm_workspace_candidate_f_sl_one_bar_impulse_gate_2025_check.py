# -*- coding: utf-8 -*-
"""RoadMap103 / 7D: test-only causal gate для one-bar impulse dominance.

Runner повторює production Candidate F Replay 2025 після 6K negative-PD recovery,
але лише в test-only Runtime відхиляє ALLOW-сигнал, якщо остання завершена M15
створила весь 30-хвилинний спрямований close-to-close рух і закрилася біля
екстремуму сигнальної свічки. Production-код, профілі, SL/TP та exit policy не
змінюються. Gate використовує тільки signal bar і дві попередні завершені M15.
"""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
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
    WorkspaceSignalRecord,
)

BASELINE_TRADES = 59
BASELINE_WINS = 40
BASELINE_LOSSES = 18
BASELINE_BREAK_EVEN = 1
BASELINE_STOP_LOSSES = 9
BASELINE_NET = -4.05
BASELINE_PROFIT_FACTOR = 0.7808
BASELINE_DRAWDOWN = 5.80

EXPECTED_GATED_TRADES = 49
EXPECTED_GATED_WINS = 36
EXPECTED_GATED_LOSSES = 12
EXPECTED_GATED_BREAK_EVEN = 1
EXPECTED_GATED_STOP_LOSSES = 4
EXPECTED_GATED_NET = 4.58
EXPECTED_GATED_PROFIT_FACTOR = 1.5776
EXPECTED_GATED_DRAWDOWN = 2.55
EXPECTED_GATE_REJECTIONS = 10

GATE_SHARE30_THRESHOLD = 1.00
GATE_CLOSE_LOCATION_THRESHOLD = 0.90
EPSILON = 1e-12


def _directional_delta(direction: str, newer: float, older: float) -> float:
    if direction == "BUY":
        return newer - older
    return older - newer


def _directional_close_location(
    direction: str,
    event: WorkspaceMarketEvent,
) -> float:
    width = max(event.high - event.low, EPSILON)
    if direction == "BUY":
        return (event.close - event.low) / width
    return (event.high - event.close) / width


class OneBarImpulseGateRuntime(WorkspaceRuntime):
    """Test-only Runtime з causal 7D gate перед risk/execution."""

    def __init__(self, *args, **kwargs) -> None:
        self.strategy_events: dict[datetime, WorkspaceMarketEvent] = {}
        self.gate_rejections: list[tuple[datetime, str, float, float]] = []
        super().__init__(*args, **kwargs)

    @property
    def historical_signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Повернути immutable snapshot історичних записів сигналів для тесту."""
        return tuple(self._historical_signal_records)

    def _accept_market_event(
        self,
        event: WorkspaceMarketEvent,
        *,
        origin: str,
        warmup_only: bool = False,
        advance_replay_execution: bool = True,
    ) -> None:
        if event.timeframe == self.context.timeframe:
            self.strategy_events[event.timestamp] = event
        super()._accept_market_event(
            event,
            origin=origin,
            warmup_only=warmup_only,
            advance_replay_execution=advance_replay_execution,
        )

    def _record_signal(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalRecord:
        proposal = self._apply_test_only_gate(event, proposal)
        return super()._record_signal(event, proposal)

    def _apply_test_only_gate(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalProposal:
        if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
            return proposal

        timestamps = sorted(
            timestamp
            for timestamp in self.strategy_events
            if timestamp <= event.timestamp
        )
        if len(timestamps) < 3:
            return proposal
        signal_event = self.strategy_events[timestamps[-1]]
        previous_1 = self.strategy_events[timestamps[-2]]
        previous_2 = self.strategy_events[timestamps[-3]]
        if signal_event.timestamp != event.timestamp:
            return proposal

        current_move = _directional_delta(
            proposal.direction,
            signal_event.close,
            previous_1.close,
        )
        previous_move = _directional_delta(
            proposal.direction,
            previous_1.close,
            previous_2.close,
        )
        net_30m = current_move + previous_move
        if net_30m > EPSILON:
            share_30 = current_move / net_30m
        else:
            share_30 = math.inf
        close_location = _directional_close_location(
            proposal.direction,
            signal_event,
        )

        if not (
            share_30 >= GATE_SHARE30_THRESHOLD
            and close_location >= GATE_CLOSE_LOCATION_THRESHOLD
        ):
            return proposal

        self.gate_rejections.append(
            (
                event.timestamp,
                proposal.direction,
                share_30,
                close_location,
            )
        )
        return replace(
            proposal,
            filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
            filter_reason_code="TEST_ONLY_ONE_BAR_IMPULSE_DOMINANCE",
            reason=(
                f"{proposal.reason}; TEST_ONLY_ONE_BAR_IMPULSE_DOMINANCE: "
                f"share30={share_30:.3f}, close_location={close_location:.3f}"
            ).strip("; "),
        )


def _close_enough(actual: float, expected: float, tolerance: float = 0.005) -> bool:
    return abs(float(actual) - float(expected)) <= tolerance


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def main() -> None:
    """Запустити один causal counterfactual Replay з 7D test-only gate."""
    assert_frozen_oos_snapshot()
    runtime = OneBarImpulseGateRuntime(
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

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    assert summary.opened_trades == EXPECTED_GATED_TRADES
    assert summary.winning_trades == EXPECTED_GATED_WINS
    assert summary.losing_trades == EXPECTED_GATED_LOSSES
    assert summary.break_even_trades == EXPECTED_GATED_BREAK_EVEN
    assert summary.close_reason_count("STOP_LOSS") == EXPECTED_GATED_STOP_LOSSES
    assert _close_enough(summary.net_profit, EXPECTED_GATED_NET)
    assert summary.profit_factor is not None
    assert _close_enough(
        summary.profit_factor,
        EXPECTED_GATED_PROFIT_FACTOR,
        0.00005,
    )
    assert _close_enough(summary.maximum_drawdown, EXPECTED_GATED_DRAWDOWN)
    assert len(runtime.gate_rejections) == EXPECTED_GATE_REJECTIONS

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    rejected_records = tuple(
        record
        for record in runtime.historical_signal_records
        if record.filter_reason_code == "TEST_ONLY_ONE_BAR_IMPULSE_DOMINANCE"
    )
    assert len(rejected_records) == len(runtime.gate_rejections)
    assert all(not record.accepted for record in rejected_records)

    print("Algorithm Workspace Candidate F SL One-Bar Impulse Gate 2025 result")
    print("  mode=TEST_ONLY_CAUSAL_ONE_BAR_IMPULSE_GATE")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  alternative_stop_applied=False")
    print("  exit_recovery_policy_preserved=True")
    print("  future_price_used_as_gate=False")
    print(
        "  gate="
        f"share30>={GATE_SHARE30_THRESHOLD:.2f}_AND_"
        f"close_location>={GATE_CLOSE_LOCATION_THRESHOLD:.2f}"
    )
    print(
        "  baseline="
        f"trades:{BASELINE_TRADES},wins:{BASELINE_WINS},"
        f"losses:{BASELINE_LOSSES},break_even:{BASELINE_BREAK_EVEN},"
        f"sl:{BASELINE_STOP_LOSSES},net:{BASELINE_NET:+.2f},"
        f"pf:{BASELINE_PROFIT_FACTOR:.4f},dd:{BASELINE_DRAWDOWN:.2f}"
    )
    print(
        "  gated="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"sl:{summary.close_reason_count('STOP_LOSS')},"
        f"net:{summary.net_profit:+.2f},pf:{_fmt_pf(summary.profit_factor)},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(f"  gate_rejections={len(runtime.gate_rejections)}")
    print("  chronological_gate_rejections:")
    for index, (timestamp, direction, share_30, close_location) in enumerate(
        runtime.gate_rejections,
        start=1,
    ):
        share_text = "INF" if not math.isfinite(share_30) else f"{share_30:.3f}"
        print(
            f"    {index:02d}. {timestamp.isoformat()} {direction} "
            f"share30:{share_text} close_location:{close_location:.3f}"
        )
    print("  completed_bars_only=True")
    print("  causal_signal_and_two_prior_M15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_ONE_BAR_IMPULSE_GATE_2025_CHECK=OK")


if __name__ == "__main__":
    main()
