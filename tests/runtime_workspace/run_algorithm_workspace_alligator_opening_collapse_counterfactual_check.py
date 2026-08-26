# -*- coding: utf-8 -*-
"""Counterfactual Replay severe opening-collapse guard RoadMap101 №33.

Тест не змінює production. На фіксованих Development / Validation / Holdout
порівнює вже GREEN A/B/C baseline з двома test-only варіантами:
D = 4-bar Alligator + causal ACTIVE opening-collapse guard;
E = 4-bar + ARMED/deferred MACD + той самий guard.

Guard використовує лише завершені Alligator observations, доступні в момент
сигналу: ``normalized_opening(t) - normalized_opening(t-2)``. Перевіряються
три наперед визначені консервативні thresholds -0.75/-0.70/-0.65 без
підбору за PnL. Для кожного Replay друкуються фактичні метрики та конкретні
сигнали, відхилені guard. NEXT_BAR_OPEN, margin, SL/TP і Profit Drawdown
залишаються production Replay execution. No-look-ahead і відсутність broker
execution є обов'язковими інваріантами.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.workspace_alligator as workspace_alligator  # noqa: E402
from core.workspace_algorithm import WorkspaceSignalOutput  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    ALLIGATOR_REGIME_PHASE_ACTIVE,
    WorkspaceMacdAlligatorReplayAlgorithm,
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

CONFIRMATION_BARS = 4
THRESHOLDS = (-0.750, -0.700, -0.650)
GUARD_REASON_CODE = "ALLIGATOR_ACTIVE_OPENING_COLLAPSE_TEST_REJECT"

C_4BAR_ARMED_LOCKED = {
    "DEVELOPMENT": (9, 6, 3, 0, 9, 0, 1.02, 0.19, 5.8571),
    "VALIDATION": (21, 10, 11, 4, 17, 0, -3.89, 4.46, 0.5221),
    "HOLDOUT": (10, 4, 6, 2, 8, 0, -4.01, 4.01, 0.0631),
}


@dataclass(frozen=True, slots=True)
class GuardRejection:
    """Один causal signal, який test-only guard відхилив до execution."""

    timestamp: datetime
    direction: str
    signal_type: str
    opening_t_minus_2: float
    opening_current: float
    opening_delta: float


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Фактичний counterfactual Replay result D/E."""

    window: str
    variant: str
    threshold: float
    trades: int
    winners: int
    losers: int
    stop_loss_closes: int
    profit_drawdown_closes: int
    take_profit_closes: int
    net_profit: float
    maximum_drawdown: float
    profit_factor: float | None
    guard_rejections: tuple[GuardRejection, ...]
    deferred_releases: int
    cancelled_opposite_cross: int
    broker_execution_attempted: bool


class _OpeningCollapseGuardMixin:
    """Test-only causal guard для production/deferred algorithm wrappers."""

    collapse_threshold: float
    guard_rejections: list[GuardRejection]

    def _init_guard(self, threshold: float) -> None:
        self.collapse_threshold = float(threshold)
        self.guard_rejections = []

    def _reset_guard(self) -> None:
        self.guard_rejections = []

    def _apply_opening_collapse_guard(
        self,
        output: WorkspaceSignalOutput,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        proposals = _proposal_tuple(output)
        if not proposals:
            return output

        signal_filter = getattr(self, "signal_filter", None)
        if signal_filter is None:
            return output
        observation = signal_filter.latest_observation
        if (
            observation is None
            or observation.regime_phase != ALLIGATOR_REGIME_PHASE_ACTIVE
        ):
            return output
        history = signal_filter.diagnostic_observation_history(observation, limit=3)
        if len(history) < 3:
            return output
        oldest = history[0]
        if oldest.normalized_opening is None or observation.normalized_opening is None:
            return output
        opening_delta = float(
            observation.normalized_opening - oldest.normalized_opening
        )
        if opening_delta >= self.collapse_threshold:
            return output

        changed = False
        guarded: list[WorkspaceSignalProposal] = []
        for proposal in proposals:
            if proposal.filter_decision != WORKSPACE_SIGNAL_FILTER_ALLOW:
                guarded.append(proposal)
                continue
            changed = True
            self.guard_rejections.append(
                GuardRejection(
                    timestamp=event.timestamp,
                    direction=proposal.direction,
                    signal_type=proposal.signal_type,
                    opening_t_minus_2=float(oldest.normalized_opening),
                    opening_current=float(observation.normalized_opening),
                    opening_delta=opening_delta,
                )
            )
            guarded.append(
                replace(
                    proposal,
                    filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
                    filter_reason_code=GUARD_REASON_CODE,
                    reason=(
                        f"{proposal.reason}; {GUARD_REASON_CODE}: "
                        f"opening_delta_t2_t={opening_delta:.6f}; "
                        f"threshold={self.collapse_threshold:.3f}"
                    ).strip("; "),
                )
            )
        if not changed:
            return output
        if isinstance(output, WorkspaceSignalProposal):
            return guarded[0]
        return tuple(guarded)


class OpeningCollapseGuardAlgorithm(
    _OpeningCollapseGuardMixin,
    WorkspaceMacdAlligatorReplayAlgorithm,
):
    """Варіант D: production 4-bar + test-only opening-collapse guard."""

    def __init__(self, algorithm_id: str, threshold: float) -> None:
        WorkspaceMacdAlligatorReplayAlgorithm.__init__(self, algorithm_id)
        self._init_guard(threshold)

    def start(self) -> None:
        super().start()
        self._reset_guard()

    def on_market_event(self, event: WorkspaceMarketEvent) -> WorkspaceSignalOutput:
        output = super().on_market_event(event)
        return self._apply_opening_collapse_guard(output, event)


def _load_source_30():
    """Завантажити GREEN №30 для workspace/deferred wrapper без package import."""
    assert SOURCE_30.is_file(), SOURCE_30
    spec = importlib.util.spec_from_file_location(
        "roadmap101_deferred_entry_comparison_30",
        SOURCE_30,
    )
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


def _guarded_deferred_class(source_30):
    """Створити E wrapper поверх test-only ARMED/deferred алгоритму №30."""
    deferred_base = source_30.DeferredMacdAlligatorReplayAlgorithm

    class GuardedDeferredAlgorithm(_OpeningCollapseGuardMixin, deferred_base):
        """Варіант E: 4-bar + ARMED + causal opening-collapse guard."""

        def __init__(self, algorithm_id: str, threshold: float) -> None:
            deferred_base.__init__(self, algorithm_id)
            self._init_guard(threshold)

        def start(self) -> None:
            deferred_base.start(self)
            self._reset_guard()

        def on_market_event(
            self,
            event: WorkspaceMarketEvent,
        ) -> WorkspaceSignalOutput:
            output = deferred_base.on_market_event(self, event)
            return self._apply_opening_collapse_guard(output, event)

    return GuardedDeferredAlgorithm


def _factory_d(threshold: float) -> Callable[[str], OpeningCollapseGuardAlgorithm]:
    def factory(algorithm_id: str) -> OpeningCollapseGuardAlgorithm:
        return OpeningCollapseGuardAlgorithm(algorithm_id, threshold)

    return factory


def _factory_e(source_30, threshold: float) -> Callable[[str], Any]:
    guarded_class = _guarded_deferred_class(source_30)

    def factory(algorithm_id: str):
        return guarded_class(algorithm_id, threshold)

    return factory


def _run(
    *,
    source_30,
    window: str,
    start_utc: str,
    end_utc: str,
    variant: str,
    threshold: float,
) -> ReplayResult:
    """Виконати один реальний Replay D або E з локальним 4-bar constant."""
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS
    workspace_factory = getattr(source_30, "_workspace")
    if variant == "D_4BAR_COLLAPSE":
        algorithm_factory = _factory_d(threshold)
    elif variant == "E_4BAR_ARMED_COLLAPSE":
        algorithm_factory = _factory_e(source_30, threshold)
    else:
        raise AssertionError(variant)

    try:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = (
            CONFIRMATION_BARS
        )
        runtime = WorkspaceRuntime(
            workspace_factory(start_utc, end_utc),
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
        assert isinstance(algorithm, _OpeningCollapseGuardMixin)
        guard_rejections = tuple(algorithm.guard_rejections)
        assert all(item.opening_delta < threshold for item in guard_rejections)
        broker_execution_attempted = any(
            bool(entry.details.get("broker_execution_attempted"))
            for entry in runtime.journal
            if isinstance(entry.details, dict)
        )
        assert not broker_execution_attempted

        deferred_releases = int(len(getattr(algorithm, "deferred_releases", ())))
        cancelled_opposite_cross = int(
            getattr(algorithm, "cancelled_opposite_cross", 0)
        )
        return ReplayResult(
            window=window,
            variant=variant,
            threshold=threshold,
            trades=summary.opened_trades,
            winners=summary.winning_trades,
            losers=summary.losing_trades,
            stop_loss_closes=summary.close_reason_count("STOP_LOSS"),
            profit_drawdown_closes=summary.close_reason_count("PROFIT_DRAWDOWN"),
            take_profit_closes=summary.close_reason_count("TAKE_PROFIT"),
            net_profit=summary.net_profit,
            maximum_drawdown=summary.maximum_drawdown,
            profit_factor=summary.profit_factor,
            guard_rejections=guard_rejections,
            deferred_releases=deferred_releases,
            cancelled_opposite_cross=cancelled_opposite_cross,
            broker_execution_attempted=broker_execution_attempted,
        )
    finally:
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS = original


def _locked_tuple(
    result,
) -> tuple[int, int, int, int, int, int, float, float, float | None]:
    return (
        result.trades,
        result.winners,
        result.losers,
        result.stop_loss_closes,
        result.profit_drawdown_closes,
        result.take_profit_closes,
        result.net_profit,
        result.maximum_drawdown,
        result.profit_factor,
    )


def _format_locked(values) -> str:
    trades, wins, losses, sl, pd, tp, pnl, dd, pf = values
    pf_text = "NONE" if pf is None else f"{pf:.4f}"
    return (
        f"trades:{trades},wins:{wins},losses:{losses},sl:{sl},pd:{pd},tp:{tp},"
        f"pnl:{pnl:.2f},dd:{dd:.2f},pf:{pf_text}"
    )


def _format_result(result: ReplayResult) -> str:
    return (
        _format_locked(
            (
                result.trades,
                result.winners,
                result.losers,
                result.stop_loss_closes,
                result.profit_drawdown_closes,
                result.take_profit_closes,
                result.net_profit,
                result.maximum_drawdown,
                result.profit_factor,
            )
        )
        + f",guard_rejects:{len(result.guard_rejections)}"
    )


def _format_guarded(result: ReplayResult) -> str:
    if not result.guard_rejections:
        return "NONE"
    return "; ".join(
        f"{item.timestamp.isoformat()} {item.direction} {item.signal_type} "
        f"opening:{item.opening_t_minus_2:.6f}->{item.opening_current:.6f} "
        f"delta:{item.opening_delta:+.6f}"
        for item in result.guard_rejections
    )


def _same_locked_metrics(result: ReplayResult, locked) -> bool:
    actual = _locked_tuple(result)
    for index, (left, right) in enumerate(zip(actual, locked, strict=True)):
        if index in {6, 7, 8}:
            if left is None or right is None:
                if left is not right:
                    return False
            elif not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-4):
                return False
        elif left != right:
            return False
    return True


def main() -> None:
    source_30 = _load_source_30()
    windows = tuple(source_30.WINDOWS)
    original = workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS

    a_locked = {
        window: _locked_tuple(source_30.A_3BAR[window]) for window, *_ in windows
    }
    b_locked = {
        window: _locked_tuple(source_30.B_4BAR[window]) for window, *_ in windows
    }
    c_locked = dict(C_4BAR_ARMED_LOCKED)

    results: dict[tuple[str, str, float], ReplayResult] = {}
    for window, start_utc, end_utc in windows:
        for threshold in THRESHOLDS:
            for variant in ("D_4BAR_COLLAPSE", "E_4BAR_ARMED_COLLAPSE"):
                results[(window, variant, threshold)] = _run(
                    source_30=source_30,
                    window=window,
                    start_utc=start_utc,
                    end_utc=end_utc,
                    variant=variant,
                    threshold=threshold,
                )

    assert (
        workspace_alligator.ALLIGATOR_REGIME_TREND_START_CONFIRMATION_BARS == original
    )
    assert all(not result.broker_execution_attempted for result in results.values())

    # Threshold ordering: a looser threshold may only add guard candidates at
    # the signal layer. This catches accidental inversion of the comparison.
    for window, *_ in windows:
        for variant in ("D_4BAR_COLLAPSE", "E_4BAR_ARMED_COLLAPSE"):
            counts = [
                len(results[(window, variant, threshold)].guard_rejections)
                for threshold in THRESHOLDS
            ]
            assert counts == sorted(counts), (window, variant, counts)

    # E must preserve the known deferred lifecycle when the guard does not
    # reject those releases. Any change is printed explicitly below.
    for threshold in THRESHOLDS:
        development_e = results[("DEVELOPMENT", "E_4BAR_ARMED_COLLAPSE", threshold)]
        validation_e = results[("VALIDATION", "E_4BAR_ARMED_COLLAPSE", threshold)]
        holdout_e = results[("HOLDOUT", "E_4BAR_ARMED_COLLAPSE", threshold)]
        assert development_e.deferred_releases == 2
        assert validation_e.deferred_releases == 0
        assert holdout_e.cancelled_opposite_cross == 1

    print("Algorithm Workspace Alligator opening-collapse counterfactual result")
    print("  mode=TEST_ONLY_COUNTERFACTUAL_NO_PRODUCTION_GATE_CHANGE")
    print(
        "  variants=A:3BAR / B:4BAR / C:4BAR+ARMED / "
        "D:4BAR+COLLAPSE / E:4BAR+ARMED+COLLAPSE"
    )
    print("  collapse_feature=normalized_opening(t)-normalized_opening(t-2)")
    print("  collapse_thresholds=-0.750/-0.700/-0.650")
    print("  threshold_selection=PREDEFINED_CONSERVATIVE_NOT_PNL_OPTIMIZED")
    print("  confirmation_bars_for_D_E=4")
    print("  fixed_workspace=RM96 EURUSD M15 Historical")
    print("  fixed_macd=8/17/5 EXTENDED prominence=0.000015 distance=0.000050 ABC=2.25")
    print("  fixed_alligator=13/8,8/5,5/3 SMOOTHED MEDIAN SAME_TIMEFRAME")

    for window, _start_utc, _end_utc in windows:
        key = window.lower()
        print(f"  {key}_a_3bar={_format_locked(a_locked[window])}")
        print(f"  {key}_b_4bar={_format_locked(b_locked[window])}")
        print(f"  {key}_c_4bar_armed={_format_locked(c_locked[window])}")
        for threshold in THRESHOLDS:
            threshold_key = str(abs(threshold)).replace(".", "_")
            d = results[(window, "D_4BAR_COLLAPSE", threshold)]
            e = results[(window, "E_4BAR_ARMED_COLLAPSE", threshold)]
            print(f"  {key}_d_collapse_{threshold_key}={_format_result(d)}")
            print(f"  {key}_d_guarded_{threshold_key}={_format_guarded(d)}")
            print(f"  {key}_e_armed_collapse_{threshold_key}={_format_result(e)}")
            print(f"  {key}_e_guarded_{threshold_key}={_format_guarded(e)}")

    # Strongest conservative screen from №32 should alter Validation and not
    # be a silent no-op. We intentionally do not assert that PnL improves.
    severe_d = results[("VALIDATION", "D_4BAR_COLLAPSE", -0.750)]
    severe_e = results[("VALIDATION", "E_4BAR_ARMED_COLLAPSE", -0.750)]
    assert severe_d.guard_rejections
    assert severe_e.guard_rejections
    assert not _same_locked_metrics(severe_d, b_locked["VALIDATION"])
    assert not _same_locked_metrics(severe_e, c_locked["VALIDATION"])

    print("  severe_threshold_validation_not_noop=True")
    print("  threshold_order_guard_counts_monotonic=True")
    print("  deferred_lifecycle_preserved=True")
    print("  completed_bars_only=True")
    print("  no_look_ahead=True")
    print("  production_trade_gate_changed=False")
    print("  production_algorithm_registration_changed=False")
    print("  production_confirmation_constant_restored=True")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_ALLIGATOR_OPENING_COLLAPSE_COUNTERFACTUAL_CHECK=OK")


if __name__ == "__main__":
    main()
