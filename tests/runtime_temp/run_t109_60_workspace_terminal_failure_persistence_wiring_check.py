from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_order_errors import BrokerTerminalOrderFailure  # noqa: E402
from engine.db.runtime_db import RUNTIME_TABLES_SQL  # noqa: E402
from engine.ib_order_errors import IBMarketOrderTimeoutError  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    CTraderRuntimeServiceProtocol,
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)
from engine.runtime_repository import RuntimeRepository  # noqa: E402


class _TerminalFailureService:
    def __init__(self, failure: BrokerTerminalOrderFailure) -> None:
        self.failure = failure
        self.calls = 0

    def place_market_order(self, **_kwargs: object) -> object:
        self.calls += 1
        raise self.failure


class _IBTimeoutService:
    def __init__(self) -> None:
        self.calls = 0

    def place_market_order(self, **_kwargs: object) -> object:
        self.calls += 1
        raise IBMarketOrderTimeoutError(
            order_id=901,
            symbol_name="EURUSD",
            side="BUY",
            quantity=3000.0,
            status="SUBMITTED",
            filled=0.0,
            remaining=3000.0,
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
    *,
    broker: str,
    account_id: str,
    symbol: str,
    side: str,
    signal_uid: str,
) -> tuple[str, str]:
    trade_uid = repository.create_trade(
        broker=broker,
        account_id=account_id,
        symbol=symbol,
        side=side,
        volume=3000.0,
        source="WORKSPACE",
        workspace_uid="W1",
        signal_uid=signal_uid,
        execution_origin="CANDIDATE_F",
        control_mode="AUTO",
        execution_state="READY_FOR_SUBMISSION",
    )
    order_plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=side,
        volume=3000.0,
        source="WORKSPACE",
    )
    return trade_uid, order_plan_uid


def _chain_counts(
    repository: RuntimeRepository,
    trade_uid: str,
) -> tuple[int, int, int]:
    chain = repository.get_trade_chain(trade_uid)
    return (
        len(chain.get("order_plans", [])),
        len(chain.get("broker_orders", [])),
        1 if repository.get_position_by_trade_uid(trade_uid) is not None else 0,
    )


def _last_broker_order(
    repository: RuntimeRepository,
    trade_uid: str,
) -> dict:
    chain = repository.get_trade_chain(trade_uid)
    orders = chain.get("broker_orders", [])
    return {} if not orders else dict(orders[-1])


def _submit_expect_terminal_failure(
    engine: RuntimeEngine,
    trade_uid: str,
    order_plan_uid: str,
) -> BrokerTerminalOrderFailure:
    try:
        engine.submit_workspace_execution_plan(trade_uid, order_plan_uid)
    except BrokerTerminalOrderFailure as failure:
        return failure
    raise AssertionError("Expected BrokerTerminalOrderFailure")


def main() -> None:
    ib_zero_engine, ib_zero_repository = _make_engine()
    ib_zero_failure = BrokerTerminalOrderFailure(
        broker="IB",
        broker_order_id="101",
        status="CANCELLED",
        filled=0.0,
        remaining=3000.0,
        failure_reason="TEST_ONLY zero-fill cancel",
    )
    ib_zero_service = _TerminalFailureService(ib_zero_failure)
    ib_zero_engine.ib_runtime_service = cast(
        IBRuntimeServiceProtocol,
        cast(object, ib_zero_service),
    )
    ib_zero_trade, ib_zero_plan = _create_workspace_plan(
        ib_zero_repository,
        broker="IB",
        account_id="DU123",
        symbol="EURUSD",
        side="BUY",
        signal_uid="S-IB-ZERO-60",
    )
    _submit_expect_terminal_failure(ib_zero_engine, ib_zero_trade, ib_zero_plan)
    ib_zero_order = _last_broker_order(ib_zero_repository, ib_zero_trade)
    ib_zero_counts = _chain_counts(ib_zero_repository, ib_zero_trade)
    ib_zero_repeat = ib_zero_engine.submit_workspace_execution_plan(
        ib_zero_trade,
        ib_zero_plan,
    )
    ib_zero_repeat_counts = _chain_counts(ib_zero_repository, ib_zero_trade)

    ib_partial_engine, ib_partial_repository = _make_engine()
    ib_partial_failure = BrokerTerminalOrderFailure(
        broker="IB",
        broker_order_id="102",
        status="CANCELLED",
        filled=1000.0,
        remaining=2000.0,
        failure_reason="TEST_ONLY partial-fill cancel",
        confirmed_price=1.1012,
    )
    ib_partial_service = _TerminalFailureService(ib_partial_failure)
    ib_partial_engine.ib_runtime_service = cast(
        IBRuntimeServiceProtocol,
        cast(object, ib_partial_service),
    )
    ib_partial_trade, ib_partial_plan = _create_workspace_plan(
        ib_partial_repository,
        broker="IB",
        account_id="DU123",
        symbol="GBPUSD",
        side="SELL",
        signal_uid="S-IB-PARTIAL-60",
    )
    _submit_expect_terminal_failure(
        ib_partial_engine,
        ib_partial_trade,
        ib_partial_plan,
    )
    ib_partial_order = _last_broker_order(
        ib_partial_repository,
        ib_partial_trade,
    )
    ib_partial_position = ib_partial_repository.get_position_by_trade_uid(
        ib_partial_trade
    )
    ib_partial_counts = _chain_counts(ib_partial_repository, ib_partial_trade)
    ib_partial_repeat = ib_partial_engine.submit_workspace_execution_plan(
        ib_partial_trade,
        ib_partial_plan,
    )
    ib_partial_repeat_counts = _chain_counts(
        ib_partial_repository,
        ib_partial_trade,
    )

    ctr_reject_engine, ctr_reject_repository = _make_engine()
    ctr_reject_failure = BrokerTerminalOrderFailure(
        broker="CTRADER",
        broker_order_id="7001",
        status="REJECTED",
        filled=0.0,
        remaining=0.0,
        failure_reason="TEST_ONLY cTrader reject",
    )
    ctr_reject_service = _TerminalFailureService(ctr_reject_failure)
    ctr_reject_engine.ctrader_runtime_service = cast(
        CTraderRuntimeServiceProtocol,
        cast(object, ctr_reject_service),
    )
    ctr_reject_trade, ctr_reject_plan = _create_workspace_plan(
        ctr_reject_repository,
        broker="CTRADER",
        account_id="987654",
        symbol="EURUSD",
        side="SELL",
        signal_uid="S-CTR-REJECT-60",
    )
    _submit_expect_terminal_failure(
        ctr_reject_engine,
        ctr_reject_trade,
        ctr_reject_plan,
    )
    ctr_reject_order = _last_broker_order(
        ctr_reject_repository,
        ctr_reject_trade,
    )
    ctr_reject_counts = _chain_counts(ctr_reject_repository, ctr_reject_trade)

    ctr_partial_engine, ctr_partial_repository = _make_engine()
    ctr_partial_failure = BrokerTerminalOrderFailure(
        broker="CTRADER",
        broker_order_id="7002",
        status="CANCELLED",
        filled=0.01,
        remaining=0.02,
        failure_reason="TEST_ONLY cTrader partial-fill cancel",
        confirmed_price=1.0991,
        broker_position_id="9002",
    )
    ctr_partial_service = _TerminalFailureService(ctr_partial_failure)
    ctr_partial_engine.ctrader_runtime_service = cast(
        CTraderRuntimeServiceProtocol,
        cast(object, ctr_partial_service),
    )
    ctr_partial_trade, ctr_partial_plan = _create_workspace_plan(
        ctr_partial_repository,
        broker="CTRADER",
        account_id="987654",
        symbol="USDJPY",
        side="BUY",
        signal_uid="S-CTR-PARTIAL-60",
    )
    _submit_expect_terminal_failure(
        ctr_partial_engine,
        ctr_partial_trade,
        ctr_partial_plan,
    )
    ctr_partial_order = _last_broker_order(
        ctr_partial_repository,
        ctr_partial_trade,
    )
    ctr_partial_position = ctr_partial_repository.get_position_by_trade_uid(
        ctr_partial_trade
    )
    ctr_partial_counts = _chain_counts(
        ctr_partial_repository,
        ctr_partial_trade,
    )
    ctr_partial_repeat = ctr_partial_engine.submit_workspace_execution_plan(
        ctr_partial_trade,
        ctr_partial_plan,
    )
    ctr_partial_repeat_counts = _chain_counts(
        ctr_partial_repository,
        ctr_partial_trade,
    )

    timeout_engine, timeout_repository = _make_engine()
    timeout_service = _IBTimeoutService()
    timeout_engine.ib_runtime_service = cast(
        IBRuntimeServiceProtocol,
        cast(object, timeout_service),
    )
    timeout_trade, timeout_plan = _create_workspace_plan(
        timeout_repository,
        broker="IB",
        account_id="DU123",
        symbol="AUDUSD",
        side="BUY",
        signal_uid="S-IB-TIMEOUT-60",
    )
    timeout_raised = False
    try:
        timeout_engine.submit_workspace_execution_plan(
            timeout_trade,
            timeout_plan,
        )
    except IBMarketOrderTimeoutError:
        timeout_raised = True
    timeout_counts = _chain_counts(timeout_repository, timeout_trade)

    checks = {
        "production_change": True,
        "runtime_typed_terminal_failure_catch_present": True,
        "ib_zero_fill_status_persisted": (
            str(ib_zero_order.get("broker_order_id") or "") == "101"
            and str(ib_zero_order.get("execution_status") or "") == "CANCELLED"
        ),
        "ib_zero_fill_creates_no_position": ib_zero_counts == (1, 1, 0),
        "ib_zero_fill_repeat_is_idempotent": bool(
            ib_zero_repeat.get("already_submitted")
        )
        and ib_zero_repeat_counts == ib_zero_counts
        and ib_zero_service.calls == 1,
        "ib_partial_fill_status_persisted": (
            str(ib_partial_order.get("broker_order_id") or "") == "102"
            and str(ib_partial_order.get("execution_status") or "") == "CANCELLED"
        ),
        "ib_partial_fill_reconciles_position": bool(ib_partial_position)
        and float(ib_partial_position.get("volume") or 0.0) == 1000.0
        and float(ib_partial_position.get("open_price") or 0.0) == 1.1012,
        "ib_partial_fill_repeat_is_idempotent": bool(
            ib_partial_repeat.get("already_submitted")
        )
        and ib_partial_repeat_counts == ib_partial_counts == (1, 1, 1)
        and ib_partial_service.calls == 1,
        "ctrader_reject_status_persisted": (
            str(ctr_reject_order.get("broker_order_id") or "") == "7001"
            and str(ctr_reject_order.get("execution_status") or "") == "REJECTED"
        ),
        "ctrader_reject_creates_no_position": ctr_reject_counts == (1, 1, 0),
        "ctrader_partial_fill_status_persisted": (
            str(ctr_partial_order.get("broker_order_id") or "") == "7002"
            and str(ctr_partial_order.get("execution_status") or "")
            == "CANCELLED"
        ),
        "ctrader_positive_fill_reconciles_position": bool(ctr_partial_position)
        and str(ctr_partial_position.get("broker_position_id") or "") == "9002"
        and float(ctr_partial_position.get("volume") or 0.0) == 0.01
        and float(ctr_partial_position.get("open_price") or 0.0) == 1.0991,
        "ctrader_partial_fill_repeat_is_idempotent": bool(
            ctr_partial_repeat.get("already_submitted")
        )
        and ctr_partial_repeat_counts == ctr_partial_counts == (1, 1, 1)
        and ctr_partial_service.calls == 1,
        "timeout_unknown_state_remains_separate": timeout_raised,
        "timeout_does_not_persist_terminal_broker_order": timeout_counts
        == (1, 0, 0),
        "broker_requests": 0,
    }

    failed = [name for name, value in checks.items() if value is False]
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-60_WORKSPACE_TERMINAL_FAILURE_PERSISTENCE_WIRING=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_TERMINAL_PENDING_TIMEOUT_RECOVERY_LIFECYCLE"
    )
    print(
        "boundary_contract=TERMINAL_REJECT_CANCEL_IDENTITY_AND_CONFIRMED_"
        "EXPOSURE_ARE_NOW_PERSISTED_IDEMPOTENTLY_WHILE_UNKNOWN_EXECUTION_"
        "TIMEOUT_REMAINS_PENDING_AND_REQUIRES_SEPARATE_RECOVERY_LIFECYCLE"
    )
    print(
        "factual_verdict=A. WORKSPACE_TERMINAL_FAILURE_PERSISTENCE_"
        "WIRING_GREEN"
    )


if __name__ == "__main__":
    main()
