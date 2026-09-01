"""Runtime schema v7 broker-comment persistence and migration check."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import (  # noqa: E402
    SCHEMA_VERSION,
    connect_runtime_db,
    get_schema_version,
)
from engine.ib_virtual_position_leg import IBVirtualPositionLeg  # noqa: E402
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_repository import RuntimeRepository  # noqa: E402


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name});").fetchall()
    }


def _create_legacy_row(db_path: Path) -> None:
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
    repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id="100",
        execution_status="FILLED",
        source="MANUAL",
    )
    connection.close()

    legacy = sqlite3.connect(db_path)
    legacy.execute("PRAGMA foreign_keys=OFF")
    legacy.execute("ALTER TABLE trades DROP COLUMN comment")
    legacy.execute("ALTER TABLE broker_orders DROP COLUMN broker_comment")
    legacy.execute("ALTER TABLE ib_virtual_position_leg_orders DROP COLUMN order_ref")
    legacy.execute("PRAGMA user_version=6")
    legacy.commit()
    legacy.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lge_runtime_schema_v7_") as temp_dir:
        db_path = Path(temp_dir) / "runtime.db"
        _create_legacy_row(db_path)

        connection = connect_runtime_db(db_path)
        repository = RuntimeRepository(connection)

        assert get_schema_version(connection) == SCHEMA_VERSION == 7
        assert "comment" in _column_names(connection, "trades")
        assert "broker_comment" in _column_names(
            connection,
            "broker_orders",
        )
        assert "order_ref" in _column_names(
            connection,
            "ib_virtual_position_leg_orders",
        )

        legacy_trade = connection.execute(
            "SELECT comment FROM trades WHERE broker = 'IB' LIMIT 1"
        ).fetchone()
        legacy_order = connection.execute(
            "SELECT broker_comment FROM broker_orders LIMIT 1"
        ).fetchone()
        assert legacy_trade is not None and legacy_trade[0] == ""
        assert legacy_order is not None and legacy_order[0] == ""

        trade_uid = repository.create_trade(
            broker="IB",
            account_id="DUM513747",
            symbol="USDZAR",
            side="BUY",
            volume=2000.0,
            source="SEMI",
            comment="Schema v7 check",
        )
        order_plan_uid = repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side="BUY",
            volume=2000.0,
            source="SEMI",
        )
        broker_order_uid = repository.create_broker_order(
            trade_uid=trade_uid,
            order_plan_uid=order_plan_uid,
            broker="IB",
            broker_order_id="201",
            execution_status="FILLED",
            source="SEMI",
            broker_comment="[LGE:S] Schema v7 check",
        )
        position_uid = repository.create_position(
            trade_uid=trade_uid,
            broker_order_uid=broker_order_uid,
            broker="IB",
            broker_position_id="IB:DUM513747:USDZAR",
            symbol="USDZAR",
            side="BUY",
            volume=2000.0,
            open_price=16.45,
            opened_utc="2026-07-22T10:00:00+00:00",
            source="BROKER",
        )
        repository.upsert_ib_virtual_position_leg(
            IBVirtualPositionLeg(
                position_uid=position_uid,
                trade_uid=trade_uid,
                broker_position_id="IB:DUM513747:USDZAR",
                account_id="DUM513747",
                symbol_name="USDZAR",
                side="BUY",
                volume=2000.0,
                entry_price=16.45,
                opened_utc="2026-07-22T10:00:00+00:00",
                source="SEMI",
                parent_order_id=201,
                stop_loss_order_id=202,
                take_profit_order_id=203,
                stop_loss=16.3,
                take_profit=16.6,
                oca_group="LGE_SCHEMA_V7",
                leg_status=IB_LEG_STATUS_OPEN,
                protection_status=IB_PROTECTION_STATUS_COMPLETE,
                reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
            )
        )

        expected_ref = "[LGE:S] Schema v7 check"
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_PARENT,
            broker_order_id=201,
            execution_status="FILLED",
            action="BUY",
            order_type="MKT",
            quantity=2000.0,
            order_ref=expected_ref,
        )
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_STOP_LOSS,
            broker_order_id=202,
            parent_order_id=201,
            execution_status="SUBMITTED",
            action="SELL",
            order_type="STP",
            quantity=2000.0,
            price=16.3,
            order_ref=expected_ref,
        )
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            broker_order_id=203,
            parent_order_id=201,
            execution_status="SUBMITTED",
            action="SELL",
            order_type="LMT",
            quantity=2000.0,
            price=16.6,
            order_ref=expected_ref,
        )

        trade_row = connection.execute(
            "SELECT comment FROM trades WHERE trade_uid = ?",
            (trade_uid,),
        ).fetchone()
        order_row = connection.execute(
            "SELECT broker_comment FROM broker_orders WHERE broker_order_uid = ?",
            (broker_order_uid,),
        ).fetchone()
        order_refs = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT order_ref
                FROM ib_virtual_position_leg_orders
                WHERE position_uid = ?
                """,
                (position_uid,),
            ).fetchall()
        }

        assert trade_row is not None and trade_row[0] == "Schema v7 check"
        assert order_row is not None and order_row[0] == expected_ref
        assert order_refs == {expected_ref}
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()

        print("Runtime order-comment schema result")
        print("  schema_version=7")
        print("  legacy_rows_preserved=True")
        print("  trade_comment=Schema v7 check")
        print("  broker_comment=[LGE:S] Schema v7 check")
        print("  parent_sl_tp_order_refs_exact=True")
        print("RUNTIME_ORDER_COMMENT_SCHEMA_CHECK=OK")
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
