# -*- coding: utf-8 -*-
"""T105-15: TEST_ONLY Stochastic Entry Anatomy для Candidate F.

Runner виконує actual WorkspaceRuntime Replay з production PD=35% окремо
для 2025 і 2026. Для кожного фактичного Candidate F entry він фіксує
Stochastic на causal signal bar, сформованому тільки з completed M15 bars.

Використано наявний у проєкті canonical/reference profile 14/1/3:
raw %K за High/Low/Close 14 bars, smoothing %K=1, %D=SMA(%K, 3).
Рівні 20/80 і freshness-групи є лише anatomy labels. Runner не створює
threshold/filter, не використовує Donchian gate і не змінює production.
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

TEST_ID = "T105-15"
K_LENGTH = 14
K_SMOOTHING = 1
D_LENGTH = 3
OVERSOLD_LEVEL = 20.0
OVERBOUGHT_LEVEL = 80.0
MIDLINE = 50.0
EPSILON = 1e-12

OUTCOME_WIN = "WIN"
OUTCOME_LOSS = "LOSS"
OUTCOME_BREAK_EVEN = "BE"
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)

ZONE_OVERSOLD = "OVERSOLD"
ZONE_NEUTRAL = "NEUTRAL"
ZONE_OVERBOUGHT = "OVERBOUGHT"
ZONES = (ZONE_OVERSOLD, ZONE_NEUTRAL, ZONE_OVERBOUGHT)

CROSS_UP = "UP"
CROSS_DOWN = "DOWN"
CROSS_NONE = "NONE"


@dataclass(frozen=True, slots=True)
class StochasticEntryRow:
    """Causal Stochastic snapshot одного фактичного Candidate F entry."""

    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    percent_k: float
    percent_d: float
    k_minus_d: float
    last_cross_direction: str
    bars_since_cross: int | None
    slope_k: float
    slope_d: float
    zone: str
    distance_to_50: float
    signed_k_minus_50: float
    kd_state: str
    cross_alignment: str
    cross_freshness: str
    slope_state: str
    reference_start: datetime


class StochasticAnatomyRuntime(WorkspaceRuntime):
    """Production runtime з TEST_ONLY доступом до completed M15 history."""

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


def _canonical_stochastic(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[tuple[float | None, ...], tuple[float | None, ...]]:
    """Обчислити causal canonical %K(14,1) та %D SMA(3)."""
    percent_k: list[float | None] = [None] * len(events)
    for index in range(K_LENGTH - 1, len(events)):
        window = events[index - K_LENGTH + 1 : index + 1]
        highest = max(float(event.high) for event in window)
        lowest = min(float(event.low) for event in window)
        width = highest - lowest
        if width <= EPSILON:
            percent_k[index] = MIDLINE
        else:
            close = float(events[index].close)
            percent_k[index] = 100.0 * (close - lowest) / width

    percent_d: list[float | None] = [None] * len(events)
    first_d_index = K_LENGTH + D_LENGTH - 2
    for index in range(first_d_index, len(events)):
        window = percent_k[index - D_LENGTH + 1 : index + 1]
        if all(value is not None for value in window):
            percent_d[index] = statistics.fmean(float(value) for value in window)
    return tuple(percent_k), tuple(percent_d)


def _cross_direction(
    previous_k: float,
    previous_d: float,
    current_k: float,
    current_d: float,
) -> str | None:
    if previous_k <= previous_d + EPSILON and current_k > current_d + EPSILON:
        return CROSS_UP
    if previous_k >= previous_d - EPSILON and current_k < current_d - EPSILON:
        return CROSS_DOWN
    return None


def _last_cross(
    index: int,
    percent_k: tuple[float | None, ...],
    percent_d: tuple[float | None, ...],
) -> tuple[str, int | None]:
    """Знайти останній K/D cross не пізніше causal signal bar."""
    for cross_index in range(index, 0, -1):
        current_k = percent_k[cross_index]
        current_d = percent_d[cross_index]
        previous_k = percent_k[cross_index - 1]
        previous_d = percent_d[cross_index - 1]
        if None in (current_k, current_d, previous_k, previous_d):
            continue
        direction = _cross_direction(
            float(previous_k),
            float(previous_d),
            float(current_k),
            float(current_d),
        )
        if direction is not None:
            return direction, index - cross_index
    return CROSS_NONE, None


def _zone(percent_k: float) -> str:
    if percent_k < OVERSOLD_LEVEL:
        return ZONE_OVERSOLD
    if percent_k > OVERBOUGHT_LEVEL:
        return ZONE_OVERBOUGHT
    return ZONE_NEUTRAL


def _kd_state(percent_k: float, percent_d: float) -> str:
    if percent_k > percent_d + EPSILON:
        return "K_ABOVE_D"
    if percent_k < percent_d - EPSILON:
        return "K_BELOW_D"
    return "K_EQUALS_D"


def _cross_alignment(direction: str, cross_direction: str) -> str:
    expected = CROSS_UP if direction == "BUY" else CROSS_DOWN
    if cross_direction == CROSS_NONE:
        return "UNAVAILABLE"
    return "ALIGNED" if cross_direction == expected else "OPPOSED"


def _cross_freshness(bars_since_cross: int | None) -> str:
    """Описова група свіжості; її межі не є entry threshold."""
    if bars_since_cross is None:
        return "UNAVAILABLE"
    if bars_since_cross == 0:
        return "CURRENT_BAR"
    if bars_since_cross <= 2:
        return "ONE_TO_TWO_BARS"
    return "THREE_PLUS_BARS"


def _slope_state(direction: str, slope_k: float, slope_d: float) -> str:
    multiplier = 1.0 if direction == "BUY" else -1.0
    directional_k = multiplier * slope_k
    directional_d = multiplier * slope_d
    k_favorable = directional_k > EPSILON
    d_favorable = directional_d > EPSILON
    k_opposed = directional_k < -EPSILON
    d_opposed = directional_d < -EPSILON
    if k_favorable and d_favorable:
        return "BOTH_ALIGNED"
    if k_opposed and d_opposed:
        return "BOTH_OPPOSED"
    if not (k_favorable or d_favorable or k_opposed or d_opposed):
        return "BOTH_FLAT"
    return "MIXED"


def _build_rows(
    runtime: StochasticAnatomyRuntime,
) -> tuple[StochasticEntryRow, ...]:
    """Зіставити factual entries зі Stochastic на completed signal bars."""
    execution = runtime.replay_execution
    assert execution is not None

    events = tuple(
        runtime.strategy_events[timestamp]
        for timestamp in sorted(runtime.strategy_events)
    )
    event_indexes = {event.timestamp: index for index, event in enumerate(events)}
    assert len(event_indexes) == len(events)
    assert all(event.timeframe == "M15" for event in events)

    records = {
        record.signal_uid: record
        for record in runtime.historical_signal_records
        if record.accepted
    }
    percent_k, percent_d = _canonical_stochastic(events)

    rows: list[StochasticEntryRow] = []
    minimum_index = K_LENGTH + D_LENGTH - 1
    for trade in execution.trade_diagnostics():
        record = records.get(trade.signal_uid)
        assert record is not None, trade.signal_uid
        assert record.timestamp == trade.signal_timestamp

        index = event_indexes.get(trade.signal_timestamp)
        assert index is not None, trade.signal_timestamp
        assert index >= minimum_index
        signal_event = events[index]
        assert signal_event.timestamp == trade.signal_timestamp

        current_k = percent_k[index]
        current_d = percent_d[index]
        previous_k = percent_k[index - 1]
        previous_d = percent_d[index - 1]
        assert None not in (current_k, current_d, previous_k, previous_d)
        k = float(current_k)
        d = float(current_d)
        slope_k = k - float(previous_k)
        slope_d = d - float(previous_d)
        cross_direction, bars_since_cross = _last_cross(index, percent_k, percent_d)
        reference_start = events[index - K_LENGTH + 1].timestamp
        assert reference_start <= signal_event.timestamp
        assert all(
            event.timestamp <= signal_event.timestamp
            for event in events[index - K_LENGTH + 1 : index + 1]
        )

        rows.append(
            StochasticEntryRow(
                trade=trade,
                outcome=_outcome(trade),
                percent_k=k,
                percent_d=d,
                k_minus_d=k - d,
                last_cross_direction=cross_direction,
                bars_since_cross=bars_since_cross,
                slope_k=slope_k,
                slope_d=slope_d,
                zone=_zone(k),
                distance_to_50=abs(k - MIDLINE),
                signed_k_minus_50=k - MIDLINE,
                kd_state=_kd_state(k, d),
                cross_alignment=_cross_alignment(str(trade.direction), cross_direction),
                cross_freshness=_cross_freshness(bars_since_cross),
                slope_state=_slope_state(str(trade.direction), slope_k, slope_d),
                reference_start=reference_start,
            )
        )

    assert len(rows) == len(execution.trade_diagnostics())
    return tuple(rows)


def _assert_baseline(spec: PeriodSpec, runtime: StochasticAnatomyRuntime) -> None:
    """Звірити production PD=35% baseline однаковими метриками."""
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


def _counter_text(values: list[str]) -> str:
    counts = Counter(values)
    return "|".join(f"{key}:{counts[key]}" for key in sorted(counts)) or "NONE"


def _median(rows: tuple[StochasticEntryRow, ...], attribute: str) -> float:
    assert rows
    return float(statistics.median(getattr(row, attribute) for row in rows))


def _group_line(name: str, rows: tuple[StochasticEntryRow, ...]) -> str:
    """Надрукувати anatomy-групу без перетворення її на selection rule."""
    if not rows:
        return f"    {name}=n:0,pnl:+0.00"
    cross_ages = [
        row.bars_since_cross for row in rows if row.bars_since_cross is not None
    ]
    cross_age_median = (
        "NONE" if not cross_ages else f"{statistics.median(cross_ages):.1f}"
    )
    return (
        f"    {name}=n:{len(rows)},"
        f"pnl:{math.fsum(row.trade.final_profit for row in rows):+.2f},"
        f"outcomes:{_counter_text([row.outcome for row in rows])},"
        f"K_med:{_median(rows, 'percent_k'):.3f},"
        f"D_med:{_median(rows, 'percent_d'):.3f},"
        f"K_minus_D_med:{_median(rows, 'k_minus_d'):+.3f},"
        f"slope_K_med:{_median(rows, 'slope_k'):+.3f},"
        f"slope_D_med:{_median(rows, 'slope_d'):+.3f},"
        f"distance_50_med:{_median(rows, 'distance_to_50'):.3f},"
        f"cross_age_med:{cross_age_median},"
        f"crosses:{_counter_text([row.last_cross_direction for row in rows])},"
        f"zones:{_counter_text([row.zone for row in rows])}"
    )


def _print_entry(index: int, row: StochasticEntryRow) -> None:
    trade = row.trade
    cross_age = "NONE" if row.bars_since_cross is None else str(row.bars_since_cross)
    print(
        f"    entry={index:02d},signal:{trade.signal_timestamp.isoformat()},"
        f"direction:{trade.direction},outcome:{row.outcome},"
        f"pnl:{trade.final_profit:+.2f},close_reason:{trade.close_reason},"
        f"K:{row.percent_k:.4f},D:{row.percent_d:.4f},"
        f"K_minus_D:{row.k_minus_d:+.4f},"
        f"last_cross:{row.last_cross_direction},bars_since_cross:{cross_age},"
        f"slope_K:{row.slope_k:+.4f},slope_D:{row.slope_d:+.4f},"
        f"zone:{row.zone},distance_to_50:{row.distance_to_50:.4f},"
        f"signed_K_minus_50:{row.signed_k_minus_50:+.4f},"
        f"reference_start:{row.reference_start.isoformat()}"
    )


def _print_state_groups(
    rows: tuple[StochasticEntryRow, ...],
    attribute: str,
    values: tuple[str, ...],
) -> None:
    print(f"  {attribute}_groups")
    for value in values:
        group = tuple(row for row in rows if getattr(row, attribute) == value)
        print(_group_line(value, group))


def _run_period(spec: PeriodSpec) -> tuple[StochasticEntryRow, ...]:
    """Виконати один незалежний actual Candidate F WorkspaceRuntime Replay."""
    runtime = StochasticAnatomyRuntime(
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
        f"dd:{summary.maximum_drawdown:.2f},"
        f"PD:{summary.close_reason_count('PROFIT_DRAWDOWN')},"
        f"SL:{summary.close_reason_count('STOP_LOSS')},"
        f"TP:{summary.close_reason_count('TAKE_PROFIT')},"
        f"SESSION:{summary.close_reason_count('SESSION_END')}"
    )
    print("  factual_entries")
    for index, row in enumerate(rows, start=1):
        _print_entry(index, row)

    print("  outcome_groups")
    for outcome in OUTCOMES:
        group = tuple(row for row in rows if row.outcome == outcome)
        print(_group_line(outcome, group))

    _print_state_groups(rows, "zone", ZONES)
    _print_state_groups(
        rows,
        "kd_state",
        ("K_ABOVE_D", "K_BELOW_D", "K_EQUALS_D"),
    )
    _print_state_groups(
        rows,
        "cross_alignment",
        ("ALIGNED", "OPPOSED", "UNAVAILABLE"),
    )
    _print_state_groups(
        rows,
        "cross_freshness",
        ("CURRENT_BAR", "ONE_TO_TWO_BARS", "THREE_PLUS_BARS", "UNAVAILABLE"),
    )
    _print_state_groups(
        rows,
        "slope_state",
        ("BOTH_ALIGNED", "BOTH_OPPOSED", "MIXED", "BOTH_FLAT"),
    )
    return rows


def main() -> None:
    """Запустити T105-15 без threshold, filter та production-рішення."""
    production_before = _production_hashes()

    print("T105-15 Candidate F Stochastic Entry Anatomy result")
    print(f"  test_id={TEST_ID}")
    print("  mode=TEST_ONLY_ACTUAL_CANDIDATE_F_WORKSPACE_RUNTIME")
    print("  production_profit_drawdown_threshold=35.0")
    print("  stochastic_profile=CANONICAL_REFERENCE_14_1_3")
    print("  stochastic_percent_k=HLC_14_SMOOTHING_1")
    print("  stochastic_percent_d=SMA_PERCENT_K_3")
    print("  stochastic_profile_is_universal_constant=False")
    print("  signal_bar=CAUSAL_COMPLETED_M15")
    print("  stochastic_reference_includes_completed_signal_bar=True")
    print("  zone_source=PERCENT_K")
    print("  zone_levels=20_80_ANATOMY_ONLY")
    print("  cross_freshness_groups=ANATOMY_ONLY")
    print("  threshold_created=False")
    print("  entry_filter_created=False")
    print("  donchian_gate_used=False")

    all_rows = tuple(_run_period(spec) for spec in PERIODS)
    assert tuple(len(rows) for rows in all_rows) == tuple(
        spec.trades for spec in PERIODS
    )
    assert _production_hashes() == production_before

    print("  factual_entry_count_check=2025:59,2026:29")
    print("  production_hashes_unchanged=True")
    print("  production_files_changed=False")
    print("  production_entry_logic_changed=False")
    print("  production_exit_logic_changed=False")
    print("  production_decision_made=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("T105_15_STOCHASTIC_ENTRY_ANATOMY=OK")


if __name__ == "__main__":
    main()
