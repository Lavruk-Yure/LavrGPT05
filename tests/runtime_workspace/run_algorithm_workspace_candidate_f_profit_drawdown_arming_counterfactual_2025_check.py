# -*- coding: utf-8 -*-
"""RoadMap102 / 6C: test-only counterfactual Profit Drawdown arming OOS 2025.

Runner не змінює production-код. Для frozen Candidate F 2025 він повторює
повний Replay для трьох наперед зафіксованих arming-рівнів 0.10R/0.20R/0.30R.
Після досягнення position-relative arming threshold продовжує діяти чинний
Profit Drawdown 30%. Усі входи, MACD, Alligator, Candidate F, risk, SL/TP,
NEXT_BAR_OPEN і M1 execution chronology залишаються незмінними.

PASS не залежить від PnL/PF/DD: результат може бути кращим або гіршим за
baseline. Runner лише перевіряє causal execution, frozen thresholds і повну
відсутність broker execution.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_ownership import WorkspacePositionSnapshot  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WORKSPACE_PROFIT_ACTION_CLOSE,
    WORKSPACE_PROFIT_ACTION_HOLD,
    WorkspaceProfitProtectionDecision,
    WorkspaceProfitProtectionPolicy,
)

ARMING_LEVELS_R = (0.10, 0.20, 0.30)
BASELINE_TRADES = 59
BASELINE_WINS = 31
BASELINE_LOSSES = 27
BASELINE_BREAK_EVEN = 1
BASELINE_NET = -5.90
BASELINE_PROFIT_FACTOR = 0.6895
BASELINE_DRAWDOWN = 6.90
BASELINE_MACD_QUALITY_PASS = 414
BASELINE_MACD_QUALITY_REJECT = 2626
BASELINE_ALLIGATOR_ALLOW = 59
BASELINE_ALLIGATOR_REJECT = 357
NUMERIC_EPSILON = 1e-9


class WorkspaceRArmingProfitDrawdownGuard:
    """Test-only guard: production 30% drawdown після position-relative R arming."""

    def __init__(
        self,
        policy: WorkspaceProfitProtectionPolicy,
        arming_level_r: float,
    ) -> None:
        if arming_level_r <= 0.0:
            raise ValueError("arming_level_r must be positive")
        self.policy = policy
        self.arming_level_r = float(arming_level_r)

    @staticmethod
    def _initial_risk_usd(position: WorkspacePositionSnapshot) -> float | None:
        """Повернути initial 1R у USD з незмінних entry/SL/volume позиції."""
        if (
            position.entry_price is None
            or position.stop_loss is None
            or position.volume <= 0.0
        ):
            return None
        risk_usd = abs(position.entry_price - position.stop_loss) * position.volume
        if not math.isfinite(risk_usd) or risk_usd <= 0.0:
            return None
        return risk_usd

    def evaluate(
        self,
        position: WorkspacePositionSnapshot,
        *,
        timestamp,
        runtime_ready: bool,
        spread_guard_passed: bool,
    ) -> WorkspaceProfitProtectionDecision:
        """Повернути HOLD/CLOSE без майбутніх даних і без broker execution."""
        current_price_verified = bool(
            position.current_price is not None
            and math.isfinite(position.current_price)
            and position.current_price > 0.0
        )
        risk_usd = self._initial_risk_usd(position)
        minimum_profit = 0.0 if risk_usd is None else risk_usd * self.arming_level_r

        action = WORKSPACE_PROFIT_ACTION_HOLD
        if not self.policy.enabled:
            reason = "profit protection is disabled"
        elif not runtime_ready:
            reason = "runtime is not ready"
        elif self.policy.activation_mode == "AFTER_SPREAD" and not spread_guard_passed:
            reason = "spread guard is not passed"
        elif not current_price_verified:
            reason = "current price is unavailable"
        elif risk_usd is None:
            reason = "initial risk is unavailable"
        elif position.peak_profit + NUMERIC_EPSILON < minimum_profit:
            reason = "position-relative R arming threshold is not reached"
        elif position.peak_profit <= 0.0:
            reason = "position has no positive peak profit"
        elif position.profit_drawdown <= self.policy.max_drawdown_percent:
            reason = "profit drawdown is within limit"
        else:
            action = WORKSPACE_PROFIT_ACTION_CLOSE
            reason = (
                f"profit drawdown {position.profit_drawdown:.2f}% exceeds "
                f"limit {self.policy.max_drawdown_percent:.2f}% after "
                f"{self.arming_level_r:.2f}R arming"
            )

        return WorkspaceProfitProtectionDecision(
            timestamp=timestamp,
            workspace_uid=position.workspace_uid,
            broker=position.broker,
            account_id=position.account_id,
            symbol=position.symbol,
            position_id=position.position_id,
            broker_position_id=position.broker_position_id,
            action=action,
            reason=reason,
            current_profit=position.current_profit,
            peak_profit=position.peak_profit,
            drawdown_percent=position.profit_drawdown,
            drawdown_limit_percent=self.policy.max_drawdown_percent,
            minimum_profit=minimum_profit,
            ownership_verified=True,
            current_price_verified=current_price_verified,
            spread_guard_passed=spread_guard_passed,
            runtime_ready=runtime_ready,
            execution_attempted=False,
        )


@dataclass(frozen=True, slots=True)
class VariantResult:
    """Підсумок одного повного counterfactual Replay."""

    arming_level_r: float
    trades: int
    wins: int
    losses: int
    break_even: int
    net_profit: float
    profit_factor: float | None
    maximum_drawdown: float
    maximum_drawdown_percent: float
    average_trade: float
    final_balance: float
    stop_loss_closes: int
    take_profit_closes: int
    profit_drawdown_closes: int
    session_end_closes: int
    pd_positive: int
    pd_negative: int
    pd_zero: int
    macd_quality_pass: int
    macd_quality_reject: int
    alligator_allow: int
    alligator_reject: int
    broker_execution_attempted: bool


def _run_variant(arming_level_r: float) -> VariantResult:
    """Виконати один повний frozen OOS Replay з test-only R arming guard."""
    workspace = frozen_oos_workspace()
    assert workspace.profit_protection["max_profit_drawdown_percent"] == 30.0
    assert workspace.profit_protection["minimum_profit"] == 0.0

    runtime = FrozenOosRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
    )
    runtime.profit_drawdown_guard = WorkspaceRArmingProfitDrawdownGuard(
        runtime.profit_protection_policy,
        arming_level_r,
    )

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert summary is not None
    assert execution is not None
    trades = execution.trade_diagnostics()
    assert len(trades) == summary.opened_trades
    assert all(trade.close_timestamp >= trade.entry_timestamp for trade in trades)

    pd_trades = tuple(
        trade for trade in trades if trade.close_reason == "PROFIT_DRAWDOWN"
    )
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    signals = summary.signals

    # Exit policy має змінювати лише execution lifecycle, не signal algorithm.
    assert signals.macd_quality_accept == BASELINE_MACD_QUALITY_PASS
    assert signals.macd_quality_reject == BASELINE_MACD_QUALITY_REJECT
    assert signals.alligator_allow == BASELINE_ALLIGATOR_ALLOW
    assert signals.alligator_reject == BASELINE_ALLIGATOR_REJECT
    assert not broker_execution_attempted

    return VariantResult(
        arming_level_r=arming_level_r,
        trades=summary.opened_trades,
        wins=summary.winning_trades,
        losses=summary.losing_trades,
        break_even=summary.break_even_trades,
        net_profit=summary.net_profit,
        profit_factor=summary.profit_factor,
        maximum_drawdown=summary.maximum_drawdown,
        maximum_drawdown_percent=summary.maximum_drawdown_percent,
        average_trade=summary.average_trade,
        final_balance=summary.final_balance,
        stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
        take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
        profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
        session_end_closes=summary.close_reason_count("SESSION_END"),
        pd_positive=sum(trade.final_profit > 0.0 for trade in pd_trades),
        pd_negative=sum(trade.final_profit < 0.0 for trade in pd_trades),
        pd_zero=sum(trade.final_profit == 0.0 for trade in pd_trades),
        macd_quality_pass=signals.macd_quality_accept,
        macd_quality_reject=signals.macd_quality_reject,
        alligator_allow=signals.alligator_allow,
        alligator_reject=signals.alligator_reject,
        broker_execution_attempted=broker_execution_attempted,
    )


def _fmt_pf(value: float | None) -> str:
    """Форматувати optional Profit Factor."""
    return "NONE" if value is None else f"{value:.4f}"


def main() -> None:
    """Порівняти 0.10R/0.20R/0.30R без performance-based PASS."""
    assert_frozen_oos_snapshot()

    results = tuple(_run_variant(level_r) for level_r in ARMING_LEVELS_R)
    assert tuple(result.arming_level_r for result in results) == ARMING_LEVELS_R
    assert all(not result.broker_execution_attempted for result in results)

    print(
        "Algorithm Workspace Candidate F "
        "Profit Drawdown Arming Counterfactual 2025 result"
    )
    print("  mode=TEST_ONLY_FIXED_R_ARMING_COUNTERFACTUAL_EXECUTION")
    print(
        "  baseline="
        f"trades:{BASELINE_TRADES},wins:{BASELINE_WINS},"
        f"losses:{BASELINE_LOSSES},break_even:{BASELINE_BREAK_EVEN},"
        f"net:{BASELINE_NET:+.2f},pf:{BASELINE_PROFIT_FACTOR:.4f},"
        f"dd:{BASELINE_DRAWDOWN:.2f}"
    )
    print("  variants=0.10R;0.20R;0.30R")
    print("  production_profit_drawdown=30.0%")
    print("  production_minimum_profit=0.0")
    print("  test_arming_is_position_relative_initial_risk=True")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  execution_chronology=M1")

    for result in results:
        print(f"  arm_{result.arming_level_r:.2f}R:")
        print(
            "    trades="
            f"{result.trades},wins:{result.wins},losses:{result.losses},"
            f"break_even:{result.break_even}"
        )
        print(
            "    performance="
            f"net:{result.net_profit:+.2f},pf:{_fmt_pf(result.profit_factor)},"
            f"dd:{result.maximum_drawdown:.2f}/"
            f"{result.maximum_drawdown_percent:.2f}%,"
            f"avg_trade:{result.average_trade:+.4f},"
            f"final_balance:{result.final_balance:.2f}"
        )
        print(
            "    delta_vs_baseline="
            f"net:{result.net_profit - BASELINE_NET:+.2f},"
            f"dd:{result.maximum_drawdown - BASELINE_DRAWDOWN:+.2f},"
            f"trades:{result.trades - BASELINE_TRADES:+d}"
        )
        print(
            "    closes="
            f"sl:{result.stop_loss_closes},tp:{result.take_profit_closes},"
            f"profit_drawdown:{result.profit_drawdown_closes},"
            f"session_end:{result.session_end_closes}"
        )
        print(
            "    profit_drawdown_outcomes="
            f"positive:{result.pd_positive},negative:{result.pd_negative},"
            f"zero:{result.pd_zero}"
        )
        print(
            "    signal_pipeline="
            f"macd_quality_pass:{result.macd_quality_pass},"
            f"macd_quality_reject:{result.macd_quality_reject},"
            f"alligator_allow:{result.alligator_allow},"
            f"alligator_reject:{result.alligator_reject}"
        )

    print("  entry_logic_changed=False")
    print("  stop_loss_policy_changed=False")
    print("  take_profit_policy_changed=False")
    print("  profit_drawdown_percent_changed=False")
    print("  only_profit_drawdown_arming_changed_test_only=True")
    print("  future_price_used_as_exit_gate=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print(
        "ALGORITHM_WORKSPACE_CANDIDATE_F_PROFIT_DRAWDOWN_ARMING_"
        "COUNTERFACTUAL_2025_CHECK=OK"
    )


if __name__ == "__main__":
    main()
