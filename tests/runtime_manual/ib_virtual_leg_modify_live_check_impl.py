"""
Controlled real IB Paper virtual-leg SL/TP Modify check.

The script selects one persisted OPEN virtual leg by position_uid, creates a
consistent backup of data/demo.db, executes the RoadMap89 broker operation for
that exact leg, and verifies the schema v5 persistence update.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
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
    backup_path = BACKUP_DIRECTORY / f"demo_before_ib_virtual_leg_modify_{timestamp}.db"
    _copy_database_snapshot(DB_PATH, backup_path)
    return backup_path


def _optional_float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(value, (int, float, str)):
        return None

    try:
        number = float(value)
    except ValueError:
        return None

    if not math.isfinite(number):
        return None

    return number


def _read_optional_price(
    prompt: str,
    current_value: float | None,
) -> float | None:
    current_text = str(current_value) if current_value is not None else "NONE"

    while True:
        text = (
            input(f"{prompt} [{current_text}; NONE = CANCEL]: ")
            .strip()
            .replace(",", ".")
        )

        if not text:
            return current_value

        if text.upper() in {"NONE", "CANCEL", "-"}:
            return None

        parsed_value = _optional_float_value(text)

        if parsed_value is None:
            print("Потрібне числове значення або NONE.")
            continue

        if parsed_value <= 0.0:
            print("Значення повинно бути більше нуля.")
            continue

        return parsed_value


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
            f"SL={seed['persisted_stop_loss']} | "
            f"TP={seed['persisted_take_profit']}"
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
            selected_leg = _mapping_to_text_key_dict(seeds[selected_index - 1])
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

    for price_key, order_id_key, label in (
        ("stop_loss", "stop_loss_order_id", "Stop Loss"),
        ("take_profit", "take_profit_order_id", "Take Profit"),
    ):
        price_present = leg.get(price_key) is not None
        order_id_present = leg.get(order_id_key) is not None

        if price_present != order_id_present:
            raise RuntimeError(f"Selected persisted leg {label} identity differs")


def _confirm_modify(
    *,
    leg: dict[str, Any],
    stop_loss: float | None,
    take_profit: float | None,
) -> bool:
    print()
    print("Буде виконано реальний IB Paper virtual-leg Modify:")
    print(f"  position_uid={leg['position_uid']}")
    print(f"  symbol={leg['symbol']}")
    print(f"  side={leg['side']}")
    print(f"  volume={leg['remaining_volume']}")
    print(
        f"  Stop Loss: {leg['stop_loss']} -> {stop_loss} "
        f"(order {leg['stop_loss_order_id']})"
    )
    print(
        f"  Take Profit: {leg['take_profit']} -> {take_profit} "
        f"(order {leg['take_profit_order_id']})"
    )
    confirmation = input("Для підтвердження введіть MODIFY: ").strip().upper()
    return confirmation == "MODIFY"


def _prices_equal(
    left: object,
    right: float | None,
) -> bool:
    left_number = _optional_float_value(left)

    if left_number is None or right is None:
        return left_number is None and right is None

    return math.isclose(
        left_number,
        right,
        rel_tol=1e-9,
        abs_tol=1e-10,
    )


def _active_order_id(
    by_role: dict[str, dict[str, Any]],
    order_role: str,
) -> object:
    row = by_role.get(order_role)

    if row is None:
        return None

    return row.get("broker_order_id")


def main() -> int:
    print("IB virtual-leg live SL/TP Modify check")
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
        stop_loss = _read_optional_price(
            "Новий Stop Loss",
            _optional_float_value(leg.get("stop_loss")),
        )
        take_profit = _read_optional_price(
            "Новий Take Profit",
            _optional_float_value(leg.get("take_profit")),
        )

        if _prices_equal(leg["stop_loss"], stop_loss) and _prices_equal(
            leg["take_profit"], take_profit
        ):
            raise RuntimeError("Обидва рівні залишилися без змін")

        if not _confirm_modify(
            leg=leg,
            stop_loss=stop_loss,
            take_profit=take_profit,
        ):
            print("IB virtual-leg Modify скасовано користувачем.")
            return 0

        backup_path = _create_backup()
        engine.set_ib_runtime_service(service)

        if not engine.connect_ib_demo():
            raise RuntimeError("IB Paper connection was not established")

        result = engine.modify_runtime_position_leg_sl_tp(
            position_uid=position_uid,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        persisted = engine.repository.get_ib_virtual_position_leg(position_uid)

        if persisted is None:
            raise RuntimeError("Modified persisted virtual leg was lost")

        if not _prices_equal(persisted.get("stop_loss"), stop_loss):
            raise RuntimeError("Persisted Stop Loss differs after Modify")

        if not _prices_equal(persisted.get("take_profit"), take_profit):
            raise RuntimeError("Persisted Take Profit differs after Modify")

        active_orders = engine.repository.get_ib_virtual_position_leg_orders(
            position_uid=position_uid,
            active_only=True,
        )
        by_role = {str(row["order_role"]): row for row in active_orders}
        broker_result = dict(result.get("broker_result") or {})
        persistence = dict(result.get("persistence") or {})

        print("IB virtual-leg live Modify result")
        print(f"  position_uid={position_uid}")
        print(f"  stop_loss={persisted.get('stop_loss')}")
        print(f"  take_profit={persisted.get('take_profit')}")
        print(
            "  stop_loss_order_id="
            f"{_active_order_id(by_role, IB_LEG_ORDER_ROLE_STOP_LOSS)}"
        )
        print(
            "  take_profit_order_id="
            f"{_active_order_id(by_role, IB_LEG_ORDER_ROLE_TAKE_PROFIT)}"
        )
        print(f"  oca_group={persisted.get('oca_group')}")
        print("  stop_loss_action=" f"{broker_result.get('stop_loss_action')}")
        print("  take_profit_action=" f"{broker_result.get('take_profit_action')}")
        print(
            "  operation_order_ids="
            f"{sorted(broker_result.get('operation_order_ids') or [])}"
        )
        print("  persistence_legs_written=" f"{persistence.get('legs_written')}")
        print(f"  active_order_mappings={len(active_orders)}")
        print(f"  backup={backup_path}")
        print("IB_VIRTUAL_LEG_MODIFY_LIVE_CHECK=OK")
    finally:
        service.disconnect()
        engine.connection.close()

    return 0
