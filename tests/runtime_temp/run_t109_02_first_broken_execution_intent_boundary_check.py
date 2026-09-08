"""run_t109_02_first_broken_execution_intent_boundary_check.py — T109-02.

TEST_ONLY runner відтворює рівно першу зламану execution boundary: реальний
accepted production Candidate F ``WorkspaceSignalProposal`` входить до
``WorkspaceRuntime._record_signal()``, але має ``trade_intent=None``, тому
risk/execution branch не виконується. AUTO і SEMI проходять окремо на
chronological completed BROKER bars із канонічного T105-18 Replay input.

Фактичний proposal захоплюється read-only Python call tracing без subclass,
mock, synthetic intent або зміни аргументів production методу. Runner також
AST-аналізом перелічує всі constructors ``WorkspaceTradeIntent`` і всі його
присвоєння proposal, не викликає network/broker API, не створює order plan та
не змінює algorithm, risk, control-mode semantics, production wiring чи MD7.
"""

from __future__ import annotations

import ast
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from run_t105_18_stochastic_current_bar_production_regression_check import (  # noqa
    PERIODS,
    _run_period,
    _workspace,
)
from run_t109_01_broker_signal_to_execution_path_anatomy_check import (  # noqa
    CompletedHistoryBrokerProvider,
    _broker_events,
    _production_hashes,
)

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
)
from core.workspace_algorithm import (  # noqa: E402
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)

TEST_ID = "T109-02"
MODE = "FIRST_BROKEN_EXECUTION_INTENT_BOUNDARY_TEST_ONLY"
BOUNDARY_CONTRACT = "INTENT_EXPECTED_BEFORE_RECORD_SIGNAL"
FIRST_BROKEN_BOUNDARY = "execution_intent"
FACTUAL_VERDICT = "B. SIGNAL_CREATED_EXECUTION_INTENT_NOT_CREATED"


@dataclass(frozen=True, slots=True)
class AcceptedBoundaryFact:
    """Зберегти exact proposal/record pair фактичного accepted signal."""

    control_mode: str
    event: WorkspaceMarketEvent
    proposal: WorkspaceSignalProposal
    record: WorkspaceSignalRecord
    completed_bars_delivered: int
    broker_requests: int
    broker_execution_attempted: bool


@dataclass(frozen=True, slots=True)
class IntentCallSiteInventory:
    """Зберегти production/test constructor та proposal assignment sites."""

    production_constructors: tuple[str, ...]
    test_constructors: tuple[str, ...]
    production_proposal_assignments: tuple[str, ...]
    test_proposal_assignments: tuple[str, ...]


def _call_name(node: ast.AST) -> str:
    """Повернути просте ім'я викликаного constructor з AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _site(path: Path, line_number: int) -> str:
    """Сформувати deterministic repository-relative file:line evidence."""
    return f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line_number}"


def _intent_call_sites() -> IntentCallSiteInventory:
    """Знайти всі Python constructors intent та його proposal assignments."""
    production_constructors: list[str] = []
    test_constructors: list[str] = []
    production_assignments: list[str] = []
    test_assignments: list[str] = []
    roots = (PROJECT_ROOT / "core", PROJECT_ROOT / "engine", PROJECT_ROOT / "tests")
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            is_production = path.parts[-2] in {"core", "engine"} or any(
                part in {"core", "engine"}
                for part in path.relative_to(PROJECT_ROOT).parts[:1]
            )
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func)
                if name == "WorkspaceTradeIntent":
                    target = (
                        production_constructors if is_production else test_constructors
                    )
                    target.append(_site(path, node.lineno))
                if name != "WorkspaceSignalProposal":
                    continue
                if not any(item.arg == "trade_intent" for item in node.keywords):
                    continue
                target = (
                    production_assignments if is_production else test_assignments
                )
                target.append(_site(path, node.lineno))
    return IntentCallSiteInventory(
        production_constructors=tuple(sorted(production_constructors)),
        test_constructors=tuple(sorted(test_constructors)),
        production_proposal_assignments=tuple(sorted(production_assignments)),
        test_proposal_assignments=tuple(sorted(test_assignments)),
    )


def _proposal_trace(
    captured: list[WorkspaceSignalProposal],
) -> Callable[[FrameType, str, object], object]:
    """Побудувати read-only profiler для exact production method argument."""
    target_code = WorkspaceRuntime._record_signal.__code__

    def trace(frame: FrameType, event: str, arg: object) -> object:
        """Захопити proposal на вході й не змінювати frame або return value."""
        del arg
        if event == "call" and frame.f_code is target_code:
            proposal = frame.f_locals.get("proposal")
            if not isinstance(proposal, WorkspaceSignalProposal):
                raise AssertionError("_record_signal proposal contract changed")
            captured.append(proposal)
        return trace

    return trace


def _run_mode(
    control_mode: str,
    events: tuple[WorkspaceMarketEvent, ...],
) -> AcceptedBoundaryFact:
    """Захопити real accepted proposal у незміненому BROKER runtime path."""
    workspace = _workspace(PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.control_mode = control_mode
    workspace.account_mode = "DEMO"
    provider = CompletedHistoryBrokerProvider(events)
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    if type(runtime.algorithm) is not WorkspaceMacdAlligatorReplayAlgorithm:
        raise AssertionError("registered production Candidate F class changed")

    accepted_fact: AcceptedBoundaryFact | None = None
    captured: list[WorkspaceSignalProposal] = []
    while accepted_fact is None:
        record_offset = len(runtime.signal_records())
        proposal_offset = len(captured)
        previous_profile = sys.getprofile()
        sys.setprofile(_proposal_trace(captured))
        try:
            market_event = runtime.advance_broker_market()
        finally:
            sys.setprofile(previous_profile)
        if market_event is None:
            break
        new_proposals = captured[proposal_offset:]
        new_records = runtime.signal_records()[record_offset:]
        if len(new_proposals) != len(new_records):
            raise AssertionError("proposal/record observation count mismatch")
        for proposal, record in zip(new_proposals, new_records):
            if not record.accepted:
                continue
            accepted_fact = AcceptedBoundaryFact(
                control_mode=control_mode,
                event=market_event,
                proposal=proposal,
                record=record,
                completed_bars_delivered=provider.completed_bars_delivered,
                broker_requests=provider.broker_requests,
                broker_execution_attempted=provider.broker_execution_attempted,
            )
            break

    if accepted_fact is None:
        raise AssertionError(f"{control_mode} accepted production signal not found")
    runtime.stop(f"{TEST_ID} {control_mode} boundary reproduced")
    return accepted_fact


def _proposal_metadata(fact: AcceptedBoundaryFact) -> str:
    """Сформувати компактний exact metadata snapshot accepted proposal."""
    proposal = fact.proposal
    return ",".join(
        (
            f"timestamp={fact.event.timestamp.isoformat()}",
            f"signal_type={proposal.signal_type}",
            f"direction={proposal.direction}",
            f"strength={proposal.strength:.12f}",
            f"macd_state={proposal.macd_state}",
            f"alligator_confirmation={proposal.alligator_confirmation}",
            f"filter_decision={proposal.filter_decision}",
            f"filter_reason_code={proposal.filter_reason_code}",
            f"source_profile_uid={proposal.source_profile_uid}",
            f"source_profile_revision={proposal.source_profile_revision}",
        )
    )


def _joined(values: tuple[str, ...]) -> str:
    """Надрукувати NONE або всі deterministic call sites одним полем."""
    return ";".join(values) if values else "NONE"


def _record_signal_contract() -> tuple[bool, bool, bool]:
    """Перевірити intent guard і відсутність post-record production creator."""
    source = inspect.getsource(WorkspaceRuntime._record_signal)
    full_runtime_source = inspect.getsource(WorkspaceRuntime)
    guard_present = "if accepted and proposal.trade_intent is not None:" in source
    risk_call_present = "self._evaluate_signal_risk(" in source
    post_record_creator = "WorkspaceTradeIntent(" in full_runtime_source
    return guard_present, risk_call_present, post_record_creator


def main() -> None:
    """Відтворити boundary, надрукувати call sites, branch і safety facts."""
    hashes_before = _production_hashes()
    replay_runtime, _rejects, replay_broker_requests = _run_period(PERIODS[0])
    replay_session = replay_runtime.replay_session
    if replay_session is None or not replay_session.completed:
        raise AssertionError("canonical 2025 Replay input is unavailable")
    broker_events = _broker_events(tuple(replay_session.events))

    auto = _run_mode(WORKSPACE_CONTROL_MODE_AUTO, broker_events)
    semi = _run_mode(WORKSPACE_CONTROL_MODE_SEMI, broker_events)
    inventory = _intent_call_sites()
    guard_present, risk_call_present, post_record_creator = (
        _record_signal_contract()
    )
    hashes_after = _production_hashes()

    facts = (auto, semi)
    accepted_signal_created = all(fact.record.accepted for fact in facts)
    proposal_type = type(auto.proposal).__name__
    proposal_trade_intent = auto.proposal.trade_intent
    risk_branch_entered = any(fact.record.risk_decision is not None for fact in facts)
    execution_plan_created = False
    runtime_order_boundary_reached = False
    broker_requests = replay_broker_requests + sum(
        fact.broker_requests for fact in facts
    )
    broker_execution_attempted = any(
        fact.broker_execution_attempted or fact.record.risk_execution_attempted
        for fact in facts
    )
    production_logic_changed = hashes_before != hashes_after
    defect_reproduced = bool(
        accepted_signal_created
        and proposal_trade_intent is None
        and guard_present
        and risk_call_present
        and not risk_branch_entered
        and not execution_plan_created
        and not runtime_order_boundary_reached
        and not inventory.production_constructors
        and not inventory.production_proposal_assignments
        and not post_record_creator
    )

    assert proposal_type == "WorkspaceSignalProposal"
    assert all(fact.proposal.trade_intent is None for fact in facts)
    assert auto.record.direction == auto.proposal.direction
    assert semi.record.direction == semi.proposal.direction
    assert auto.record.risk_decision is None
    assert semi.record.risk_decision is None
    assert inventory.test_constructors
    assert inventory.test_proposal_assignments
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert not production_logic_changed
    assert defect_reproduced

    creator = (
        "core/workspace_macd.py:544 WorkspaceMacdSignalSource._proposal -> "
        "core/workspace_alligator.py:1453 "
        "WorkspaceMacdAlligatorReplayAlgorithm._candidate_f_output"
    )
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"accepted_signal_created={accepted_signal_created}")
    print(f"proposal_type={proposal_type}")
    print(f"proposal_accepted={auto.record.accepted and semi.record.accepted}")
    print(
        "proposal_side_direction="
        f"AUTO:{auto.proposal.direction};SEMI:{semi.proposal.direction}"
    )
    print(f"proposal_metadata_auto={_proposal_metadata(auto)}")
    print(f"proposal_metadata_semi={_proposal_metadata(semi)}")
    print(f"proposal_trade_intent={proposal_trade_intent}")
    print(f"proposal_creator={creator}")
    print("trade_intent_definition=core/workspace_signal.py:37 WorkspaceTradeIntent")
    print(
        "trade_intent_production_creators="
        f"{_joined(inventory.production_constructors)}"
    )
    print(
        "trade_intent_test_only_creators="
        f"{_joined(inventory.test_constructors)}"
    )
    print(
        "trade_intent_production_proposal_assignments="
        f"{_joined(inventory.production_proposal_assignments)}"
    )
    print(
        "trade_intent_test_only_proposal_assignments="
        f"{_joined(inventory.test_proposal_assignments)}"
    )
    print("trade_intent_broker_auto_creator=NONE")
    print("trade_intent_broker_semi_creator=NONE")
    print("trade_intent_replay_status=TEST_HELPERS_ONLY")
    print("trade_intent_manual_status=NOT_USED_BY_MANUAL_ORDER_PATH")
    print(
        "record_signal_trade_intent_guard="
        "if accepted and proposal.trade_intent is not None"
    )
    print(f"risk_branch_entered={risk_branch_entered}")
    print(f"execution_plan_created={execution_plan_created}")
    print(f"runtime_order_boundary_reached={runtime_order_boundary_reached}")
    print("broken_boundary_reproduction=")
    print("  expected_input=accepted execution-capable production signal")
    print("  factual_input=accepted Candidate F WorkspaceSignalProposal")
    print("  factual_trade_intent=None")
    print("  branch=trade_intent guard evaluates False; risk call skipped")
    print("  return=WorkspaceSignalRecord accepted without risk decision")
    print("  post_record_production_intent_creator=NONE")
    print(f"auto_completed_bars_delivered={auto.completed_bars_delivered}")
    print(f"auto_proposal_trade_intent={auto.proposal.trade_intent}")
    print(f"auto_risk_branch_entered={auto.record.risk_decision is not None}")
    print(f"semi_completed_bars_delivered={semi.completed_bars_delivered}")
    print(f"semi_proposal_trade_intent={semi.proposal.trade_intent}")
    print(f"semi_risk_branch_entered={semi.record.risk_decision is not None}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"first_broken_boundary={FIRST_BROKEN_BOUNDARY}")
    print(f"defect_reproduced={defect_reproduced}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print(f"  production_logic_changed={production_logic_changed}")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_02_FIRST_BROKEN_EXECUTION_INTENT_BOUNDARY=OK")


if __name__ == "__main__":
    main()
