"""
Controlled live persistence sync for the confirmed EURUSD parent 114 event.

Console modes:
1 - PLAN runs the live reconciliation and persistence sync on a temporary
    consistent copy of data/demo.db.
2 - APPLY creates a backup and persists the reconciled transition to the
    working data/demo.db.
"""

from __future__ import annotations

import gc
import hashlib
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"
BACKUP_DIRECTORY = PROJECT_ROOT / "data" / "backups"
TARGET_POSITION_UID = "a3badcf4-d572-4e03-a8e5-afb9b43ffaac"
TARGET_PARENT_ORDER_ID = 114
TARGET_STOP_LOSS_ORDER_ID = 116
TARGET_TAKE_PROFIT_ORDER_ID = 115
TARGET_OCA_GROUP = "1620614047"
TARGET_VOLUME = 2000.0

SyncMode = Literal["PLAN", "APPLY"]


class PersistedState(TypedDict):
    leg_status: str
    remaining_volume: float
    closed_utc: str | None
    reconciliation_status: str
    active_protective_count: int
    stop_loss_active: bool
    take_profit_active: bool
    stop_loss_status: str
    take_profit_status: str
    open_seed_count: int


class LiveSyncResult(TypedDict):
    already_applied: bool
    snapshot_legs: int
    persistence_legs_written: int
    persistence_orders_written: int
    transition_order_id: int | None
    persisted_state: PersistedState


def _database_digest(db_path: Path) -> tuple[str, dict[str, int]]:
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
            table_name_text = str(table_name)
            quoted_name = table_name_text.replace('"', '""')
            cursor = connection.execute(f'SELECT * FROM "{quoted_name}" ORDER BY rowid')
            rows = cursor.fetchall()
            table_counts[table_name_text] = len(rows)
            digest.update(table_name_text.encode("utf-8"))
            digest.update(repr(cursor.description).encode("utf-8"))

            for row in rows:
                digest.update(repr(tuple(row)).encode("utf-8"))

    return digest.hexdigest(), table_counts


def _copy_database_snapshot(source_path: Path, target_path: Path) -> None:
    resolved_source = source_path.resolve()
    source_uri = f"file:{resolved_source.as_posix()}?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _create_backup() -> Path:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIRECTORY / f"demo_before_ib_virtual_leg_live_sync_{timestamp}.db"
    )
    _copy_database_snapshot(DB_PATH, backup_path)
    return backup_path


def _read_persisted_state(db_path: Path) -> PersistedState:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        leg_row = connection.execute(
            """
            SELECT
                leg_status,
                remaining_volume,
                closed_utc,
                reconciliation_status
            FROM ib_virtual_position_legs
            WHERE position_uid = ?
            """,
            (TARGET_POSITION_UID,),
        ).fetchone()

        if leg_row is None:
            raise RuntimeError("Persisted EURUSD parent 114 leg was not found")

        order_rows = connection.execute(
            """
            SELECT
                order_role,
                broker_order_id,
                execution_status,
                is_active
            FROM ib_virtual_position_leg_orders
            WHERE position_uid = ?
              AND order_role IN (?, ?)
            ORDER BY id
            """,
            (
                TARGET_POSITION_UID,
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            ),
        ).fetchall()

        open_seed_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM ib_virtual_position_legs
                WHERE position_uid = ?
                  AND leg_status IN ('OPEN', 'PARTIALLY_CLOSED')
                """,
                (TARGET_POSITION_UID,),
            ).fetchone()[0]
        )

    rows_by_order_id = {
        int(row["broker_order_id"]): row
        for row in order_rows
        if str(row["broker_order_id"] or "").isdigit()
    }
    stop_row = rows_by_order_id.get(TARGET_STOP_LOSS_ORDER_ID)
    take_profit_row = rows_by_order_id.get(TARGET_TAKE_PROFIT_ORDER_ID)
    active_protective_count = sum(1 for row in order_rows if bool(row["is_active"]))

    return {
        "leg_status": str(leg_row["leg_status"] or "").strip().upper(),
        "remaining_volume": float(leg_row["remaining_volume"] or 0.0),
        "closed_utc": str(leg_row["closed_utc"] or "").strip() or None,
        "reconciliation_status": str(leg_row["reconciliation_status"] or "")
        .strip()
        .upper(),
        "active_protective_count": active_protective_count,
        "stop_loss_active": bool(stop_row["is_active"]) if stop_row else False,
        "take_profit_active": (
            bool(take_profit_row["is_active"]) if take_profit_row else False
        ),
        "stop_loss_status": (
            str(stop_row["execution_status"] or "").strip().upper() if stop_row else ""
        ),
        "take_profit_status": (
            str(take_profit_row["execution_status"] or "").strip().upper()
            if take_profit_row
            else ""
        ),
        "open_seed_count": open_seed_count,
    }


def _validate_pre_sync_state(state: PersistedState) -> bool:
    if state["leg_status"] == IB_LEG_STATUS_CLOSED:
        _validate_closed_state(state)
        return True

    if state["leg_status"] != IB_LEG_STATUS_OPEN:
        raise RuntimeError(
            "Unexpected persisted parent 114 leg status: " f"{state['leg_status']}"
        )

    if abs(state["remaining_volume"] - TARGET_VOLUME) > 1e-9:
        raise RuntimeError("Persisted parent 114 remaining volume differs")

    if state["reconciliation_status"] != (IB_RECONCILIATION_STATUS_RECONCILED):
        raise RuntimeError("Persisted parent 114 leg is not reconciled")

    if not state["stop_loss_active"]:
        raise RuntimeError("Persisted stop-loss order 116 is not active")

    if not state["take_profit_active"]:
        raise RuntimeError("Persisted take-profit order 115 is not active")

    if state["active_protective_count"] != 2:
        raise RuntimeError("Persisted active protective mapping count differs")

    return False


def _validate_closed_state(state: PersistedState) -> None:
    if abs(state["remaining_volume"]) > 1e-9:
        raise RuntimeError("Closed parent 114 leg retained remaining volume")

    if state["reconciliation_status"] != (IB_RECONCILIATION_STATUS_RECONCILED):
        raise RuntimeError("Closed parent 114 leg is not reconciled")

    if state["active_protective_count"] != 0:
        raise RuntimeError("Closed parent 114 leg retained active protection")

    if state["open_seed_count"] != 0:
        raise RuntimeError("Closed parent 114 leg remained an open seed")

    if not state["closed_utc"]:
        raise RuntimeError("Closed parent 114 leg has no close timestamp")


def _validate_live_sync_snapshot(result: dict[str, Any]) -> int:
    snapshot = result["snapshot"]
    matching_legs = [
        leg
        for leg in snapshot.legs
        if leg.position_uid == TARGET_POSITION_UID
        and leg.parent_order_id == TARGET_PARENT_ORDER_ID
    ]

    if len(matching_legs) != 1:
        raise RuntimeError(
            "Live sync did not return exactly one parent 114 virtual leg"
        )

    leg = matching_legs[0]

    if leg.leg_status != IB_LEG_STATUS_CLOSED:
        raise RuntimeError("Live sync did not close parent 114 virtual leg")

    if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
        raise RuntimeError("Live parent 114 transition is not reconciled")

    if leg.stop_loss_order_id != TARGET_STOP_LOSS_ORDER_ID:
        raise RuntimeError("Live close execution is not stop-loss order 116")

    if str(leg.oca_group or "") != TARGET_OCA_GROUP:
        raise RuntimeError("Live parent 114 OCA group differs")

    if snapshot.unmapped_protective_order_ids:
        raise RuntimeError("Live sync contains unmapped protective orders")

    return int(leg.stop_loss_order_id)


def _run_live_sync(db_path: Path) -> LiveSyncResult:
    pre_state = _read_persisted_state(db_path)
    already_applied = _validate_pre_sync_state(pre_state)

    if already_applied:
        return {
            "already_applied": True,
            "snapshot_legs": 0,
            "persistence_legs_written": 0,
            "persistence_orders_written": 0,
            "transition_order_id": TARGET_STOP_LOSS_ORDER_ID,
            "persisted_state": pre_state,
        }

    engine = RuntimeEngine(db_path=str(db_path))
    service = IBRuntimeService()
    connected = False

    try:
        engine.set_ib_runtime_service(service)
        connected = engine.connect_ib_demo()

        if not connected:
            raise RuntimeError("IB Paper connection was not established")

        result = engine.sync_reconciled_ib_virtual_position_legs()
        transition_order_id = _validate_live_sync_snapshot(result)
        persistence = result["persistence"]
        snapshot = result["snapshot"]
    finally:
        if connected:
            service.disconnect()

        engine.connection.close()
        del engine
        del service
        gc.collect()

    persisted_state = _read_persisted_state(db_path)
    _validate_closed_state(persisted_state)

    return {
        "already_applied": False,
        "snapshot_legs": len(snapshot.legs),
        "persistence_legs_written": int(persistence["legs_written"]),
        "persistence_orders_written": int(persistence["orders_written"]),
        "transition_order_id": transition_order_id,
        "persisted_state": persisted_state,
    }


def _read_mode_from_console() -> SyncMode:
    print("IB virtual-leg live persistence sync")
    print("  1 - PLAN: перевірка і запис лише у тимчасову копію demo.db")
    print("  2 - APPLY: резервна копія і запис у робочу demo.db")
    selected_mode: SyncMode | None = None

    while selected_mode is None:
        choice = input("Виберіть режим [1/2]: ").strip().upper()

        if choice in {"1", "PLAN"}:
            selected_mode = "PLAN"
            continue

        if choice in {"2", "APPLY"}:
            confirmation = (
                input("Для підтвердження запису введіть APPLY: ").strip().upper()
            )

            if confirmation == "APPLY":
                selected_mode = "APPLY"
            else:
                print("Запис не підтверджено. Виберіть режим ще раз.")

            continue

        print("Невідомий режим. Введіть 1 або 2.")

    return selected_mode


def _run_selected_mode(
    mode: SyncMode,
) -> tuple[Path | None, LiveSyncResult, bool]:
    before_digest, before_counts = _database_digest(DB_PATH)

    if mode == "APPLY":
        backup_path = _create_backup()
        result = _run_live_sync(DB_PATH)
        return backup_path, result, True

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_virtual_leg_live_sync_",
        ignore_cleanup_errors=True,
    ) as temporary_directory:
        target_path = Path(temporary_directory) / "demo_plan.db"
        _copy_database_snapshot(DB_PATH, target_path)
        result = _run_live_sync(target_path)

    after_digest, after_counts = _database_digest(DB_PATH)
    sqlite_read_only = before_digest == after_digest and before_counts == after_counts
    return None, result, sqlite_read_only


def main() -> int:
    mode = _read_mode_from_console()
    print(f"  source_db={DB_PATH}")
    backup_path, result, sqlite_read_only = _run_selected_mode(mode)
    state = result["persisted_state"]

    print("IB virtual-leg live persistence sync result")
    print(f"  mode={mode}")
    print(f"  already_applied={result['already_applied']}")
    print(f"  snapshot_legs={result['snapshot_legs']}")
    print("  persistence_legs_written=" f"{result['persistence_legs_written']}")
    print("  persistence_orders_written=" f"{result['persistence_orders_written']}")
    print(f"  transition_order_id={result['transition_order_id']}")
    print(f"  leg_status={state['leg_status']}")
    print(f"  remaining_volume={state['remaining_volume']}")
    print(f"  closed_utc={state['closed_utc']}")
    print("  active_protective_mappings=" f"{state['active_protective_count']}")
    print(f"  stop_loss_status={state['stop_loss_status']}")
    print(f"  take_profit_status={state['take_profit_status']}")
    print(f"  open_seed_count={state['open_seed_count']}")

    if backup_path is not None:
        print(f"  backup={backup_path}")

    if mode == "PLAN":
        print(f"  sqlite_read_only={sqlite_read_only}")

        if not sqlite_read_only:
            raise AssertionError("PLAN modified the working demo.db")

    print("IB_VIRTUAL_LEG_LIVE_PERSISTENCE_SYNC=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
