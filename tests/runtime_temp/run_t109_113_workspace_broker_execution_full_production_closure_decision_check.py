"""T109-113 — Workspace Broker Execution Full Production Closure Decision.

TEST_ONLY closure decision повторно проходить безпечний post-risk AUTO/SEMI
маршрут T109-112 через фактичний production controller, але замінює broker
position/submission endpoints локальним evidence engine. Додатково перевіряє,
що production RuntimeEngine містить уже прийняті identity, duplicate-submit,
timeout, terminal-failure та reconciliation fail-closed маршрути.

Тест не викликає broker, не змінює production, schema, Replay, thresholds або
settings. Якщо всі вже реалізовані межі на місці, broker execution boundary
вважається закритою без нової production зміни, а наступною межею стає
ROADMAP109_CANONICAL_DOCUMENTATION_UPDATE.
"""

from __future__ import annotations

import sqlite3
import sys
from inspect import getfile
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TEMP = PROJECT_ROOT / "tests" / "runtime_temp"
for import_root in (PROJECT_ROOT, RUNTIME_TEMP):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from core.algorithm_workspace import (  # noqa: E402
    WORKSPACE_CONTROL_MODE_AUTO,
    WORKSPACE_CONTROL_MODE_SEMI,
)
from core.workspace_runtime import WorkspaceRuntime  # noqa: E402
from engine.db.runtime_db import SCHEMA_VERSION, connect_runtime_db  # noqa: E402
from engine.runtime_repository import RuntimeRepository  # noqa: E402
from run_t109_112_workspace_broker_execution_post_risk_end_to_end_anatomy_check import (  # noqa: E402,E501
    _run_mode,
)

TEST_ID = "T109-113"
FIRST_UNRESOLVED_BOUNDARY = "ROADMAP109_CANONICAL_DOCUMENTATION_UPDATE"
BOUNDARY_CONTRACT = (
    "WORKSPACE_BROKER_EXECUTION_PRODUCTION_IS_CLOSED_FROM_POST_RISK_ALLOW_"
    "THROUGH_CAUSAL_TRADE_ORDER_PLAN_AUTO_SAME_CALL_FLAT_GATED_DISPATCH_"
    "SEMI_CONFIRMATION_HOLD_AND_IDENTITY_PRESERVING_TERMINAL_RECOVERY_WITH_"
    "NO_ADDITIONAL_PRODUCTION_CHANGE_REQUIRED"
)
FACTUAL_VERDICT = (
    "A. WORKSPACE_BROKER_EXECUTION_FULL_PRODUCTION_CLOSURE_GREEN_WITH_NO_"
    "ADDITIONAL_PRODUCTION_CHANGE_AND_CANONICAL_DOCUMENTATION_AS_NEXT_BOUNDARY"
)


def _read(relative_path: str) -> str:
    """Прочитати фактичний production source від кореня WorkspaceRuntime."""
    production_root = Path(getfile(WorkspaceRuntime)).resolve().parents[1]
    return (production_root / relative_path).read_text(encoding="utf-8")


def main() -> None:
    """Прийняти closure decision для повного Workspace broker execution path."""
    controller_source = _read("core/algorithm_workspace_controller.py")
    engine_source = _read("engine/runtime_engine.py")

    with TemporaryDirectory(prefix="t109_113_") as tmp_dir:
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

    post_risk_identity_path_closed = all(
        (
            auto.accepted,
            auto.risk_decision == "ALLOW",
            auto.execution_state == "READY_FOR_SUBMISSION",
            bool(auto.trade_uid),
            bool(auto.order_plan_uid),
            auto.position_snapshot_calls == 1,
            auto.submission_calls == 1,
            auto.submitted_trade_uid == auto.trade_uid,
            auto.submitted_order_plan_uid == auto.order_plan_uid,
        )
    )
    semi_confirmation_boundary_closed = all(
        (
            semi.accepted,
            semi.risk_decision == "ALLOW",
            semi.execution_state == "PENDING_CONFIRMATION",
            bool(semi.trade_uid),
            bool(semi.order_plan_uid),
            semi.position_snapshot_calls == 0,
            semi.submission_calls == 0,
        )
    )
    controller_production_contract_closed = all(
        token in controller_source
        for token in (
            "signal_record_observer=self._persist_workspace_trade_after_risk_allow",
            'execution_state = "READY_FOR_SUBMISSION"',
            'execution_state = "PENDING_CONFIRMATION"',
            "workspace_same_call_position_snapshot_confirms_flat",
            "_submit_workspace_auto_after_same_call_flat",
        )
    )
    submission_safety_contract_closed = all(
        token in engine_source
        for token in (
            "def submit_workspace_execution_plan(",
            "validate_workspace_broker_binding",
            "existing_orders = [",
            'existing_status == "PENDING_CONFIRMATION"',
            '"resubmit_allowed": False',
            "Workspace reverse submission requires confirmed flat exposure",
        )
    )
    terminal_recovery_contract_closed = all(
        token in engine_source
        for token in (
            "except IBMarketOrderTimeoutError as timeout_error:",
            "except CTraderMarketOrderTimeoutError as timeout_error:",
            "except BrokerTerminalOrderFailure as failure:",
            "def recover_ctrader_workspace_timeout(",
            "def reconcile_workspace_broker_order(",
        )
    )

    actual_broker_requests = auto.broker_requests + semi.broker_requests
    actual_broker_execution_attempted = (
        auto.broker_execution_attempted or semi.broker_execution_attempted
    )
    schema_change_required = SCHEMA_VERSION != 12
    production_change_required = not all(
        (
            post_risk_identity_path_closed,
            semi_confirmation_boundary_closed,
            controller_production_contract_closed,
            submission_safety_contract_closed,
            terminal_recovery_contract_closed,
        )
    )
    workspace_broker_execution_boundary_closed = not production_change_required

    assert post_risk_identity_path_closed
    assert semi_confirmation_boundary_closed
    assert controller_production_contract_closed
    assert submission_safety_contract_closed
    assert terminal_recovery_contract_closed
    assert not schema_change_required
    assert not production_change_required
    assert workspace_broker_execution_boundary_closed
    assert actual_broker_requests == 0
    assert not actual_broker_execution_attempted

    print("T109-113_WORKSPACE_BROKER_EXECUTION_FULL_PRODUCTION_CLOSURE_DECISION=OK")
    print("test_scope_test_only=True")
    print("production_change=False")
    print(f"schema_version={SCHEMA_VERSION}")
    print(f"post_risk_identity_path_closed={post_risk_identity_path_closed}")
    print(
        "semi_confirmation_boundary_closed="
        f"{semi_confirmation_boundary_closed}"
    )
    print(
        "controller_production_contract_closed="
        f"{controller_production_contract_closed}"
    )
    print(
        "submission_safety_contract_closed="
        f"{submission_safety_contract_closed}"
    )
    print(
        "terminal_recovery_contract_closed="
        f"{terminal_recovery_contract_closed}"
    )
    print(
        "workspace_broker_execution_boundary_closed="
        f"{workspace_broker_execution_boundary_closed}"
    )
    print(f"production_change_required={production_change_required}")
    print(f"actual_broker_requests={actual_broker_requests}")
    print(
        "actual_broker_execution_attempted="
        f"{actual_broker_execution_attempted}"
    )
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


def test_t109_113_workspace_broker_execution_full_production_closure() -> None:
    """Запустити T109-113 як pytest test."""
    main()


if __name__ == "__main__":
    main()
