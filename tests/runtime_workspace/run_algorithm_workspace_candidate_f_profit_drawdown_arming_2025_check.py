# -*- coding: utf-8 -*-
"""RoadMap102 / 6B: diagnostic-only arming для Profit Drawdown OOS 2025.

Runner повторює frozen Candidate F Replay 2025 і аналізує фактичний mark-to-close
шлях тих самих 48 позицій, які production закрив через Profit Drawdown. Жоден
exit не переграється: рівні 0.10R/0.20R/0.30R/0.50R лише показують, чи був би
мінімальний meaningful profit досягнутий ДО фактичного production exit.
Події після фактичного close не використовуються, counterfactual trades/exits
не створюються.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    FrozenOosRuntime,
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)

M15_SECONDS = 15 * 60
PROFIT_DRAWDOWN_PERCENT = 30.0
ARMING_LEVELS_R = (0.10, 0.20, 0.30, 0.50)
NUMERIC_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class ObservedArmingCase:
    """Один arming-рівень на фактичному шляху до production close."""

    reached: bool
    arm_event_index: int | None
    arm_delay_m15: float | None
    arm_profit_r: float | None
    post_arm_peak_mark_r: float | None
    post_arm_trough_mark_r: float | None
    drawdown_triggered: bool
    trigger_delay_m15: float | None
    trigger_profit_r: float | None


def _risk_usd(trade: WorkspaceHistoricalTradeDiagnostic) -> float:
    """Повернути initial 1R у USD для фактичного virtual volume."""
    risk = trade.stop_loss_distance * trade.volume
    if risk <= 0.0:
        raise AssertionError("Initial risk must be positive")
    return risk


def _mark_profit(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> float:
    """Відтворити production executable mark-to-close PnL на M1 event."""
    close_price = event.bid if trade.direction == "BUY" else event.ask
    direction = 1.0 if trade.direction == "BUY" else -1.0
    return (
        (close_price - trade.entry_price)
        * trade.volume
        * direction
    )


def _trade_events(
    trade: WorkspaceHistoricalTradeDiagnostic,
    source_events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceMarketEvent, ...]:
    """Повернути тільки фактично спостережений M1 шлях позиції до close."""
    selected = tuple(
        event
        for event in source_events
        if trade.entry_timestamp <= event.timestamp <= trade.close_timestamp
    )
    if not selected:
        raise AssertionError("Trade has no observed M1 events")
    if selected[0].timestamp != trade.entry_timestamp:
        raise AssertionError("Trade entry event is missing from M1 path")
    if selected[-1].timestamp != trade.close_timestamp:
        raise AssertionError("Trade close event is missing from M1 path")
    return selected


def _observed_arming_case(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    level_r: float,
) -> ObservedArmingCase:
    """Оцінити arming і старий 30% drawdown лише на observed production path."""
    risk_usd = _risk_usd(trade)
    threshold_usd = risk_usd * level_r
    mark_profits = tuple(_mark_profit(trade, event) for event in events)

    peak_profit = 0.0
    arm_index: int | None = None
    trigger_index: int | None = None
    for index, current_profit in enumerate(mark_profits):
        peak_profit = max(peak_profit, current_profit, 0.0)
        if arm_index is None and peak_profit + NUMERIC_EPSILON >= threshold_usd:
            arm_index = index
        if arm_index is None or peak_profit <= 0.0:
            continue
        drawdown = (peak_profit - current_profit) / peak_profit * 100.0
        if drawdown > PROFIT_DRAWDOWN_PERCENT:
            trigger_index = index
            break

    if arm_index is None:
        return ObservedArmingCase(
            reached=False,
            arm_event_index=None,
            arm_delay_m15=None,
            arm_profit_r=None,
            post_arm_peak_mark_r=None,
            post_arm_trough_mark_r=None,
            drawdown_triggered=False,
            trigger_delay_m15=None,
            trigger_profit_r=None,
        )

    post_arm_marks = mark_profits[arm_index:]
    arm_event = events[arm_index]
    arm_delay_m15 = (
        (arm_event.timestamp - trade.entry_timestamp).total_seconds()
        / M15_SECONDS
    )
    trigger_delay_m15: float | None = None
    trigger_profit_r: float | None = None
    if trigger_index is not None:
        trigger_event = events[trigger_index]
        trigger_delay_m15 = (
            (trigger_event.timestamp - arm_event.timestamp).total_seconds()
            / M15_SECONDS
        )
        trigger_profit_r = mark_profits[trigger_index] / risk_usd

    return ObservedArmingCase(
        reached=True,
        arm_event_index=arm_index,
        arm_delay_m15=arm_delay_m15,
        arm_profit_r=mark_profits[arm_index] / risk_usd,
        post_arm_peak_mark_r=max(post_arm_marks) / risk_usd,
        post_arm_trough_mark_r=min(post_arm_marks) / risk_usd,
        drawdown_triggered=trigger_index is not None,
        trigger_delay_m15=trigger_delay_m15,
        trigger_profit_r=trigger_profit_r,
    )


def _baseline_drawdown_close_matches(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> bool:
    """Перевірити реконструкцію чинного minimum_profit=0 Profit Drawdown."""
    peak_profit = 0.0
    for index, event in enumerate(events):
        current_profit = _mark_profit(trade, event)
        peak_profit = max(peak_profit, current_profit, 0.0)
        if peak_profit <= 0.0:
            continue
        drawdown = (peak_profit - current_profit) / peak_profit * 100.0
        if drawdown > PROFIT_DRAWDOWN_PERCENT:
            return index == len(events) - 1
    return False


def _mean(values: tuple[float, ...]) -> float | None:
    """Повернути arithmetic mean або None для порожньої вибірки."""
    if not values:
        return None
    return sum(values) / len(values)


def _fmt(value: float | None, digits: int = 3) -> str:
    """Стисло форматувати optional diagnostic number."""
    if value is None:
        return "NONE"
    return f"{value:.{digits}f}"


def main() -> None:
    """Запустити frozen Replay і надрукувати arming anatomy без нових exits."""
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
    assert len(trades) == 59

    source_events = tuple(
        event
        for window in session.execution_windows
        for event in window
    )
    assert source_events
    assert all(
        earlier.timestamp < later.timestamp
        for earlier, later in zip(source_events, source_events[1:])
    )

    pd_trades = tuple(
        trade for trade in trades if trade.close_reason == "PROFIT_DRAWDOWN"
    )
    assert len(pd_trades) == 48
    pd_positive = tuple(trade for trade in pd_trades if trade.final_profit > 0.0)
    pd_negative = tuple(trade for trade in pd_trades if trade.final_profit < 0.0)
    pd_zero = tuple(trade for trade in pd_trades if trade.final_profit == 0.0)
    assert (len(pd_positive), len(pd_negative), len(pd_zero)) == (29, 18, 1)

    paths = {
        trade.position_id: _trade_events(trade, source_events)
        for trade in pd_trades
    }
    assert all(
        _baseline_drawdown_close_matches(trade, paths[trade.position_id])
        for trade in pd_trades
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Profit Drawdown Arming 2025 result")
    print("  mode=FROZEN_EXIT_ARMING_ANATOMY_DIAGNOSTIC_ONLY")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f}"
    )
    print("  production_profit_drawdown=30.0%")
    print("  production_minimum_profit=0.0")
    print("  arming_levels_r=0.10,0.20,0.30,0.50")
    print(
        "  production_pd_trades="
        f"48,positive:{len(pd_positive)},negative:{len(pd_negative)},"
        f"zero:{len(pd_zero)}"
    )
    print("  baseline_mark_path_reconstruction_matches=48/48")
    print("  observed_path_stops_at_production_close=True")

    for level_r in ARMING_LEVELS_R:
        cases = {
            trade.position_id: _observed_arming_case(
                trade,
                paths[trade.position_id],
                level_r,
            )
            for trade in pd_trades
        }
        reached = tuple(
            trade for trade in pd_trades if cases[trade.position_id].reached
        )
        not_reached = tuple(
            trade for trade in pd_trades if not cases[trade.position_id].reached
        )
        positive_reached = tuple(
            trade for trade in pd_positive if cases[trade.position_id].reached
        )
        positive_not_reached = tuple(
            trade for trade in pd_positive if not cases[trade.position_id].reached
        )
        negative_reached = tuple(
            trade for trade in pd_negative if cases[trade.position_id].reached
        )
        negative_not_reached = tuple(
            trade for trade in pd_negative if not cases[trade.position_id].reached
        )
        zero_reached = tuple(
            trade for trade in pd_zero if cases[trade.position_id].reached
        )
        drawdown_triggered = tuple(
            trade
            for trade in reached
            if cases[trade.position_id].drawdown_triggered
        )

        arm_delays = tuple(
            case.arm_delay_m15
            for case in cases.values()
            if case.arm_delay_m15 is not None
        )
        post_arm_peak = tuple(
            case.post_arm_peak_mark_r
            for case in cases.values()
            if case.post_arm_peak_mark_r is not None
        )
        post_arm_trough = tuple(
            case.post_arm_trough_mark_r
            for case in cases.values()
            if case.post_arm_trough_mark_r is not None
        )
        trigger_profit = tuple(
            case.trigger_profit_r
            for case in cases.values()
            if case.trigger_profit_r is not None
        )

        print(f"  arm_{level_r:.2f}R:")
        print(
            "    reached_before_production_exit="
            f"{len(reached)}/48,not_reached:{len(not_reached)}"
        )
        print(
            "    current_positive_pd="
            f"armed:{len(positive_reached)},not_armed:{len(positive_not_reached)}"
        )
        print(
            "    current_negative_pd="
            f"armed:{len(negative_reached)},not_armed:{len(negative_not_reached)}"
        )
        print(
            "    current_zero_pd="
            f"armed:{len(zero_reached)},not_armed:{len(pd_zero) - len(zero_reached)}"
        )
        print(
            "    old_30pct_trigger_within_observed_path="
            f"{len(drawdown_triggered)}/{len(reached)}"
        )
        print(
            "    arm_delay_m15="
            f"mean:{_fmt(_mean(arm_delays), 2)},"
            f"median:{_fmt(median(arm_delays) if arm_delays else None, 2)}"
        )
        print(
            "    post_arm_mark_path_r="
            f"peak_mean:{_fmt(_mean(post_arm_peak))},"
            f"trough_mean:{_fmt(_mean(post_arm_trough))},"
            f"trigger_profit_mean:{_fmt(_mean(trigger_profit))}"
        )

    print("  counterfactual_trades_created=False")
    print("  counterfactual_exits_created=False")
    print("  future_after_production_close_used=False")
    print("  exit_logic_changed=False")
    print("  entry_logic_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  alligator_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_PROFIT_DRAWDOWN_ARMING_2025_CHECK=OK")


if __name__ == "__main__":
    main()
