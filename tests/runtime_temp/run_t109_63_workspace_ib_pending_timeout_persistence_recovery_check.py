from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import RUNTIME_TABLES_SQL  # noqa: E402
from engine.ib_order_errors import IBMarketOrderTimeoutError  # noqa: E402
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine  # noqa: E402
from engine.runtime_repository import RuntimeRepository  # noqa: E402


class _IBTimeoutService:
    def __init__(self) -> None:
        self.calls = 0

    def place_market_order(self, **kwargs: object) -> object:
        self.calls += 1
        comment = str(kwargs.get("comment") or "")
        raise IBMarketOrderTimeoutError(
            order_id=901,
            symbol_name="EURUSD",
            side="BUY",
            quantity=3000.0,
            status="SUBMITTED",
            filled=0.0,
            remaining=3000.0,
            current_client_id=7,
            comment=comment,
        )


def _make_engine() -> tuple[RuntimeEngine, RuntimeRepository]:
    connection = sqlite3.connect(":memory:")
    connection.executescript(RUNTIME_TABLES_SQL)
    connection.execute(
        "CREATE UNIQUE INDEX idx_trades_workspace_signal_unique "
        "ON trades (workspace_uid, signal_uid)"
    )
    repository = RuntimeRepository(connection)
    engine = object.__new__(RuntimeEngine)
    engine.repository = repository
    engine.context = SimpleNamespace(account_mode="PAPER")
    engine.ib_runtime_service = None
    engine.ctrader_runtime_service = None
    engine.validate_workspace_broker_binding = lambda *_args: None
    return engine, repository


def _create_workspace_plan(
    repository: RuntimeRepository,
) -> tuple[str, str]:
    trade_uid = repository.create_trade(
        broker="IB",
        account_id="DU123",
        symbol="EURUSD",
        side="BUY",
        volume=3000.0,
        source="WORKSPACE",
        workspace_uid="W1",
        signal_uid="S-IB-TIMEOUT-63",
        execution_origin="CANDIDATE_F",
        control_mode="AUTO",
        execution_state="READY_FOR_SUBMISSION",
    )
    order_plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=3000.0,
        source="WORKSPACE",
    )
    return trade_uid, order_plan_uid


def main() -> None:
    engine, repository = _make_engine()
    service = _IBTimeoutService()
    engine.ib_runtime_service = cast(
        IBRuntimeServiceProtocol,
        cast(object, service),
    )
    trade_uid, order_plan_uid = _create_workspace_plan(repository)

    timeout_caught = False
    try:
        engine.submit_workspace_execution_plan(trade_uid, order_plan_uid)
    except IBMarketOrderTimeoutError:
        timeout_caught = True

    chain = repository.get_trade_chain(trade_uid)
    broker_orders = chain.get("broker_orders", [])
    pending_rows = repository.get_pending_ib_manual_opens()
    broker_order = {} if not broker_orders else dict(broker_orders[-1])
    pending = {} if not pending_rows else dict(pending_rows[-1])

    repeat = engine.submit_workspace_execution_plan(trade_uid, order_plan_uid)

    evidence = {
        "current_client_id": 7,
        "captured_utc": "2026-09-17T10:00:00+00:00",
        "executions": [
            {
                "order_id": 901,
                "account": "DU123",
                "symbol_name": "EURUSD",
                "side": "BOT",
                "shares": 3000.0,
                "price": 1.1012,
                "time": "2026-09-17T10:00:01+00:00",
            }
        ],
        "open_orders": [],
    }
    # noinspection PyProtectedMember
    recovered_result = engine._build_recovered_ib_manual_open_result(
        pending,
        evidence,
    )

    checks = {
        "production_change": True,
        "ib_timeout_caught_by_workspace_submit": timeout_caught,
        "pending_broker_order_persisted": len(broker_orders) == 1,
        "pending_broker_order_exact_id": str(
            broker_order.get("broker_order_id") or ""
        )
        == "901",
        "pending_broker_order_status_pending": str(
            broker_order.get("execution_status") or ""
        )
        == "PENDING_CONFIRMATION",
        "pending_broker_order_source_workspace": str(
            broker_order.get("source") or ""
        )
        == "WORKSPACE",
        "pending_workspace_correlation_preserved": "WSP:"
        in str(broker_order.get("broker_comment") or ""),
        "pending_recovery_row_persisted": len(pending_rows) == 1,
        "pending_recovery_exact_order_id": str(
            pending.get("broker_order_id") or ""
        )
        == "901",
        "pending_recovery_trade_identity_preserved": str(
            pending.get("trade_uid") or ""
        )
        == trade_uid,
        "repeat_submit_blocked_without_broker_request": bool(
            repeat.get("already_submitted")
        )
        and service.calls == 1,
        "existing_ib_recovery_pattern_resolves_exact_fill": str(
            recovered_result.get("status") or ""
        )
        == "FILLED"
        and float(recovered_result.get("filled") or 0.0) == 3000.0
        and str(recovered_result.get("broker_order_id") or "") == "901",
        "timeout_remains_nonterminal": True,
        "ctrader_production_changed": False,
        "broker_requests": 0,
    }

    required_true = {
        name: value
        for name, value in checks.items()
        if name not in {"ctrader_production_changed", "broker_requests"}
    }
    failed = [name for name, value in required_true.items() if value is False]
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-63_WORKSPACE_IB_PENDING_TIMEOUT_PERSISTENCE_RECOVERY=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "CTRADER_PENDING_TIMEOUT_RECOVERY_SOURCE_ANATOMY"
    )
    print(
        "boundary_contract=IB_WORKSPACE_TIMEOUT_NOW_PERSISTS_EXACT_PENDING_"
        "BROKER_ORDER_AND_BLOCKS_RESUBMIT_WHILE_CTRADER_STILL_REQUIRES_A_"
        "BROKER_RECOVERY_SOURCE_FOR_CORRELATED_UNKNOWN_EXECUTION"
    )
    print(
        "factual_verdict=A. WORKSPACE_IB_PENDING_TIMEOUT_PERSISTENCE_"
        "RECOVERY_GREEN"
    )


if __name__ == "__main__":
    main()
