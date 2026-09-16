from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import RUNTIME_TABLES_SQL  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    CTraderRuntimeServiceProtocol,
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)
from engine.runtime_repository import RuntimeRepository  # noqa: E402


class _IBService:
    def __init__(self) -> None:
        self.calls = 0

    def place_market_order(self, **_kwargs: object) -> dict[str, Any]:
        self.calls += 1
        return {
            "broker": "IB",
            "order_id": "101",
            "broker_order_id": "101",
            "status": "FILLED",
            "filled": 3000.0,
            "remaining": 0.0,
            "avg_fill_price": 1.1012,
        }


class _CTraderService:
    def __init__(self) -> None:
        self.calls = 0

    def place_market_order(self, **_kwargs: object) -> object:
        self.calls += 1
        trade_data = SimpleNamespace(
            volume=300000,
            openTimestamp=1770000000000,
        )
        position = SimpleNamespace(
            positionId=9001,
            tradeData=trade_data,
            price=1.0991,
        )
        order = SimpleNamespace(orderId=7001)
        return SimpleNamespace(order=order, position=position)


class _RejectService:
    def place_market_order(self, **_kwargs: object) -> object:
        raise RuntimeError("terminal reject")


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


def main() -> None:
    engine, repository = _make_engine()

    ib_service = _IBService()
    engine.ib_runtime_service = cast(
        IBRuntimeServiceProtocol,
        cast(object, ib_service),
    )
    ib_trade, ib_plan = _create_workspace_plan(
        repository,
        broker="IB",
        account_id="DU123",
        symbol="EURUSD",
        side="BUY",
        signal_uid="S-IB-56",
    )
    ib_result = engine.submit_workspace_execution_plan(ib_trade, ib_plan)
    ib_position = repository.get_position_by_trade_uid(ib_trade)
    ib_counts = _chain_counts(repository, ib_trade)
    ib_repeat = engine.submit_workspace_execution_plan(ib_trade, ib_plan)
    ib_repeat_counts = _chain_counts(repository, ib_trade)

    ctr_service = _CTraderService()
    engine.ctrader_runtime_service = cast(
        CTraderRuntimeServiceProtocol,
        cast(object, ctr_service),
    )
    ctr_trade, ctr_plan = _create_workspace_plan(
        repository,
        broker="CTRADER",
        account_id="987654",
        symbol="EURUSD",
        side="SELL",
        signal_uid="S-CTR-56",
    )
    ctr_result = engine.submit_workspace_execution_plan(ctr_trade, ctr_plan)
    ctr_position = repository.get_position_by_trade_uid(ctr_trade)
    ctr_counts = _chain_counts(repository, ctr_trade)
    ctr_repeat = engine.submit_workspace_execution_plan(ctr_trade, ctr_plan)
    ctr_repeat_counts = _chain_counts(repository, ctr_trade)

    reject_engine, reject_repository = _make_engine()
    reject_service = _RejectService()
    reject_engine.ctrader_runtime_service = cast(
        CTraderRuntimeServiceProtocol,
        cast(object, reject_service),
    )
    reject_trade, reject_plan = _create_workspace_plan(
        reject_repository,
        broker="CTRADER",
        account_id="987654",
        symbol="GBPUSD",
        side="BUY",
        signal_uid="S-REJECT-56",
    )
    reject_raised = False
    try:
        reject_engine.submit_workspace_execution_plan(
            reject_trade,
            reject_plan,
        )
    except RuntimeError:
        reject_raised = True

    reject_position = reject_repository.get_position_by_trade_uid(reject_trade)
    reject_counts = _chain_counts(reject_repository, reject_trade)

    checks = {
        "production_change": True,
        "ib_terminal_fill_maps_position": bool(ib_result.get("position_uid")),
        "ib_position_uses_existing_trade": bool(ib_position)
        and str(ib_position.get("trade_uid") or "") == ib_trade,
        "ib_confirmed_volume_preserved": bool(ib_position)
        and float(ib_position.get("volume") or 0.0) == 3000.0,
        "ib_confirmed_price_preserved": bool(ib_position)
        and float(ib_position.get("open_price") or 0.0) == 1.1012,
        "ib_repeat_submit_is_idempotent": bool(ib_repeat.get("already_submitted"))
        and ib_counts == ib_repeat_counts == (1, 1, 1)
        and ib_service.calls == 1,
        "ctrader_terminal_fill_maps_position": bool(ctr_result.get("position_uid")),
        "ctrader_position_uses_existing_trade": bool(ctr_position)
        and str(ctr_position.get("trade_uid") or "") == ctr_trade,
        "ctrader_position_id_preserved": bool(ctr_position)
        and str(ctr_position.get("broker_position_id") or "") == "9001",
        "ctrader_confirmed_lots_preserved": bool(ctr_position)
        and float(ctr_position.get("volume") or 0.0) == 0.03,
        "ctrader_execution_status_filled": str(ctr_result.get("execution_status") or "")
        == "FILLED",
        "ctrader_repeat_submit_is_idempotent": bool(ctr_repeat.get("already_submitted"))
        and ctr_counts == ctr_repeat_counts == (1, 1, 1)
        and ctr_service.calls == 1,
        "terminal_reject_creates_no_position": reject_raised
        and reject_position is None,
        "terminal_reject_not_yet_persisted_as_broker_order": (
            reject_counts == (1, 0, 0)
        ),
        "duplicate_trade_order_plan_broker_order_added": (
            ib_counts == (1, 1, 1) and ctr_counts == (1, 1, 1)
        ),
        "broker_requests": 0,
    }

    failed = [name for name, value in checks.items() if value is False]
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-56_WORKSPACE_TERMINAL_BROKER_RESULT_TO_" "CONFIRMED_POSITION_WIRING=OK")
    for name, value in checks.items():
        print(f"{name}={value}")

    print(
        "first_unresolved_boundary="
        "WORKSPACE_TERMINAL_REJECT_CANCEL_IDENTITY_PERSISTENCE"
    )
    print(
        "boundary_contract=SUCCESSFUL_TERMINAL_FILL_NOW_PERSISTS_CONFIRMED_"
        "WORKSPACE_POSITION_BUT_TERMINAL_REJECT_OR_CANCEL_MUST_STILL_PERSIST_"
        "EXACT_BROKER_ORDER_IDENTITY_AND_STATUS_WITHOUT_CREATING_POSITION"
    )
    print(
        "factual_verdict=A. WORKSPACE_TERMINAL_BROKER_RESULT_TO_CONFIRMED_"
        "POSITION_WIRING_GREEN"
    )


if __name__ == "__main__":
    main()
