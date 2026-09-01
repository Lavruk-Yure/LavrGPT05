"""
Перевірка schema v5 та persistence IB virtual position legs.

RoadMap90:
- v4 -> v5 migration без зміни legacy Runtime chain;
- current leg state;
- active child order mapping;
- replacement history;
- SQLite foreign keys.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import (
    SCHEMA_VERSION,
    connect_runtime_db,
    get_schema_version,
)
from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_repository import RuntimeRepository


def _count_rows(
    connection: sqlite3.Connection,
    table_name: str,
) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def _create_v4_fixture(
    db_path: Path,
) -> tuple[str, str]:
    connection = connect_runtime_db(db_path)
    repository = RuntimeRepository(connection)

    trade_uid = repository.create_trade(
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        side="BUY",
        volume=1000.0,
        source="MANUAL",
    )
    order_plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=1000.0,
        source="MANUAL",
    )
    broker_order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id="111",
        execution_status="FILLED",
        source="MANUAL",
    )
    position_uid = repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id="IB:DUM513747:EURUSD",
        symbol="EURUSD",
        side="BUY",
        volume=1000.0,
        open_price=1.14685,
        opened_utc="2026-07-16T10:00:00+00:00",
        source="BROKER",
    )

    connection.execute("DROP TABLE ib_virtual_position_leg_orders")
    connection.execute("DROP TABLE ib_virtual_position_legs")
    connection.execute("PRAGMA user_version=4")
    connection.commit()
    connection.close()

    return trade_uid, position_uid


def _assert_schema(
    connection: sqlite3.Connection,
) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }

    required_tables = {
        "ib_virtual_position_legs",
        "ib_virtual_position_leg_orders",
    }
    required_indexes = {
        "idx_ib_virtual_legs_broker_position",
        "idx_ib_virtual_legs_status",
        "idx_ib_virtual_leg_orders_position",
        "idx_ib_virtual_leg_orders_active_role",
    }

    if not required_tables.issubset(tables):
        raise AssertionError("IB virtual-leg tables are incomplete")

    if not required_indexes.issubset(indexes):
        raise AssertionError("IB virtual-leg indexes are incomplete")


def main() -> int:
    with TemporaryDirectory(prefix="lge_ib_virtual_leg_") as temp_dir:
        db_path = Path(temp_dir) / "demo.db"
        trade_uid, position_uid = _create_v4_fixture(db_path)

        connection = connect_runtime_db(db_path)
        repository = RuntimeRepository(connection)

        _assert_schema(connection)

        if get_schema_version(connection) != SCHEMA_VERSION:
            raise AssertionError("Runtime schema version was not migrated")

        legacy_counts = {
            "trades": _count_rows(connection, "trades"),
            "order_plans": _count_rows(connection, "order_plans"),
            "broker_orders": _count_rows(connection, "broker_orders"),
            "positions": _count_rows(connection, "positions"),
        }

        if any(value != 1 for value in legacy_counts.values()):
            raise AssertionError("Legacy Runtime chain changed during migration")

        leg = IBVirtualPositionLeg(
            position_uid=position_uid,
            trade_uid=trade_uid,
            broker_position_id="IB:DUM513747:EURUSD",
            account_id="DUM513747",
            symbol_name="EURUSD",
            side="BUY",
            volume=1000.0,
            entry_price=1.14685,
            opened_utc="2026-07-16T10:00:00+00:00",
            source="MANUAL",
            parent_order_id=111,
            stop_loss_order_id=113,
            take_profit_order_id=112,
            stop_loss=1.144,
            take_profit=1.151,
            oca_group="1620614043",
            leg_status=IB_LEG_STATUS_OPEN,
            protection_status=IB_PROTECTION_STATUS_COMPLETE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
        )
        repository.upsert_ib_virtual_position_leg(leg)

        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_PARENT,
            broker_order_id=111,
            execution_status="FILLED",
            client_id=1,
            action="BUY",
            order_type="MKT",
            quantity=1000.0,
        )
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_STOP_LOSS,
            broker_order_id=113,
            parent_order_id=111,
            execution_status="SUBMITTED",
            client_id=1,
            action="SELL",
            order_type="STP",
            quantity=1000.0,
            price=1.144,
            oca_group="1620614043",
            oca_type=1,
        )
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            broker_order_id=112,
            parent_order_id=111,
            execution_status="SUBMITTED",
            client_id=1,
            action="SELL",
            order_type="LMT",
            quantity=1000.0,
            price=1.151,
            oca_group="1620614043",
            oca_type=1,
        )

        replacement_leg = replace(
            leg,
            take_profit_order_id=115,
            take_profit=1.1505,
            oca_group="1620615000",
        )
        repository.upsert_ib_virtual_position_leg(
            replacement_leg,
            remaining_volume=1000.0,
        )
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            broker_order_id=115,
            parent_order_id=111,
            execution_status="SUBMITTED",
            client_id=1,
            action="SELL",
            order_type="LMT",
            quantity=1000.0,
            price=1.1505,
            oca_group="1620615000",
            oca_type=1,
        )

        leg_row = repository.get_ib_virtual_position_leg(position_uid)
        all_orders = repository.get_ib_virtual_position_leg_orders(position_uid)
        active_orders = repository.get_ib_virtual_position_leg_orders(
            position_uid,
            active_only=True,
        )

        if leg_row is None:
            raise AssertionError("Persisted IB virtual leg was not found")

        active_by_role = {
            str(row["order_role"]): str(row["broker_order_id"]) for row in active_orders
        }
        old_take_profit = next(
            row for row in all_orders if str(row["broker_order_id"]) == "112"
        )

        if str(leg_row["take_profit_order_id"]) != "115":
            raise AssertionError("Current take-profit mapping was not updated")

        if float(leg_row["initial_volume"]) != 1000.0:
            raise AssertionError("Initial leg volume changed unexpectedly")

        if float(leg_row["remaining_volume"]) != 1000.0:
            raise AssertionError("Remaining leg volume is invalid")

        if active_by_role != {
            IB_LEG_ORDER_ROLE_PARENT: "111",
            IB_LEG_ORDER_ROLE_STOP_LOSS: "113",
            IB_LEG_ORDER_ROLE_TAKE_PROFIT: "115",
        }:
            raise AssertionError("Active IB virtual-leg order mapping is invalid")

        if int(old_take_profit["is_active"]) != 0:
            raise AssertionError("Replaced take-profit order lost history state")

        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()

        if foreign_key_rows:
            raise AssertionError("IB virtual-leg persistence has FK violations")

        print("RuntimeRepository IB virtual-leg persistence result")
        print(f"  schema_version={get_schema_version(connection)}")
        print(f"  legacy_counts={legacy_counts}")
        print(f"  leg_rows={_count_rows(connection, 'ib_virtual_position_legs')}")
        print(
            "  order_history_rows="
            f"{_count_rows(connection, 'ib_virtual_position_leg_orders')}"
        )
        print(f"  active_orders={active_by_role}")
        print("  replaced_take_profit_active=" f"{bool(old_take_profit['is_active'])}")
        print(f"  foreign_key_violations={len(foreign_key_rows)}")
        print("RUNTIME_REPOSITORY_IB_VIRTUAL_LEG_PERSISTENCE_CHECK=OK")

        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
