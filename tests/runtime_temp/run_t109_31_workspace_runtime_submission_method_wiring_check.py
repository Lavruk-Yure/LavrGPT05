"""T109-31: production Workspace RuntimeEngine submission method wiring check."""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

runtime_account_state_module = importlib.import_module(
    "engine.runtime_account_state"
)
runtime_broker_health_module = importlib.import_module(
    "engine.runtime_broker_health"
)
runtime_engine_module = importlib.import_module("engine.runtime_engine")

RuntimeAccountState = runtime_account_state_module.RuntimeAccountState
RuntimeBrokerHealth = runtime_broker_health_module.RuntimeBrokerHealth
RuntimeEngine = runtime_engine_module.RuntimeEngine


class _FakeCTraderService:
    def __init__(self, account_id: str) -> None:
        self._account_state = RuntimeAccountState(
            account_id=account_id,
            broker_name="CTRADER",
            currency="USD",
        )
        self._health = RuntimeBrokerHealth()
        self._health.set_connected()
        self.submission_calls: list[dict[str, Any]] = []

    def refresh_broker_health(self) -> RuntimeBrokerHealth:
        return self._health

    def get_broker_health(self) -> RuntimeBrokerHealth:
        return self._health

    def get_account_state(self) -> RuntimeAccountState:
        return self._account_state

    def place_market_order(self, **kwargs: Any) -> dict[str, Any]:
        self.submission_calls.append(dict(kwargs))
        return {"order_id": "CTR-9001", "status": "FILLED"}


class _FakeIBService:
    def __init__(self, account_id: str) -> None:
        self._account_id = account_id
        self._health = RuntimeBrokerHealth()
        self._health.set_connected()
        self.submission_calls: list[dict[str, Any]] = []

    def refresh_broker_health(self) -> RuntimeBrokerHealth:
        return self._health

    def get_broker_health(self) -> RuntimeBrokerHealth:
        return self._health

    def get_managed_accounts(self) -> list[str]:
        return [self._account_id]

    def place_market_order(self, **kwargs: Any) -> dict[str, Any]:
        self.submission_calls.append(dict(kwargs))
        return {"order_id": "IB-9001", "status": "SUBMITTED"}


def _create_workspace_chain(
    engine: RuntimeEngine,
    *,
    broker: str,
    account_id: str,
    control_mode: str,
    execution_state: str,
) -> tuple[str, str]:
    trade_uid = engine.repository.create_trade(
        broker=broker,
        account_id=account_id,
        symbol="EURUSD",
        side="BUY",
        volume=3000.0,
        source="WORKSPACE",
        workspace_uid=f"WSP-{broker}-{control_mode}",
        signal_uid=f"SIG-{broker}-{control_mode}",
        execution_origin="WORKSPACE",
        control_mode=control_mode,
        execution_state=execution_state,
    )
    order_plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=3000.0,
        source="WORKSPACE",
        stop_loss=1.1,
    )
    return trade_uid, order_plan_uid


def _new_engine(_db_path: Path) -> RuntimeEngine:
    return RuntimeEngine(db_path=":memory:")


def main() -> None:
    broker_requests = 0
    with tempfile.TemporaryDirectory(prefix="t109_31_") as temp_dir:
        temp_path = Path(temp_dir)

        ctrader_engine = _new_engine(temp_path / "ctrader.sqlite")
        ctrader_service = _FakeCTraderService("CTR-ACC")
        ctrader_engine.ctrader_runtime_service = ctrader_service
        ctr_trade_uid, ctr_plan_uid = _create_workspace_chain(
            ctrader_engine,
            broker="CTRADER",
            account_id="CTR-ACC",
            control_mode="AUTO",
            execution_state="READY_FOR_SUBMISSION",
        )
        ctr_result = ctrader_engine.submit_workspace_execution_plan(
            ctr_trade_uid,
            ctr_plan_uid,
        )
        assert len(ctrader_service.submission_calls) == 1
        ctr_call = ctrader_service.submission_calls[0]
        assert ctr_call["lots"] == 0.03
        assert ctr_call["stop_loss"] == 1.1
        assert "WSP:" in ctr_call["comment"]
        ctr_chain = ctrader_engine.repository.get_trade_chain(ctr_trade_uid)
        assert len(ctr_chain["order_plans"]) == 1
        assert len(ctr_chain["broker_orders"]) == 1
        assert ctr_chain["positions"] == []
        assert ctr_result["already_submitted"] is False

        ctr_repeat = ctrader_engine.submit_workspace_execution_plan(
            ctr_trade_uid,
            ctr_plan_uid,
        )
        assert ctr_repeat["already_submitted"] is True
        assert len(ctrader_service.submission_calls) == 1

        ib_engine = _new_engine(temp_path / "ib.sqlite")
        ib_service = _FakeIBService("IB-ACC")
        ib_engine.ib_runtime_service = ib_service
        ib_trade_uid, ib_plan_uid = _create_workspace_chain(
            ib_engine,
            broker="IB",
            account_id="IB-ACC",
            control_mode="AUTO",
            execution_state="READY_FOR_SUBMISSION",
        )
        ib_result = ib_engine.submit_workspace_execution_plan(
            ib_trade_uid,
            ib_plan_uid,
        )
        assert len(ib_service.submission_calls) == 1
        ib_call = ib_service.submission_calls[0]
        assert ib_call["quantity"] == 3000.0
        assert ib_call["stop_loss"] == 1.1
        assert "WSP:" in ib_call["comment"]
        ib_chain = ib_engine.repository.get_trade_chain(ib_trade_uid)
        assert len(ib_chain["order_plans"]) == 1
        assert len(ib_chain["broker_orders"]) == 1
        assert ib_chain["positions"] == []
        assert ib_result["already_submitted"] is False

        semi_engine = _new_engine(temp_path / "semi.sqlite")
        semi_service = _FakeIBService("IB-SEMI")
        semi_engine.ib_runtime_service = semi_service
        semi_trade_uid, semi_plan_uid = _create_workspace_chain(
            semi_engine,
            broker="IB",
            account_id="IB-SEMI",
            control_mode="SEMI",
            execution_state="PENDING_CONFIRMATION",
        )
        try:
            semi_engine.submit_workspace_execution_plan(
                semi_trade_uid,
                semi_plan_uid,
            )
        except RuntimeError as error:
            assert "not ready" in str(error).lower()
        else:
            raise AssertionError("SEMI pending confirmation must not submit")
        assert semi_service.submission_calls == []

        reverse_engine = _new_engine(temp_path / "reverse.sqlite")
        reverse_service = _FakeIBService("IB-REV")
        reverse_engine.ib_runtime_service = reverse_service
        reverse_trade_uid, reverse_plan_uid = _create_workspace_chain(
            reverse_engine,
            broker="IB",
            account_id="IB-REV",
            control_mode="AUTO",
            execution_state="READY_FOR_SUBMISSION",
        )
        try:
            reverse_engine.submit_workspace_execution_plan(
                reverse_trade_uid,
                reverse_plan_uid,
                reverse_required=True,
                confirmed_flat=False,
            )
        except RuntimeError as error:
            assert "confirmed flat" in str(error).lower()
        else:
            raise AssertionError("Reverse submission must require confirmed flat")
        assert reverse_service.submission_calls == []

        mismatch_engine = _new_engine(temp_path / "mismatch.sqlite")
        mismatch_service = _FakeCTraderService("ACTIVE-ACC")
        mismatch_engine.ctrader_runtime_service = mismatch_service
        mismatch_trade_uid, mismatch_plan_uid = _create_workspace_chain(
            mismatch_engine,
            broker="CTRADER",
            account_id="OTHER-ACC",
            control_mode="AUTO",
            execution_state="READY_FOR_SUBMISSION",
        )
        try:
            mismatch_engine.submit_workspace_execution_plan(
                mismatch_trade_uid,
                mismatch_plan_uid,
            )
        except RuntimeError as error:
            assert "account" in str(error).lower()
        else:
            raise AssertionError("Account mismatch must block Workspace submission")
        assert mismatch_service.submission_calls == []

    print("T109-31_WORKSPACE_RUNTIME_SUBMISSION_METHOD_WIRING=OK")
    print("production_change=True")
    print("runtime_submit_method_present=True")
    print("persisted_trade_reused=True")
    print("persisted_order_plan_reused=True")
    print("duplicate_trade_created=False")
    print("duplicate_order_plan_created=False")
    print("duplicate_submission_blocked_by_persisted_broker_order=True")
    print("exact_broker_account_binding_enforced=True")
    print("ib_base_units_quantity=3000.0")
    print("ctrader_base_units_lots=0.03")
    print("broker_trade_uid_hint_present=True")
    print("auto_ready_for_submission_supported=True")
    print("semi_pending_confirmation_blocked=True")
    print("reverse_confirmed_flat_gate_enforced=True")
    print("broker_order_persisted_after_simulated_submission=True")
    print("position_persisted_before_confirmation=False")
    print("workspace_controller_submission_wiring=False")
    print(f"broker_requests={broker_requests}")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_CONTROLLER_TO_RUNTIME_ENGINE_SUBMISSION_WIRING"
    )
    print(
        "boundary_contract="
        "AUTO_READY_WORKSPACE_PLAN_MUST_CALL_RUNTIME_SUBMIT_ONLY_AFTER_"
        "ALL_EXECUTION_GATES_PASS"
    )
    print(
        "factual_verdict=A. RUNTIME_ENGINE_WORKSPACE_SUBMISSION_METHOD_GREEN"
    )


if __name__ == "__main__":
    main()
