"""T116-04 · TEST_ONLY · offline перевірка Workspace -> cTrader execution boundary.

Не читає конфігурацію, не відкриває БД, не створює broker connection
і не формує справжніх заявок у cTrader.
"""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
)
from core.workspace_runtime import (  # noqa: E402
    WorkspaceRuntime,
    WorkspaceRuntimeContext,
)
from core.workspace_signal import WorkspaceSignalRecord  # noqa: E402
from engine.broker_account import BrokerAccount  # noqa: E402
from engine.broker_order_identity import get_broker_order_control_mode  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.services.ctrader_runtime_service import (  # noqa: E402
    CTraderRuntimeService,
    CTraderSessionManagerProtocol,
)

ACCOUNT = "T116-FAKE-DEMO-ACCOUNT"
WORKSPACE = "T116-FAKE-WORKSPACE"
SIGNAL = "T116-FAKE-SIGNAL"
TRADE = "T116-FAKE-TRADE"
PLAN = "T116-FAKE-PLAN"


class DryRunIntercept(Exception):
    """Зупинити виконання до реального cTrader adapter або persistence."""


class OfflineAdapter:
    """Єдиний adapter у тесті; не містить мережевих операцій."""

    def __init__(self, connected: bool = True, alive: bool = True):
        self.connected = connected
        self.alive = alive
        self.captured_orders: list[dict] = []

    def is_connected(self) -> bool:
        return self.connected

    def is_session_alive(self) -> bool:
        return self.alive

    @staticmethod
    def get_account_info() -> BrokerAccount:
        return BrokerAccount(
            broker="CTRADER", account_id=ACCOUNT, account_mode="DEMO", currency="USD"
        )

    def place_market_order(self, **kwargs):
        self.captured_orders.append(dict(kwargs))
        raise DryRunIntercept("TEST_ONLY: adapter call intercepted")


def make_engine(
    *,
    account_id=ACCOUNT,
    connected=True,
    alive=True,
    plan_volume=1000.0,
    existing_order=False,
):
    adapter = OfflineAdapter(connected=connected, alive=alive)
    session = Mock(spec=CTraderSessionManagerProtocol)
    session.get_active_adapter.return_value = adapter
    service = CTraderRuntimeService(session_manager=session)
    chain = {
        "trade": {
            "source": "WORKSPACE",
            "broker": "CTRADER",
            "account_id": account_id,
            "control_mode": "AUTO",
            "execution_state": "READY_FOR_SUBMISSION",
            "symbol": "EURUSD",
            "volume": 1000.0,
        },
        "order_plans": [
            {
                "source": "WORKSPACE",
                "order_plan_uid": PLAN,
                "order_type": "MARKET",
                "side": "BUY",
                "volume": plan_volume,
                "stop_loss": 1.0800,
            }
        ],
        "broker_orders": (
            [
                {
                    "order_plan_uid": PLAN,
                    "broker_order_uid": "T116-EXISTING",
                    "broker_order_id": "T116-OFFLINE-ID",
                    "execution_status": "SUBMITTED",
                }
            ]
            if existing_order
            else []
        ),
    }
    repository = Mock()
    repository.get_trade_chain.return_value = chain
    repository.create_broker_order.side_effect = AssertionError(
        "TEST_ONLY: database write is forbidden"
    )
    engine = RuntimeEngine.__new__(RuntimeEngine)
    engine.ctrader_runtime_service = service
    engine.ib_runtime_service = None
    engine.repository = repository
    return engine, adapter, repository


# noinspection PyProtectedMember
def check_controller_plan():
    """Перевірити production controller на синтетичному post-risk записі."""
    repo = Mock()
    repo.create_trade.return_value = TRADE
    repo.get_trade_chain.return_value = {"order_plans": []}
    repo.create_order_plan.return_value = PLAN
    submission = Mock(side_effect=AssertionError("TEST_ONLY: submit forbidden"))

    controller = AlgorithmWorkspaceController.__new__(AlgorithmWorkspaceController)
    controller._runtime_engine = SimpleNamespace(
        repository=repo, submit_workspace_execution_plan=submission
    )
    runtime = WorkspaceRuntime.__new__(WorkspaceRuntime)
    runtime.context = WorkspaceRuntimeContext(
        workspace_uid=WORKSPACE,
        broker="CTRADER",
        account_id=ACCOUNT,
        account_mode="DEMO",
        symbol="EURUSD",
        timeframe="M15",
        algorithm_id="TEST_ONLY",
        data_mode="BROKER",
        control_mode="AUTO",
    )
    controller._runtimes = {WORKSPACE: runtime}
    controller._workspace_submission_identities = {}

    record = WorkspaceSignalRecord(
        timestamp=datetime.now(UTC),
        signal_uid=SIGNAL,
        workspace_uid=WORKSPACE,
        broker="CTRADER",
        account_id=ACCOUNT,
        symbol="EURUSD",
        timeframe="M15",
        source_mode="BROKER",
        signal_type="MACD",
        direction="BUY",
        strength=1.0,
        macd_state="BULLISH",
        alligator_confirmation="CONFIRMED",
        spread_status="OK",
        accepted=True,
        reason="TEST_ONLY synthetic record",
        risk_decision="ALLOW",
        requested_volume=1000.0,
        approved_volume=1000.0,
        stop_loss=1.0800,
    )
    with patch.object(
        AlgorithmWorkspaceController,
        "workspace_same_call_position_snapshot_confirms_flat",
        return_value=False,
    ):
        controller._persist_workspace_trade_after_risk_allow(record)

    trade_args = repo.create_trade.call_args.kwargs
    plan_args = repo.create_order_plan.call_args.kwargs
    assert trade_args["broker"] == "CTRADER"
    assert trade_args["account_id"] == ACCOUNT
    assert trade_args["source"] == "WORKSPACE"
    assert trade_args["execution_state"] == "READY_FOR_SUBMISSION"
    assert plan_args["trade_uid"] == TRADE
    assert plan_args["order_type"] == "MARKET"
    assert plan_args["side"] == "BUY"
    assert plan_args["volume"] == 1000.0
    assert plan_args["stop_loss"] == 1.0800
    assert controller._workspace_submission_identity_for_signal(WORKSPACE, SIGNAL) == (
        TRADE,
        PLAN,
    )
    submission.assert_not_called()

    repo.create_trade.reset_mock()
    repo.create_order_plan.reset_mock()
    controller._persist_workspace_trade_after_risk_allow(
        replace(record, risk_decision="REJECT")
    )
    repo.create_trade.assert_not_called()
    repo.create_order_plan.assert_not_called()
    print("post_risk_orderplan_wiring=OK")
    print("risk_reject_does_not_create_plan=OK")


def check_engine_dry_run():
    """Зупинити справжній submit метод на підставному adapter."""
    engine, adapter, repo = make_engine()
    try:
        engine.submit_workspace_execution_plan(TRADE, PLAN)
    except DryRunIntercept:
        pass
    else:
        raise AssertionError("TEST_ONLY interception was not reached")

    assert len(adapter.captured_orders) == 1
    order = adapter.captured_orders[0]
    assert order["symbol_name"] == "EURUSD"
    assert order["side"] == "BUY"
    assert math.isclose(order["lots"], 0.01, rel_tol=0.0, abs_tol=1e-12)
    assert order["stop_loss"] == 1.0800
    assert order["take_profit"] is None
    assert get_broker_order_control_mode(order["comment"]) == "AUTO"
    assert "WSP:" + TRADE.replace("-", "")[:12] in order["comment"]
    repo.create_broker_order.assert_not_called()
    print("offline_fake_ctrader_binding=OK")
    print("base_units_to_lots=OK")
    print("market_payload_sl_tp_comment=OK")

    wrong, wrong_adapter, wrong_repo = make_engine(account_id="OTHER-FAKE-ACCOUNT")
    try:
        wrong.submit_workspace_execution_plan(TRADE, PLAN)
    except RuntimeError as caught:
        assert "does not match" in str(caught), str(caught)
    else:
        raise AssertionError("Wrong account was not blocked")
    assert not wrong_adapter.captured_orders
    wrong_repo.create_broker_order.assert_not_called()
    print("wrong_account_blocks_before_adapter=OK")

    invalid, invalid_adapter, invalid_repo = make_engine(plan_volume=2000.0)
    try:
        invalid.submit_workspace_execution_plan(TRADE, PLAN)
    except RuntimeError as caught:
        assert "volumes differ" in str(caught), str(caught)
    else:
        raise AssertionError("Mismatched volume was not blocked")
    assert not invalid_adapter.captured_orders
    invalid_repo.create_broker_order.assert_not_called()
    print("volume_mismatch_blocks_before_adapter=OK")

    restarted, restarted_adapter, restarted_repo = make_engine(existing_order=True)
    result = restarted.submit_workspace_execution_plan(TRADE, PLAN)
    assert result["already_submitted"] is True
    assert result["broker_order_uid"] == "T116-EXISTING"
    assert not restarted_adapter.captured_orders
    restarted_repo.create_broker_order.assert_not_called()
    print("persisted_order_after_fake_restart_no_duplicate=OK")

    print("intercepted_adapter_calls=1")
    print("real_broker_requests=0")
    print("database_writes=0")
    print("production_changes=0")
    print("active_lge_session=NOT_CHECKED")
    print("candidate_f_live_signal=NOT_TESTED")
    print("T116-04=GREEN_OFFLINE_DRY_RUN")


def test():
    print("T116-04 TEST_ONLY | offline controller + cTrader dry-run")
    with patch("socket.socket.connect", side_effect=AssertionError("network blocked")):
        check_controller_plan()
        check_engine_dry_run()


if __name__ == "__main__":
    try:
        test()
    except Exception as error:
        print(f"failure={type(error).__name__}: {error}")
        print("T116-04=RED")
        raise SystemExit(1)
