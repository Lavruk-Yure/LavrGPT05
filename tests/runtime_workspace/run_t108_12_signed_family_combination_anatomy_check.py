"""run_t108_12_signed_family_combination_anatomy_check.py — T108-12.

TEST_ONLY anatomy повторно використовує causal normalized family states GREEN
T108-11 і розкладає кожен completed M15 decision bar за exact tuple
MACD/Alligator/Stochastic. Для fixed P1..P5 runner окремо описує single,
same-direction pair, full-consensus і conflict populations у 2025 та 2026.

One-bar future HIGH/LOW використовується тільки як factual outcome label у R
decision bar; сам decision bar не входить у future window. Conflict states
отримують окремі BUY і SELL labels без majority direction. Runner не створює
угод, weights, threshold, best persistence, entry/exit/reverse logic, не
використовує Supertrend і не змінює production або MD7.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-12"
MODE = "RM108_T108_12_SIGNED_FAMILY_COMBINATION_ANATOMY_TEST_ONLY"
VOTE_SCRIPT = "run_t108_11_unweighted_family_vote_anatomy_check.py"
PERSISTENCES = (1, 2, 3, 4, 5)
PERIOD_CODES = ("2025", "2026")

SAME_STATES = {
    (1, 0, 0): "M_BUY",
    (-1, 0, 0): "M_SELL",
    (0, 1, 0): "A_BUY",
    (0, -1, 0): "A_SELL",
    (0, 0, 1): "S_BUY",
    (0, 0, -1): "S_SELL",
    (1, 1, 0): "MA_BUY",
    (-1, -1, 0): "MA_SELL",
    (1, 0, 1): "MS_BUY",
    (-1, 0, -1): "MS_SELL",
    (0, 1, 1): "AS_BUY",
    (0, -1, -1): "AS_SELL",
    (1, 1, 1): "MAS_BUY",
    (-1, -1, -1): "MAS_SELL",
}
CONFLICT_STATES = {
    (1, -1, 0): "M_BUY_A_SELL",
    (-1, 1, 0): "M_SELL_A_BUY",
    (1, 0, -1): "M_BUY_S_SELL",
    (-1, 0, 1): "M_SELL_S_BUY",
    (0, 1, -1): "A_BUY_S_SELL",
    (0, -1, 1): "A_SELL_S_BUY",
    (1, 1, -1): "MA_BUY_VS_S_SELL",
    (-1, -1, 1): "MA_SELL_VS_S_BUY",
    (1, -1, 1): "MS_BUY_VS_A_SELL",
    (-1, 1, -1): "MS_SELL_VS_A_BUY",
    (-1, 1, 1): "AS_BUY_VS_M_SELL",
    (1, -1, -1): "AS_SELL_VS_M_BUY",
}
SAME_CLASSES = tuple(SAME_STATES.values())
CONFLICT_CLASSES = tuple(CONFLICT_STATES.values())
PAIR_STRUCTURES = {
    "MA": ("M", "A"),
    "MS": ("M", "S"),
    "AS": ("A", "S"),
}
STRUCTURES = ("M", "A", "S", "MA", "MS", "AS", "MAS")


def _load_vote_module() -> ModuleType:
    """Завантажити GREEN T108-11 з canonical workspace path."""

    file_path = TEST_ROOT / VOTE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location("rm108_t108_12_vote", file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VOTE = _load_vote_module()
PERIODS = getattr(VOTE, "PERIODS")
RUN_PERIOD: Callable[..., Any] = getattr(VOTE, "RUN_PERIOD")
DECISION_ROWS: Callable[..., Any] = getattr(VOTE, "_decision_rows")
OUTCOME_METRICS: Callable[..., Any] = getattr(VOTE, "OUTCOME_METRICS")
PRODUCTION_HASHES: Callable[..., dict[str, str]] = getattr(
    VOTE,
    "PRODUCTION_HASHES",
)


@dataclass(frozen=True, slots=True)
class DirectionalOutcomeEvent:
    """Напрям factual outcome label для одного decision timestamp."""

    timestamp: datetime
    direction: str


@dataclass(frozen=True, slots=True)
class CombinationResult:
    """Exact taxonomy та directional metrics одного period/P variant."""

    same_rows: dict[str, tuple[Any, ...]]
    conflict_rows: dict[str, tuple[Any, ...]]
    same_metrics: dict[str, Any]
    conflict_metrics: dict[str, dict[str, Any]]
    neutral_count: int
    unclassified: Counter[tuple[int, int, int]]
    total_rows: int


def _direction(class_name: str) -> str:
    """Визначити expected side лише для same-direction class."""

    return "BUY" if class_name.endswith("_BUY") else "SELL"


def _events(rows: tuple[Any, ...], direction: str) -> tuple[Any, ...]:
    """Перетворити class rows на one-bar factual directional labels."""

    return tuple(DirectionalOutcomeEvent(row.timestamp, direction) for row in rows)


def _analyze(replay: Any, persistence: int) -> CombinationResult:
    """Класифікувати всі 27 exact states без score aggregation чи priority."""

    rows, _, _ = DECISION_ROWS(replay, persistence)
    same_lists: dict[str, list[Any]] = {name: [] for name in SAME_CLASSES}
    conflict_lists: dict[str, list[Any]] = {
        name: [] for name in CONFLICT_CLASSES
    }
    neutral_count = 0
    unclassified: Counter[tuple[int, int, int]] = Counter()
    for row in rows:
        state = (row.macd_vote, row.alligator_vote, row.stochastic_vote)
        if state in SAME_STATES:
            same_lists[SAME_STATES[state]].append(row)
        elif state in CONFLICT_STATES:
            conflict_lists[CONFLICT_STATES[state]].append(row)
        elif state == (0, 0, 0):
            neutral_count += 1
        else:
            unclassified[state] += 1

    same_rows = {name: tuple(items) for name, items in same_lists.items()}
    conflict_rows = {
        name: tuple(items) for name, items in conflict_lists.items()
    }
    same_metrics = {
        name: OUTCOME_METRICS(
            replay.events,
            _events(items, _direction(name)),
            1,
        )
        for name, items in same_rows.items()
    }
    conflict_metrics = {
        name: {
            direction: OUTCOME_METRICS(
                replay.events,
                _events(items, direction),
                1,
            )
            for direction in ("BUY", "SELL")
        }
        for name, items in conflict_rows.items()
    }
    classified = (
        sum(len(items) for items in same_rows.values())
        + sum(len(items) for items in conflict_rows.values())
        + neutral_count
        + sum(unclassified.values())
    )
    assert classified == len(rows)
    return CombinationResult(
        same_rows=same_rows,
        conflict_rows=conflict_rows,
        same_metrics=same_metrics,
        conflict_metrics=conflict_metrics,
        neutral_count=neutral_count,
        unclassified=unclassified,
        total_rows=len(rows),
    )


def _number(value: float | None) -> str:
    """Форматувати deterministic metric або NONE для zero population."""

    return "NONE" if value is None else f"{value:.4f}"


def _delta(left: float | None, right: float | None) -> str:
    """Форматувати left-minus-right або NONE без вигаданого zero."""

    if left is None or right is None:
        return "NONE"
    return f"{left - right:+.4f}"


def _count_delta(left: int, right: int) -> str:
    """Форматувати factual signed population delta."""

    return f"{left - right:+d}"


def _warning(count: int) -> str:
    """Позначити малу population, не відкидаючи class."""

    return "SMALL_SAMPLE" if count < 30 else "NONE"


def _metric_fields(metric: Any) -> str:
    """Сформувати повний factual outcome block same-direction class."""

    return (
        f"bars_count={metric.events}|"
        f"directional_success_count={metric.successes}|"
        "directional_success_rate_percent="
        f"{_number(metric.success_rate)}|"
        f"favorable_move_r_median={_number(metric.favorable_median)}|"
        f"adverse_move_r_median={_number(metric.adverse_median)}|"
        f"net_directional_edge_r_median={_number(metric.net_median)}|"
        f"sample_warning={_warning(metric.events)}"
    )


def _print_coverage(results: dict[str, dict[int, CombinationResult]]) -> None:
    """Вивести exact class populations та контроль повного покриття."""

    print("COMBINATION_COVERAGE")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            result = results[period][persistence]
            fields = [
                f"{name}={len(result.same_rows[name])}" for name in SAME_CLASSES
            ]
            fields.extend(
                f"{name}={len(result.conflict_rows[name])}"
                for name in CONFLICT_CLASSES
            )
            fields.extend(
                (
                    f"NEUTRAL={result.neutral_count}",
                    f"unclassified_count={sum(result.unclassified.values())}",
                    f"total_decision_bars={result.total_rows}",
                )
            )
            print(
                f"period={period}|persistence=P{persistence}|"
                + "|".join(fields)
            )


def _print_same(results: dict[str, dict[int, CombinationResult]]) -> None:
    """Вивести outcomes усіх exact same-direction combinations."""

    print("SAME_DIRECTION_COMBINATIONS")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            for name in SAME_CLASSES:
                metric = results[period][persistence].same_metrics[name]
                print(
                    f"period={period}|persistence=P{persistence}|class={name}|"
                    f"{_metric_fields(metric)}"
                )


def _print_conflicts(results: dict[str, dict[int, CombinationResult]]) -> None:
    """Вивести BUY і SELL labels conflict classes без winner selection."""

    print("CONFLICT_COMBINATIONS")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            result = results[period][persistence]
            for name in CONFLICT_CLASSES:
                buy = result.conflict_metrics[name]["BUY"]
                sell = result.conflict_metrics[name]["SELL"]
                print(
                    f"period={period}|persistence=P{persistence}|class={name}|"
                    f"bars_count={buy.events}|buy_success_count={buy.successes}|"
                    "buy_success_rate_percent="
                    f"{_number(buy.success_rate)}|"
                    f"buy_net_edge_r_median={_number(buy.net_median)}|"
                    f"sell_success_count={sell.successes}|"
                    "sell_success_rate_percent="
                    f"{_number(sell.success_rate)}|"
                    f"sell_net_edge_r_median={_number(sell.net_median)}|"
                    f"sample_warning={_warning(buy.events)}"
                )


def _print_pair_synergy(results: dict[str, dict[int, CombinationResult]]) -> None:
    """Порівняти кожну pair з обома constituent singles без selection."""

    print("PAIR_SYNERGY_CHECK")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            metrics = results[period][persistence].same_metrics
            for pair, singles in PAIR_STRUCTURES.items():
                for direction in ("BUY", "SELL"):
                    pair_metric = metrics[f"{pair}_{direction}"]
                    left = metrics[f"{singles[0]}_{direction}"]
                    right = metrics[f"{singles[1]}_{direction}"]
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"pair={pair}|direction={direction}|"
                        f"pair_bars={pair_metric.events}|"
                        f"{singles[0].lower()}_bars={left.events}|"
                        f"{singles[1].lower()}_bars={right.events}|"
                        f"pair_success_minus_{singles[0].lower()}="
                        f"{_delta(pair_metric.success_rate, left.success_rate)}|"
                        f"pair_success_minus_{singles[1].lower()}="
                        f"{_delta(pair_metric.success_rate, right.success_rate)}|"
                        f"pair_edge_minus_{singles[0].lower()}="
                        f"{_delta(pair_metric.net_median, left.net_median)}|"
                        f"pair_edge_minus_{singles[1].lower()}="
                        f"{_delta(pair_metric.net_median, right.net_median)}"
                    )


def _print_full_consensus(
    results: dict[str, dict[int, CombinationResult]],
) -> None:
    """Порівняти MAS з кожною pair того самого factual direction."""

    print("FULL_CONSENSUS_CHECK")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            metrics = results[period][persistence].same_metrics
            for direction in ("BUY", "SELL"):
                full = metrics[f"MAS_{direction}"]
                fields = [
                    f"period={period}",
                    f"persistence=P{persistence}",
                    f"direction={direction}",
                    f"mas_bars={full.events}",
                ]
                for pair in ("MA", "MS", "AS"):
                    item = metrics[f"{pair}_{direction}"]
                    fields.extend(
                        (
                            f"{pair.lower()}_bars={item.events}",
                            f"mas_success_minus_{pair.lower()}="
                            f"{_delta(full.success_rate, item.success_rate)}",
                            f"mas_edge_minus_{pair.lower()}="
                            f"{_delta(full.net_median, item.net_median)}",
                        )
                    )
                print("|".join(fields))


def _print_stochastic(
    results: dict[str, dict[int, CombinationResult]],
) -> None:
    """Показати factual deltas після додавання Stochastic до M, A або MA."""

    print("STOCHASTIC_CONTRIBUTION_CHECK")
    comparisons = (("MA", "MAS"), ("M", "MS"), ("A", "AS"))
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            metrics = results[period][persistence].same_metrics
            for without, with_stochastic in comparisons:
                for direction in ("BUY", "SELL"):
                    base = metrics[f"{without}_{direction}"]
                    candidate = metrics[f"{with_stochastic}_{direction}"]
                    print(
                        f"period={period}|persistence=P{persistence}|"
                        f"comparison={without}_TO_{with_stochastic}|"
                        f"direction={direction}|"
                        "bars_count_delta="
                        f"{_count_delta(candidate.events, base.events)}|"
                        "success_rate_delta="
                        f"{_delta(candidate.success_rate, base.success_rate)}|"
                        f"net_edge_delta="
                        f"{_delta(candidate.net_median, base.net_median)}"
                    )


def _print_asymmetry(results: dict[str, dict[int, CombinationResult]]) -> None:
    """Порівняти BUY і SELL populations кожної structural combination."""

    print("BUY_SELL_ASYMMETRY")
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            metrics = results[period][persistence].same_metrics
            for structure in STRUCTURES:
                buy = metrics[f"{structure}_BUY"]
                sell = metrics[f"{structure}_SELL"]
                print(
                    f"period={period}|persistence=P{persistence}|"
                    f"structure={structure}|buy_bars={buy.events}|"
                    f"sell_bars={sell.events}|"
                    f"buy_success_rate={_number(buy.success_rate)}|"
                    f"sell_success_rate={_number(sell.success_rate)}|"
                    f"buy_net_edge={_number(buy.net_median)}|"
                    f"sell_net_edge={_number(sell.net_median)}|"
                    "sell_minus_buy_success_rate="
                    f"{_delta(sell.success_rate, buy.success_rate)}|"
                    "sell_minus_buy_net_edge="
                    f"{_delta(sell.net_median, buy.net_median)}"
                )


def _same_sign(left: float | None, right: float | None) -> bool:
    """Перевірити однаковий ненульовий знак edge у двох periods."""

    return left is not None and right is not None and left * right > 0.0


def _above_50(left: float | None, right: float | None) -> bool:
    """Перевірити strict descriptive success above 50 у двох periods."""

    return left is not None and right is not None and left > 50.0 and right > 50.0


def _print_stability(results: dict[str, dict[int, CombinationResult]]) -> None:
    """Поставити 2025 і 2026 поруч для кожної same-direction class."""

    print("CROSS_PERIOD_STABILITY")
    for persistence in PERSISTENCES:
        for name in SAME_CLASSES:
            left = results["2025"][persistence].same_metrics[name]
            right = results["2026"][persistence].same_metrics[name]
            print(
                f"persistence=P{persistence}|class={name}|"
                f"2025_bars={left.events}|"
                f"2025_success_rate={_number(left.success_rate)}|"
                f"2025_net_edge={_number(left.net_median)}|"
                f"2025_sample_warning={_warning(left.events)}|"
                f"2026_bars={right.events}|"
                f"2026_success_rate={_number(right.success_rate)}|"
                f"2026_net_edge={_number(right.net_median)}|"
                f"2026_sample_warning={_warning(right.events)}|"
                "same_sign_edge_both_periods="
                f"{_same_sign(left.net_median, right.net_median)}|"
                "success_above_50_both_periods="
                f"{_above_50(left.success_rate, right.success_rate)}"
            )


def _print_unclassified(
    results: dict[str, dict[int, CombinationResult]],
) -> None:
    """Вивести NONE або exact unclassified tuple/count без нової semantics."""

    print("UNCLASSIFIED_STATES")
    found = False
    for period in PERIOD_CODES:
        for persistence in PERSISTENCES:
            unclassified = results[period][persistence].unclassified
            for state, count in sorted(unclassified.items()):
                found = True
                print(
                    f"period={period}|persistence=P{persistence}|"
                    f"state={state}|count={count}"
                )
    if not found:
        print("NONE")


def main() -> int:
    """Виконати T108-12 anatomy та перевірити scope/safety contracts."""

    before_hashes = PRODUCTION_HASHES()
    print("T108_12_SIGNED_FAMILY_COMBINATION_ANATOMY")
    replays: dict[str, Any] = {}
    results: dict[str, dict[int, CombinationResult]] = {}
    for spec in PERIODS:
        print(f"running_period={spec.code}", flush=True)
        replay = RUN_PERIOD(spec)
        replays[spec.code] = replay
        results[spec.code] = {
            persistence: _analyze(replay, persistence)
            for persistence in PERSISTENCES
        }
    assert tuple(results) == PERIOD_CODES
    assert PRODUCTION_HASHES() == before_hashes

    _print_coverage(results)
    _print_same(results)
    _print_conflicts(results)
    _print_pair_synergy(results)
    _print_full_consensus(results)
    _print_stochastic(results)
    _print_asymmetry(results)
    _print_stability(results)
    _print_unclassified(results)

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=COMPLETED_M15_EXACT_BASE_FAMILY_STATES")
    print("families=MACD_ALLIGATOR_STOCHASTIC")
    print("supertrend_included=False")
    print("family_normalization=True")
    print("max_one_vote_per_family=True")
    print("conflict_priority_used=False")
    print("weights_used=False")
    print("score_threshold_selected=False")
    print("best_persistence_selected=False")
    print("decision_bar_in_future_window=False")
    print("future_movement_role=OUTCOME_LABEL_ONLY")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("optimization_performed=False")
    print("threshold_sweep_performed=False")
    print("counterfactual_trades_simulated=False")
    print("next_bar_open_execution_simulated=False")
    print("sl_tp_pd_simulated=False")
    print("new_entry_rule_created=False")
    print("new_exit_rule_created=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={sum(item.broker_requests for item in replays.values())}")
    print(
        "broker_execution_attempted="
        f"{any(item.broker_execution_attempted for item in replays.values())}"
    )
    print("T108_12_SIGNED_FAMILY_COMBINATION_ANATOMY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
