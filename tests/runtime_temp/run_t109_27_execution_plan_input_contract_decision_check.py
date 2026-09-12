# -*- coding: utf-8 -*-
"""T109-27 — execution-plan input contract decision, TEST_ONLY."""

from __future__ import annotations

import importlib
import inspect
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

controller_module = importlib.import_module("core.algorithm_workspace_controller")
signal_module = importlib.import_module("core.workspace_signal")
runtime_db_module = importlib.import_module("engine.db.runtime_db")
repository_module = importlib.import_module("engine.runtime_repository")

AlgorithmWorkspaceController = controller_module.AlgorithmWorkspaceController
WorkspaceSignalRecord = signal_module.WorkspaceSignalRecord
WorkspaceTradeIntent = signal_module.WorkspaceTradeIntent
SCHEMA_VERSION = runtime_db_module.SCHEMA_VERSION
connect_runtime_db = runtime_db_module.connect_runtime_db
RuntimeRepository = repository_module.RuntimeRepository

TEST_ID = "T109-27"
FACTUAL_VERDICT = "A. MINIMAL_EXECUTION_PLAN_INPUT_CONTRACT_IDENTIFIED"
FIRST_UNRESOLVED_BOUNDARY = "EXECUTION_PLAN_PERSISTENCE_SCHEMA_AND_CREATION_WIRING"
BOUNDARY_CONTRACT = (
    "POST_RISK_ALLOW_MUST_RETAIN_TRADE_UID_AND_PERSIST_STOP_LOSS_WITH_"
    "EXECUTION_PLAN_BEFORE_ANY_BROKER_SUBMISSION"
)


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def main() -> None:
    intent_parameters = set(inspect.signature(WorkspaceTradeIntent).parameters)
    record_parameters = set(inspect.signature(WorkspaceSignalRecord).parameters)
    persist_method = getattr(
        AlgorithmWorkspaceController,
        "_persist_workspace_trade_after_risk_allow",
    )
    controller_source = inspect.getsource(persist_method)
    create_trade_source = inspect.getsource(RuntimeRepository.create_trade)
    create_order_plan_source = inspect.getsource(RuntimeRepository.create_order_plan)

    assert "stop_loss" in intent_parameters
    assert "stop_loss" not in record_parameters
    assert "trade_uid = create_trade(" not in controller_source
    assert "create_trade(" in controller_source
    assert "return trade_uid" in create_trade_source

    with tempfile.TemporaryDirectory(prefix="t109_27_") as tmp_dir:
        db_path = Path(tmp_dir) / "runtime.db"
        connection = connect_runtime_db(db_path)
        order_plan_columns = _columns(connection, "order_plans")
        trade_columns = _columns(connection, "trades")
        connection.close()

    assert "trade_uid" in order_plan_columns
    assert "stop_loss" not in order_plan_columns
    assert "workspace_uid" in trade_columns
    assert "signal_uid" in trade_columns

    # Contract decision:
    # 1) do not add trade_uid to WorkspaceSignalRecord; it is post-risk data.
    # 2) retain create_trade() return locally in controller;
    # 3) preserve stop_loss from WorkspaceTradeIntent into WorkspaceSignalRecord so the
    #    observer receives the causal protection input;
    # 4) extend order_plans with nullable stop_loss for restart-safe persistence;
    # 5) create/reuse plan after trade persistence; broker submission stays absent.
    recommended_record_extension = "stop_loss"
    recommended_local_execution_root = "trade_uid=create_trade_return_value"
    recommended_order_plan_extension = "stop_loss"
    new_execution_entity_required = False
    workspace_trade_lookup_required = False
    broker_submission_required = False

    assert "INSERT INTO order_plans" in create_order_plan_source
    assert recommended_record_extension == "stop_loss"
    assert recommended_local_execution_root == "trade_uid=create_trade_return_value"
    assert recommended_order_plan_extension == "stop_loss"
    assert not new_execution_entity_required
    assert not workspace_trade_lookup_required
    assert not broker_submission_required

    print(f"{TEST_ID}_EXECUTION_PLAN_INPUT_CONTRACT_DECISION=OK")
    print("test_scope=TEST_ONLY")
    print(f"schema_version={SCHEMA_VERSION}")
    print("trade_intent_stop_loss_present=True")
    print("signal_record_stop_loss_present=False")
    print("create_trade_returns_trade_uid=True")
    print("controller_retains_trade_uid=False")
    print("order_plan_trade_uid_link_present=True")
    print("order_plan_stop_loss_present=False")
    print("recommended_signal_record_extension=stop_loss")
    print(
        "recommended_trade_uid_contract="
        "retain_create_trade_return_value_locally"
    )
    print("recommended_order_plan_extension=stop_loss")
    print("workspace_trade_lookup_required=False")
    print("new_execution_entity_required=False")
    print("broker_submission_wiring=False")
    print("production_change=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
