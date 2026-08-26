# -*- coding: utf-8 -*-
"""RoadMap102 / 6A: анатомія exit на frozen Candidate F OOS 2025.

Diagnostic-only runner повторює незмінний frozen Candidate F Replay 2025 та
аналізує вже закриті virtual positions. Жоден entry/exit threshold не
змінюється, альтернативні exit не створюються, future data не використовується
як gate. Мета — виміряти initial risk R, MFE/MAE, realized R, holding time,
peak capture та поведінку Profit Drawdown для тих самих production entries.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from tests.runtime_workspace.run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

M15_SECONDS = 15 * 60
NUMERIC_PEAK_EPSILON_USD = 1e-9


def _risk_usd(trade: WorkspaceHistoricalTradeDiagnostic) -> float:
    """Повернути initial 1R у USD для фактичного virtual volume."""
    return trade.stop_loss_distance * trade.volume


def _signed_r(value: float, risk_usd: float) -> float:
    """Нормалізувати USD result до initial risk R."""
    if risk_usd <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return value / risk_usd


def _mfe_bin(mfe_r: float) -> str:
    """Класифікувати MFE за наперед визначеними R-діапазонами."""
    if mfe_r < 0.5:
        return "<0.5R"
    if mfe_r < 1.0:
        return "0.5-1R"
    if mfe_r < 1.5:
        return "1-1.5R"
    if mfe_r < 2.0:
        return "1.5-2R"
    return ">=2R"


def _capture_ratio(trade: WorkspaceHistoricalTradeDiagnostic) -> float | None:
    """Повернути realized/MFE для прибуткової угоди з додатним MFE."""
    if trade.final_profit <= 0.0 or trade.maximum_favorable_excursion <= 0.0:
        return None
    return trade.final_profit / trade.maximum_favorable_excursion


def _profit_drawdown_percent(
    trade: WorkspaceHistoricalTradeDiagnostic,
) -> float | None:
    """Повернути фактичний відкат від mark-to-close peak до exit."""
    if trade.peak_profit <= NUMERIC_PEAK_EPSILON_USD:
        return None
    pullback = trade.peak_profit - trade.final_profit
    return pullback / trade.peak_profit * 100.0


def _fmt(value: float | None, digits: int = 3) -> str:
    """Стисло форматувати optional diagnostic number."""
    if value is None:
        return "NONE"
    return f"{value:.{digits}f}"


def _reason_summary(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    reason: str,
) -> str:
    """Повернути стислий агрегат одного close reason."""
    selected = tuple(trade for trade in trades if trade.close_reason == reason)
    if not selected:
        return "count:0"
    realized = [trade.final_profit for trade in selected]
    mfe_r = [
        _signed_r(trade.maximum_favorable_excursion, _risk_usd(trade))
        for trade in selected
    ]
    mae_r = [
        _signed_r(trade.maximum_adverse_excursion, _risk_usd(trade))
        for trade in selected
    ]
    realized_r = [_signed_r(trade.final_profit, _risk_usd(trade)) for trade in selected]
    return (
        f"count:{len(selected)},net:{sum(realized):+.2f},"
        f"avg_realized_r:{sum(realized_r) / len(realized_r):+.3f},"
        f"avg_mfe_r:{sum(mfe_r) / len(mfe_r):.3f},"
        f"avg_mae_r:{sum(mae_r) / len(mae_r):+.3f}"
    )


def main() -> None:
    """Запустити frozen Replay один раз і надрукувати exit anatomy."""
    assert_frozen_oos_snapshot()

    runtime = FrozenOosRuntime(
        frozen_oos_workspace(),
        algorithm_factory=create_registered_workspace_algorithm,
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
    assert len(trades) == summary.opened_trades == 59
    assert all(trade.close_timestamp >= trade.entry_timestamp for trade in trades)
    assert all(_risk_usd(trade) > 0.0 for trade in trades)
    assert all(trade.take_profit_distance > 0.0 for trade in trades)

    reason_counts = Counter(trade.close_reason for trade in trades)
    mfe_bins = Counter(
        _mfe_bin(_signed_r(trade.maximum_favorable_excursion, _risk_usd(trade)))
        for trade in trades
    )

    profitable = tuple(trade for trade in trades if trade.final_profit > 0.0)
    losing = tuple(trade for trade in trades if trade.final_profit < 0.0)
    break_even = tuple(trade for trade in trades if trade.final_profit == 0.0)
    capture_values = tuple(
        value for trade in profitable if (value := _capture_ratio(trade)) is not None
    )
    aggregate_capture = sum(trade.final_profit for trade in profitable) / sum(
        trade.maximum_favorable_excursion for trade in profitable
    )

    pd_trades = tuple(
        trade for trade in trades if trade.close_reason == "PROFIT_DRAWDOWN"
    )
    pd_positive = tuple(trade for trade in pd_trades if trade.final_profit > 0.0)
    pd_zero = tuple(trade for trade in pd_trades if trade.final_profit == 0.0)
    pd_negative = tuple(trade for trade in pd_trades if trade.final_profit < 0.0)
    pd_tiny_peak = tuple(
        trade
        for trade in pd_trades
        if 0.0 < trade.peak_profit <= NUMERIC_PEAK_EPSILON_USD
    )
    pd_drawdown_values = tuple(
        value
        for trade in pd_trades
        if (value := _profit_drawdown_percent(trade)) is not None
    )

    holding_m15_equivalent = tuple(
        trade.holding_seconds / M15_SECONDS for trade in trades
    )
    tp_r_multiples = tuple(
        trade.take_profit_distance / trade.stop_loss_distance for trade in trades
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Exit Potential 2025 result")
    print("  mode=FROZEN_ENTRY_EXIT_ANATOMY_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print("  entry_logic_changed=False")
    print("  exit_logic_changed=False")
    print("  alternative_exits_created=False")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  stop_policy=SIGNAL_BAR_RANGE_1R")
    print("  take_profit_policy=SIGNAL_BAR_RANGE_2R")
    print("  profit_drawdown_percent=30.0")
    print(
        "  close_reasons="
        f"sl:{reason_counts['STOP_LOSS']},tp:{reason_counts['TAKE_PROFIT']},"
        f"profit_drawdown:{reason_counts['PROFIT_DRAWDOWN']},"
        f"session_end:{reason_counts['SESSION_END']}"
    )
    print(
        "  outcome_counts="
        f"positive:{len(profitable)},negative:{len(losing)},"
        f"zero:{len(break_even)}"
    )
    print(
        "  tp_r_multiple="
        f"min:{min(tp_r_multiples):.3f},median:{median(tp_r_multiples):.3f},"
        f"max:{max(tp_r_multiples):.3f}"
    )
    print(
        "  mfe_distribution="
        f"<0.5R:{mfe_bins['<0.5R']},"
        f"0.5-1R:{mfe_bins['0.5-1R']},"
        f"1-1.5R:{mfe_bins['1-1.5R']},"
        f"1.5-2R:{mfe_bins['1.5-2R']},"
        f">=2R:{mfe_bins['>=2R']}"
    )
    print(
        "  positive_capture="
        f"trades:{len(capture_values)},"
        f"aggregate_realized_over_mfe:{aggregate_capture:.3f},"
        f"median_trade_capture:{median(capture_values):.3f}"
    )
    print(
        "  holding_m15_equivalent="
        f"mean:{sum(holding_m15_equivalent) / len(holding_m15_equivalent):.2f},"
        f"median:{median(holding_m15_equivalent):.2f},"
        f"max:{max(holding_m15_equivalent):.2f}"
    )
    print(
        "  profit_drawdown_outcomes="
        f"positive:{len(pd_positive)},zero:{len(pd_zero)},negative:{len(pd_negative)},"
        f"negative_share:{len(pd_negative) / len(pd_trades) * 100.0:.1f}%"
    )
    print(
        "  profit_drawdown_numeric_tiny_peak="
        f"count:{len(pd_tiny_peak)},epsilon_usd:{NUMERIC_PEAK_EPSILON_USD:g}"
    )
    print(
        "  profit_drawdown_actual_pullback="
        f"stable_peak_count:{len(pd_drawdown_values)},"
        f"mean:{sum(pd_drawdown_values) / len(pd_drawdown_values):.2f}%,"
        f"median:{median(pd_drawdown_values):.2f}%"
    )
    print(f"  stop_loss_summary={_reason_summary(trades, 'STOP_LOSS')}")
    print(f"  take_profit_summary={_reason_summary(trades, 'TAKE_PROFIT')}")
    print("  profit_drawdown_summary=" f"{_reason_summary(trades, 'PROFIT_DRAWDOWN')}")
    print("  chronological_trade_anatomy:")

    for index, trade in enumerate(trades, start=1):
        risk_usd = _risk_usd(trade)
        realized_r = _signed_r(trade.final_profit, risk_usd)
        mfe_r = _signed_r(trade.maximum_favorable_excursion, risk_usd)
        mae_r = _signed_r(trade.maximum_adverse_excursion, risk_usd)
        peak_r = _signed_r(trade.peak_profit, risk_usd)
        holding_bars = trade.holding_seconds / M15_SECONDS
        capture = _capture_ratio(trade)
        pullback_pct = _profit_drawdown_percent(trade)
        print(
            f"    {index:02d}. {trade.signal_timestamp.isoformat()} "
            f"{trade.direction} close:{trade.close_reason} "
            f"risk:${risk_usd:.2f}"
            f" realized:{trade.final_profit:+.2f}/{realized_r:+.3f}R "
            f"mfe:{trade.maximum_favorable_excursion:+.2f}/{mfe_r:.3f}R "
            f"mae:{trade.maximum_adverse_excursion:+.2f}/{mae_r:+.3f}R "
            f"peak:{trade.peak_profit:+.2f}/{peak_r:.3f}R "
            f"capture:{_fmt(capture)} "
            f"pd_pullback:{_fmt(pullback_pct, 1)}% "
            f"holding:{holding_bars:.2f}M15eq"
        )

    print("  completed_bars_only=True")
    print("  future_price_used_as_exit_gate=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_EXIT_POTENTIAL_2025_CHECK=OK")


if __name__ == "__main__":
    main()
