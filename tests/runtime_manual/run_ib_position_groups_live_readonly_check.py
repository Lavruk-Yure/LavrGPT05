"""
Live read-only перевірка IB broker position groups із persisted virtual legs.

RoadMap91:
1. Працювати з тимчасовою копією data/demo.db.
2. Підключитися до IB Paper через canonical RuntimeEngine path.
3. Викликати RuntimeEngine.get_active_broker_position_groups().
4. Перевірити загальні інваріанти поточного persisted snapshot.
5. Не змінити робочу data/demo.db і broker state.
"""

from __future__ import annotations

import gc
import hashlib
import sqlite3
import tempfile
from pathlib import Path

from engine.ib_position_group import IBPositionGroupSnapshot
from engine.runtime_constants import (
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS,
    IB_POSITION_GROUP_MODE_NET_ONLY,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"


def _database_digest(db_path: Path) -> tuple[str, dict[str, int]]:
    """
    Повернути digest user tables через read-only SQLite connection.
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


def _copy_database_snapshot(
    source_path: Path,
    target_path: Path,
) -> None:
    """
    Скопіювати узгоджений SQLite snapshot через backup API.
    """
    resolved_source = source_path.resolve()
    source_uri = f"file:{resolved_source.as_posix()}?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _format_number(value: float | None) -> str:
    """
    Відформатувати optional numeric value для console output.
    """
    if value is None:
        return "-"

    if value.is_integer():
        return f"{value:,.0f}".replace(",", " ")

    return f"{value:.10f}".rstrip("0").rstrip(".")


def _validate_snapshot_consistency(
    snapshot: IBPositionGroupSnapshot,
) -> str:
    """Підтвердити загальні live-інваріанти без hardcoded order IDs."""
    if snapshot.unmapped_protective_order_ids:
        raise AssertionError(
            "Live snapshot contains unmapped protective orders: "
            f"{snapshot.unmapped_protective_order_ids}"
        )

    seen_position_uids: set[str] = set()
    open_legs = 0
    closed_legs = 0
    net_only_groups = 0

    for group in snapshot.groups:
        if group.group_mode == IB_POSITION_GROUP_MODE_NET_ONLY:
            net_only_groups += 1

            if group.legs:
                raise AssertionError("NET_ONLY group unexpectedly contains legs")

            if group.leg_operations_enabled:
                raise AssertionError("NET_ONLY group enabled leg operations")

            continue

        if group.group_mode != IB_POSITION_GROUP_MODE_LGE_VIRTUAL_LEGS:
            raise AssertionError(f"Unknown group mode: {group.group_mode}")

        if not group.legs:
            raise AssertionError("LGE_VIRTUAL_LEGS group has no persisted legs")

        expected_leg_operations = (
            group.reconciliation_status == IB_RECONCILIATION_STATUS_RECONCILED
            and bool(group.open_legs)
        )

        if group.leg_operations_enabled != expected_leg_operations:
            raise AssertionError("Group leg-operation flag is inconsistent")

        for leg in group.legs:
            if leg.position_uid in seen_position_uids:
                raise AssertionError(
                    f"Duplicate position_uid in snapshot: {leg.position_uid}"
                )

            seen_position_uids.add(leg.position_uid)

            if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
                raise AssertionError(
                    "Persisted leg is not reconciled: "
                    f"{leg.position_uid}={leg.reconciliation_status}"
                )

            if leg.leg_status in {
                IB_LEG_STATUS_OPEN,
                IB_LEG_STATUS_PARTIALLY_CLOSED,
            }:
                open_legs += 1

                if leg not in group.open_legs:
                    raise AssertionError("Open leg missing from group.open_legs")

                continue

            if leg.leg_status != IB_LEG_STATUS_CLOSED:
                raise AssertionError(f"Unexpected virtual-leg status: {leg.leg_status}")

            closed_legs += 1

            if leg not in group.closed_legs:
                raise AssertionError("Closed leg missing from group.closed_legs")

            if leg.protection_status != IB_PROTECTION_STATUS_NONE:
                raise AssertionError("Closed virtual leg retained protection")

    return (
        f"groups={len(snapshot.groups)}; "
        f"open_legs={open_legs}; "
        f"closed_legs={closed_legs}; "
        f"net_only_groups={net_only_groups}"
    )


def _print_snapshot(snapshot: IBPositionGroupSnapshot) -> None:
    """
    Надрукувати live IB position-group snapshot.
    """
    groups = snapshot.groups
    print("IB position groups live read-only result")
    print(f"  complete={snapshot.complete}")
    print(f"  captured_utc={snapshot.captured_utc}")
    print(f"  groups={len(groups)}")
    print(
        "  unmapped_protective_order_ids=" f"{snapshot.unmapped_protective_order_ids}"
    )

    for index, group in enumerate(groups, start=1):
        print(
            f"  group[{index}] "
            f"symbol={group.symbol_name} "
            f"mode={group.group_mode} "
            f"broker_present={group.broker_position_present} "
            f"broker_side={group.broker_side} "
            f"broker_volume={_format_number(group.broker_volume)} "
            f"broker_kind={group.broker_position_kind} "
            f"status={group.reconciliation_status} "
            f"leg_operations={group.leg_operations_enabled}"
        )
        print(
            "    "
            f"broker_position_id={group.broker_position_id} "
            f"open_legs={len(group.open_legs)} "
            f"closed_legs={len(group.closed_legs)} "
            f"signed_open_legs="
            f"{_format_number(group.signed_open_leg_volume)}"
        )

        for message in group.reconciliation_messages:
            print(f"    group_message={message}")

        for leg_index, leg in enumerate(group.legs, start=1):
            print(
                f"    leg[{leg_index}] "
                f"side={leg.side} "
                f"volume={_format_number(leg.volume)} "
                f"status={leg.leg_status} "
                f"reconciliation={leg.reconciliation_status}"
            )
            print(
                "      "
                f"parent={leg.parent_order_id} "
                f"sl_order={leg.stop_loss_order_id} "
                f"tp_order={leg.take_profit_order_id} "
                f"oca={leg.oca_group or '-'} "
                f"protection={leg.protection_status}"
            )

            for message in leg.reconciliation_messages:
                print(f"      message={message}")


def main() -> int:
    """
    Запустити live group check без зміни робочої БД.
    """
    before_digest, before_counts = _database_digest(DB_PATH)
    print(f"  source_db={DB_PATH}")

    temporary_directory = tempfile.TemporaryDirectory(
        prefix="lge_ib_position_groups_live_",
        ignore_cleanup_errors=True,
    )
    runtime_db_path = Path(temporary_directory.name) / "demo_runtime_snapshot.db"
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

        snapshot = engine.get_active_broker_position_groups()

        if not snapshot.complete:
            raise RuntimeError("IB position-group snapshot is incomplete")

        _print_snapshot(snapshot)
        consistency = _validate_snapshot_consistency(snapshot)
        print(f"  snapshot_consistency={consistency}")
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
        raise AssertionError("Live position-group check modified SQLite")

    print("IB_POSITION_GROUPS_LIVE_READONLY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
