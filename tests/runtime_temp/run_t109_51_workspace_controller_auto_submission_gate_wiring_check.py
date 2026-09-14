from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
    WORKSPACE_DATA_MODE_BROKER,
)
from core.algorithm_workspace_controller import (  # noqa: E402
    AlgorithmWorkspaceController,
    WorkspaceSignalRecord,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.broker_position import (  # noqa: E402
    BrokerPosition,
    BrokerPositionSnapshot,
)


class _FakeRuntimeEngine:
    def __init__(self) -> None:
        self.snapshot_mode = "FLAT"
        self.snapshot_calls = 0
        self.submit_calls: list[dict[str, object]] = []

    def get_workspace_broker_positions_snapshot(
        self,
        broker_name: str,
        account_id: str,
    ) -> BrokerPositionSnapshot:
        self.snapshot_calls += 1
        if self.snapshot_mode == "FAIL":
            return BrokerPositionSnapshot.failure_result(
                broker_name,
                account_id,
                "TEST_ONLY failure",
            )
        if self.snapshot_mode == "EXPOSURE":
            position = BrokerPosition(
                broker=broker_name,
                account_id=account_id,
                account_mode="PAPER",
                position_id="P1",
                symbol_name="EURUSD",
                side="BUY",
                volume=3000.0,
            )
            return BrokerPositionSnapshot.success_result(
                broker_name,
                account_id,
                [position],
            )
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
        call = {
            "trade_uid": trade_uid,
            "order_plan_uid": order_plan_uid,
            "reverse_required": reverse_required,
            "confirmed_flat": confirmed_flat,
        }
        self.submit_calls.append(call)
        return call


def _controller(
    engine: _FakeRuntimeEngine,
    *,
    control_mode: str = WORKSPACE_CONTROL_MODE_AUTO,
) -> AlgorithmWorkspaceController:
    controller = object.__new__(AlgorithmWorkspaceController)
    controller._runtime_engine = engine
    controller._workspace_submission_identities = {("W1", "S1"): ("T1", "O1")}
    controller._runtimes = cast(
        dict[str, WorkspaceRuntime],
        cast(
            object,
            {
                "W1": SimpleNamespace(
                    context=SimpleNamespace(
                        workspace_uid="W1",
                        broker="IB",
                        account_id="DU123",
                        symbol="EURUSD",
                        data_mode=WORKSPACE_DATA_MODE_BROKER,
                        control_mode=control_mode,
                    )
                )
            },
        ),
    )
    return controller


def _record() -> WorkspaceSignalRecord:
    return cast(
        WorkspaceSignalRecord,
        cast(
            object,
            SimpleNamespace(
                workspace_uid="W1",
                signal_uid="S1",
            ),
        ),
    )


def main() -> None:
    record = _record()

    flat_engine = _FakeRuntimeEngine()
    flat_controller = _controller(flat_engine)
    # noinspection PyProtectedMember
    flat_controller._submit_workspace_auto_after_same_call_flat(record)
    assert flat_engine.snapshot_calls == 1
    assert len(flat_engine.submit_calls) == 1
    flat_call = flat_engine.submit_calls[0]
    assert flat_call["trade_uid"] == "T1"
    assert flat_call["order_plan_uid"] == "O1"
    assert flat_call["reverse_required"] is True
    assert flat_call["confirmed_flat"] is True

    exposure_engine = _FakeRuntimeEngine()
    exposure_engine.snapshot_mode = "EXPOSURE"
    exposure_controller = _controller(exposure_engine)
    # noinspection PyProtectedMember
    exposure_controller._submit_workspace_auto_after_same_call_flat(record)
    assert exposure_engine.snapshot_calls == 1
    assert exposure_engine.submit_calls == []

    failure_engine = _FakeRuntimeEngine()
    failure_engine.snapshot_mode = "FAIL"
    failure_controller = _controller(failure_engine)
    # noinspection PyProtectedMember
    failure_controller._submit_workspace_auto_after_same_call_flat(record)
    assert failure_engine.snapshot_calls == 1
    assert failure_engine.submit_calls == []

    semi_engine = _FakeRuntimeEngine()
    semi_controller = _controller(
        semi_engine,
        control_mode=WORKSPACE_CONTROL_MODE_SEMI,
    )
    # noinspection PyProtectedMember
    semi_controller._submit_workspace_auto_after_same_call_flat(record)
    assert semi_engine.snapshot_calls == 0
    assert semi_engine.submit_calls == []

    source = (PROJECT_ROOT / "core" / "algorithm_workspace_controller.py").read_text(
        encoding="utf-8"
    )
    assert "self._submit_workspace_auto_after_same_call_flat(record)" in source
    assert "submit_workspace_execution_plan" in source
    assert "reverse_required=True" in source
    assert "confirmed_flat=True" in source

    print("T109-51_WORKSPACE_CONTROLLER_AUTO_SUBMISSION_GATE_WIRING=OK")
    print("production_change=True")
    print("controller_auto_submit_wiring_present=True")
    print("retained_trade_order_plan_identity_used=True")
    print("same_call_confirmed_flat_gate_precedes_submit=True")
    print("fresh_flat_submits_once=True")
    print("matching_exposure_blocks_submit=True")
    print("terminal_failure_blocks_submit=True")
    print("semi_mode_does_not_snapshot_or_submit=True")
    print("reverse_guard_engaged=True")
    print("confirmed_flat_forwarded=True")
    print("duplicate_trade_or_order_plan_creation_added=False")
    print("broker_requests=0")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_BROKER_ORDER_CONFIRMATION_TO_POSITION_LIFECYCLE"
    )
    print(
        "boundary_contract="
        "SUBMITTED_WORKSPACE_BROKER_ORDER_MUST_PROGRESS_FROM_BROKER_"
        "CONFIRMATION_OR_RECONCILIATION_TO_PERSISTED_POSITION_WITHOUT_"
        "LOSING_TRADE_ORDER_PLAN_IDENTITY"
    )
    print(
        "factual_verdict=A. " "WORKSPACE_CONTROLLER_AUTO_SUBMISSION_GATE_WIRING_GREEN"
    )


if __name__ == "__main__":
    main()
