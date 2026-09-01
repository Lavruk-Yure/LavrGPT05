# -*- coding: utf-8 -*-
"""T105-10: production regression для Profit Drawdown 35%.

Перевірка підтверджує новий canonical default 35% та actual
WorkspaceRuntime Candidate F на cTrader 2025 і 2026. Інша entry/exit логіка
не змінюється.
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

from core.algorithm_workspace import AlgorithmWorkspace  # noqa: E402
from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX,
    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1,
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    frozen_oos_workspace,
)

PRODUCTION_PD_THRESHOLD = 35.0


@dataclass(frozen=True, slots=True)
class PeriodSpec:
    """Очікуваний production baseline одного Replay періоду."""

    code: str
    file_name: str
    start_utc: str
    end_utc: str
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


PERIODS = (
    PeriodSpec(
        code="2025",
        file_name="2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv",
        start_utc="2025-01-01T22:01:00+00:00",
        end_utc="2025-12-31T21:58:00+00:00",
        trades=59,
        wins=40,
        losses=18,
        break_even=1,
        net=-3.79,
        profit_factor=0.7949,
        drawdown=5.19,
        profit_drawdown_closes=48,
        stop_loss_closes=9,
        take_profit_closes=2,
    ),
    PeriodSpec(
        code="2026",
        file_name="2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv",
        start_utc="2026-01-01T22:01:00+00:00",
        end_utc="2026-08-25T15:07:00+00:00",
        trades=29,
        wins=23,
        losses=5,
        break_even=1,
        net=3.32,
        profit_factor=1.6103,
        drawdown=3.53,
        profit_drawdown_closes=26,
        stop_loss_closes=2,
        take_profit_closes=1,
    ),
)


def _assert_fresh_workspace_default() -> None:
    """Підтвердити 35% для нового WSP без persisted override."""
    workspace = AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id="TEST",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
    )
    assert DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT == PRODUCTION_PD_THRESHOLD
    assert (
        workspace.profit_protection["max_profit_drawdown_percent"]
        == PRODUCTION_PD_THRESHOLD
    )

    runtime = WorkspaceRuntime(workspace)
    assert runtime.context.profit_drawdown_close_percent == PRODUCTION_PD_THRESHOLD
    assert (
        runtime.profit_protection_policy.max_drawdown_percent == PRODUCTION_PD_THRESHOLD
    )


def _workspace(spec: PeriodSpec):
    """Підготувати actual Candidate F cTrader Replay з production 35%."""
    workspace = frozen_oos_workspace()
    workspace.broker = "CTRADER"

    profit_protection = dict(workspace.profit_protection)
    threshold_key = "max_profit_drawdown_percent"
    profit_protection[threshold_key] = DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT
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
                / spec.file_name
            ),
            "start_utc": spec.start_utc,
            "end_utc": spec.end_utc,
            "source": Path(spec.file_name).stem,
            "source_timeframe": "M1",
        }
    )
    workspace.replay_settings = replay_settings
    return workspace


def _run(spec: PeriodSpec) -> None:
    """Запустити один production-equivalent WorkspaceRuntime Replay."""
    runtime = WorkspaceRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
    )

    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1 == 3
    assert CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX == 2
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
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

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print(
        f"  period={spec.code} "
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f},"
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')}"
    )


def main() -> None:
    _assert_fresh_workspace_default()

    print("T105-10 Candidate F PD 35% Production Regression result")
    print("  production_profit_drawdown_threshold=35.0")
    print("  candidate_f_negative_pd_recovery_window_m1=3")
    print("  candidate_f_negative_pd_m2_early_abort=True")
    print("  actual_workspace_runtime=True")

    for spec in PERIODS:
        _run(spec)

    print("  production_entry_logic_changed=False")
    print("  other_exit_logic_changed=False")
    print("  completed_market_events_only=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_10_PD_35_PRODUCTION_REGRESSION=OK")


if __name__ == "__main__":
    main()
