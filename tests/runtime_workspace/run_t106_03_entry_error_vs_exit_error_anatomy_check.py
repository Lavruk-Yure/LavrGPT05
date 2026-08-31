"""run_t106_03_entry_error_vs_exit_error_anatomy_check.py — T106-03.

TEST_ONLY runner виконує незмінений registered current-production Candidate F
Replay окремо для 2025 і 2026 та досліджує тільки factual LOSS trades. Після
завершення кожної factual угоди її production diagnostics поєднуються з
completed M15 bars від entry до close, щоб відновити час MFE, meaningful
adverse move і тривалість позиції. Future bars використовуються виключно для
outcome anatomy та ніколи не впливають на entry decision або його features.

Класифікація використовує фіксовані, не оптимізовані TEST_ONLY рівні 0.50R
для meaningful favorable і adverse excursion. ENTRY_BAD означає відсутність
meaningful MFE; WHIPSAW_REVERSAL вимагає, щоб peak MFE був на ранішому bar,
ніж перше досягнення 0.50R adverse move; решта робочих entries, що завершилися
LOSS, належать до ENTRY_GOOD_EXIT_BAD. Внутрішньобарний порядок не вгадується.

Runner не створює entry guard, exit rule або production threshold, не виконує
sweep/ML, не використовує Donchian, Supertrend чи новий індикатор і перевіряє
production hashes, deterministic completed-bar Replay та broker_requests=0.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from run_algorithm_workspace_replay_virtual_execution_check import (
    BrokerRequestProbe,
)
from run_t105_10_pd_35_production_regression_check import (
    PeriodSpec,
    _workspace,
)
from run_t105_15_stochastic_entry_anatomy_check import (
    StochasticAnatomyRuntime,
    _production_hashes,
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
from core.workspace_market_event import WorkspaceMarketEvent

TEST_ID = "T106-03"
MODE = "RM106_T106_03_ENTRY_ERROR_VS_EXIT_ERROR_ANATOMY_TEST_ONLY"
EPSILON = 1e-12
MEANINGFUL_FAVORABLE_R = 0.50
MEANINGFUL_ADVERSE_R = 0.50
ENTRY_BAD = "ENTRY_BAD"
ENTRY_GOOD_EXIT_BAD = "ENTRY_GOOD_EXIT_BAD"
WHIPSAW_REVERSAL = "WHIPSAW_REVERSAL"
ANATOMY_CLASSES = (ENTRY_BAD, ENTRY_GOOD_EXIT_BAD, WHIPSAW_REVERSAL)
PROTECTION_CLOSE_REASONS = {"STOP_LOSS", "TAKE_PROFIT"}


class OutcomeAnatomyRuntime(StochasticAnatomyRuntime):
    """Зберегти всі completed events, якими factual execution рухає позиції."""

    def __init__(self, *args, **kwargs) -> None:
        self.execution_events: dict[datetime, WorkspaceMarketEvent] = {}
        super().__init__(*args, **kwargs)

    def _advance_replay_execution(
        self,
        event: WorkspaceMarketEvent,
    ) -> None:
        """Запам'ятати completed event перед незміненою factual обробкою."""

        existing = self.execution_events.get(event.timestamp)
        assert existing is None or existing == event
        self.execution_events[event.timestamp] = event
        super()._advance_replay_execution(event)


@dataclass(frozen=True, slots=True)
class OutcomeAnatomyRow:
    """Factual LOSS та його TEST_ONLY післявхідна outcome anatomy."""

    period: str
    trade: WorkspaceHistoricalTradeDiagnostic
    risk: float
    mfe: float
    mae: float
    mfe_r: float
    mae_r: float
    bars_to_mfe: int
    bars_to_adverse: int | None
    bars_held: int
    mfe_before_adverse: bool
    anatomy_class: str


def _bar_excursions(
    trade: WorkspaceHistoricalTradeDiagnostic,
    event: WorkspaceMarketEvent,
) -> tuple[float, float]:
    """Обчислити favorable/adverse PnL одного завершеного M15 bar."""

    direction = 1.0 if trade.direction == "BUY" else -1.0
    if trade.direction == "BUY":
        favorable_price = event.high
        adverse_price = event.low
    else:
        favorable_price = event.low
        adverse_price = event.high
    favorable = (
        favorable_price - trade.entry_price
    ) * trade.volume * direction
    adverse = (
        adverse_price - trade.entry_price
    ) * trade.volume * direction
    return max(favorable, 0.0), min(adverse, 0.0)


def _close_excursions(
    trade: WorkspaceHistoricalTradeDiagnostic,
) -> tuple[float, float]:
    """Відтворити factual close point без припущення intrabar ordering."""

    direction = 1.0 if trade.direction == "BUY" else -1.0
    profit = (
        trade.close_price - trade.entry_price
    ) * trade.volume * direction
    return max(profit, 0.0), min(profit, 0.0)


def _trade_events(
    trade: WorkspaceHistoricalTradeDiagnostic,
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceMarketEvent, ...]:
    """Вибрати completed M15 bars від factual entry до factual close включно."""

    selected = tuple(
        event
        for event in events
        if trade.entry_timestamp <= event.timestamp <= trade.close_timestamp
    )
    assert selected
    assert selected[0].timestamp == trade.entry_timestamp
    assert selected[-1].timestamp == trade.close_timestamp, (
        trade.position_id,
        trade.entry_timestamp,
        trade.close_timestamp,
        selected[-1].timestamp,
    )
    return selected


def _classify(
    mfe_r: float,
    bars_to_mfe: int,
    bars_to_adverse: int | None,
) -> tuple[bool, str]:
    """Застосувати фіксовані TEST_ONLY anatomy rules без optimization."""

    if mfe_r + EPSILON < MEANINGFUL_FAVORABLE_R:
        return False, ENTRY_BAD
    mfe_before_adverse = (
        bars_to_adverse is not None and bars_to_mfe < bars_to_adverse
    )
    if mfe_before_adverse:
        return True, WHIPSAW_REVERSAL
    return False, ENTRY_GOOD_EXIT_BAD


def _build_loss_rows(
    period: str,
    trades: tuple[WorkspaceHistoricalTradeDiagnostic, ...],
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[OutcomeAnatomyRow, ...]:
    """Побудувати outcome anatomy лише для factual negative-PnL trades."""

    rows: list[OutcomeAnatomyRow] = []
    for trade in trades:
        if trade.final_profit >= -EPSILON:
            continue
        risk = trade.stop_loss_distance * trade.volume
        assert risk > 0.0
        selected = _trade_events(trade, events)
        maximum_favorable = 0.0
        maximum_adverse = 0.0
        bars_to_mfe = 0
        bars_to_adverse: int | None = None
        for bar_number, event in enumerate(selected, start=1):
            if (
                event.timestamp == trade.close_timestamp
                and trade.close_reason in PROTECTION_CLOSE_REASONS
            ):
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
            maximum_adverse = min(maximum_adverse, adverse)
            if (
                bars_to_adverse is None
                and -adverse / risk + EPSILON >= MEANINGFUL_ADVERSE_R
            ):
                bars_to_adverse = bar_number

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
        ), (
            trade.position_id,
            trade.close_reason,
            maximum_adverse,
            trade.maximum_adverse_excursion,
            trade.entry_timestamp,
            trade.close_timestamp,
        )
        mfe_r = maximum_favorable / risk
        mae_r = maximum_adverse / risk
        mfe_before_adverse, anatomy_class = _classify(
            mfe_r,
            bars_to_mfe,
            bars_to_adverse,
        )
        rows.append(
            OutcomeAnatomyRow(
                period=period,
                trade=trade,
                risk=risk,
                mfe=maximum_favorable,
                mae=maximum_adverse,
                mfe_r=mfe_r,
                mae_r=mae_r,
                bars_to_mfe=bars_to_mfe,
                bars_to_adverse=bars_to_adverse,
                bars_held=len(selected),
                mfe_before_adverse=mfe_before_adverse,
                anatomy_class=anatomy_class,
            )
        )
    return tuple(rows)


def _run_period(spec: PeriodSpec) -> tuple[OutcomeAnatomyRow, ...]:
    """Виконати один factual current-production Replay без broker execution."""

    broker_probe = BrokerRequestProbe()
    runtime = OutcomeAnatomyRuntime(
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
    execution = runtime.replay_execution
    summary = runtime.historical_summary
    assert execution is not None and summary is not None
    trades = execution.trade_diagnostics()
    events = tuple(
        runtime.execution_events[timestamp]
        for timestamp in sorted(runtime.execution_events)
    )
    rows = _build_loss_rows(spec.code, trades, events)
    assert len(rows) == summary.losing_trades
    assert broker_probe.requests == 0
    assert not _broker_execution_attempted(runtime)
    assert session.completed
    assert all(event.timeframe == "M15" for event in session.events)
    print(
        f"  population_{spec.code}=trades:{summary.opened_trades},"
        f"W:{summary.winning_trades},L:{summary.losing_trades},"
        f"BE:{summary.break_even_trades},net:{summary.net_profit:+.2f},"
        f"pf:{summary.profit_factor:.4f},dd:{summary.maximum_drawdown:.2f},"
        f"stochastic_current_bar_rejects:{stochastic_rejects},"
        f"broker_requests:{broker_probe.requests}"
    )
    return rows


def _optional_bar(value: int | None) -> str:
    """Надрукувати номер bar або явну відсутність meaningful adverse move."""

    return "NONE" if value is None else str(value)


def _print_rows(rows_by_period: dict[str, tuple[OutcomeAnatomyRow, ...]]) -> None:
    """Надрукувати окремий audit row для кожного factual LOSS."""

    print("  FACTUAL_LOSS_ROWS")
    print(
        "    period|timestamp|close_timestamp|side|entry_price|close_price|"
        "pnl|close_reason|R|SL_distance|MFE|MFE_R|MAE|MAE_R|bars_to_mfe|"
        "bars_to_adverse|bars_held|mfe_before_adverse|anatomy_class"
    )
    for period in ("2025", "2026"):
        for row in rows_by_period[period]:
            trade = row.trade
            print(
                f"    {period}|{trade.entry_timestamp.isoformat()}|"
                f"{trade.close_timestamp.isoformat()}|{trade.direction}|"
                f"{trade.entry_price:.5f}|{trade.close_price:.5f}|"
                f"{trade.final_profit:+.4f}|{trade.close_reason}|"
                f"{row.risk:.4f}|{trade.stop_loss_distance:.5f}|"
                f"{row.mfe:.4f}|{row.mfe_r:.4f}|{row.mae:.4f}|"
                f"{row.mae_r:.4f}|{row.bars_to_mfe}|"
                f"{_optional_bar(row.bars_to_adverse)}|{row.bars_held}|"
                f"{row.mfe_before_adverse}|{row.anatomy_class}"
            )


def _mean(values: tuple[float, ...]) -> float:
    """Повернути deterministic arithmetic mean непорожньої population."""

    assert values
    return statistics.fmean(values)


def _print_summary(
    label: str,
    rows: tuple[OutcomeAnatomyRow, ...],
) -> None:
    """Надрукувати anatomy summary та перетин із factual close reason."""

    assert rows
    counts = Counter(row.anatomy_class for row in rows)
    total = len(rows)
    print(f"  SUMMARY_{label}")
    print(f"    LOSS_count={total}")
    for anatomy_class in ANATOMY_CLASSES:
        count = counts[anatomy_class]
        print(
            f"    {anatomy_class}=count:{count},percent:{count / total * 100:.2f}"
        )
    print("    anatomy_x_close_reason")
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        matrix[row.anatomy_class][row.trade.close_reason] += 1
    close_reasons = sorted({row.trade.close_reason for row in rows})
    for anatomy_class in ANATOMY_CLASSES:
        values = ",".join(
            f"{reason}:{matrix[anatomy_class][reason]}"
            for reason in close_reasons
        )
        print(f"      {anatomy_class}|{values}")

    mfe_values = tuple(row.mfe_r for row in rows)
    mae_values = tuple(row.mae_r for row in rows)
    print(
        f"    MFE_R=mean:{_mean(mfe_values):.4f},"
        f"median:{statistics.median(mfe_values):.4f}"
    )
    print(
        f"    MAE_R=mean:{_mean(mae_values):.4f},"
        f"median:{statistics.median(mae_values):.4f}"
    )
    stop_loss = tuple(
        row for row in rows if row.trade.close_reason == "STOP_LOSS"
    )
    profit_drawdown = tuple(
        row for row in rows if row.trade.close_reason == "PROFIT_DRAWDOWN"
    )
    pd_meaningfully_profitable = sum(
        row.mfe_r + EPSILON >= MEANINGFUL_FAVORABLE_R
        for row in profit_drawdown
    )
    print(f"    STOP_LOSS_losses={len(stop_loss)}")
    print(f"    PROFIT_DRAWDOWN_losses={len(profit_drawdown)}")
    print(
        "    PROFIT_DRAWDOWN_losses_meaningfully_profitable_first="
        f"{pd_meaningfully_profitable}/{len(profit_drawdown)}"
    )
    print(f"    potential_entry_problem={counts[ENTRY_BAD]}")
    print(
        "    potential_exit_or_PD_problem="
        f"{counts[ENTRY_GOOD_EXIT_BAD]}"
    )
    print(f"    whipsaw_or_reversal={counts[WHIPSAW_REVERSAL]}")


def main() -> None:
    """Запустити T106-03 та зафіксувати factual LOSS outcome anatomy."""

    production_before = _production_hashes()
    print("T106-03 Entry Error vs Exit Error Anatomy")
    print(f"  test_id={TEST_ID}")
    print(f"  mode={MODE}")
    print("  population=FACTUAL_CURRENT_PRODUCTION_LOSSES_ONLY")
    print("  classification_rules=TEST_ONLY_NOT_PRODUCTION")
    print(f"  meaningful_favorable_threshold_R={MEANINGFUL_FAVORABLE_R:.2f}")
    print(f"  meaningful_adverse_threshold_R={MEANINGFUL_ADVERSE_R:.2f}")
    print("  bar_numbers=ONE_BASED_FROM_ENTRY;ZERO_MEANS_MFE_AT_ENTRY_ONLY")
    print("  same_bar_ordering_assumed=False")
    print("  ENTRY_BAD_rule=MFE_R_LT_0.50")
    print(
        "  WHIPSAW_REVERSAL_rule=MFE_R_GE_0.50_AND_MFE_BAR_STRICTLY_BEFORE_"
        "FIRST_ADVERSE_0.50R_BAR"
    )
    print("  ENTRY_GOOD_EXIT_BAD_rule=MFE_R_GE_0.50_AND_NOT_WHIPSAW_REVERSAL")
    rows_by_period = {spec.code: _run_period(spec) for spec in PERIODS}
    _print_rows(rows_by_period)
    _print_summary("2025", rows_by_period["2025"])
    _print_summary("2026", rows_by_period["2026"])
    combined = rows_by_period["2025"] + rows_by_period["2026"]
    _print_summary("COMBINED", combined)

    assert _production_hashes() == production_before
    print("  factual_current_production_losses_only=True")
    print("  future_bars_used_for_outcome_anatomy_only=True")
    print("  future_bars_used_for_entry_features=False")
    print("  completed_market_events_only=True")
    print("  no_look_ahead_entry_decision=True")
    print("  deterministic_replay=True")
    print("  donchian_used=False")
    print("  supertrend_used=False")
    print("  production_logic_changed=False")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  entry_filter_created=False")
    print("  exit_rule_created=False")
    print("  threshold_optimization_performed=False")
    print("T106_03_ENTRY_ERROR_VS_EXIT_ERROR_ANATOMY=OK")


if __name__ == "__main__":
    main()
