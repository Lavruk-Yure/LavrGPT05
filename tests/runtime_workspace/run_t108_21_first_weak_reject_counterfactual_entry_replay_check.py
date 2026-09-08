"""run_t108_21_first_weak_reject_counterfactual_entry_replay_check.py.

T108-21 є TEST_ONLY causal-precondition checkpoint для гіпотези додаткового
entry на першому factual ``MACD_EXTREMUM_TOO_WEAK`` reject у strong/missed
Alligator segment. Runner повторно запускає canonical T108-08/T108-20 Replay
для незалежних періодів 2025/2026, звіряє production baseline, повну weak
population та FIRST ordinal population.

До будь-якої counterfactual execution runner інспектує фактичний helper chain,
який утворює канонічну population. Strong/missed membership використовує весь
завершений segment, його майбутню ціну та factual trades на повній довжині,
тому на decision bar така membership недоступна. Відповідно runner навмисно
не створює orders/trades, не підміняє population іншим causal правилом і
завершується контрольованим ``CAUSAL_ENTRY_HYPOTHESIS_NOT_EXECUTABLE``.

Production entry/exit logic, thresholds, MD7 і broker path не змінюються.
Future segment data використовується лише для аудиту походження factual
population, а не як entry feature; completed-bar chronology та ordinal=1
окремо перевіряються як prior/current-only розрахунок.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

TEST_ID = "T108-21"
MODE = "RM108_T108_21_FIRST_WEAK_REJECT_COUNTERFACTUAL_ENTRY_REPLAY_TEST_ONLY"
HYPOTHESIS = "FIRST_WEAK_REJECT_ONLY"
SOURCE_SCRIPT = (
    "run_t108_20_macd_weak_reject_internal_temporal_geometry_anatomy_check.py"
)
PERIOD_CODES = ("2025", "2026")
EXPECTED_WEAK_COUNTS = {"2025": 136, "2026": 96}
EXPECTED_FIRST_COUNTS = {"2025": 74, "2026": 50}
EXPECTED_BASELINE_PREFIXES = {
    "2025": (
        "trades:42,wins:30,losses:11,break_even:1,"
        "net:+4.03,pf:1.5424,dd:3.58"
    ),
    "2026": (
        "trades:18,wins:15,losses:2,break_even:1,"
        "net:+3.68,pf:3.7669,dd:1.20"
    ),
}


def _load_source_module() -> ModuleType:
    """Завантажити GREEN T108-20 з exact retained workspace path."""

    file_path = TEST_ROOT / SOURCE_SCRIPT
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(
        "rm108_t108_21_source",
        file_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = _load_source_module()
PERIODS = getattr(SOURCE, "PERIODS")
RUN_WITH_RUNTIME: Callable[..., tuple[Any, Any]] = getattr(
    SOURCE,
    "RUN_WITH_RUNTIME",
)
BUILD_ROWS: Callable[..., tuple[Any, ...]] = getattr(SOURCE, "_rows")
PRODUCTION_HASHES: Callable[[], Any] = getattr(SOURCE, "PRODUCTION_HASHES")
BROKER_EXECUTION_ATTEMPTED: Callable[[Any], bool] = getattr(
    SOURCE,
    "BROKER_EXECUTION_ATTEMPTED",
)


def _causal_precondition() -> dict[str, bool]:
    """Довести з actual source походження population та ordinal."""

    t108_19 = getattr(SOURCE, "SOURCE")
    t108_08 = getattr(t108_19, "T108_08")
    missed_strong_segments = getattr(t108_08, "_missed_strong_segments")
    strong_move_r = missed_strong_segments.__globals__["_strong_move_r"]
    causal_cluster_values = getattr(SOURCE, "_causal_cluster_values")

    strong_source = inspect.getsource(strong_move_r)
    missed_source = inspect.getsource(missed_strong_segments)
    ordinal_source = inspect.getsource(causal_cluster_values)

    full_segment_observations_used = (
        "segment.observations" in strong_source
        and "segment_events" in strong_source
    )
    future_price_used = (
        "max(item.high for item in segment_events)" in strong_source
        and "min(item.low for item in segment_events)" in strong_source
    )
    strong_label_selects_population = (
        "_strong_move_r(segment, runtime.strategy_events)" in missed_source
        and "< STRONG_MOVE_R" in missed_source
    )
    full_segment_trade_coverage_used = (
        "trade_keys" in missed_source
        and "for item in segment.observations" in missed_source
    )
    ordinal_prior_current_only = all(
        token in ordinal_source
        for token in (
            "for row in sorted(source_rows",
            "prior = counts[segment_key]",
            "prior + 1",
            "counts[segment_key] += 1",
        )
    )
    assert full_segment_observations_used
    assert future_price_used
    assert strong_label_selects_population
    assert full_segment_trade_coverage_used
    assert ordinal_prior_current_only

    membership_causal = not (
        full_segment_observations_used
        or future_price_used
        or full_segment_trade_coverage_used
    )
    assert not membership_causal
    return {
        "strong_trend_segment_membership_causal_at_decision_time": (
            membership_causal
        ),
        "first_weak_reject_ordinal_prior_current_only": (
            ordinal_prior_current_only
        ),
        "eventual_segment_observations_used_by_population": (
            full_segment_observations_used
        ),
        "future_price_used_by_population": future_price_used,
        "full_segment_trade_coverage_used_by_population": (
            full_segment_trade_coverage_used
        ),
        "future_rejects_used_for_ordinal": False,
    }


def _print_causal_precondition(result: dict[str, bool]) -> None:
    """Надрукувати контрольований verdict causal executability."""

    print("CAUSAL_PRECONDITION")
    for name, value in result.items():
        print(f"{name}={value}")
    print("causal_entry_hypothesis_executable=False")
    print("CAUSAL_ENTRY_HYPOTHESIS_NOT_EXECUTABLE=True")


def _print_blocked_execution(period: str, candidate_events: int) -> None:
    """Показати нульову execution accounting без вигаданих trade metrics."""

    print(
        f"period={period}|candidate_events={candidate_events}|"
        "blocking_labels_evaluated=False|blocked_by_existing_position=0|"
        "blocked_by_pending_order=0|created_orders=0|"
        "completed_counterfactual_trades=0|"
        "session_end_cancelled_pending=0|"
        "execution_status=NOT_RUN_CAUSAL_PRECONDITION_FAILED"
    )
    print(
        f"period={period}|trades=0|wins=0|losses=0|break_even=0|"
        "win_rate=NONE|net=NONE|pf=NONE|max_dd=NONE|PD=0|SL=0|TP=0|"
        "SESSION_END=0|mean_realized_r=NONE|median_realized_r=NONE|"
        "metrics_status=NOT_RUN_CAUSAL_PRECONDITION_FAILED"
    )


def main() -> int:
    """Виконати causal gate, canonical reconciliation та safety assertions."""

    production_before = PRODUCTION_HASHES()
    precondition = _causal_precondition()
    _print_causal_precondition(precondition)

    broker_requests = 0
    execution_attempted = False
    print("POPULATION_RECONCILIATION")
    for spec in PERIODS:
        assert spec.code in PERIOD_CODES
        print(f"running_period={spec.code}", flush=True)
        result, runtime = RUN_WITH_RUNTIME(spec)
        rows = BUILD_ROWS(spec.code, result, runtime)
        weak_count = len(rows)
        first_count = sum(
            int(row.values["reject_ordinal"]) == 1 for row in rows
        )
        assert weak_count == EXPECTED_WEAK_COUNTS[spec.code]
        assert first_count == EXPECTED_FIRST_COUNTS[spec.code]
        assert result.baseline.startswith(
            EXPECTED_BASELINE_PREFIXES[spec.code]
        )
        broker_requests += result.broker_requests
        execution_attempted = (
            execution_attempted or BROKER_EXECUTION_ATTEMPTED(runtime)
        )
        print(
            f"period={spec.code}|factual_weak_reject_events={weak_count}|"
            f"expected={EXPECTED_WEAK_COUNTS[spec.code]}|reconciled=True"
        )
        print(
            f"period={spec.code}|reject_ordinal=1|"
            f"candidate_events={first_count}|"
            f"expected={EXPECTED_FIRST_COUNTS[spec.code]}|reconciled=True"
        )
        print(f"period={spec.code}|production_baseline={result.baseline}")
        _print_blocked_execution(spec.code, first_count)

    assert broker_requests == 0
    assert not execution_attempted
    assert PRODUCTION_HASHES() == production_before

    print("DECISION")
    print(
        "FIRST_WEAK_REJECT_ENTRY_HYPOTHESIS="
        "CAUSAL_ENTRY_HYPOTHESIS_NOT_EXECUTABLE"
    )
    print("production_approval=False")
    print("substitute_logic_created=False")

    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"hypothesis={HYPOTHESIS}")
    print("reject_ordinal_required=1")
    print("other_t108_20_features_used=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("classifier_created=False")
    print("generic_score_model_created=False")
    print("weights_used=False")
    print("counterfactual_trades_simulated=False")
    print("alternative_exit_simulated=False")
    print("canonical_exit_stack_preserved=True")
    print("next_bar_open=True")
    print("next_bar_open_execution_status=NOT_EXECUTED")
    print("completed_bars_only=True")
    print("lookahead_used=False")
    print("future_segment_information_used=False")
    print("future_segment_information_detected_in_population=True")
    print("new_production_entry_logic=False")
    print("new_production_exit_logic=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={execution_attempted}")
    print("T108_21_FIRST_WEAK_REJECT_COUNTERFACTUAL_ENTRY_REPLAY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
