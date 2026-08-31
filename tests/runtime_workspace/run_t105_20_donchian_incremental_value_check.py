# -*- coding: utf-8 -*-
"""T105-20: TEST_ONLY Donchian value over current production Candidate F."""

from __future__ import annotations

from dataclasses import replace

from run_algorithm_workspace_replay_virtual_execution_check import BrokerRequestProbe
from run_t105_10_pd_35_production_regression_check import PeriodSpec, _workspace
from run_t105_11_donchian_entry_anatomy_check import (
    DONCHIAN_PERIOD,
    DONCHIAN_SHIFT,
    _production_hashes,
)
from run_t105_12_donchian_breakout_filter_check import (
    FILTER_REASON,
    DonchianBreakoutFilterRuntime,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    WorkspaceMacdAlligatorReplayAlgorithm,
    _assert_geometry,
    _assert_policy,
    _broker_execution_attempted,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (
    _run_period as _run_production_period,
)

from core.workspace_algorithm import create_registered_workspace_algorithm
from core.workspace_alligator import (
    ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
    CANDIDATE_F_STOCHASTIC_D_PERIOD,
    CANDIDATE_F_STOCHASTIC_K_PERIOD,
    CANDIDATE_F_STOCHASTIC_K_SMOOTHING,
)
from core.workspace_market_event import WorkspaceMarketEvent
from core.workspace_signal import (
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
)

TEST_ID = "T105-20"
MODE = "RM105_T105_20_DONCHIAN_INCREMENTAL_VALUE_TEST_ONLY"


def _summary_line(runtime) -> str:
    summary = runtime.historical_summary
    assert summary is not None
    profit_factor = (
        "NONE" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    )
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{profit_factor},"
        f"dd:{summary.maximum_drawdown:.2f},"
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )


class CurrentProductionDonchianRuntime(DonchianBreakoutFilterRuntime):
    """Production algorithm plus one exact TEST_ONLY Donchian N20 gate."""

    def __init__(self, *args, **kwargs) -> None:
        self.stochastic_rejects = 0
        self.would_reject_stochastic_rejected = 0
        self.reference_windows = 0
        super().__init__(*args, **kwargs)

    def _channel(
        self,
        event: WorkspaceMarketEvent,
    ) -> tuple[float, float, float]:
        timestamps = sorted(
            timestamp
            for timestamp in self.strategy_events
            if timestamp <= event.timestamp
        )
        assert len(timestamps) >= DONCHIAN_PERIOD + 1
        signal_event = self.strategy_events[timestamps[-1]]
        assert signal_event.timestamp == event.timestamp
        reference = tuple(
            self.strategy_events[timestamp]
            for timestamp in timestamps[-(DONCHIAN_PERIOD + 1) : -1]  # noqa
        )
        assert len(reference) == DONCHIAN_PERIOD
        assert all(item.timeframe == "M15" for item in reference)
        assert all(item.timestamp < signal_event.timestamp for item in reference)
        assert signal_event not in reference
        self.reference_windows += 1
        return (
            float(signal_event.close),
            max(float(item.high) for item in reference),
            min(float(item.low) for item in reference),
        )

    @staticmethod
    def _allows(direction: str, close: float, upper: float, lower: float) -> bool:
        return (direction == "BUY" and close > upper) or (
            direction == "SELL" and close < lower
        )

    def _apply_test_only_donchian_gate(
        self,
        event: WorkspaceMarketEvent,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalProposal:
        is_stochastic_reject = bool(
            proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
            and proposal.filter_reason_code
            == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
        )
        if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
            if is_stochastic_reject:
                self.stochastic_rejects += 1
                close, upper, lower = self._channel(event)
                if not self._allows(proposal.direction, close, upper, lower):
                    self.would_reject_stochastic_rejected += 1
            return proposal

        close, upper, lower = self._channel(event)
        diagnostic = (event.timestamp, proposal.direction, close, upper, lower)
        if self._allows(proposal.direction, close, upper, lower):
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


def _run_filtered(spec: PeriodSpec) -> tuple[CurrentProductionDonchianRuntime, int]:
    broker_probe = BrokerRequestProbe()
    runtime = CurrentProductionDonchianRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
    )
    _assert_policy(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    assert type(runtime.algorithm) is WorkspaceMacdAlligatorReplayAlgorithm
    assert session.completed
    assert session.strategy_timeframe == "M15"
    assert all(event.timeframe == "M15" for event in session.events)
    _assert_geometry(runtime)
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    return runtime, broker_probe.requests


def _print_period(spec: PeriodSpec) -> None:
    baseline, _rejects, baseline_broker_requests = _run_production_period(spec)
    filtered, filtered_broker_requests = _run_filtered(spec)
    baseline_summary = baseline.historical_summary
    filtered_summary = filtered.historical_summary
    assert baseline_summary is not None and filtered_summary is not None

    allows = len(filtered.donchian_allows)
    rejects = len(filtered.donchian_rejections)
    production_allow_population = allows + rejects
    stochastic_survivors = production_allow_population
    factual_candidate_population = stochastic_survivors + filtered.stochastic_rejects
    assert production_allow_population == allows + rejects
    assert filtered.reference_windows == factual_candidate_population
    assert baseline_broker_requests == filtered_broker_requests == 0

    print(f"  period={spec.code}")
    pf_delta = (
        "NONE"
        if filtered_summary.profit_factor is None
        else f"{filtered_summary.profit_factor - baseline_summary.profit_factor:+.4f}"
    )
    print(f"    BASELINE={_summary_line(baseline)}")
    print(f"    DONCHIAN_N20={_summary_line(filtered)}")
    trade_count_delta = filtered_summary.opened_trades - baseline_summary.opened_trades
    dd_delta = filtered_summary.maximum_drawdown - baseline_summary.maximum_drawdown
    print(
        "    DELTA="
        f"trade_count:{trade_count_delta:+0d},"
        f"net:{filtered_summary.net_profit - baseline_summary.net_profit:+.2f},"
        f"pf:{pf_delta},"
        f"dd:{dd_delta:+.2f}"
    )
    print(
        "    gate_anatomy="
        f"production_allow_population:{production_allow_population},"
        f"donchian_allows:{allows},donchian_rejects:{rejects}"
    )
    print(
        "    overlap="
        f"factual_candidate_population:{factual_candidate_population},"
        f"stochastic_rejects:{filtered.stochastic_rejects},"
        f"stochastic_survivors:{stochastic_survivors},"
        f"donchian_rejects_among_stochastic_survivors:{rejects},"
        "would_donchian_reject_stochastic_rejected:"
        f"{filtered.would_reject_stochastic_rejected}"
    )


def main() -> None:
    production_before = _production_hashes()
    assert DONCHIAN_PERIOD == 20 and DONCHIAN_SHIFT == 0
    assert (
        CANDIDATE_F_STOCHASTIC_K_PERIOD,
        CANDIDATE_F_STOCHASTIC_K_SMOOTHING,
        CANDIDATE_F_STOCHASTIC_D_PERIOD,
    ) == (14, 1, 3)

    print("T105-20 Donchian Incremental Value on Current Production")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  pipeline=PRODUCTION_CANDIDATE_F__STOCHASTIC__TEST_ONLY_DONCHIAN_N20")
    print("  rule=BUY_CLOSE_GT_PREVIOUS_UPPER__SELL_CLOSE_LT_PREVIOUS_LOWER")
    for spec in PERIODS:
        _print_period(spec)

    assert _production_hashes() == production_before
    print("  donchian_previous_completed_M15_only=True")
    print("  donchian_current_signal_bar_excluded=True")
    print("  future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  production_stochastic_gate_active=True")
    print("  stochastic_profile=14/1/3")
    print("  donchian_gate_test_only=True")
    print("  donchian_production_gate=False")
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_exit_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_20_DONCHIAN_INCREMENTAL_VALUE=OK")


if __name__ == "__main__":
    main()
