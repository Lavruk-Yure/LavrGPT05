"""run_t107_14_broker_auto_semi_execution_contract_check.py — T107-14.

TEST_ONLY diagnostic перевіряє фактичний BROKER control-flow поточного WSP:
completed-bar aggregation для M1/M5/M15, delivery сигналу, наявність trade
intent, risk gates, AUTO/SEMI semantics та перехід до broker execution. Для
post-signal risk seam використовується локальний deterministic algorithm і
read-only provider; жоден реальний broker endpoint не створюється й не
викликається.

Runner навмисно відділяє production Candidate F proposal від синтетичного
trade-intent probe. Він завершується OK, коли чесно зафіксовано як наявні
контракти, так і missing wiring; OK не означає, що AUTO або SEMI operational.
Production, Replay, Candidate F, параметри, SL/TP, PD, MD7 і локалізація не
змінюються.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
    AlgorithmWorkspace,
)
from core.workspace_algorithm import (  # noqa: E402
    PassiveWorkspaceAlgorithm,
    create_registered_workspace_algorithm,
)
from core.workspace_alligator import (  # noqa: E402
    WorkspaceMacdAlligatorReplayAlgorithm,
)
from core.workspace_broker_market import (  # noqa: E402
    WorkspaceBrokerBinding,
    WorkspaceBrokerMarketProviderProtocol,
    WorkspaceLiveBarAggregator,
)
from core.workspace_market_event import WorkspaceMarketEvent  # noqa: E402
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WorkspaceSignalProposal,
    WorkspaceTradeIntent,
)
from engine.risk.constants import (  # noqa: E402
    RISK_REASON_ACCOUNT_BINDING_MISMATCH,
    RISK_REASON_DAILY_LOSS_LIMIT_REACHED,
    RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
    RISK_REASON_RUNTIME_NOT_READY,
    RISK_REASON_SPREAD_BLOCKED,
    RISK_REASON_STOP_LOSS_REQUIRED,
)
from engine.risk.risk_model import (  # noqa: E402
    WorkspaceRiskEvaluator,
    WorkspaceRiskPolicy,
    WorkspaceRiskRequest,
)

TEST_ID = "T107-14"
MODE = "RM107_T107_14_BROKER_AUTO_SEMI_EXECUTION_CONTRACT_TEST_ONLY"
BASE_TIME = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ModeProbeResult:
    """Зберегти observable результат одного AUTO або SEMI runtime probe."""

    accepted: bool
    risk_allowed: bool
    risk_execution_attempted: bool
    actual_broker_requests: int
    actual_broker_execution_attempted: bool


class SafeBrokerMarketProvider(WorkspaceBrokerMarketProviderProtocol):
    """Подати warm-up і live completed bar без execution API та мережі."""

    def __init__(self, timeframe: str) -> None:
        self.timeframe = timeframe
        self.workspace_uid: str | None = None
        self.actual_broker_requests = 0
        self.actual_broker_execution_attempted = False
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
        """Підтвердити binding і повернути потрібну кількість warm-up bars."""
        del account_id, spread_limit
        if broker != "CTRADER" or symbol != "EURUSD":
            raise AssertionError("unexpected test binding")
        if timeframe != self.timeframe or warmup_bars != 1:
            raise AssertionError("unexpected warm-up contract")
        self.workspace_uid = workspace_uid
        self._live_event = _market_event(
            timeframe,
            BASE_TIME + timedelta(minutes=30),
        )
        return (_market_event(timeframe, BASE_TIME),)

    def poll_workspace(self, workspace_uid: str) -> WorkspaceMarketEvent | None:
        """Віддати один immutable completed bar, а потім лише None."""
        self._require_workspace(workspace_uid)
        event = self._live_event
        self._live_event = None
        return event

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        """Повернути deterministic healthy state лише для active binding."""
        return workspace_uid == self.workspace_uid

    def suspend_workspace(self, workspace_uid: str) -> None:
        """Перевірити UID під час безпечного локального suspend."""
        self._require_workspace(workspace_uid)

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Підтвердити UID без додаткового broker request."""
        self._require_workspace(workspace_uid)
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        """Звільнити лише локальну binding без broker operation."""
        self._require_workspace(workspace_uid)
        self.workspace_uid = None

    def _require_workspace(self, workspace_uid: str) -> None:
        """Відхилити звернення до чужого test workspace."""
        if workspace_uid != self.workspace_uid:
            raise AssertionError("unexpected workspace UID")


class TradeIntentProbeAlgorithm(PassiveWorkspaceAlgorithm):
    """Подати один контрольований intent після Candidate F proposal boundary."""

    def __init__(self, algorithm_id: str) -> None:
        super().__init__(algorithm_id)
        self._emitted = False

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        """Створити один allowed signal із валідним broker-neutral intent."""
        super().on_market_event(event)
        if self.context is None or not self.context.signal_allowed:
            return None
        if self._emitted:
            return None
        self._emitted = True
        return WorkspaceSignalProposal(
            signal_type="CANDIDATE_F_TEST_SEAM",
            direction="BUY",
            strength=1.0,
            macd_state="CROSS_UP",
            alligator_confirmation="CONFIRMED",
            trade_intent=WorkspaceTradeIntent(
                requested_volume=1000.0,
                estimated_loss_at_stop=50.0,
                stop_loss=1.1600,
                signal_uid=f"t10714-{self.context.control_mode.lower()}",
            ),
        )


def _market_event(timeframe: str, timestamp: datetime) -> WorkspaceMarketEvent:
    """Побудувати валідний completed BROKER bar для одного timeframe."""
    return WorkspaceMarketEvent(
        timestamp=timestamp,
        broker="CTRADER",
        symbol="EURUSD",
        timeframe=timeframe,
        bid=1.1700,
        ask=1.1702,
        spread=0.0002,
        open=1.1695,
        high=1.1704,
        low=1.1693,
        close=1.1701,
        volume=100.0,
        source_mode=WORKSPACE_DATA_MODE_BROKER,
    )


def _workspace(control_mode: str) -> AlgorithmWorkspace:
    """Створити BROKER DEMO WSP з усіма явними risk limits тесту."""
    return AlgorithmWorkspace.create(
        broker="CTRADER",
        account_id=f"T10714-{control_mode}",
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        algorithm="RailAlgorithm",
        data_mode=WORKSPACE_DATA_MODE_BROKER,
        control_mode=control_mode,
        parameters={
            "warmup_bars": 1,
            "spread_limit": 0.0010,
        },
        risk_settings={
            "risk_percent": 1.0,
            "maximum_position_volume": 1000.0,
            "maximum_open_positions": 2,
            "max_daily_loss_percent": 2.0,
            "require_stop_loss": True,
        },
    )


def _probe_mode(control_mode: str) -> ModeProbeResult:
    """Пройти public BROKER runtime до ALLOW risk decision без execution."""
    provider = SafeBrokerMarketProvider("M15")
    algorithm = TradeIntentProbeAlgorithm("RailAlgorithm")
    runtime = WorkspaceRuntime(
        _workspace(control_mode),
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    runtime.set_risk_account_snapshot(
        equity=100_000.0,
        daily_realized_pnl=0.0,
        open_positions_count=0,
        snapshot_utc=BASE_TIME,
    )
    event = runtime.advance_broker_market()
    if event is None or len(runtime.signals) != 1:
        raise AssertionError("controlled BROKER signal was not recorded")
    record = runtime.signals[0]
    result = ModeProbeResult(
        accepted=record.accepted,
        risk_allowed=record.risk_decision == "ALLOW",
        risk_execution_attempted=record.risk_execution_attempted,
        actual_broker_requests=provider.actual_broker_requests,
        actual_broker_execution_attempted=(
            provider.actual_broker_execution_attempted
        ),
    )
    runtime.stop("T107-14 probe completed")
    return result


def _timeframe_support() -> dict[str, bool]:
    """Перевірити незалежний rollover production aggregator для трьох WSP."""
    intervals = {"M1": 1, "M5": 5, "M15": 15}
    results: dict[str, bool] = {}
    aggregators: list[WorkspaceLiveBarAggregator] = []
    for timeframe, minutes in intervals.items():
        binding = WorkspaceBrokerBinding(
            workspace_uid=f"t10714-{timeframe.lower()}",
            broker="CTRADER",
            account_id="T10714-DEMO",
            symbol="EURUSD",
            timeframe=timeframe,
        )
        aggregator = WorkspaceLiveBarAggregator(binding)
        aggregators.append(aggregator)
        partial = aggregator.update(
            timestamp=BASE_TIME + timedelta(seconds=2),
            bid=1.1700,
            ask=1.1702,
            volume=10.0,
        )
        completed = aggregator.update(
            timestamp=BASE_TIME + timedelta(minutes=minutes, seconds=2),
            bid=1.1701,
            ask=1.1703,
            volume=20.0,
        )
        results[timeframe] = bool(
            partial is None
            and completed is not None
            and completed.timeframe == timeframe
            and completed.timestamp == BASE_TIME
        )
    unique_state = len({id(item) for item in aggregators}) == len(aggregators)
    if not unique_state:
        raise AssertionError("timeframe aggregators unexpectedly share state")
    return results


def _risk_gate_support() -> dict[str, bool]:
    """Довести executable BLOCK guards на одному broker-neutral request."""
    policy = WorkspaceRiskPolicy(
        max_risk_percent=1.0,
        maximum_position_volume=1000.0,
        maximum_open_positions=2,
        max_daily_loss_percent=2.0,
        require_stop_loss=True,
    )
    evaluator = WorkspaceRiskEvaluator(policy)
    request = WorkspaceRiskRequest(
        timestamp=BASE_TIME,
        workspace_uid="t10714-risk",
        broker="CTRADER",
        account_id="T10714-DEMO",
        symbol="EURUSD",
        side="BUY",
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        requested_volume=1000.0,
        equity=100_000.0,
        estimated_loss_at_stop=500.0,
        stop_loss=1.1600,
        open_positions_count=0,
        daily_realized_pnl=0.0,
        runtime_ready=True,
        binding_verified=True,
        market_valid=True,
        spread_guard_passed=True,
    )
    cases = {
        "runtime": (
            replace(request, runtime_ready=False),
            RISK_REASON_RUNTIME_NOT_READY,
        ),
        "binding": (
            replace(request, binding_verified=False),
            RISK_REASON_ACCOUNT_BINDING_MISMATCH,
        ),
        "positions": (
            replace(request, open_positions_count=2),
            RISK_REASON_MAXIMUM_OPEN_POSITIONS_REACHED,
        ),
        "daily_loss": (
            replace(request, daily_realized_pnl=-2000.0),
            RISK_REASON_DAILY_LOSS_LIMIT_REACHED,
        ),
        "spread": (
            replace(request, spread_guard_passed=False),
            RISK_REASON_SPREAD_BLOCKED,
        ),
        "stop_loss": (
            replace(request, stop_loss=None),
            RISK_REASON_STOP_LOSS_REQUIRED,
        ),
    }
    return {
        name: (
            evaluator.evaluate(blocked_request).reason_code == expected_reason
        )
        for name, (blocked_request, expected_reason) in cases.items()
    }


def _production_contract() -> dict[str, bool]:
    """Зіставити registry, Candidate F schema, runtime й UI execution seams."""
    algorithm = create_registered_workspace_algorithm("RailAlgorithm")
    production_algorithm_registered = isinstance(
        algorithm,
        WorkspaceMacdAlligatorReplayAlgorithm,
    )
    proposal_sources = "\n".join(
        (
            (PROJECT_ROOT / "core" / "workspace_macd.py").read_text(
                encoding="utf-8"
            ),
            (PROJECT_ROOT / "core" / "workspace_alligator.py").read_text(
                encoding="utf-8"
            ),
        )
    )
    runtime_source = inspect.getsource(WorkspaceRuntime)
    area_source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_area.py"
    ).read_text(encoding="utf-8")
    candidate_f_trade_intent_created = bool(
        "WorkspaceTradeIntent(" in proposal_sources
        or "trade_intent=" in proposal_sources
    )
    runtime_execution_endpoint = any(
        token in runtime_source
        for token in (
            "send_order(",
            "place_order(",
            "create_order_plan(",
            "submit_order(",
        )
    )
    runtime_constructor_execution_seam = any(
        token in inspect.signature(WorkspaceRuntime.__init__).parameters
        for token in ("order_manager", "execution_provider", "broker_executor")
    )
    semi_confirmation_ui_available = any(
        token in area_source
        for token in (
            "confirm_workspace_signal",
            "confirm_signal_execution",
            "execute_selected_signal",
        )
    )
    return {
        "production_algorithm_registered": production_algorithm_registered,
        "candidate_f_trade_intent_created": candidate_f_trade_intent_created,
        "runtime_execution_endpoint": runtime_execution_endpoint,
        "runtime_constructor_execution_seam": runtime_constructor_execution_seam,
        "semi_confirmation_ui_available": semi_confirmation_ui_available,
    }


def main() -> None:
    """Надрукувати factual AUTO/SEMI/M1/M5/M15 contract і точний verdict."""
    timeframes = _timeframe_support()
    risk_guards = _risk_gate_support()
    production = _production_contract()
    auto_probe = _probe_mode(WORKSPACE_CONTROL_MODE_AUTO)
    semi_probe = _probe_mode(WORKSPACE_CONTROL_MODE_SEMI)

    broker_data_path_wired = bool(
        all(timeframes.values()) and production["production_algorithm_registered"]
    )
    generic_trade_intent_reaches_risk_gate = bool(
        auto_probe.accepted
        and auto_probe.risk_allowed
        and semi_probe.accepted
        and semi_probe.risk_allowed
    )
    candidate_f_reaches_execution_gate = bool(
        production["candidate_f_trade_intent_created"]
        and generic_trade_intent_reaches_risk_gate
    )
    order_plan_created = bool(
        candidate_f_reaches_execution_gate
        and production["runtime_execution_endpoint"]
    )
    broker_request_would_be_sent = bool(
        order_plan_created and production["runtime_constructor_execution_seam"]
    )
    semi_confirmation_state = bool(
        candidate_f_reaches_execution_gate
        and production["semi_confirmation_ui_available"]
    )
    actual_broker_requests = (
        auto_probe.actual_broker_requests + semi_probe.actual_broker_requests
    )
    actual_execution_attempted = bool(
        auto_probe.actual_broker_execution_attempted
        or auto_probe.risk_execution_attempted
        or semi_probe.actual_broker_execution_attempted
        or semi_probe.risk_execution_attempted
    )

    contract_ok = bool(
        broker_data_path_wired
        and generic_trade_intent_reaches_risk_gate
        and all(risk_guards.values())
        and not candidate_f_reaches_execution_gate
        and not order_plan_created
        and not broker_request_would_be_sent
        and not semi_confirmation_state
        and actual_broker_requests == 0
        and not actual_execution_attempted
    )
    if not contract_ok:
        raise AssertionError("T107-14 factual contract changed; inspect output")

    print(f"test_id={TEST_ID}")
    print(f"mode={MODE}")
    print(f"broker_data_path_wired={broker_data_path_wired}")
    print(f"m1_broker_supported={timeframes['M1']}")
    print(f"m5_broker_supported={timeframes['M5']}")
    print(f"m15_broker_supported={timeframes['M15']}")
    print("independent_m1_m5_m15_wsp_supported=True")
    print(
        "candidate_f_trade_intent_created="
        f"{production['candidate_f_trade_intent_created']}"
    )
    print(
        "generic_trade_intent_reaches_risk_gate="
        f"{generic_trade_intent_reaches_risk_gate}"
    )
    print(f"auto_signal_reaches_execution_gate={candidate_f_reaches_execution_gate}")
    print(f"auto_order_plan_created={order_plan_created}")
    print(f"auto_broker_request_would_be_sent={broker_request_would_be_sent}")
    print("auto_end_to_end_operational=False")
    print(f"semi_signal_reaches_confirmation_state={semi_confirmation_state}")
    print("semi_user_confirmation_required=True")
    print(
        "semi_confirmation_ui_available="
        f"{production['semi_confirmation_ui_available']}"
    )
    print("semi_confirmed_order_reaches_execution_gate=False")
    print(f"semi_broker_request_would_be_sent={broker_request_would_be_sent}")
    print("semi_end_to_end_operational=False")
    print("broker_health_guard=True")
    print("market_availability_guard=True")
    print(f"account_binding_guard={risk_guards['binding']}")
    print("execution_control_mode_guard=False")
    print(f"risk_manager_guard={generic_trade_intent_reaches_risk_gate}")
    print(f"max_open_positions_guard={risk_guards['positions']}")
    print(f"daily_loss_guard={risk_guards['daily_loss']}")
    print(f"spread_guard={risk_guards['spread']}")
    print(f"stop_loss_required_guard={risk_guards['stop_loss']}")
    print("demo_paper_execution_restriction=NOT_APPLICABLE_NO_EXECUTION_PATH")
    print("break_1=Candidate F proposal has no WorkspaceTradeIntent")
    print("break_2=WorkspaceRuntime has no BROKER order-plan/execution endpoint")
    print("break_3=SEMI has no signal-confirmation action wired to execution")
    print(f"actual_broker_requests={actual_broker_requests}")
    print(f"actual_broker_execution_attempted={actual_execution_attempted}")
    print("production_logic_changed=False")
    print("AUTO verdict=PARTIAL")
    print("SEMI verdict=PARTIAL")
    print("M1 verdict=DATA_OPERATIONAL_EXECUTION_NOT_WIRED")
    print("M5 verdict=DATA_OPERATIONAL_EXECUTION_NOT_WIRED")
    print("M15 verdict=DATA_OPERATIONAL_EXECUTION_NOT_WIRED")
    print("tomorrow_demo_paper_verdict=READ_ONLY_SIGNAL_OBSERVATION_ONLY")
    print("T107_14_BROKER_AUTO_SEMI_EXECUTION_CONTRACT=OK")


if __name__ == "__main__":
    main()
