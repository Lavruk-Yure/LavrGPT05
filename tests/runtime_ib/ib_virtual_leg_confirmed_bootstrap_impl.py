"""
One-time controlled bootstrap of the four confirmed RoadMap90 IB legs.

The script asks for the mode through console input:
1 - PLAN validates evidence and writes only to a temporary SQLite copy.
2 - APPLY creates a consistent backup and writes to data/demo.db.
"""

from __future__ import annotations

import gc
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from engine.db.runtime_db import connect_runtime_db
from engine.ib_virtual_position_leg import IBVirtualPositionLeg
from engine.runtime_constants import (
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_STOP_ORDER_TYPES,
    IB_TAKE_PROFIT_ORDER_TYPES,
)
from engine.runtime_engine import RuntimeEngine
from engine.runtime_repository import RuntimeRepository
from engine.services.ib_runtime_service import IBRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "demo.db"
BACKUP_DIRECTORY = PROJECT_ROOT / "data" / "backups"
ACCOUNT_ID = "DUM513747"
CURRENT_CLIENT_ID = 1
CONFIRMED_CAPTURED_UTC = "2026-07-16T16:23:58+00:00"


def _copy_database_snapshot(source_path: Path, target_path: Path) -> None:
    resolved_source = source_path.resolve()
    source_uri = f"file:{resolved_source.as_posix()}?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target_path) as target_connection:
            source_connection.backup(target_connection)


def _build_confirmed_legs() -> list[IBVirtualPositionLeg]:
    message = (
        "Controlled bootstrap from complete live reconciliation captured "
        f"{CONFIRMED_CAPTURED_UTC}; exact close timestamp was not persisted"
    )
    return [
        IBVirtualPositionLeg(
            position_uid="9c2f63dd-9343-4f0a-a36e-89e2bfb46d1c",
            trade_uid="365e1950-645d-4779-9879-9a3b8b1ad80b",
            broker_position_id=f"IB:{ACCOUNT_ID}:EURUSD",
            account_id=ACCOUNT_ID,
            symbol_name="EURUSD",
            side="BUY",
            volume=1000.0,
            entry_price=1.14685,
            opened_utc="2026-07-16T08:51:37+00:00",
            source="MANUAL",
            parent_order_id=111,
            stop_loss_order_id=113,
            stop_loss=1.144,
            oca_group="1620614043",
            leg_status=IB_LEG_STATUS_CLOSED,
            protection_status=IB_PROTECTION_STATUS_NONE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
            reconciliation_messages=(message,),
        ),
        IBVirtualPositionLeg(
            position_uid="a3badcf4-d572-4e03-a8e5-afb9b43ffaac",
            trade_uid="84c99573-ab3d-4c54-93c6-15da1532ea3f",
            broker_position_id=f"IB:{ACCOUNT_ID}:EURUSD",
            account_id=ACCOUNT_ID,
            symbol_name="EURUSD",
            side="BUY",
            volume=2000.0,
            entry_price=1.14665,
            opened_utc="2026-07-16T08:53:31+00:00",
            source="MANUAL",
            parent_order_id=114,
            stop_loss_order_id=116,
            take_profit_order_id=115,
            stop_loss=1.143,
            take_profit=1.152,
            oca_group="1620614047",
            leg_status=IB_LEG_STATUS_OPEN,
            protection_status=IB_PROTECTION_STATUS_COMPLETE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
            reconciliation_messages=(message,),
        ),
        IBVirtualPositionLeg(
            position_uid="70800966-87f3-4574-9054-290ab986fbfe",
            trade_uid="ddaf2775-a7cb-416c-8073-b959f5c59a7c",
            broker_position_id=f"IB:{ACCOUNT_ID}:GBPUSD",
            account_id=ACCOUNT_ID,
            symbol_name="GBPUSD",
            side="BUY",
            volume=3000.0,
            entry_price=1.35225,
            opened_utc="2026-07-16T08:56:44+00:00",
            source="MANUAL",
            parent_order_id=117,
            stop_loss_order_id=119,
            stop_loss=1.349,
            oca_group="1620614054",
            leg_status=IB_LEG_STATUS_CLOSED,
            protection_status=IB_PROTECTION_STATUS_NONE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
            reconciliation_messages=(message,),
        ),
        IBVirtualPositionLeg(
            position_uid="52a6c682-1564-4d09-9517-93b18f6f0123",
            trade_uid="07dfbc4b-35c7-4a5c-bf02-53fdcb324d87",
            broker_position_id=f"IB:{ACCOUNT_ID}:GBPUSD",
            account_id=ACCOUNT_ID,
            symbol_name="GBPUSD",
            side="SELL",
            volume=2000.0,
            entry_price=1.35165,
            opened_utc="2026-07-16T09:17:36+00:00",
            source="MANUAL",
            parent_order_id=120,
            take_profit_order_id=121,
            take_profit=1.349,
            oca_group="1620614064",
            leg_status=IB_LEG_STATUS_CLOSED,
            protection_status=IB_PROTECTION_STATUS_NONE,
            reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
            reconciliation_messages=(message,),
        ),
    ]


def _parent_mapping(leg: IBVirtualPositionLeg) -> dict[str, Any]:
    return {
        "position_uid": leg.position_uid,
        "order_role": IB_LEG_ORDER_ROLE_PARENT,
        "broker_order_id": leg.parent_order_id,
        "parent_id": None,
        "client_id": CURRENT_CLIENT_ID,
        "action": leg.side,
        "order_type": "MKT",
        "quantity": leg.volume,
        "price": leg.entry_price,
        "execution_status": "FILLED",
        "is_active": True,
    }


def _protective_mapping(
    leg: IBVirtualPositionLeg,
    order_role: str,
    broker_order_id: int,
    order_type: str,
    price: float,
    execution_status: str,
    is_active: bool,
) -> dict[str, Any]:
    return {
        "position_uid": leg.position_uid,
        "order_role": order_role,
        "broker_order_id": broker_order_id,
        "parent_id": leg.parent_order_id,
        "client_id": CURRENT_CLIENT_ID,
        "action": leg.protective_action,
        "order_type": order_type,
        "quantity": leg.volume,
        "price": price,
        "oca_group": leg.oca_group,
        "oca_type": 1,
        "execution_status": execution_status,
        "is_active": is_active,
    }


def _build_confirmed_order_mappings(
    legs: list[IBVirtualPositionLeg],
) -> list[dict[str, Any]]:
    result = [_parent_mapping(leg) for leg in legs]
    result.extend(
        [
            _protective_mapping(
                leg=legs[0],
                order_role=IB_LEG_ORDER_ROLE_STOP_LOSS,
                broker_order_id=113,
                order_type="STP",
                price=1.144,
                execution_status="FILLED",
                is_active=False,
            ),
            _protective_mapping(
                leg=legs[1],
                order_role=IB_LEG_ORDER_ROLE_STOP_LOSS,
                broker_order_id=116,
                order_type="STP",
                price=1.143,
                execution_status="SUBMITTED",
                is_active=True,
            ),
            _protective_mapping(
                leg=legs[1],
                order_role=IB_LEG_ORDER_ROLE_TAKE_PROFIT,
                broker_order_id=115,
                order_type="LMT",
                price=1.152,
                execution_status="SUBMITTED",
                is_active=True,
            ),
            _protective_mapping(
                leg=legs[2],
                order_role=IB_LEG_ORDER_ROLE_STOP_LOSS,
                broker_order_id=119,
                order_type="STP",
                price=1.349,
                execution_status="FILLED",
                is_active=False,
            ),
            _protective_mapping(
                leg=legs[3],
                order_role=IB_LEG_ORDER_ROLE_TAKE_PROFIT,
                broker_order_id=121,
                order_type="LMT",
                price=1.349,
                execution_status="FILLED",
                is_active=False,
            ),
        ]
    )
    return result


def _capture_live_evidence() -> dict[str, Any]:
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="lge_ib_leg_bootstrap_evidence_",
        ignore_cleanup_errors=True,
    )
    runtime_db_path = Path(temporary_directory.name) / "runtime.db"
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

        if not evidence.get("complete"):
            raise RuntimeError("IB virtual-leg evidence is incomplete")

        return evidence
    finally:
        if connected:
            service.disconnect()

        engine.connection.close()
        del engine
        del service
        gc.collect()
        temporary_directory.cleanup()


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        text = value.strip()

        if not text:
            return None

        try:
            return float(text)
        except ValueError:
            return None

    return None


def _safe_float(value: object) -> float:
    number = _optional_float(value)
    return number if number is not None else 0.0


def _optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not value.is_integer():
            return None
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()

        if not text:
            return None

        try:
            number = int(text)
        except ValueError:
            return None
    else:
        return None

    return number if number > 0 else None


def _order_price(row: dict[str, Any]) -> float:
    order_type = str(row.get("order_type") or "").strip().upper()

    if order_type in IB_STOP_ORDER_TYPES:
        return _safe_float(row.get("aux_price"))

    return _safe_float(row.get("lmt_price"))


def _validate_live_active_orders(evidence: dict[str, Any]) -> None:
    expected = {
        115: {
            "order_type": "LMT",
            "quantity": 2000.0,
            "price": 1.152,
        },
        116: {
            "order_type": "STP",
            "quantity": 2000.0,
            "price": 1.143,
        },
    }
    relevant_rows: list[dict[str, Any]] = []

    for row in evidence.get("open_orders") or []:
        account = str(row.get("account") or "").strip()
        symbol = str(row.get("symbol_name") or "").strip().upper()
        order_type = str(row.get("order_type") or "").strip().upper()

        if (
            account == ACCOUNT_ID
            and symbol in {"EURUSD", "GBPUSD"}
            and order_type in IB_STOP_ORDER_TYPES | IB_TAKE_PROFIT_ORDER_TYPES
        ):
            relevant_rows.append(dict(row))

    rows_by_id: dict[int, dict[str, Any]] = {}

    for row in relevant_rows:
        order_id = _optional_positive_int(row.get("order_id"))

        if order_id is not None:
            rows_by_id[order_id] = row

    if set(rows_by_id) != set(expected):
        raise RuntimeError(
            "Live active protective orders differ from confirmed 115/116"
        )

    oca_groups: set[str] = set()

    for order_id, expected_row in expected.items():
        row = rows_by_id[order_id]
        order_type = str(row.get("order_type") or "").strip().upper()
        quantity = _safe_float(row.get("total_quantity", row.get("quantity")))
        price = _order_price(row)

        if order_type != expected_row["order_type"]:
            raise RuntimeError(f"Live order type differs for order {order_id}")

        if abs(quantity - expected_row["quantity"]) > 1e-9:
            raise RuntimeError(f"Live order quantity differs for order {order_id}")

        if abs(price - expected_row["price"]) > 1e-9:
            raise RuntimeError(f"Live order price differs for order {order_id}")

        if str(row.get("action") or "").strip().upper() != "SELL":
            raise RuntimeError(f"Live protective action differs for order {order_id}")

        if not bool(row.get("same_client_id")):
            raise RuntimeError(f"Live protective order {order_id} has foreign clientId")

        oca_groups.add(str(row.get("oca_group") or "").strip())

    if oca_groups != {"1620614047"}:
        raise RuntimeError("Live protective OCA group differs")


def _backup_database() -> Path:
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = (
        BACKUP_DIRECTORY / f"demo_before_ib_virtual_leg_bootstrap_{timestamp}.db"
    )
    _copy_database_snapshot(DB_PATH, backup_path)
    return backup_path


def _run_bootstrap(db_path: Path) -> BootstrapResult:
    connection = connect_runtime_db(db_path)
    repository = RuntimeRepository(connection)
    legs = _build_confirmed_legs()
    order_mappings = _build_confirmed_order_mappings(legs)

    try:
        result = repository.bootstrap_confirmed_ib_virtual_position_leg_snapshot(
            legs=legs,
            order_mappings=order_mappings,
            closed_utc_by_position_uid={leg.position_uid: None for leg in legs},
        )
        leg_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM ib_virtual_position_legs"
            ).fetchone()[0]
        )
        order_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM ib_virtual_position_leg_orders"
            ).fetchone()[0]
        )
        active_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM ib_virtual_position_leg_orders
                WHERE is_active = 1
                """
            ).fetchone()[0]
        )
        open_seed_count = len(
            repository.get_open_ib_virtual_position_leg_seeds(account_id=ACCOUNT_ID)
        )
    finally:
        connection.close()

    return {
        "already_applied": bool(result.get("already_applied")),
        "leg_count": leg_count,
        "order_count": order_count,
        "active_count": active_count,
        "open_seed_count": open_seed_count,
    }


BootstrapMode = Literal["PLAN", "APPLY"]


class BootstrapResult(TypedDict):
    already_applied: bool
    leg_count: int
    order_count: int
    active_count: int
    open_seed_count: int


def _run_selected_mode(
    mode: BootstrapMode,
) -> tuple[Path | None, BootstrapResult]:
    if mode == "APPLY":
        backup_path = _backup_database()
        result = _run_bootstrap(DB_PATH)
        return backup_path, result

    with tempfile.TemporaryDirectory(
        prefix="lge_ib_leg_bootstrap_plan_",
        ignore_cleanup_errors=True,
    ) as temporary_directory:
        target_path = Path(temporary_directory) / "demo_plan.db"
        _copy_database_snapshot(DB_PATH, target_path)
        result = _run_bootstrap(target_path)

    return None, result


def _read_mode_from_console() -> BootstrapMode:
    print("IB virtual-leg confirmed bootstrap")
    print("  1 - PLAN: перевірка без запису в робочу demo.db")
    print("  2 - APPLY: резервна копія і запис у робочу demo.db")

    selected_mode: BootstrapMode | None = None

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
                continue

            print("Запис скасовано. Виберіть режим ще раз.")
            continue

        print("Невірний вибір. Введіть 1 або 2.")

    return selected_mode


def main() -> int:
    mode = _read_mode_from_console()

    print(f"  source_db={DB_PATH}")
    evidence = _capture_live_evidence()
    _validate_live_active_orders(evidence)
    print("  live_active_orders=[115, 116]")
    print("  live_oca_group=1620614047")

    backup_path, result = _run_selected_mode(mode)

    print("IB confirmed virtual-leg bootstrap result")
    print(f"  mode={mode}")
    print(f"  already_applied={result['already_applied']}")
    print(f"  legs={result['leg_count']}")
    print(f"  order_history={result['order_count']}")
    print(f"  active_mappings={result['active_count']}")
    print(f"  open_seeds={result['open_seed_count']}")

    if backup_path is not None:
        print(f"  backup={backup_path}")

    if result["leg_count"] != 4:
        raise AssertionError("Confirmed bootstrap leg count differs")

    if result["order_count"] != 9 or result["active_count"] != 6:
        raise AssertionError("Confirmed bootstrap order mapping differs")

    if result["open_seed_count"] != 1:
        raise AssertionError("Confirmed bootstrap open leg count differs")

    print("IB_VIRTUAL_LEG_CONFIRMED_BOOTSTRAP=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
