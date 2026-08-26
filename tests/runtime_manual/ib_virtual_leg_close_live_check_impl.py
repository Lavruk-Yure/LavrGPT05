"""Controlled real IB Paper exact virtual-leg Close check."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_CLOSE,
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"
BACKUP_DIRECTORY = PROJECT_ROOT / "data" / "backups"


def _copy_database_snapshot(source_path: Path, target_path: Path) -> None:
    source_uri = f"file:{source_path.resolve().as_posix()}?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _create_backup() -> Path:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIRECTORY
        / f"demo_before_ib_virtual_leg_close_{timestamp}.db"
    )
    _copy_database_snapshot(DB_PATH, backup_path)
    return backup_path


def _mapping_to_text_key_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("Virtual-leg seed has an invalid structure")

    return {str(key): item for key, item in value.items()}


def _select_open_leg(engine: RuntimeEngine) -> dict[str, Any]:
    seeds = engine.repository.get_open_ib_virtual_position_leg_seeds()

    if not seeds:
        raise RuntimeError("У schema v5 немає OPEN IB virtual legs")

    print("Відкриті IB virtual legs:")

    for index, seed in enumerate(seeds, start=1):
        print(
            f"  {index} - {seed['symbol_name']} "
            f"{seed['logical_side']} {seed['logical_volume']} | "
            f"position_uid={seed['position_uid']} | "
            f"parent={seed['persisted_parent_order_id']} | "
            f"SL order={seed['persisted_stop_loss_order_id']} | "
            f"TP order={seed['persisted_take_profit_order_id']}"
        )

    selected_leg: dict[str, Any] | None = None

    while selected_leg is None:
        value = input("Виберіть leg [1]: ").strip() or "1"

        try:
            selected_index = int(value)
        except ValueError:
            print("Потрібен номер leg.")
            continue

        if 1 <= selected_index <= len(seeds):
            selected_leg = _mapping_to_text_key_dict(
                seeds[selected_index - 1]
            )
            continue

        print("Немає leg з таким номером.")

    return selected_leg


def _validate_persisted_leg(leg: dict[str, Any]) -> None:
    if str(leg.get("leg_status") or "") != IB_LEG_STATUS_OPEN:
        raise RuntimeError("Selected persisted leg is not OPEN")

    if (
        str(leg.get("reconciliation_status") or "")
        != IB_RECONCILIATION_STATUS_RECONCILED
    ):
        raise RuntimeError("Selected persisted leg is not RECONCILED")

    if leg.get("parent_order_id") is None:
        raise RuntimeError("Selected persisted leg parent ID is missing")


def _confirm_close(leg: dict[str, Any]) -> bool:
    print()
    print("Буде виконано реальний IB Paper virtual-leg Close:")
    print(f"  position_uid={leg['position_uid']}")
    print(f"  symbol={leg['symbol']}")
    print(f"  side={leg['side']}")
    print(f"  volume={leg['remaining_volume']}")
    print(f"  parent_order_id={leg['parent_order_id']}")
    print(f"  stop_loss_order_id={leg['stop_loss_order_id']}")
    print(f"  take_profit_order_id={leg['take_profit_order_id']}")
    confirmation = input(
        "Для підтвердження введіть CLOSE: "
    ).strip().upper()
    return confirmation == "CLOSE"


def main() -> int:
    print("IB virtual-leg live Close check")
    print(f"  source_db={DB_PATH}")
    engine = RuntimeEngine(db_path=str(DB_PATH))
    service = IBRuntimeService()

    try:
        seed = _select_open_leg(engine)
        position_uid = str(seed.get("position_uid") or "").strip()
        leg = engine.repository.get_ib_virtual_position_leg(position_uid)

        if leg is None:
            raise RuntimeError("Selected persisted virtual leg was not found")

        _validate_persisted_leg(leg)

        if not _confirm_close(leg):
            print("IB virtual-leg Close скасовано користувачем.")
            return 0

        backup_path = _create_backup()
        engine.set_ib_runtime_service(service)

        if not engine.connect_ib_demo():
            raise RuntimeError("IB Paper connection was not established")

        result = engine.close_runtime_position_leg(position_uid)
        persisted = engine.repository.get_ib_virtual_position_leg(
            position_uid
        )

        if persisted is None:
            raise RuntimeError("Closed persisted virtual leg was lost")

        if persisted.get("leg_status") != IB_LEG_STATUS_CLOSED:
            raise RuntimeError("Persisted virtual leg is not CLOSED")

        if float(persisted.get("remaining_volume") or 0.0) != 0.0:
            raise RuntimeError("Persisted closed leg volume is not zero")

        active_orders = (
            engine.repository.get_ib_virtual_position_leg_orders(
                position_uid=position_uid,
                active_only=True,
            )
        )
        active_roles = {str(row["order_role"]) for row in active_orders}

        if active_roles != {IB_LEG_ORDER_ROLE_PARENT}:
            raise RuntimeError("Protective mapping remained active after Close")

        order_history = (
            engine.repository.get_ib_virtual_position_leg_orders(
                position_uid=position_uid,
                active_only=False,
            )
        )
        close_rows = [
            row
            for row in order_history
            if row["order_role"] == IB_LEG_ORDER_ROLE_CLOSE
        ]

        if len(close_rows) != 1:
            raise RuntimeError("Close order mapping was not persisted uniquely")

        open_seeds = (
            engine.repository.get_open_ib_virtual_position_leg_seeds()
        )
        persistence = dict(result.get("persistence") or {})
        broker_result = dict(result.get("broker_result") or {})

        print("IB virtual-leg live Close result")
        print(f"  position_uid={position_uid}")
        print(f"  close_order_id={result.get('close_order_id')}")
        print(f"  close_side={result.get('close_side')}")
        print(f"  close_quantity={result.get('close_quantity')}")
        print(f"  leg_status={persisted.get('leg_status')}")
        print(
            "  remaining_volume="
            f"{persisted.get('remaining_volume')}"
        )
        print(
            "  cancelled_order_ids="
            f"{broker_result.get('cancelled_order_ids')}"
        )
        print(
            "  persistence_legs_written="
            f"{persistence.get('legs_written')}"
        )
        print(f"  active_order_mappings={len(active_orders)}")
        print(f"  order_history_rows={len(order_history)}")
        print(f"  total_open_seeds={len(open_seeds)}")
        print(f"  backup={backup_path}")
        print("IB_VIRTUAL_LEG_CLOSE_LIVE_CHECK=OK")
    finally:
        service.disconnect()
        engine.connection.close()

    return 0
