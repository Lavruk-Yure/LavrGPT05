# run_ib_virtual_leg_live_readonly_check.py
"""
Live read-only перевірка IB virtual position legs.

RoadMap90:
1. Підключитися до IB Paper через canonical RuntimeEngine path.
2. Прочитати RuntimeRepository seeds із data/demo.db.
3. Отримати live positions/open/completed/execution evidence.
4. Побудувати reconciled virtual-leg snapshot.
5. Підтвердити, що SQLite не змінилася.

Тест не виконує trading operations. RuntimeEngine працює з тимчасовою
SQLite-копією, тому runtime events не змінюють робочу data/demo.db.
"""

from __future__ import annotations

import gc
import hashlib
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from engine.runtime_constants import (
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
)
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"


def _database_digest(db_path: Path) -> tuple[str, dict[str, int]]:
    """
    Повернути digest усіх user tables через read-only SQLite connection.
    """
    resolved_path = db_path.resolve()
    uri = f"file:{resolved_path.as_posix()}?mode=ro"
    digest = hashlib.sha256()
    table_counts: dict[str, int] = {}

    with sqlite3.connect(uri, uri=True) as connection:
        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        for (table_name,) in table_rows:
            quoted_name = str(table_name).replace('"', '""')
            cursor = connection.execute(f'SELECT * FROM "{quoted_name}" ORDER BY rowid')
            rows = cursor.fetchall()
            table_counts[str(table_name)] = len(rows)
            digest.update(str(table_name).encode("utf-8"))
            digest.update(repr(cursor.description).encode("utf-8"))

            for row in rows:
                digest.update(repr(tuple(row)).encode("utf-8"))

    return digest.hexdigest(), table_counts


def _copy_database_snapshot(
    source_path: Path,
    target_path: Path,
) -> None:
    """
    Скопіювати узгоджений SQLite snapshot через backup API.

    RuntimeEngine працює з тимчасовою копією, тому його runtime_events
    не змінюють робочу data/demo.db. WAL-зміни джерела враховуються
    read-only connection автоматично.
    """
    resolved_source = source_path.resolve()
    source_uri = f"file:{resolved_source.as_posix()}?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _format_optional_number(value: Any) -> str:
    """
    Відформатувати optional numeric value для console output.
    """
    if value is None:
        return "-"

    number = float(value)

    if number.is_integer():
        return f"{number:,.0f}".replace(",", " ")

    return f"{number:.10f}".rstrip("0").rstrip(".")


def _print_leg(index: int, leg: Any) -> None:
    """
    Надрукувати одну reconciled virtual leg.
    """
    print(
        f"  leg[{index}] "
        f"symbol={leg.symbol_name} "
        f"side={leg.side} "
        f"volume={_format_optional_number(leg.volume)} "
        f"status={leg.leg_status} "
        f"reconciliation={leg.reconciliation_status}"
    )
    print("    " f"position_uid={leg.position_uid} " f"trade_uid={leg.trade_uid}")
    print(
        "    "
        f"parent={leg.parent_order_id} "
        f"sl_order={leg.stop_loss_order_id} "
        f"tp_order={leg.take_profit_order_id} "
        f"oca={leg.oca_group or '-'}"
    )
    print(
        "    "
        f"entry={_format_optional_number(leg.entry_price)} "
        f"sl={_format_optional_number(leg.stop_loss)} "
        f"tp={_format_optional_number(leg.take_profit)} "
        f"protection={leg.protection_status}"
    )

    for message in leg.reconciliation_messages:
        print(f"    message={message}")


def main() -> int:
    """
    Запустити live virtual-leg reconciliation без зміни робочої БД.
    """
    before_digest, before_counts = _database_digest(DB_PATH)
    print(f"  source_db={DB_PATH}")

    temporary_directory = tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_live_",
        ignore_cleanup_errors=True,
    )
    runtime_db_path = (
        Path(temporary_directory.name) / "demo_runtime_snapshot.db"
    )
    _copy_database_snapshot(
        source_path=DB_PATH,
        target_path=runtime_db_path,
    )

    engine = RuntimeEngine(db_path=str(runtime_db_path))
    service = IBRuntimeService()
    connected = False
    try:
        engine.set_ib_runtime_service(service)
        connected = engine.connect_ib_demo()

        if not connected:
            raise RuntimeError("IB Paper connection was not established")

        snapshot = engine.get_open_runtime_position_legs()

        if not snapshot.complete:
            raise RuntimeError("IB virtual-leg snapshot is incomplete")

        open_statuses = {
            IB_LEG_STATUS_OPEN,
            IB_LEG_STATUS_PARTIALLY_CLOSED,
        }
        open_legs = [
            leg for leg in snapshot.legs if leg.leg_status in open_statuses
        ]
        closed_legs = [
            leg for leg in snapshot.legs
            if leg.leg_status == IB_LEG_STATUS_CLOSED
        ]

        print("IB virtual-leg live read-only result")
        print(f"  complete={snapshot.complete}")
        print(f"  captured_utc={snapshot.captured_utc}")
        print(f"  legs={len(snapshot.legs)}")
        print(f"  open_legs={len(open_legs)}")
        print(f"  closed_legs={len(closed_legs)}")
        print(
            "  unmapped_protective_order_ids="
            f"{snapshot.unmapped_protective_order_ids}"
        )

        for broker_position_id, status in snapshot.group_statuses.items():
            print(f"  group={broker_position_id} status={status}")

            for message in snapshot.group_messages.get(
                broker_position_id,
                (),
            ):
                print(f"    group_message={message}")

        for index, leg in enumerate(snapshot.legs, start=1):
            _print_leg(index=index, leg=leg)

    finally:
        if connected:
            service.disconnect()

        engine.connection.close()
        del engine
        del service
        gc.collect()
        temporary_directory.cleanup()

    after_digest, after_counts = _database_digest(DB_PATH)
    sqlite_read_only = before_digest == after_digest and before_counts == after_counts

    print(f"  sqlite_read_only={sqlite_read_only}")

    if not sqlite_read_only:
        raise AssertionError("Live virtual-leg check modified SQLite")

    print("IB_VIRTUAL_LEG_LIVE_READONLY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
