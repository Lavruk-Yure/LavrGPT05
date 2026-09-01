"""
Controlled real IB Paper Open with automatic virtual-leg persistence.

The script creates a consistent backup of data/demo.db, places one explicit
LGE-owned IB Forex order, and verifies that schema v5 contains the new leg and
its exact parent/SL/TP mappings.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from engine.runtime_constants import (
    IB_LEG_PERSISTENCE_STATUS_RECONCILED,
    IB_LEG_STATUS_OPEN,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_engine import RuntimeEngine
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"
BACKUP_DIRECTORY = PROJECT_ROOT / "data" / "backups"


def _read_text(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def _read_side() -> str:
    while True:
        value = _read_text("Напрям BUY/SELL", "BUY").upper()

        if value in {"BUY", "SELL"}:
            return value

        print("Введіть BUY або SELL.")


def _read_positive_float(prompt: str, default: str) -> float:
    selected_value: float | None = None

    while selected_value is None:
        text = _read_text(prompt, default).replace(",", ".")

        try:
            value = float(text)
        except ValueError:
            print("Потрібне числове значення.")
            continue

        if value <= 0.0:
            print("Значення повинно бути більше нуля.")
            continue

        selected_value = value

    return selected_value


def _read_optional_float(prompt: str) -> float | None:
    while True:
        text = input(f"{prompt} [порожньо = без рівня]: ").strip()

        if not text:
            return None

        try:
            value = float(text.replace(",", "."))
        except ValueError:
            print("Потрібне числове значення або порожній рядок.")
            continue

        if value <= 0.0:
            print("Значення повинно бути більше нуля.")
            continue

        return value


def _copy_database_snapshot(source_path: Path, target_path: Path) -> None:
    source_uri = f"file:{source_path.resolve().as_posix()}?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _create_backup() -> Path:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIRECTORY / f"demo_before_ib_virtual_leg_open_{timestamp}.db"
    _copy_database_snapshot(DB_PATH, backup_path)
    return backup_path


def _confirm_order(
    *,
    symbol_name: str,
    side: str,
    lots: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> bool:
    print()
    print("Буде виконано реальний IB Paper MARKET Open:")
    print(f"  symbol={symbol_name}")
    print(f"  side={side}")
    print(f"  lots={lots}")
    print(f"  stop_loss={stop_loss}")
    print(f"  take_profit={take_profit}")
    confirmation = input("Для підтвердження введіть OPEN: ").strip().upper()
    return confirmation == "OPEN"


def main() -> int:
    print("IB virtual-leg live Open persistence check")
    print(f"  source_db={DB_PATH}")

    symbol_name = _read_text("Торговий символ", "EURUSD").upper()
    side = _read_side()
    lots = _read_positive_float("Розмір лота", "0.01")
    stop_loss = _read_optional_float("Stop Loss")
    take_profit = _read_optional_float("Take Profit")

    if not _confirm_order(
        symbol_name=symbol_name,
        side=side,
        lots=lots,
        stop_loss=stop_loss,
        take_profit=take_profit,
    ):
        print("IB virtual-leg Open скасовано користувачем.")
        return 0

    backup_path = _create_backup()
    engine = RuntimeEngine(db_path=str(DB_PATH))
    service = IBRuntimeService()

    try:
        engine.set_ib_runtime_service(service)

        if not engine.connect_ib_demo():
            raise RuntimeError("IB Paper connection was not established")

        result = engine.place_manual_market_order(
            symbol_name=symbol_name,
            side=side,
            lots=lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment="RoadMap90 live virtual-leg Open persistence check",
        )
        position_uid = str(result.get("position_uid") or "").strip()
        persistence_status = (
            str(result.get("virtual_leg_persistence_status") or "").strip().upper()
        )
        persistence_error = str(
            result.get("virtual_leg_persistence_error") or ""
        ).strip()
        broker_result = dict(result.get("broker_result") or {})

        print("IB virtual-leg live Open result")
        print(f"  position_uid={position_uid or '-'}")
        print(f"  parent_order_id={broker_result.get('parent_order_id')}")
        print("  stop_loss_order_id=" f"{broker_result.get('stop_loss_order_id')}")
        print("  take_profit_order_id=" f"{broker_result.get('take_profit_order_id')}")
        print(f"  persistence_status={persistence_status}")
        print(f"  persistence_error={persistence_error or '-'}")
        print(f"  backup={backup_path}")

        if not position_uid:
            raise RuntimeError(
                "Broker order was filled, but Runtime position was not found"
            )

        if persistence_status != IB_LEG_PERSISTENCE_STATUS_RECONCILED:
            raise RuntimeError(
                "Broker order was filled, but virtual-leg persistence failed: "
                f"{persistence_error or persistence_status}"
            )

        leg = engine.repository.get_ib_virtual_position_leg(position_uid)

        if leg is None:
            raise RuntimeError("Persisted virtual leg was not found")

        if str(leg.get("leg_status") or "") != IB_LEG_STATUS_OPEN:
            raise RuntimeError("Persisted virtual leg is not OPEN")

        if (
            str(leg.get("reconciliation_status") or "")
            != IB_RECONCILIATION_STATUS_RECONCILED
        ):
            raise RuntimeError("Persisted virtual leg is not RECONCILED")

        order_rows = engine.repository.get_ib_virtual_position_leg_orders(
            position_uid=position_uid,
            active_only=True,
        )
        open_seeds = engine.repository.get_open_ib_virtual_position_leg_seeds()

        print(f"  leg_side={leg.get('side')}")
        print(f"  initial_volume={leg.get('initial_volume')}")
        print(f"  remaining_volume={leg.get('remaining_volume')}")
        print(f"  entry_price={leg.get('entry_price')}")
        print(f"  protection_status={leg.get('protection_status')}")
        print(f"  active_order_mappings={len(order_rows)}")
        print(f"  total_open_seeds={len(open_seeds)}")
        print("IB_VIRTUAL_LEG_OPEN_LIVE_CHECK=OK")
    finally:
        service.disconnect()
        engine.connection.close()

    return 0
