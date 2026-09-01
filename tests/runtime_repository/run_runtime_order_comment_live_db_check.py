"""Read-only check for schema v7 order comments in the current DEMO DB."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import SCHEMA_VERSION  # noqa: E402


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name});").fetchall()
    }


def main() -> int:
    db_path = PROJECT_ROOT / "data" / "demo.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Runtime DEMO DB was not found: {db_path}")

    connection = sqlite3.connect(
        f"file:{db_path.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        assert schema_version == SCHEMA_VERSION == 7
        assert "comment" in _column_names(connection, "trades")
        assert "broker_comment" in _column_names(
            connection,
            "broker_orders",
        )
        assert "order_ref" in _column_names(
            connection,
            "ib_virtual_position_leg_orders",
        )

        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        assert integrity == "ok"
        assert not foreign_key_rows

        recent_rows = connection.execute(
            """
            SELECT
                trades.id AS trade_id,
                trades.broker,
                trades.symbol,
                trades.source,
                trades.comment,
                broker_orders.broker_order_id,
                broker_orders.broker_comment
            FROM trades
            LEFT JOIN broker_orders
                ON broker_orders.trade_uid = trades.trade_uid
            ORDER BY trades.id DESC, broker_orders.id DESC
            LIMIT 10
            """
        ).fetchall()
        order_ref_rows = connection.execute(
            """
            SELECT
                position_uid,
                order_role,
                broker_order_id,
                order_ref,
                is_active
            FROM ib_virtual_position_leg_orders
            WHERE order_ref != ''
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

        print("Runtime order-comment live DB result")
        print(f"  source_db={db_path}")
        print(f"  schema_version={schema_version}")
        print(f"  integrity={integrity}")
        print(f"  foreign_key_violations={len(foreign_key_rows)}")
        print(f"  recent_trade_rows={len(recent_rows)}")

        for row in recent_rows:
            print(
                "  trade[{trade_id}] broker={broker} symbol={symbol} "
                "source={source} comment={comment!r} order_id={order_id} "
                "broker_comment={broker_comment!r}".format(
                    trade_id=row["trade_id"],
                    broker=row["broker"],
                    symbol=row["symbol"],
                    source=row["source"],
                    comment=row["comment"],
                    order_id=row["broker_order_id"],
                    broker_comment=row["broker_comment"],
                )
            )

        print(f"  exact_order_ref_rows={len(order_ref_rows)}")

        for row in order_ref_rows:
            print(
                "  order_ref position_uid={position_uid} role={role} "
                "order_id={order_id} active={active} value={value!r}".format(
                    position_uid=row["position_uid"],
                    role=row["order_role"],
                    order_id=row["broker_order_id"],
                    active=bool(row["is_active"]),
                    value=row["order_ref"],
                )
            )

        print("RUNTIME_ORDER_COMMENT_LIVE_DB_CHECK=OK")
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
