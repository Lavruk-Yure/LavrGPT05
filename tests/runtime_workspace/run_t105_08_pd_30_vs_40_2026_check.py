# -*- coding: utf-8 -*-
"""T105-08: TEST_ONLY порівняння Profit Drawdown 30% проти 40% у 2026.

Обидва варіанти запускаються окремим повним Historical Replay через фактичний
WorkspaceRuntime. Production-логіка не змінюється. Поріг 30% є production
baseline, 40% — лише research candidate після T105-07.

Перевірка використовує завершені market events, не додає look-ahead і не
звертається до брокера.
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

THRESHOLDS = (30.0, 40.0)
BASELINE_THRESHOLD = 30.0

EXPECTED_BASELINE_TRADES = 29
EXPECTED_BASELINE_WINS = 23
EXPECTED_BASELINE_LOSSES = 5
EXPECTED_BASELINE_BREAK_EVEN = 1
EXPECTED_BASELINE_NET = 1.37
EXPECTED_BASELINE_PF = 1.2518382352948338
EXPECTED_BASELINE_DD = 3.53


@dataclass(frozen=True, slots=True)
class Result:
    """Метрики одного незалежного Replay для заданого PD threshold."""

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


def _workspace(threshold: float):
    """Підготувати Candidate F cTrader 2026 без зміни production-коду."""
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
                / "2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv"
            ),
            "start_utc": "2026-01-01T22:01:00+00:00",
            "end_utc": "2026-08-25T15:07:00+00:00",
            "source": "2026-01-01_2026-08-25_CTRADER_EURUSD_M1",
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = replay_settings
    return workspace


def _run(threshold: float) -> Result:
    """Виконати один незалежний actual WorkspaceRuntime Replay."""
    workspace = _workspace(threshold)
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

    return Result(
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


def _assert_baseline(result: Result) -> None:
    """Підтвердити actual cTrader 2026 production baseline 30%."""
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
        abs_tol=1e-12,
    )
    assert math.isclose(
        result.drawdown,
        EXPECTED_BASELINE_DD,
        rel_tol=0.0,
        abs_tol=0.005,
    )


def _fmt_pf(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.4f}"


def main() -> None:
    assert_frozen_oos_snapshot()

    results = tuple(_run(threshold) for threshold in THRESHOLDS)
    baseline = next(
        result for result in results if result.threshold == BASELINE_THRESHOLD
    )
    candidate = next(result for result in results if result.threshold == 40.0)
    _assert_baseline(baseline)

    for result in results:
        assert result.trades == result.wins + result.losses + result.break_even
        assert result.trades == (
            result.profit_drawdown_closes
            + result.stop_loss_closes
            + result.take_profit_closes
            + result.session_end_closes
        )

    print("T105-08 Candidate F PD 30% vs 40% Cross-period 2026 result")
    print("  mode=TEST_ONLY_ACTUAL_WORKSPACE_RUNTIME_PD_30_VS_40")
    print("  source=CTRADER_EURUSD_M1_2026_TO_2026-08-25_15:07")
    print("  profile=LGE_CANDIDATE_F_SMOOTHED_R1")
    print("  production_baseline_threshold=30.0")
    print("  research_candidate_threshold=40.0")

    for result in results:
        print(
            f"  threshold={result.threshold:.0f}% "
            f"trades:{result.trades},wins:{result.wins},"
            f"losses:{result.losses},break_even:{result.break_even},"
            f"net:{result.net:+.2f},pf:{_fmt_pf(result.profit_factor)},"
            f"dd:{result.drawdown:.2f},"
            f"PD:{result.profit_drawdown_closes},"
            f"SL:{result.stop_loss_closes},"
            f"TP:{result.take_profit_closes},"
            f"SESSION:{result.session_end_closes}"
        )
        print(
            "    negative_recovery="
            f"started:{result.negative_recovery_started},"
            f"recovered:{result.negative_recovered},"
            f"m2_abort:{result.negative_m2_abort},"
            f"m3_timeout:{result.negative_m3_timeout}"
        )

    print(
        "  candidate_delta_vs_30="
        f"net:{candidate.net - baseline.net:+.2f},"
        f"pf:{candidate.profit_factor - baseline.profit_factor:+.4f},"
        f"dd:{candidate.drawdown - baseline.drawdown:+.2f},"
        f"trades:{candidate.trades - baseline.trades:+d},"
        f"PD:{candidate.profit_drawdown_closes - baseline.profit_drawdown_closes:+d},"
        f"SL:{candidate.stop_loss_closes - baseline.stop_loss_closes:+d},"
        f"TP:{candidate.take_profit_closes - baseline.take_profit_closes:+d}"
    )
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_08_PD_30_VS_40_2026=OK")


if __name__ == "__main__":
    main()
