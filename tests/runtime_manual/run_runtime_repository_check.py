"""
Перевірка RuntimeRepository.

RoadMap82:
Trade
    ↓
OrderPlan
    ↓
BrokerOrder
    ↓
Position
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3

from engine.db.runtime_db import connect_runtime_db, get_runtime_database_path
from engine.runtime_repository import RuntimeRepository


def count_rows(
    connection: sqlite3.Connection,
    table_name: str,
) -> int:
    cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(cursor.fetchone()[0])


def main() -> None:

    db_path = get_runtime_database_path("DEMO")
    connection = connect_runtime_db(db_path)

    repository = RuntimeRepository(connection)

    trade_uid = repository.create_trade(
        broker="CTRADER",
        account_id="123456",
        symbol="EURUSD",
        side="BUY",
        volume=0.01,
    )

    order_plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=0.01,
    )

    broker_order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="CTRADER",
        broker_order_id="100001",
        execution_status="FILLED",
    )

    position_uid = repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="CTRADER",
        broker_position_id="200001",
        symbol="EURUSD",
        side="BUY",
        volume=0.01,
        open_price=1.12345,
        opened_utc="2026-07-05T10:00:00+00:00",
    )

    chain = repository.get_trade_chain(trade_uid)

    print()
    print("=== Runtime Trade Chain ===")
    print(f"trade exists         : {chain['trade'] is not None}")
    print(f"order_plans count    : {len(chain['order_plans'])}")
    print(f"broker_orders count  : {len(chain['broker_orders'])}")
    print(f"positions count      : {len(chain['positions'])}")

    latest_trade_uid = repository.get_latest_trade_uid()

    print()
    print("=== Runtime Latest Trade ===")
    print(f"latest_trade_uid    : {latest_trade_uid}")
    print(f"latest is current   : {latest_trade_uid == trade_uid}")

    print()
    print("=== Runtime Repository Check ===")
    print(f"trade_uid         : {trade_uid}")
    print(f"order_plan_uid    : {order_plan_uid}")
    print(f"broker_order_uid  : {broker_order_uid}")
    print(f"position_uid      : {position_uid}")
    print()

    for table in (
        "trades",
        "order_plans",
        "broker_orders",
        "positions",
    ):
        print(f"{table:16} rows = {count_rows(connection, table)}")


if __name__ == "__main__":
    main()
