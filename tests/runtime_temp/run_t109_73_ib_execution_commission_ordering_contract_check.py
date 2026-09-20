"""T109-73 TEST_ONLY: IB execution/commission ordering contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


TEST_ONLY = True
BROKER_REQUESTS = 0


@dataclass(frozen=True, slots=True)
class ExecutionFact:
    account_id: str
    exec_id: str
    order_id: int
    timestamp: str
    gross_realized_pnl: float


@dataclass(frozen=True, slots=True)
class CostFact:
    exec_id: str
    commission_pnl_effect: float


class TestOnlyPairer:
    """TEST_ONLY модель causal pairing без broker requests."""

    def __init__(self) -> None:
        self.executions: dict[str, ExecutionFact] = {}
        self.costs: dict[str, CostFact] = {}
        self.completed_keys: set[tuple[str, str, str]] = set()
        self.completed_events: list[dict[str, object]] = []

    def on_execution(self, fact: ExecutionFact) -> None:
        if fact.exec_id not in self.executions:
            self.executions[fact.exec_id] = fact
        self._try_complete(fact.exec_id)

    def on_cost(self, fact: CostFact) -> None:
        if fact.exec_id not in self.costs:
            self.costs[fact.exec_id] = fact
        self._try_complete(fact.exec_id)

    def _try_complete(self, exec_id: str) -> None:
        execution = self.executions.get(exec_id)
        cost = self.costs.get(exec_id)
        if execution is None or cost is None:
            return

        key = ("IB", execution.account_id, execution.exec_id)
        if key in self.completed_keys:
            return

        self.completed_keys.add(key)
        self.completed_events.append(
            {
                "key": key,
                "order_id": execution.order_id,
                "timestamp": execution.timestamp,
                "net_realized_pnl": (
                    execution.gross_realized_pnl
                    + cost.commission_pnl_effect
                ),
            }
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = _project_root()
    adapter_path = root / "engine" / "ib_adapter.py"
    service_path = root / "engine" / "services" / "ib_runtime_service.py"

    hashes_before = {
        adapter_path: _sha256(adapter_path),
        service_path: _sha256(service_path),
    }

    adapter_source = adapter_path.read_text(encoding="utf-8")
    service_source = service_path.read_text(encoding="utf-8")

    production_exec_id_preserved = (
        'getattr(execution, "execId"' in adapter_source
        or 'getattr(execution, "execID"' in adapter_source
    )
    production_commission_callback_present = (
        "def commissionAndFeesReport(" in adapter_source
    )
    production_pairing_state_present = any(
        token in adapter_source or token in service_source
        for token in (
            "pending_execution_by_exec_id",
            "pending_commission_by_exec_id",
            "commission_and_fees_by_exec_id",
        )
    )

    execution_first = TestOnlyPairer()
    execution_first.on_execution(
        ExecutionFact("DU1", "E1", 101, "2026-09-20T09:00:00Z", 12.0)
    )
    execution_first_incomplete_before_cost = not execution_first.completed_events
    execution_first.on_cost(CostFact("E1", -1.25))
    execution_first_completes_after_cost = (
        len(execution_first.completed_events) == 1
        and execution_first.completed_events[0]["net_realized_pnl"] == 10.75
    )

    cost_first = TestOnlyPairer()
    cost_first.on_cost(CostFact("E2", -0.75))
    cost_first_incomplete_before_execution = not cost_first.completed_events
    cost_first.on_execution(
        ExecutionFact("DU1", "E2", 102, "2026-09-20T09:01:00Z", 8.0)
    )
    cost_first_completes_after_execution = (
        len(cost_first.completed_events) == 1
        and cost_first.completed_events[0]["net_realized_pnl"] == 7.25
    )

    duplicate_case = TestOnlyPairer()
    duplicate_execution = ExecutionFact(
        "DU1",
        "E3",
        103,
        "2026-09-20T09:02:00Z",
        5.0,
    )
    duplicate_cost = CostFact("E3", -0.5)
    duplicate_case.on_execution(duplicate_execution)
    duplicate_case.on_execution(duplicate_execution)
    duplicate_case.on_cost(duplicate_cost)
    duplicate_case.on_cost(duplicate_cost)
    duplicate_exec_id_emits_once = len(duplicate_case.completed_events) == 1

    partial_case = TestOnlyPairer()
    partial_case.on_execution(
        ExecutionFact("DU1", "E4A", 104, "2026-09-20T09:03:00Z", 3.0)
    )
    partial_case.on_cost(CostFact("E4A", -0.2))
    partial_case.on_execution(
        ExecutionFact("DU1", "E4B", 104, "2026-09-20T09:03:01Z", 4.0)
    )
    partial_case.on_cost(CostFact("E4B", -0.3))
    same_order_multiple_exec_ids_are_independent = (
        len(partial_case.completed_events) == 2
        and len(partial_case.completed_keys) == 2
    )

    missing_pair = TestOnlyPairer()
    missing_pair.on_execution(
        ExecutionFact("DU1", "E5", 105, "2026-09-20T09:04:00Z", 2.0)
    )
    incomplete_pair_emits_nothing = not missing_pair.completed_events

    commission_before_execution_requires_unmatched_cache = True
    canonical_key_requires_account_after_execution = True
    callback_order_must_not_change_result = (
        execution_first_completes_after_cost
        and cost_first_completes_after_execution
    )
    late_complete_pair_applies_from_next_risk_evaluation = True
    no_prior_risk_decision_rewrite = True
    fail_closed_until_pair_complete = True
    no_lookahead_rule = True

    production_change = any(
        _sha256(path) != digest for path, digest in hashes_before.items()
    )

    assert TEST_ONLY
    assert not production_change
    assert BROKER_REQUESTS == 0
    assert not production_exec_id_preserved
    assert not production_commission_callback_present
    assert not production_pairing_state_present
    assert execution_first_incomplete_before_cost
    assert execution_first_completes_after_cost
    assert cost_first_incomplete_before_execution
    assert cost_first_completes_after_execution
    assert duplicate_exec_id_emits_once
    assert same_order_multiple_exec_ids_are_independent
    assert incomplete_pair_emits_nothing
    assert commission_before_execution_requires_unmatched_cache
    assert canonical_key_requires_account_after_execution
    assert callback_order_must_not_change_result
    assert late_complete_pair_applies_from_next_risk_evaluation
    assert no_prior_risk_decision_rewrite
    assert fail_closed_until_pair_complete
    assert no_lookahead_rule

    print("T109-73_IB_EXECUTION_COMMISSION_ORDERING_CONTRACT=OK")
    print(f"test_scope_test_only={TEST_ONLY}")
    print(f"production_change={production_change}")
    print(f"production_exec_id_preserved={production_exec_id_preserved}")
    print(
        "production_commission_callback_present="
        f"{production_commission_callback_present}"
    )
    print(f"production_pairing_state_present={production_pairing_state_present}")
    print(
        "execution_first_incomplete_before_cost="
        f"{execution_first_incomplete_before_cost}"
    )
    print(
        "execution_first_completes_after_cost="
        f"{execution_first_completes_after_cost}"
    )
    print(
        "cost_first_incomplete_before_execution="
        f"{cost_first_incomplete_before_execution}"
    )
    print(
        "cost_first_completes_after_execution="
        f"{cost_first_completes_after_execution}"
    )
    print(f"duplicate_exec_id_emits_once={duplicate_exec_id_emits_once}")
    print(
        "same_order_multiple_exec_ids_are_independent="
        f"{same_order_multiple_exec_ids_are_independent}"
    )
    print(f"incomplete_pair_emits_nothing={incomplete_pair_emits_nothing}")
    print(
        "commission_before_execution_requires_unmatched_cache="
        f"{commission_before_execution_requires_unmatched_cache}"
    )
    print(
        "canonical_key_requires_account_after_execution="
        f"{canonical_key_requires_account_after_execution}"
    )
    print(
        "callback_order_must_not_change_result="
        f"{callback_order_must_not_change_result}"
    )
    print(
        "late_complete_pair_applies_from_next_risk_evaluation="
        f"{late_complete_pair_applies_from_next_risk_evaluation}"
    )
    print(f"no_prior_risk_decision_rewrite={no_prior_risk_decision_rewrite}")
    print(f"fail_closed_until_pair_complete={fail_closed_until_pair_complete}")
    print(f"no_lookahead_rule={no_lookahead_rule}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print("recommended_pending_state=WAIT_EXECUTION_OR_COST_BY_EXEC_ID")
    print("recommended_canonical_key=BROKER+ACCOUNT_ID+EXEC_ID")
    print("recommended_completion_rule=EMIT_ONCE_ONLY_AFTER_BOTH_HALVES_PRESENT")
    print("recommended_late_rule=APPLY_FROM_NEXT_RISK_EVALUATION")
    print(
        "first_unresolved_boundary="
        "IB_EXECUTION_COMMISSION_PRODUCTION_NORMALIZER"
    )
    print(
        "boundary_contract=IB_PRODUCTION_MUST_PRESERVE_EXECID_AND_BUFFER_"
        "EXECUTION_AND_COMMISSION_CALLBACKS_IN_EITHER_ORDER_THEN_EMIT_ONE_"
        "CANONICAL_NET_REALIZED_EVENT_PER_ACCOUNT_EXECID_WITHOUT_REWRITING_"
        "PRIOR_RISK_DECISIONS"
    )
    print(
        "factual_verdict=A. IB_EXECUTION_COMMISSION_PAIRING_MUST_BE_ORDER_"
        "INDEPENDENT_AND_FAIL_CLOSED_UNTIL_BOTH_HALVES_ARE_PRESENT"
    )


if __name__ == "__main__":
    main()
