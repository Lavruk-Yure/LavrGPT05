# run_runtime_position_close_check.py
"""
Перевірити Runtime close-position chain за broker_position_id.

Приклад:
D:\\LavrGPT\\venv313\\Scripts\\python.exe D:\\LavrGPT\\LavrGPT05\\tests\\runtime
\\run_runtime_position_close_check.py 649648986
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"


def _row_to_dict(row: sqlite3.Row) -> dict:
    """
    Перетворити sqlite row на dict.
    """
    return {key: row[key] for key in row.keys()}


def _print_rows(title: str, rows: list[sqlite3.Row]) -> None:
    """
    Надрукувати набір рядків.
    """
    print()
    print(f"=== {title} ===")

    if not rows:
        print("No rows.")
        return

    for row in rows:
        print(_row_to_dict(row))


def main() -> int:
    """
    Entry point.
    """
    if len(sys.argv) >= 2:
        broker_position_id = str(sys.argv[1]).strip()
    else:
        broker_position_id = input("Enter broker_position_id: ").strip()

    if not broker_position_id:
        print("broker_position_id is empty.")
        return 2

    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row

    print("=== Runtime Position Close Check ===")
    print(f"db_path            : {DB_PATH}")
    print(f"broker_position_id : {broker_position_id}")

    positions = connection.execute(
        """
        SELECT *
        FROM positions
        WHERE broker_position_id = ?
        ORDER BY id DESC
        """,
        (broker_position_id,),
    ).fetchall()

    _print_rows("Positions", positions)

    if not positions:
        connection.close()
        return 1

    latest_position = positions[0]
    trade_uid = str(latest_position["trade_uid"])

    print()
    print("=== Summary ===")
    print(f"trade_uid          : {trade_uid}")
    print(f"position_state     : {latest_position['state']}")

    order_plans = connection.execute(
        """
        SELECT *
        FROM order_plans
        WHERE trade_uid = ?
        ORDER BY id
        """,
        (trade_uid,),
    ).fetchall()

    broker_orders = connection.execute(
        """
        SELECT *
        FROM broker_orders
        WHERE trade_uid = ?
        ORDER BY id
        """,
        (trade_uid,),
    ).fetchall()

    _print_rows("OrderPlans", order_plans)
    _print_rows("BrokerOrders", broker_orders)

    print()
    print("=== Counts ===")
    print(f"order_plans count   : {len(order_plans)}")
    print(f"broker_orders count : {len(broker_orders)}")

    connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
