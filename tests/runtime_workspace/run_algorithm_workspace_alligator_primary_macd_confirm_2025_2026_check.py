# -*- coding: utf-8 -*-
"""RoadMap103 / 8C: Alligator-primary + MACD 6/13/4 role-swap probe.

TEST_ONLY runner міняє ролі індикаторів без зміни production Candidate F.
Alligator бере видимі у TradingView Zalligator parameters 8/3, 13/5, 21/8
на ``hl2``: jaw=21/8, teeth=13/5, lips=8/3, Smoothed/Median. Перший causal
STARTING bar створює candidate. MACD 6/13/4 EMA/EMA підтверджує його тільки
свіжим same-direction MACD/Signal cross у causal 4-bar window. Entry — open
наступного M15 bucket. Hard protection: SL 12 pip, TP 24 pip. Paired exit
variant додає opposite MACD/Signal cross на close M15 bar.

MACD Quality gates тут не застосовуються, бо MACD вже не primary signal source.
Future bars не використовуються для signal/confirmation; broker I/O та production
logic не змінюються. Performance diagnostic-only і не є PASS-критерієм.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_PHASE_STARTING,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
    WorkspaceAlligatorFilter,
    WorkspaceAlligatorObservation,
    WorkspaceAlligatorRuntimeProfile,
)
from core.workspace_history import WorkspaceCsvHistoryLoader  # noqa: E402
from core.workspace_indicator_profile import (  # noqa: E402
    ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F,
    WORKSPACE_INDICATOR_MA_EXPONENTIAL,
    WORKSPACE_INDICATOR_SOURCE_CLOSE,
    WorkspaceIndicatorProfileBinding,
    built_in_workspace_indicator_profile,
)
from core.workspace_macd import (  # noqa: E402
    MACD_STATE_CROSS_DOWN,
    MACD_STATE_CROSS_UP,
    WorkspaceMacdObservation,
    WorkspaceMacdRuntimeProfile,
    WorkspaceMacdSignalSource,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_timeframe_aggregation import (  # noqa: E402
    WorkspaceTimeframeAggregator,
)
from engine.runtime_constants import (  # noqa: E402
    WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
    resolve_forex_pip_size,
    resolve_workspace_history_default_spread,
)

SYMBOL = "EURUSD"
SOURCE_BROKER = "CTRADER"
PIP_SIZE = resolve_forex_pip_size(SYMBOL)
MACD_FAST = 6
MACD_SLOW = 13
MACD_SIGNAL = 4
VIEW_JAW_PERIOD = 21
VIEW_TEETH_PERIOD = 13
VIEW_LIPS_PERIOD = 8
CONFIRMATION_WINDOW_BARS = 4
STOP_LOSS_PIPS = 12.0
TAKE_PROFIT_PIPS = 24.0
FIXED_VOLUME = 1000.0
EXPECTED_M15_DELTA = timedelta(minutes=15)
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """Один real-history EURUSD period для 8C."""

    label: str
    file_name: str
    start_utc: str
    end_utc: str
    candidate_f_reference_trades: int


WINDOWS = (
    ReplayWindow(
        label="2025",
        file_name="2025-01-01_2025-12-31_CTRADER_EURUSD_M1.csv",
        start_utc="2025-01-01T22:01:00+00:00",
        end_utc="2025-12-31T21:58:00+00:00",
        candidate_f_reference_trades=59,
    ),
    ReplayWindow(
        label="2026_TO_2026-08-25_15:07",
        file_name="2026-01-01_2026-08-25_CTRADER_EURUSD_M1.csv",
        start_utc="2026-01-01T22:01:00+00:00",
        end_utc="2026-08-25T15:07:00+00:00",
        candidate_f_reference_trades=29,
    ),
)


@dataclass(frozen=True, slots=True)
class IndicatorRun:
    """Completed M15 events та causal observations обох індикаторів."""

    events: tuple[WorkspaceMarketEvent, ...]
    completed_at: tuple[datetime, ...]
    alligator: tuple[WorkspaceAlligatorObservation, ...]
    macd: tuple[WorkspaceMacdObservation, ...]
    accepted_m1_rows: int
    completed_m15_bars: int
    dropped_incomplete_buckets: int


@dataclass(frozen=True, slots=True)
class ConfirmedCandidate:
    """Один Alligator opening, підтверджений MACD у causal window."""

    direction: str
    start_index: int
    confirm_index: int
    entry_index: int
    start_timestamp: datetime
    confirm_timestamp: datetime
    entry_timestamp: datetime
    delay_bars: int
    confirmation_is_fresh_cross: bool
    macd_was_aligned_before_start: bool


@dataclass(frozen=True, slots=True)
class TradeResult:
    """Paired fixed-entry outcome одного 8C candidate."""

    direction: str
    start_timestamp: datetime
    confirm_timestamp: datetime
    entry_timestamp: datetime
    close_timestamp: datetime
    entry_price: float
    close_price: float
    close_reason: str
    pnl: float
    holding_bars: int


@dataclass(frozen=True, slots=True)
class VariantSummary:
    """Компактні метрики paired trade set."""

    trades: int
    wins: int
    losses: int
    break_even: int
    net: float
    profit_factor: float | None
    maximum_drawdown: float
    average_holding_bars: float
    close_reasons: Counter[str]


def _history_file(window: ReplayWindow) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "history"
        / SOURCE_BROKER
        / SYMBOL
        / "M1"
        / window.file_name
    )


def _alligator_runtime_profile() -> WorkspaceAlligatorRuntimeProfile:
    profile = built_in_workspace_indicator_profile(
        ALLIGATOR_PROFILE_UID_LGE_CANDIDATE_F
    )
    binding = WorkspaceIndicatorProfileBinding.from_profile(profile)
    baseline = WorkspaceAlligatorRuntimeProfile.from_binding(binding)
    return WorkspaceAlligatorRuntimeProfile(
        profile_uid="RM103_8C_VIEW_ZALLIGATOR_21_13_8",
        profile_revision=1,
        profile_name="RM103 8C View Zalligator 21/13/8",
        source=baseline.source,
        jaw_period=VIEW_JAW_PERIOD,
        jaw_shift=baseline.jaw_shift,
        teeth_period=VIEW_TEETH_PERIOD,
        teeth_shift=baseline.teeth_shift,
        lips_period=VIEW_LIPS_PERIOD,
        lips_shift=baseline.lips_shift,
        ma_type=baseline.ma_type,
        logic_mode=baseline.logic_mode,
        trend_start_confirmation_bars=(baseline.trend_start_confirmation_bars),
        deferred_expiry_bars=baseline.deferred_expiry_bars,
        opening_collapse_threshold=baseline.opening_collapse_threshold,
        volatility_lookback_bars=baseline.volatility_lookback_bars,
        weak_max_active_age=baseline.weak_max_active_age,
        weak_max_opening=baseline.weak_max_opening,
        spike_min_range_ratio=baseline.spike_min_range_ratio,
        spike_max_opening_delta=baseline.spike_max_opening_delta,
        spike_max_slope_delta=baseline.spike_max_slope_delta,
        overextended_min_slope=baseline.overextended_min_slope,
        overextended_min_opening=baseline.overextended_min_opening,
    )


def _macd_runtime_profile() -> WorkspaceMacdRuntimeProfile:
    return WorkspaceMacdRuntimeProfile(
        profile_uid="RM103_8C_MACD_6_13_4",
        profile_revision=1,
        profile_name="RM103 8C MACD 6/13/4 EMA Close",
        source=WORKSPACE_INDICATOR_SOURCE_CLOSE,
        fast_period=MACD_FAST,
        slow_period=MACD_SLOW,
        signal_period=MACD_SIGNAL,
        oscillator_ma_type=WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        signal_ma_type=WORKSPACE_INDICATOR_MA_EXPONENTIAL,
        shift=0,
    )


def _load_indicator_run(window: ReplayWindow) -> IndicatorRun:
    history_file = _history_file(window)
    assert history_file.is_file(), history_file
    data_set = WorkspaceCsvHistoryLoader().load(
        file_path=history_file,
        broker=SOURCE_BROKER,
        symbol=SYMBOL,
        timeframe="M1",
        start_utc=window.start_utc,
        end_utc=window.end_utc,
        source_timezone="UTC",
        delimiter="AUTO",
        decimal_separator=".",
        default_spread=resolve_workspace_history_default_spread(SYMBOL),
        source_name=history_file.stem,
    )
    aggregator = WorkspaceTimeframeAggregator(
        source_timeframe="M1",
        target_timeframe="M15",
    )
    completed = []
    for event in data_set.events:
        item = aggregator.on_market_event(event)
        if item is not None:
            completed.append(item)
    final = aggregator.complete()
    if final is not None:
        completed.append(final)

    alligator_filter = WorkspaceAlligatorFilter(
        enabled=True,
        confirmation_mode=WORKSPACE_ALLIGATOR_CONFIRMATION_SAME_TIMEFRAME,
        runtime_profile=_alligator_runtime_profile(),
        timeframe="M15",
    )
    macd_source = WorkspaceMacdSignalSource(
        enabled=True,
        mode="LINEAR",
        runtime_profile=_macd_runtime_profile(),
    )
    alligator_observations = []
    macd_observations = []
    events = []
    completed_at = []
    for item in completed:
        events.append(item.event)
        completed_at.append(item.completed_at)
        alligator_observations.append(
            alligator_filter.on_market_event(
                item.event,
                available_at=item.completed_at,
            )
        )
        macd_source.on_market_event(item.event)
        macd_observations.append(macd_source.observations[-1])

    assert len(events) == len(alligator_observations) == len(macd_observations)
    assert all(
        observation.available_at == available
        for observation, available in zip(alligator_observations, completed_at)
    )
    return IndicatorRun(
        events=tuple(events),
        completed_at=tuple(completed_at),
        alligator=tuple(alligator_observations),
        macd=tuple(macd_observations),
        accepted_m1_rows=data_set.report.accepted_rows,
        completed_m15_bars=aggregator.completed_bars,
        dropped_incomplete_buckets=aggregator.dropped_incomplete_buckets,
    )


def _alligator_direction(observation: WorkspaceAlligatorObservation) -> str | None:
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_UP
        and observation.state == ALLIGATOR_STATE_BULLISH
    ):
        return "BUY"
    if (
        observation.regime == ALLIGATOR_REGIME_TREND_DOWN
        and observation.state == ALLIGATOR_STATE_BEARISH
    ):
        return "SELL"
    return None


def _is_opening(
    observations: tuple[WorkspaceAlligatorObservation, ...],
    index: int,
) -> bool:
    current = observations[index]
    direction = _alligator_direction(current)
    if direction is None or current.regime_phase != ALLIGATOR_REGIME_PHASE_STARTING:
        return False
    if index == 0:
        return True
    previous = observations[index - 1]
    previous_direction = _alligator_direction(previous)
    return not (
        previous_direction == direction
        and previous.regime_phase == ALLIGATOR_REGIME_PHASE_STARTING
    )


def _alligator_candidate_still_valid(
    observation: WorkspaceAlligatorObservation,
    direction: str,
) -> bool:
    return bool(
        _alligator_direction(observation) == direction
        and observation.regime_phase
        in {ALLIGATOR_REGIME_PHASE_STARTING, ALLIGATOR_REGIME_PHASE_ACTIVE}
    )


def _macd_aligned(observation: WorkspaceMacdObservation, direction: str) -> bool:
    histogram = observation.histogram
    if not observation.warmed_up or histogram is None:
        return False
    if direction == "BUY":
        return histogram > 0.0
    return histogram < 0.0


def _fresh_cross(observation: WorkspaceMacdObservation, direction: str) -> bool:
    if direction == "BUY":
        return observation.state == MACD_STATE_CROSS_UP
    return observation.state == MACD_STATE_CROSS_DOWN


def _confirmed_candidates(
    run: IndicatorRun,
) -> tuple[
    tuple[ConfirmedCandidate, ...],
    int,
    int,
    int,
]:
    confirmed = []
    opening_count = 0
    invalidated = 0
    timed_out = 0
    for start_index in range(len(run.events)):
        if not _is_opening(run.alligator, start_index):
            continue
        opening_count += 1
        direction = _alligator_direction(run.alligator[start_index])
        assert direction is not None
        previous_aligned = bool(
            start_index > 0 and _macd_aligned(run.macd[start_index - 1], direction)
        )
        found_index = None
        candidate_invalidated = False
        maximum_index = min(
            start_index + CONFIRMATION_WINDOW_BARS - 1,
            len(run.events) - 1,
        )
        for index in range(start_index, maximum_index + 1):
            if not _alligator_candidate_still_valid(run.alligator[index], direction):
                candidate_invalidated = True
                break
            if _fresh_cross(run.macd[index], direction):
                found_index = index
                break
        if found_index is None:
            if candidate_invalidated:
                invalidated += 1
            else:
                timed_out += 1
            continue
        entry_index = found_index + 1
        if entry_index >= len(run.events):
            timed_out += 1
            continue
        if run.events[entry_index].timestamp - run.events[found_index].timestamp != (
            EXPECTED_M15_DELTA
        ):
            timed_out += 1
            continue
        confirmed.append(
            ConfirmedCandidate(
                direction=direction,
                start_index=start_index,
                confirm_index=found_index,
                entry_index=entry_index,
                start_timestamp=run.completed_at[start_index],
                confirm_timestamp=run.completed_at[found_index],
                entry_timestamp=run.events[entry_index].timestamp,
                delay_bars=found_index - start_index,
                confirmation_is_fresh_cross=_fresh_cross(
                    run.macd[found_index],
                    direction,
                ),
                macd_was_aligned_before_start=previous_aligned,
            )
        )
    return tuple(confirmed), opening_count, invalidated, timed_out


def _entry_price(event: WorkspaceMarketEvent, direction: str) -> float:
    half_spread = event.spread / 2.0
    if direction == "BUY":
        return event.open + half_spread
    return event.open - half_spread


def _close_at_market(event: WorkspaceMarketEvent, direction: str) -> float:
    if direction == "BUY":
        return event.bid
    return event.ask


def _opposite_cross(observation: WorkspaceMacdObservation, direction: str) -> bool:
    if direction == "BUY":
        return observation.state == MACD_STATE_CROSS_DOWN
    return observation.state == MACD_STATE_CROSS_UP


def _simulate_trade(
    run: IndicatorRun,
    candidate: ConfirmedCandidate,
    *,
    macd_exit_enabled: bool,
) -> TradeResult:
    entry_event = run.events[candidate.entry_index]
    entry_price = _entry_price(entry_event, candidate.direction)
    stop_distance = STOP_LOSS_PIPS * PIP_SIZE
    take_distance = TAKE_PROFIT_PIPS * PIP_SIZE
    if candidate.direction == "BUY":
        stop_price = entry_price - stop_distance
        take_price = entry_price + take_distance
    else:
        stop_price = entry_price + stop_distance
        take_price = entry_price - take_distance

    close_index = len(run.events) - 1
    close_price = _close_at_market(run.events[close_index], candidate.direction)
    close_reason = "SESSION_END"
    for index in range(candidate.entry_index, len(run.events)):
        event = run.events[index]
        if candidate.direction == "BUY":
            stop_touched = event.low <= stop_price
            take_touched = event.high >= take_price
        else:
            stop_touched = event.high >= stop_price
            take_touched = event.low <= take_price
        if stop_touched:
            close_index = index
            close_price = stop_price
            close_reason = "STOP_LOSS"
            break
        if take_touched:
            close_index = index
            close_price = take_price
            close_reason = "TAKE_PROFIT"
            break
        if macd_exit_enabled and _opposite_cross(run.macd[index], candidate.direction):
            close_index = index
            close_price = _close_at_market(event, candidate.direction)
            close_reason = "OPPOSITE_MACD_CROSS"
            break

    sign = 1.0 if candidate.direction == "BUY" else -1.0
    pnl = (close_price - entry_price) * FIXED_VOLUME * sign
    return TradeResult(
        direction=candidate.direction,
        start_timestamp=candidate.start_timestamp,
        confirm_timestamp=candidate.confirm_timestamp,
        entry_timestamp=candidate.entry_timestamp,
        close_timestamp=run.events[close_index].timestamp + EXPECTED_M15_DELTA,
        entry_price=entry_price,
        close_price=close_price,
        close_reason=close_reason,
        pnl=pnl,
        holding_bars=close_index - candidate.entry_index + 1,
    )


def _summary(trades: tuple[TradeResult, ...]) -> VariantSummary:
    wins = sum(item.pnl > EPSILON for item in trades)
    losses = sum(item.pnl < -EPSILON for item in trades)
    break_even = len(trades) - wins - losses
    gross_profit = sum(item.pnl for item in trades if item.pnl > 0.0)
    gross_loss = -sum(item.pnl for item in trades if item.pnl < 0.0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else None
    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    ordered = sorted(
        trades,
        key=lambda row: (row.close_timestamp, row.entry_timestamp),
    )
    for item in ordered:
        cumulative += item.pnl
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)
    average_holding = (
        statistics.fmean(item.holding_bars for item in trades) if trades else 0.0
    )
    return VariantSummary(
        trades=len(trades),
        wins=wins,
        losses=losses,
        break_even=break_even,
        net=sum(item.pnl for item in trades),
        profit_factor=profit_factor,
        maximum_drawdown=maximum_drawdown,
        average_holding_bars=average_holding,
        close_reasons=Counter(item.close_reason for item in trades),
    )


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def _summary_text(summary: VariantSummary) -> str:
    reasons = summary.close_reasons
    return (
        f"trades:{summary.trades},wins:{summary.wins},losses:{summary.losses},"
        f"break_even:{summary.break_even},net:{summary.net:+.2f},"
        f"pf:{_fmt_pf(summary.profit_factor)},dd:{summary.maximum_drawdown:.2f},"
        f"hold:{summary.average_holding_bars:.2f},"
        f"sl:{reasons['STOP_LOSS']},tp:{reasons['TAKE_PROFIT']},"
        f"macd_exit:{reasons['OPPOSITE_MACD_CROSS']},"
        f"session_end:{reasons['SESSION_END']}"
    )


def _run_window(window: ReplayWindow) -> dict[str, object]:
    print(f"  running_period={window.label}", flush=True)
    run = _load_indicator_run(window)
    candidates, openings, invalidated, timed_out = _confirmed_candidates(run)
    assert openings > 0
    assert candidates
    assert all(0 <= item.delay_bars < CONFIRMATION_WINDOW_BARS for item in candidates)
    assert all(item.start_timestamp <= item.confirm_timestamp for item in candidates)
    assert all(item.confirm_timestamp == item.entry_timestamp for item in candidates)

    sltp = tuple(
        _simulate_trade(run, item, macd_exit_enabled=False) for item in candidates
    )
    macd_exit = tuple(
        _simulate_trade(run, item, macd_exit_enabled=True) for item in candidates
    )
    assert len(sltp) == len(macd_exit) == len(candidates)
    improved = sum(
        right.pnl > left.pnl + EPSILON for left, right in zip(sltp, macd_exit)
    )
    worsened = sum(
        right.pnl < left.pnl - EPSILON for left, right in zip(sltp, macd_exit)
    )
    unchanged = len(candidates) - improved - worsened
    delay_counts = Counter(item.delay_bars for item in candidates)
    same_bar = delay_counts[0]
    fresh_cross = sum(item.confirmation_is_fresh_cross for item in candidates)
    prealigned = sum(item.macd_was_aligned_before_start for item in candidates)
    return {
        "run": run,
        "candidates": candidates,
        "openings": openings,
        "invalidated": invalidated,
        "timed_out": timed_out,
        "delay_counts": delay_counts,
        "same_bar": same_bar,
        "fresh_cross": fresh_cross,
        "prealigned": prealigned,
        "sltp": _summary(sltp),
        "macd_exit": _summary(macd_exit),
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
    }


def main() -> None:
    results = [(window, _run_window(window)) for window in WINDOWS]

    for window, result in results:
        run = result["run"]
        assert isinstance(run, IndicatorRun)
        assert run.accepted_m1_rows > 0
        assert run.completed_m15_bars == len(run.events)
        assert all(
            current.timestamp > previous.timestamp
            for previous, current in zip(run.events, run.events[1:])
        )
        assert all(
            observation.available_at <= completed_at
            for observation, completed_at in zip(run.alligator, run.completed_at)
        )

    print("Algorithm Workspace Alligator Primary MACD Confirm/Exit result")
    print("  mode=RM103_8C_ALLIGATOR_PRIMARY_MACD_6_13_4_TEST_ONLY")
    print("  production_candidate_f_logic_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  source_broker=CTRADER")
    print("  symbol=EURUSD")
    print("  source_timeframe=M1")
    print("  strategy_timeframe=M15")
    print("  alligator_primary_event=FIRST_DIRECTIONAL_STARTING_BAR")
    print("  alligator_profile=VIEW_ZALLIGATOR_21_13_8_TEST_ONLY")
    print("  alligator_view_parameters=8/3_13/5_21/8_hl2")
    print("  alligator_ma_type=SMOOTHED")
    print("  alligator_confirmation_window_bars=4")
    print("  macd_role=FRESH_CROSS_CONFIRM_AND_OPPOSITE_CROSS_EXIT")
    print("  macd_profile=6/13/4_EMA_EMA_CLOSE")
    print("  macd_quality_gate_used=False")
    print("  entry_policy=NEXT_M15_OPEN_AFTER_CONFIRM")
    print("  stop_loss_pips=12.0")
    print("  take_profit_pips=24.0")
    print("  protection_ambiguous_bar_policy=STOP_LOSS_FIRST")
    print("  paired_entries_ignore_portfolio_capacity=True")
    print("  future_price_used_for_signal_or_confirmation=False")
    for window, result in results:
        run = result["run"]
        assert isinstance(run, IndicatorRun)
        candidates = result["candidates"]
        assert isinstance(candidates, tuple)
        delay_counts = result["delay_counts"]
        assert isinstance(delay_counts, Counter)
        print(
            f"  {window.label}/DATA="
            f"m1:{run.accepted_m1_rows},m15:{run.completed_m15_bars},"
            f"dropped_incomplete:{run.dropped_incomplete_buckets}"
        )
        print(
            f"  {window.label}/SIGNALS="
            f"alligator_openings:{result['openings']},"
            f"confirmed:{len(candidates)},invalidated:{result['invalidated']},"
            f"timeout:{result['timed_out']},same_bar:{result['same_bar']},"
            f"fresh_cross_confirm:{result['fresh_cross']},"
            f"prealigned_before_start:{result['prealigned']}"
        )
        print(
            f"  {window.label}/CONFIRM_DELAY="
            f"b0:{delay_counts[0]},b1:{delay_counts[1]},"
            f"b2:{delay_counts[2]},b3:{delay_counts[3]}"
        )
        print(
            f"  {window.label}/CANDIDATE_F_REFERENCE_TRADES="
            f"{window.candidate_f_reference_trades}"
        )
        sltp = result["sltp"]
        macd_exit = result["macd_exit"]
        assert isinstance(sltp, VariantSummary)
        assert isinstance(macd_exit, VariantSummary)
        print(f"  {window.label}/SLTP_ONLY={_summary_text(sltp)}")
        print(f"  {window.label}/MACD_EXIT={_summary_text(macd_exit)}")
        print(
            f"  {window.label}/MACD_EXIT_PAIRED="
            f"improved:{result['improved']},worsened:{result['worsened']},"
            f"unchanged:{result['unchanged']}"
        )
    print("  performance_is_diagnostic_not_pass_criterion=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_PRIMARY_MACD_CONFIRM_EXIT_CHECK=OK")


if __name__ == "__main__":
    main()
