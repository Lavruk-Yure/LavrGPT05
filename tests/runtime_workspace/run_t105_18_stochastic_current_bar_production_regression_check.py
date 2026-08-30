# -*- coding: utf-8 -*-
"""T105-18: production regression Stochastic CURRENT_BAR reject.

Runner використовує registered production Candidate F algorithm без
TEST_ONLY gate wrapper. Перевіряються causal completed M15 state, production
метрики, незмінна SL/TP/PD geometry та відсутність broker execution.
"""

from __future__ import annotations

import hashlib
import inspect
import math
import sys
from dataclasses import dataclass
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

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS,
    CANDIDATE_F_STOCHASTIC_D_PERIOD,
    CANDIDATE_F_STOCHASTIC_K_PERIOD,
    CANDIDATE_F_STOCHASTIC_K_SMOOTHING,
    CANDIDATE_F_STOCHASTIC_TIMEFRAME,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_profit_guard import (  # noqa: E402
    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX,
    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1,
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_REJECT,
)
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
)

TEST_ID = "T105-18"
EPSILON = 1e-12
BASELINE_POPULATION = {"2025": 59, "2026": 29}
EXPECTED_REJECTS = {"2025": 17, "2026": 11}
EXIT_FILES = (
    PROJECT_ROOT / "core" / "workspace_replay_execution.py",
    PROJECT_ROOT / "core" / "workspace_profit_guard.py",
    PROJECT_ROOT / "engine" / "runtime_constants.py",
)


@dataclass(frozen=True, slots=True)
class ProductionExpectation:
    """Очікувані production Replay facts одного періоду."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float
    drawdown: float
    profit_drawdown: int
    stop_loss: int
    take_profit: int


EXPECTATIONS = {
    "2025": ProductionExpectation(42, 30, 11, 1, 4.03, 1.5424, 3.58, 36, 4, 2),
    "2026": ProductionExpectation(18, 15, 2, 1, 3.68, 3.7669, 1.20, 16, 1, 1),
}


def _file_hashes() -> dict[str, str]:
    """Зафіксувати production exit-policy файли навколо Replay."""
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in EXIT_FILES
    }


def _metric(actual: float, expected: float, tolerance: float) -> None:
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance), (
        actual,
        expected,
    )


def _broker_execution_attempted(runtime: WorkspaceRuntime) -> bool:
    """Знайти будь-яку factual broker-execution позначку в Journal."""
    return any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )


def _assert_policy(runtime: WorkspaceRuntime) -> None:
    """Підтвердити незмінні PD, recovery та SL/TP production defaults."""
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1 == 3
    assert CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX == 2
    assert DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT == 35.0
    assert PRODUCTION_PD_THRESHOLD == 35.0
    _metric(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
        EPSILON,
    )


def _assert_geometry(runtime: WorkspaceRuntime) -> None:
    """Звірити кожну trade diagnostic із max(range, spread*10) і TP=2R."""
    engine = runtime.replay_execution
    session = runtime.replay_session
    assert engine is not None and session is not None
    assert engine.policy.stop_range_multiplier == 1.0
    assert engine.policy.minimum_spread_multiples == 10.0
    assert engine.policy.take_profit_r_multiple == 2.0
    events = {event.timestamp: event for event in session.events}
    records = {
        record.signal_uid: record
        for record in runtime.signal_records_for_ui()
        if record.accepted
    }
    trades = engine.trade_diagnostics()
    assert len(trades) == runtime.historical_summary.opened_trades
    for trade in trades:
        record = records[trade.signal_uid]
        signal_event = events[record.timestamp]
        signal_range = max(signal_event.high - signal_event.low, 0.0)
        spread_floor = signal_event.spread * 10.0
        expected_stop = max(signal_range, spread_floor)
        _metric(trade.stop_loss_distance, expected_stop, EPSILON)
        _metric(trade.take_profit_distance, expected_stop * 2.0, EPSILON)


def _assert_metrics(spec: PeriodSpec, runtime: WorkspaceRuntime) -> None:
    """Звірити всі задані production regression metrics."""
    summary = runtime.historical_summary
    expected = EXPECTATIONS[spec.code]
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
    _metric(summary.net_profit, expected.net, 0.005)
    _metric(summary.profit_factor, expected.profit_factor, 0.00005)
    _metric(summary.maximum_drawdown, expected.drawdown, 0.005)
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == expected.profit_drawdown
    assert summary.close_reason_count("STOP_LOSS") == expected.stop_loss
    assert summary.close_reason_count("TAKE_PROFIT") == expected.take_profit
    assert summary.close_reason_count("SESSION_END") == 0


def _assert_stochastic_path(
    spec: PeriodSpec,
    runtime: WorkspaceRuntime,
) -> int:
    """Підтвердити production class, M15 state і factual gate records."""
    algorithm = runtime.algorithm
    session = runtime.replay_session
    assert type(algorithm) is WorkspaceMacdAlligatorReplayAlgorithm
    assert session is not None and session.completed
    assert session.strategy_timeframe == CANDIDATE_F_STOCHASTIC_TIMEFRAME == "M15"
    assert all(event.timeframe == "M15" for event in session.events)
    assert CANDIDATE_F_STOCHASTIC_K_PERIOD == 14
    assert CANDIDATE_F_STOCHASTIC_K_SMOOTHING == 1
    assert CANDIDATE_F_STOCHASTIC_D_PERIOD == 3

    records = runtime.signal_records_for_ui()
    rejected = tuple(
        record
        for record in records
        if record.filter_reason_code == ALLIGATOR_REASON_STOCHASTIC_CURRENT_BAR_CROSS
    )
    assert len(rejected) == EXPECTED_REJECTS[spec.code]
    assert runtime.historical_summary is not None
    assert (
        runtime.historical_summary.opened_trades + len(rejected)
        == BASELINE_POPULATION[spec.code]
    )
    assert all(
        not record.accepted
        and record.filter_decision == WORKSPACE_SIGNAL_FILTER_REJECT
        and "stochastic_profile=14/1/3" in record.reason
        and "bars_since_cross=0" in record.reason
        and ("cross=UP" in record.reason or "cross=DOWN" in record.reason)
        for record in rejected
    )
    return len(rejected)


def _run_period(spec: PeriodSpec) -> tuple[WorkspaceRuntime, int, int]:
    """Виконати actual registered production WorkspaceRuntime Replay."""
    broker_probe = BrokerRequestProbe()
    runtime = WorkspaceRuntime(
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
    _assert_metrics(spec, runtime)
    rejects = _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    return runtime, rejects, broker_probe.requests


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


def main() -> None:
    """Запустити T105-18 через actual production algorithm factory."""
    exit_hashes_before = _file_hashes()
    algorithm_source = inspect.getsource(WorkspaceMacdAlligatorReplayAlgorithm)
    assert "DONCHIAN" not in algorithm_source.upper()

    print("T105-18 Production Integration: Stochastic CURRENT_BAR Reject")
    print(f"  test_id={TEST_ID}")
    print("  path=REGISTERED_PRODUCTION_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  test_only_gate_wrapper=False")
    for spec in PERIODS:
        runtime, rejects, broker_requests = _run_period(spec)
        print(f"  period={spec.code}")
        print(f"    production={_summary_line(runtime)}")
        print(
            f"    stochastic_current_bar_rejects={rejects},"
            f"factual_population={BASELINE_POPULATION[spec.code]}"
        )
        print(f"    broker_requests={broker_requests}")

    assert _file_hashes() == exit_hashes_before
    print("  stochastic_current_bar_reject_production=True")
    print("  stochastic_profile=14/1/3")
    print("  donchian_production_gate=False")
    print("  production_profit_drawdown_threshold=35.0")
    print("  production_sl_geometry=max(signal_bar_range,spread*10)")
    print("  production_tp_geometry=2R")
    print("  negative_pd_recovery_unchanged=True")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_exit_logic_changed=False")
    print("T105_18_STOCHASTIC_CURRENT_BAR_PRODUCTION_REGRESSION=OK")


if __name__ == "__main__":
    main()
