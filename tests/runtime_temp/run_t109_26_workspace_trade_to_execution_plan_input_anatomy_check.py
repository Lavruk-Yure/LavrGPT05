# -*- coding: utf-8 -*-
"""T109-26: anatomy persisted Workspace trade -> execution plan inputs."""

from __future__ import annotations

import importlib
import inspect
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

workspace_signal = importlib.import_module("core.workspace_signal")
controller_module = importlib.import_module("core.algorithm_workspace_controller")
runtime_module = importlib.import_module("core.workspace_runtime")
runtime_db = importlib.import_module("engine.db.runtime_db")
runtime_repository = importlib.import_module("engine.runtime_repository")

WorkspaceTradeIntent = workspace_signal.WorkspaceTradeIntent
WorkspaceSignalRecord = workspace_signal.WorkspaceSignalRecord
AlgorithmWorkspaceController = controller_module.AlgorithmWorkspaceController
WorkspaceRuntime = runtime_module.WorkspaceRuntime
RuntimeRepository = runtime_repository.RuntimeRepository
connect_runtime_db = runtime_db.connect_runtime_db

TEST_ID = "T109-26"
FACTUAL_VERDICT = "C. EXECUTION_PLAN_INPUTS_NOT_PRESERVED_END_TO_END"
FIRST_UNRESOLVED_BOUNDARY = "WORKSPACE_TRADE_TO_EXECUTION_PLAN_INPUT_CONTRACT"
BOUNDARY_CONTRACT = (
    "PERSISTED_WORKSPACE_TRADE_AND_PROTECTION_INPUTS_MUST_BE_AVAILABLE_"
    "BEFORE_EXECUTION_PLAN_CREATION"
)


def _field_names(model: type) -> set[str]:
    dataclass_fields = getattr(model, "__dataclass_fields__")
    return set(dataclass_fields)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def main() -> None:
    intent_fields = _field_names(WorkspaceTradeIntent)
    record_fields = _field_names(WorkspaceSignalRecord)

    assert "stop_loss" in intent_fields
    assert "requested_volume" in intent_fields
    assert "stop_loss" not in record_fields
    assert "trade_intent" not in record_fields
    assert "approved_volume" in record_fields
    assert "signal_uid" in record_fields
    assert "workspace_uid" in record_fields

    record_signal = getattr(WorkspaceRuntime, "_record_signal")
    record_signal_source = inspect.getsource(record_signal)
    assert "proposal.trade_intent" in record_signal_source
    assert "approved_volume=" in record_signal_source
    assert "stop_loss=" not in record_signal_source
    assert "self.signal_record_observer(record)" in record_signal_source

    persist_workspace_trade = getattr(
        AlgorithmWorkspaceController,
        "_persist_workspace_trade_after_risk_allow",
    )
    persist_source = inspect.getsource(persist_workspace_trade)
    assert "create_trade(" in persist_source
    assert "trade_uid = create_trade(" not in persist_source
    assert "create_order_plan(" not in persist_source
    assert "stop_loss" not in persist_source

    create_plan_signature = inspect.signature(RuntimeRepository.create_order_plan)
    create_plan_parameters = set(create_plan_signature.parameters)
    assert "trade_uid" in create_plan_parameters
    assert "order_type" in create_plan_parameters
    assert "side" in create_plan_parameters
    assert "volume" in create_plan_parameters
    assert "stop_loss" not in create_plan_parameters

    connection = connect_runtime_db(":memory:")
    try:
        trade_columns = _table_columns(connection, "trades")
        plan_columns = _table_columns(connection, "order_plans")
    finally:
        connection.close()

    assert "workspace_uid" in trade_columns
    assert "signal_uid" in trade_columns
    assert "execution_state" in trade_columns
    assert "trade_uid" in plan_columns
    assert "stop_loss" not in plan_columns
    assert "workspace_uid" not in plan_columns
    assert "signal_uid" not in plan_columns

    repository_source = inspect.getsource(RuntimeRepository)
    workspace_lookup_present = (
        "def get_trade_by_workspace_signal" in repository_source
        or "def get_workspace_trade" in repository_source
    )
    assert not workspace_lookup_present

    print(f"{TEST_ID}_WORKSPACE_TRADE_TO_EXECUTION_PLAN_INPUT_ANATOMY=OK")
    print("test_scope=TEST_ONLY")
    print("workspace_trade_persistence_present=True")
    print("workspace_trade_identity_persisted=True")
    print("create_trade_return_value_retained=False")
    print("workspace_trade_lookup_by_causal_key_present=False")
    print("trade_intent_stop_loss_present=True")
    print("signal_record_stop_loss_present=False")
    print("signal_record_trade_intent_present=False")
    print("order_plan_stop_loss_field_present=False")
    print("order_plan_trade_uid_link_present=True")
    print("broker_submission_wiring=False")
    print("broker_requests=0")
    print(f"first_unresolved_boundary={FIRST_UNRESOLVED_BOUNDARY}")
    print(f"boundary_contract={BOUNDARY_CONTRACT}")
    print(f"factual_verdict={FACTUAL_VERDICT}")


if __name__ == "__main__":
    main()
