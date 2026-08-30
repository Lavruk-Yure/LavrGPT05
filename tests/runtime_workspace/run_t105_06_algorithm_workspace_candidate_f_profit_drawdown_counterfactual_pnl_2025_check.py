# -*- coding: utf-8 -*-
"""T105-06: контрфактична PnL-анатомія Profit Drawdown Candidate F, cTrader 2025.

TEST_ONLY діагностика. Production-логіка входу та виходу не змінюється.
Runner повторно використовує фактичну PD-анатомію WorkspaceRuntime з T105-05
і порівнює кожне фактичне закриття PROFIT_DRAWDOWN з першим початковим рівнем
SL/TP, якого ціна досягнула б після цього закриття.

Майбутні бари використовуються лише для контрфактичної мітки після закриття
і ніколи не використовуються як production-умова виходу.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)
from run_t105_05_algorithm_workspace_candidate_f_production_profit_drawdown_anatomy_2025_check import (  # noqa: E402
    AnatomyRuntime,
    _anatomy_rows,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)

TEST_ID = "T105-06"
EPSILON = 1e-9

EXPECTED_TRADES = 59
EXPECTED_WINS = 40
EXPECTED_LOSSES = 18
EXPECTED_BREAK_EVEN = 1
EXPECTED_PD = 48
EXPECTED_SL = 9
EXPECTED_TP = 2
EXPECTED_SAVED_FUTURE_SL = 35
EXPECTED_CUT_FUTURE_TP = 13


def _build_runtime() -> AnatomyRuntime:
    """Побудувати той самий фактичний cTrader 2025 runtime, що й T105-05."""
    assert_frozen_oos_snapshot()
    workspace = frozen_oos_workspace()
    workspace.broker = "CTRADER"
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
    workspace.set_replay_settings(replay_settings)

    runtime = AnatomyRuntime(
        workspace,
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
    return runtime


def _fmt_money(value: float) -> str:
    return f"{value:+.4f}"


def _fmt_r(value: float) -> str:
    return f"{value:+.4f}"


def main() -> None:
    runtime = _build_runtime()
    summary = runtime.historical_summary
    assert summary is not None

    assert summary.opened_trades == EXPECTED_TRADES
    assert summary.winning_trades == EXPECTED_WINS
    assert summary.losing_trades == EXPECTED_LOSSES
    assert summary.break_even_trades == EXPECTED_BREAK_EVEN
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == EXPECTED_PD
    assert summary.close_reason_count("STOP_LOSS") == EXPECTED_SL
    assert summary.close_reason_count("TAKE_PROFIT") == EXPECTED_TP

    rows = _anatomy_rows(runtime)
    assert len(rows) == EXPECTED_PD

    saved_sl = tuple(row for row in rows if row.fate == "PD_SAVED_FUTURE_SL")
    cut_tp = tuple(row for row in rows if row.fate == "PD_CUT_FUTURE_TP")
    unresolved = tuple(row for row in rows if row.fate == "UNRESOLVED_BY_2025_END")

    assert len(saved_sl) == EXPECTED_SAVED_FUTURE_SL
    assert len(cut_tp) == EXPECTED_CUT_FUTURE_TP
    assert not unresolved
    assert len(saved_sl) + len(cut_tp) == EXPECTED_PD

    actual_pd_pnl = math.fsum(row.trade.final_profit for row in rows)
    actual_pd_r = math.fsum(row.trade.final_profit / row.risk_usd for row in rows)

    counterfactual_sltp_pnl = math.fsum(-row.risk_usd for row in saved_sl) + math.fsum(
        2.0 * row.risk_usd for row in cut_tp
    )
    counterfactual_sltp_r = -float(len(saved_sl)) + 2.0 * float(len(cut_tp))

    saved_loss_value = math.fsum(
        row.trade.final_profit + row.risk_usd for row in saved_sl
    )
    saved_loss_r = math.fsum(
        row.trade.final_profit / row.risk_usd + 1.0 for row in saved_sl
    )

    cut_profit_value = math.fsum(
        2.0 * row.risk_usd - row.trade.final_profit for row in cut_tp
    )
    cut_profit_r = math.fsum(
        2.0 - row.trade.final_profit / row.risk_usd for row in cut_tp
    )

    net_pd_contribution = actual_pd_pnl - counterfactual_sltp_pnl
    net_pd_contribution_r = actual_pd_r - counterfactual_sltp_r

    assert math.isclose(
        net_pd_contribution,
        saved_loss_value - cut_profit_value,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert math.isclose(
        net_pd_contribution_r,
        saved_loss_r - cut_profit_r,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    positive_rows = tuple(row for row in rows if row.trade.final_profit > EPSILON)
    negative_rows = tuple(row for row in rows if row.trade.final_profit < -EPSILON)
    zero_rows = tuple(row for row in rows if abs(row.trade.final_profit) <= EPSILON)
    assert len(positive_rows) == 38
    assert len(negative_rows) == 9
    assert len(zero_rows) == 1

    saved_actual_pnl = math.fsum(row.trade.final_profit for row in saved_sl)
    cut_actual_pnl = math.fsum(row.trade.final_profit for row in cut_tp)
    saved_counterfactual_pnl = -math.fsum(row.risk_usd for row in saved_sl)
    cut_counterfactual_pnl = math.fsum(2.0 * row.risk_usd for row in cut_tp)

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    assert all(
        math.isfinite(value)
        for value in (
            actual_pd_pnl,
            actual_pd_r,
            counterfactual_sltp_pnl,
            counterfactual_sltp_r,
            saved_loss_value,
            saved_loss_r,
            cut_profit_value,
            cut_profit_r,
            net_pd_contribution,
            net_pd_contribution_r,
        )
    )

    print("T105-06 Candidate F Profit Drawdown Counterfactual PnL 2025 result")
    print("  mode=TEST_ONLY_ACTUAL_WORKSPACE_RUNTIME_PD_COUNTERFACTUAL_PNL")
    print("  source=CTRADER_EURUSD_M1_2025")
    print("  profile=LGE_CANDIDATE_F_SMOOTHED_R1")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(
        "  closes="
        f"profit_drawdown:{EXPECTED_PD},stop_loss:{EXPECTED_SL},"
        f"take_profit:{EXPECTED_TP}"
    )
    print(
        "  pd_fate="
        f"saved_future_sl:{len(saved_sl)},cut_future_tp:{len(cut_tp)},"
        f"unresolved:{len(unresolved)}"
    )
    print(
        "  factual_pd_pnl="
        f"usd:{_fmt_money(actual_pd_pnl)},R_sum:{_fmt_r(actual_pd_r)}"
    )
    print(
        "  counterfactual_initial_sltp_pnl="
        f"usd:{_fmt_money(counterfactual_sltp_pnl)},"
        f"R_sum:{_fmt_r(counterfactual_sltp_r)}"
    )
    print(
        "  saved_sl_group="
        f"trades:{len(saved_sl)},actual_usd:{_fmt_money(saved_actual_pnl)},"
        f"counterfactual_sl_usd:{_fmt_money(saved_counterfactual_pnl)},"
        f"saved_loss_value_usd:{_fmt_money(saved_loss_value)},"
        f"saved_loss_R:{_fmt_r(saved_loss_r)}"
    )
    print(
        "  cut_tp_group="
        f"trades:{len(cut_tp)},actual_usd:{_fmt_money(cut_actual_pnl)},"
        f"counterfactual_tp_usd:{_fmt_money(cut_counterfactual_pnl)},"
        f"cut_profit_value_usd:{_fmt_money(cut_profit_value)},"
        f"cut_profit_R:{_fmt_r(cut_profit_r)}"
    )
    print(
        "  pd_net_contribution_vs_initial_sltp="
        f"usd:{_fmt_money(net_pd_contribution)},"
        f"R_sum:{_fmt_r(net_pd_contribution_r)}"
    )
    print(
        "  pd_actual_exit_signs="
        f"positive:{len(positive_rows)},negative:{len(negative_rows)},"
        f"zero:{len(zero_rows)}"
    )
    print("  identity_net_equals_saved_minus_cut=True")
    print("  post_close_future_used_for_counterfactual_label_only=True")
    print("  future_price_used_as_production_exit_gate=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_06_CANDIDATE_F_PROFIT_DRAWDOWN_COUNTERFACTUAL_PNL_2025=OK")


if __name__ == "__main__":
    main()
