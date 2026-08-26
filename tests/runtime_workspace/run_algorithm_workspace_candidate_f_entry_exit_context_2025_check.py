# -*- coding: utf-8 -*-
"""RoadMap103 / 7K: entry/exit context diagnostic production Candidate F 2025.

Diagnostic-only runner повторює production Candidate F після 6K
і для всіх 59 фактично відкритих угод зіставляє causal контекст
сигналу з ширшим Alligator Macro Trend із 7J. Production logic,
profile, entry, SL/TP та exit policy не змінюються.

Causal entry evidence використовує лише дані, доступні на
завершеному M15 signal bar: active_age, Alligator lines/opening/slope,
положення ціни відносно Jaw/Teeth/Lips та рух останніх 15/30/60 хв.
Окремо diagnostic-only після завершення Replay рахується retrospective
положення signal/exit усередині повного Macro Trend
(EARLY/MIDDLE/LATE). Воно НЕ є causal gate і не може використовуватися
production без окремої causal формалізації.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
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

from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402

EXPECTED_BASELINE = (59, 40, 18, 1, 9, 2, -4.05, 0.7808, 5.80)
PIP = 0.0001
EPSILON = 1e-12

PHASE_EARLY = "EARLY"
PHASE_MIDDLE = "MIDDLE"
PHASE_LATE = "LATE"
PHASES = (PHASE_EARLY, PHASE_MIDDLE, PHASE_LATE)

OUTCOME_STOP_LOSS = "STOP_LOSS"
OUTCOME_TAKE_PROFIT = "TAKE_PROFIT"
OUTCOME_WIN_PD = "WIN_PD"
OUTCOME_LOSS_PD = "LOSS_PD"
OUTCOME_BREAK_EVEN = "BREAK_EVEN"

OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "LavrGPT05" / "RM103_7K_Entry_Exit_Context_2025"
)
OUTPUT_CSV = OUTPUT_DIR / "candidate_f_entry_exit_context_2025.csv"

MANUAL_CASES = {
    datetime.fromisoformat("2025-03-05T12:30:00+00:00"),
    datetime.fromisoformat("2025-04-21T07:30:00+00:00"),
    datetime.fromisoformat("2025-05-13T07:30:00+00:00"),
    datetime.fromisoformat("2025-05-30T08:45:00+00:00"),
    datetime.fromisoformat("2025-06-06T12:00:00+00:00"),
    datetime.fromisoformat("2025-06-06T15:00:00+00:00"),
}


@dataclass(frozen=True, slots=True)
class ActiveRun:
    """One strict contiguous directional ACTIVE run for 7K matching."""

    run_id: int
    direction: str
    observations: tuple[WorkspaceAlligatorObservation, ...]

    @property
    def start_utc(self) -> datetime:
        return self.observations[0].timestamp

    @property
    def end_utc(self) -> datetime:
        return self.observations[-1].timestamp


@dataclass(frozen=True, slots=True)
class MacroTrend:
    """Same-direction Alligator regime trend used only for diagnostics."""

    macro_id: int
    direction: str
    observations: tuple[WorkspaceAlligatorObservation, ...]
    active_runs: tuple[ActiveRun, ...]

    @property
    def start_utc(self) -> datetime:
        return self.observations[0].timestamp

    @property
    def end_utc(self) -> datetime:
        return self.observations[-1].timestamp


def _active_direction(observation: WorkspaceAlligatorObservation) -> str | None:
    if observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE:
        return None
    if (
        observation.state == ALLIGATOR_STATE_BULLISH
        and observation.regime == ALLIGATOR_REGIME_TREND_UP
    ):
        return "BUY"
    if (
        observation.state == ALLIGATOR_STATE_BEARISH
        and observation.regime == ALLIGATOR_REGIME_TREND_DOWN
    ):
        return "SELL"
    return None


def _regime_direction(observation: WorkspaceAlligatorObservation) -> str | None:
    if observation.regime == ALLIGATOR_REGIME_TREND_UP:
        return "BUY"
    if observation.regime == ALLIGATOR_REGIME_TREND_DOWN:
        return "SELL"
    return None


def _split_active_runs(
    observations: tuple[WorkspaceAlligatorObservation, ...],
) -> tuple[ActiveRun, ...]:
    m15_seconds = 15 * 60
    raw_runs: list[tuple[str, tuple[WorkspaceAlligatorObservation, ...]]] = []
    current: list[WorkspaceAlligatorObservation] = []
    current_direction: str | None = None
    previous_timestamp: datetime | None = None

    for observation in observations:
        direction = _active_direction(observation)
        contiguous = (
            previous_timestamp is not None
            and (observation.timestamp - previous_timestamp).total_seconds()
            == m15_seconds
        )
        if direction is None:
            if current:
                assert current_direction is not None
                raw_runs.append((current_direction, tuple(current)))
                current = []
            current_direction = None
            previous_timestamp = observation.timestamp
            continue
        if current and (direction != current_direction or not contiguous):
            assert current_direction is not None
            raw_runs.append((current_direction, tuple(current)))
            current = []
        current.append(observation)
        current_direction = direction
        previous_timestamp = observation.timestamp

    if current:
        assert current_direction is not None
        raw_runs.append((current_direction, tuple(current)))

    return tuple(
        ActiveRun(run_id=index, direction=direction, observations=run)
        for index, (direction, run) in enumerate(raw_runs, start=1)
    )


def _split_macro_trends(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    active_runs: tuple[ActiveRun, ...],
) -> tuple[MacroTrend, ...]:
    max_interval_seconds = 15 * 60 * 5
    raw_macros: list[tuple[str, tuple[WorkspaceAlligatorObservation, ...]]] = []
    current: list[WorkspaceAlligatorObservation] = []
    current_direction: str | None = None
    previous_timestamp: datetime | None = None

    for observation in observations:
        direction = _regime_direction(observation)
        interval_allowed = (
            previous_timestamp is None
            or (observation.timestamp - previous_timestamp).total_seconds()
            <= max_interval_seconds
        )
        must_break = bool(current) and (
            direction is None or direction != current_direction or not interval_allowed
        )
        if must_break:
            assert current_direction is not None
            raw_macros.append((current_direction, tuple(current)))
            current = []
            current_direction = None
        if direction is not None:
            current.append(observation)
            current_direction = direction
        previous_timestamp = observation.timestamp

    if current:
        assert current_direction is not None
        raw_macros.append((current_direction, tuple(current)))

    macros: list[MacroTrend] = []
    for macro_id, (direction, macro_observations) in enumerate(raw_macros, start=1):
        start_utc = macro_observations[0].timestamp
        end_utc = macro_observations[-1].timestamp
        contained_runs = tuple(
            active_run
            for active_run in active_runs
            if active_run.direction == direction
            and start_utc <= active_run.start_utc
            and active_run.end_utc <= end_utc
        )
        macros.append(
            MacroTrend(
                macro_id=macro_id,
                direction=direction,
                observations=macro_observations,
                active_runs=contained_runs,
            )
        )
    return tuple(macros)


@dataclass(frozen=True, slots=True)
class TradeContextEvidence:
    """Combined causal entry and retrospective macro-trend trade context."""

    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    signal_record: WorkspaceSignalRecord
    signal_event: WorkspaceMarketEvent
    observation: WorkspaceAlligatorObservation
    macro: MacroTrend
    macro_age_bars: int
    macro_age_minutes: float
    macro_position_ratio: float
    macro_phase: str
    active_age: int
    opening: float
    slope: float
    price_to_lips_r: float
    price_to_teeth_r: float
    price_to_jaw_r: float
    pre15_r: float
    pre30_r: float
    pre60_r: float
    recent_5bar_location: float
    mfe_r: float
    mae_r: float
    final_r: float
    exit_relation: str
    exit_macro_ratio: float | None


class EntryExitContextRuntime(WorkspaceRuntime):
    """Production Runtime with immutable diagnostic access for 7K."""

    def __init__(self, *args, **kwargs) -> None:
        self.strategy_events: dict[datetime, WorkspaceMarketEvent] = {}
        super().__init__(*args, **kwargs)

    def _accept_market_event(
        self,
        event: WorkspaceMarketEvent,
        *,
        origin: str,
        warmup_only: bool = False,
        advance_replay_execution: bool = True,
    ) -> None:
        if event.timeframe == self.context.timeframe:
            self.strategy_events[event.timestamp] = event
        super()._accept_market_event(
            event,
            origin=origin,
            warmup_only=warmup_only,
            advance_replay_execution=advance_replay_execution,
        )

    @property
    def historical_signal_records(self) -> tuple[WorkspaceSignalRecord, ...]:
        """Return complete Replay signal history for diagnostic matching."""
        return tuple(self._historical_signal_records)


def _assert_baseline(runtime: EntryExitContextRuntime) -> None:
    summary = runtime.historical_summary
    assert summary is not None
    expected = EXPECTED_BASELINE
    assert summary.opened_trades == expected[0]
    assert summary.winning_trades == expected[1]
    assert summary.losing_trades == expected[2]
    assert summary.break_even_trades == expected[3]
    assert summary.close_reason_count("STOP_LOSS") == expected[4]
    assert summary.close_reason_count("TAKE_PROFIT") == expected[5]
    assert math.isclose(summary.net_profit, expected[6], abs_tol=0.005)
    assert summary.profit_factor is not None
    assert math.isclose(summary.profit_factor, expected[7], abs_tol=0.00005)
    assert math.isclose(summary.maximum_drawdown, expected[8], abs_tol=0.005)


def _directional_delta(direction: str, newer: float, older: float) -> float:
    if direction == "BUY":
        return newer - older
    return older - newer


def _directional_line_distance(
    direction: str,
    price: float,
    line_value: float,
) -> float:
    if direction == "BUY":
        return price - line_value
    return line_value - price


def _directional_range_location(
    direction: str,
    close: float,
    events: tuple[WorkspaceMarketEvent, ...],
) -> float:
    high = max(event.high for event in events)
    low = min(event.low for event in events)
    width = max(high - low, EPSILON)
    if direction == "BUY":
        return (close - low) / width
    return (high - close) / width


def _phase(ratio: float) -> str:
    if ratio <= 1.0 / 3.0:
        return PHASE_EARLY
    if ratio <= 2.0 / 3.0:
        return PHASE_MIDDLE
    return PHASE_LATE


def _macro_for_signal(
    macros: tuple[MacroTrend, ...],
    direction: str,
    timestamp: datetime,
) -> MacroTrend:
    matched = tuple(
        macro
        for macro in macros
        if macro.direction == direction
        and macro.start_utc <= timestamp <= macro.end_utc
    )
    assert len(matched) == 1, (direction, timestamp, matched)
    return matched[0]


def _macro_position(macro: MacroTrend, timestamp: datetime) -> float:
    total = (macro.end_utc - macro.start_utc).total_seconds()
    if total <= 0.0:
        return 0.0
    elapsed = (timestamp - macro.start_utc).total_seconds()
    return min(max(elapsed / total, 0.0), 1.0)


def _outcome(trade: WorkspaceHistoricalTradeDiagnostic) -> str:
    if trade.close_reason == "STOP_LOSS":
        return OUTCOME_STOP_LOSS
    if trade.close_reason == "TAKE_PROFIT":
        return OUTCOME_TAKE_PROFIT
    if trade.final_profit > EPSILON:
        return OUTCOME_WIN_PD
    if trade.final_profit < -EPSILON:
        return OUTCOME_LOSS_PD
    return OUTCOME_BREAK_EVEN


def _exit_relation(
    macro: MacroTrend,
    trade: WorkspaceHistoricalTradeDiagnostic,
) -> tuple[str, float | None]:
    if trade.close_timestamp < macro.start_utc:
        return "BEFORE_MACRO", None
    if trade.close_timestamp > macro.end_utc:
        return "AFTER_MACRO", None
    ratio = _macro_position(macro, trade.close_timestamp)
    return f"INSIDE_{_phase(ratio)}", ratio


def _build_evidence(
    runtime: EntryExitContextRuntime,
    macros: tuple[MacroTrend, ...],
) -> tuple[TradeContextEvidence, ...]:
    execution = runtime.replay_execution
    algorithm = runtime.algorithm
    assert execution is not None
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None

    observations_by_timestamp = {
        observation.timestamp: observation for observation in signal_filter.observations
    }
    records_by_uid = {
        record.signal_uid: record for record in runtime.historical_signal_records
    }
    strategy_events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_index = {
        event.timestamp: index for index, event in enumerate(strategy_events)
    }

    rows: list[TradeContextEvidence] = []
    for trade in execution.trade_diagnostics():
        record = records_by_uid.get(trade.signal_uid)
        assert record is not None, trade.signal_uid
        context = record.filter_context
        assert context is not None
        assert context.active_age is not None
        assert context.normalized_opening is not None
        assert context.normalized_slope is not None
        assert context.available_at is not None
        assert context.available_at <= record.timestamp

        signal_event = runtime.strategy_events.get(trade.signal_timestamp)
        assert signal_event is not None, trade.signal_timestamp
        observation = observations_by_timestamp.get(trade.signal_timestamp)
        assert observation is not None, trade.signal_timestamp
        assert observation.jaw is not None
        assert observation.teeth is not None
        assert observation.lips is not None
        assert observation.available_at <= trade.signal_timestamp

        macro = _macro_for_signal(macros, trade.direction, trade.signal_timestamp)
        macro_observed_to_signal = tuple(
            item
            for item in macro.observations
            if item.timestamp <= trade.signal_timestamp
        )
        assert macro_observed_to_signal
        macro_age_bars = len(macro_observed_to_signal)
        macro_age_minutes = (
            trade.signal_timestamp - macro.start_utc
        ).total_seconds() / 60.0
        macro_ratio = _macro_position(macro, trade.signal_timestamp)

        index = event_index.get(trade.signal_timestamp)
        assert index is not None
        assert index >= 4
        recent = strategy_events[index - 4 : index + 1]  # noqa: E203
        stop_distance = trade.stop_loss_distance
        assert stop_distance > 0.0
        pre15_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                recent[-2].close,
            )
            / stop_distance
        )
        pre30_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                recent[-3].close,
            )
            / stop_distance
        )
        pre60_r = (
            _directional_delta(
                trade.direction,
                signal_event.close,
                recent[-5].close,
            )
            / stop_distance
        )

        risk_usd = trade.stop_loss_distance * trade.volume
        assert risk_usd > 0.0
        mfe_r = trade.maximum_favorable_excursion / risk_usd
        mae_r = -trade.maximum_adverse_excursion / risk_usd
        final_r = trade.final_profit / risk_usd
        exit_relation, exit_ratio = _exit_relation(macro, trade)

        rows.append(
            TradeContextEvidence(
                trade=trade,
                outcome=_outcome(trade),
                signal_record=record,
                signal_event=signal_event,
                observation=observation,
                macro=macro,
                macro_age_bars=macro_age_bars,
                macro_age_minutes=macro_age_minutes,
                macro_position_ratio=macro_ratio,
                macro_phase=_phase(macro_ratio),
                active_age=int(context.active_age),
                opening=float(context.normalized_opening),
                slope=float(context.normalized_slope),
                price_to_lips_r=(
                    _directional_line_distance(
                        trade.direction,
                        signal_event.close,
                        float(observation.lips),
                    )
                    / stop_distance
                ),
                price_to_teeth_r=(
                    _directional_line_distance(
                        trade.direction,
                        signal_event.close,
                        float(observation.teeth),
                    )
                    / stop_distance
                ),
                price_to_jaw_r=(
                    _directional_line_distance(
                        trade.direction,
                        signal_event.close,
                        float(observation.jaw),
                    )
                    / stop_distance
                ),
                pre15_r=pre15_r,
                pre30_r=pre30_r,
                pre60_r=pre60_r,
                recent_5bar_location=_directional_range_location(
                    trade.direction,
                    signal_event.close,
                    recent,
                ),
                mfe_r=mfe_r,
                mae_r=mae_r,
                final_r=final_r,
                exit_relation=exit_relation,
                exit_macro_ratio=exit_ratio,
            )
        )
    return tuple(rows)


def _median(items: tuple[TradeContextEvidence, ...], attr: str) -> float:
    assert items
    return float(statistics.median(float(getattr(item, attr)) for item in items))


def _write_csv(rows: tuple[TradeContextEvidence, ...]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "signal_utc",
        "entry_utc",
        "close_utc",
        "direction",
        "outcome",
        "close_reason",
        "final_profit",
        "final_r",
        "macro_id",
        "macro_start_utc",
        "macro_end_utc",
        "macro_age_bars_causal",
        "macro_age_minutes_causal",
        "macro_position_ratio_retrospective",
        "macro_phase_retrospective",
        "active_age_causal",
        "opening_causal",
        "slope_causal",
        "price_to_lips_r_causal",
        "price_to_teeth_r_causal",
        "price_to_jaw_r_causal",
        "pre15_r_causal",
        "pre30_r_causal",
        "pre60_r_causal",
        "recent_5bar_location_causal",
        "old_sl_pips",
        "old_tp_pips",
        "mfe_r_post_trade",
        "mae_r_post_trade",
        "exit_relation_retrospective",
        "exit_macro_ratio_retrospective",
        "manual_case",
    )
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for item in rows:
            trade = item.trade
            writer.writerow(
                {
                    "signal_utc": trade.signal_timestamp.isoformat(),
                    "entry_utc": trade.entry_timestamp.isoformat(),
                    "close_utc": trade.close_timestamp.isoformat(),
                    "direction": trade.direction,
                    "outcome": item.outcome,
                    "close_reason": trade.close_reason,
                    "final_profit": f"{trade.final_profit:.4f}",
                    "final_r": f"{item.final_r:.6f}",
                    "macro_id": item.macro.macro_id,
                    "macro_start_utc": item.macro.start_utc.isoformat(),
                    "macro_end_utc": item.macro.end_utc.isoformat(),
                    "macro_age_bars_causal": item.macro_age_bars,
                    "macro_age_minutes_causal": f"{item.macro_age_minutes:.1f}",
                    "macro_position_ratio_retrospective": (
                        f"{item.macro_position_ratio:.6f}"
                    ),
                    "macro_phase_retrospective": item.macro_phase,
                    "active_age_causal": item.active_age,
                    "opening_causal": f"{item.opening:.6f}",
                    "slope_causal": f"{item.slope:.6f}",
                    "price_to_lips_r_causal": f"{item.price_to_lips_r:.6f}",
                    "price_to_teeth_r_causal": f"{item.price_to_teeth_r:.6f}",
                    "price_to_jaw_r_causal": f"{item.price_to_jaw_r:.6f}",
                    "pre15_r_causal": f"{item.pre15_r:.6f}",
                    "pre30_r_causal": f"{item.pre30_r:.6f}",
                    "pre60_r_causal": f"{item.pre60_r:.6f}",
                    "recent_5bar_location_causal": f"{item.recent_5bar_location:.6f}",
                    "old_sl_pips": f"{trade.stop_loss_distance / PIP:.2f}",
                    "old_tp_pips": f"{trade.take_profit_distance / PIP:.2f}",
                    "mfe_r_post_trade": f"{item.mfe_r:.6f}",
                    "mae_r_post_trade": f"{item.mae_r:.6f}",
                    "exit_relation_retrospective": item.exit_relation,
                    "exit_macro_ratio_retrospective": (
                        ""
                        if item.exit_macro_ratio is None
                        else f"{item.exit_macro_ratio:.6f}"
                    ),
                    "manual_case": (
                        "YES" if trade.signal_timestamp in MANUAL_CASES else "NO"
                    ),
                }
            )
    return OUTPUT_CSV


def _summary_line(name: str, items: tuple[TradeContextEvidence, ...]) -> str:
    phases = Counter(item.macro_phase for item in items)
    return (
        f"    {name}=n:{len(items)},"
        f"phase:E:{phases[PHASE_EARLY]},M:{phases[PHASE_MIDDLE]},"
        f"L:{phases[PHASE_LATE]},"
        f"macro_pos_med:{_median(items, 'macro_position_ratio'):.3f},"
        f"active_age_med:{_median(items, 'active_age'):.1f},"
        f"opening_med:{_median(items, 'opening'):.3f},"
        f"price_lips_med:{_median(items, 'price_to_lips_r'):.3f}R,"
        f"pre30_med:{_median(items, 'pre30_r'):+.3f}R,"
        f"MFE_med:{_median(items, 'mfe_r'):.3f}R,"
        f"MAE_med:{_median(items, 'mae_r'):.3f}R"
    )


def _trade_line(index: int, item: TradeContextEvidence) -> str:
    trade = item.trade
    return (
        "    "
        f"{index:02d}. {trade.signal_timestamp.isoformat()} {trade.direction} "
        f"{item.outcome} pnl:{trade.final_profit:+.2f} "
        f"macro:{item.macro.macro_id} {item.macro_phase} "
        f"pos:{item.macro_position_ratio:.3f} "
        f"macro_age:{item.macro_age_bars} active_age:{item.active_age} "
        f"open:{item.opening:.3f} slope:{item.slope:.3f} "
        f"L/T/J:{item.price_to_lips_r:+.2f}/"
        f"{item.price_to_teeth_r:+.2f}/{item.price_to_jaw_r:+.2f}R "
        f"pre15/30/60:{item.pre15_r:+.2f}/"
        f"{item.pre30_r:+.2f}/{item.pre60_r:+.2f}R "
        f"SL/TP:{trade.stop_loss_distance / PIP:.1f}/"
        f"{trade.take_profit_distance / PIP:.1f}pip "
        f"MFE/MAE:{item.mfe_r:.2f}/{item.mae_r:.2f}R "
        f"exit:{item.exit_relation}"
    )


def main() -> None:
    """Run production 6K Replay and print 7K entry/exit context."""
    assert_frozen_oos_snapshot()
    runtime = EntryExitContextRuntime(
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
    algorithm = runtime.algorithm
    assert isinstance(algorithm, WorkspaceMacdAlligatorReplayAlgorithm)
    signal_filter = algorithm.signal_filter
    assert signal_filter is not None
    observations = tuple(signal_filter.observations)
    active_runs = _split_active_runs(observations)
    macros = _split_macro_trends(observations, active_runs)
    evidence = _build_evidence(runtime, macros)

    summary = runtime.historical_summary
    assert summary is not None
    assert len(evidence) == 59
    assert all(item.signal_record.accepted for item in evidence)
    assert all(
        item.observation.available_at <= item.trade.signal_timestamp
        for item in evidence
    )

    groups: dict[str, tuple[TradeContextEvidence, ...]] = {}
    for outcome in (
        OUTCOME_STOP_LOSS,
        OUTCOME_TAKE_PROFIT,
        OUTCOME_WIN_PD,
        OUTCOME_LOSS_PD,
        OUTCOME_BREAK_EVEN,
    ):
        groups[outcome] = tuple(item for item in evidence if item.outcome == outcome)

    assert len(groups[OUTCOME_STOP_LOSS]) == 9
    assert len(groups[OUTCOME_TAKE_PROFIT]) == 2
    assert sum(len(items) for items in groups.values()) == 59

    phase_counts = Counter(item.macro_phase for item in evidence)
    exit_counts = Counter(item.exit_relation for item in evidence)
    sl_phase_counts = Counter(item.macro_phase for item in groups[OUTCOME_STOP_LOSS])
    tp_phase_counts = Counter(item.macro_phase for item in groups[OUTCOME_TAKE_PROFIT])

    manual_rows = tuple(
        item for item in evidence if item.trade.signal_timestamp in MANUAL_CASES
    )
    assert len(manual_rows) >= 4

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    output_csv = _write_csv(evidence)

    print("Algorithm Workspace Candidate F Entry Exit Context 2025 result")
    print("  mode=PRODUCTION_6K_ENTRY_EXIT_CONTEXT_DIAGNOSTIC_ONLY")
    print("  production_logic_changed=False")
    print("  production_profile_changed=False")
    print("  entry_policy_changed=False")
    print("  sl_tp_changed=False")
    print("  exit_policy_changed=False")
    print("  causal_entry_features_only=True")
    print("  macro_phase_is_retrospective_diagnostic_only=True")
    print("  future_macro_end_not_used_as_gate=True")
    print(
        "  baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"sl:{summary.close_reason_count('STOP_LOSS')},"
        f"tp:{summary.close_reason_count('TAKE_PROFIT')},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print(
        "  all_trades_macro_phase="
        f"EARLY:{phase_counts[PHASE_EARLY]},"
        f"MIDDLE:{phase_counts[PHASE_MIDDLE]},"
        f"LATE:{phase_counts[PHASE_LATE]}"
    )
    print(
        "  stop_loss_macro_phase="
        f"EARLY:{sl_phase_counts[PHASE_EARLY]},"
        f"MIDDLE:{sl_phase_counts[PHASE_MIDDLE]},"
        f"LATE:{sl_phase_counts[PHASE_LATE]}"
    )
    print(
        "  take_profit_macro_phase="
        f"EARLY:{tp_phase_counts[PHASE_EARLY]},"
        f"MIDDLE:{tp_phase_counts[PHASE_MIDDLE]},"
        f"LATE:{tp_phase_counts[PHASE_LATE]}"
    )
    print("  retrospective_phase_matrix:")
    for phase_name in PHASES:
        phase_items = tuple(item for item in evidence if item.macro_phase == phase_name)
        phase_outcomes = Counter(item.outcome for item in phase_items)
        sl_rate = (
            phase_outcomes[OUTCOME_STOP_LOSS] / len(phase_items) * 100.0
            if phase_items
            else 0.0
        )
        print(
            "    "
            f"{phase_name}=n:{len(phase_items)},"
            f"SL:{phase_outcomes[OUTCOME_STOP_LOSS]},"
            f"TP:{phase_outcomes[OUTCOME_TAKE_PROFIT]},"
            f"WIN_PD:{phase_outcomes[OUTCOME_WIN_PD]},"
            f"LOSS_PD:{phase_outcomes[OUTCOME_LOSS_PD]},"
            f"BE:{phase_outcomes[OUTCOME_BREAK_EVEN]},"
            f"SL_rate:{sl_rate:.1f}%"
        )
    print("  outcome_group_medians:")
    for outcome, items in groups.items():
        if items:
            print(_summary_line(outcome, items))
    print(
        "  exit_relation_counts="
        + ",".join(f"{name}:{count}" for name, count in sorted(exit_counts.items()))
    )
    print("  chronological_stop_loss_context:")
    for index, item in enumerate(groups[OUTCOME_STOP_LOSS], start=1):
        print(_trade_line(index, item))
    print("  take_profit_context:")
    for index, item in enumerate(groups[OUTCOME_TAKE_PROFIT], start=1):
        print(_trade_line(index, item))
    print("  previously_reviewed_manual_cases:")
    for index, item in enumerate(manual_rows, start=1):
        print(_trade_line(index, item))
    print(f"  output_csv={output_csv}")
    print("  completed_bars_only=True")
    print("  broker_requests=0")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_ENTRY_EXIT_CONTEXT_2025_CHECK=OK")


if __name__ == "__main__":
    main()
