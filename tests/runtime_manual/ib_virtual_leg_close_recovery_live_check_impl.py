"""Controlled recovery of one already executed IB virtual-leg Close."""

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
        BACKUP_DIRECTORY / f"demo_before_ib_virtual_leg_close_recovery_{timestamp}.db"
    )
    _copy_database_snapshot(DB_PATH, backup_path)
    return backup_path


def _mapping_to_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("Virtual-leg seed has an invalid structure")

    return {str(key): item for key, item in value.items()}


def _select_open_leg(engine: RuntimeEngine) -> dict[str, Any]:
    seeds = engine.repository.get_open_ib_virtual_position_leg_seeds()

    if not seeds:
        raise RuntimeError("У schema v5 немає OPEN IB virtual legs")

    print("Відкриті persisted IB virtual legs:")

    for index, seed in enumerate(seeds, start=1):
        print(
            f"  {index} - {seed['symbol_name']} "
            f"{seed['logical_side']} {seed['logical_volume']} | "
            f"position_uid={seed['position_uid']} | "
            f"parent={seed['persisted_parent_order_id']} | "
            f"SL={seed['persisted_stop_loss_order_id']} | "
            f"TP={seed['persisted_take_profit_order_id']}"
        )

    selected: dict[str, Any] | None = None

    while selected is None:
        raw_value = input("Виберіть leg [1]: ").strip() or "1"

        try:
            selected_index = int(raw_value)
        except ValueError:
            print("Потрібен номер leg.")
            continue

        if 1 <= selected_index <= len(seeds):
            selected = _mapping_to_dict(seeds[selected_index - 1])
        else:
            print("Немає leg з таким номером.")

    return selected


def _read_close_order_id(default_value: int = 128) -> int:
    selected: int | None = None

    while selected is None:
        raw_value = input(
            f"Вже виконаний close MARKET order ID [{default_value}]: "
        ).strip() or str(default_value)

        try:
            parsed = int(raw_value)
        except ValueError:
            print("Order ID має бути цілим числом.")
            continue

        if parsed > 0:
            selected = parsed
        else:
            print("Order ID має бути додатним.")

    return selected


def main() -> int:
    print("IB virtual-leg confirmed Close recovery")
    print("  УВАГА: цей скрипт НЕ надсилає новий торговий ордер.")
    print(f"  source_db={DB_PATH}")
    engine = RuntimeEngine(db_path=str(DB_PATH))
    service = IBRuntimeService()

    try:
        seed = _select_open_leg(engine)
        position_uid = str(seed.get("position_uid") or "").strip()
        close_order_id = _read_close_order_id()
        print()
        print("Буде відновлено persistence вже виконаного Close:")
        print(f"  position_uid={position_uid}")
        print(f"  symbol={seed.get('symbol_name')}")
        print(f"  side={seed.get('logical_side')}")
        print(f"  volume={seed.get('logical_volume')}")
        print(f"  close_order_id={close_order_id}")
        confirmation = input("Для підтвердження введіть RECOVER: ").strip().upper()

        if confirmation != "RECOVER":
            print("Відновлення скасовано користувачем.")
            return 0

        backup_path = _create_backup()
        engine.set_ib_runtime_service(service)

        if not engine.connect_ib_demo():
            raise RuntimeError("IB Paper connection was not established")

        result = engine.recover_confirmed_runtime_position_leg_close(
            position_uid=position_uid,
            close_order_id=close_order_id,
        )
        persisted = engine.repository.get_ib_virtual_position_leg(position_uid)

        if persisted is None or persisted.get("leg_status") != (IB_LEG_STATUS_CLOSED):
            raise RuntimeError("Recovered persisted leg is not CLOSED")

        active_orders = engine.repository.get_ib_virtual_position_leg_orders(
            position_uid=position_uid,
            active_only=True,
        )
        active_roles = {str(row["order_role"]) for row in active_orders}

        if active_roles != {IB_LEG_ORDER_ROLE_PARENT}:
            raise RuntimeError("Recovered protection remained active")

        history = engine.repository.get_ib_virtual_position_leg_orders(
            position_uid=position_uid,
            active_only=False,
        )
        close_ids = {
            int(row["broker_order_id"])
            for row in history
            if row["order_role"] == IB_LEG_ORDER_ROLE_CLOSE
        }

        if close_ids != {close_order_id}:
            raise RuntimeError("Recovered close order history differs")

        open_seeds = engine.repository.get_open_ib_virtual_position_leg_seeds()
        persistence = dict(result.get("persistence") or {})

        print("IB virtual-leg Close recovery result")
        print(f"  position_uid={position_uid}")
        print(f"  close_order_id={close_order_id}")
        print(f"  already_recovered={result.get('already_recovered')}")
        print(f"  leg_status={persisted.get('leg_status')}")
        print("  remaining_volume=" f"{persisted.get('remaining_volume')}")
        print(
            "  cash_fx_virtual_observation_offset="
            f"{result.get('cash_fx_virtual_observation_offset')}"
        )
        print("  persistence_legs_written=" f"{persistence.get('legs_written')}")
        print(f"  active_order_mappings={len(active_orders)}")
        print(f"  order_history_rows={len(history)}")
        print(f"  total_open_seeds={len(open_seeds)}")
        print(f"  backup={backup_path}")
        print("IB_VIRTUAL_LEG_CLOSE_RECOVERY_LIVE_CHECK=OK")
        return 0
    finally:
        service.disconnect()
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
