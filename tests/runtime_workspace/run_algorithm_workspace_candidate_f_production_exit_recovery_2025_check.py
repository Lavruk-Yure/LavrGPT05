# -*- coding: utf-8 -*-
"""RoadMap102 / 6K: production Candidate F negative-PD recovery 2025.

Перевірка фіксує перенесення validated 6J exit lifecycle у production
WorkspaceRuntime лише для Candidate F SAME_TIMEFRAME M15 Historical Replay
із M1 execution chronology. Frozen pre-6J OOS baseline зберігається окремим
FrozenOosRuntime і не змішується з production regression.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_profit_guard import (  # noqa: E402
    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX,
    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1,
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

EXPECTED_TRADES = 59
EXPECTED_WINS = 40
EXPECTED_LOSSES = 18
EXPECTED_BREAK_EVEN = 1
EXPECTED_NET = -4.05
EXPECTED_PROFIT_FACTOR = 0.7808
EXPECTED_DRAWDOWN = 5.80
EXPECTED_RECOVERY_STARTED = 18
EXPECTED_RECOVERY_CLOSES = 9
EXPECTED_EARLY_ABORT_CLOSES = 5
EXPECTED_TIMEOUT_CLOSES = 4


def _close_enough(actual: float, expected: float, tolerance: float = 0.005) -> bool:
    return abs(float(actual) - float(expected)) <= tolerance


def main() -> None:
    """Run production Candidate F OOS with fixed 6J exit lifecycle."""
    assert_frozen_oos_snapshot()
    runtime = WorkspaceRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    guard = runtime.profit_drawdown_guard
    assert isinstance(guard, WorkspaceCandidateFNegativePdRecoveryGuard)
    assert CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1 == 3
    assert CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX == 2
    assert any(
        entry.event == "CANDIDATE_F_NEGATIVE_PD_RECOVERY_ACTIVE"
        for entry in runtime.journal
    )

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    assert summary is not None
    assert summary.opened_trades == EXPECTED_TRADES
    assert summary.winning_trades == EXPECTED_WINS
    assert summary.losing_trades == EXPECTED_LOSSES
    assert summary.break_even_trades == EXPECTED_BREAK_EVEN
    assert _close_enough(summary.net_profit, EXPECTED_NET)
    assert summary.profit_factor is not None
    assert _close_enough(summary.profit_factor, EXPECTED_PROFIT_FACTOR, 0.00005)
    assert _close_enough(summary.maximum_drawdown, EXPECTED_DRAWDOWN)
    assert summary.close_reason_count("STOP_LOSS") == 9
    assert summary.close_reason_count("TAKE_PROFIT") == 2
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == 48
    assert len(guard.started_position_ids) == EXPECTED_RECOVERY_STARTED
    assert len(guard.recovery_close_ids) == EXPECTED_RECOVERY_CLOSES
    assert len(guard.early_abort_close_ids) == EXPECTED_EARLY_ABORT_CLOSES
    assert len(guard.timeout_close_ids) == EXPECTED_TIMEOUT_CLOSES
    assert not guard.pending

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Production Exit Recovery 2025 result")
    print("  production_policy=NEGATIVE_PD_3_M1_RECOVERY_WITH_M2_ABORT")
    print("  activation=Candidate F SAME_TIMEFRAME M15 Replay with M1 source")
    print("  recovery_window_m1=3")
    print("  early_abort_event=M2")
    print("  early_abort_rule=M1_STEP_NONPOSITIVE_AND_M2_STEP_NONPOSITIVE")
    print(
        "  trades="
        f"{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades}"
    )
    print(
        "  performance="
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(
        "  recovery_pending="
        f"started:{len(guard.started_position_ids)},"
        f"recovery:{len(guard.recovery_close_ids)},"
        f"early_abort:{len(guard.early_abort_close_ids)},"
        f"timeout:{len(guard.timeout_close_ids)}"
    )
    print("  frozen_pre_6j_baseline_isolated=True")
    print("  production_candidate_f_signals_preserved=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_PRODUCTION_EXIT_RECOVERY_2025_CHECK=OK")


if __name__ == "__main__":
    main()
