# -*- coding: utf-8 -*-
"""T105-07: TEST_ONLY sweep порога Profit Drawdown Candidate F за 2025 рік.

Кожен поріг запускається окремим повним Historical Replay через фактичний
WorkspaceRuntime. Це зберігає production chronology, entry availability,
Candidate F negative-PD recovery та всі інші exit rules без look-ahead.

Production-логіка не змінюється. Поріг 30% є контрольним baseline.
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

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

TEST_ID = "T105-07"
THRESHOLDS = (20.0, 30.0, 40.0, 50.0, 60.0)
BASELINE_THRESHOLD = 30.0

EXPECTED_BASELINE_TRADES = 59
EXPECTED_BASELINE_WINS = 40
EXPECTED_BASELINE_LOSSES = 18
EXPECTED_BASELINE_BREAK_EVEN = 1
EXPECTED_BASELINE_NET = -4.05
EXPECTED_BASELINE_PF = 0.7808
EXPECTED_BASELINE_DD = 5.80
EXPECTED_BASELINE_PD = 48
EXPECTED_BASELINE_SL = 9
EXPECTED_BASELINE_TP = 2


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Один повний Replay для конкретного TEST_ONLY PD threshold."""

    threshold: float
    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float
    drawdown: float
    profit_drawdown_closes: int
    stop_loss_closes: int
    take_profit_closes: int
    session_end_closes: int
    negative_recovery_started: int
    negative_recovered: int
    negative_m2_abort: int
    negative_m3_timeout: int


def _workspace_for_threshold(threshold: float):
    """Підготувати cTrader 2025 Candidate F без зміни production-коду."""
    workspace = frozen_oos_workspace()
    workspace.broker = "CTRADER"

    profit_protection = dict(workspace.profit_protection)
    profit_protection["max_profit_drawdown_percent"] = threshold
    workspace.profit_protection = profit_protection

    replay_settings = dict(workspace.replay_settings)
    replay_settings.update(
        {
            "file_path": str(
                PROJECT_ROOT
                / "data"
                / "history"
                / "CTRADER"
                / "EURUSD"
                / "M1"
                / "2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv"
            ),
            "start_utc": "2025-01-01T22:01:00+00:00",
            "end_utc": "2025-12-31T21:58:00+00:00",
            "source": "2025-01-01_2025-12-31_CTRADER_EURUSD_M1",
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = replay_settings
    return workspace


def _run_threshold(threshold: float) -> SweepResult:
    """Виконати один незалежний фактичний WorkspaceRuntime Replay."""
    workspace = _workspace_for_threshold(threshold)
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )

    guard = runtime.profit_drawdown_guard
    assert isinstance(guard, WorkspaceCandidateFNegativePdRecoveryGuard)
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        threshold,
        rel_tol=0.0,
        abs_tol=1e-12,
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

    return SweepResult(
        threshold=threshold,
        trades=summary.opened_trades,
        wins=summary.winning_trades,
        losses=summary.losing_trades,
        break_even=summary.break_even_trades,
        net=summary.net_profit,
        profit_factor=summary.profit_factor,
        drawdown=summary.maximum_drawdown,
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
        session_end_closes=summary.close_reason_count("SESSION_END"),
        negative_recovery_started=len(guard.started_position_ids),
        negative_recovered=len(guard.recovery_close_ids),
        negative_m2_abort=len(guard.early_abort_close_ids),
        negative_m3_timeout=len(guard.timeout_close_ids),
    )


def _fmt_pf(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.4f}"


def _assert_baseline(result: SweepResult) -> None:
    """Підтвердити, що sweep відтворює GREEN cTrader 2025 baseline."""
    assert result.threshold == BASELINE_THRESHOLD
    assert result.trades == EXPECTED_BASELINE_TRADES
    assert result.wins == EXPECTED_BASELINE_WINS
    assert result.losses == EXPECTED_BASELINE_LOSSES
    assert result.break_even == EXPECTED_BASELINE_BREAK_EVEN
    assert math.isclose(
        result.net,
        EXPECTED_BASELINE_NET,
        rel_tol=0.0,
        abs_tol=0.005,
    )
    assert math.isclose(
        result.profit_factor,
        EXPECTED_BASELINE_PF,
        rel_tol=0.0,
        abs_tol=0.00005,
    )
    assert math.isclose(
        result.drawdown,
        EXPECTED_BASELINE_DD,
        rel_tol=0.0,
        abs_tol=0.005,
    )
    assert result.profit_drawdown_closes == EXPECTED_BASELINE_PD
    assert result.stop_loss_closes == EXPECTED_BASELINE_SL
    assert result.take_profit_closes == EXPECTED_BASELINE_TP


def main() -> None:
    assert_frozen_oos_snapshot()

    results = tuple(_run_threshold(threshold) for threshold in THRESHOLDS)
    baseline = next(
        result for result in results if result.threshold == BASELINE_THRESHOLD
    )
    _assert_baseline(baseline)

    assert all(
        result.trades == result.wins + result.losses + result.break_even
        for result in results
    )
    assert all(
        result.trades
        == (
            result.profit_drawdown_closes
            + result.stop_loss_closes
            + result.take_profit_closes
            + result.session_end_closes
        )
        for result in results
    )
    assert all(
        math.isfinite(result.net)
        and math.isfinite(result.drawdown)
        and (math.isfinite(result.profit_factor) or math.isinf(result.profit_factor))
        for result in results
    )

    print("T105-07 Candidate F Profit Drawdown Threshold Sweep 2025 result")
    print("  mode=TEST_ONLY_ACTUAL_WORKSPACE_RUNTIME_PD_THRESHOLD_SWEEP")
    print("  source=CTRADER_EURUSD_M1_2025")
    print("  profile=LGE_CANDIDATE_F_SMOOTHED_R1")
    print("  production_baseline_threshold=30.0")
    print("  production_logic_changed=False")
    print("  each_threshold_full_independent_replay=True")
    print("  candidate_f_negative_pd_recovery_preserved=True")

    for result in results:
        print(
            f"  threshold={result.threshold:.0f}% "
            f"trades:{result.trades},"
            f"wins:{result.wins},losses:{result.losses},"
            f"break_even:{result.break_even},"
            f"net:{result.net:+.2f},pf:{_fmt_pf(result.profit_factor)},"
            f"dd:{result.drawdown:.2f},"
            f"PD:{result.profit_drawdown_closes},"
            f"SL:{result.stop_loss_closes},"
            f"TP:{result.take_profit_closes},"
            f"SESSION:{result.session_end_closes},"
            f"delta_net_vs_30:{result.net - baseline.net:+.2f},"
            f"delta_pf_vs_30:{result.profit_factor - baseline.profit_factor:+.4f},"
            f"delta_dd_vs_30:{result.drawdown - baseline.drawdown:+.2f}"
        )
        print(
            f"    negative_recovery="
            f"started:{result.negative_recovery_started},"
            f"recovered:{result.negative_recovered},"
            f"m2_abort:{result.negative_m2_abort},"
            f"m3_timeout:{result.negative_m3_timeout}"
        )

    ranked = sorted(
        results,
        key=lambda result: (
            -result.net,
            -result.profit_factor,
            result.drawdown,
            result.threshold,
        ),
    )
    print(
        "  research_rank_by_net_then_pf_then_dd="
        + ",".join(f"{result.threshold:.0f}%" for result in ranked)
    )
    print("  production_decision_made=False")
    print("  cross_period_2026_required_before_any_production_change=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_07_PD_THRESHOLD_SWEEP_2025=OK")


if __name__ == "__main__":
    main()
