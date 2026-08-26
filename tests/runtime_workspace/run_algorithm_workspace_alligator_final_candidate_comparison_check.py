# -*- coding: utf-8 -*-
"""Фінальне test-only порівняння Alligator candidate, RoadMap101 №37.

Порівнює зафіксований поточний production A (3-bar confirmation) з єдиним
складеним candidate F:
4-bar confirmation + ARMED/deferred MACD + opening-collapse -0.700 + три
GREEN structural guards №35: WEAK_OPENING_TOO_EARLY_ACTIVE,
VOLATILITY_SPIKE_WITH_DETERIORATION і OVEREXTENDED_TREND.

Candidate складається поверх GREEN №30/33/35 без зміни production trade gate,
algorithm registration або профілів. Усі рішення використовують лише завершені
M15 bars. Volatility reference — 20 попередніх завершених M15 bars, без signal
bar. Тест друкує метрики Development / Validation / Holdout, causal rejection
факти, deferred lifecycle і сумарну різницю проти production A.
"""

from __future__ import annotations

import importlib.util
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
SOURCE_35 = Path(__file__).with_name(
    "run_algorithm_workspace_alligator_structural_guard_counterfactual_check.py"
)

WINDOWS = (
    (
        "DEVELOPMENT",
        "2026-01-02T00:00:00+00:00",
        "2026-02-28T00:00:00+00:00",
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
DEFERRED_SIGNAL_TYPE = "MACD_DEFERRED_RELEASE"
STRUCTURAL_REASON_CODE = "ALLIGATOR_STRUCTURAL_TEST_REJECT"


@dataclass(frozen=True, slots=True)
class StructuralRejection:
    """Один causal signal, відхилений structural guard candidate F."""

    timestamp: datetime
    direction: str
    signal_type: str
    matched_guard: str
    active_age: int
    normalized_slope: float
    normalized_opening: float
    slope_delta: float
    opening_delta: float
    range_ratio: float


@dataclass(frozen=True, slots=True)
class CandidateRun:
    """Результат одного повного Replay candidate F."""

    window: str
    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    take_profit_closes: int
    net_profit: float
    maximum_drawdown: float
    profit_factor: float | None
    collapse_rejections: tuple[Any, ...]
    structural_rejections: tuple[StructuralRejection, ...]
    deferred_releases: tuple[Any, ...]
    deferred_accepted_records: int
    deferred_trades: int
    cancelled_opposite_cross: int
    cancelled_opposite_alligator: int
    cancelled_macd_invalid: int
    deferred_expired: int
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


def _matched_component(
    source_35,
    *,
    active_age: int,
    slope: float,
    opening: float,
    slope_delta: float,
    opening_delta: float,
    range_ratio: float,
) -> str | None:
    weak = (
        active_age <= source_35.WEAK_MAX_ACTIVE_AGE
        and opening < source_35.WEAK_MAX_OPENING
    )
    if weak:
        return source_35.GUARD_WEAK

    deterioration = (
        opening_delta < source_35.SPIKE_MAX_OPENING_DELTA
        or slope_delta < source_35.SPIKE_MAX_SLOPE_DELTA
    )
    spike = range_ratio >= source_35.SPIKE_MIN_RANGE_RATIO and deterioration
    if spike:
        return source_35.GUARD_SPIKE

    overextended = (
        slope >= source_35.OVEREXTENDED_MIN_SLOPE
        and opening >= source_35.OVEREXTENDED_MIN_OPENING
    )
    if overextended:
        return source_35.GUARD_OVEREXTENDED
    return None


def _final_candidate_class(source_30, source_33, source_35):
    """Створити 4BAR+ARMED+collapse+structural candidate F."""
    guarded_deferred_builder = getattr(source_33, "_guarded_deferred_class")
    base = guarded_deferred_builder(source_30)

    class FinalCandidateAlgorithm(base):
        """Test-only повний candidate F без production registration."""

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
            if (
                oldest.normalized_slope is None
                or oldest.normalized_opening is None
            ):
                return output

            event_range = float(event.high - event.low)
            assert event_range > 0.0
            assert prior20_range > 0.0
            range_ratio = event_range / prior20_range
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
                    source_35,
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
                        signal_type=proposal.signal_type,
                        matched_guard=matched,
                        active_age=active_age,
                        normalized_slope=slope,
                        normalized_opening=opening,
                        slope_delta=slope_delta,
                        opening_delta=opening_delta,
                        range_ratio=range_ratio,
                    )
                )
                guarded.append(
                    replace(
                        proposal,
                        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
                        filter_reason_code=STRUCTURAL_REASON_CODE,
                        reason=(
                            f"{proposal.reason}; {STRUCTURAL_REASON_CODE}: "
                            f"{matched}"
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

    return FinalCandidateAlgorithm


def _run_candidate(
    source_30,
    source_33,
    source_35,
    window: str,
    start: str,
    end: str,
) -> CandidateRun:
    """Виконати один повний candidate F Replay."""
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    workspace_factory = getattr(source_30, "_workspace")
    candidate_class = _final_candidate_class(source_30, source_33, source_35)

    def algorithm_factory(algorithm_id: str):
        return candidate_class(algorithm_id)

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
        execution = runtime.replay_execution
        algorithm = runtime.algorithm
        assert summary is not None
        assert execution is not None
        assert algorithm is not None

        records = runtime.signal_records()
        deferred_records = tuple(
            record
            for record in records
            if record.signal_type == DEFERRED_SIGNAL_TYPE and record.accepted
        )
        deferred_uids = {record.signal_uid for record in deferred_records}
        diagnostics = execution.trade_diagnostics()
        deferred_trades = sum(
            1 for trade in diagnostics if trade.signal_uid in deferred_uids
        )

        collapse_rejections = tuple(getattr(algorithm, "guard_rejections", ()))
        structural_rejections = tuple(
            getattr(algorithm, "structural_rejections", ())
        )
        deferred_releases = tuple(getattr(algorithm, "deferred_releases", ()))
        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted

        return CandidateRun(
            window=window,
            trades=summary.opened_trades,
            winners=summary.winning_trades,
            losers=summary.losing_trades,
            stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
            profit_drawdown_closes=summary.close_reason_count(
                "PROFIT_DRAWDOWN"
            ),
            take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
            net_profit=summary.net_profit,
            maximum_drawdown=summary.maximum_drawdown,
            profit_factor=summary.profit_factor,
            collapse_rejections=collapse_rejections,
            structural_rejections=structural_rejections,
            deferred_releases=deferred_releases,
            deferred_accepted_records=len(deferred_records),
            deferred_trades=deferred_trades,
            cancelled_opposite_cross=int(
                getattr(algorithm, "cancelled_opposite_cross", 0)
            ),
            cancelled_opposite_alligator=int(
                getattr(algorithm, "cancelled_opposite_alligator", 0)
            ),
            cancelled_macd_invalid=int(
                getattr(algorithm, "cancelled_macd_invalid", 0)
            ),
            deferred_expired=int(getattr(algorithm, "expired", 0)),
            broker_execution_attempted=broker_execution_attempted,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = (
            original
        )


def _format_baseline(result) -> str:
    pf = "NONE" if result.profit_factor is None else f"{result.profit_factor:.4f}"
    return (
        f"trades:{result.trades},wins:{result.winners},losses:{result.losers},"
        f"sl:{result.stop_loss_closes},pd:{result.profit_drawdown_closes},"
        f"tp:{result.take_profit_closes},pnl:{result.net_profit:+.2f},"
        f"dd:{result.maximum_drawdown:.2f},pf:{pf}"
    )


def _format_candidate(result: CandidateRun) -> str:
    pf = "NONE" if result.profit_factor is None else f"{result.profit_factor:.4f}"
    return (
        f"trades:{result.trades},wins:{result.winners},losses:{result.losers},"
        f"sl:{result.stop_loss_closes},pd:{result.profit_drawdown_closes},"
        f"tp:{result.take_profit_closes},pnl:{result.net_profit:+.2f},"
        f"dd:{result.maximum_drawdown:.2f},pf:{pf},"
        f"collapse_rejects:{len(result.collapse_rejections)},"
        f"structural_rejects:{len(result.structural_rejections)},"
        f"deferred_releases:{len(result.deferred_releases)},"
        f"deferred_accepted:{result.deferred_accepted_records},"
        f"deferred_trades:{result.deferred_trades}"
    )


def _format_delta(baseline, candidate: CandidateRun) -> str:
    return (
        f"trades:{candidate.trades - baseline.trades:+d},"
        f"wins:{candidate.winners - baseline.winners:+d},"
        f"losses:{candidate.losers - baseline.losers:+d},"
        f"sl:{candidate.stop_loss_closes - baseline.stop_loss_closes:+d},"
        f"pnl:{candidate.net_profit - baseline.net_profit:+.2f},"
        f"dd:{candidate.maximum_drawdown - baseline.maximum_drawdown:+.2f}"
    )


def _format_collapse_rejections(result: CandidateRun) -> str:
    if not result.collapse_rejections:
        return "NONE"
    return "; ".join(
        f"{item.timestamp.isoformat()} {item.direction} {item.signal_type} "
        f"opening_delta:{item.opening_delta:+.6f}"
        for item in result.collapse_rejections
    )


def _format_structural_rejections(result: CandidateRun) -> str:
    if not result.structural_rejections:
        return "NONE"
    return "; ".join(
        f"{item.timestamp.isoformat()} {item.direction} {item.signal_type} "
        f"{item.matched_guard} active:{item.active_age},"
        f"opening:{item.normalized_opening:.6f},"
        f"opening_d:{item.opening_delta:+.6f},"
        f"slope:{item.normalized_slope:.6f},"
        f"slope_d:{item.slope_delta:+.6f},"
        f"range_ratio:{item.range_ratio:.3f}"
        for item in result.structural_rejections
    )


def _format_deferred_lifecycle(result: CandidateRun) -> str:
    return (
        f"releases:{len(result.deferred_releases)},"
        f"accepted:{result.deferred_accepted_records},"
        f"trades:{result.deferred_trades},"
        f"opposite_cross:{result.cancelled_opposite_cross},"
        f"opposite_alligator:{result.cancelled_opposite_alligator},"
        f"macd_invalid:{result.cancelled_macd_invalid},"
        f"expired:{result.deferred_expired}"
    )


def _aggregate_baselines(baselines: dict[str, Any]) -> tuple[int, ...] | tuple:
    return (
        sum(item.trades for item in baselines.values()),
        sum(item.winners for item in baselines.values()),
        sum(item.losers for item in baselines.values()),
        sum(item.stop_loss_closes for item in baselines.values()),
        sum(item.profit_drawdown_closes for item in baselines.values()),
        sum(item.take_profit_closes for item in baselines.values()),
        sum(item.net_profit for item in baselines.values()),
    )


def _aggregate_candidates(results: dict[str, CandidateRun]) -> tuple:
    return (
        sum(item.trades for item in results.values()),
        sum(item.winners for item in results.values()),
        sum(item.losers for item in results.values()),
        sum(item.stop_loss_closes for item in results.values()),
        sum(item.profit_drawdown_closes for item in results.values()),
        sum(item.take_profit_closes for item in results.values()),
        sum(item.net_profit for item in results.values()),
    )


def _format_aggregate(values: tuple) -> str:
    trades, wins, losses, sl, pd, tp, pnl = values
    return (
        f"trades:{trades},wins:{wins},losses:{losses},sl:{sl},pd:{pd},"
        f"tp:{tp},sum_pnl:{pnl:+.2f}"
    )


def main() -> None:
    source_30 = _load_module(
        SOURCE_30,
        "roadmap101_deferred_entry_30_for_37",
    )
    source_33 = _load_module(
        SOURCE_33,
        "roadmap101_opening_collapse_33_for_37",
    )
    source_35 = _load_module(
        SOURCE_35,
        "roadmap101_structural_guard_35_for_37",
    )

    original_confirmation = (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    )
    assert original_confirmation == 3
    assert source_35.CONFIRMATION_BARS == CONFIRMATION_BARS
    assert source_35.COLLAPSE_THRESHOLD == COLLAPSE_THRESHOLD
    assert source_35.VOLATILITY_LOOKBACK_BARS == VOLATILITY_LOOKBACK_BARS

    baselines = source_30.A_3BAR
    results: dict[str, CandidateRun] = {}
    for window, start, end in WINDOWS:
        assert window in baselines
        results[window] = _run_candidate(
            source_30,
            source_33,
            source_35,
            window,
            start,
            end,
        )

    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
        == original_confirmation
    )
    assert all(not result.broker_execution_attempted for result in results.values())

    baseline_total = _aggregate_baselines(baselines)
    candidate_total = _aggregate_candidates(results)

    print("Algorithm Workspace Alligator final-candidate comparison result")
    print("  mode=TEST_ONLY_FINAL_CANDIDATE_NO_PRODUCTION_CHANGE")
    print("  variants=A:CURRENT_3BAR / F:FINAL_COMBINED_CANDIDATE")
    print(
        "  candidate_f=4BAR+ARMED+OPENING_COLLAPSE_-0.700+"
        "WEAK_OPENING+VOLATILITY_SPIKE_DETERIORATION+OVEREXTENDED"
    )
    print("  source_chain=GREEN_ROADMAP101_30/33/35")
    print("  deferred_expiry_bars=5")
    print("  collapse_threshold=-0.700")
    print(
        "  weak_rule=active_age<=2 AND normalized_opening<0.500"
    )
    print(
        "  spike_rule=range_ratio>=3.500 AND "
        "(opening_delta<-0.500 OR slope_delta<-0.010)"
    )
    print(
        "  overextended_rule=normalized_slope>=0.200 AND "
        "normalized_opening>=3.000"
    )
    print("  range_reference=MEAN_20_PREVIOUS_COMPLETED_M15_BARS")

    for window, _start, _end in WINDOWS:
        baseline = baselines[window]
        result = results[window]
        key = window.lower()
        print(f"  {key}_a_current_3bar={_format_baseline(baseline)}")
        print(f"  {key}_f_final_candidate={_format_candidate(result)}")
        print(f"  {key}_f_minus_a={_format_delta(baseline, result)}")
        print(
            f"  {key}_collapse_rejected="
            f"{_format_collapse_rejections(result)}"
        )
        print(
            f"  {key}_structural_rejected="
            f"{_format_structural_rejections(result)}"
        )
        print(
            f"  {key}_deferred_lifecycle="
            f"{_format_deferred_lifecycle(result)}"
        )

    print(f"  aggregate_a_current_3bar={_format_aggregate(baseline_total)}")
    print(f"  aggregate_f_final_candidate={_format_aggregate(candidate_total)}")
    print(
        "  aggregate_f_minus_a="
        f"trades:{candidate_total[0] - baseline_total[0]:+d},"
        f"wins:{candidate_total[1] - baseline_total[1]:+d},"
        f"losses:{candidate_total[2] - baseline_total[2]:+d},"
        f"sl:{candidate_total[3] - baseline_total[3]:+d},"
        f"sum_pnl:{candidate_total[6] - baseline_total[6]:+.2f}"
    )
    print("  candidate_uses_completed_bars_only=True")
    print("  volatility_reference_excludes_signal_bar=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_confirmation_constant_restored=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_FINAL_CANDIDATE_COMPARISON_CHECK=OK")


if __name__ == "__main__":
    main()
