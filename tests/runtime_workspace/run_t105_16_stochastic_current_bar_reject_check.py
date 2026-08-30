# -*- coding: utf-8 -*-
"""T105-16: TEST_ONLY Stochastic Current-Bar Cross Reject prototype.

Runner виконує незалежні actual WorkspaceRuntime Replay baseline і filtered
для 2025 та 2026 з production PD=35%. Єдине TEST_ONLY правило відхиляє
Candidate F entry, якщо causal Stochastic 14/1/3 K/D cross стався саме на
поточному completed M15 signal bar. Усі інші Stochastic states дозволені.

Donchian та будь-які zone, slope, K/D або distance-to-50 thresholds не
використовуються. Production-файли та production-логіка не змінюються.
"""

from __future__ import annotations

import math
import sys
from collections import deque
from dataclasses import replace
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
    create_registered_workspace_algorithm,
    normalize_signal_output,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX,
    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1,
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

TEST_ID = "T105-16"
FILTER_REASON = "TEST_ONLY_STOCHASTIC_CURRENT_BAR_CROSS"
CROSS_UP = "UP"
CROSS_DOWN = "DOWN"
CROSS_NONE = "NONE"
REFERENCE_REJECTIONS = {"2025": 17, "2026": 11}


class StochasticCurrentBarGateAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Production Candidate F з вузьким TEST_ONLY Stochastic gate."""

    def __init__(self, algorithm_id: str) -> None:
        super().__init__(algorithm_id)
        self._events: deque[WorkspaceMarketEvent] = deque(maxlen=K_LENGTH)
        self._k_values: deque[float] = deque(maxlen=D_LENGTH)
        self._previous_k: float | None = None
        self._previous_d: float | None = None
        self.current_cross = CROSS_NONE
        self.evaluated = 0
        self.allows = 0
        self.rejects = 0

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        """Оновити causal Stochastic та застосувати єдине правило до entry."""
        self._update_stochastic(event)
        output = super().on_market_event(event)
        proposals = normalize_signal_output(output)
        return tuple(self._apply_gate(proposal) for proposal in proposals)

    def _update_stochastic(self, event: WorkspaceMarketEvent) -> None:
        """Оновити canonical 14/1/3 лише поточним completed M15 bar."""
        assert event.timeframe == "M15"
        self.current_cross = CROSS_NONE
        self._events.append(event)
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
        previous_k = self._previous_k
        previous_d = self._previous_d
        if previous_k is not None and previous_d is not None:
            if (
                previous_k <= previous_d + EPSILON
                and percent_k > percent_d + EPSILON
            ):
                self.current_cross = CROSS_UP
            elif (
                previous_k >= previous_d - EPSILON
                and percent_k < percent_d - EPSILON
            ):
                self.current_cross = CROSS_DOWN
        self._previous_k = percent_k
        self._previous_d = percent_d

    def _apply_gate(
        self,
        proposal: WorkspaceSignalProposal,
    ) -> WorkspaceSignalProposal:
        """Відхилити лише entry із K/D cross age == CURRENT_BAR."""
        is_candidate_entry = bool(
            proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
        )
        if not is_candidate_entry:
            return proposal

        self.evaluated += 1
        if self.current_cross == CROSS_NONE:
            self.allows += 1
            return proposal

        self.rejects += 1
        reason = (
            f"{proposal.reason}; " if proposal.reason else ""
        ) + (
            f"{FILTER_REASON}: stochastic K/D cross={self.current_cross},"
            "bars_since_cross=0"
        )
        return replace(
            proposal,
            reason=reason,
            filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
            filter_reason_code=FILTER_REASON,
        )


def _filtered_algorithm_factory(algorithm_id: str) -> WorkspaceAlgorithm:
    """Створити production Candidate F з TEST_ONLY prototype gate."""
    return StochasticCurrentBarGateAlgorithm(algorithm_id)


def _assert_production_policy(runtime: WorkspaceRuntime) -> None:
    """Підтвердити незмінний production PD=35% і Candidate F guard."""
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT == 35.0
    assert PRODUCTION_PD_THRESHOLD == 35.0
    assert CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1 == 3
    assert CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX == 2
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )


def _complete_replay(runtime: WorkspaceRuntime) -> None:
    """Завершити actual WorkspaceRuntime Replay без broker requests."""
    _assert_production_policy(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()


def _assert_baseline(spec: PeriodSpec, runtime: WorkspaceRuntime) -> None:
    """Звірити production baseline однаковими незмінними метриками."""
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


def _broker_execution_attempted(runtime: WorkspaceRuntime) -> bool:
    """Перевірити Journal на будь-яку спробу broker execution."""
    return any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )


def _summary_line(summary) -> str:
    """Повернути однаковий набір метрик baseline або filtered."""
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


def _run_period(spec: PeriodSpec) -> tuple[int, int, int]:
    """Виконати незалежні baseline і filtered Replay одного періоду."""
    baseline_runtime = WorkspaceRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    _complete_replay(baseline_runtime)
    _assert_baseline(spec, baseline_runtime)
    baseline = baseline_runtime.historical_summary
    assert baseline is not None
    assert not _broker_execution_attempted(baseline_runtime)

    filtered_runtime = WorkspaceRuntime(
        _workspace(spec),
        algorithm_factory=_filtered_algorithm_factory,
    )
    _complete_replay(filtered_runtime)
    filtered = filtered_runtime.historical_summary
    assert filtered is not None
    assert not _broker_execution_attempted(filtered_runtime)

    gate = filtered_runtime.algorithm
    assert isinstance(gate, StochasticCurrentBarGateAlgorithm)
    assert gate.evaluated == gate.allows + gate.rejects
    assert gate.evaluated == spec.trades, (
        spec.code,
        gate.allows,
        gate.rejects,
        gate.evaluated,
        filtered.opened_trades,
    )
    assert gate.rejects == REFERENCE_REJECTIONS[spec.code], (
        spec.code,
        gate.rejects,
    )
    assert filtered.opened_trades == gate.allows

    print(f"  period={spec.code}")
    print(f"    baseline={_summary_line(baseline)}")
    print(f"    filtered={_summary_line(filtered)}")
    print(
        f"    stochastic_gate=allows:{gate.allows},rejects:{gate.rejects},"
        f"evaluated:{gate.evaluated}"
    )
    print(
        f"    delta=trades:{filtered.opened_trades - baseline.opened_trades:+d},"
        f"net:{filtered.net_profit - baseline.net_profit:+.2f},"
        f"pf:{filtered.profit_factor - baseline.profit_factor:+.4f},"
        f"dd:{filtered.maximum_drawdown - baseline.maximum_drawdown:+.2f}"
    )
    return gate.allows, gate.rejects, gate.evaluated


def main() -> None:
    """Запустити T105-16 без додаткових Stochastic або Donchian rules."""
    production_before = _production_hashes()
    assert K_SMOOTHING == 1

    print("T105-16 Candidate F Stochastic Current-Bar Reject result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  production_profit_drawdown_threshold=35.0")
    print("  stochastic_profile=CANONICAL_REFERENCE_14_1_3")
    print("  signal_bar=CAUSAL_COMPLETED_M15")
    print("  rule=CROSS_AGE_EQ_CURRENT_BAR_REJECT__ALL_OTHER_STATES_ALLOW")
    print("  full_independent_filtered_replay=True")
    print("  donchian_gate_used=False")
    print("  whitelist_1_2_bars_used=False")
    print("  zone_threshold_used=False")
    print("  slope_threshold_used=False")
    print("  percent_k_d_threshold_used=False")
    print("  distance_50_threshold_used=False")

    results = {
        spec.code: _run_period(spec)
        for spec in PERIODS
    }
    assert _production_hashes() == production_before

    print(
        "  current_bar_reject_count_check="
        + ",".join(
            f"{spec.code}:{results[spec.code][1]}"
            for spec in PERIODS
        )
    )
    print("  production_hashes_unchanged=True")
    print("  production_files_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_16_STOCHASTIC_CURRENT_BAR_REJECT=OK")


if __name__ == "__main__":
    main()
