# -*- coding: utf-8 -*-
"""RoadMap102: test-only delayed transition entry D3/D3+S за 2025 рік.

Runner використовує frozen OOS Candidate F і causal transition episodes 05H.
Для всіх episodes, незалежно від майбутнього outcome, test-only schedule формує
лише два вже зафіксовані confirmation variants:
D3 — close третього завершеного M15 bar пішов у напрямку opposite Quality MACD;
D3+S — те саме плюс deterioration slope старого Alligator на signal bar.

На confirmation bar додається окремий shadow signal. Далі використовується
штатний Historical Replay execution: NEXT_BAR_OPEN, той самий spread, SL/TP,
Profit Drawdown, maximum open positions і margin. Production MACD Quality,
Alligator та Candidate F не змінюються. Майбутній outcome transition episode
не використовується як gate. Performance assertions відсутні.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_algorithm_workspace_candidate_f_frozen_oos_2025_check as frozen  # noqa: E402
from run_algorithm_workspace_candidate_f_alligator_transition_lag_2025_check import (  # noqa: E402,E501
    TransitionDiagnosticDataset,
    TransitionEpisode,
    build_transition_diagnostic_dataset,
)

from core.workspace_algorithm import WorkspaceSignalOutput  # noqa: E402
from core.workspace_alligator import (  # noqa: E402
    WorkspaceAlligatorObservation,
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)

EXPECTED_M15_DELTA = timedelta(minutes=15)
VARIANT_D3 = "D3"
VARIANT_D3_S = "D3+S"
VARIANTS = (VARIANT_D3, VARIANT_D3_S)
SHADOW_SIGNAL_TYPES = {
    VARIANT_D3: "TRANSITION_D3",
    VARIANT_D3_S: "TRANSITION_D3S",
}


@dataclass(frozen=True, slots=True)
class TransitionShadowTrigger:
    """Один causal delayed confirmation, дозволений без future outcome."""

    variant: str
    original_signal_timestamp: datetime
    confirmation_timestamp: datetime
    direction: str
    original_signal_close: float
    confirmation_close: float
    signal_slope_deteriorating: bool


@dataclass(frozen=True, slots=True)
class DelayedEntryVariantResult:
    """Підсумок одного повного counterfactual Historical Replay variant."""

    variant: str
    scheduled_confirmations: int
    accepted_shadow_records: int
    shadow_trades: int
    shadow_wins: int
    shadow_losses: int
    shadow_break_even: int
    shadow_net_profit: float
    shadow_profit_factor: float | None
    shadow_drawdown: float
    shadow_stop_loss_closes: int
    shadow_take_profit_closes: int
    shadow_profit_drawdown_closes: int
    portfolio_trades: int
    portfolio_wins: int
    portfolio_losses: int
    portfolio_break_even: int
    portfolio_net_profit: float
    portfolio_profit_factor: float | None
    portfolio_drawdown: float
    production_signal_records_unchanged: bool
    broker_execution_attempted: bool


class DelayedTransitionShadowAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Production Candidate F плюс test-only delayed transition confirmations."""

    def __init__(
        self,
        algorithm_id: str,
        variant: str,
        triggers: tuple[TransitionShadowTrigger, ...],
    ) -> None:
        super().__init__(algorithm_id)
        normalized_variant = str(variant or "").strip().upper()
        if normalized_variant not in VARIANTS:
            raise ValueError(f"Unsupported delayed transition variant: {variant}")
        self.variant = normalized_variant
        self.triggers = tuple(
            trigger for trigger in triggers if trigger.variant == normalized_variant
        )
        self.triggers_by_timestamp: dict[
            datetime,
            tuple[TransitionShadowTrigger, ...],
        ] = {}
        grouped: dict[datetime, list[TransitionShadowTrigger]] = {}
        for trigger in self.triggers:
            grouped.setdefault(trigger.confirmation_timestamp, []).append(trigger)
        self.triggers_by_timestamp = {
            timestamp: tuple(items) for timestamp, items in grouped.items()
        }

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalOutput:
        base_output = super().on_market_event(event)
        triggers = self.triggers_by_timestamp.get(event.timestamp, ())
        if not triggers:
            return base_output

        proposals = list(_output_tuple(base_output))
        for trigger in triggers:
            proposals.append(self._shadow_proposal(trigger))
        return tuple(proposals)

    def _shadow_proposal(
        self,
        trigger: TransitionShadowTrigger,
    ) -> WorkspaceSignalProposal:
        source = self.source
        if source is None:
            raise AssertionError("MACD source must exist")
        signal_type = SHADOW_SIGNAL_TYPES[self.variant]
        direction = trigger.direction
        macd_state = "MACD_CROSS_UP" if direction == "BUY" else "MACD_CROSS_DOWN"
        strength = abs(trigger.confirmation_close - trigger.original_signal_close)
        return WorkspaceSignalProposal(
            signal_type=signal_type,
            direction=direction,
            strength=strength,
            macd_state=macd_state,
            alligator_confirmation=f"TEST_ONLY_{self.variant}_CONFIRMATION",
            reason=(
                f"TEST_ONLY_{self.variant}_DELAYED_TRANSITION_CONFIRMATION; "
                f"original_signal={trigger.original_signal_timestamp.isoformat()}; "
                "confirmation_completed_bars=3; "
                f"signal_slope_deteriorating={trigger.signal_slope_deteriorating}; "
                "execution=PRODUCTION_NEXT_BAR_OPEN"
            ),
            source_reason_code=f"TEST_ONLY_{self.variant}_CONFIRMATION",
            source_profile_uid=source.profile_uid,
            source_profile_revision=source.profile_revision,
            filter_decision=WORKSPACE_SIGNAL_FILTER_ALLOW,
        )


def _output_tuple(
    output: WorkspaceSignalOutput,
) -> tuple[WorkspaceSignalProposal, ...]:
    if output is None:
        return ()
    if isinstance(output, WorkspaceSignalProposal):
        return (output,)
    return tuple(output)


def _direction_sign(direction: str) -> float:
    if direction == "BUY":
        return 1.0
    if direction == "SELL":
        return -1.0
    raise AssertionError(direction)


def _continuous_three_bars(
    episode: TransitionEpisode,
    events: tuple[WorkspaceMarketEvent, ...],
) -> bool:
    if episode.horizon_bars < 3:
        return False
    end_index = episode.signal_index + 3
    for index in range(episode.signal_index + 1, end_index + 1):
        if events[index].timestamp - events[index - 1].timestamp != EXPECTED_M15_DELTA:
            return False
    return True


def _signal_slope_deteriorating(
    episode: TransitionEpisode,
    *,
    events: tuple[WorkspaceMarketEvent, ...],
    observations_by_timestamp: dict[datetime, WorkspaceAlligatorObservation],
) -> bool | None:
    if episode.signal_index <= 0:
        return None
    current_event = events[episode.signal_index]
    previous_event = events[episode.signal_index - 1]
    if current_event.timestamp - previous_event.timestamp != EXPECTED_M15_DELTA:
        return None
    current = observations_by_timestamp.get(current_event.timestamp)
    previous = observations_by_timestamp.get(previous_event.timestamp)
    if current is None or previous is None:
        return None
    if current.normalized_slope is None or previous.normalized_slope is None:
        return None
    return current.normalized_slope < previous.normalized_slope


def _build_trigger_sets(
    dataset: TransitionDiagnosticDataset,
) -> dict[str, tuple[TransitionShadowTrigger, ...]]:
    events = dataset.events
    observations_by_timestamp = {
        observation.timestamp: observation for observation in dataset.observations
    }
    result: dict[str, list[TransitionShadowTrigger]] = {
        VARIANT_D3: [],
        VARIANT_D3_S: [],
    }

    for episode in dataset.episodes:
        if not _continuous_three_bars(episode, events):
            continue
        signal_event = events[episode.signal_index]
        confirmation_event = events[episode.signal_index + 3]
        sign = _direction_sign(episode.target_direction)
        if sign * (confirmation_event.close - signal_event.close) <= 0.0:
            continue

        slope_deteriorating = _signal_slope_deteriorating(
            episode,
            events=events,
            observations_by_timestamp=observations_by_timestamp,
        )
        base_trigger = TransitionShadowTrigger(
            variant=VARIANT_D3,
            original_signal_timestamp=episode.signal_timestamp,
            confirmation_timestamp=confirmation_event.timestamp,
            direction=episode.target_direction,
            original_signal_close=signal_event.close,
            confirmation_close=confirmation_event.close,
            signal_slope_deteriorating=bool(slope_deteriorating),
        )
        result[VARIANT_D3].append(base_trigger)
        if slope_deteriorating:
            result[VARIANT_D3_S].append(
                TransitionShadowTrigger(
                    variant=VARIANT_D3_S,
                    original_signal_timestamp=episode.signal_timestamp,
                    confirmation_timestamp=confirmation_event.timestamp,
                    direction=episode.target_direction,
                    original_signal_close=signal_event.close,
                    confirmation_close=confirmation_event.close,
                    signal_slope_deteriorating=True,
                )
            )

    return {name: tuple(items) for name, items in result.items()}


def _signal_signature(
    record: WorkspaceSignalRecord,
) -> tuple[object, ...]:
    return (
        record.timestamp,
        record.signal_type,
        record.direction,
        record.accepted,
        record.source_reason_code,
        record.filter_decision,
        record.filter_reason_code,
    )


def _production_signal_signatures(
    records: tuple[WorkspaceSignalRecord, ...],
) -> tuple[tuple[object, ...], ...]:
    shadow_types = set(SHADOW_SIGNAL_TYPES.values())
    return tuple(
        _signal_signature(record)
        for record in records
        if record.signal_type not in shadow_types
    )


def _profit_factor(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> float | None:
    gross_profit = sum(max(0.0, trade.final_profit) for trade in trades)
    gross_loss = -sum(min(0.0, trade.final_profit) for trade in trades)
    if gross_loss <= 0.0:
        return None
    return gross_profit / gross_loss


def _closed_pnl_drawdown(
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
) -> float:
    running = 0.0
    peak = 0.0
    maximum = 0.0
    for trade in sorted(trades, key=lambda item: item.close_timestamp):
        running += trade.final_profit
        peak = max(peak, running)
        maximum = max(maximum, peak - running)
    return maximum


def _run_variant(
    variant: str,
    triggers: tuple[TransitionShadowTrigger, ...],
    *,
    baseline_signatures: tuple[tuple[object, ...], ...],
) -> DelayedEntryVariantResult:
    frozen.assert_frozen_oos_snapshot()
    algorithm = DelayedTransitionShadowAlgorithm(
        "RailAlgorithm",
        variant,
        triggers,
    )
    runtime = frozen.FrozenOosRuntime(
        frozen.frozen_oos_workspace(),
        algorithm_factory=lambda _algorithm_id: algorithm,
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

    records = runtime.historical_signal_records_for_test()
    signal_type = SHADOW_SIGNAL_TYPES[variant]
    shadow_records = tuple(
        record for record in records if record.signal_type == signal_type
    )
    accepted_shadow_records = tuple(
        record for record in shadow_records if record.accepted
    )
    accepted_uids = {record.signal_uid for record in accepted_shadow_records}
    all_trades = execution.trade_diagnostics()
    shadow_trades = tuple(
        trade for trade in all_trades if trade.signal_uid in accepted_uids
    )

    wins = sum(trade.final_profit > 0.0 for trade in shadow_trades)
    losses = sum(trade.final_profit < 0.0 for trade in shadow_trades)
    break_even = len(shadow_trades) - wins - losses
    close_reasons = {
        reason: sum(trade.close_reason == reason for trade in shadow_trades)
        for reason in ("STOP_LOSS", "TAKE_PROFIT", "PROFIT_DRAWDOWN")
    }
    production_signatures = _production_signal_signatures(records)
    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted
    assert len(shadow_records) == len(triggers)
    assert len(accepted_shadow_records) == len(triggers)

    return DelayedEntryVariantResult(
        variant=variant,
        scheduled_confirmations=len(triggers),
        accepted_shadow_records=len(accepted_shadow_records),
        shadow_trades=len(shadow_trades),
        shadow_wins=wins,
        shadow_losses=losses,
        shadow_break_even=break_even,
        shadow_net_profit=sum(trade.final_profit for trade in shadow_trades),
        shadow_profit_factor=_profit_factor(shadow_trades),
        shadow_drawdown=_closed_pnl_drawdown(shadow_trades),
        shadow_stop_loss_closes=close_reasons["STOP_LOSS"],
        shadow_take_profit_closes=close_reasons["TAKE_PROFIT"],
        shadow_profit_drawdown_closes=close_reasons["PROFIT_DRAWDOWN"],
        portfolio_trades=summary.opened_trades,
        portfolio_wins=summary.winning_trades,
        portfolio_losses=summary.losing_trades,
        portfolio_break_even=summary.break_even_trades,
        portfolio_net_profit=summary.net_profit,
        portfolio_profit_factor=summary.profit_factor,
        portfolio_drawdown=summary.maximum_drawdown,
        production_signal_records_unchanged=production_signatures
        == baseline_signatures,
        broker_execution_attempted=broker_execution_attempted,
    )


def _fmt_pf(value: float | None) -> str:
    return "NONE" if value is None else f"{value:.4f}"


def main() -> None:
    dataset = build_transition_diagnostic_dataset()
    baseline_summary = dataset.runtime.historical_summary
    assert baseline_summary is not None
    baseline_records = dataset.runtime.historical_signal_records_for_test()
    baseline_signatures = _production_signal_signatures(baseline_records)
    trigger_sets = _build_trigger_sets(dataset)

    assert trigger_sets[VARIANT_D3]
    assert trigger_sets[VARIANT_D3_S]
    assert (
        set(trigger_sets[VARIANT_D3_S]).issubset(set(trigger_sets[VARIANT_D3])) is False
    )

    results = tuple(
        _run_variant(
            variant,
            trigger_sets[variant],
            baseline_signatures=baseline_signatures,
        )
        for variant in VARIANTS
    )
    assert all(item.production_signal_records_unchanged for item in results)
    assert all(not item.broker_execution_attempted for item in results)

    print("Algorithm Workspace Candidate F Transition Delayed Entry 2025 result")
    print("  mode=TEST_ONLY_FIXED_D3_D3S_COUNTERFACTUAL_EXECUTION")
    print(
        "  baseline="
        f"trades:{baseline_summary.opened_trades},"
        f"wins:{baseline_summary.winning_trades},"
        f"losses:{baseline_summary.losing_trades},"
        f"break_even:{baseline_summary.break_even_trades},"
        f"net:{baseline_summary.net_profit:+.2f},"
        f"pf:{_fmt_pf(baseline_summary.profit_factor)},"
        f"dd:{baseline_summary.maximum_drawdown:.2f}"
    )
    print("  variants=D3;D3+S")
    print("  confirmation_delay_bars=3")
    print("  entry_policy=NEXT_BAR_OPEN")
    print("  production_candidate_f_signals_preserved=True")
    for item in results:
        print(f"  {item.variant}:")
        print(
            "    confirmations="
            f"scheduled:{item.scheduled_confirmations},"
            f"accepted_records:{item.accepted_shadow_records},"
            f"filled_trades:{item.shadow_trades}"
        )
        print(
            "    shadow_trades="
            f"wins:{item.shadow_wins},losses:{item.shadow_losses},"
            f"break_even:{item.shadow_break_even},"
            f"net:{item.shadow_net_profit:+.2f},"
            f"pf:{_fmt_pf(item.shadow_profit_factor)},"
            f"closed_pnl_dd:{item.shadow_drawdown:.2f}"
        )
        print(
            "    shadow_closes="
            f"sl:{item.shadow_stop_loss_closes},"
            f"tp:{item.shadow_take_profit_closes},"
            f"profit_drawdown:{item.shadow_profit_drawdown_closes}"
        )
        print(
            "    full_portfolio="
            f"trades:{item.portfolio_trades},wins:{item.portfolio_wins},"
            f"losses:{item.portfolio_losses},"
            f"break_even:{item.portfolio_break_even},"
            f"net:{item.portfolio_net_profit:+.2f},"
            f"pf:{_fmt_pf(item.portfolio_profit_factor)},"
            f"dd:{item.portfolio_drawdown:.2f}"
        )
        print(
            "    production_signal_records_unchanged="
            f"{item.production_signal_records_unchanged}"
        )
    print("  schedule_uses_transition_outcome=False")
    print("  confirmation_uses_completed_m15_bars_only=True")
    print("  future_outcome_used_as_entry_gate=False")
    print("  alligator_thresholds_changed=False")
    print("  macd_quality_thresholds_changed=False")
    print("  candidate_f_thresholds_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  performance_threshold_assertions=False")
    print("ALGORITHM_WORKSPACE_CANDIDATE_F_TRANSITION_DELAYED_ENTRY_2025_CHECK=OK")


if __name__ == "__main__":
    main()
