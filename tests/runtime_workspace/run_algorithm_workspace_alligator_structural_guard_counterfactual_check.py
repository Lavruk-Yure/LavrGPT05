# -*- coding: utf-8 -*-
"""Structural guard screening + combined counterfactual, RoadMap101 №35.

Тест не змінює production. Від GREEN №33 D baseline бере 4-bar Alligator
та causal opening-collapse guard -0.700. На фактичних baseline trades окремо
екранує три наперед визначені structural guard-кандидати з №34:
WEAK_OPENING / TOO_EARLY_ACTIVE, VOLATILITY_SPIKE + DETERIORATION та
OVEREXTENDED_TREND. Потім виконує реальний counterfactual Replay тільки для
їх об'єднання, щоб не множити дорогі повні Replay.

Усі ознаки causal на завершеному M15 signal bar. Volatility reference —
середній range 20 попередніх завершених M15 bars; поточний bar не входить.
Для кожного screen друкуються всі фактичні baseline trades, які він би
відхилив, а для COMBINED — реальні Replay метрики та всі guard rejections.
MFE/MAE не використовуються. Production trade gate, registration, профілі
та broker execution тест не змінює.
"""

from __future__ import annotations

import importlib.util
import math
import statistics
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_alligator as workspace_alligator  # noqa: E402
from core.workspace_algorithm import WorkspaceSignalOutput  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    ALLIGATOR_REGIME_TREND_DOWN,
    ALLIGATOR_REGIME_TREND_UP,
    ALLIGATOR_STATE_BEARISH,
    ALLIGATOR_STATE_BULLISH,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalProposal,
)

SOURCE_30 = Path(__file__).with_name(
    "run_algorithm_workspace_macd_deferred_alligator_entry_comparison_check.py"
)
SOURCE_33 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_opening_collapse_counterfactual_check.py"
)
SOURCE_34 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_remaining_sl_diagnostic_check.py"
)

WINDOWS = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T23:59:00+00:00",
    ),
    (
        "VALIDATION",
        "2026-03-01T00:00:00+00:00",
        "2026-05-31T23:59:00+00:00",
    ),
    (
        "HOLDOUT",
        "2026-06-01T00:00:00+00:00",
        "2026-08-11T08:24:00+00:00",
    ),
)

CONFIRMATION_BARS = 4
COLLAPSE_THRESHOLD = -0.700
VOLATILITY_LOOKBACK_BARS = 20

WEAK_MAX_ACTIVE_AGE = 2
WEAK_MAX_OPENING = 0.500
SPIKE_MIN_RANGE_RATIO = 3.500
SPIKE_MAX_OPENING_DELTA = -0.500
SPIKE_MAX_SLOPE_DELTA = -0.010
OVEREXTENDED_MIN_SLOPE = 0.200
OVEREXTENDED_MIN_OPENING = 3.000

GUARD_WEAK = "WEAK_OPENING_TOO_EARLY_ACTIVE"
GUARD_SPIKE = "VOLATILITY_SPIKE_WITH_DETERIORATION"
GUARD_OVEREXTENDED = "OVEREXTENDED_TREND"
GUARD_COMBINED = "COMBINED_STRUCTURAL_GUARDS"
GUARD_COMPONENTS = (GUARD_WEAK, GUARD_SPIKE, GUARD_OVEREXTENDED)
GUARD_REASON_CODE = "ALLIGATOR_STRUCTURAL_TEST_REJECT"

LOCKED_D_RESULTS = {
    "DEVELOPMENT": (7, 5, 2, 0, 7, 1.01, 0.19, 6.3158),
    "VALIDATION": (17, 10, 7, 3, 14, -2.23, 4.44, 0.6559),
    "HOLDOUT": (9, 4, 5, 2, 7, -3.84, 3.90, 0.0657),
}

IMPULSE_DIAGNOSTIC_TIMESTAMP = "2026-04-21T19:30:00+00:00"


@dataclass(frozen=True, slots=True)
class StructuralRejection:
    """Один causal signal, відхилений combined structural guard."""

    timestamp: datetime
    direction: str
    matched_guard: str
    active_age: int
    normalized_slope: float
    normalized_opening: float
    slope_delta: float
    opening_delta: float
    signal_range: float
    prior20_range: float
    range_ratio: float


@dataclass(frozen=True, slots=True)
class CombinedReplayResult:
    """Фактичний Replay 4-bar+collapse+combined structural guards."""

    window: str
    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    net_profit: float
    maximum_drawdown: float
    profit_factor: float | None
    collapse_rejections: int
    structural_rejections: tuple[StructuralRejection, ...]
    broker_execution_attempted: bool


def _load_module(path: Path, module_name: str):
    """Завантажити GREEN sibling test без tests package dependency."""
    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _proposal_tuple(
    output: WorkspaceSignalOutput,
) -> tuple[WorkspaceSignalProposal, ...]:
    if output is None:
        return ()
    if isinstance(output, WorkspaceSignalProposal):
        return (output,)
    return tuple(output)


def _direction_signature(direction: str) -> tuple[str, str]:
    if direction == "BUY":
        return ALLIGATOR_REGIME_TREND_UP, ALLIGATOR_STATE_BULLISH
    if direction == "SELL":
        return ALLIGATOR_REGIME_TREND_DOWN, ALLIGATOR_STATE_BEARISH
    raise AssertionError(direction)


def _active_age(observations: tuple[Any, ...], direction: str) -> int:
    """Causal ACTIVE age поточного observation для signal direction."""
    regime, state = _direction_signature(direction)
    count = 0
    for observation in reversed(observations):
        if not (
            observation.regime == regime
            and observation.state == state
            and observation.regime_phase == ALLIGATOR_REGIME_PHASE_ACTIVE
        ):
            break
        count += 1
    return count


def _matches_values(
    guard_name: str,
    *,
    active_age: int,
    slope: float,
    opening: float,
    slope_delta: float,
    opening_delta: float,
    range_ratio: float,
) -> bool:
    """Єдина канонічна test-only predicate для screen і live wrapper."""
    if guard_name == GUARD_WEAK:
        return active_age <= WEAK_MAX_ACTIVE_AGE and opening < WEAK_MAX_OPENING
    if guard_name == GUARD_SPIKE:
        deterioration = (
            opening_delta < SPIKE_MAX_OPENING_DELTA
            or slope_delta < SPIKE_MAX_SLOPE_DELTA
        )
        return range_ratio >= SPIKE_MIN_RANGE_RATIO and deterioration
    if guard_name == GUARD_OVEREXTENDED:
        return slope >= OVEREXTENDED_MIN_SLOPE and opening >= OVEREXTENDED_MIN_OPENING
    raise AssertionError(guard_name)


def _matched_component(
    *,
    active_age: int,
    slope: float,
    opening: float,
    slope_delta: float,
    opening_delta: float,
    range_ratio: float,
) -> str | None:
    for guard_name in GUARD_COMPONENTS:
        if _matches_values(
            guard_name,
            active_age=active_age,
            slope=slope,
            opening=opening,
            slope_delta=slope_delta,
            opening_delta=opening_delta,
            range_ratio=range_ratio,
        ):
            return guard_name
    return None


def _guarded_class(source_33):
    """Створити combined wrapper поверх GREEN №33 D algorithm."""
    base = source_33.OpeningCollapseGuardAlgorithm

    class CombinedStructuralGuardAlgorithm(base):
        """4-bar + collapse -0.700 + combined structural guards."""

        def __init__(self, algorithm_id: str) -> None:
            base.__init__(self, algorithm_id, COLLAPSE_THRESHOLD)
            self.structural_rejections: list[StructuralRejection] = []
            self._prior_ranges: list[float] = []

        def start(self) -> None:
            base.start(self)
            self.structural_rejections = []
            self._prior_ranges = []

        def _apply_structural_guard(
            self,
            output: WorkspaceSignalOutput,
            event: WorkspaceMarketEvent,
            prior20_range: float | None,
        ) -> WorkspaceSignalOutput:
            proposals = _proposal_tuple(output)
            if not proposals or prior20_range is None:
                return output
            signal_filter = getattr(self, "signal_filter", None)
            if signal_filter is None:
                return output
            current = signal_filter.latest_observation
            if (
                current is None
                or current.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
                or current.normalized_slope is None
                or current.normalized_opening is None
            ):
                return output
            history = signal_filter.diagnostic_observation_history(
                current,
                limit=3,
            )
            if len(history) < 3:
                return output
            oldest = history[0]
            if oldest.normalized_slope is None or oldest.normalized_opening is None:
                return output

            signal_range = float(event.high - event.low)
            assert signal_range > 0.0
            assert prior20_range > 0.0
            range_ratio = signal_range / prior20_range
            slope = float(current.normalized_slope)
            opening = float(current.normalized_opening)
            slope_delta = float(slope - oldest.normalized_slope)
            opening_delta = float(opening - oldest.normalized_opening)

            changed = False
            guarded: list[WorkspaceSignalProposal] = []
            for proposal in proposals:
                if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
                    guarded.append(proposal)
                    continue
                active_age = _active_age(
                    tuple(signal_filter.observations),
                    proposal.direction,
                )
                matched = _matched_component(
                    active_age=active_age,
                    slope=slope,
                    opening=opening,
                    slope_delta=slope_delta,
                    opening_delta=opening_delta,
                    range_ratio=range_ratio,
                )
                if matched is None:
                    guarded.append(proposal)
                    continue
                changed = True
                self.structural_rejections.append(
                    StructuralRejection(
                        timestamp=event.timestamp,
                        direction=proposal.direction,
                        matched_guard=matched,
                        active_age=active_age,
                        normalized_slope=slope,
                        normalized_opening=opening,
                        slope_delta=slope_delta,
                        opening_delta=opening_delta,
                        signal_range=signal_range,
                        prior20_range=prior20_range,
                        range_ratio=range_ratio,
                    )
                )
                guarded.append(
                    replace(
                        proposal,
                        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
                        filter_reason_code=GUARD_REASON_CODE,
                        reason=(
                            f"{proposal.reason}; {GUARD_REASON_CODE}: " f"{matched}"
                        ).strip("; "),
                    )
                )
            if not changed:
                return output
            if isinstance(output, WorkspaceSignalProposal):
                return guarded[0]
            return tuple(guarded)

        def on_market_event(
            self,
            event: WorkspaceMarketEvent,
        ) -> WorkspaceSignalOutput:
            prior20_range = None
            if len(self._prior_ranges) >= VOLATILITY_LOOKBACK_BARS:
                prior20_range = statistics.fmean(
                    self._prior_ranges[-VOLATILITY_LOOKBACK_BARS:]
                )
            output = base.on_market_event(self, event)
            guarded = self._apply_structural_guard(
                output,
                event,
                prior20_range,
            )
            event_range = float(event.high - event.low)
            if event_range > 0.0:
                self._prior_ranges.append(event_range)
            return guarded

    return CombinedStructuralGuardAlgorithm


def _run_combined(
    source_30,
    source_33,
    window: str,
    start: str,
    end: str,
) -> CombinedReplayResult:
    """Виконати один real Replay combined structural counterfactual."""
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    workspace_factory = getattr(source_30, "_workspace")
    guarded_class = _guarded_class(source_33)

    def algorithm_factory(algorithm_id: str):
        return guarded_class(algorithm_id)

    try:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = (
            CONFIRMATION_BARS
        )
        runtime = WorkspaceRuntime(
            workspace_factory(start, end),
            algorithm_factory=algorithm_factory,
        )
        runtime.begin_start()
        runtime.complete_start()
        session = runtime.replay_session
        assert session is not None
        while not session.completed:
            runtime.advance_replay()

        summary = runtime.historical_summary
        algorithm = runtime.algorithm
        assert summary is not None
        assert algorithm is not None
        rejections = tuple(getattr(algorithm, "structural_rejections", ()))
        collapse_rejections = len(getattr(algorithm, "guard_rejections", ()))
        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted
        return CombinedReplayResult(
            window=window,
            trades=summary.opened_trades,
            winners=summary.winning_trades,
            losers=summary.losing_trades,
            stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
            profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
            net_profit=summary.net_profit,
            maximum_drawdown=summary.maximum_drawdown,
            profit_factor=summary.profit_factor,
            collapse_rejections=collapse_rejections,
            structural_rejections=rejections,
            broker_execution_attempted=broker_execution_attempted,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _screen_matches(trades: tuple[Any, ...], guard_name: str) -> tuple[Any, ...]:
    """Відібрати actual D baseline trades, що відповідають predicate."""
    return tuple(
        trade
        for trade in trades
        if _matches_values(
            guard_name,
            active_age=trade.active_age_bars,
            slope=trade.normalized_slope,
            opening=trade.normalized_opening,
            slope_delta=trade.slope_delta_t2_t,
            opening_delta=trade.opening_delta_t2_t,
            range_ratio=trade.signal_range_ratio,
        )
    )


def _format_screen(trades: tuple[Any, ...]) -> str:
    if not trades:
        return "count:0,wins:0,losses:0,sl:0,pnl:+0.00"
    winners = sum(1 for trade in trades if trade.winner)
    losses = sum(1 for trade in trades if trade.loser)
    stop_loss = sum(1 for trade in trades if trade.close_reason == "STOP_LOSS")
    pnl = sum(trade.final_profit for trade in trades)
    return (
        f"count:{len(trades)},wins:{winners},losses:{losses},"
        f"sl:{stop_loss},pnl:{pnl:+.2f}"
    )


def _format_screen_trades(trades: tuple[Any, ...]) -> str:
    if not trades:
        return "NONE"
    return "; ".join(
        f"{trade.signal_timestamp.isoformat()} {trade.direction} "
        f"{trade.close_reason} pnl:{trade.final_profit:+.2f},"
        f"active:{trade.active_age_bars},"
        f"opening:{trade.normalized_opening:.6f},"
        f"opening_d:{trade.opening_delta_t2_t:+.6f},"
        f"slope:{trade.normalized_slope:.6f},"
        f"slope_d:{trade.slope_delta_t2_t:+.6f},"
        f"range_ratio:{trade.signal_range_ratio:.3f}"
        for trade in trades
    )


def _format_combined(result: CombinedReplayResult) -> str:
    pf_text = "NONE" if result.profit_factor is None else f"{result.profit_factor:.4f}"
    return (
        f"trades:{result.trades},wins:{result.winners},losses:{result.losers},"
        f"sl:{result.stop_loss_closes},pd:{result.profit_drawdown_closes},"
        f"pnl:{result.net_profit:+.2f},dd:{result.maximum_drawdown:.2f},"
        f"pf:{pf_text},collapse_rejects:{result.collapse_rejections},"
        f"structural_rejects:{len(result.structural_rejections)}"
    )


def _format_rejections(result: CombinedReplayResult) -> str:
    if not result.structural_rejections:
        return "NONE"
    return "; ".join(
        f"{item.timestamp.isoformat()} {item.direction} {item.matched_guard} "
        f"active:{item.active_age},opening:{item.normalized_opening:.6f},"
        f"opening_d:{item.opening_delta:+.6f},"
        f"slope:{item.normalized_slope:.6f},"
        f"slope_d:{item.slope_delta:+.6f},"
        f"range_ratio:{item.range_ratio:.3f}"
        for item in result.structural_rejections
    )


def _assert_locked_baseline(window: str, result) -> None:
    """Baseline evidence Replay має бути рівно GREEN №33 D."""
    locked = LOCKED_D_RESULTS[window]
    actual = (
        len(result.trades),
        result.winners,
        result.losers,
        result.stop_loss_closes,
        result.profit_drawdown_closes,
        result.net_profit,
    )
    assert actual[:5] == locked[:5]
    assert math.isclose(actual[5], locked[5], rel_tol=0.0, abs_tol=1e-9)


def main() -> None:
    source_30 = _load_module(
        SOURCE_30,
        "roadmap101_deferred_entry_comparison_30_for_35",
    )
    source_33 = _load_module(
        SOURCE_33,
        "roadmap101_opening_collapse_33_for_35",
    )
    source_34 = _load_module(
        SOURCE_34,
        "roadmap101_remaining_sl_34_for_35",
    )
    original_confirmation = (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    )
    assert original_confirmation == 3

    baselines = {}
    combined = {}
    screens: dict[tuple[str, str], tuple[Any, ...]] = {}
    run_source_34_window = getattr(source_34, "_run_window")
    for window, start, end in WINDOWS:
        baseline = run_source_34_window(
            source_30,
            source_33,
            window,
            start,
            end,
        )
        _assert_locked_baseline(window, baseline)
        baselines[window] = baseline
        for guard_name in GUARD_COMPONENTS:
            screens[(window, guard_name)] = _screen_matches(
                baseline.trades,
                guard_name,
            )
        combined[window] = _run_combined(
            source_30,
            source_33,
            window,
            start,
            end,
        )

    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
        == original_confirmation
    )

    validation_impulse = tuple(
        trade
        for trade in baselines["VALIDATION"].trades
        if trade.signal_timestamp.isoformat() == IMPULSE_DIAGNOSTIC_TIMESTAMP
    )
    assert len(validation_impulse) == 1
    impulse = validation_impulse[0]
    assert impulse.close_reason == "STOP_LOSS"
    assert not any(
        impulse in screens[("VALIDATION", guard_name)]
        for guard_name in GUARD_COMPONENTS
    )

    print("Algorithm Workspace Alligator structural-guard counterfactual result")
    print("  mode=SCREEN_3_GUARDS + REAL_COMBINED_COUNTERFACTUAL")
    print("  baseline=D:4BAR+OPENING_COLLAPSE_-0.700")
    print(
        "  screens=WEAK_OPENING_TOO_EARLY_ACTIVE / "
        "VOLATILITY_SPIKE_WITH_DETERIORATION / OVEREXTENDED_TREND"
    )
    print("  weak_rule=active_age<=2 AND normalized_opening<0.500")
    print(
        "  spike_rule=range_ratio>=3.500 AND "
        "(opening_delta<-0.500 OR slope_delta<-0.010)"
    )
    print(
        "  overextended_rule=normalized_slope>=0.200 AND " "normalized_opening>=3.000"
    )
    print("  thresholds=PREDEFINED_STRUCTURAL_NOT_PNL_OPTIMIZED")
    print("  range_reference=MEAN_20_PREVIOUS_COMPLETED_M15_BARS")
    for window, _start, _end in WINDOWS:
        locked = LOCKED_D_RESULTS[window]
        print(
            f"  {window.lower()}_baseline_d="
            f"trades:{locked[0]},wins:{locked[1]},losses:{locked[2]},"
            f"sl:{locked[3]},pd:{locked[4]},pnl:{locked[5]:+.2f},"
            f"dd:{locked[6]:.2f},pf:{locked[7]:.4f}"
        )
        for guard_name in GUARD_COMPONENTS:
            matched = screens[(window, guard_name)]
            key = guard_name.lower()
            print(f"  {window.lower()}_{key}_screen=" f"{_format_screen(matched)}")
            print(
                f"  {window.lower()}_{key}_trades=" f"{_format_screen_trades(matched)}"
            )
        result = combined[window]
        print(
            f"  {window.lower()}_{GUARD_COMBINED.lower()}="
            f"{_format_combined(result)}"
        )
        print(
            f"  {window.lower()}_{GUARD_COMBINED.lower()}_rejected="
            f"{_format_rejections(result)}"
        )

    print(
        "  impulse_candidate_2026_04_21="
        f"NOT_GATED,range_ratio:{impulse.signal_range_ratio:.3f},"
        f"angle:{impulse.macd_effective_angle:.2f},"
        f"pnl:{impulse.final_profit:+.2f}"
    )
    print("  independent_screens_are_observational_on_actual_D_trades=True")
    print("  combined_variant_is_full_counterfactual_replay=True")
    print("  completed_bars_only=True")
    print("  volatility_reference_excludes_signal_bar=True")
    print("  mfe_mae_not_used_as_entry_features=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_confirmation_constant_restored=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_STRUCTURAL_GUARD_COUNTERFACTUAL_CHECK=OK")


if __name__ == "__main__":
    main()
