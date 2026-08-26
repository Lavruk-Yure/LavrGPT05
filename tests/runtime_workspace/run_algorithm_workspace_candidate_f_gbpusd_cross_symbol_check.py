# -*- coding: utf-8 -*-
"""RoadMap103 / 7X: Candidate F cross-symbol diagnostic для GBPUSD.

Перевірка запускає production Candidate F без tuning на cTrader GBPUSD M1:
повний 2025 рік і 2026 до спільного завершеного часу 2026-08-25 15:07 UTC.
EURUSD reference за ті самі production settings зафіксований окремо лише для
порівняння. Performance не є PASS-критерієм: runner фіксує deterministic
snapshot, causal Replay і відсутність broker execution.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_DATA_MODE_REPLAY,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
    new_workspace_indicator_profile_bindings,
)
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    WORKSPACE_REPLAY_SOURCE_CSV,
    resolve_forex_pip_size,
    resolve_new_workspace_macd_extremum_min_prominence,
    resolve_new_workspace_macd_extremum_to_cross_min_distance,
    resolve_workspace_history_default_spread,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
)

SYMBOL = "GBPUSD"
SOURCE_BROKER = "CTRADER"
SPREAD_LIMIT_PIPS = 2.0


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """Один фіксований cross-symbol Replay period."""

    label: str
    file_name: str
    start_utc: str
    end_utc: str


@dataclass(frozen=True, slots=True)
class RunMetrics:
    """Deterministic metrics одного production Candidate F Replay."""

    signals: int
    alligator_allow: int
    alligator_reject: int
    trades: int
    wins: int
    losses: int
    break_even: int
    stop_losses: int
    take_profits: int
    profit_drawdown_closes: int
    net_profit: float
    profit_factor: float
    maximum_drawdown: float
    recovery_started: int
    recovery_closes: int
    early_abort_closes: int
    timeout_closes: int


WINDOWS = (
    ReplayWindow(
        label="2025",
        file_name="2025-01-01_2025-12-31_CTRADER_GBPUSD_M1.csv",
        start_utc="2025-01-01T22:01:00+00:00",
        end_utc="2025-12-31T21:58:00+00:00",
    ),
    ReplayWindow(
        label="2026_TO_2026-08-25_15:07",
        file_name="2026-01-01_2026-08-25_CTRADER_GBPUSD_M1.csv",
        start_utc="2026-01-01T22:01:00+00:00",
        end_utc="2026-08-25T15:07:00+00:00",
    ),
)

EXPECTED_GBPUSD = {
    "2025": RunMetrics(
        signals=3072,
        alligator_allow=92,
        alligator_reject=452,
        trades=92,
        wins=61,
        losses=28,
        break_even=3,
        stop_losses=13,
        take_profits=0,
        profit_drawdown_closes=79,
        net_profit=-12.83,
        profit_factor=0.5701842546066671,
        maximum_drawdown=16.05,
        recovery_started=28,
        recovery_closes=13,
        early_abort_closes=6,
        timeout_closes=9,
    ),
    "2026_TO_2026-08-25_15:07": RunMetrics(
        signals=1953,
        alligator_allow=58,
        alligator_reject=285,
        trades=58,
        wins=38,
        losses=20,
        break_even=0,
        stop_losses=9,
        take_profits=0,
        profit_drawdown_closes=49,
        net_profit=-11.47,
        profit_factor=0.4660148975793066,
        maximum_drawdown=12.83,
        recovery_started=22,
        recovery_closes=10,
        early_abort_closes=5,
        timeout_closes=6,
    ),
}

EURUSD_REFERENCE = {
    "2025": RunMetrics(
        signals=3042,
        alligator_allow=59,
        alligator_reject=357,
        trades=59,
        wins=40,
        losses=18,
        break_even=1,
        stop_losses=9,
        take_profits=2,
        profit_drawdown_closes=48,
        net_profit=-4.05,
        profit_factor=0.7808441558444823,
        maximum_drawdown=5.80,
        recovery_started=18,
        recovery_closes=9,
        early_abort_closes=5,
        timeout_closes=4,
    ),
    "2026_TO_2026-08-25_15:07": RunMetrics(
        signals=1962,
        alligator_allow=29,
        alligator_reject=154,
        trades=29,
        wins=23,
        losses=5,
        break_even=1,
        stop_losses=2,
        take_profits=0,
        profit_drawdown_closes=27,
        net_profit=1.37,
        profit_factor=1.2518382352948338,
        maximum_drawdown=3.53,
        recovery_started=6,
        recovery_closes=3,
        early_abort_closes=0,
        timeout_closes=3,
    ),
}


def _candidate_bindings() -> dict[str, dict[str, object]]:
    """Повернути frozen Candidate F indicator bindings."""
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def _workspace(window: ReplayWindow) -> AlgorithmWorkspace:
    """Створити production-equivalent GBPUSD Candidate F Replay WSP."""
    history_file = (
        PROJECT_ROOT
        / "data"
        / "history"
        / SOURCE_BROKER
        / SYMBOL
        / "M1"
        / window.file_name
    )
    assert history_file.is_file(), history_file

    pip_size = resolve_forex_pip_size(SYMBOL)
    return AlgorithmWorkspace.create(
        broker=SOURCE_BROKER,
        account_id=None,
        account_mode=None,
        symbol=SYMBOL,
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name=f"RM103 7X Candidate F {SYMBOL} {window.label}",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": (
                WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME
            ),
            "spread_limit": SPREAD_LIMIT_PIPS * pip_size,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": (
                resolve_new_workspace_macd_extremum_min_prominence(SYMBOL)
            ),
            "macd_extremum_to_cross_min_distance": (
                resolve_new_workspace_macd_extremum_to_cross_min_distance(SYMBOL)
            ),
            "macd_cross_min_angle": 45.0,
            "macd_cross_angle_model": "ABC_REALTIME_SCALED",
            "macd_cross_min_abc_angle": 2.25,
        },
        risk_settings={
            "risk_percent": 0.5,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
        profit_protection={
            "enabled": True,
            "activation_mode": "AFTER_SPREAD",
            "max_profit_drawdown_percent": 30.0,
            "minimum_profit": 0.0,
        },
        replay_settings={
            "source_type": WORKSPACE_REPLAY_SOURCE_CSV,
            "file_path": str(history_file),
            "start_utc": window.start_utc,
            "end_utc": window.end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": resolve_workspace_history_default_spread(SYMBOL),
            "source": history_file.stem,
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=_candidate_bindings(),
    )


def _run(window: ReplayWindow) -> RunMetrics:
    """Виконати один completed Historical Replay."""
    runtime = WorkspaceRuntime(
        _workspace(window),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    guard = runtime.profit_drawdown_guard
    assert isinstance(guard, WorkspaceCandidateFNegativePdRecoveryGuard)

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    assert summary.symbol == SYMBOL
    assert summary.timeframe == "M15"
    assert summary.source_timeframe == "M1"

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert not guard.pending

    profit_factor = summary.profit_factor
    assert profit_factor is not None
    return RunMetrics(
        signals=summary.signals.total,
        alligator_allow=summary.signals.alligator_allow,
        alligator_reject=summary.signals.alligator_reject,
        trades=summary.opened_trades,
        wins=summary.winning_trades,
        losses=summary.losing_trades,
        break_even=summary.break_even_trades,
        stop_losses=summary.close_reason_count("STOP_LOSS"),
        take_profits=summary.close_reason_count("TAKE_PROFIT"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        net_profit=summary.net_profit,
        profit_factor=profit_factor,
        maximum_drawdown=summary.maximum_drawdown,
        recovery_started=len(guard.started_position_ids),
        recovery_closes=len(guard.recovery_close_ids),
        early_abort_closes=len(guard.early_abort_close_ids),
        timeout_closes=len(guard.timeout_close_ids),
    )


def _assert_snapshot(actual: RunMetrics, expected: RunMetrics) -> None:
    """Перевірити deterministic snapshot без performance PASS criterion."""
    assert actual.signals == expected.signals
    assert actual.alligator_allow == expected.alligator_allow
    assert actual.alligator_reject == expected.alligator_reject
    assert actual.trades == expected.trades
    assert actual.wins == expected.wins
    assert actual.losses == expected.losses
    assert actual.break_even == expected.break_even
    assert actual.stop_losses == expected.stop_losses
    assert actual.take_profits == expected.take_profits
    assert actual.profit_drawdown_closes == expected.profit_drawdown_closes
    assert math.isclose(actual.net_profit, expected.net_profit, abs_tol=0.005)
    assert math.isclose(
        actual.profit_factor,
        expected.profit_factor,
        abs_tol=0.00005,
    )
    assert math.isclose(
        actual.maximum_drawdown,
        expected.maximum_drawdown,
        abs_tol=0.005,
    )
    assert actual.recovery_started == expected.recovery_started
    assert actual.recovery_closes == expected.recovery_closes
    assert actual.early_abort_closes == expected.early_abort_closes
    assert actual.timeout_closes == expected.timeout_closes


def _fmt(metrics: RunMetrics) -> str:
    return (
        f"trades:{metrics.trades},wins:{metrics.wins},losses:{metrics.losses},"
        f"break_even:{metrics.break_even},net:{metrics.net_profit:+.2f},"
        f"pf:{metrics.profit_factor:.4f},dd:{metrics.maximum_drawdown:.2f}"
    )


def main() -> None:
    """Run frozen cross-symbol diagnostic without GBPUSD tuning."""
    assert_frozen_oos_snapshot()
    assert resolve_forex_pip_size(SYMBOL) == 0.0001
    assert resolve_workspace_history_default_spread(SYMBOL) == 0.00012
    assert resolve_new_workspace_macd_extremum_min_prominence(SYMBOL) == 0.000015
    assert (
        resolve_new_workspace_macd_extremum_to_cross_min_distance(SYMBOL)
        == 0.000050
    )

    results: dict[str, RunMetrics] = {}
    for window in WINDOWS:
        print(f"  running_period={window.label}", flush=True)
        metrics = _run(window)
        _assert_snapshot(metrics, EXPECTED_GBPUSD[window.label])
        results[window.label] = metrics

    print("Algorithm Workspace Candidate F GBPUSD Cross-Symbol result")
    print("  mode=RM103_7X_CANDIDATE_F_GBPUSD_CROSS_SYMBOL_DIAGNOSTIC")
    print("  source_broker=CTRADER")
    print("  symbol=GBPUSD")
    print("  timeframe=M15")
    print("  execution_source=M1")
    print("  production_candidate_f_logic_changed=False")
    print("  symbol_specific_tuning=False")
    print("  pip_size=0.0001")
    print("  replay_spread_pips=1.2")
    print("  spread_limit_pips=2.0")
    print("  macd_prominence_pips=0.15")
    print("  macd_distance_pips=0.5")
    print("  comparison_2026_terminal_tail=COMMON_END_2026-08-25_15:07_UTC")
    for window in WINDOWS:
        target = results[window.label]
        reference = EURUSD_REFERENCE[window.label]
        print(f"  GBPUSD/{window.label}={_fmt(target)}")
        print(f"  EURUSD_REFERENCE/{window.label}={_fmt(reference)}")
        print(
            f"  DELTA/{window.label}="
            f"trades:{target.trades - reference.trades:+d},"
            f"net:{target.net_profit - reference.net_profit:+.2f},"
            f"pf:{target.profit_factor - reference.profit_factor:+.4f},"
            f"dd:{target.maximum_drawdown - reference.maximum_drawdown:+.2f}"
        )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_GBPUSD_CROSS_SYMBOL_CHECK=OK")


if __name__ == "__main__":
    main()
