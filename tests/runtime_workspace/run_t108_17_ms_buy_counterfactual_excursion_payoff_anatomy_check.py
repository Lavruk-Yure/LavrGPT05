"""run_t108_17_ms_buy_counterfactual_excursion_payoff_anatomy_check.py — T108-17.

TEST_ONLY runner повторює чотири counterfactual MS_BUY + factual FLAT
populations із T108-16 (2025/2026, P3/P4) і досліджує їхній payoff path
тільки від causal NEXT_BAR_OPEN entry до factual canonical close. Для кожної
закритої trade штатні MFE, MAE і realized PnL нормуються на її initial 1R;
фіксовані 0.25R/0.50R/1R/2R рівні є лише descriptive bins.

Агрегації за outcome та close reason, LOSS excursion і WIN payoff показують,
чому позитивний one-bar directional label не перетворився на прибутковий
Replay. Future bars після factual exit не читаються, alternative exits не
симулюються, thresholds не оптимізуються. Runner повторно використовує
T108-16 harness і незмінені SL/TP/Profit Drawdown/negative-PD mechanics,
не звертається до broker та не змінює production, thresholds або MD7.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-17"
MODE = "RM108_T108_17_MS_BUY_COUNTERFACTUAL_EXCURSION_PAYOFF_ANATOMY_TEST_ONLY"
COUNTERFACTUAL_SCRIPT = "run_t108_16_ms_buy_flat_counterfactual_entry_replay_check.py"
VARIANTS = (3, 4)
PERIOD_CODES = ("2025", "2026")
OUTCOMES = ("WIN", "LOSS", "BE")
CLOSE_REASONS = ("PROFIT_DRAWDOWN", "STOP_LOSS", "TAKE_PROFIT")
R_LEVELS = (0.25, 0.50, 1.0, 2.0)
EPSILON = 1e-12


def _load_counterfactual_module() -> ModuleType:
    """Завантажити T108-16 як безпосередній canonical test-only harness."""

    file_path = TEST_ROOT / COUNTERFACTUAL_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_17_counterfactual",
        file_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COUNTERFACTUAL = _load_counterfactual_module()
PERIODS = getattr(COUNTERFACTUAL, "PERIODS")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    COUNTERFACTUAL,
    "PRODUCTION_HASHES",
)
RUN_WITH_RUNTIME: Callable[..., tuple[Any, Any]] = getattr(
    COUNTERFACTUAL,
    "RUN_WITH_RUNTIME",
)
POSITION_LABELS: Callable[..., dict[datetime, Any]] = getattr(
    COUNTERFACTUAL,
    "POSITION_LABELS",
)
CANDIDATE_AUDIT: Callable[..., Any] = getattr(
    COUNTERFACTUAL,
    "_candidate_audit",
)
RUN_COUNTERFACTUAL: Callable[..., Any] = getattr(
    COUNTERFACTUAL,
    "_run_counterfactual",
)
ASSERT_BASELINE: Callable[..., None] = getattr(
    COUNTERFACTUAL,
    "_assert_baseline",
)
BROKER_EXECUTION_ATTEMPTED: Callable[..., bool] = getattr(
    COUNTERFACTUAL,
    "BROKER_EXECUTION_ATTEMPTED",
)


@dataclass(frozen=True, slots=True)
class ExcursionRow:
    """Factual до-close excursion та payoff однієї counterfactual trade."""

    period: str
    persistence: int
    trade: Any
    outcome: str
    mfe_r: float
    mae_r: float
    realized_r: float
    reached_0_25r: bool
    reached_0_50r: bool
    reached_1r: bool
    reached_2r: bool


@dataclass(frozen=True, slots=True)
class GroupStats:
    """Однакова excursion aggregation для outcome/close-reason group."""

    trades: int
    median_mfe_r: float
    mean_mfe_r: float
    median_mae_r: float
    mean_mae_r: float
    reached_counts: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Distribution:
    """П'ятиточковий descriptive розподіл без threshold selection."""

    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    mean: float


def _trades(runtime: Any) -> tuple[Any, ...]:
    """Прочитати immutable closed trades із canonical execution engine."""

    execution = runtime.replay_execution
    assert execution is not None
    return tuple(execution.trade_diagnostics())


def _outcome(final_profit: float) -> str:
    """Класифікувати factual payoff у WIN/LOSS/BE."""

    if final_profit > EPSILON:
        return "WIN"
    if final_profit < -EPSILON:
        return "LOSS"
    return "BE"


def _excursion_row(period: str, persistence: int, trade: Any) -> ExcursionRow:
    """Нормувати штатні до-close MFE/MAE та realized PnL на initial 1R."""

    initial_risk = trade.stop_loss_distance * trade.volume
    assert initial_risk > 0.0
    mfe_r = trade.maximum_favorable_excursion / initial_risk
    mae_r = -trade.maximum_adverse_excursion / initial_risk
    realized_r = trade.final_profit / initial_risk
    assert mfe_r >= -EPSILON
    assert mae_r >= -EPSILON
    assert trade.close_timestamp >= trade.entry_timestamp
    return ExcursionRow(
        period=period,
        persistence=persistence,
        trade=trade,
        outcome=_outcome(trade.final_profit),
        mfe_r=max(mfe_r, 0.0),
        mae_r=max(mae_r, 0.0),
        realized_r=realized_r,
        reached_0_25r=mfe_r + EPSILON >= R_LEVELS[0],
        reached_0_50r=mfe_r + EPSILON >= R_LEVELS[1],
        reached_1r=mfe_r + EPSILON >= R_LEVELS[2],
        reached_2r=mfe_r + EPSILON >= R_LEVELS[3],
    )


def _stats(rows: tuple[ExcursionRow, ...]) -> GroupStats:
    """Порахувати required MFE/MAE і reached-level facts непорожньої group."""

    assert rows
    mfe_values = tuple(row.mfe_r for row in rows)
    mae_values = tuple(row.mae_r for row in rows)
    reached_counts = (
        sum(row.reached_0_25r for row in rows),
        sum(row.reached_0_50r for row in rows),
        sum(row.reached_1r for row in rows),
        sum(row.reached_2r for row in rows),
    )
    return GroupStats(
        trades=len(rows),
        median_mfe_r=statistics.median(mfe_values),
        mean_mfe_r=statistics.fmean(mfe_values),
        median_mae_r=statistics.median(mae_values),
        mean_mae_r=statistics.fmean(mae_values),
        reached_counts=reached_counts,
    )


def _distribution(values: Iterable[float]) -> Distribution:
    """Побудувати inclusive quartiles для factual WIN payoff distribution."""

    sequence = tuple(values)
    assert sequence
    if len(sequence) == 1:
        q1 = sequence[0]
        q3 = sequence[0]
    else:
        q1, _, q3 = statistics.quantiles(sequence, n=4, method="inclusive")
    return Distribution(
        minimum=min(sequence),
        q1=q1,
        median=statistics.median(sequence),
        q3=q3,
        maximum=max(sequence),
        mean=statistics.fmean(sequence),
    )


def _percentage(count: int, total: int) -> float:
    """Повернути factual percentage без special empty-group semantics."""

    assert total > 0
    return count / total * 100.0


def _stats_fields(stats: GroupStats) -> str:
    """Стиснути required group metrics в deterministic output schema."""

    levels = []
    for label, count in zip(("0_25", "0_50", "1", "2"), stats.reached_counts):
        levels.append(f"reached_{label}r_count={count}")
        levels.append(
            f"reached_{label}r_percent={_percentage(count, stats.trades):.2f}"
        )
    return (
        f"trades={stats.trades}|median_MFE_R={stats.median_mfe_r:.4f}|"
        f"mean_MFE_R={stats.mean_mfe_r:.4f}|"
        f"median_MAE_R={stats.median_mae_r:.4f}|"
        f"mean_MAE_R={stats.mean_mae_r:.4f}|" + "|".join(levels)
    )


def _distribution_fields(prefix: str, values: Distribution) -> str:
    """Сформувати deterministic min/Q1/median/Q3/max/mean поля."""

    return (
        f"{prefix}_min={values.minimum:.4f}|{prefix}_q1={values.q1:.4f}|"
        f"{prefix}_median={values.median:.4f}|{prefix}_q3={values.q3:.4f}|"
        f"{prefix}_max={values.maximum:.4f}|{prefix}_mean={values.mean:.4f}"
    )


def _population_rows(
    all_rows: tuple[ExcursionRow, ...],
    period: str,
    persistence: int,
) -> tuple[ExcursionRow, ...]:
    """Вибрати одну з чотирьох наперед визначених populations."""

    return tuple(
        row
        for row in all_rows
        if row.period == period and row.persistence == persistence
    )


def _print_group_aggregations(all_rows: tuple[ExcursionRow, ...]) -> None:
    """Надрукувати окремі outcome та close-reason aggregations."""

    print("AGGREGATION_BY_OUTCOME")
    for period in PERIOD_CODES:
        for persistence in VARIANTS:
            population = _population_rows(all_rows, period, persistence)
            for outcome in OUTCOMES:
                rows = tuple(row for row in population if row.outcome == outcome)
                if not rows:
                    continue
                print(
                    f"period={period}|variant=P{persistence}|outcome={outcome}|"
                    f"{_stats_fields(_stats(rows))}"
                )

    print("AGGREGATION_BY_CLOSE_REASON")
    for period in PERIOD_CODES:
        for persistence in VARIANTS:
            population = _population_rows(all_rows, period, persistence)
            for close_reason in CLOSE_REASONS:
                rows = tuple(
                    row for row in population if row.trade.close_reason == close_reason
                )
                if not rows:
                    continue
                print(
                    f"period={period}|variant=P{persistence}|"
                    f"close_reason={close_reason}|{_stats_fields(_stats(rows))}"
                )


def _print_loss_anatomy(all_rows: tuple[ExcursionRow, ...]) -> None:
    """Показати prior favorable excursion factual LOSS без exit висновку."""

    print("LOSS_EXCURSION_ANATOMY")
    for period in PERIOD_CODES:
        for persistence in VARIANTS:
            losses = tuple(
                row
                for row in _population_rows(all_rows, period, persistence)
                if row.outcome == "LOSS"
            )
            stats = _stats(losses)
            print(
                f"period={period}|variant=P{persistence}|losses={len(losses)}|"
                f"loss_reached_0_25r={stats.reached_counts[0]}|"
                f"loss_reached_0_50r={stats.reached_counts[1]}|"
                f"loss_reached_1r={stats.reached_counts[2]}|"
                f"loss_reached_2r={stats.reached_counts[3]}|"
                f"median_MFE_R_loss={stats.median_mfe_r:.4f}|"
                f"median_MAE_R_loss={stats.median_mae_r:.4f}"
            )


def _print_win_payoff(all_rows: tuple[ExcursionRow, ...]) -> None:
    """Показати factual WIN MFE та realized-R distribution."""

    print("WIN_PAYOFF_ANATOMY")
    for period in PERIOD_CODES:
        for persistence in VARIANTS:
            wins = tuple(
                row
                for row in _population_rows(all_rows, period, persistence)
                if row.outcome == "WIN"
            )
            mfe = _distribution(row.mfe_r for row in wins)
            realized = _distribution(row.realized_r for row in wins)
            print(
                f"period={period}|variant=P{persistence}|wins={len(wins)}|"
                f"{_distribution_fields('MFE_R', mfe)}|"
                f"{_distribution_fields('realized_R', realized)}"
            )


def _impulse_label(rows: tuple[ExcursionRow, ...]) -> str:
    """Класифікувати median MFE за фіксованими user-supplied R bins."""

    median_mfe = statistics.median(row.mfe_r for row in rows)
    if median_mfe < 0.50 - EPSILON:
        return "mostly_small"
    if median_mfe >= 1.0 - EPSILON:
        return "substantial"
    return "mixed"


def _losses_often_prior_favorable(rows: tuple[ExcursionRow, ...]) -> bool:
    """Позначити, чи щонайменше половина LOSS досягла descriptive +0.25R."""

    losses = tuple(row for row in rows if row.outcome == "LOSS")
    assert losses
    reached = sum(row.reached_0_25r for row in losses)
    return reached * 2 >= len(losses)


def _print_population_summary(all_rows: tuple[ExcursionRow, ...]) -> None:
    """Надрукувати чотири descriptive labels та cross-period consistency."""

    print("POPULATION_SUMMARY")
    labels: dict[tuple[str, int], tuple[str, bool]] = {}
    for period in PERIOD_CODES:
        for persistence in VARIANTS:
            rows = _population_rows(all_rows, period, persistence)
            impulse = _impulse_label(rows)
            prior_favorable = _losses_often_prior_favorable(rows)
            labels[(period, persistence)] = (impulse, prior_favorable)
            print(
                f"period={period}|variant=P{persistence}|"
                f"directional_impulse={impulse}|"
                "losses_often_had_prior_favorable_excursion="
                f"{prior_favorable}"
            )
    stable = all(
        labels[("2025", persistence)] == labels[("2026", persistence)]
        for persistence in VARIANTS
    )
    print(f"cross_period_pattern_stable={stable}")
    print("summary_labels_are_descriptive_only=True")


def _print_trade_details(all_rows: tuple[ExcursionRow, ...]) -> None:
    """Надрукувати вимірювання кожної factual counterfactual trade."""

    print("COUNTERFACTUAL_EXCURSION_DETAIL")
    for row in all_rows:
        trade = row.trade
        print(
            f"period={row.period}|variant=P{row.persistence}|"
            f"trade_id={trade.position_id}|"
            f"entry_time={trade.entry_timestamp.isoformat()}|"
            f"factual_exit_time={trade.close_timestamp.isoformat()}|"
            f"outcome={row.outcome}|close_reason={trade.close_reason}|"
            f"MFE_R={row.mfe_r:.4f}|MAE_R={row.mae_r:.4f}|"
            f"realized_R={row.realized_r:+.4f}|"
            f"reached_0_25R={row.reached_0_25r}|"
            f"reached_0_50R={row.reached_0_50r}|"
            f"reached_1R={row.reached_1r}|reached_2R={row.reached_2r}"
        )


def main() -> int:
    """Виконати чотири T108-16 populations та factual payoff anatomy."""

    before_hashes = PRODUCTION_HASHES()
    baseline: dict[str, tuple[Any, Any, dict[datetime, Any]]] = {}
    results: list[Any] = []
    rows: list[ExcursionRow] = []
    print("T108_17_MS_BUY_COUNTERFACTUAL_EXCURSION_PAYOFF_ANATOMY")

    for spec in PERIODS:
        print(f"running_baseline_period={spec.code}", flush=True)
        replay, runtime = RUN_WITH_RUNTIME(spec)
        ASSERT_BASELINE(spec.code, runtime)
        assert not BROKER_EXECUTION_ATTEMPTED(runtime)
        labels = POSITION_LABELS(replay, runtime)
        baseline[spec.code] = (replay, runtime, labels)

    for spec in PERIODS:
        replay, _, labels = baseline[spec.code]
        for persistence in VARIANTS:
            audit = CANDIDATE_AUDIT(replay, labels, persistence)
            print(
                f"running_counterfactual_period={spec.code}|" f"variant=P{persistence}",
                flush=True,
            )
            result = RUN_COUNTERFACTUAL(spec, persistence, audit)
            results.append(result)
            trade_rows = tuple(
                _excursion_row(spec.code, persistence, trade)
                for trade in _trades(result.runtime)
            )
            assert len(trade_rows) == result.runtime.historical_summary.opened_trades
            rows.extend(trade_rows)

    result_tuple = tuple(results)
    all_rows = tuple(rows)
    assert len(result_tuple) == len(PERIOD_CODES) * len(VARIANTS)
    assert PRODUCTION_HASHES() == before_hashes
    _print_group_aggregations(all_rows)
    _print_loss_anatomy(all_rows)
    _print_win_payoff(all_rows)
    _print_population_summary(all_rows)
    _print_trade_details(all_rows)

    broker_requests = sum(
        replay.broker_requests for replay, _, _ in baseline.values()
    ) + sum(result.broker_requests for result in result_tuple)
    broker_execution_attempted = any(
        BROKER_EXECUTION_ATTEMPTED(runtime) for _, runtime, _ in baseline.values()
    ) or any(BROKER_EXECUTION_ATTEMPTED(result.runtime) for result in result_tuple)
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("hypothesis=EXACT_MS_BUY_FLAT_ONLY")
    print("variants=P3_P4_PREDEFINED")
    print("factual_entry_to_factual_exit_timeline_only=True")
    print("future_bars_after_factual_exit_used=False")
    print("alternative_exit_simulated=False")
    print("canonical_exit_stack_preserved=True")
    print("profit_drawdown_threshold=35")
    print("next_bar_open=True")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("best_mfe_threshold_selected=False")
    print("new_entry_filter_created=False")
    print("generic_score_model_created=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    assert broker_requests == 0
    assert not broker_execution_attempted
    print("T108_17_MS_BUY_COUNTERFACTUAL_EXCURSION_PAYOFF_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
