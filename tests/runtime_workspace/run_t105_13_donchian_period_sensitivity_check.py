# -*- coding: utf-8 -*-
"""T105-13: TEST_ONLY sensitivity Donchian Period для Candidate F entry gate.

Runner не шукає «найкращий» Period. Він перевіряє, чи causal directional
breakout rule з T105-12 лишається корисним у сусідній області 10/15/20/25/30
на незалежних actual WorkspaceRuntime Replay 2025 і 2026.
"""

from __future__ import annotations

import math
import statistics
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
    DONCHIAN_SHIFT,
    EPSILON,
    _production_hashes,
)
from run_t105_12_donchian_breakout_filter_check import (  # noqa: E402
    FILTER_REASON,
    _assert_baseline,
    _broker_execution_attempted,
    _summary_line,
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

TEST_ID = "T105-13"
DONCHIAN_PERIODS = (10, 15, 20, 25, 30)


class DonchianPeriodSensitivityRuntime(WorkspaceRuntime):
    """Actual Runtime з одним TEST_ONLY gate і заданим Donchian Period."""

    def __init__(self, *args, donchian_period: int, **kwargs) -> None:
        self.donchian_period = int(donchian_period)
        self.strategy_events: dict[datetime, WorkspaceMarketEvent] = {}
        self.donchian_rejections = 0
        self.donchian_allows = 0
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
        if len(timestamps) < self.donchian_period + 1:
            return proposal

        signal_event = self.strategy_events[timestamps[-1]]
        if signal_event.timestamp != event.timestamp:
            return proposal

        reference_timestamps = timestamps[-(self.donchian_period + 1):-1]
        reference = tuple(
            self.strategy_events[timestamp] for timestamp in reference_timestamps
        )
        assert len(reference) == self.donchian_period
        assert all(item.timeframe == self.context.timeframe for item in reference)
        assert all(item.timestamp < signal_event.timestamp for item in reference)
        assert signal_event not in reference

        upper = max(float(item.high) for item in reference)
        lower = min(float(item.low) for item in reference)
        close = float(signal_event.close)
        directional_breakout = (
            proposal.direction == "BUY" and close > upper + EPSILON
        ) or (
            proposal.direction == "SELL" and close < lower - EPSILON
        )

        if directional_breakout:
            self.donchian_allows += 1
            return proposal

        self.donchian_rejections += 1
        return replace(
            proposal,
            filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
            filter_reason_code=FILTER_REASON,
            reason=(
                f"{proposal.reason}; {FILTER_REASON}: period={self.donchian_period}, "
                f"close={close:.5f}, upper={upper:.5f}, lower={lower:.5f}"
            ).strip("; "),
        )


def _run_baseline(spec: PeriodSpec) -> WorkspaceRuntime:
    runtime = WorkspaceRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_baseline(spec, runtime)
    assert not _broker_execution_attempted(runtime)
    return runtime


def _run_filtered(
    spec: PeriodSpec,
    period: int,
) -> DonchianPeriodSensitivityRuntime:
    runtime = DonchianPeriodSensitivityRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        donchian_period=period,
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
    assert runtime.donchian_allows > 0
    assert runtime.donchian_rejections > 0
    assert not _broker_execution_attempted(runtime)
    return runtime


def _metric_tuple(runtime: WorkspaceRuntime) -> tuple[float, float, float]:
    summary = runtime.historical_summary
    assert summary is not None
    return summary.net_profit, summary.profit_factor, summary.maximum_drawdown


def main() -> None:
    production_before = _production_hashes()

    print("T105-13 Candidate F Donchian Period Sensitivity result")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  production_profit_drawdown_threshold=35.0")
    print("  donchian_periods=10,15,20,25,30")
    print("  donchian_period_selection_goal=STABILITY_NOT_BEST_FIT")
    print(f"  donchian_shift={DONCHIAN_SHIFT}")
    print("  reference_bars=previous_N_completed_M15")
    print("  current_signal_bar_excluded=True")
    print("  rule=BUY_CLOSE_GT_PREVIOUS_UPPER__SELL_CLOSE_LT_PREVIOUS_LOWER")
    print("  inside_action=REJECT")
    print("  full_independent_filtered_replay=True")

    baselines = {spec.code: _run_baseline(spec) for spec in PERIODS}
    print("  baselines")
    for spec in PERIODS:
        print(f"    period={spec.code} {_summary_line(baselines[spec.code])}")

    cross_period: dict[int, tuple[float, float, float]] = {}
    for period in DONCHIAN_PERIODS:
        print(f"  donchian_period={period}")
        period_metrics: list[tuple[float, float, float]] = []
        for spec in PERIODS:
            runtime = _run_filtered(spec, period)
            summary = runtime.historical_summary
            assert summary is not None
            period_metrics.append(_metric_tuple(runtime))
            print(f"    period={spec.code} filtered={_summary_line(runtime)}")
            print(
                f"      donchian_gate=allows:{runtime.donchian_allows},"
                f"rejections:{runtime.donchian_rejections},"
                f"evaluated:{runtime.donchian_allows + runtime.donchian_rejections}"
            )
            print(
                f"      delta=trades:{summary.opened_trades - spec.trades:+d},"
                f"net:{summary.net_profit - spec.net:+.2f},"
                f"pf:{summary.profit_factor - spec.profit_factor:+.4f},"
                f"dd:{summary.maximum_drawdown - spec.drawdown:+.2f}"
            )

        combined_net = math.fsum(metric[0] for metric in period_metrics)
        mean_pf = statistics.fmean(metric[1] for metric in period_metrics)
        worst_dd = max(metric[2] for metric in period_metrics)
        cross_period[period] = combined_net, mean_pf, worst_dd

    print("  cross_period_summary")
    for period in DONCHIAN_PERIODS:
        combined_net, mean_pf, worst_dd = cross_period[period]
        print(
            f"    N={period},combined_net:{combined_net:+.2f},"
            f"mean_pf:{mean_pf:.4f},worst_dd:{worst_dd:.2f}"
        )

    assert _production_hashes() == production_before
    print("  production_files_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_13_DONCHIAN_PERIOD_SENSITIVITY=OK")


if __name__ == "__main__":
    main()
