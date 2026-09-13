"""T109-33: retain exact Workspace trade/order-plan identity before submit."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

controller_module = importlib.import_module("core.algorithm_workspace_controller")
workspace_module = importlib.import_module("core.algorithm_workspace")
risk_constants = importlib.import_module("engine.risk.constants")

AlgorithmWorkspaceController = controller_module.AlgorithmWorkspaceController
WORKSPACE_CONTROL_MODE_AUTO = workspace_module.WORKSPACE_CONTROL_MODE_AUTO
WORKSPACE_DATA_MODE_BROKER = workspace_module.WORKSPACE_DATA_MODE_BROKER
RISK_DECISION_ALLOW = risk_constants.RISK_DECISION_ALLOW


class _Repository:
    def __init__(self) -> None:
        self.trade_uid = "trade-t109-33"
        self.order_plan_uid = "plan-t109-33"
        self.order_plans: list[dict[str, Any]] = []
        self.create_trade_calls = 0
        self.create_order_plan_calls = 0

    def create_trade(self, **_kwargs: Any) -> str:
        self.create_trade_calls += 1
        return self.trade_uid

    def get_trade_chain(self, trade_uid: str) -> dict[str, Any]:
        assert trade_uid == self.trade_uid
        return {
            "trade": {"trade_uid": self.trade_uid},
            "order_plans": [dict(plan) for plan in self.order_plans],
            "broker_orders": [],
            "positions": [],
        }

    def create_order_plan(self, **kwargs: Any) -> str:
        self.create_order_plan_calls += 1
        self.order_plans.append(
            {
                "order_plan_uid": self.order_plan_uid,
                "trade_uid": kwargs["trade_uid"],
                "order_type": kwargs["order_type"],
                "side": kwargs["side"],
                "volume": float(kwargs["volume"]),
                "stop_loss": kwargs["stop_loss"],
                "source": kwargs["source"],
            }
        )
        return self.order_plan_uid


def _controller(repository: _Repository) -> Any:
    controller = object.__new__(AlgorithmWorkspaceController)
    controller._workspace_submission_identities = {}
    controller._runtimes = {
        "workspace-t109-33": SimpleNamespace(
            context=SimpleNamespace(control_mode=WORKSPACE_CONTROL_MODE_AUTO)
        )
    }
    controller._runtime_engine = SimpleNamespace(repository=repository)
    return controller


def _record() -> Any:
    return SimpleNamespace(
        accepted=True,
        source_mode=WORKSPACE_DATA_MODE_BROKER,
        risk_decision=RISK_DECISION_ALLOW,
        workspace_uid="workspace-t109-33",
        signal_uid="signal-t109-33",
        broker="IB",
        account_id="DU123456",
        symbol="EURUSD",
        direction="BUY",
        approved_volume=3000.0,
        stop_loss=1.1,
    )


def main() -> None:
    repository = _Repository()
    controller = _controller(repository)
    record = _record()

    persist = getattr(controller, "_persist_workspace_trade_after_risk_allow")
    identity_for_signal = getattr(
        controller,
        "_workspace_submission_identity_for_signal",
    )

    persist(record)
    first_identity = identity_for_signal(record.workspace_uid, record.signal_uid)
    assert first_identity == (repository.trade_uid, repository.order_plan_uid)
    assert repository.create_order_plan_calls == 1

    persist(record)
    second_identity = identity_for_signal(record.workspace_uid, record.signal_uid)
    assert second_identity == first_identity
    assert repository.create_order_plan_calls == 1

    conflict_blocked = False
    remember_identity = getattr(
        controller,
        "_remember_workspace_submission_identity",
    )
    try:
        remember_identity(
            record.workspace_uid,
            record.signal_uid,
            repository.trade_uid,
            "different-plan",
        )
    except RuntimeError:
        conflict_blocked = True
    assert conflict_blocked

    print("T109-33_WORKSPACE_CONTROLLER_ORDER_PLAN_IDENTITY_RETENTION=OK")
    print("production_change=True")
    print("trade_uid_retained=True")
    print("new_order_plan_uid_retained=True")
    print("existing_order_plan_uid_recovered=True")
    print("workspace_submission_identity_pair_available=True")
    print("duplicate_order_plan_created=False")
    print("conflicting_retained_identity_rejected=True")
    print("controller_runtime_submit_called=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_CONTROLLER_TO_RUNTIME_ENGINE_SUBMISSION_GATE"
    )
    print(
        "boundary_contract="
        "AUTO_READY_WORKSPACE_SIGNAL_MUST_PASS_EXECUTION_GATES_BEFORE_"
        "CONTROLLER_CALLS_RUNTIME_SUBMIT_WITH_EXACT_RETAINED_IDENTITY"
    )
    print("factual_verdict=A. WORKSPACE_ORDER_PLAN_IDENTITY_RETENTION_GREEN")


if __name__ == "__main__":
    main()
