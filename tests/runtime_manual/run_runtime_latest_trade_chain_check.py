"""
Read-only перевірка останнього Runtime Trade Chain.

RoadMap82:
показує останній Trade -> OrderPlan -> BrokerOrder -> Position
без створення нових записів.
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


def print_dict(
    title: str,
    data: dict | None,
) -> None:
    print()
    print(title)

    if data is None:
        print("  <none>")
        return

    for key, value in data.items():
        print(f"  {key}: {value}")


def main() -> None:
    db_path = get_runtime_database_path("DEMO")
    connection = connect_runtime_db(db_path)

    repository = RuntimeRepository(connection)

    latest_trade_uid = repository.get_latest_trade_uid()

    print()
    print("=== Runtime Latest Trade Chain Check ===")
    print(f"db_path          : {db_path}")
    print(f"latest_trade_uid : {latest_trade_uid}")

    if latest_trade_uid is None:
        print("No trades found.")
        return

    chain = repository.get_trade_chain(latest_trade_uid)

    print_dict("=== Trade ===", chain["trade"])

    print()
    print("=== OrderPlans ===")
    for row in chain["order_plans"]:
        print(dict(row))

    print()
    print("=== BrokerOrders ===")
    for row in chain["broker_orders"]:
        print(dict(row))

    print()
    print("=== Positions ===")
    for row in chain["positions"]:
        print(dict(row))

    print()
    print("=== Table Counts ===")
    for table in (
        "trades",
        "order_plans",
        "broker_orders",
        "positions",
    ):
        print(f"{table:16} rows = {count_rows(connection, table)}")


if __name__ == "__main__":
    main()
