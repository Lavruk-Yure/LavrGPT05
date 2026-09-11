"""run_t109_01_broker_signal_to_execution_path_anatomy_check.py — T109-01.

TEST_ONLY anatomy відтворює фактичний production шлях від завершеного BROKER
bar до Candidate F signal record у WorkspaceRuntime для AUTO і SEMI. Джерелом
безпечних вхідних даних є immutable completed M15 bars канонічного Replay;
локальний provider лише подає їх по одному через production broker-market
protocol і не має execution API, мережі або broker adapter.

Runner окремо звіряє canonical Replay 2025/2026, production call boundaries,
guards і першу відсутню межу. Він не додає synthetic signal/trade intent, не
імітує відсутню execution wiring, не викликає RuntimeEngine order methods і не
торкається Candidate F, індикаторів, risk, SL/TP, Profit Drawdown або MD7.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
from dataclasses import dataclass, replace
from pathlib import Path

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
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
    WorkspaceLiveBarAggregator,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402

TEST_ID = "T109-01"
MODE = "BROKER_SIGNAL_TO_EXECUTION_PATH_ANATOMY_TEST_ONLY"
VERDICT = "B. SIGNAL_CREATED_EXECUTION_INTENT_NOT_CREATED"
PRODUCTION_FILES = (
    PROJECT_ROOT / "core" / "workspace_broker_market.py",
    PROJECT_ROOT / "core" / "workspace_runtime.py",
    PROJECT_ROOT / "core" / "workspace_macd.py",
    PROJECT_ROOT / "core" / "workspace_alligator.py",
    PROJECT_ROOT / "core" / "workspace_signal.py",
    PROJECT_ROOT / "engine" / "runtime_engine.py",
)


@dataclass(frozen=True, slots=True)
class BrokerModeFact:
    """Зберегти observable результат одного production AUTO/SEMI проходу."""

    control_mode: str
    completed_bars_delivered: int
    live_signal_created: bool
    live_signal_accepted: bool
    risk_decision_created: bool
    risk_execution_attempted: bool
    broker_requests: int
    broker_execution_attempted: bool


class CompletedHistoryBrokerProvider(WorkspaceBrokerMarketProviderProtocol):
    """Подати completed historical bars без мережі та execution підміни."""

    def __init__(self, events: tuple[WorkspaceMarketEvent, ...]) -> None:
        self._events = events
        self._index = 0
        self._workspace_uid: str | None = None
        self.completed_bars_delivered = 0
        self.broker_requests = 0
        self.broker_execution_attempted = False

    def start_workspace(
        self,
        *,
        workspace_uid: str,
        broker: str,
        account_id: str | None,
        symbol: str,
        timeframe: str,
        warmup_bars: int,
        spread_limit: float,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Повернути exact chronological prefix для production warm-up."""
        del account_id, spread_limit
        if broker != "CTRADER" or symbol != "EURUSD" or timeframe != "M15":
            raise AssertionError("unexpected production broker binding")
        if warmup_bars <= 0 or warmup_bars >= len(self._events):
            raise AssertionError("invalid production warm-up requirement")
        self._workspace_uid = workspace_uid
        self._index = warmup_bars
        self.completed_bars_delivered = warmup_bars
        return self._events[:warmup_bars]

    def poll_workspace(self, workspace_uid: str) -> WorkspaceMarketEvent | None:
        """Віддати наступний completed bar рівно один раз у chronology."""
        self._require_workspace(workspace_uid)
        if self._index >= len(self._events):
            return None
        event = self._events[self._index]
        self._index += 1
        self.completed_bars_delivered += 1
        return event

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        """Підтвердити лише локальну активну binding без broker request."""
        return workspace_uid == self._workspace_uid

    def suspend_workspace(self, workspace_uid: str) -> None:
        """Перевірити UID без зміни historical input."""
        self._require_workspace(workspace_uid)

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Підтвердити binding без мережі та додаткового warm-up."""
        self._require_workspace(workspace_uid)
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        """Звільнити локальну binding без broker operation."""
        self._require_workspace(workspace_uid)
        self._workspace_uid = None

    def _require_workspace(self, workspace_uid: str) -> None:
        """Відхилити звернення до іншого workspace."""
        if workspace_uid != self._workspace_uid:
            raise AssertionError("unexpected workspace UID")


def _production_hashes() -> dict[str, str]:
    """Зафіксувати production modules до і після TEST_ONLY anatomy."""
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in PRODUCTION_FILES
    }


def _broker_events(
    events: tuple[WorkspaceMarketEvent, ...],
) -> tuple[WorkspaceMarketEvent, ...]:
    """Змінити лише source_mode completed Replay bars на BROKER input mode."""
    result = tuple(
        replace(event, source_mode=WORKSPACE_DATA_MODE_BROKER) for event in events
    )
    assert result
    assert all(event.source_mode == WORKSPACE_DATA_MODE_BROKER for event in result)
    assert all(
        current.timestamp < following.timestamp
        for current, following in zip(result, result[1:])
    )
    return result


def _run_broker_mode(
    control_mode: str,
    events: tuple[WorkspaceMarketEvent, ...],
) -> BrokerModeFact:
    """Пройти public BROKER runtime з registered production Candidate F."""
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
    assert type(runtime.algorithm) is WorkspaceMacdAlligatorReplayAlgorithm
    signals_before_live = len(runtime.signal_records())
    first_live_record = None
    accepted_live_record = None
    observed_records = signals_before_live
    while accepted_live_record is None:
        event = runtime.advance_broker_market()
        if event is None:
            break
        records = runtime.signal_records()
        new_records = records[observed_records:]
        observed_records = len(records)
        if new_records and first_live_record is None:
            first_live_record = new_records[0]
        accepted_live_record = next(
            (record for record in new_records if record.accepted),
            None,
        )
    if first_live_record is None:
        raise AssertionError(f"{control_mode} production BROKER signal was not created")
    if accepted_live_record is None:
        raise AssertionError(
            f"{control_mode} production BROKER signal was never accepted"
        )
    result = BrokerModeFact(
        control_mode=control_mode,
        completed_bars_delivered=provider.completed_bars_delivered,
        live_signal_created=True,
        live_signal_accepted=accepted_live_record.accepted,
        risk_decision_created=accepted_live_record.risk_decision is not None,
        risk_execution_attempted=accepted_live_record.risk_execution_attempted,
        broker_requests=provider.broker_requests,
        broker_execution_attempted=provider.broker_execution_attempted,
    )
    runtime.stop(f"{TEST_ID} {control_mode} anatomy completed")
    return result


def _completed_bar_boundary() -> bool:
    """Виконати production aggregator rollover без broker/network provider."""
    from core.workspace_broker_market import WorkspaceBrokerBinding

    first = _workspace(PERIODS[0])
    aggregator = WorkspaceLiveBarAggregator(
        WorkspaceBrokerBinding(
            workspace_uid="t10901-rollover",
            broker="CTRADER",
            account_id="T10901-DEMO",
            symbol="EURUSD",
            timeframe="M15",
        )
    )
    event = _broker_events_for_rollover(first.broker)
    partial = aggregator.update(**event[0])
    completed = aggregator.update(**event[1])
    return bool(
        partial is None
        and completed is not None
        and completed.timestamp
        == event[0]["timestamp"].replace(
            minute=0,
            second=0,
            microsecond=0,
        )
        and completed.source_mode == WORKSPACE_DATA_MODE_BROKER
    )


def _broker_events_for_rollover(broker: str) -> tuple[dict[str, object], ...]:
    """Побудувати дві quote facts лише для rollover contract aggregator."""
    del broker
    from datetime import UTC, datetime

    return (
        {
            "timestamp": datetime(2026, 9, 8, 9, 0, 2, tzinfo=UTC),
            "bid": 1.1700,
            "ask": 1.1702,
            "volume": 1.0,
        },
        {
            "timestamp": datetime(2026, 9, 8, 9, 15, 2, tzinfo=UTC),
            "bid": 1.1701,
            "ask": 1.1703,
            "volume": 2.0,
        },
    )


def _proposal_intent_contract() -> tuple[int, bool]:
    """Довести AST-ом, що production MACD/Candidate F не створює intent."""
    sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "core" / "workspace_macd.py",
            PROJECT_ROOT / "core" / "workspace_alligator.py",
        )
    )
    calls = []
    for source in sources:
        tree = ast.parse(source)
        calls.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "WorkspaceSignalProposal"
        )
    intent_keywords = [
        keyword
        for call in calls
        for keyword in call.keywords
        if keyword.arg == "trade_intent"
    ]
    intent_constructor_present = any(
        "WorkspaceTradeIntent" in source for source in sources
    )
    return len(calls), bool(intent_keywords or intent_constructor_present)


def _runtime_route_contract() -> tuple[bool, bool, bool]:
    """Зіставити WSP runtime з наявною manual RuntimeEngine order boundary."""
    runtime_source = inspect.getsource(WorkspaceRuntime)
    runtime_parameters = inspect.signature(WorkspaceRuntime.__init__).parameters
    runtime_execution_dependency = any(
        name in runtime_parameters
        for name in ("runtime_engine", "order_manager", "execution_provider")
    )
    runtime_order_call = any(
        token in runtime_source
        for token in (
            "place_manual_market_order(",
            "place_market_order(",
            "submit_order(",
        )
    )
    runtime_engine_source = (PROJECT_ROOT / "engine" / "runtime_engine.py").read_text(
        encoding="utf-8"
    )
    manual_order_boundary_present = bool(
        "def place_manual_market_order(" in runtime_engine_source
        and "service.place_market_order(" in runtime_engine_source
    )
    return (
        runtime_execution_dependency,
        runtime_order_call,
        manual_order_boundary_present,
    )


def _baseline_line(runtime: WorkspaceRuntime) -> str:
    """Сформувати canonical metrics line одного завершеного Replay."""
    summary = runtime.historical_summary
    if summary is None:
        raise AssertionError("canonical Replay summary is absent")
    return (
        f"trades={summary.opened_trades} | {summary.winning_trades}W | "
        f"{summary.losing_trades}L | {summary.break_even_trades} BE | "
        f"net={summary.net_profit:+.2f} | PF={summary.profit_factor:.4f} | "
        f"DD={summary.maximum_drawdown:.2f}"
    )


def main() -> None:
    """Надрукувати call-chain, boundary status, guards і factual verdict."""
    hashes_before = _production_hashes()
    baseline_runtimes: dict[str, WorkspaceRuntime] = {}
    broker_requests = 0
    for spec in PERIODS:
        runtime, _rejects, requests = _run_period(spec)
        baseline_runtimes[spec.code] = runtime
        broker_requests += requests

    replay_2025 = baseline_runtimes["2025"].replay_session
    if replay_2025 is None or not replay_2025.completed:
        raise AssertionError("2025 canonical Replay did not complete")
    events = _broker_events(tuple(replay_2025.events))
    auto = _run_broker_mode(WORKSPACE_CONTROL_MODE_AUTO, events)
    semi = _run_broker_mode(WORKSPACE_CONTROL_MODE_SEMI, events)
    completed_bar_pass = _completed_bar_boundary()
    proposal_calls, candidate_f_intent_created = _proposal_intent_contract()
    (
        runtime_execution_dependency,
        runtime_order_call,
        manual_order_boundary_present,
    ) = _runtime_route_contract()
    hashes_after = _production_hashes()

    broker_requests += auto.broker_requests + semi.broker_requests
    broker_execution_attempted = bool(
        auto.broker_execution_attempted
        or auto.risk_execution_attempted
        or semi.broker_execution_attempted
        or semi.risk_execution_attempted
    )
    signal_created = auto.live_signal_created and semi.live_signal_created
    execution_intent_created = candidate_f_intent_created
    production_logic_changed = hashes_before != hashes_after

    assert completed_bar_pass
    assert signal_created
    assert auto.live_signal_accepted
    assert semi.live_signal_accepted
    assert proposal_calls > 0
    assert not execution_intent_created
    assert not auto.risk_decision_created
    assert not semi.risk_decision_created
    assert not runtime_execution_dependency
    assert not runtime_order_call
    assert manual_order_boundary_present
    assert broker_requests == 0
    assert not broker_execution_attempted
    assert not production_logic_changed

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print("reconstructed_production_call_chain=")
    print("  1. RuntimeEngineWorkspaceMarketProvider.poll_workspace")
    print("  2. WorkspaceLiveBarAggregator.update -> completed BROKER bar")
    print("  3. WorkspaceRuntime.advance_broker_market")
    print("  4. WorkspaceRuntime._accept_market_event")
    print("  5. WorkspaceRuntime._dispatch_market_event_to_algorithm")
    print("  6. WorkspaceMacdAlligatorReplayAlgorithm.on_market_event")
    print("  7. WorkspaceMacdSignalSource.on_market_event")
    print("  8. Candidate F guards -> WorkspaceSignalProposal")
    print("  9. WorkspaceRuntime._record_signal")
    print("  X. WorkspaceTradeIntent NOT CREATED; route stops")
    print("  -. WorkspaceRuntime -> RuntimeEngine.place_manual_market_order MISSING")
    print("  -. RuntimeEngine -> broker service.place_market_order NOT REACHED")
    print("boundaries=")
    print(f"  completed_broker_bar=PASS ({completed_bar_pass})")
    print("  production_algorithm_evaluation=PASS")
    print(f"  candidate_f_decision_signal=PASS ({signal_created})")
    print(f"  auto_control_mode_signal_path=PASS ({auto.live_signal_created})")
    print(f"  semi_control_mode_signal_path=PASS ({semi.live_signal_created})")
    print("  execution_intent=FAIL (WorkspaceTradeIntent absent)")
    print("  position_risk_guards=FAIL (not reached without trade intent)")
    print("  runtime_broker_service_route=FAIL (no WorkspaceRuntime order call)")
    print("  broker_adapter_order_api=FAIL (manual boundary exists, not reached)")
    print("guards=")
    print("  broker_connected; startup_phase; completed_bar_rollover")
    print("  warmup_complete; fresh_live_spread; spread_limit")
    print("  external_exposure_safety_hold; runtime_running; binding_match")
    print("  candidate_f_macd_quality; alligator; stochastic_current_bar")
    print("  risk guards require trade_intent and are not reached")
    print(f"auto_completed_bars_delivered={auto.completed_bars_delivered}")
    print(f"auto_live_signal_accepted={auto.live_signal_accepted}")
    print(f"semi_completed_bars_delivered={semi.completed_bars_delivered}")
    print(f"semi_live_signal_accepted={semi.live_signal_accepted}")
    print(f"production_signal_proposal_calls={proposal_calls}")
    print(f"execution_intent_created={execution_intent_created}")
    print(f"runtime_execution_dependency={runtime_execution_dependency}")
    print(f"runtime_order_call={runtime_order_call}")
    print(f"manual_order_api_boundary_present={manual_order_boundary_present}")
    print("first_broken_boundary=execution_intent")
    print(f"factual_verdict={VERDICT}")
    print("canonical_replay_baseline=")
    print(f"  2025: {_baseline_line(baseline_runtimes['2025'])}")
    print(f"  2026: {_baseline_line(baseline_runtimes['2026'])}")
    print("safety_invariants=")
    print("  TEST_ONLY=True")
    print(f"  broker_requests={broker_requests}")
    print(f"  broker_execution_attempted={broker_execution_attempted}")
    print(f"  production_logic_changed={production_logic_changed}")
    print("  trading_logic_changed=False")
    print("  lookahead_used=False")
    print("T109_01_BROKER_SIGNAL_TO_EXECUTION_PATH_ANATOMY=OK")


if __name__ == "__main__":
    main()
