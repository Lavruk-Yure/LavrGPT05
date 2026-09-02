# -*- coding: utf-8 -*-
"""T105-09: фінальний TEST_ONLY fine sweep Profit Drawdown за 2025–2026.

Для порогів 30/33/35/38/40% кожен період запускається окремим повним
Historical Replay через фактичний WorkspaceRuntime. Production-логіка не
змінюється. Мета — остаточно вибрати або відхилити research candidate
перед закриттям питання PD threshold у RoadMap105.

Використовуються лише завершені market events; broker requests відсутні.
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

THRESHOLDS = (30.0, 33.0, 35.0, 38.0, 40.0)
BASELINE_THRESHOLD = 30.0


@dataclass(frozen=True, slots=True)
class PeriodSpec:
    """Один контрольний Historical Replay період."""

    code: str
    file_name: str
    start_utc: str
    end_utc: str
    expected_trades: int
    expected_wins: int
    expected_losses: int
    expected_break_even: int
    expected_net: float
    expected_pf: float
    expected_dd: float


@dataclass(frozen=True, slots=True)
class Result:
    """Метрики одного незалежного Replay."""

    period: str
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


PERIODS = (
    PeriodSpec(
        code="2025",
        file_name="2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv",
        start_utc="2025-01-01T22:01:00+00:00",
        end_utc="2025-12-31T21:58:00+00:00",
        expected_trades=59,
        expected_wins=40,
        expected_losses=18,
        expected_break_even=1,
        expected_net=-4.05,
        expected_pf=0.7808441558441558,
        expected_dd=5.80,
    ),
    PeriodSpec(
        code="2026",
        file_name="2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv",
        start_utc="2026-01-01T22:01:00+00:00",
        end_utc="2026-08-25T15:07:00+00:00",
        expected_trades=29,
        expected_wins=23,
        expected_losses=5,
        expected_break_even=1,
        expected_net=1.37,
        expected_pf=1.2518382352948338,
        expected_dd=3.53,
    ),
)


def _workspace(spec: PeriodSpec, threshold: float):
    """Підготувати cTrader Candidate F для заданого періоду й порога."""
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


def _run(spec: PeriodSpec, threshold: float) -> Result:
    """Виконати один незалежний actual WorkspaceRuntime Replay."""
    runtime = WorkspaceRuntime(
        _workspace(spec, threshold),
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
        period=spec.code,
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
    )


def _assert_baseline(spec: PeriodSpec, result: Result) -> None:
    """Підтвердити production baseline 30% для заданого періоду."""
    assert result.threshold == BASELINE_THRESHOLD
    assert result.trades == spec.expected_trades
    assert result.wins == spec.expected_wins
    assert result.losses == spec.expected_losses
    assert result.break_even == spec.expected_break_even
    assert math.isclose(result.net, spec.expected_net, rel_tol=0.0, abs_tol=0.005)
    assert math.isclose(
        result.profit_factor,
        spec.expected_pf,
        rel_tol=0.0,
        abs_tol=0.00005,
    )
    assert math.isclose(
        result.drawdown,
        spec.expected_dd,
        rel_tol=0.0,
        abs_tol=0.005,
    )


def _fmt_pf(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.4f}"


def main() -> None:
    assert_frozen_oos_snapshot()

    all_results: list[Result] = []

    print("T105-09 Candidate F PD Fine Sweep 2025-2026 result")
    print("  mode=TEST_ONLY_ACTUAL_WORKSPACE_RUNTIME_PD_FINE_SWEEP")
    print("  thresholds=30,33,35,38,40")
    print("  production_baseline_threshold=30.0")
    print("  production_logic_changed=False")
    print("  each_threshold_full_independent_replay=True")

    for spec in PERIODS:
        results = tuple(_run(spec, threshold) for threshold in THRESHOLDS)
        all_results.extend(results)

        baseline = next(
            result for result in results if result.threshold == BASELINE_THRESHOLD
        )
        _assert_baseline(spec, baseline)

        print(f"  period={spec.code}")
        for result in results:
            assert result.trades == result.wins + result.losses + result.break_even
            assert result.trades == (
                result.profit_drawdown_closes
                + result.stop_loss_closes
                + result.take_profit_closes
                + result.session_end_closes
            )
            print(
                f"    threshold={result.threshold:.0f}% "
                f"trades:{result.trades},wins:{result.wins},"
                f"losses:{result.losses},break_even:{result.break_even},"
                f"net:{result.net:+.2f},pf:{_fmt_pf(result.profit_factor)},"
                f"dd:{result.drawdown:.2f},"
                f"PD:{result.profit_drawdown_closes},"
                f"SL:{result.stop_loss_closes},"
                f"TP:{result.take_profit_closes},"
                f"delta_net_vs_30:{result.net - baseline.net:+.2f},"
                f"delta_pf_vs_30:"
                f"{result.profit_factor - baseline.profit_factor:+.4f},"
                f"delta_dd_vs_30:{result.drawdown - baseline.drawdown:+.2f}"
            )

    print("  cross_period_summary")
    for threshold in THRESHOLDS:
        threshold_results = tuple(
            result for result in all_results if result.threshold == threshold
        )
        assert len(threshold_results) == len(PERIODS)
        combined_net = math.fsum(result.net for result in threshold_results)
        mean_pf = math.fsum(result.profit_factor for result in threshold_results) / len(
            threshold_results
        )
        worst_dd = max(result.drawdown for result in threshold_results)
        print(
            f"    threshold={threshold:.0f}% "
            f"combined_net:{combined_net:+.2f},"
            f"mean_pf:{mean_pf:.4f},"
            f"worst_period_dd:{worst_dd:.2f}"
        )

    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_09_PD_FINE_SWEEP_2025_2026=OK")


if __name__ == "__main__":
    main()
