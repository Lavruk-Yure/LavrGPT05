"""run_t108_23_weak_prominence_existing_distance_gate_counterfactual_entry_check.py.

T108-23 є TEST_ONLY counterfactual Replay однієї наперед визначеної causal
гіпотези: factual source-level ``MACD_EXTREMUM_TOO_WEAK`` reject допускається
лише коли його ``extremum_distance`` не менша за фактичний production minimum.
Runner читає threshold із production-configured source, підтверджує очікуване
0.0000500000 і не створює нового cutoff або normalized-distance signal.

Повна causal population та fixed H=8 descriptive labels повторно будуються
через GREEN T108-22. Pass/fail anatomy не впливає на execution. Distance-pass
events на completed M15 bar проходять штатний NEXT_BAR_OPEN Replay stack після
виключення factual production-position conflicts; counterfactual positions не
можуть hedge, reverse або дублювати одна одну.

Added-only trades використовують canonical SL=max(signal range, spread*10),
TP=2R, Profit Drawdown 35% і незмінний negative-PD recovery. Baseline не
змішується з counterfactual PnL. Runner не змінює production, thresholds, MD7,
entry/exit/reverse wiring і не звертається до broker.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean, median
from types import ModuleType
from typing import Any, Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = Path(__file__).resolve().parent
for import_path in (PROJECT_ROOT, TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntimeContext  # noqa: E402
from core.workspace_signal import WorkspaceSignalProposal  # noqa: E402

TEST_ID = "T108-23"
MODE = (
    "RM108_T108_23_WEAK_PROMINENCE_EXISTING_DISTANCE_GATE_"
    "COUNTERFACTUAL_ENTRY_TEST_ONLY"
)
SOURCE_SCRIPT = "run_t108_22_causal_weak_reject_population_rebuild_anatomy_check.py"
EXECUTION_SCRIPT = "run_t108_16_ms_buy_flat_counterfactual_entry_replay_check.py"
PERIOD_CODES = ("2025", "2026")
EXPECTED_POPULATIONS = {"2025": 1679, "2026": 1209}
EXPECTED_THRESHOLD = 0.00005
M15_DELTA = timedelta(minutes=15)
EPSILON = 1e-12


def _load_module(filename: str, name: str) -> ModuleType:
    """Завантажити retained GREEN runner з exact workspace path."""

    file_path = TEST_ROOT / filename
    assert file_path.is_file(), file_path
    spec = importlib.util.spec_from_file_location(name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = _load_module(SOURCE_SCRIPT, "rm108_t108_23_source")
EXECUTION = _load_module(EXECUTION_SCRIPT, "rm108_t108_23_execution")
PERIODS = getattr(SOURCE, "PERIODS")
RUN_WITH_RUNTIME: Callable[..., tuple[Any, Any]] = getattr(
    SOURCE,
    "RUN_WITH_RUNTIME",
)
BUILD_ROWS: Callable[[str, Any], tuple[Any, ...]] = getattr(SOURCE, "_rows")
THRESHOLDS: Callable[[Any], tuple[float, float]] = getattr(
    SOURCE,
    "THRESHOLDS",
)
PRODUCTION_HASHES: Callable[[], Any] = getattr(SOURCE, "PRODUCTION_HASHES")
BROKER_EXECUTION_ATTEMPTED: Callable[[Any], bool] = getattr(
    SOURCE,
    "BROKER_EXECUTION_ATTEMPTED",
)
BUILD_WORKSPACE: Callable[[Any], Any] = getattr(EXECUTION, "BUILD_WORKSPACE")
ASSERT_POLICY: Callable[[Any], None] = getattr(EXECUTION, "ASSERT_POLICY")
ASSERT_GEOMETRY: Callable[[Any], None] = getattr(EXECUTION, "ASSERT_GEOMETRY")
BASE_RUNTIME = getattr(EXECUTION, "BASE_RUNTIME")
BROKER_REQUEST_PROBE = getattr(EXECUTION, "BrokerRequestProbe")


@dataclass(frozen=True, slots=True)
class GateAnatomy:
    """Pass/fail/unavailable decomposition повної weak-reject population."""

    all_rows: tuple[Any, ...]
    passed: tuple[Any, ...]
    failed: tuple[Any, ...]
    unavailable: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class CandidateAudit:
    """Distance-pass candidates та causal production-position conflicts."""

    all_candidates: tuple[Any, ...]
    factual_position_blocked: tuple[Any, ...]
    executable: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class CounterfactualResult:
    """Added-only Replay, exact blocking decomposition та broker count."""

    period: str
    audit: CandidateAudit
    runtime: Any
    created_orders: int
    added_position_blocked: int
    pending_order_blocked: int
    session_end_cancelled_pending: int
    broker_requests: int


class DistanceGateCounterfactualAlgorithm(WorkspaceMacdAlligatorReplayAlgorithm):
    """Емітувати лише causal distance-pass proposals заданого напрямку."""

    def __init__(
        self,
        algorithm_id: str,
        candidates: Mapping[datetime, str],
    ) -> None:
        super().__init__(algorithm_id)
        self.candidates = dict(candidates)

    def configure(
        self,
        context: WorkspaceRuntimeContext,
        parameters: Mapping[str, Any],
    ) -> None:
        """Зберегти canonical production configuration та warm-up."""

        super().configure(context, parameters)

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        """Повернути proposal на completed candidate bar без інших ознак."""

        if not self.started:
            raise RuntimeError("Counterfactual algorithm is not started")
        direction = self.candidates.get(event.timestamp)
        if direction is None:
            return None
        return WorkspaceSignalProposal(
            signal_type="T108_23_WEAK_PROMINENCE_DISTANCE_GATE",
            direction=direction,
            strength=1.0,
            macd_state=direction,
            alligator_confirmation="TEST_ONLY_DISTANCE_GATE",
            reason=(
                "Factual weak-prominence reject passed existing production "
                "distance minimum."
            ),
        )


def _trades(runtime: Any) -> tuple[Any, ...]:
    """Прочитати immutable trade diagnostics завершеного Replay."""

    execution = runtime.replay_execution
    assert execution is not None
    return tuple(execution.trade_diagnostics())


def _gate_anatomy(rows: tuple[Any, ...], threshold: float) -> GateAnatomy:
    """Застосувати рівно один existing production distance gate."""

    passed: list[Any] = []
    failed: list[Any] = []
    unavailable: list[Any] = []
    for row in rows:
        distance = row.values.get("extremum_distance")
        normalized = row.values.get("normalized_distance")
        if distance is None:
            unavailable.append(row)
            continue
        assert normalized is not None
        gate_passed = float(distance) >= threshold
        assert gate_passed == (float(normalized) >= 1.0)
        if gate_passed:
            passed.append(row)
        else:
            failed.append(row)
    assert len(rows) == len(passed) + len(failed) + len(unavailable)
    return GateAnatomy(
        all_rows=rows,
        passed=tuple(passed),
        failed=tuple(failed),
        unavailable=tuple(unavailable),
    )


def _position_blocked(row: Any, trades: tuple[Any, ...]) -> bool:
    """Перевірити factual position або simultaneous entry на fill time."""

    decision_at = row.timestamp + M15_DELTA
    active = any(
        trade.entry_timestamp < decision_at <= trade.close_timestamp for trade in trades
    )
    simultaneous_entry = any(
        trade.signal_timestamp == row.timestamp and trade.entry_timestamp == decision_at
        for trade in trades
    )
    return active or simultaneous_entry


def _candidate_audit(anatomy: GateAnatomy, runtime: Any) -> CandidateAudit:
    """Відокремити factual production-position conflicts до CF Replay."""

    trades = _trades(runtime)
    blocked: list[Any] = []
    executable: list[Any] = []
    for row in anatomy.passed:
        target = blocked if _position_blocked(row, trades) else executable
        target.append(row)
    assert len(anatomy.passed) == len(blocked) + len(executable)
    return CandidateAudit(
        all_candidates=anatomy.passed,
        factual_position_blocked=tuple(blocked),
        executable=tuple(executable),
    )


def _counterfactual_workspace(spec: Any) -> Any:
    """Створити TEST_ONLY production workspace з one-position limit."""

    workspace = BUILD_WORKSPACE(spec)
    risk_settings: dict[str, Any] = dict(workspace.risk_settings)
    risk_settings["maximum_open_positions"] = 1
    workspace.risk_settings = risk_settings
    return workspace


def _created_order_timestamps(runtime: Any) -> frozenset[datetime]:
    """Прочитати signal timestamps із public immutable order snapshots."""

    execution = runtime.replay_execution
    assert execution is not None
    timestamps = {
        datetime.fromisoformat(order.created_at).astimezone(UTC)
        for order in execution.snapshot().orders
    }
    return frozenset(timestamps)


def _capacity_blocking(
    audit: CandidateAudit,
    runtime: Any,
) -> tuple[int, int]:
    """Розділити canonical capacity blocks на active та pending складові."""

    trades = _trades(runtime)
    created = _created_order_timestamps(runtime)
    added_position_blocked = 0
    pending_order_blocked = 0
    for row in audit.executable:
        timestamp = row.timestamp.astimezone(UTC)
        if timestamp in created:
            continue
        if _position_blocked(row, trades):
            added_position_blocked += 1
        else:
            pending_order_blocked += 1
    return added_position_blocked, pending_order_blocked


def _run_counterfactual(
    spec: Any,
    audit: CandidateAudit,
) -> CounterfactualResult:
    """Прогнати executable candidates через canonical added-only stack."""

    broker_probe = BROKER_REQUEST_PROBE()
    candidates = {row.timestamp: row.direction for row in audit.executable}
    assert len(candidates) == len(audit.executable)

    def algorithm_factory(
        algorithm_id: str,
    ) -> DistanceGateCounterfactualAlgorithm:
        """Створити один TEST_ONLY distance-gate algorithm."""

        return DistanceGateCounterfactualAlgorithm(algorithm_id, candidates)

    runtime = BASE_RUNTIME(
        _counterfactual_workspace(spec),
        algorithm_factory=algorithm_factory,
        broker_market_provider=broker_probe,
    )
    ASSERT_POLICY(runtime)
    runtime.begin_start()
    runtime.complete_start()
    session = runtime.replay_session
    assert session is not None
    while not session.completed:
        runtime.advance_replay()

    ASSERT_GEOMETRY(runtime)
    execution = runtime.replay_execution
    assert execution is not None
    assert execution.policy.maximum_open_positions == 1
    created = sum(entry.event == "VIRTUAL_ORDER_CREATED" for entry in runtime.journal)
    blocked = sum(entry.event == "VIRTUAL_ORDER_BLOCKED" for entry in runtime.journal)
    added_blocked, pending_blocked = _capacity_blocking(audit, runtime)
    assert blocked == added_blocked + pending_blocked
    assert created + blocked == len(audit.executable)
    cancelled = sum(
        order.status == "CANCELLED_SESSION_END" for order in execution.snapshot().orders
    )
    assert len(_trades(runtime)) + cancelled == created
    assert broker_probe.requests == 0
    assert not BROKER_EXECUTION_ATTEMPTED(runtime)
    return CounterfactualResult(
        period=spec.code,
        audit=audit,
        runtime=runtime,
        created_orders=created,
        added_position_blocked=added_blocked,
        pending_order_blocked=pending_blocked,
        session_end_cancelled_pending=cancelled,
        broker_requests=broker_probe.requests,
    )


def _optional(value: float | None) -> str:
    """Форматувати factual metric або NONE."""

    return "NONE" if value is None else f"{value:.4f}"


def _rate(count: int, total: int) -> str:
    """Форматувати percentage або NONE для empty labeled group."""

    return "NONE" if not total else f"{100.0 * count / total:.4f}"


def _anatomy_line(
    period: str,
    group: str,
    rows: tuple[Any, ...],
    total: int,
) -> str:
    """Сформувати pre-trade H=8 descriptive anatomy одного gate group."""

    labeled = tuple(row for row in rows if row.favorable_move_r is not None)
    moves = tuple(float(row.favorable_move_r) for row in labeled)
    reached_1r = sum(value + EPSILON >= 1.0 for value in moves)
    reached_2r = sum(value + EPSILON >= 2.0 for value in moves)
    percentage = 100.0 * len(rows) / total if total else 0.0
    median_move = median(moves) if moves else None
    return (
        f"period={period}|gate={group}|n={len(rows)}|"
        f"percentage={percentage:.4f}|h8_labeled_n={len(labeled)}|"
        f"reached_1r_rate={_rate(reached_1r, len(labeled))}|"
        f"reached_2r_rate={_rate(reached_2r, len(labeled))}|"
        f"median_favorable_move_r={_optional(median_move)}"
    )


def _profit_factor_text(value: float | None) -> str:
    """Форматувати PF без numeric sentinel."""

    return "NONE" if value is None else f"{value:.4f}"


def _realized_r(trade: Any) -> float:
    """Нормувати realized PnL на factual initial stop risk."""

    risk = trade.stop_loss_distance * trade.volume
    assert risk > 0.0
    return trade.final_profit / risk


def _print_counterfactual(result: CounterfactualResult) -> None:
    """Надрукувати required accounting та added-only trade metrics."""

    summary = result.runtime.historical_summary
    assert summary is not None
    trades = _trades(result.runtime)
    realized = tuple(_realized_r(trade) for trade in trades)
    reasons = Counter(trade.close_reason for trade in trades)
    factual_blocked = len(result.audit.factual_position_blocked)
    existing_blocked = factual_blocked + result.added_position_blocked
    print(
        f"period={result.period}|candidate_events="
        f"{len(result.audit.all_candidates)}|"
        f"blocked_by_factual_production_position={factual_blocked}|"
        f"blocked_by_added_counterfactual_position="
        f"{result.added_position_blocked}|"
        f"blocked_by_existing_position={existing_blocked}|"
        f"blocked_by_pending_order={result.pending_order_blocked}|"
        f"created_orders={result.created_orders}|"
        f"completed_counterfactual_trades={len(trades)}|"
        "session_end_cancelled_pending="
        f"{result.session_end_cancelled_pending}"
    )
    print(
        f"population_role=ADDED_ONLY_COUNTERFACTUAL_TRADES|"
        f"period={result.period}|trades={summary.opened_trades}|"
        f"wins={summary.winning_trades}|losses={summary.losing_trades}|"
        f"break_even={summary.break_even_trades}|"
        f"win_rate={_rate(summary.winning_trades, summary.opened_trades)}|"
        f"net={summary.net_profit:+.2f}|"
        f"profit_factor={_profit_factor_text(summary.profit_factor)}|"
        f"max_drawdown={summary.maximum_drawdown:.2f}|"
        f"PD={reasons['PROFIT_DRAWDOWN']}|SL={reasons['STOP_LOSS']}|"
        f"TP={reasons['TAKE_PROFIT']}|SESSION_END={reasons['SESSION_END']}|"
        f"mean_realized_r={_optional(fmean(realized) if realized else None)}|"
        "median_realized_r="
        f"{_optional(median(realized) if realized else None)}"
    )


def _supported(results: tuple[CounterfactualResult, ...]) -> bool:
    """Застосувати exact two-period hypothesis decision contract."""

    assert {result.period for result in results} == set(PERIOD_CODES)
    for result in results:
        summary = result.runtime.historical_summary
        assert summary is not None
        if summary.opened_trades <= 0 or summary.net_profit <= 0.0:
            return False
        if summary.profit_factor is None or summary.profit_factor <= 1.0:
            return False
    return True


def main() -> int:
    """Виконати threshold proof, anatomy, CF Replay та safety checks."""

    production_before = PRODUCTION_HASHES()
    baseline: dict[str, tuple[Any, GateAnatomy, CandidateAudit]] = {}
    results: list[CounterfactualResult] = []
    broker_requests = 0
    baseline_execution_attempted = False
    confirmed_thresholds: dict[str, float] = {}

    heading = "T108_23_WEAK_PROMINENCE_EXISTING_DISTANCE_GATE"
    print(f"{heading}_COUNTERFACTUAL_ENTRY")
    print("PRE_TRADE_ANATOMY")
    for spec in PERIODS:
        print(f"running_baseline_period={spec.code}", flush=True)
        baseline_result, runtime = RUN_WITH_RUNTIME(spec)
        _, threshold = THRESHOLDS(runtime)
        assert math.isclose(
            threshold,
            EXPECTED_THRESHOLD,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
        confirmed_thresholds[spec.code] = threshold
        rows = BUILD_ROWS(spec.code, runtime)
        assert len(rows) == EXPECTED_POPULATIONS[spec.code]
        anatomy = _gate_anatomy(rows, threshold)
        audit = _candidate_audit(anatomy, runtime)
        baseline[spec.code] = (runtime, anatomy, audit)
        broker_requests += baseline_result.broker_requests
        baseline_execution_attempted = (
            baseline_execution_attempted or BROKER_EXECUTION_ATTEMPTED(runtime)
        )
        print(
            f"period={spec.code}|production_minimum_distance="
            f"{threshold:.10f}|threshold_confirmed=True|"
            "threshold_source=ACTUAL_CONFIGURED_PRODUCTION_SOURCE"
        )
        print(
            f"period={spec.code}|all_weak_rejects={len(anatomy.all_rows)}|"
            f"distance_gate_pass={len(anatomy.passed)}|"
            f"distance_gate_fail={len(anatomy.failed)}|"
            f"distance_unavailable={len(anatomy.unavailable)}|"
            "reconciled=True"
        )
        print(_anatomy_line(spec.code, "PASS", anatomy.passed, len(rows)))
        print(_anatomy_line(spec.code, "FAIL", anatomy.failed, len(rows)))
        print(
            f"population=CANONICAL_PRODUCTION_BASELINE|period={spec.code}|"
            f"{baseline_result.baseline.replace(',', '|').replace(':', '=')}"
        )

    assert set(confirmed_thresholds.values()) == {EXPECTED_THRESHOLD}
    for spec in PERIODS:
        _, _, audit = baseline[spec.code]
        print(f"running_counterfactual_period={spec.code}", flush=True)
        result = _run_counterfactual(spec, audit)
        results.append(result)
        broker_requests += result.broker_requests
        _print_counterfactual(result)

    result_tuple = tuple(results)
    assert len(result_tuple) == len(PERIOD_CODES)
    assert PRODUCTION_HASHES() == production_before
    decision = (
        "SUPPORTED_FOR_FURTHER_RESEARCH"
        if _supported(result_tuple)
        else "REJECTED_AS_ADDED_ENTRY_HYPOTHESIS"
    )
    print("DECISION")
    print(f"DISTANCE_GATE_HYPOTHESIS={decision}")
    print("production_approval=False")
    print("baseline_counterfactual_pnl_mechanically_summed=False")

    counterfactual_execution_attempted = any(
        BROKER_EXECUTION_ATTEMPTED(result.runtime) for result in result_tuple
    )
    execution_attempted = (
        baseline_execution_attempted or counterfactual_execution_attempted
    )
    print("SAFETY")
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("population=all_factual_weak_reject_events")
    print("population_causal_at_decision_time=True")
    print("distance_threshold_source=EXISTING_PRODUCTION_MINIMUM_DISTANCE")
    print("normalized_distance_role=RECONCILIATION_ONLY")
    print("new_threshold_created=False")
    print("threshold_sweep_performed=False")
    print("optimization_performed=False")
    print("other_t108_22_features_used=False")
    print("completed_bars_only=True")
    print("next_bar_open=True")
    print("lookahead_used=False")
    print("future_segment_information_used=False")
    print("counterfactual_trades_simulated=True")
    print("canonical_exit_stack_preserved=True")
    print("new_production_entry_logic=False")
    print("new_production_exit_logic=False")
    print("reverse_logic_created=False")
    print("production_logic_changed=False")
    print("production_threshold_changed=False")
    print("md7_changed=False")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={execution_attempted}")
    assert broker_requests == 0
    assert not execution_attempted
    marker = "T108_23_WEAK_PROMINENCE_EXISTING_DISTANCE_GATE"
    print(f"{marker}_COUNTERFACTUAL_ENTRY=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
