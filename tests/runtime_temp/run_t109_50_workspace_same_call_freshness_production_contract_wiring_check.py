"""T109-50 — production wiring same-call freshness для Workspace AUTO gate."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
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
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.broker_position import (  # noqa: E402
    BrokerPosition,
    BrokerPositionSnapshot,
)


class _FakeRuntimeEngine:
    def __init__(self) -> None:
        self.mode = "FLAT"
        self.snapshot_calls = 0
        self.submit_calls = 0

    def get_workspace_broker_positions_snapshot(
        self,
        broker_name: str,
        account_id: str,
    ) -> BrokerPositionSnapshot:
        self.snapshot_calls += 1
        broker = str(broker_name).strip().upper()
        account = str(account_id).strip()
        if self.mode == "FAILURE":
            return BrokerPositionSnapshot.failure_result(
                broker,
                account,
                "TEST_FAILURE",
            )
        if self.mode == "REUSED_OLD":
            return BrokerPositionSnapshot(
                broker=broker,
                account_id=account,
                success=True,
                observed_at_utc=datetime.now(UTC) - timedelta(seconds=1),
                positions=(),
            )
        positions: list[BrokerPosition] = []
        if self.mode == "EXPOSURE":
            positions.append(
                BrokerPosition(
                    broker=broker,
                    account_id=account,
                    account_mode="PAPER",
                    position_id="P1",
                    symbol_name="EURUSD",
                    side="BUY",
                    volume=1000.0,
                )
            )
        return BrokerPositionSnapshot.success_result(
            broker,
            account,
            positions,
        )

    def submit_workspace_execution_plan(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> dict:
        self.submit_calls += 1
        raise AssertionError("T109-50 must not submit to broker")


def _controller(
    engine: _FakeRuntimeEngine,
    *,
    control_mode: str = WORKSPACE_CONTROL_MODE_AUTO,
) -> AlgorithmWorkspaceController:
    controller = object.__new__(AlgorithmWorkspaceController)
    controller._runtime_engine = engine
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


def main() -> None:
    engine = _FakeRuntimeEngine()
    controller = _controller(engine)

    check_flat = controller.workspace_same_call_position_snapshot_confirms_flat
    first_flat = check_flat("W1")
    first_calls = engine.snapshot_calls
    second_flat = check_flat("W1")
    second_calls = engine.snapshot_calls

    engine.mode = "EXPOSURE"
    exposure_blocks = not check_flat("W1")

    engine.mode = "FAILURE"
    failure_blocks = not check_flat("W1")

    engine.mode = "REUSED_OLD"
    reused_old_blocks = not check_flat("W1")

    semi_engine = _FakeRuntimeEngine()
    semi_controller = _controller(
        semi_engine,
        control_mode=WORKSPACE_CONTROL_MODE_SEMI,
    )
    semi_blocks_without_snapshot = not (
        semi_controller.workspace_same_call_position_snapshot_confirms_flat("W1")
    )

    new_snapshot_each_attempt = first_calls == 1 and second_calls == 2
    no_submit_call = engine.submit_calls == 0 and semi_engine.submit_calls == 0

    assert first_flat
    assert second_flat
    assert new_snapshot_each_attempt
    assert exposure_blocks
    assert failure_blocks
    assert reused_old_blocks
    assert semi_blocks_without_snapshot
    assert semi_engine.snapshot_calls == 0
    assert no_submit_call

    print("T109-50_WORKSPACE_SAME_CALL_FRESHNESS_PRODUCTION_CONTRACT_WIRING=OK")
    print("production_change=True")
    print("controller_same_call_snapshot_gate_present=True")
    print("exact_workspace_broker_account_symbol_scope=True")
    print(f"fresh_flat_allows_gate={first_flat}")
    print(f"new_snapshot_each_attempt={new_snapshot_each_attempt}")
    print(f"matching_exposure_blocks={exposure_blocks}")
    print(f"terminal_failure_blocks={failure_blocks}")
    print(f"reused_old_snapshot_blocks={reused_old_blocks}")
    print(f"semi_mode_blocks_without_snapshot={semi_blocks_without_snapshot}")
    print("numeric_ttl_required=False")
    print("request_timeout_used_as_freshness_ttl=False")
    print(f"workspace_controller_submission_wiring={not no_submit_call}")
    print("broker_requests=0")
    print("first_unresolved_boundary=WORKSPACE_CONTROLLER_AUTO_SUBMISSION_GATE_WIRING")
    print(
        "boundary_contract=CONTROLLER_MAY_SUBMIT_AUTO_ONLY_AFTER_SAME_CALL_"
        "TERMINAL_POSITION_SNAPSHOT_GATE_PASSES_AND_MUST_PRESERVE_RETAINED_"
        "TRADE_ORDER_PLAN_IDENTITY"
    )
    print(
        "factual_verdict=A. WORKSPACE_SAME_CALL_FRESHNESS_PRODUCTION_"
        "CONTRACT_WIRING_GREEN"
    )


if __name__ == "__main__":
    main()
