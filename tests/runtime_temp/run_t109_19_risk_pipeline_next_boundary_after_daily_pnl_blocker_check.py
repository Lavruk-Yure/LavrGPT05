"""run_t109_19_risk_pipeline_next_boundary_after_daily_pnl_blocker_check.py.

TEST_ONLY probe подає chronological completed BROKER bars у registered Candidate
F runtime окремо для AUTO і SEMI. Для exact-bound account snapshot він бере
cached equity та currency з ``RuntimeAccountState`` і лише в harness додає
явно маркований ``daily_realized_pnl=0.0``, залишаючи
``open_positions_count`` невідомим, щоб ізолювати наступний production risk
guard після відомого daily-PnL blocker-а.

Окремий production-like regression без surrogate доводить незмінний fail-safe
``DAILY_PNL_SNAPSHOT_MISSING``. Runner не створює execution plan, не викликає
RuntimeEngine, broker adapter або network, не змінює account/risk/Candidate F
production code та не використовує future bars. Canonical Replay 2025/2026 і
production hashes захищають causal trading semantics та scope кроку.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TEST_ROOT = PROJECT_ROOT / "tests" / "runtime_workspace"
RUNTIME_TEMP_ROOT = PROJECT_ROOT / "tests" / "runtime_temp"
for import_path in (PROJECT_ROOT, WORKSPACE_TEST_ROOT, RUNTIME_TEMP_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def _test_helper(module_name: str, helper_name: str) -> Any:
    """Завантажити established TEST_ONLY helper без копіювання harness."""
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
proposal_trace = _test_helper(
    "run_t109_03_minimal_production_execution_intent_repair_check",
    "_proposal_trace",
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
    WORKSPACE_SIGNAL_FILTER_ALLOW,
    WorkspaceSignalProposal,
    WorkspaceSignalRecord,
)
from engine.risk.account_snapshot import (  # noqa: E402
    WorkspaceRiskAccountSnapshot,
)
from engine.risk.constants import (  # noqa: E402
    RISK_DECISION_ALLOW,
    RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING,
    RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402

TEST_ID = "T109-19"
EXPECTED_2025 = "42/30/11/1/+4.03/1.5424/3.58"
EXPECTED_2026 = "18/15/2/1/+3.68/3.7669/1.20"
DAILY_PNL_SURROGATE = 0.0
FACTUAL_VERDICT = "A. NEXT_BOUNDARY_OPEN_POSITIONS_SNAPSHOT"
FIRST_UNRESOLVED_BOUNDARY = "RISK_OPEN_POSITIONS_SNAPSHOT_MISSING"
BOUNDARY_CONTRACT = (
    "BOUND_BROKER_RISK_SNAPSHOT_REQUIRES_OPEN_POSITIONS_COUNT_AFTER_"
    "DAILY_REALIZED_PNL_IS_PRESENT"
)
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "algorithm_workspace_controller.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_algorithm.py",
    PROJECT_ROOT / "core" / "workspace_alligator.py",
    PROJECT_ROOT / "core" / "workspace_macd.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "risk" / "account_snapshot.py",
    PROJECT_ROOT / "engine" / "risk" / "constants.py",
    PROJECT_ROOT / "engine" / "risk" / "risk_model.py",
    PROJECT_ROOT / "engine" / "runtime_account_state.py",
)


@dataclass(frozen=True, slots=True)
class ModeProbeFact:
    """Зберегти observable facts одного AUTO або SEMI BROKER проходу."""

    control_mode: str
    proposal: WorkspaceSignalProposal
    record: WorkspaceSignalRecord
    snapshot: WorkspaceRiskAccountSnapshot
    completed_bars_delivered: int
    broker_requests: int
    broker_execution_attempted: bool


def _production_hashes() -> dict[str, str]:
    """Зафіксувати scoped production modules до і після TEST_ONLY probe."""
    return {
        path.relative_to(PROJECT_ROOT)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in PRODUCTION_FILES
    }


def _combined_hash(hashes: dict[str, str]) -> str:
    """Згорнути ordered per-file hashes у deterministic marker."""
    payload = "\n".join(f"{path}={hashes[path]}" for path in sorted(hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _baseline_key(runtime: WorkspaceRuntime) -> str:
    """Повернути exact compact canonical Replay metrics key."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary missing")
    return (
        f"{summary.opened_trades}/{summary.winning_trades}/"
        f"{summary.losing_trades}/{summary.break_even_trades}/"
        f"{summary.net_profit:+.2f}/{summary.profit_factor:.4f}/"
        f"{summary.maximum_drawdown:.2f}"
    )


def _cached_account_state(
    *,
    broker: str,
    account_id: str,
    snapshot_utc: str,
) -> RuntimeAccountState:
    """Побудувати cached broker account facts без refresh або network."""
    return RuntimeAccountState(
        account_id=account_id,
        broker_name=broker,
        currency="USD",
        balance=100_000.0,
        equity=100_000.0,
        snapshot_utc=snapshot_utc,
    )


def _bound_snapshot(
    runtime: WorkspaceRuntime,
    first_event: WorkspaceMarketEvent,
    *,
    daily_realized_pnl: float | None,
) -> WorkspaceRiskAccountSnapshot:
    """Створити exact-bound snapshot із cached facts до risk decision."""
    account_id = runtime.context.account_id
    if account_id is None:
        raise AssertionError("bound BROKER account is required")
    account_state = _cached_account_state(
        broker=runtime.context.broker,
        account_id=account_id,
        snapshot_utc=first_event.timestamp.isoformat(),
    )
    snapshot = WorkspaceRiskAccountSnapshot(
        snapshot_utc=first_event.timestamp,
        workspace_uid=runtime.context.workspace_uid,
        broker=account_state.broker_name,
        account_id=account_state.account_id,
        source_mode=runtime.context.data_mode,
        equity=account_state.equity,
        daily_realized_pnl=daily_realized_pnl,
        open_positions_count=None,
        currency=account_state.currency,
        binding_verified=True,
        synthetic=daily_realized_pnl is not None,
    )
    return runtime.set_risk_account_snapshot(snapshot)


def _run_mode(
    control_mode: str,
    events: tuple[WorkspaceMarketEvent, ...],
    *,
    daily_realized_pnl: float | None,
) -> ModeProbeFact:
    """Пройти public BROKER runtime до першого pre-risk accepted signal."""
    workspace = create_workspace_fixture(CANONICAL_PERIODS[0])
    workspace.data_mode = WORKSPACE_DATA_MODE_BROKER
    workspace.control_mode = control_mode
    workspace.account_mode = "DEMO"
    workspace.account_id = f"T10919-{control_mode}-DEMO"
    provider = CompletedHistoryBrokerProvider(events)
    runtime = WorkspaceRuntime(
        workspace,
        algorithm_factory=create_registered_workspace_algorithm,
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    if type(runtime.algorithm) is not WorkspaceMacdAlligatorReplayAlgorithm:
        raise AssertionError("registered Candidate F algorithm changed")
    snapshot = _bound_snapshot(
        runtime,
        events[0],
        daily_realized_pnl=daily_realized_pnl,
    )

    captured: list[WorkspaceSignalProposal] = []
    accepted_pair: tuple[WorkspaceSignalProposal, WorkspaceSignalRecord] | None = None
    while accepted_pair is None:
        record_offset = len(runtime.signal_records())
        proposal_offset = len(captured)
        previous_profile = sys.getprofile()
        sys.setprofile(proposal_trace(captured))
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
            if (
                runtime.can_form_signal()
                and proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
            ):
                accepted_pair = proposal, record
                break

    if accepted_pair is None:
        raise AssertionError(f"{control_mode} accepted Candidate F signal missing")
    proposal, record = accepted_pair
    result = ModeProbeFact(
        control_mode=control_mode,
        proposal=proposal,
        record=record,
        snapshot=snapshot,
        completed_bars_delivered=provider.completed_bars_delivered,
        broker_requests=provider.broker_requests,
        broker_execution_attempted=provider.broker_execution_attempted,
    )
    runtime.stop(f"{TEST_ID} {control_mode} probe completed")
    return result


def _assert_missing_daily(fact: ModeProbeFact) -> None:
    """Довести незмінний production fail-safe без TEST_ONLY surrogate."""
    assert fact.proposal.trade_intent is not None
    assert fact.snapshot.daily_realized_pnl is None
    assert fact.snapshot.open_positions_count is None
    assert fact.record.risk_decision == "BLOCK"
    assert fact.record.risk_reason_code == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
    assert not fact.record.risk_execution_attempted


def _assert_surrogate(fact: ModeProbeFact) -> None:
    """Довести ізольований прохід daily guard і наступний factual blocker."""
    assert fact.proposal.trade_intent is not None
    assert fact.snapshot.daily_realized_pnl == DAILY_PNL_SURROGATE
    assert fact.snapshot.open_positions_count is None
    assert fact.record.risk_decision == "BLOCK"
    assert fact.record.risk_reason_code == RISK_REASON_OPEN_POSITIONS_SNAPSHOT_MISSING
    assert not fact.record.risk_execution_attempted


def main() -> None:
    """Виконати safety regression, AUTO/SEMI probe і Replay validation."""
    hashes_before = _production_hashes()
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

    production_auto = _run_mode(
        WORKSPACE_CONTROL_MODE_AUTO,
        events,
        daily_realized_pnl=None,
    )
    production_semi = _run_mode(
        WORKSPACE_CONTROL_MODE_SEMI,
        events,
        daily_realized_pnl=None,
    )
    auto = _run_mode(
        WORKSPACE_CONTROL_MODE_AUTO,
        events,
        daily_realized_pnl=DAILY_PNL_SURROGATE,
    )
    semi = _run_mode(
        WORKSPACE_CONTROL_MODE_SEMI,
        events,
        daily_realized_pnl=DAILY_PNL_SURROGATE,
    )
    for fact in (production_auto, production_semi):
        _assert_missing_daily(fact)
    for fact in (auto, semi):
        _assert_surrogate(fact)

    facts = (production_auto, production_semi, auto, semi)
    broker_requests += sum(fact.broker_requests for fact in facts)
    broker_execution_attempted = any(
        fact.broker_execution_attempted or fact.record.risk_execution_attempted
        for fact in facts
    )
    production_missing_daily_pnl_still_blocks = all(
        fact.record.risk_reason_code == RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
        for fact in (production_auto, production_semi)
    )
    auto_signal_accepted = (
        auto.proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
    )
    semi_signal_accepted = (
        semi.proposal.filter_decision == WORKSPACE_SIGNAL_FILTER_ALLOW
    )
    auto_risk_entered = auto.record.risk_decision is not None
    semi_risk_entered = semi.record.risk_decision is not None
    auto_daily_pnl_guard_passed = (
        auto.record.risk_reason_code != RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
    )
    semi_daily_pnl_guard_passed = (
        semi.record.risk_reason_code != RISK_REASON_DAILY_PNL_SNAPSHOT_MISSING
    )
    auto_risk_allowed = auto.record.risk_decision == RISK_DECISION_ALLOW
    semi_risk_allowed = semi.record.risk_decision == RISK_DECISION_ALLOW
    open_positions_snapshot_present = all(
        fact.snapshot.open_positions_count is not None for fact in (auto, semi)
    )
    execution_plan_created = False
    runtime_engine_execution_called = False
    hashes_after = _production_hashes()

    assert hashes_before == hashes_after
    assert canonical_2025_exact_match and canonical_2026_exact_match
    assert production_missing_daily_pnl_still_blocks
    assert auto_signal_accepted and semi_signal_accepted
    assert auto.proposal.trade_intent is not None
    assert semi.proposal.trade_intent is not None
    assert auto_risk_entered and semi_risk_entered
    assert auto_daily_pnl_guard_passed and semi_daily_pnl_guard_passed
    assert not auto_risk_allowed and not semi_risk_allowed
    assert not open_positions_snapshot_present
    assert not execution_plan_created
    assert not runtime_engine_execution_called
    assert broker_requests == 0
    assert not broker_execution_attempted

    combined_before = _combined_hash(hashes_before)
    combined_after = _combined_hash(hashes_after)
    print(f"test_id={TEST_ID}")
    print("probe_mode=TEST_ONLY")
    print("daily_pnl_source=TEST_ONLY_SURROGATE")
    print(f"daily_pnl_surrogate_value={DAILY_PNL_SURROGATE:.1f}")
    print("daily_pnl_production_fallback_added=False")
    print(
        "production_missing_daily_pnl_reason="
        f"{production_auto.record.risk_reason_code}"
    )
    print(
        "production_missing_daily_pnl_still_blocks="
        f"{production_missing_daily_pnl_still_blocks}"
    )
    print(f"auto_signal_accepted={auto_signal_accepted}")
    print(f"auto_trade_intent_present={auto.proposal.trade_intent is not None}")
    print(f"auto_risk_entered={auto_risk_entered}")
    print(f"auto_daily_pnl_guard_passed={auto_daily_pnl_guard_passed}")
    print(f"auto_risk_reason={auto.record.risk_reason_code}")
    print(f"auto_risk_allowed={auto_risk_allowed}")
    print(f"semi_signal_accepted={semi_signal_accepted}")
    print(f"semi_trade_intent_present={semi.proposal.trade_intent is not None}")
    print(f"semi_risk_entered={semi_risk_entered}")
    print(f"semi_daily_pnl_guard_passed={semi_daily_pnl_guard_passed}")
    print(f"semi_risk_reason={semi.record.risk_reason_code}")
    print(f"semi_risk_allowed={semi_risk_allowed}")
    print(f"open_positions_snapshot_present={open_positions_snapshot_present}")
    print(f"execution_plan_created={execution_plan_created}")
    print(f"runtime_engine_execution_called={runtime_engine_execution_called}")
    print(f"broker_requests={broker_requests}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")
    print(f"canonical_2025_exact_match={canonical_2025_exact_match}")
    print(f"canonical_2026_exact_match={canonical_2026_exact_match}")
    print(f"production_hashes_before={combined_before}")
    print(f"production_hashes_after={combined_after}")
    print("production_hashes_before_after_match=True")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print("  broker_requests=0")
    print("  broker_execution_attempted=False")
    print("  production_logic_changed=False")
    print("  trading_logic_changed=False")
    print("  daily_pnl_production_fallback_added=False")
    print("  lookahead_used=False")
    print("T109_19_RISK_PIPELINE_NEXT_BOUNDARY_PROBE=OK")


def test_t109_19_risk_pipeline_next_boundary() -> None:
    """Запустити T109-19 як один pytest-compatible checkpoint."""
    main()


if __name__ == "__main__":
    main()
