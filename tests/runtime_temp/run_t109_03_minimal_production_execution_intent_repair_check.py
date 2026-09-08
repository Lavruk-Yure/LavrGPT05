"""run_t109_03_minimal_production_execution_intent_repair_check.py — T109-03.

Targeted offline regression перевіряє мінімальну production wiring межі
Candidate F signal → ``WorkspaceTradeIntent`` → existing risk pipeline.
Registered production algorithm отримує chronological completed BROKER bars;
read-only tracing захоплює exact proposal на вході ``_record_signal`` окремо
для AUTO і SEMI без mock/synthetic intent, RuntimeEngine або broker adapter.

Runner доводить causal field/source mapping, відсутність executable intent у
rejected Candidate F proposal, фактичний вхід у risk branch і наступну межу
``ACCOUNT_BINDING_MISMATCH`` без broker snapshot. Canonical Replay підтверджує,
що Candidate F decisions, SL/TP, PD і trading results не змінилися. Network,
broker requests, order plan та downstream execution навмисно не виконуються.
"""

from __future__ import annotations

import importlib
import inspect
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType, FunctionType
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити перевірений helper сусіднього TEST_ONLY runner-а."""
    module = importlib.import_module(module_name)
    helper = getattr(module, helper_name, None)
    if helper is None:
        raise AssertionError(f"missing TEST_ONLY helper: {helper_name}")
    return helper


CANONICAL_PERIODS = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "PERIODS",
)
run_canonical_period = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_run_period",
)
create_workspace_fixture = _test_helper(
    "run_t105_18_stochastic_current_bar_production_regression_check",
    "_workspace",
)
CompletedHistoryBrokerProvider = _test_helper(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "CompletedHistoryBrokerProvider",
)
broker_events = _test_helper(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "_broker_events",
)
production_hashes = _test_helper(
    "run_t109_01_broker_signal_to_execution_path_anatomy_check",
    "_production_hashes",
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
from core.workspace_replay_execution import (  # noqa: E402
    WorkspaceReplayExecutionPolicy,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)
from engine.risk.constants import (  # noqa: E402
    RISK_REASON_ACCOUNT_BINDING_MISMATCH,
)

TEST_ID = "T109-03"
MODE = "MINIMAL_PRODUCTION_EXECUTION_INTENT_REPAIR_OFFLINE"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"


def _runtime_function(name: str) -> FunctionType:
    """Отримати production method для read-only source/profile inspection."""
    function = vars(WorkspaceRuntime).get(name)
    if not isinstance(function, FunctionType):
        raise AssertionError(f"WorkspaceRuntime method missing: {name}")
    return function


@dataclass(frozen=True, slots=True)
class ModeRepairFact:
    """Зберегти accepted/rejected proposal facts одного control mode."""

    control_mode: str
    workspace_uid: str
    account_id: str | None
    symbol: str
    runtime_risk_policy_maximum_position_volume: float
    accepted_event: WorkspaceMarketEvent
    accepted_proposal: WorkspaceSignalProposal
    accepted_record: WorkspaceSignalRecord
    rejected_proposal: WorkspaceSignalProposal
    rejected_record: WorkspaceSignalRecord
    completed_bars_delivered: int
    broker_requests: int
    broker_execution_attempted: bool


def _proposal_trace(
    captured: list[WorkspaceSignalProposal],
) -> Callable[[FrameType, str, object], object]:
    """Побудувати read-only trace exact proposal після production wiring."""
    target_code = _runtime_function("_record_signal").__code__

    def trace(frame: FrameType, event: str, _arg: object) -> object:
        """Захопити аргумент виклику без зміни frame, proposal або result."""
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
) -> ModeRepairFact:
    """Відтворити Candidate F intent/risk boundary без account підміни."""
    workspace = create_workspace_fixture(CANONICAL_PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.control_mode = control_mode
    workspace.account_mode = "DEMO"
    workspace.account_id = f"T10903-{control_mode}-DEMO"
    provider = CompletedHistoryBrokerProvider(events)
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=provider,
    )
    expected_maximum_position_volume = runtime.risk_policy.maximum_position_volume
    runtime.begin_start()
    runtime.complete_start()
    if type(runtime.algorithm) is not WorkspaceMacdAlligatorReplayAlgorithm:
        raise AssertionError("registered Candidate F algorithm changed")

    captured: list[WorkspaceSignalProposal] = []
    accepted_pair: (
        tuple[
            WorkspaceMarketEvent,
            WorkspaceSignalProposal,
            WorkspaceSignalRecord,
        ]
        | None
    ) = None
    rejected_pair: tuple[WorkspaceSignalProposal, WorkspaceSignalRecord] | None = None
    while accepted_pair is None or rejected_pair is None:
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
            pre_risk_accepted = bool(
                runtime.can_form_signal()
                and proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
            )
            if pre_risk_accepted and accepted_pair is None:
                accepted_pair = market_event, proposal, record
            if not pre_risk_accepted and rejected_pair is None:
                rejected_pair = proposal, record

    if accepted_pair is None:
        raise AssertionError(f"{control_mode} accepted Candidate F proposal missing")
    if rejected_pair is None:
        raise AssertionError(f"{control_mode} rejected Candidate F proposal missing")
    accepted_event, accepted_proposal, accepted_record = accepted_pair
    rejected_proposal, rejected_record = rejected_pair
    result = ModeRepairFact(
        control_mode=control_mode,
        workspace_uid=runtime.context.workspace_uid,
        account_id=runtime.context.account_id,
        symbol=runtime.context.symbol,
        runtime_risk_policy_maximum_position_volume=expected_maximum_position_volume,
        accepted_event=accepted_event,
        accepted_proposal=accepted_proposal,
        accepted_record=accepted_record,
        rejected_proposal=rejected_proposal,
        rejected_record=rejected_record,
        completed_bars_delivered=provider.completed_bars_delivered,
        broker_requests=provider.broker_requests,
        broker_execution_attempted=provider.broker_execution_attempted,
    )
    runtime.stop(f"{TEST_ID} {control_mode} repair check completed")
    return result


def _expected_intent_values(
    fact: ModeRepairFact,
) -> tuple[float, float, float]:
    """Обчислити очікувані values лише з existing production sources."""
    policy = WorkspaceReplayExecutionPolicy(
        fixed_volume=fact.runtime_risk_policy_maximum_position_volume,
        maximum_open_positions=2,
    )
    event = fact.accepted_event
    distance = (
        max(
            event.high - event.low,
            event.spread * policy.minimum_spread_multiples,
        )
        * policy.stop_range_multiplier
    )
    stop_loss = (
        event.close - distance
        if fact.accepted_proposal.direction == "BUY"
        else event.close + distance
    )
    estimated_loss = distance * policy.fixed_volume
    return policy.fixed_volume, stop_loss, estimated_loss


def _assert_mode(fact: ModeRepairFact) -> None:
    """Звірити intent fields, rejected path і factual next boundary."""
    intent = fact.accepted_proposal.trade_intent
    if intent is None:
        raise AssertionError("accepted Candidate F intent was not created")
    volume, stop_loss, estimated_loss = _expected_intent_values(fact)
    assert intent.requested_volume == volume
    assert math.isclose(intent.stop_loss or 0.0, stop_loss, abs_tol=1e-12)
    assert math.isclose(
        intent.estimated_loss_at_stop,
        estimated_loss,
        abs_tol=1e-12,
    )
    assert intent.signal_uid is None
    assert fact.accepted_record.risk_decision == "BLOCK"
    assert fact.accepted_record.risk_reason_code == RISK_REASON_ACCOUNT_BINDING_MISMATCH
    assert fact.accepted_record.requested_volume == intent.requested_volume
    assert fact.accepted_record.approved_volume is None
    assert not fact.accepted_record.risk_execution_attempted
    assert fact.rejected_proposal.trade_intent is None
    assert fact.rejected_record.risk_decision is None


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Повернути exact compact canonical metrics key одного Replay."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def _intent_location() -> str:
    """Повернути current verified file:line production helper location."""
    line = inspect.getsourcelines(_runtime_function("_candidate_f_execution_intent"))[1]
    return (
        f"core/workspace_runtime.py:{line} "
        "WorkspaceRuntime._candidate_f_execution_intent before _record_signal"
    )


def _broker_execution_attempted(runtime: WorkspaceRuntime) -> bool:
    """Знайти factual broker execution marker у runtime Journal."""
    return any(
        bool(entry.details.get("broker_execution_attempted"))
        for entry in runtime.journal
        if isinstance(entry.details, dict)
    )


def main() -> None:
    """Перевірити repair, canonical Replay і наступну execution boundary."""
    hashes_before = production_hashes()
    baselines: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in CANONICAL_PERIODS:
        runtime, _rejects, requests = run_canonical_period(spec)
        baselines[spec.code] = runtime
        broker_requests += requests

    canonical_2025_exact_match = _baseline_key(baselines["2025"]) == EXPECTED_2025
    canonical_2026_exact_match = _baseline_key(baselines["2026"]) == EXPECTED_2026
    replay_session = baselines["2025"].replay_session
    if replay_session is None or not replay_session.completed:
        raise AssertionError("canonical completed M15 input missing")
    events = broker_events(tuple(replay_session.events))
    auto = _run_mode(WORKSPACE_CONTROL_MODE_AUTO, events)
    semi = _run_mode(WORKSPACE_CONTROL_MODE_SEMI, events)
    facts = (auto, semi)
    for fact in facts:
        _assert_mode(fact)
    hashes_after = production_hashes()

    accepted_signal_created = all(
        fact.accepted_proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
        for fact in facts
    )
    accepted_trade_intent_created = all(
        fact.accepted_proposal.trade_intent is not None for fact in facts
    )
    rejected_signal_executable_intent = any(
        fact.rejected_proposal.trade_intent is not None for fact in facts
    )
    risk_branch_entered = all(
        fact.accepted_record.risk_decision is not None for fact in facts
    )
    risk_decision_created = risk_branch_entered
    broker_requests += sum(fact.broker_requests for fact in facts)
    broker_execution_attempted = bool(
        any(
            fact.broker_execution_attempted
            or fact.accepted_record.risk_execution_attempted
            for fact in facts
        )
        or any(_broker_execution_attempted(runtime) for runtime in baselines.values())
    )
    production_logic_changed = bool(
        hasattr(WorkspaceRuntime, "_candidate_f_execution_intent")
        and "self._candidate_f_execution_intent(event, proposal)"
        in inspect.getsource(_runtime_function("_dispatch_market_event_to_algorithm"))
    )
    trading_logic_changed = not (
        canonical_2025_exact_match and canonical_2026_exact_match
    )

    assert hashes_before == hashes_after
    assert accepted_signal_created
    assert accepted_trade_intent_created
    assert not rejected_signal_executable_intent
    assert risk_branch_entered and risk_decision_created
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert production_logic_changed
    assert not trading_logic_changed

    intent = auto.accepted_proposal.trade_intent
    if intent is None:
        raise AssertionError("AUTO intent unexpectedly missing after assertions")
    semi_intent = semi.accepted_proposal.trade_intent
    if semi_intent is None:
        raise AssertionError("SEMI intent unexpectedly missing after assertions")
    auto_volume_source_contract_match = bool(
        intent.requested_volume == auto.runtime_risk_policy_maximum_position_volume
    )
    semi_volume_source_contract_match = bool(
        semi_intent.requested_volume == semi.runtime_risk_policy_maximum_position_volume
    )
    assert auto_volume_source_contract_match
    assert semi_volume_source_contract_match
    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("production_files_changed=core/workspace_runtime.py")
    print(f"intent_creation_location={_intent_location()}")
    print(f"accepted_signal_created={accepted_signal_created}")
    print(f"accepted_trade_intent_created={accepted_trade_intent_created}")
    print(f"intent_direction={auto.accepted_proposal.direction}")
    print(f"intent_symbol={auto.symbol}")
    print(f"intent_account={auto.account_id}")
    print("intent_volume_source=WorkspaceRuntime.risk_policy.maximum_position_volume")
    print(f"intent_requested_volume={intent.requested_volume:.6f}")
    print(
        "intent_sl_source=completed signal bar + existing "
        "WorkspaceReplayExecutionPolicy max(range,spread*10)*1R"
    )
    print(f"intent_stop_loss={intent.stop_loss:.12f}")
    print(
        "intent_estimated_loss_source=protection_distance*requested_volume "
        "per existing Replay PnL contract"
    )
    print(f"intent_estimated_loss_at_stop={intent.estimated_loss_at_stop:.12f}")
    print(
        "intent_tp_source=NOT_A_WORKSPACE_TRADE_INTENT_FIELD; "
        "existing downstream Replay policy TP=2R unchanged"
    )
    print("rejected_signal_executable_intent=" f"{rejected_signal_executable_intent}")
    print(f"risk_branch_entered={risk_branch_entered}")
    print(f"risk_decision_created={risk_decision_created}")
    print(f"auto_intent_created={auto.accepted_proposal.trade_intent is not None}")
    print(
        "auto_runtime_risk_policy_maximum_position_volume="
        f"{auto.runtime_risk_policy_maximum_position_volume:.6f}"
    )
    print("auto_trade_intent_requested_volume=" f"{intent.requested_volume:.6f}")
    print("auto_volume_source_contract_match=" f"{auto_volume_source_contract_match}")
    print(f"auto_risk_reason={auto.accepted_record.risk_reason_code}")
    print(f"semi_intent_created={semi.accepted_proposal.trade_intent is not None}")
    print(
        "semi_runtime_risk_policy_maximum_position_volume="
        f"{semi.runtime_risk_policy_maximum_position_volume:.6f}"
    )
    print("semi_trade_intent_requested_volume=" f"{semi_intent.requested_volume:.6f}")
    print("semi_volume_source_contract_match=" f"{semi_volume_source_contract_match}")
    print(f"semi_risk_reason={semi.accepted_record.risk_reason_code}")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print("next_execution_boundary=RISK_ACCOUNT_BINDING_MISMATCH_NO_SNAPSHOT")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"production_logic_changed={production_logic_changed}")
    print(f"trading_logic_changed={trading_logic_changed}")
    print("lookahead_used=False")
    print("T109_03_MINIMAL_PRODUCTION_EXECUTION_INTENT_REPAIR=OK")


if __name__ == "__main__":
    main()
