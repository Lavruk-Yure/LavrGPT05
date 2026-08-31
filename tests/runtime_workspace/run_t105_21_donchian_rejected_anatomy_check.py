# -*- coding: utf-8 -*-
"""T105-21: anatomy of Donchian-rejected current-production survivors."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass

from run_algorithm_workspace_replay_virtual_execution_check import BrokerRequestProbe
from run_t105_10_pd_35_production_regression_check import PeriodSpec, _workspace
from run_t105_11_donchian_entry_anatomy_check import (
    DONCHIAN_PERIOD,
    DONCHIAN_SHIFT,
    PIP_SIZE,
    DonchianAnatomyRuntime,
    DonchianEntryRow,
)
from run_t105_11_donchian_entry_anatomy_check import _build_rows as _build_donchian_rows
from run_t105_11_donchian_entry_anatomy_check import (
    _production_hashes,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    OUTCOME_BREAK_EVEN,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    StochasticAnatomyRuntime,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    _build_rows as _build_stochastic_rows,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (
    PERIODS,
    _assert_geometry,
    _assert_metrics,
    _assert_policy,
    _assert_stochastic_path,
    _broker_execution_attempted,
)

from core.workspace_algorithm import create_registered_workspace_algorithm
from core.workspace_historical_trade_diagnostics import (
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_signal import WorkspaceSignalFilterContext

TEST_ID = "T105-21"
MODE = "RM105_T105_21_DONCHIAN_REJECTED_SURVIVORS_ANATOMY_TEST_ONLY"
EXPECTED_SURVIVORS = {"2025": 42, "2026": 18}
EXPECTED_REJECTED = {"2025": 22, "2026": 11}
CLOSE_REASONS = ("PROFIT_DRAWDOWN", "STOP_LOSS", "TAKE_PROFIT", "SESSION_END")
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)


class RejectedSurvivorAnatomyRuntime(
    StochasticAnatomyRuntime,
    DonchianAnatomyRuntime,
):
    """Об'єднати сумісні nominal contracts test-only anatomy helpers."""


def _donchian_allows(
    direction: str,
    close: float,
    upper: float,
    lower: float,
) -> bool:
    """Повторити точний TEST_ONLY directional breakout contract T105-20."""
    if direction == "BUY":
        return close > upper
    if direction == "SELL":
        return close < lower
    raise AssertionError(direction)


@dataclass(frozen=True, slots=True)
class RejectedSurvivorRow:
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    signal_close: float
    upper20: float
    lower20: float
    channel_width: float
    favorable_distance: float
    adverse_distance: float
    favorable_fraction: float
    adverse_fraction: float
    percent_k: float
    percent_d: float
    signed_kd: float
    regime: str
    line_order: str
    normalized_opening: float
    opening_delta: float
    normalized_slope: float

    @property
    def favorable_distance_pips(self) -> float:
        return self.favorable_distance / PIP_SIZE

    @property
    def channel_width_pips(self) -> float:
        return self.channel_width / PIP_SIZE


def _alligator_anatomy(
    context: WorkspaceSignalFilterContext,
    signal_timestamp,
) -> tuple[str, str, float, float, float]:
    assert context.observation_timestamp is not None
    assert context.available_at is not None
    assert context.observation_timestamp <= signal_timestamp
    assert context.available_at <= signal_timestamp
    observations = context.diagnostic_observations
    assert observations
    assert all(item.available_at <= signal_timestamp for item in observations)
    current = observations[-1]
    oldest = observations[0]
    assert current.normalized_opening is not None
    assert oldest.normalized_opening is not None
    assert context.normalized_slope is not None
    return (
        str(context.regime),
        current.state,
        float(current.normalized_opening),
        float(current.normalized_opening - oldest.normalized_opening),
        float(context.normalized_slope),
    )


def _rejected_rows(
    runtime: RejectedSurvivorAnatomyRuntime,
) -> tuple[RejectedSurvivorRow, ...]:
    donchian = {row.trade.signal_uid: row for row in _build_donchian_rows(runtime)}
    stochastic = {row.trade.signal_uid: row for row in _build_stochastic_rows(runtime)}
    records = {
        record.signal_uid: record
        for record in runtime.historical_signal_records
        if record.accepted
    }
    assert donchian.keys() == stochastic.keys() == records.keys()

    rejected: list[RejectedSurvivorRow] = []
    for signal_uid, stochastic_row in stochastic.items():
        donchian_row: DonchianEntryRow = donchian[signal_uid]
        trade = stochastic_row.trade
        signal_event = runtime.strategy_events[trade.signal_timestamp]
        close = float(signal_event.close)
        if _donchian_allows(
            trade.direction,
            close,
            donchian_row.upper,
            donchian_row.lower,
        ):
            continue

        width = donchian_row.upper - donchian_row.lower
        assert width > 0.0
        if trade.direction == "BUY":
            favorable = donchian_row.upper - close
            adverse = close - donchian_row.lower
        else:
            favorable = close - donchian_row.lower
            adverse = donchian_row.upper - close
        assert favorable >= 0.0
        context = records[signal_uid].filter_context
        assert context is not None
        regime, line_order, opening, opening_delta, slope = _alligator_anatomy(
            context,
            trade.signal_timestamp,
        )
        assert stochastic_row.bars_since_cross != 0
        rejected.append(
            RejectedSurvivorRow(
                trade=trade,
                outcome=stochastic_row.outcome,
                signal_close=close,
                upper20=donchian_row.upper,
                lower20=donchian_row.lower,
                channel_width=width,
                favorable_distance=favorable,
                adverse_distance=adverse,
                favorable_fraction=favorable / width,
                adverse_fraction=adverse / width,
                percent_k=stochastic_row.percent_k,
                percent_d=stochastic_row.percent_d,
                signed_kd=stochastic_row.k_minus_d,
                regime=regime,
                line_order=line_order,
                normalized_opening=opening,
                opening_delta=opening_delta,
                normalized_slope=slope,
            )
        )
    return tuple(rejected)


def _pf(rows: tuple[RejectedSurvivorRow, ...]) -> str:
    gross_profit = math.fsum(max(row.trade.final_profit, 0.0) for row in rows)
    gross_loss = -math.fsum(min(row.trade.final_profit, 0.0) for row in rows)
    return "NONE" if gross_loss == 0.0 else f"{gross_profit / gross_loss:.4f}"


def _median(rows: tuple[RejectedSurvivorRow, ...], attribute: str) -> str:
    if not rows:
        return "NONE"
    return f"{statistics.median(getattr(row, attribute) for row in rows):.4f}"


def _outcome_line(outcome: str, rows: tuple[RejectedSurvivorRow, ...]) -> str:
    group = tuple(row for row in rows if row.outcome == outcome)
    median_abs_kd = (
        "NONE"
        if not group
        else f"{statistics.median(abs(row.signed_kd) for row in group):.4f}"
    )
    return (
        f"      {outcome}=trades:{len(group)},"
        f"median_favorable_distance_pips:{_median(group, 'favorable_distance_pips')},"
        f"median_favorable_distance_fraction:{_median(group, 'favorable_fraction')},"
        f"median_adverse_distance_fraction:{_median(group, 'adverse_fraction')},"
        f"median_channel_width_pips:{_median(group, 'channel_width_pips')},"
        f"median_abs_KD:{median_abs_kd}"
    )


def _bin_name(value: float) -> str:
    if value <= 0.05:
        return "A_LE_0.05"
    if value <= 0.10:
        return "B_0.05_TO_0.10"
    if value <= 0.25:
        return "C_0.10_TO_0.25"
    if value <= 0.50:
        return "D_0.25_TO_0.50"
    return "E_GT_0.50"


def _group_counts(name: str, rows: tuple[RejectedSurvivorRow, ...]) -> str:
    counts = Counter(row.outcome for row in rows)
    return (
        f"      {name}=trades:{len(rows)},W:{counts[OUTCOME_WIN]},"
        f"L:{counts[OUTCOME_LOSS]},BE:{counts[OUTCOME_BREAK_EVEN]},"
        f"net:{math.fsum(row.trade.final_profit for row in rows):+.2f}"
    )


def _print_period(spec: PeriodSpec) -> None:
    broker_probe = BrokerRequestProbe()
    runtime = RejectedSurvivorAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=broker_probe,
    )
    _assert_policy(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_metrics(spec, runtime)
    stochastic_rejects = _assert_stochastic_path(spec, runtime)
    _assert_geometry(runtime)
    rows = _rejected_rows(runtime)
    assert runtime.historical_summary is not None
    assert runtime.historical_summary.opened_trades == EXPECTED_SURVIVORS[spec.code]
    assert len(rows) == EXPECTED_REJECTED[spec.code]
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    assert session.completed and all(
        event.timeframe == "M15" for event in session.events
    )

    counts = Counter(row.outcome for row in rows)
    reasons = Counter(row.trade.close_reason for row in rows)
    assert set(reasons).issubset(CLOSE_REASONS)
    print(f"  period={spec.code}")
    print(
        "    population="
        f"production_survivors:{EXPECTED_SURVIVORS[spec.code]},"
        f"stochastic_rejects:{stochastic_rejects},donchian_rejected:{len(rows)}"
    )
    print(
        "    REJECTED_TOTAL="
        f"trades:{len(rows)},wins:{counts[OUTCOME_WIN]},"
        f"losses:{counts[OUTCOME_LOSS]},break_even:{counts[OUTCOME_BREAK_EVEN]},"
        f"net:{math.fsum(row.trade.final_profit for row in rows):+.2f},pf:{_pf(rows)},"
        + ",".join(f"{reason}:{reasons[reason]}" for reason in CLOSE_REASONS)
    )
    print("    WIN_VS_LOSS")
    print(_outcome_line(OUTCOME_WIN, rows))
    print(_outcome_line(OUTCOME_LOSS, rows))
    print("    DISTANCE_BINS")
    for name in (
        "A_LE_0.05",
        "B_0.05_TO_0.10",
        "C_0.10_TO_0.25",
        "D_0.25_TO_0.50",
        "E_GT_0.50",
    ):
        group = tuple(row for row in rows if _bin_name(row.favorable_fraction) == name)
        print(_group_counts(name, group))
    print("    DIRECTION")
    for direction in ("BUY", "SELL"):
        print(
            _group_counts(
                direction,
                tuple(row for row in rows if row.trade.direction == direction),
            )
        )

    if spec.code == "2026":
        print("    REJECTED_TRADES_2026")
        print(
            "      timestamp|side|close_reason|pnl|favorable_distance_pips|"
            "favorable_distance_fraction|channel_width_pips|K|D|abs_KD"
        )
        for row in rows:
            print(
                f"      {row.trade.signal_timestamp.isoformat()}|{row.trade.direction}|"
                f"{row.trade.close_reason}|{row.trade.final_profit:+.2f}|"
                f"{row.favorable_distance_pips:.2f}|{row.favorable_fraction:.4f}|"
                f"{row.channel_width_pips:.2f}|{row.percent_k:.4f}|"
                f"{row.percent_d:.4f}|{abs(row.signed_kd):.4f}"
            )


def main() -> None:
    production_before = _production_hashes()
    assert DONCHIAN_PERIOD == 20 and DONCHIAN_SHIFT == 0
    print("T105-21 Donchian Rejected Survivors Anatomy")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  population=PRODUCTION_STOCHASTIC_SURVIVORS__DONCHIAN_N20_REJECT")
    print("  outcome_usage=LABEL_ONLY")
    print("  factual_R=OMITTED_NO_EXISTING_HELPER")
    print(
        "  alligator_anatomy=direction,regime,line_order,normalized_opening,"
        "opening_delta,normalized_slope"
    )
    print("  alligator_center_slope=OMITTED_NO_STRUCTURED_HELPER")
    for spec in PERIODS:
        _print_period(spec)

    assert _production_hashes() == production_before
    print("  stochastic_current_bar_cross=False")
    print("  donchian_previous_completed_M15_only=True")
    print("  donchian_current_signal_bar_excluded=True")
    print("  entry_features_future_bars_used=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  production_stochastic_gate_active=True")
    print("  donchian_gate_test_only=True")
    print("  donchian_production_gate=False")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  filter_rule_created=False")
    print("T105_21_DONCHIAN_REJECTED_ANATOMY=OK")


if __name__ == "__main__":
    main()
