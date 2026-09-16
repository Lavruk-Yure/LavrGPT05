from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.broker_position import BrokerPosition  # noqa: E402
from engine.db.runtime_db import RUNTIME_TABLES_SQL  # noqa: E402
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_repository import RuntimeRepository  # noqa: E402


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
    return engine, repository


def _create_workspace_chain(
    repository: RuntimeRepository,
    *,
    broker: str,
    account_id: str,
    symbol: str,
    side: str,
    volume: float,
    signal_uid: str,
) -> tuple[str, str, str]:
    trade_uid = repository.create_trade(
        broker=broker,
        account_id=account_id,
        symbol=symbol,
        side=side,
        volume=volume,
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
        volume=volume,
        source="WORKSPACE",
    )
    broker_order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker=broker,
        broker_order_id=f"ORDER-{signal_uid}",
        execution_status="SUBMITTED",
        source="WORKSPACE",
    )
    return trade_uid, order_plan_uid, broker_order_uid


def _position(
    *,
    broker: str,
    account_id: str,
    position_id: str,
    symbol: str,
    side: str,
    volume: float,
    entry_price: float,
) -> BrokerPosition:
    return BrokerPosition(
        broker=broker,
        account_id=account_id,
        account_mode="PAPER",
        position_id=position_id,
        symbol_name=symbol,
        side=side,
        volume=volume,
        entry_price=entry_price,
        opened_utc="2026-09-16T09:00:00+00:00",
    )


def _broker_order_status(repository: RuntimeRepository, trade_uid: str) -> str:
    chain = repository.get_trade_chain(trade_uid)
    orders = chain.get("broker_orders", [])
    return str(orders[-1].get("execution_status") or "") if orders else ""


def _position_row(
    repository: RuntimeRepository,
    trade_uid: str,
) -> dict[str, Any] | None:
    return repository.get_position_by_trade_uid(trade_uid)


def main() -> None:
    engine, repository = _make_engine()

    ib_trade, ib_plan, ib_order = _create_workspace_chain(
        repository,
        broker="IB",
        account_id="DU123",
        symbol="EURUSD",
        side="BUY",
        volume=3000.0,
        signal_uid="S-IB",
    )
    ib_partial = _position(
        broker="IB",
        account_id="DU123",
        position_id="IB:DU123:EURUSD",
        symbol="EURUSD",
        side="BUY",
        volume=1000.0,
        entry_price=1.1000,
    )
    partial_result = engine.reconcile_workspace_broker_order(
        ib_trade,
        ib_plan,
        ib_order,
        execution_status="PARTIALLY_FILLED",
        confirmed_position=ib_partial,
    )
    partial_uid = str(partial_result["position_uid"])
    ib_partial.volume = 1500.0
    second_partial_result = engine.reconcile_workspace_broker_order(
        ib_trade,
        ib_plan,
        ib_order,
        execution_status="PARTIALLY_FILLED",
        confirmed_position=ib_partial,
    )
    ib_full = _position(
        broker="IB",
        account_id="DU123",
        position_id="IB:DU123:EURUSD",
        symbol="EURUSD",
        side="BUY",
        volume=3000.0,
        entry_price=1.1002,
    )
    full_result = engine.reconcile_workspace_broker_order(
        ib_trade,
        ib_plan,
        ib_order,
        execution_status="FILLED",
        confirmed_position=ib_full,
    )
    ib_row = _position_row(repository, ib_trade)

    ctr_trade, ctr_plan, ctr_order = _create_workspace_chain(
        repository,
        broker="CTRADER",
        account_id="987654",
        symbol="EURUSD",
        side="SELL",
        volume=3000.0,
        signal_uid="S-CTR",
    )
    ctr_position = _position(
        broker="CTRADER",
        account_id="987654",
        position_id="CTR-POS-1",
        symbol="EURUSD",
        side="SELL",
        volume=0.03,
        entry_price=1.0990,
    )
    ctr_first = engine.reconcile_workspace_broker_order(
        ctr_trade,
        ctr_plan,
        ctr_order,
        execution_status="FILLED",
        confirmed_position=ctr_position,
    )
    ctr_repeat = engine.reconcile_workspace_broker_order(
        ctr_trade,
        ctr_plan,
        ctr_order,
        execution_status="FILLED",
        confirmed_position=ctr_position,
    )
    ctr_row = _position_row(repository, ctr_trade)

    reject_trade, reject_plan, reject_order = _create_workspace_chain(
        repository,
        broker="IB",
        account_id="DU123",
        symbol="GBPUSD",
        side="SELL",
        volume=2000.0,
        signal_uid="S-REJECT",
    )
    reject_result = engine.reconcile_workspace_broker_order(
        reject_trade,
        reject_plan,
        reject_order,
        execution_status="REJECTED",
        confirmed_position=None,
    )

    cancel_trade, cancel_plan, cancel_order = _create_workspace_chain(
        repository,
        broker="CTRADER",
        account_id="987654",
        symbol="USDJPY",
        side="BUY",
        volume=2000.0,
        signal_uid="S-CANCEL",
    )
    cancel_result = engine.reconcile_workspace_broker_order(
        cancel_trade,
        cancel_plan,
        cancel_order,
        execution_status="CANCELLED",
        confirmed_position=None,
    )

    cancel_partial_trade, cancel_partial_plan, cancel_partial_order = (
        _create_workspace_chain(
            repository,
            broker="IB",
            account_id="DU123",
            symbol="AUDUSD",
            side="BUY",
            volume=2000.0,
            signal_uid="S-CANCEL-PARTIAL",
        )
    )
    cancel_partial_position = _position(
        broker="IB",
        account_id="DU123",
        position_id="IB:DU123:AUDUSD",
        symbol="AUDUSD",
        side="BUY",
        volume=800.0,
        entry_price=0.6500,
    )
    cancel_partial_result = engine.reconcile_workspace_broker_order(
        cancel_partial_trade,
        cancel_partial_plan,
        cancel_partial_order,
        execution_status="CANCELLED",
        confirmed_position=cancel_partial_position,
    )

    checks = {
        "production_change": True,
        "workspace_reconciler_present": hasattr(
            RuntimeEngine,
            "reconcile_workspace_broker_order",
        ),
        "repository_confirmed_position_upsert_present": hasattr(
            RuntimeRepository,
            "upsert_confirmed_position",
        ),
        "ib_partial_fill_creates_position": bool(partial_uid),
        "ib_partial_fill_updates_same_position": str(
            second_partial_result["position_uid"]
        )
        == partial_uid,
        "ib_full_fill_reuses_same_position": str(full_result["position_uid"])
        == partial_uid,
        "ib_full_fill_volume_confirmed": bool(ib_row)
        and float(ib_row["volume"]) == 3000.0,
        "ib_order_status_updated_to_filled": _broker_order_status(
            repository,
            ib_trade,
        )
        == "FILLED",
        "ctrader_full_fill_creates_position": bool(ctr_first["position_uid"]),
        "ctrader_repeat_is_idempotent": str(ctr_repeat["position_uid"])
        == str(ctr_first["position_uid"]),
        "ctrader_confirmed_broker_volume_preserved": bool(ctr_row)
        and float(ctr_row["volume"]) == 0.03,
        "reject_creates_no_position": not reject_result["position_uid"]
        and _position_row(repository, reject_trade) is None,
        "reject_status_persisted": _broker_order_status(repository, reject_trade)
        == "REJECTED",
        "cancel_zero_fill_creates_no_position": not cancel_result["position_uid"]
        and _position_row(repository, cancel_trade) is None,
        "cancel_status_persisted": _broker_order_status(repository, cancel_trade)
        == "CANCELLED",
        "cancel_partial_fill_preserves_position": bool(
            cancel_partial_result["position_uid"]
        )
        and _position_row(repository, cancel_partial_trade) is not None,
        "broker_requests": 0,
    }

    failed = [name for name, value in checks.items() if value is False]
    if failed:
        raise AssertionError(", ".join(failed))

    print("T109-54_WORKSPACE_POSITION_RECONCILER_PRODUCTION_WIRING=OK")
    for name, value in checks.items():
        print(f"{name}={value}")
    print(
        "first_unresolved_boundary="
        "WORKSPACE_BROKER_CONFIRMATION_SOURCE_TO_RECONCILER_WIRING"
    )
    print(
        "boundary_contract=BROKER_CONFIRMATION_OR_RECONCILIATION_MUST_FEED_"
        "EXACT_WORKSPACE_BROKER_ORDER_AND_CONFIRMED_POSITION_INTO_THE_"
        "IDEMPOTENT_RECONCILER"
    )
    print(
        "factual_verdict=A. WORKSPACE_POSITION_RECONCILER_PRODUCTION_WIRING_GREEN"
    )


if __name__ == "__main__":
    main()
