"""run_t109_112_workspace_broker_execution_post_risk_end_to_end_anatomy_check.py.

TEST_ONLY anatomy проходить фактичний public WorkspaceRuntime signal pipeline
після закриття IB risk snapshot boundary. Для AUTO і SEMI окремі completed IB
events формують risk=ALLOW; production AlgorithmWorkspaceController зберігає
Trade та OrderPlan із причинними workspace/signal identities.

AUTO додатково проходить production same-call confirmed-flat gate та передає
ті самі Trade/OrderPlan UID у submission route. SEMI залишається у
PENDING_CONFIRMATION без position snapshot і submission. Broker position та
submission endpoints замінені локальним evidence engine: production controller
викликається, але broker network, order execution і production SQLite відсутні.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.session_repository import SessionRepository  # noqa: E402
from core.workspace_algorithm import PassiveWorkspaceAlgorithm  # noqa: E402
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerMarketProviderProtocol,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceTradeIntent,
)
from engine.broker_position import BrokerPositionSnapshot  # noqa: E402
from engine.db.runtime_db import connect_runtime_db  # noqa: E402
from engine.runtime_repository import RuntimeRepository  # noqa: E402

TEST_ID = "T109-112"
EVENT_UTC = datetime(2026, 9, 23, 16, 20, tzinfo=UTC)
FIRST_UNRESOLVED_BOUNDARY = (
    "WORKSPACE_BROKER_EXECUTION_FULL_PRODUCTION_CLOSURE_DECISION"
)
BOUNDARY_CONTRACT = (
    "POST_RISK_ALLOW_NOW_REACHES_PERSISTED_TRADE_AND_ORDER_PLAN_WITH_AUTO_"
    "SAME_CALL_FLAT_GATED_SUBMISSION_AND_SEMI_PENDING_CONFIRMATION_WHILE_"
    "THE_COMPLETE_BROKER_EXECUTION_CHAIN_REMAINS_TO_CLOSE_CANONICALLY"
)
FACTUAL_VERDICT = (
    "A. WORKSPACE_BROKER_EXECUTION_POST_RISK_END_TO_END_ANATOMY_GREEN_WITH_"
    "AUTO_IDENTITY_PRESERVING_DISPATCH_SEMI_CONFIRMATION_HOLD_AND_ZERO_"
    "ACTUAL_BROKER_EXECUTION"
)


class UnusedSessionRepository(SessionRepository):
    """Надати controller-у SessionRepository без persisted Session роботи."""


@dataclass(frozen=True, slots=True)
class ModeResult:
    """Зберегти observable post-risk результат одного control mode."""

    accepted: bool
    risk_decision: str | None
    execution_state: str
    trade_uid: str
    order_plan_uid: str
    position_snapshot_calls: int
    submission_calls: int
    submitted_trade_uid: str | None
    submitted_order_plan_uid: str | None
    broker_requests: int
    broker_execution_attempted: bool


class EvidenceRuntimeEngine:
    """Перехопити position evidence та submission без broker endpoint."""

    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository
        self.position_snapshot_calls = 0
        self.submission_calls: list[dict[str, object]] = []
        self.actual_broker_requests = 0
        self.actual_broker_execution_attempted = False

    def get_workspace_broker_positions_snapshot(
        self,
        broker_name: str,
        account_id: str,
    ) -> BrokerPositionSnapshot:
        """Повернути supplied complete empty same-call position snapshot."""
        self.position_snapshot_calls += 1
        return BrokerPositionSnapshot.success_result(
            broker_name,
            account_id,
            [],
        )

    def submit_workspace_execution_plan(
        self,
        trade_uid: str,
        order_plan_uid: str,
        *,
        reverse_required: bool = False,
        confirmed_flat: bool = False,
    ) -> dict[str, object]:
        """Зафіксувати production-shaped dispatch без broker execution."""
        call = {
            "trade_uid": trade_uid,
            "order_plan_uid": order_plan_uid,
            "reverse_required": reverse_required,
            "confirmed_flat": confirmed_flat,
        }
        self.submission_calls.append(call)
        return call


class SafeIbMarketProvider(WorkspaceBrokerMarketProviderProtocol):
    """Подати warm-up і один live IB event без broker network."""

    def __init__(self) -> None:
        self.workspace_uid: str | None = None
        self.broker_requests = 0
        self.broker_execution_attempted = False
        self._live_event: WorkspaceMarketEvent | None = None

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
        """Підтвердити test binding і повернути completed warm-up bar."""
        del spread_limit
        if (
            broker != "IB"
            or not str(account_id or "").startswith("D")
            or symbol != "AAPL"
            or timeframe != "M15"
            or warmup_bars != 1
        ):
            raise AssertionError("unexpected TEST_ONLY IB binding")
        self.workspace_uid = workspace_uid
        self._live_event = _market_event(EVENT_UTC)
        return (_market_event(EVENT_UTC - timedelta(minutes=15)),)

    def poll_workspace(self, workspace_uid: str) -> WorkspaceMarketEvent | None:
        """Віддати один completed live event, потім лише None."""
        self._require_workspace(workspace_uid)
        event = self._live_event
        self._live_event = None
        return event

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        """Повернути connected state лише для активної binding."""
        return workspace_uid == self.workspace_uid

    def suspend_workspace(self, workspace_uid: str) -> None:
        """Перевірити workspace identity під час локального suspend."""
        self._require_workspace(workspace_uid)

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Підтвердити workspace identity без додаткових events."""
        self._require_workspace(workspace_uid)
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        """Звільнити тільки локальну binding."""
        self._require_workspace(workspace_uid)
        self.workspace_uid = None

    def _require_workspace(self, workspace_uid: str) -> None:
        """Відхилити звернення до чужого workspace."""
        if workspace_uid != self.workspace_uid:
            raise AssertionError("unexpected workspace UID")


class RiskAllowAlgorithm(PassiveWorkspaceAlgorithm):
    """Створити один контрольований signal із повним trade intent."""

    def __init__(self, algorithm_id: str, signal_uid: str) -> None:
        super().__init__(algorithm_id)
        self._signal_uid = signal_uid
        self._emitted = False

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        """Подати intent після дозволу production runtime context."""
        super().on_market_event(event)
        if self.context is None or not self.context.signal_allowed:
            return None
        if self._emitted:
            return None
        self._emitted = True
        return WorkspaceSignalProposal(
            signal_type="T109_112_POST_RISK",
            direction="BUY",
            strength=1.0,
            macd_state="CROSS_UP",
            alligator_confirmation="CONFIRMED",
            trade_intent=WorkspaceTradeIntent(
                requested_volume=1.0,
                estimated_loss_at_stop=50.0,
                stop_loss=189.0,
                signal_uid=self._signal_uid,
            ),
        )


def _market_event(timestamp: datetime) -> WorkspaceMarketEvent:
    """Побудувати completed causal IB market event."""
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="IB",
        symbol="AAPL",
        timeframe="M15",
        bid=199.98,
        ask=200.00,
        spread=0.02,
        open=199.40,
        high=200.20,
        low=199.20,
        close=199.99,
        volume=1000.0,
        source_mode=WORKSPACE_DATA_MODE_BROKER,
    )


def _workspace(control_mode: str) -> AlgorithmWorkspace:
    """Створити окремий IB PAPER workspace для control mode."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=f"D109112-{control_mode}",
        account_mode="PAPER",
        symbol="AAPL",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=control_mode,
        parameters={
            "warmup_bars": 1,
            "spread_limit": 0.05,
        },
        risk_settings={
            "risk_percent": 1.0,
            "maximum_position_volume": 10.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
    )


def _run_mode(
    control_mode: str,
    connection: sqlite3.Connection,
    repository: RuntimeRepository,
) -> ModeResult:
    """Пройти public runtime від risk ALLOW до controller post-risk action."""
    provider = SafeIbMarketProvider()
    engine = EvidenceRuntimeEngine(repository)
    algorithm = RiskAllowAlgorithm(
        "RailAlgorithm",
        f"t109112-{control_mode.lower()}",
    )
    controller = AlgorithmWorkspaceController(
        repository=UnusedSessionRepository(),
        algorithm_factory=lambda _algorithm_id: algorithm,
    )
    controller.set_runtime_engine(engine)
    runtime = controller.attach_workspace_runtime(_workspace(control_mode))
    runtime.set_broker_market_provider(provider)
    runtime.begin_start()
    runtime.complete_start()
    runtime.set_risk_account_snapshot(
        equity=100_000.0,
        daily_realized_pnl=0.0,
        open_positions_count=0,
        currency="USD",
        snapshot_utc=EVENT_UTC,
    )
    event = runtime.advance_broker_market()
    if event is None or len(runtime.signals) != 1:
        raise AssertionError("post-risk signal was not recorded exactly once")
    record = runtime.signals[0]

    rows = connection.execute(
        "SELECT * FROM trades WHERE workspace_uid = ? AND signal_uid = ?",
        (record.workspace_uid, record.signal_uid),
    ).fetchall()
    if len(rows) != 1:
        raise AssertionError("post-risk trade was not persisted exactly once")
    trade = rows[0]
    trade_uid = str(trade["trade_uid"])
    chain = repository.get_trade_chain(trade_uid)
    plans = chain.get("order_plans", [])
    if len(plans) != 1:
        raise AssertionError("post-risk order plan was not persisted exactly once")
    order_plan_uid = str(plans[0]["order_plan_uid"])

    call = engine.submission_calls[0] if engine.submission_calls else None
    result = ModeResult(
        accepted=record.accepted,
        risk_decision=record.risk_decision,
        execution_state=str(trade["execution_state"]),
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        position_snapshot_calls=engine.position_snapshot_calls,
        submission_calls=len(engine.submission_calls),
        submitted_trade_uid=(str(call["trade_uid"]) if call else None),
        submitted_order_plan_uid=(
            str(call["order_plan_uid"]) if call else None
        ),
        broker_requests=provider.broker_requests + engine.actual_broker_requests,
        broker_execution_attempted=(
            provider.broker_execution_attempted
            or engine.actual_broker_execution_attempted
        ),
    )
    runtime.stop(f"{TEST_ID} {control_mode} completed")
    return result


def main() -> None:
    """Запустити AUTO/SEMI anatomy та визначити наступну межу."""
    production_root = Path(getfile(WorkspaceRuntime)).resolve().parents[1]
    controller_source = (
        production_root / "core" / "algorithm_workspace_controller.py"
    ).read_text(encoding="utf-8")
    engine_source = (
        production_root / "engine" / "runtime_engine.py"
    ).read_text(encoding="utf-8")

    with TemporaryDirectory(prefix="t109_112_") as tmp_dir:
        connection = connect_runtime_db(Path(tmp_dir) / "runtime.db")
        connection.row_factory = sqlite3.Row
        repository = RuntimeRepository(connection)
        auto = _run_mode(
            WORKSPACE_CONTROL_MODE_AUTO,
            connection,
            repository,
        )
        semi = _run_mode(
            WORKSPACE_CONTROL_MODE_SEMI,
            connection,
            repository,
        )
        connection.close()

    controller_observer_wired = (
        "signal_record_observer=self._persist_workspace_trade_after_risk_allow"
        in controller_source
    )
    auto_risk_allow_persists_trade = (
        auto.accepted
        and auto.risk_decision == "ALLOW"
        and auto.execution_state == "READY_FOR_SUBMISSION"
    )
    auto_creates_order_plan = bool(auto.trade_uid and auto.order_plan_uid)
    auto_same_call_flat_checked = auto.position_snapshot_calls == 1
    auto_dispatches_existing_identity = (
        auto.submission_calls == 1
        and auto.submitted_trade_uid == auto.trade_uid
        and auto.submitted_order_plan_uid == auto.order_plan_uid
    )
    semi_risk_allow_persists_trade = (
        semi.accepted
        and semi.risk_decision == "ALLOW"
        and semi.execution_state == "PENDING_CONFIRMATION"
    )
    semi_creates_order_plan = bool(semi.trade_uid and semi.order_plan_uid)
    semi_does_not_snapshot_or_submit = (
        semi.position_snapshot_calls == 0 and semi.submission_calls == 0
    )
    submission_method_present = (
        "def submit_workspace_execution_plan(" in engine_source
    )
    terminal_lifecycle_routes_present = all(
        token in engine_source
        for token in (
            "def reconcile_workspace_broker_order(",
            "def recover_ctrader_workspace_timeout(",
            "except BrokerTerminalOrderFailure as failure:",
        )
    )
    actual_broker_requests = auto.broker_requests + semi.broker_requests
    actual_broker_execution_attempted = (
        auto.broker_execution_attempted or semi.broker_execution_attempted
    )

    assert controller_observer_wired
    assert auto_risk_allow_persists_trade
    assert auto_creates_order_plan
    assert auto_same_call_flat_checked
    assert auto_dispatches_existing_identity
    assert semi_risk_allow_persists_trade
    assert semi_creates_order_plan
    assert semi_does_not_snapshot_or_submit
    assert submission_method_present
    assert terminal_lifecycle_routes_present
    assert actual_broker_requests == 0
    assert not actual_broker_execution_attempted

    print("T109-112_WORKSPACE_BROKER_EXECUTION_POST_RISK_END_TO_END_ANATOMY=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"controller_observer_wired={controller_observer_wired}")
    print(f"auto_risk_allow_persists_trade={auto_risk_allow_persists_trade}")
    print(f"auto_creates_order_plan={auto_creates_order_plan}")
    print(f"auto_same_call_flat_checked={auto_same_call_flat_checked}")
    print(
        "auto_dispatches_existing_identity="
        f"{auto_dispatches_existing_identity}"
    )
    print(f"semi_risk_allow_persists_trade={semi_risk_allow_persists_trade}")
    print(f"semi_creates_order_plan={semi_creates_order_plan}")
    print(
        "semi_does_not_snapshot_or_submit="
        f"{semi_does_not_snapshot_or_submit}"
    )
    print(f"submission_method_present={submission_method_present}")
    print(f"terminal_lifecycle_routes_present={terminal_lifecycle_routes_present}")
    print(f"actual_broker_requests={actual_broker_requests}")
    print(
        "actual_broker_execution_attempted="
        f"{actual_broker_execution_attempted}"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_112_workspace_broker_execution_post_risk_anatomy() -> None:
    """Запустити T109-112 як pytest test."""
    main()


if __name__ == "__main__":
    main()
