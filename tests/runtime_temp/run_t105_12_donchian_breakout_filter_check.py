# -*- coding: utf-8 -*-
"""T105-12: TEST_ONLY Donchian directional breakout entry filter.

Runner порівнює production-equivalent Candidate F baseline з окремим full Replay,
де TEST_ONLY gate дозволяє BUY лише вище Upper та SELL лише нижче Lower каналу
Donchian, побудованого за попередніми 20 завершеними M15 bars. Поточний signal
bar не входить до reference channel. Production-код і production-рішення не
змінюються.
"""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_10_pd_35_production_regression_check import (  # noqa: E402
    PERIODS,
    PRODUCTION_PD_THRESHOLD,
    PeriodSpec,
    _workspace,
)
from run_t105_11_donchian_entry_anatomy_check import (  # noqa: E402
    DONCHIAN_PERIOD,
    EPSILON,
    _production_hashes,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
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

TEST_ID = "T105-12"
FILTER_REASON = "TEST_ONLY_DONCHIAN_DIRECTIONAL_BREAKOUT_REQUIRED"


class DonchianBreakoutFilterRuntime(WorkspaceRuntime):
    """Actual Runtime з одним TEST_ONLY causal Donchian entry gate."""

    def __init__(self, *args, **kwargs) -> None:
        self.strategy_events: dict[datetime, WorkspaceMarketEvent] = {}
        self.donchian_rejections: list[tuple[datetime, str, float, float, float]] = []
        self.donchian_allows: list[tuple[datetime, str, float, float, float]] = []
        super().__init__(*args, **kwargs)

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
        proposal = self._apply_test_only_donchian_gate(event, proposal)
        return super()._record_signal(event, proposal)

    def _apply_test_only_donchian_gate(
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
        if len(timestamps) < DONCHIAN_PERIOD + 1:
            return proposal

        signal_event = self.strategy_events[timestamps[-1]]
        if signal_event.timestamp != event.timestamp:
            return proposal

        reference_timestamps = timestamps[-(DONCHIAN_PERIOD + 1) : -1]  # noqa
        reference = tuple(
            self.strategy_events[timestamp] for timestamp in reference_timestamps
        )
        assert len(reference) == DONCHIAN_PERIOD
        assert all(item.timeframe == self.context.timeframe for item in reference)
        assert all(item.timestamp < signal_event.timestamp for item in reference)
        assert signal_event not in reference

        upper = max(float(item.high) for item in reference)
        lower = min(float(item.low) for item in reference)
        close = float(signal_event.close)

        directional_breakout = (
            proposal.direction == "BUY" and close > upper + EPSILON
        ) or (proposal.direction == "SELL" and close < lower - EPSILON)

        diagnostic = (
            event.timestamp,
            proposal.direction,
            close,
            upper,
            lower,
        )
        if directional_breakout:
            self.donchian_allows.append(diagnostic)
            return proposal

        self.donchian_rejections.append(diagnostic)
        return replace(
            proposal,
            filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
            filter_reason_code=FILTER_REASON,
            reason=(
                f"{proposal.reason}; {FILTER_REASON}: "
                f"close={close:.5f}, upper={upper:.5f}, lower={lower:.5f}"
            ).strip("; "),
        )


def _broker_execution_attempted(runtime: WorkspaceRuntime) -> bool:
    return any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )


def _summary_line(runtime: WorkspaceRuntime) -> str:
    summary = runtime.historical_summary
    assert summary is not None
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f},"
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )


def _run_runtime(spec: PeriodSpec, *, filtered: bool) -> WorkspaceRuntime:
    runtime_class = DonchianBreakoutFilterRuntime if filtered else WorkspaceRuntime
    runtime = runtime_class(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    assert runtime.historical_summary is not None
    assert not _broker_execution_attempted(runtime)
    return runtime


def _assert_baseline(spec: PeriodSpec, runtime: WorkspaceRuntime) -> None:
    summary = runtime.historical_summary
    assert summary is not None
    assert summary.opened_trades == spec.trades
    assert summary.winning_trades == spec.wins
    assert summary.losing_trades == spec.losses
    assert summary.break_even_trades == spec.break_even
    assert math.isclose(summary.net_profit, spec.net, rel_tol=0.0, abs_tol=0.005)
    assert math.isclose(
        summary.profit_factor,
        spec.profit_factor,
        rel_tol=0.0,
        abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown,
        spec.drawdown,
        rel_tol=0.0,
        abs_tol=0.005,
    )
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == spec.profit_drawdown_closes
    assert summary.close_reason_count("STOP_LOSS") == spec.stop_loss_closes
    assert summary.close_reason_count("TAKE_PROFIT") == spec.take_profit_closes
    assert summary.close_reason_count("SESSION_END") == 0


def _run_period(spec: PeriodSpec) -> None:
    baseline = _run_runtime(spec, filtered=False)
    _assert_baseline(spec, baseline)

    filtered = _run_runtime(spec, filtered=True)
    assert isinstance(filtered, DonchianBreakoutFilterRuntime)
    filtered_summary = filtered.historical_summary
    assert filtered_summary is not None

    accepted = len(filtered.donchian_allows)
    rejected = len(filtered.donchian_rejections)
    assert accepted > 0
    assert rejected > 0
    assert accepted + rejected > filtered_summary.opened_trades

    print(f"  period={spec.code}")
    print(f"    baseline={_summary_line(baseline)}")
    print(f"    filtered={_summary_line(filtered)}")
    print(
        f"    donchian_gate=allows:{accepted},rejections:{rejected},"
        f"evaluated:{accepted + rejected}"
    )
    print(
        f"    delta=trades:{filtered_summary.opened_trades - spec.trades:+d},"
        f"net:{filtered_summary.net_profit - spec.net:+.2f},"
        f"pf:{filtered_summary.profit_factor - spec.profit_factor:+.4f},"
        f"dd:{filtered_summary.maximum_drawdown - spec.drawdown:+.2f}"
    )


def main() -> None:
    production_before = _production_hashes()

    print("T105-12 Candidate F Donchian Breakout Filter result")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  production_profit_drawdown_threshold=35.0")
    print("  donchian_period=20_reference_not_universal_constant")
    print("  donchian_shift=0")
    print("  reference_bars=previous_20_completed_M15")
    print("  current_signal_bar_excluded=True")
    print("  rule=BUY_CLOSE_GT_PREVIOUS_UPPER__SELL_CLOSE_LT_PREVIOUS_LOWER")
    print("  inside_action=REJECT")
    print("  full_independent_replay=True")

    for spec in PERIODS:
        _run_period(spec)

    assert _production_hashes() == production_before
    print("  production_files_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_12_DONCHIAN_BREAKOUT_FILTER=OK")


if __name__ == "__main__":
    main()
