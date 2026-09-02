# -*- coding: utf-8 -*-
"""RoadMap103 / 7M: causal Structural SL/TP paired diagnostic 2025.

Runner спочатку повторює production Candidate F після 6K без змін, а потім
для тих самих 59 фактично відкритих угод окремо моделює два paired
counterfactual варіанти protection: мінімум 12 pips та 24 pips.

Support/resistance визначаються тільки за завершеними M15 bars, доступними
на signal timestamp. Рівень — останній підтверджений 2-left/2-right pivot у
40-bar lookback. Для SL використовується відповідний рівень structure плюс
1 pip buffer і мінімальна відстань 12/24 pips. Якщо відповідного рівня немає,
SL лишається production. TP ставиться трохи перед протилежним structural
рівнем; якщо придатного рівня немає, TP = 2 x фактична відстань SL.
TP не переноситься далі за ціною.

Це paired diagnostic: entry timestamp/price/signal фіксуються за production
baseline. Змінена тривалість position не відкриває нових угод і не блокує
інші baseline entries через capacity. Тому net/PF/DD варіантів є
діагностичними, а не production portfolio backtest.
"""

from __future__ import annotations

import csv
import math
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_algorithm_workspace_candidate_f_entry_exit_context_2025_check import (  # noqa
    EntryExitContextRuntime,
    _assert_baseline,
)
from run_algorithm_workspace_candidate_f_frozen_oos_2025_check import (  # noqa: E402
    assert_frozen_oos_snapshot,
    frozen_oos_workspace,
)
from run_algorithm_workspace_candidate_f_trend_lifecycle_entry_quality_2025_check import (  # noqa: E402,E501
    PIVOT_LOOKBACK_BARS,
    PIVOT_SIDE_BARS,
    PivotLevel,
    _last_confirmed_pivot,
)

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_historical_summary import (  # noqa: E402
    WorkspaceHistoricalReplaySummary,
    build_workspace_historical_replay_summary,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_replay_execution import (  # noqa: E402
    WorkspaceReplayExecutionEngine,
    WorkspaceReplayExecutionEvent,
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

PIP = 0.0001
STRUCTURE_BUFFER_PIPS = 1.0
STRUCTURE_TOUCH_TOLERANCE_PIPS = 1.0
SL_FLOOR_VARIANTS_PIPS = (12.0, 24.0)

OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "LavrGPT05" / "RM103_7M_Structural_SL_TP_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_structural_sl_tp_2025.csv"

FOCUS_CASES = (
    datetime.fromisoformat("2025-03-05T12:30:00+00:00"),
    datetime.fromisoformat("2025-04-08T06:30:00+00:00"),
    datetime.fromisoformat("2025-04-11T17:45:00+00:00"),
    datetime.fromisoformat("2025-04-21T07:30:00+00:00"),
    datetime.fromisoformat("2025-05-13T07:30:00+00:00"),
    datetime.fromisoformat("2025-05-29T12:15:00+00:00"),
    datetime.fromisoformat("2025-05-30T08:45:00+00:00"),
    datetime.fromisoformat("2025-07-29T00:45:00+00:00"),
    datetime.fromisoformat("2025-08-05T11:30:00+00:00"),
    datetime.fromisoformat("2025-12-17T11:30:00+00:00"),
)


@dataclass(frozen=True, slots=True)
class StructuralLevel:
    """Causal pivot-рівень плюс diagnostic touch count."""

    kind: str
    timestamp: datetime
    price: float
    age_bars: int
    touches: int


@dataclass(frozen=True, slots=True)
class StructuralProtectionPlan:
    """Protection рівні одного fixed-entry paired counterfactual."""

    floor_pips: float
    entry_price: float
    support: StructuralLevel | None
    resistance: StructuralLevel | None
    stop_loss: float
    take_profit: float
    stop_distance: float
    take_distance: float
    stop_source: str
    take_source: str
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class PairedTradeResult:
    """Baseline trade, causal plan і один simulated counterfactual result."""

    baseline: WorkspaceHistoricalTradeDiagnostic
    plan: StructuralProtectionPlan
    counterfactual: WorkspaceHistoricalTradeDiagnostic


class StructuralSlTpRuntime(EntryExitContextRuntime):
    """7K Runtime plus immutable M1 guard-state evidence for paired replay."""

    def __init__(self, *args, **kwargs) -> None:
        self.execution_guard_state: dict[datetime, bool] = {}
        super().__init__(*args, **kwargs)

    def _advance_replay_execution(self, event: WorkspaceMarketEvent) -> None:
        self.execution_guard_state[event.timestamp] = bool(
            self.context.spread_ok and self.context.signal_allowed
        )
        super()._advance_replay_execution(event)


class StructuralProtectionExecutionEngine(WorkspaceReplayExecutionEngine):
    """Test-only engine that installs one precomputed protection plan at fill."""

    def __init__(self, *args, plan: StructuralProtectionPlan, **kwargs) -> None:
        self._structural_plan = plan
        super().__init__(*args, **kwargs)

    def _fill_pending_order(self, pending, event) -> WorkspaceReplayExecutionEvent:
        lifecycle = super()._fill_pending_order(pending, event)
        if lifecycle.event != "VIRTUAL_POSITION_OPENED":
            return lifecycle
        active = tuple(position for position in self._positions if position.active)
        assert len(active) == 1
        position = active[0]
        plan = self._structural_plan
        assert math.isclose(position.entry_price, plan.entry_price, abs_tol=1e-12)
        position.stop_loss = plan.stop_loss
        position.take_profit = plan.take_profit
        self._replace_order_row(
            position.order_id,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
        )
        return lifecycle


def _flatten_execution_events(
    runtime: StructuralSlTpRuntime,
) -> tuple[WorkspaceMarketEvent, ...]:
    session = runtime.replay_session
    assert session is not None
    events: list[WorkspaceMarketEvent] = []
    for index in range(len(session.events)):
        events.extend(session.execution_events_for_index(index))
    result = tuple(events)
    assert result
    assert all(
        result[index].timestamp <= result[index + 1].timestamp
        for index in range(len(result) - 1)
    )
    return result


def _touch_count(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    pivot: PivotLevel,
) -> int:
    start = max(0, signal_index - PIVOT_LOOKBACK_BARS)
    tolerance = STRUCTURE_TOUCH_TOLERANCE_PIPS * PIP
    if pivot.kind == "SUPPORT":
        return sum(
            abs(event.low - pivot.price) <= tolerance
            for event in events[start : signal_index + 1]  # noqa: E203
        )
    assert pivot.kind == "RESISTANCE"
    return sum(
        abs(event.high - pivot.price) <= tolerance
        for event in events[start : signal_index + 1]  # noqa: E203
    )


def _enrich_level(
    events: tuple[WorkspaceMarketEvent, ...],
    signal_index: int,
    pivot: PivotLevel | None,
) -> StructuralLevel | None:
    if pivot is None:
        return None
    return StructuralLevel(
        kind=pivot.kind,
        timestamp=pivot.timestamp,
        price=pivot.price,
        age_bars=pivot.age_bars,
        touches=_touch_count(events, signal_index, pivot),
    )


def _directional_price(
    direction: str,
    entry_price: float,
    distance: float,
    *,
    favorable: bool,
) -> float:
    sign = 1.0 if direction == "BUY" else -1.0
    if not favorable:
        sign = -sign
    return entry_price + sign * distance


def _build_plan(
    trade: WorkspaceHistoricalTradeDiagnostic,
    strategy_events: tuple[WorkspaceMarketEvent, ...],
    event_index: dict[datetime, int],
    *,
    floor_pips: float,
) -> StructuralProtectionPlan:
    signal_index = event_index.get(trade.signal_timestamp)
    assert signal_index is not None
    assert signal_index >= PIVOT_SIDE_BARS
    entry = trade.entry_price

    support_pivot = _last_confirmed_pivot(
        strategy_events,
        signal_index,
        kind="SUPPORT",
        entry_price=entry,
    )
    resistance_pivot = _last_confirmed_pivot(
        strategy_events,
        signal_index,
        kind="RESISTANCE",
        entry_price=entry,
    )
    support = _enrich_level(strategy_events, signal_index, support_pivot)
    resistance = _enrich_level(strategy_events, signal_index, resistance_pivot)

    buffer_distance = STRUCTURE_BUFFER_PIPS * PIP
    floor_distance = floor_pips * PIP
    stop_level = support if trade.direction == "BUY" else resistance
    if stop_level is None:
        stop_distance = trade.stop_loss_distance
        stop_loss = _directional_price(
            trade.direction,
            entry,
            stop_distance,
            favorable=False,
        )
        stop_source = "FALLBACK_PRODUCTION"
    else:
        if trade.direction == "BUY":
            structural_stop = stop_level.price - buffer_distance
            usable = structural_stop < entry
        else:
            structural_stop = stop_level.price + buffer_distance
            usable = structural_stop > entry
        if not usable:
            stop_distance = trade.stop_loss_distance
            stop_loss = _directional_price(
                trade.direction,
                entry,
                stop_distance,
                favorable=False,
            )
            stop_source = "FALLBACK_PRODUCTION"
        else:
            structural_distance = abs(entry - structural_stop)
            stop_distance = max(structural_distance, floor_distance)
            stop_loss = _directional_price(
                trade.direction,
                entry,
                stop_distance,
                favorable=False,
            )
            stop_source = "STRUCTURE"

    take_level = resistance if trade.direction == "BUY" else support
    if take_level is not None:
        if trade.direction == "BUY":
            structural_take = take_level.price - buffer_distance
            usable_take = structural_take > entry
        else:
            structural_take = take_level.price + buffer_distance
            usable_take = structural_take < entry
    else:
        structural_take = 0.0
        usable_take = False

    if usable_take:
        take_profit = structural_take
        take_distance = abs(take_profit - entry)
        take_source = "STRUCTURE"
    else:
        take_distance = stop_distance * 2.0
        take_profit = _directional_price(
            trade.direction,
            entry,
            take_distance,
            favorable=True,
        )
        take_source = "FALLBACK_2R"

    assert stop_distance > 0.0
    assert take_distance > 0.0
    assert math.isfinite(stop_loss)
    assert math.isfinite(take_profit)
    if trade.direction == "BUY":
        assert stop_loss < entry < take_profit
    else:
        assert take_profit < entry < stop_loss

    return StructuralProtectionPlan(
        floor_pips=floor_pips,
        entry_price=entry,
        support=support,
        resistance=resistance,
        stop_loss=stop_loss,
        take_profit=take_profit,
        stop_distance=stop_distance,
        take_distance=take_distance,
        stop_source=stop_source,
        take_source=take_source,
        fallback_used=(stop_source != "STRUCTURE" or take_source != "STRUCTURE"),
    )


def _simulate_one(
    runtime: StructuralSlTpRuntime,
    trade: WorkspaceHistoricalTradeDiagnostic,
    record: WorkspaceSignalRecord,
    signal_event: WorkspaceMarketEvent,
    execution_events: tuple[WorkspaceMarketEvent, ...],
    execution_index: dict[datetime, int],
    plan: StructuralProtectionPlan,
) -> WorkspaceHistoricalTradeDiagnostic:
    engine = StructuralProtectionExecutionEngine(
        workspace_uid=runtime.context.workspace_uid,
        broker=runtime.context.broker,
        account_id=runtime.context.account_id,
        symbol=runtime.context.symbol,
        policy=WorkspaceReplayExecutionPolicy(
            fixed_volume=trade.volume,
            maximum_open_positions=1,
        ),
        initial_balance=runtime.context.replay_initial_balance,
        leverage=runtime.context.replay_leverage,
        plan=plan,
    )
    queued = engine.queue_signal(record, signal_event)
    assert queued and queued[0].event == "VIRTUAL_ORDER_CREATED"

    start_index = execution_index.get(trade.entry_timestamp)
    assert start_index is not None, trade.entry_timestamp
    guard = WorkspaceCandidateFNegativePdRecoveryGuard(
        runtime.profit_drawdown_guard.policy
    )
    last_event = execution_events[-1]
    for event in execution_events[start_index:]:
        engine.on_market_event(event)
        active_positions = engine.snapshot().active_positions
        guard.synchronize_active_positions(
            {position.position_id for position in active_positions}
        )
        decisions = tuple(
            guard.evaluate(
                position,
                timestamp=event.timestamp,
                runtime_ready=True,
                spread_guard_passed=runtime.execution_guard_state.get(
                    event.timestamp,
                    True,
                ),
            )
            for position in active_positions
        )
        engine.close_profit_drawdown(decisions, event)
        if engine.trade_diagnostics():
            break
    if not engine.trade_diagnostics():
        engine.complete(last_event)

    diagnostics = engine.trade_diagnostics()
    assert len(diagnostics) == 1
    result = replace(
        diagnostics[0],
        position_id=trade.position_id,
        order_id=trade.order_id,
    )
    assert result.signal_uid == trade.signal_uid
    assert result.signal_timestamp == trade.signal_timestamp
    assert result.entry_timestamp == trade.entry_timestamp
    assert math.isclose(result.entry_price, trade.entry_price, abs_tol=1e-12)
    return result


def _variant_summary(
    baseline_summary: WorkspaceHistoricalReplaySummary,
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> WorkspaceHistoricalReplaySummary:
    close_order = tuple(
        sorted(
            trades,
            key=lambda item: (
                item.close_timestamp,
                item.signal_timestamp,
                item.position_id,
            ),
        )
    )
    return build_workspace_historical_replay_summary(
        symbol=baseline_summary.symbol,
        timeframe=baseline_summary.timeframe,
        period_start=baseline_summary.period_start,
        period_end=baseline_summary.period_end,
        accepted_bars=baseline_summary.accepted_bars,
        skipped_bars=baseline_summary.skipped_bars,
        gaps=baseline_summary.gaps,
        spread=baseline_summary.spread,
        initial_balance=baseline_summary.initial_balance,
        signals=baseline_summary.signals,
        trades=close_order,
        source_timeframe=baseline_summary.source_timeframe,
    )


def _summary_text(summary: WorkspaceHistoricalReplaySummary) -> str:
    pf = "NONE" if summary.profit_factor is None else f"{summary.profit_factor:.4f}"
    return (
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"sl:{summary.close_reason_count('STOP_LOSS')},"
        f"tp:{summary.close_reason_count('TAKE_PROFIT')},"
        f"net:{summary.net_profit:+.2f},pf:{pf},dd:{summary.maximum_drawdown:.2f}"
    )


def _level_text(level: StructuralLevel | None) -> str:
    if level is None:
        return "NONE"
    return (
        f"{level.price:.5f}@{level.timestamp.isoformat()}"
        f"/age:{level.age_bars}/touch:{level.touches}"
    )


def _write_csv(
    baseline_trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    results_by_floor: dict[float, dict[str, PairedTradeResult]],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_utc",
        "entry_utc",
        "direction",
        "entry_price",
        "production_close_utc",
        "production_close_reason",
        "production_pnl",
        "production_sl_pips",
        "production_tp_pips",
        "support_utc",
        "support_price",
        "support_age_bars",
        "support_touches",
        "resistance_utc",
        "resistance_price",
        "resistance_age_bars",
        "resistance_touches",
        "sl12_price",
        "sl12_pips",
        "sl12_source",
        "tp12_price",
        "tp12_pips",
        "tp12_source",
        "result12_close_utc",
        "result12_reason",
        "result12_pnl",
        "sl24_price",
        "sl24_pips",
        "sl24_source",
        "tp24_price",
        "tp24_pips",
        "tp24_source",
        "result24_close_utc",
        "result24_reason",
        "result24_pnl",
        "focus_case",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for trade in baseline_trades:
            key = trade.signal_uid
            row12 = results_by_floor[12.0][key]
            row24 = results_by_floor[24.0][key]
            support = row12.plan.support
            resistance = row12.plan.resistance
            writer.writerow(
                {
                    "signal_utc": trade.signal_timestamp.isoformat(),
                    "entry_utc": trade.entry_timestamp.isoformat(),
                    "direction": trade.direction,
                    "entry_price": f"{trade.entry_price:.5f}",
                    "production_close_utc": trade.close_timestamp.isoformat(),
                    "production_close_reason": trade.close_reason,
                    "production_pnl": f"{trade.final_profit:.4f}",
                    "production_sl_pips": f"{trade.stop_loss_distance / PIP:.2f}",
                    "production_tp_pips": f"{trade.take_profit_distance / PIP:.2f}",
                    "support_utc": (
                        "" if support is None else support.timestamp.isoformat()
                    ),
                    "support_price": "" if support is None else f"{support.price:.5f}",
                    "support_age_bars": "" if support is None else support.age_bars,
                    "support_touches": "" if support is None else support.touches,
                    "resistance_utc": (
                        "" if resistance is None else resistance.timestamp.isoformat()
                    ),
                    "resistance_price": (
                        "" if resistance is None else f"{resistance.price:.5f}"
                    ),
                    "resistance_age_bars": (
                        "" if resistance is None else resistance.age_bars
                    ),
                    "resistance_touches": (
                        "" if resistance is None else resistance.touches
                    ),
                    "sl12_price": f"{row12.plan.stop_loss:.5f}",
                    "sl12_pips": f"{row12.plan.stop_distance / PIP:.2f}",
                    "sl12_source": row12.plan.stop_source,
                    "tp12_price": f"{row12.plan.take_profit:.5f}",
                    "tp12_pips": f"{row12.plan.take_distance / PIP:.2f}",
                    "tp12_source": row12.plan.take_source,
                    "result12_close_utc": (
                        row12.counterfactual.close_timestamp.isoformat()
                    ),
                    "result12_reason": row12.counterfactual.close_reason,
                    "result12_pnl": f"{row12.counterfactual.final_profit:.4f}",
                    "sl24_price": f"{row24.plan.stop_loss:.5f}",
                    "sl24_pips": f"{row24.plan.stop_distance / PIP:.2f}",
                    "sl24_source": row24.plan.stop_source,
                    "tp24_price": f"{row24.plan.take_profit:.5f}",
                    "tp24_pips": f"{row24.plan.take_distance / PIP:.2f}",
                    "tp24_source": row24.plan.take_source,
                    "result24_close_utc": (
                        row24.counterfactual.close_timestamp.isoformat()
                    ),
                    "result24_reason": row24.counterfactual.close_reason,
                    "result24_pnl": f"{row24.counterfactual.final_profit:.4f}",
                    "focus_case": (
                        "YES" if trade.signal_timestamp in FOCUS_CASES else "NO"
                    ),
                }
            )
    return OUTPUT_CSV


def _focus_line(
    index: int,
    baseline: WorkspaceHistoricalTradeDiagnostic,
    row12: PairedTradeResult,
    row24: PairedTradeResult,
) -> str:
    return (
        "    "
        f"{index:02d}. {baseline.signal_timestamp.isoformat()} {baseline.direction} "
        f"entry:{baseline.entry_price:.5f} "
        f"base:{baseline.close_reason}/{baseline.final_profit:+.2f} "
        f"SL/TP:{baseline.stop_loss_distance / PIP:.1f}/"
        f"{baseline.take_profit_distance / PIP:.1f}pip "
        f"support:{_level_text(row12.plan.support)} "
        f"resistance:{_level_text(row12.plan.resistance)} "
        f"12=SL:{row12.plan.stop_distance / PIP:.1f}({row12.plan.stop_source})/"
        f"TP:{row12.plan.take_distance / PIP:.1f}({row12.plan.take_source}) -> "
        f"{row12.counterfactual.close_reason}/{row12.counterfactual.final_profit:+.2f} "
        f"24=SL:{row24.plan.stop_distance / PIP:.1f}({row24.plan.stop_source})/"
        f"TP:{row24.plan.take_distance / PIP:.1f}({row24.plan.take_source}) -> "
        f"{row24.counterfactual.close_reason}/{row24.counterfactual.final_profit:+.2f}"
    )


def main() -> None:
    """Run baseline once, then paired Structural SL/TP variants for same entries."""
    assert_frozen_oos_snapshot()
    runtime = StructuralSlTpRuntime(
        frozen_oos_workspace(),
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

    _assert_baseline(runtime)
    baseline_summary = runtime.historical_summary
    execution = runtime.replay_execution
    assert baseline_summary is not None
    assert execution is not None
    baseline_trades = execution.trade_diagnostics()
    assert len(baseline_trades) == 59

    strategy_events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    strategy_index = {
        event.timestamp: index for index, event in enumerate(strategy_events)
    }
    execution_events = _flatten_execution_events(runtime)
    execution_index = {
        event.timestamp: index for index, event in enumerate(execution_events)
    }
    records_by_uid = {
        record.signal_uid: record for record in runtime.historical_signal_records
    }

    results_by_floor: dict[float, dict[str, PairedTradeResult]] = {}
    summaries: dict[float, WorkspaceHistoricalReplaySummary] = {}
    for floor_pips in SL_FLOOR_VARIANTS_PIPS:
        by_uid: dict[str, PairedTradeResult] = {}
        variant_trades: list[WorkspaceHistoricalTradeDiagnostic] = []
        for trade in baseline_trades:
            record = records_by_uid.get(trade.signal_uid)
            assert record is not None
            signal_event = runtime.strategy_events.get(trade.signal_timestamp)
            assert signal_event is not None
            plan = _build_plan(
                trade,
                strategy_events,
                strategy_index,
                floor_pips=floor_pips,
            )
            counterfactual = _simulate_one(
                runtime,
                trade,
                record,
                signal_event,
                execution_events,
                execution_index,
                plan,
            )
            row = PairedTradeResult(
                baseline=trade,
                plan=plan,
                counterfactual=counterfactual,
            )
            by_uid[trade.signal_uid] = row
            variant_trades.append(counterfactual)
        assert len(by_uid) == len(baseline_trades)
        results_by_floor[floor_pips] = by_uid
        summaries[floor_pips] = _variant_summary(
            baseline_summary,
            tuple(variant_trades),
        )

    focus_trades = tuple(
        trade for trade in baseline_trades if trade.signal_timestamp in FOCUS_CASES
    )
    assert len(focus_trades) == len(FOCUS_CASES)

    support_found = sum(
        results_by_floor[12.0][trade.signal_uid].plan.support is not None
        for trade in baseline_trades
    )
    resistance_found = sum(
        results_by_floor[12.0][trade.signal_uid].plan.resistance is not None
        for trade in baseline_trades
    )
    stop_structure_12 = sum(
        results_by_floor[12.0][trade.signal_uid].plan.stop_source == "STRUCTURE"
        for trade in baseline_trades
    )
    tp_structure_12 = sum(
        results_by_floor[12.0][trade.signal_uid].plan.take_source == "STRUCTURE"
        for trade in baseline_trades
    )

    output_csv = _write_csv(baseline_trades, results_by_floor)
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print("Algorithm Workspace Candidate F Structural SL/TP 2025 result")
    print("  mode=PRODUCTION_6K_CAUSAL_STRUCTURAL_SL_TP_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  production_sl_tp_changed=False")
    print("  production_exit_policy_changed=False")
    print("  paired_trade_counterfactual_only=True")
    print("  paired_entries_fixed_to_production=True")
    print("  changed_capacity_does_not_create_or_block_entries=True")
    print("  future_price_used_to_define_levels=False")
    print("  pivot_confirmation=2_left_2_right_completed_M15_bars")
    print(f"  pivot_lookback_bars={PIVOT_LOOKBACK_BARS}")
    print(f"  structure_buffer_pips={STRUCTURE_BUFFER_PIPS:.1f}")
    print("  touch_count_tolerance_pips=" f"{STRUCTURE_TOUCH_TOLERANCE_PIPS:.1f}")
    print("  sl_variants_pips=12.0|24.0")
    print("  sl_rule=STRUCTURE_PLUS_BUFFER_WITH_MINIMUM_DISTANCE_ELSE_PRODUCTION")
    print("  tp_rule=STRUCTURE_INSIDE_LEVEL_ELSE_2X_ACTUAL_SL")
    print("  tp_trailing=False")
    print(f"  baseline={_summary_text(baseline_summary)}")
    print(f"  structural_12={_summary_text(summaries[12.0])}")
    print(f"  structural_24={_summary_text(summaries[24.0])}")
    print(
        "  level_inventory="
        f"support_found:{support_found}/59,resistance_found:{resistance_found}/59,"
        f"sl_structure_used_12:{stop_structure_12}/59,"
        f"tp_structure_used_12:{tp_structure_12}/59"
    )
    print("  chronological_focus_cases:")
    for index, trade in enumerate(focus_trades, start=1):
        print(
            _focus_line(
                index,
                trade,
                results_by_floor[12.0][trade.signal_uid],
                results_by_floor[24.0][trade.signal_uid],
            )
        )
    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  causal_signal_and_prior_completed_M15_only=True")
    print("  production_6k_profit_drawdown_recovery_preserved_per_trade=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_STRUCTURAL_SL_TP_2025_CHECK=OK")


if __name__ == "__main__":
    main()
