# -*- coding: utf-8 -*-
"""RoadMap103 / 7E: cross-period robustness check для 7D one-bar gate.

Gate 7D був сформований на 2025 OOS. Цей runner не змінює його пороги й
перевіряє той самий causal gate на трьох уже відомих історичних вікнах 2026:
Development, Validation і Holdout. Це не новий blind OOS для Candidate F,
оскільки 2026 раніше використовувався під час розробки алгоритму; мета 7E —
перевірити переносимість саме нового 7D gate без додаткового tuning.

Production-код, профілі, SL/TP та 6K negative-PD recovery не змінюються.
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

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
)
from run_algorithm_workspace_candidate_f_sl_one_bar_impulse_gate_2025_check import (  # noqa: E402,E501
    GATE_CLOSE_LOCATION_THRESHOLD,
    GATE_SHARE30_THRESHOLD,
    OneBarImpulseGateRuntime,
)

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
)

HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "history"
    / "IB"
    / "EURUSD"
    / "M1"
    / "2026-01-02_2026-08-11_IB_EURUSD_M1.csv"
)

WINDOWS = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T00:00:00+00:00",
    ),
    (
        "VALIDATION",
        "2026-03-01T00:00:00+00:00",
        "2026-05-31T23:59:00+00:00",
    ),
    (
        "HOLDOUT",
        "2026-06-01T00:00:00+00:00",
        "2026-08-11T08:24:00+00:00",
    ),
)


@dataclass(frozen=True, slots=True)
class ExpectedRun:
    """Очікуваний deterministic результат одного Replay."""

    trades: int
    wins: int
    losses: int
    stop_losses: int
    net_profit: float
    profit_factor: float
    maximum_drawdown: float


@dataclass(frozen=True, slots=True)
class ExpectedWindow:
    """Очікувані baseline/gated результати одного вікна 2026."""

    baseline: ExpectedRun
    gated: ExpectedRun
    rejections: int
    flagged_pnl: float


EXPECTED = {
    "DEVELOPMENT": ExpectedWindow(
        baseline=ExpectedRun(7, 6, 1, 0, 1.11, 10.2500, 0.12),
        gated=ExpectedRun(5, 4, 1, 0, 0.65, 6.4167, 0.12),
        rejections=2,
        flagged_pnl=0.46,
    ),
    "VALIDATION": ExpectedWindow(
        baseline=ExpectedRun(16, 12, 4, 2, -0.78, 0.8579, 3.69),
        gated=ExpectedRun(14, 11, 3, 2, -2.29, 0.5814, 3.69),
        rejections=2,
        flagged_pnl=1.51,
    ),
    "HOLDOUT": ExpectedWindow(
        baseline=ExpectedRun(7, 6, 1, 0, 0.46, 7.5714, 0.07),
        gated=ExpectedRun(6, 5, 1, 0, 0.28, 5.0000, 0.07),
        rejections=1,
        flagged_pnl=0.18,
    ),
}


@dataclass(frozen=True, slots=True)
class RunResult:
    """Одна deterministic Replay-метрика для baseline або test-only gate."""

    trades: int
    wins: int
    losses: int
    break_even: int
    stop_losses: int
    net_profit: float
    profit_factor: float | None
    maximum_drawdown: float
    broker_execution_attempted: bool


def _candidate_bindings() -> dict[str, dict[str, object]]:
    bindings = new_workspace_indicator_profile_bindings()
    candidate = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    bindings[WORKSPACE_ALLIGATOR_PROFILE_BINDING_KEY] = (
        WorkspaceIndicatorProfileBinding.from_profile(candidate).to_storage_dict()
    )
    return bindings


def _workspace(start_utc: str, end_utc: str) -> AlgorithmWorkspace:
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=None,
        account_mode=None,
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        display_name="RM103 7E One-Bar Gate Cross-Period 2026",
        data_mode=WORKSPACE_DATA_MODE_REPLAY,
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        parameters={
            "macd_signal_enabled": True,
            "macd_signal_mode": "EXTENDED",
            "alligator_filter_enabled": True,
            "alligator_confirmation": WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
            "spread_limit": 0.00020,
            "warmup_bars": 3,
            "macd_extremum_min_prominence": 0.000015,
            "macd_extremum_to_cross_min_distance": 0.000050,
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
            "file_path": str(HISTORY_FILE),
            "start_utc": start_utc,
            "end_utc": end_utc,
            "source_timezone": "UTC",
            "delimiter": "AUTO",
            "decimal_separator": ".",
            "spread": 0.00012,
            "source": "2026-01-02_2026-08-11_IB_EURUSD_M1",
            "source_timeframe": "M1",
            "risk_equity": 1000.0,
            "speed": -1,
        },
        indicator_profile_bindings=_candidate_bindings(),
    )


def _run(
    runtime_type: type[WorkspaceRuntime],
    start_utc: str,
    end_utc: str,
) -> tuple[WorkspaceRuntime, RunResult]:
    runtime = runtime_type(
        _workspace(start_utc, end_utc),
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
    assert summary is not None
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    return runtime, RunResult(
        trades=summary.opened_trades,
        wins=summary.winning_trades,
        losses=summary.losing_trades,
        break_even=summary.break_even_trades,
        stop_losses=summary.close_reason_count("STOP_LOSS"),
        net_profit=summary.net_profit,
        profit_factor=summary.profit_factor,
        maximum_drawdown=summary.maximum_drawdown,
        broker_execution_attempted=broker_execution_attempted,
    )


def _assert_expected(result: RunResult, expected: ExpectedRun) -> None:
    assert result.trades == expected.trades
    assert result.wins == expected.wins
    assert result.losses == expected.losses
    assert result.stop_losses == expected.stop_losses
    assert math.isclose(result.net_profit, expected.net_profit, abs_tol=0.005)
    assert result.profit_factor is not None
    assert math.isclose(
        result.profit_factor,
        expected.profit_factor,
        abs_tol=0.00005,
    )
    assert math.isclose(
        result.maximum_drawdown,
        expected.maximum_drawdown,
        abs_tol=0.005,
    )


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def _fmt_result(result: RunResult) -> str:
    return (
        f"trades:{result.trades},wins:{result.wins},losses:{result.losses},"
        f"break_even:{result.break_even},sl:{result.stop_losses},"
        f"net:{result.net_profit:+.2f},pf:{_fmt_pf(result.profit_factor)},"
        f"dd:{result.maximum_drawdown:.2f}"
    )


def main() -> None:
    """Перевірити frozen 7D gate на трьох історичних вікнах 2026."""
    assert HISTORY_FILE.is_file(), HISTORY_FILE
    assert_frozen_oos_snapshot()

    total_baseline_net = 0.0
    total_gated_net = 0.0
    total_rejections = 0
    total_flagged_pnl = 0.0
    rows: list[tuple[str, RunResult, RunResult, int, tuple[str, ...], float]] = []

    for window, start_utc, end_utc in WINDOWS:
        baseline_runtime, baseline = _run(WorkspaceRuntime, start_utc, end_utc)
        gated_runtime_base, gated = _run(
            OneBarImpulseGateRuntime,
            start_utc,
            end_utc,
        )
        assert isinstance(gated_runtime_base, OneBarImpulseGateRuntime)
        gated_runtime = gated_runtime_base

        expected = EXPECTED[window]
        _assert_expected(baseline, expected.baseline)
        _assert_expected(gated, expected.gated)
        assert len(gated_runtime.gate_rejections) == expected.rejections

        baseline_execution = baseline_runtime.replay_execution
        assert baseline_execution is not None
        baseline_trades = {
            trade.signal_timestamp: trade
            for trade in baseline_execution.trade_diagnostics()
        }
        flagged: list[str] = []
        flagged_pnl = 0.0
        for (
            timestamp,
            direction,
            share_30,
            close_location,
        ) in gated_runtime.gate_rejections:
            trade = baseline_trades.get(timestamp)
            assert trade is not None, timestamp
            flagged_pnl += trade.final_profit
            flagged.append(
                f"{timestamp.isoformat()} {direction} "
                f"share30:{share_30:.3f} close_location:{close_location:.3f} "
                f"baseline_exit:{trade.close_reason} pnl:{trade.final_profit:+.2f}"
            )
        assert math.isclose(
            flagged_pnl,
            expected.flagged_pnl,
            abs_tol=0.005,
        )
        assert math.isclose(
            baseline.net_profit - flagged_pnl,
            gated.net_profit,
            abs_tol=0.005,
        )

        total_baseline_net += baseline.net_profit
        total_gated_net += gated.net_profit
        total_rejections += len(gated_runtime.gate_rejections)
        total_flagged_pnl += flagged_pnl
        rows.append(
            (
                window,
                baseline,
                gated,
                len(gated_runtime.gate_rejections),
                tuple(flagged),
                flagged_pnl,
            )
        )

    assert total_rejections == 5
    assert math.isclose(total_baseline_net, 0.79, abs_tol=0.005)
    assert math.isclose(total_gated_net, -1.36, abs_tol=0.005)
    assert math.isclose(total_flagged_pnl, 2.15, abs_tol=0.005)
    stop_loss_reduction = sum(
        baseline.stop_losses - gated.stop_losses for _, baseline, gated, *_ in rows
    )
    net_improvement_windows = sum(
        gated.net_profit > baseline.net_profit for _, baseline, gated, *_ in rows
    )

    print("Algorithm Workspace Candidate F SL One-Bar Gate Cross-Period 2026 result")
    print("  mode=FROZEN_7D_GATE_CROSS_PERIOD_ROBUSTNESS_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  alternative_stop_applied=False")
    print("  exit_recovery_policy=PRODUCTION_6K_PRESERVED")
    print("  future_price_used_as_gate=False")
    print("  candidate_f_2026_is_not_blind_oos=True")
    print("  gate_thresholds_retuned_on_2026=False")
    print(
        "  gate="
        f"share30>={GATE_SHARE30_THRESHOLD:.2f}_AND_"
        f"close_location>={GATE_CLOSE_LOCATION_THRESHOLD:.2f}"
    )
    for window, baseline, gated, rejections, flagged, flagged_pnl in rows:
        print(f"  {window}:")
        print(f"    baseline={_fmt_result(baseline)}")
        print(f"    gated={_fmt_result(gated)}")
        print(
            "    delta="
            f"net:{gated.net_profit - baseline.net_profit:+.2f},"
            f"sl:{gated.stop_losses - baseline.stop_losses:+d},"
            f"trades:{gated.trades - baseline.trades:+d}"
        )
        print(
            f"    gate_rejections={rejections},"
            f"baseline_flagged_pnl:{flagged_pnl:+.2f}"
        )
        for index, text in enumerate(flagged, start=1):
            print(f"      {index:02d}. {text}")
    print(
        "  aggregate_window_net="
        f"baseline:{total_baseline_net:+.2f},gated:{total_gated_net:+.2f},"
        f"delta:{total_gated_net - total_baseline_net:+.2f}"
    )
    print(f"  aggregate_gate_rejections={total_rejections}")
    print(f"  aggregate_baseline_flagged_pnl={total_flagged_pnl:+.2f}")
    print(f"  stop_loss_reduction_across_2026_windows={stop_loss_reduction}")
    print(f"  net_improvement_windows={net_improvement_windows}/3")
    promotion = (
        "KEEP_FOR_FURTHER_VALIDATION"
        if stop_loss_reduction > 0 and net_improvement_windows >= 2
        else "REJECT_FOR_PRODUCTION"
    )
    print(f"  gate_promotion_decision={promotion}")
    print("  causal_signal_and_two_prior_M15_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_SL_ONE_BAR_GATE_CROSS_PERIOD_2026_CHECK=OK")


if __name__ == "__main__":
    main()
