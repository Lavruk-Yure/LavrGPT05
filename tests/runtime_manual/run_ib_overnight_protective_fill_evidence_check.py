"""
Live read-only diagnostics for overnight IB SL/TP fills.

RoadMap91 follow-up:
1. Work from a temporary SQLite backup.
2. Read one complete IB evidence snapshot through RuntimeEngine.
3. Print raw OPEN / COMPLETED / EXECUTION evidence for persisted OPEN legs.
4. Do not change working SQLite or broker state.
"""

from __future__ import annotations

import gc
import hashlib
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"


def _database_digest(db_path: Path) -> str:
    resolved = db_path.resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro"
    digest = hashlib.sha256()

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
            quoted = str(table_name).replace('"', '""')
            cursor = connection.execute(f'SELECT * FROM "{quoted}" ORDER BY rowid')
            digest.update(str(table_name).encode("utf-8"))
            digest.update(repr(cursor.description).encode("utf-8"))

            for row in cursor.fetchall():
                digest.update(repr(tuple(row)).encode("utf-8"))

    return digest.hexdigest()


def _copy_database_snapshot(source_path: Path, target_path: Path) -> None:
    resolved = source_path.resolve()
    uri = f"file:{resolved.as_posix()}?mode=ro"

    with sqlite3.connect(uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _optional_int(value: object) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    return number if number > 0 else None


def _symbol_name(row: dict[str, Any]) -> str:
    explicit = str(row.get("symbol_name") or "").strip().upper()

    if explicit:
        return explicit.replace(".", "")

    symbol = str(row.get("symbol") or "").strip().upper()
    currency = str(row.get("currency") or "").strip().upper()
    return f"{symbol}{currency}".replace(".", "")


def _load_open_leg_rows(db_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                position_uid,
                account_id,
                symbol,
                side,
                initial_volume,
                remaining_volume,
                parent_order_id,
                stop_loss_order_id,
                take_profit_order_id,
                stop_loss,
                take_profit,
                oca_group,
                leg_status,
                protection_status,
                reconciliation_status
            FROM ib_virtual_position_legs
            WHERE leg_status IN ('OPEN', 'PARTIALLY_CLOSED')
            ORDER BY symbol, position_uid
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _matching_rows(
    rows: list[dict[str, Any]],
    *,
    account_id: str,
    symbol_name: str,
    known_order_ids: set[int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for source_row in rows:
        row = dict(source_row)
        row_account = str(row.get("account_id") or row.get("account") or "").strip()
        order_id = _optional_int(row.get("order_id"))
        same_group = row_account == account_id and _symbol_name(row) == symbol_name

        if same_group or order_id in known_order_ids:
            result.append(row)

    return result


def _role_for_order_id(
    order_id: int | None,
    *,
    parent_order_id: int | None,
    stop_loss_order_id: int | None,
    take_profit_order_id: int | None,
) -> str:
    if order_id == parent_order_id:
        return "PARENT"

    if order_id == stop_loss_order_id:
        return "STOP_LOSS"

    if order_id == take_profit_order_id:
        return "TAKE_PROFIT"

    return "UNKNOWN"


def _print_order_rows(
    title: str,
    rows: list[dict[str, Any]],
    *,
    parent_order_id: int | None,
    stop_loss_order_id: int | None,
    take_profit_order_id: int | None,
) -> None:
    print(f"    {title}={len(rows)}")

    for row in rows:
        order_id = _optional_int(row.get("order_id"))
        role = _role_for_order_id(
            order_id,
            parent_order_id=parent_order_id,
            stop_loss_order_id=stop_loss_order_id,
            take_profit_order_id=take_profit_order_id,
        )
        print(
            "      "
            f"order_id={order_id} "
            f"role={role} "
            f"action={str(row.get('action') or '').strip()} "
            f"type={str(row.get('order_type') or '').strip()} "
            f"qty={row.get('total_quantity', row.get('quantity'))} "
            f"status={str(row.get('status') or '').strip()} "
            f"completed_status="
            f"{str(row.get('completed_status') or '').strip()} "
            f"parent_id={row.get('parent_id')} "
            f"oca={str(row.get('oca_group') or '').strip()} "
            f"order_ref={str(row.get('order_ref') or '').strip()}"
        )


def _print_execution_rows(
    rows: list[dict[str, Any]],
    *,
    parent_order_id: int | None,
    stop_loss_order_id: int | None,
    take_profit_order_id: int | None,
) -> None:
    print(f"    executions={len(rows)}")

    for row in rows:
        order_id = _optional_int(row.get("order_id"))
        role = _role_for_order_id(
            order_id,
            parent_order_id=parent_order_id,
            stop_loss_order_id=stop_loss_order_id,
            take_profit_order_id=take_profit_order_id,
        )
        print(
            "      "
            f"order_id={order_id} "
            f"role={role} "
            f"side={str(row.get('side') or '').strip()} "
            f"shares={row.get('shares')} "
            f"price={row.get('price')} "
            f"time={str(row.get('time') or '').strip()} "
            f"perm_id={row.get('perm_id')}"
        )


def main() -> int:
    before_digest = _database_digest(DB_PATH)
    print("IB overnight protective-fill evidence diagnostics")
    print(f"  source_db={DB_PATH}")

    temporary_directory = tempfile.TemporaryDirectory(
        prefix="lge_ib_overnight_fill_evidence_",
        ignore_cleanup_errors=True,
    )
    runtime_db_path = Path(temporary_directory.name) / "demo_snapshot.db"
    _copy_database_snapshot(DB_PATH, runtime_db_path)

    engine = RuntimeEngine(db_path=str(runtime_db_path))
    service = IBRuntimeService()
    connected = False

    try:
        engine.set_ib_runtime_service(service)
        connected = engine.connect_ib_demo()

        if not connected:
            raise RuntimeError("IB Paper connection was not established")

        evidence = engine.get_ib_virtual_position_leg_evidence_snapshot()

        if not bool(evidence.get("complete")):
            raise RuntimeError("IB evidence snapshot is incomplete")

        open_orders = [dict(row) for row in evidence.get("open_orders") or []]
        completed_orders = [dict(row) for row in evidence.get("completed_orders") or []]
        executions = [dict(row) for row in evidence.get("executions") or []]
        legs = _load_open_leg_rows(runtime_db_path)

        print(f"  captured_utc={evidence.get('captured_utc')}")
        print(f"  open_legs={len(legs)}")
        print(f"  all_open_orders={len(open_orders)}")
        print(f"  all_completed_orders={len(completed_orders)}")
        print(f"  all_executions={len(executions)}")

        for index, leg in enumerate(legs, start=1):
            account_id = str(leg.get("account_id") or "").strip()
            symbol_name = str(leg.get("symbol") or "").strip().upper()
            parent_order_id = _optional_int(leg.get("parent_order_id"))
            stop_loss_order_id = _optional_int(leg.get("stop_loss_order_id"))
            take_profit_order_id = _optional_int(leg.get("take_profit_order_id"))
            known_order_ids = {
                value
                for value in (
                    parent_order_id,
                    stop_loss_order_id,
                    take_profit_order_id,
                )
                if value is not None
            }

            matching_open_orders = _matching_rows(
                open_orders,
                account_id=account_id,
                symbol_name=symbol_name,
                known_order_ids=known_order_ids,
            )
            matching_completed_orders = _matching_rows(
                completed_orders,
                account_id=account_id,
                symbol_name=symbol_name,
                known_order_ids=known_order_ids,
            )
            matching_executions = _matching_rows(
                executions,
                account_id=account_id,
                symbol_name=symbol_name,
                known_order_ids=known_order_ids,
            )
            child_ids = {
                value
                for value in (
                    stop_loss_order_id,
                    take_profit_order_id,
                )
                if value is not None
            }
            child_execution_ids = {
                _optional_int(row.get("order_id"))
                for row in matching_executions
                if _optional_int(row.get("order_id")) in child_ids
            }
            completed_child_ids = {
                _optional_int(row.get("order_id"))
                for row in matching_completed_orders
                if _optional_int(row.get("order_id")) in child_ids
            }

            print(
                f"  leg[{index}] "
                f"position_uid={leg.get('position_uid')} "
                f"account={account_id} "
                f"symbol={symbol_name} "
                f"side={leg.get('side')} "
                f"volume={leg.get('remaining_volume')} "
                f"status={leg.get('leg_status')} "
                f"reconciliation={leg.get('reconciliation_status')}"
            )
            print(
                "    "
                f"parent={parent_order_id} "
                f"sl={stop_loss_order_id} "
                f"tp={take_profit_order_id} "
                f"oca={leg.get('oca_group')}"
            )
            _print_order_rows(
                "open_orders",
                matching_open_orders,
                parent_order_id=parent_order_id,
                stop_loss_order_id=stop_loss_order_id,
                take_profit_order_id=take_profit_order_id,
            )
            _print_order_rows(
                "completed_orders",
                matching_completed_orders,
                parent_order_id=parent_order_id,
                stop_loss_order_id=stop_loss_order_id,
                take_profit_order_id=take_profit_order_id,
            )
            _print_execution_rows(
                matching_executions,
                parent_order_id=parent_order_id,
                stop_loss_order_id=stop_loss_order_id,
                take_profit_order_id=take_profit_order_id,
            )
            print(
                "    "
                f"child_execution_ids={sorted(value for value in child_execution_ids
                                              if value is not None)}"
            )
            print(
                "    "
                f"completed_child_ids={sorted(value for value in completed_child_ids
                                              if value is not None)}"
            )
            print(
                "    "
                "execution_only_protective_fill_candidate="
                f"{bool(child_execution_ids and not completed_child_ids)}"
            )
            print(
                "    "
                "protective_fill_api_evidence_missing="
                f"{not child_execution_ids and not completed_child_ids
                   and not matching_open_orders}"
            )
    finally:
        if connected:
            service.disconnect()

        engine.connection.close()
        del engine
        del service
        gc.collect()
        temporary_directory.cleanup()

    after_digest = _database_digest(DB_PATH)
    sqlite_read_only = before_digest == after_digest
    print(f"  sqlite_read_only={sqlite_read_only}")

    if not sqlite_read_only:
        raise AssertionError("Evidence diagnostics modified SQLite")

    print("IB_OVERNIGHT_PROTECTIVE_FILL_EVIDENCE_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
