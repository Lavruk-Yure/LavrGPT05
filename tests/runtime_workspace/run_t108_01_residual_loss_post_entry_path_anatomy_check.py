"""run_t108_01_residual_loss_post_entry_path_anatomy_check.py — T108-01.

TEST_ONLY runner запускає незмінений registered current-production Candidate F
Replay окремо для 2025 і 2026 через канонічний T105-18 harness. Для кожної
factual trade він поєднує immutable execution diagnostic з completed M1 bars
від фактичного entry до фактичного close та відновлює MFE/MAE у risk units,
час їх досягнення і тривалість позиції. LOSS є основною population, а WIN і
BREAK_EVEN отримують ті самі метрики як reference population.

Захисний close-bar обробляється за factual close price без припущення про
недоступний intrabar порядок; для PROFIT_DRAWDOWN враховується completed bar і
фактична close point. Post-entry bars є лише outcome anatomy: вони не формують
entry feature, не змінюють signal, close або production execution. У core немає
канонічного local support/resistance API, тому runner явно повертає
NOT_CANONICALLY_AVAILABLE і не вигадує новий S/R algorithm.

Пороги 0.25R, 0.50R і 1.00R є лише наперед заданими descriptive bins без
sweep чи optimization. Runner перевіряє задані baseline totals, збіг excursions
з execution engine, completed-bar chronology, production hashes, відсутність
broker requests/execution та незмінність Candidate F, MD7 і локалізації.
"""

from __future__ import annotations

import math
import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_15_stochastic_entry_anatomy_check import (  # noqa: E402
    _production_hashes,
)
from run_t105_18_stochastic_current_bar_production_regression_check import (  # noqa: E402, E501
    EXPECTATIONS,
    PERIODS,
    _broker_execution_attempted,
    _run_period,
)

from core.workspace_historical_trade_diagnostics import (  # noqa: E402
    WorkspaceHistoricalTradeDiagnostic,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

TEST_ID = "T108-01"
MODE = "RM108_T108_01_RESIDUAL_LOSS_POST_ENTRY_PATH_ANATOMY_TEST_ONLY"
EPSILON = 1e-12
OUTCOME_WIN = "WIN"
OUTCOME_LOSS = "LOSS"
OUTCOME_BREAK_EVEN = "BREAK_EVEN"
OUTCOMES = (OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAK_EVEN)
PROTECTION_CLOSE_REASONS = {"STOP_LOSS", "TAKE_PROFIT"}
DESCRIPTIVE_R_LEVELS = (0.25, 0.50, 1.00)
LOCAL_STRUCTURE_METRIC = "NOT_CANONICALLY_AVAILABLE"


@dataclass(frozen=True, slots=True)
class PostEntryPathRow:
    """Factual trade та її descriptive completed-M1 outcome path."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    outcome: str
    mfe_r: float
    mae_r: float
    bars_to_mfe: int
    bars_to_mae: int
    bars_to_close: int
    reached_plus_0_25r: bool
    reached_plus_0_50r: bool
    reached_plus_1_00r: bool
    profit_then_loss: bool

    @property
    def max_achieved_r(self) -> float:
        """Повернути maximal factual favorable excursion у risk units."""

        return self.mfe_r


def _outcome(trade: WorkspaceHistoricalTradeDiagnostic) -> str:
    """Класифікувати factual realized PnL без зміни close semantics."""

    if trade.final_profit > EPSILON:
        return OUTCOME_WIN
    if trade.final_profit < -EPSILON:
        return OUTCOME_LOSS
    return OUTCOME_BREAK_EVEN


def _execution_events(
    runtime: WorkspaceRuntime,
) -> tuple[WorkspaceMarketEvent, ...]:
    """Розгорнути immutable M1 execution windows завершеного Replay."""

    session = runtime.replay_session
    assert session is not None and session.completed and session.multi_resolution
    events = tuple(
        event
        for window in session.execution_windows
        for event in window
    )
    assert events
    assert all(event.timeframe == session.source_timeframe == "M1" for event in events)
    assert all(
        previous.timestamp < current.timestamp
        for previous, current in zip(events, events[1:])
    )
    return events


def _trade_events(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    timestamps: tuple,
) -> tuple[WorkspaceMarketEvent, ...]:
    """Вибрати completed M1 bars від factual entry до close включно."""

    start = bisect_left(timestamps, trade.entry_timestamp)
    stop = bisect_right(timestamps, trade.close_timestamp)
    selected = events[start:stop]
    assert selected
    assert selected[0].timestamp == trade.entry_timestamp
    assert selected[-1].timestamp == trade.close_timestamp
    return selected


def _bar_excursions(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> tuple[float, float]:
    """Обчислити favorable/adverse PnL одного completed M1 bar."""

    direction = 1.0 if trade.direction == "BUY" else -1.0
    if trade.direction == "BUY":
        favorable_price = event.high
        adverse_price = event.low
    else:
        favorable_price = event.low
        adverse_price = event.high
    favorable = (favorable_price - trade.entry_price) * trade.volume * direction
    adverse = (adverse_price - trade.entry_price) * trade.volume * direction
    return max(favorable, 0.0), min(adverse, 0.0)


def _close_excursions(
    trade: WorkspaceHistoricalTradeDiagnostic,
) -> tuple[float, float]:
    """Відтворити factual close point без intrabar-order припущення."""

    direction = 1.0 if trade.direction == "BUY" else -1.0
    profit = (trade.close_price - trade.entry_price) * trade.volume * direction
    return max(profit, 0.0), min(profit, 0.0)


def _build_row(
    period: str,
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
    timestamps: tuple,
) -> PostEntryPathRow:
    """Відновити factual MFE/MAE path однієї закритої trade."""

    selected = _trade_events(trade, events, timestamps)
    maximum_favorable = 0.0
    maximum_adverse = 0.0
    bars_to_mfe = 0
    bars_to_mae = 0
    for bar_number, event in enumerate(selected, start=1):
        protected_close = (
            event.timestamp == trade.close_timestamp
            and trade.close_reason in PROTECTION_CLOSE_REASONS
        )
        if protected_close:
            favorable, adverse = _close_excursions(trade)
        else:
            favorable, adverse = _bar_excursions(trade, event)
            if event.timestamp == trade.close_timestamp:
                close_favorable, close_adverse = _close_excursions(trade)
                favorable = max(favorable, close_favorable)
                adverse = min(adverse, close_adverse)
        if favorable > maximum_favorable + EPSILON:
            maximum_favorable = favorable
            bars_to_mfe = bar_number
        if adverse < maximum_adverse - EPSILON:
            maximum_adverse = adverse
            bars_to_mae = bar_number

    assert math.isclose(
        maximum_favorable,
        trade.maximum_favorable_excursion,
        rel_tol=0.0,
        abs_tol=1e-8,
    )
    assert math.isclose(
        maximum_adverse,
        trade.maximum_adverse_excursion,
        rel_tol=0.0,
        abs_tol=1e-8,
    )
    risk = trade.stop_loss_distance * trade.volume
    assert risk > 0.0
    mfe_r = maximum_favorable / risk
    mae_r = -maximum_adverse / risk
    outcome = _outcome(trade)
    return PostEntryPathRow(
        period=period,
        trade=trade,
        outcome=outcome,
        mfe_r=mfe_r,
        mae_r=mae_r,
        bars_to_mfe=bars_to_mfe,
        bars_to_mae=bars_to_mae,
        bars_to_close=len(selected),
        reached_plus_0_25r=mfe_r + EPSILON >= DESCRIPTIVE_R_LEVELS[0],
        reached_plus_0_50r=mfe_r + EPSILON >= DESCRIPTIVE_R_LEVELS[1],
        reached_plus_1_00r=mfe_r + EPSILON >= DESCRIPTIVE_R_LEVELS[2],
        profit_then_loss=outcome == OUTCOME_LOSS and mfe_r > EPSILON,
    )


def _run_anatomy_period(spec) -> tuple[PostEntryPathRow, ...]:
    """Запустити canonical production Replay і побудувати всі outcome rows."""

    runtime, _, broker_requests = _run_period(spec)
    assert broker_requests == 0
    assert not _broker_execution_attempted(runtime)
    execution = runtime.replay_execution
    summary = runtime.historical_summary
    assert execution is not None and summary is not None
    events = _execution_events(runtime)
    timestamps = tuple(event.timestamp for event in events)
    rows = tuple(
        _build_row(spec.code, trade, events, timestamps)
        for trade in execution.trade_diagnostics()
    )
    expected = EXPECTATIONS[spec.code]
    assert len(rows) == expected.trades == summary.opened_trades
    counts = Counter(row.outcome for row in rows)
    assert (
        counts[OUTCOME_WIN],
        counts[OUTCOME_LOSS],
        counts[OUTCOME_BREAK_EVEN],
    ) == (expected.wins, expected.losses, expected.break_even)
    return rows


def _reference_summary(
    period: str,
    rows: tuple[PostEntryPathRow, ...],
) -> None:
    """Надрукувати однакові descriptive path metrics для WIN/LOSS/BE."""

    print(f"REFERENCE_OUTCOME_SUMMARY_{period}")
    for outcome in OUTCOMES:
        selected = tuple(row for row in rows if row.outcome == outcome)
        assert selected
        reached = tuple(
            sum(row.mfe_r + EPSILON >= level for row in selected)
            for level in DESCRIPTIVE_R_LEVELS
        )
        print(
            f"  {outcome}=count:{len(selected)},"
            "mfe_r_mean:"
            f"{statistics.fmean(row.mfe_r for row in selected):.4f},"
            "mfe_r_median:"
            f"{statistics.median(row.mfe_r for row in selected):.4f},"
            "mae_r_mean:"
            f"{statistics.fmean(row.mae_r for row in selected):.4f},"
            "mae_r_median:"
            f"{statistics.median(row.mae_r for row in selected):.4f},"
            "bars_to_mfe_median:"
            f"{statistics.median(row.bars_to_mfe for row in selected):g},"
            "bars_to_mae_median:"
            f"{statistics.median(row.bars_to_mae for row in selected):g},"
            "bars_to_close_median:"
            f"{statistics.median(row.bars_to_close for row in selected):g},"
            f"reached_0.25r:{reached[0]},reached_0.5r:{reached[1]},"
            f"reached_1r:{reached[2]}"
        )


def _print_loss_rows(rows_by_period: dict[str, tuple[PostEntryPathRow, ...]]) -> None:
    """Надрукувати компактну audit table для всіх factual LOSS."""

    print("FACTUAL_LOSS_POST_ENTRY_ROWS")
    print(
        "  period|trade_id/time|side|close_reason|MFE_R|MAE_R|bars_to_MFE|"
        "bars_to_MAE|bars_to_close|reached_0.25R|reached_0.5R|reached_1R"
    )
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            if row.outcome != OUTCOME_LOSS:
                continue
            trade = row.trade
            print(
                f"  {period}|{trade.position_id}/{trade.entry_timestamp.isoformat()}|"
                f"{trade.direction}|{trade.close_reason}|{row.mfe_r:.4f}|"
                f"{row.mae_r:.4f}|{row.bars_to_mfe}|{row.bars_to_mae}|"
                f"{row.bars_to_close}|{row.reached_plus_0_25r}|"
                f"{row.reached_plus_0_50r}|{row.reached_plus_1_00r}"
            )


def _close_reason_text(rows: tuple[PostEntryPathRow, ...]) -> str:
    """Сформувати deterministic close-reason counts для LOSS."""

    counts = Counter(
        row.trade.close_reason for row in rows if row.outcome == OUTCOME_LOSS
    )
    return ",".join(f"{reason}:{counts[reason]}" for reason in sorted(counts))


def _loss_bin_counts(rows: tuple[PostEntryPathRow, ...]) -> tuple[int, int, int, int]:
    """Порахувати задані descriptive MFE bins лише для LOSS."""

    losses = tuple(row for row in rows if row.outcome == OUTCOME_LOSS)
    return (
        sum(row.mfe_r + EPSILON < 0.25 for row in losses),
        sum(row.mfe_r + EPSILON >= 0.25 for row in losses),
        sum(row.mfe_r + EPSILON >= 0.50 for row in losses),
        sum(row.mfe_r + EPSILON >= 1.00 for row in losses),
    )


def main() -> None:
    """Запустити T108-01 і повернути factual post-entry anatomy."""

    production_before = _production_hashes()
    rows_by_period = {spec.code: _run_anatomy_period(spec) for spec in PERIODS}
    production_after = _production_hashes()
    assert production_after == production_before

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    for period in ("2025", "2026"):
        rows = rows_by_period[period]
        counts = Counter(row.outcome for row in rows)
        print(f"{period}_trades={len(rows)}")
        print(f"{period}_wins={counts[OUTCOME_WIN]}")
        print(f"{period}_losses={counts[OUTCOME_LOSS]}")
        print(f"{period}_break_even={counts[OUTCOME_BREAK_EVEN]}")

    for period in ("2025", "2026"):
        under, quarter, half, full = _loss_bin_counts(rows_by_period[period])
        print(f"{period}_loss_mfe_lt_0_25r={under}")
        print(f"{period}_loss_mfe_ge_0_25r={quarter}")
        print(f"{period}_loss_mfe_ge_0_50r={half}")
        print(f"{period}_loss_mfe_ge_1_00r={full}")

    for period in ("2025", "2026"):
        profit_then_loss = sum(
            row.profit_then_loss for row in rows_by_period[period]
        )
        print(f"{period}_loss_profit_then_loss={profit_then_loss}")
    print(
        "loss_close_reason_counts_2025="
        f"{_close_reason_text(rows_by_period['2025'])}"
    )
    print(
        "loss_close_reason_counts_2026="
        f"{_close_reason_text(rows_by_period['2026'])}"
    )
    print(f"local_structure_metric={LOCAL_STRUCTURE_METRIC}")
    print("bar_numbers=ONE_BASED_FROM_ENTRY;ZERO_MEANS_NO_NONZERO_EXCURSION")
    print("mae_r_sign=POSITIVE_ADVERSE_MAGNITUDE")
    print("descriptive_bins_only=True")
    print("alternative_exit_simulated=False")
    print("threshold_sweep_performed=False")
    print("future_bars_used_for_outcome_anatomy_only=True")
    print("completed_market_events_only=True")
    print("lookahead_used=False")
    print("broker_requests=0")
    print("broker_execution_attempted=False")
    print("production_logic_changed=False")
    for period in ("2025", "2026"):
        _reference_summary(period, rows_by_period[period])
    _print_loss_rows(rows_by_period)
    print("T108_01_RESIDUAL_LOSS_POST_ENTRY_PATH_ANATOMY=OK")


if __name__ == "__main__":
    main()
