# -*- coding: utf-8 -*-
"""T105-11: TEST_ONLY Donchian Entry Anatomy для Candidate F.

Runner виконує actual WorkspaceRuntime Replay з production PD=35% окремо
для 2025 і 2026. Для кожної фактично відкритої угоди він зіставляє signal
bar з canonical Donchian Period=20, Shift=0. Межі каналу обчислюються лише
за попередніми 20 завершеними M15 bars; current signal bar виключений.

Period=20 є reference для дослідження, а не універсальною константою.
Runner не фільтрує входи, не змінює production і не приймає production-рішень.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_10_pd_35_production_regression_check import (  # noqa: E402
    PERIODS,
    PRODUCTION_PD_THRESHOLD,
    PeriodSpec,
    _workspace,
)

from core.workspace_algorithm import create_registered_workspace_algorithm  # noqa: E402
from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_profit_guard import (  # noqa: E402
    CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX,
    CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1,
    WorkspaceCandidateFNegativePdRecoveryGuard,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT,
)

TEST_ID = "T105-11"
DONCHIAN_PERIOD = 20
DONCHIAN_SHIFT = 0
PIP_SIZE = 0.0001
EPSILON = 1e-12

STATE_INSIDE = "INSIDE"
STATE_UPPER_BREAKOUT = "UPPER_BREAKOUT"
STATE_LOWER_BREAKOUT = "LOWER_BREAKOUT"
STATES = (STATE_INSIDE, STATE_UPPER_BREAKOUT, STATE_LOWER_BREAKOUT)

OUTCOME_WIN = "WIN"
OUTCOME_LOSS = "LOSS"
OUTCOME_BREAK_EVEN = "BE"
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)


@dataclass(frozen=True, slots=True)
class DonchianEntryRow:
    """Causal Donchian snapshot одного фактичного Candidate F entry signal."""

    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    state: str
    upper: float
    lower: float
    midline: float
    channel_width_pips: float
    channel_position: float
    distance_to_upper_pips: float
    distance_to_lower_pips: float
    distance_to_midline_pips: float
    reference_start: datetime
    reference_end: datetime


class DonchianAnatomyRuntime(WorkspaceRuntime):
    """Production runtime з вузьким TEST_ONLY доступом до завершених M15 bars."""

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
        """Повернути повну історію сигналів завершеного Replay."""
        return tuple(self._historical_signal_records)


def _production_hashes() -> dict[str, str]:
    """Зафіксувати production-файли до та після TEST_ONLY Replay."""
    roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "engine")
    paths = sorted(path for root in roots for path in root.rglob("*.py"))
    strings = PROJECT_ROOT / "lang" / "strings.json"
    if strings.is_file():
        paths.append(strings)
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def _outcome(trade: WorkspaceHistoricalTradeDiagnostic) -> str:
    if trade.final_profit > EPSILON:
        return OUTCOME_WIN
    if trade.final_profit < -EPSILON:
        return OUTCOME_LOSS
    return OUTCOME_BREAK_EVEN


def _state(close: float, upper: float, lower: float) -> str:
    if close > upper + EPSILON:
        return STATE_UPPER_BREAKOUT
    if close < lower - EPSILON:
        return STATE_LOWER_BREAKOUT
    return STATE_INSIDE


def _build_rows(
    runtime: DonchianAnatomyRuntime,
) -> tuple[DonchianEntryRow, ...]:
    """Зіставити actual entries лише з попередніми completed M15 bars."""
    execution = runtime.replay_execution
    assert execution is not None

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_indexes = {event.timestamp: index for index, event in enumerate(events)}
    assert len(event_indexes) == len(events)

    records = {
        record.signal_uid: record
        for record in runtime.historical_signal_records
        if record.accepted
    }

    rows: list[DonchianEntryRow] = []
    for trade in execution.trade_diagnostics():
        record = records.get(trade.signal_uid)
        assert record is not None, trade.signal_uid
        assert record.timestamp == trade.signal_timestamp

        index = event_indexes.get(trade.signal_timestamp)
        assert index is not None, trade.signal_timestamp
        assert index >= DONCHIAN_PERIOD
        signal_event = events[index]
        reference = events[index - DONCHIAN_PERIOD : index]  # noqa

        assert len(reference) == DONCHIAN_PERIOD
        assert signal_event.timestamp == trade.signal_timestamp
        assert all(item.timeframe == "M15" for item in reference)
        assert all(item.timestamp < signal_event.timestamp for item in reference)
        assert signal_event not in reference

        upper = max(float(item.high) for item in reference)
        lower = min(float(item.low) for item in reference)
        width = upper - lower
        assert width > EPSILON
        midline = (upper + lower) / 2.0
        close = float(signal_event.close)

        rows.append(
            DonchianEntryRow(
                trade=trade,
                outcome=_outcome(trade),
                state=_state(close, upper, lower),
                upper=upper,
                lower=lower,
                midline=midline,
                channel_width_pips=width / PIP_SIZE,
                channel_position=(close - lower) / width,
                distance_to_upper_pips=(upper - close) / PIP_SIZE,
                distance_to_lower_pips=(close - lower) / PIP_SIZE,
                distance_to_midline_pips=(close - midline) / PIP_SIZE,
                reference_start=reference[0].timestamp,
                reference_end=reference[-1].timestamp,
            )
        )

    assert len(rows) == len(execution.trade_diagnostics())
    return tuple(rows)


def _assert_baseline(spec: PeriodSpec, runtime: DonchianAnatomyRuntime) -> None:
    """Звірити production PD=35% baseline без послаблення метрик."""
    summary = runtime.historical_summary
    assert summary is not None
    assert summary.opened_trades == spec.trades
    assert summary.winning_trades == spec.wins
    assert summary.losing_trades == spec.losses
    assert summary.break_even_trades == spec.break_even
    assert math.isclose(summary.net_profit, spec.net, rel_tol=0.0, abs_tol=0.005)
    assert math.isclose(
        summary.profit_factor,
        spec.profit_factor,
        rel_tol=0.0,
        abs_tol=0.00005,
    )
    assert math.isclose(
        summary.maximum_drawdown,
        spec.drawdown,
        rel_tol=0.0,
        abs_tol=0.005,
    )
    assert summary.close_reason_count("PROFIT_DRAWDOWN") == spec.profit_drawdown_closes
    assert summary.close_reason_count("STOP_LOSS") == spec.stop_loss_closes
    assert summary.close_reason_count("TAKE_PROFIT") == spec.take_profit_closes
    assert summary.close_reason_count("SESSION_END") == 0


def _median(rows: tuple[DonchianEntryRow, ...], attribute: str) -> float:
    assert rows
    return float(statistics.median(getattr(row, attribute) for row in rows))


def _group_line(name: str, rows: tuple[DonchianEntryRow, ...]) -> str:
    """Одна anatomy-група однаковими метриками без selection rule."""
    if not rows:
        return f"    {name}=n:0,pnl:+0.00"
    return (
        f"    {name}=n:{len(rows)},"
        f"pnl:{math.fsum(row.trade.final_profit for row in rows):+.2f},"
        f"avg_pnl:{statistics.fmean(row.trade.final_profit for row in rows):+.3f},"
        f"position_med:{_median(rows, 'channel_position'):.3f},"
        f"width_med:{_median(rows, 'channel_width_pips'):.2f}pip,"
        f"upper_dist_med:{_median(rows, 'distance_to_upper_pips'):+.2f}pip,"
        f"lower_dist_med:{_median(rows, 'distance_to_lower_pips'):+.2f}pip,"
        f"mid_dist_med:{_median(rows, 'distance_to_midline_pips'):+.2f}pip"
    )


def _print_entry(index: int, row: DonchianEntryRow) -> None:
    trade = row.trade
    print(
        f"    entry={index:02d},signal:{trade.signal_timestamp.isoformat()},"
        f"entry_utc:{trade.entry_timestamp.isoformat()},direction:{trade.direction},"
        f"outcome:{row.outcome},pnl:{trade.final_profit:+.2f},state:{row.state},"
        f"position:{row.channel_position:.4f},width:{row.channel_width_pips:.2f}pip,"
        f"d_upper:{row.distance_to_upper_pips:+.2f}pip,"
        f"d_lower:{row.distance_to_lower_pips:+.2f}pip,"
        f"d_mid:{row.distance_to_midline_pips:+.2f}pip,"
        f"reference:{row.reference_start.isoformat()}..{row.reference_end.isoformat()}"
    )


def _run_period(spec: PeriodSpec) -> tuple[DonchianEntryRow, ...]:
    """Виконати один незалежний actual Candidate F WorkspaceRuntime Replay."""
    runtime = DonchianAnatomyRuntime(
        _workspace(spec),
        algorithm_factory=create_registered_workspace_algorithm,
    )
    assert isinstance(
        runtime.profit_drawdown_guard,
        WorkspaceCandidateFNegativePdRecoveryGuard,
    )
    assert DEFAULT_WORKSPACE_PROFIT_DRAWDOWN_CLOSE_PERCENT == 35.0
    assert PRODUCTION_PD_THRESHOLD == 35.0
    assert CANDIDATE_F_NEGATIVE_PD_RECOVERY_WINDOW_M1 == 3
    assert CANDIDATE_F_NEGATIVE_PD_EARLY_ABORT_EVENT_INDEX == 2
    assert math.isclose(
        runtime.profit_protection_policy.max_drawdown_percent,
        PRODUCTION_PD_THRESHOLD,
        rel_tol=0.0,
        abs_tol=EPSILON,
    )

    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    _assert_baseline(spec, runtime)
    rows = _build_rows(runtime)
    summary = runtime.historical_summary
    assert summary is not None

    outcome_counts = Counter(row.outcome for row in rows)
    assert outcome_counts[OUTCOME_WIN] == spec.wins
    assert outcome_counts[OUTCOME_LOSS] == spec.losses
    assert outcome_counts[OUTCOME_BREAK_EVEN] == spec.break_even
    assert len(rows) == spec.trades
    assert math.isclose(
        math.fsum(row.trade.final_profit for row in rows),
        summary.net_profit,
        rel_tol=0.0,
        abs_tol=0.005,
    )

    broker_execution_attempted = any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )
    assert not broker_execution_attempted

    print(
        f"  period={spec.code} baseline="
        f"trades:{summary.opened_trades},wins:{summary.winning_trades},"
        f"losses:{summary.losing_trades},break_even:{summary.break_even_trades},"
        f"net:{summary.net_profit:+.2f},pf:{summary.profit_factor:.4f},"
        f"dd:{summary.maximum_drawdown:.2f}"
    )
    print("  factual_entries")
    for index, row in enumerate(rows, start=1):
        _print_entry(index, row)

    print("  outcome_groups")
    for outcome in OUTCOMES:
        group = tuple(row for row in rows if row.outcome == outcome)
        print(_group_line(outcome, group))

    print("  state_groups")
    for state in STATES:
        group = tuple(row for row in rows if row.state == state)
        print(_group_line(state, group))

    print("  outcome_x_state_groups")
    for outcome in OUTCOMES:
        for state in STATES:
            group = tuple(
                row for row in rows if row.outcome == outcome and row.state == state
            )
            print(_group_line(f"{outcome}_{state}", group))
    return rows


def main() -> None:
    """Запустити T105-11 без entry filter та production-рішення."""
    production_before = _production_hashes()

    print("T105-11 Candidate F Donchian Entry Anatomy result")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  production_profit_drawdown_threshold=35.0")
    print("  donchian_period=20_reference_not_universal_constant")
    print("  donchian_shift=0")
    print("  reference_bars=previous_20_completed_M15")
    print("  current_signal_bar_excluded=True")
    print("  entry_filter_created=False")

    all_rows = tuple(_run_period(spec) for spec in PERIODS)
    assert tuple(len(rows) for rows in all_rows) == tuple(
        spec.trades for spec in PERIODS
    )
    assert _production_hashes() == production_before

    print("  production_files_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_11_DONCHIAN_ENTRY_ANATOMY=OK")


if __name__ == "__main__":
    main()
