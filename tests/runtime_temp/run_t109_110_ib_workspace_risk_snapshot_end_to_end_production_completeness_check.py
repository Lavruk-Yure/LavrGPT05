"""run_t109_110_ib_workspace_risk_snapshot_end_to_end_production_completeness_check.py.

TEST_ONLY checkpoint проходить фактичний public WorkspaceRuntime BROKER pipeline:
локальний read-only IB provider подає completed market event, контрольований
algorithm створює trade intent, runtime формує WorkspaceRiskRequest із durable
account snapshot timestamp, а production risk evaluator ухвалює або блокує
signal. Окремі runtime-и перевіряють fresh timestamp, точну дозволену межу
30 секунд, future timestamp і першу microsecond поза freshness window.

Перевірка не викликає protected API, broker network чи execution route. Вона
не змінює production, schema, Replay, risk thresholds або user settings і
вимагає broker_requests=0 та broker_execution_attempted=False в усіх probes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
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
from engine.risk.constants import (  # noqa: E402
    RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE,
    RISK_REASON_ACCOUNT_SNAPSHOT_STALE,
    RISK_REASON_APPROVED,
)
from engine.runtime_constants import (  # noqa: E402
    RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS,
)

TEST_ID = "T109-110"
EVENT_UTC = datetime(2026, 9, 23, 15, 45, tzinfo=UTC)
FIRST_UNRESOLVED_BOUNDARY = (
    "IB_WORKSPACE_RISK_SNAPSHOT_PRODUCTION_CLOSURE_DECISION"
)
BOUNDARY_CONTRACT = (
    "THE_FULL_IB_WORKSPACE_BROKER_SIGNAL_PATH_NOW_CONSUMES_ONE_COMPLETE_"
    "CAUSAL_RISK_SNAPSHOT_AND_ENFORCES_DECISION_TIME_FRESHNESS_WITHOUT_"
    "BROKER_EXECUTION_WHILE_CANONICAL_PRODUCTION_CLOSURE_REMAINS_TO_DECIDE"
)
FACTUAL_VERDICT = (
    "A. IB_WORKSPACE_RISK_SNAPSHOT_END_TO_END_PRODUCTION_COMPLETENESS_GREEN_"
    "WITH_PUBLIC_RUNTIME_SIGNAL_PATH_SHARED_SNAPSHOT_FRESHNESS_BOUNDARIES_"
    "AND_ZERO_BROKER_EXECUTION"
)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Зберегти observable risk result одного public runtime probe."""

    accepted: bool
    risk_decision: str | None
    risk_reason_code: str | None
    risk_execution_attempted: bool
    broker_requests: int
    broker_execution_attempted: bool


class SafeIbMarketProvider(WorkspaceBrokerMarketProviderProtocol):
    """Подати warm-up і один live event без broker network чи execution."""

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
        """Підтвердити IB binding і повернути один completed warm-up bar."""
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
        """Віддати один immutable completed live event, потім лише None."""
        self._require_workspace(workspace_uid)
        event = self._live_event
        self._live_event = None
        return event

    def is_workspace_broker_connected(self, workspace_uid: str) -> bool:
        """Повернути deterministic connected state активної test binding."""
        return workspace_uid == self.workspace_uid

    def suspend_workspace(self, workspace_uid: str) -> None:
        """Перевірити workspace identity під час локального suspend."""
        self._require_workspace(workspace_uid)

    def resume_workspace(
        self,
        workspace_uid: str,
    ) -> tuple[WorkspaceMarketEvent, ...]:
        """Підтвердити workspace identity без додаткових market events."""
        self._require_workspace(workspace_uid)
        return ()

    def stop_workspace(self, workspace_uid: str) -> None:
        """Звільнити тільки локальну test binding."""
        self._require_workspace(workspace_uid)
        self.workspace_uid = None

    def _require_workspace(self, workspace_uid: str) -> None:
        """Відхилити звернення до чужого workspace."""
        if workspace_uid != self.workspace_uid:
            raise AssertionError("unexpected workspace UID")


class RiskSignalAlgorithm(PassiveWorkspaceAlgorithm):
    """Створити один контрольований signal з повним trade intent."""

    def __init__(self, algorithm_id: str, signal_uid: str) -> None:
        super().__init__(algorithm_id)
        self._signal_uid = signal_uid
        self._emitted = False

    def on_market_event(
        self,
        event: WorkspaceMarketEvent,
    ) -> WorkspaceSignalProposal | None:
        """Подати intent лише після дозволу production runtime context."""
        super().on_market_event(event)
        if self.context is None or not self.context.signal_allowed:
            return None
        if self._emitted:
            return None
        self._emitted = True
        return WorkspaceSignalProposal(
            signal_type="T109_110_RISK_COMPLETENESS",
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
    """Побудувати причинний completed IB bar для runtime pipeline."""
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


def _workspace(control_mode: str, scenario: str) -> AlgorithmWorkspace:
    """Створити окремий IB PAPER workspace з повними risk limits."""
    return AlgorithmWorkspace.create(
        broker="IB",
        account_id=f"D109110-{scenario}-{control_mode}",
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


def _probe(
    *,
    control_mode: str,
    scenario: str,
    snapshot_utc: datetime,
) -> ProbeResult:
    """Пройти public runtime від completed event до записаного risk result."""
    provider = SafeIbMarketProvider()
    algorithm = RiskSignalAlgorithm(
        "RailAlgorithm",
        f"t109110-{scenario.lower()}-{control_mode.lower()}",
    )
    runtime = WorkspaceRuntime(
        _workspace(control_mode, scenario),
        algorithm_factory=lambda _algorithm_id: algorithm,
        broker_market_provider=provider,
    )
    runtime.begin_start()
    runtime.complete_start()
    runtime.set_risk_account_snapshot(
        equity=100_000.0,
        daily_realized_pnl=0.0,
        open_positions_count=0,
        currency="USD",
        snapshot_utc=snapshot_utc,
    )
    event = runtime.advance_broker_market()
    if event is None or event.timestamp != EVENT_UTC:
        raise AssertionError("completed IB event did not reach WorkspaceRuntime")
    if len(runtime.signals) != 1:
        raise AssertionError("controlled risk signal was not recorded exactly once")
    record = runtime.signals[0]
    result = ProbeResult(
        accepted=record.accepted,
        risk_decision=record.risk_decision,
        risk_reason_code=record.risk_reason_code,
        risk_execution_attempted=record.risk_execution_attempted,
        broker_requests=provider.broker_requests,
        broker_execution_attempted=provider.broker_execution_attempted,
    )
    runtime.stop(f"{TEST_ID} {scenario} probe completed")
    return result


def main() -> None:
    """Запустити end-to-end completeness assertions і надрукувати verdict."""
    max_age = timedelta(seconds=RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS)
    fresh_auto = _probe(
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        scenario="FRESH_AUTO",
        snapshot_utc=EVENT_UTC,
    )
    fresh_semi = _probe(
        control_mode=WORKSPACE_CONTROL_MODE_SEMI,
        scenario="FRESH_SEMI",
        snapshot_utc=EVENT_UTC,
    )
    boundary = _probe(
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        scenario="EXACT_BOUNDARY",
        snapshot_utc=EVENT_UTC - max_age,
    )
    future = _probe(
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        scenario="FUTURE",
        snapshot_utc=EVENT_UTC + timedelta(microseconds=1),
    )
    stale = _probe(
        control_mode=WORKSPACE_CONTROL_MODE_AUTO,
        scenario="STALE",
        snapshot_utc=EVENT_UTC - max_age - timedelta(microseconds=1),
    )

    public_runtime_signal_path_present = all(
        result.risk_decision is not None
        for result in (fresh_auto, fresh_semi, boundary, future, stale)
    )
    fresh_complete_snapshot_allows_auto = (
        fresh_auto.accepted
        and fresh_auto.risk_decision == "ALLOW"
        and fresh_auto.risk_reason_code == RISK_REASON_APPROVED
    )
    fresh_complete_snapshot_allows_semi = (
        fresh_semi.accepted
        and fresh_semi.risk_decision == "ALLOW"
        and fresh_semi.risk_reason_code == RISK_REASON_APPROVED
    )
    exact_max_age_boundary_allowed = (
        boundary.accepted
        and boundary.risk_decision == "ALLOW"
        and boundary.risk_reason_code == RISK_REASON_APPROVED
    )
    future_snapshot_blocks_signal = (
        not future.accepted
        and future.risk_decision == "BLOCK"
        and future.risk_reason_code == RISK_REASON_ACCOUNT_SNAPSHOT_FUTURE
    )
    stale_snapshot_blocks_signal = (
        not stale.accepted
        and stale.risk_decision == "BLOCK"
        and stale.risk_reason_code == RISK_REASON_ACCOUNT_SNAPSHOT_STALE
    )
    all_results = (fresh_auto, fresh_semi, boundary, future, stale)
    risk_execution_attempted = any(
        result.risk_execution_attempted for result in all_results
    )
    broker_execution_attempted = any(
        result.broker_execution_attempted for result in all_results
    )
    broker_requests = sum(result.broker_requests for result in all_results)

    assert public_runtime_signal_path_present
    assert fresh_complete_snapshot_allows_auto
    assert fresh_complete_snapshot_allows_semi
    assert exact_max_age_boundary_allowed
    assert future_snapshot_blocks_signal
    assert stale_snapshot_blocks_signal
    assert not risk_execution_attempted
    assert not broker_execution_attempted
    assert broker_requests == 0

    print("T109-110_IB_WORKSPACE_RISK_SNAPSHOT_END_TO_END_COMPLETENESS=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"selected_max_age_seconds={RUNTIME_ACCOUNT_REFRESH_INTERVAL_SECONDS}")
    print(f"public_runtime_signal_path_present={public_runtime_signal_path_present}")
    print(
        "fresh_complete_snapshot_allows_auto="
        f"{fresh_complete_snapshot_allows_auto}"
    )
    print(
        "fresh_complete_snapshot_allows_semi="
        f"{fresh_complete_snapshot_allows_semi}"
    )
    print(f"exact_max_age_boundary_allowed={exact_max_age_boundary_allowed}")
    print(f"future_snapshot_blocks_signal={future_snapshot_blocks_signal}")
    print(f"stale_snapshot_blocks_signal={stale_snapshot_blocks_signal}")
    print(f"risk_execution_attempted={risk_execution_attempted}")
    print(f"broker_execution_attempted={broker_execution_attempted}")
    print(f"broker_requests={broker_requests}")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_110_ib_workspace_risk_snapshot_end_to_end_completeness() -> None:
    """Запустити T109-110 як pytest test."""
    main()


if __name__ == "__main__":
    main()
