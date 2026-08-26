"""
Перевірка контрольованого historical bootstrap IB virtual legs.

RoadMap90:
- exact legacy identity validation;
- atomic current-leg та broker-order persistence;
- idempotent repeat;
- conflicting bootstrap is rejected before SQLite changes.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
)
from engine.runtime_repository import RuntimeRepository

ACCOUNT_ID = "DUM513747"
CLIENT_ID = 1


def _database_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
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
        cursor = connection.execute(
            f'SELECT * FROM "{quoted_name}" ORDER BY rowid'
        )
        digest.update(str(table_name).encode("utf-8"))

        for row in cursor.fetchall():
            digest.update(repr(tuple(row)).encode("utf-8"))

    return digest.hexdigest()


def _create_legacy_leg(
    repository: RuntimeRepository,
    symbol: str,
    logical_side: str,
    logical_volume: float,
    parent_order_id: int,
    broker_snapshot_side: str,
    broker_snapshot_volume: float,
    broker_snapshot_price: float,
    opened_utc: str,
) -> tuple[str, str]:
    trade_uid = repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol=symbol,
        side=logical_side,
        volume=logical_volume,
        source="MANUAL",
    )
    plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=logical_side,
        volume=logical_volume,
        source="MANUAL",
    )
    broker_order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=plan_uid,
        broker="IB",
        broker_order_id=str(parent_order_id),
        execution_status="FILLED",
        source="MANUAL",
    )
    position_uid = repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=f"IB:{ACCOUNT_ID}:{symbol}",
        symbol=symbol,
        side=broker_snapshot_side,
        volume=broker_snapshot_volume,
        open_price=broker_snapshot_price,
        opened_utc=opened_utc,
        source="BROKER",
    )
    return trade_uid, position_uid


def _parent_mapping(leg: IBVirtualPositionLeg) -> dict[str, Any]:
    return {
        "position_uid": leg.position_uid,
        "order_role": IB_LEG_ORDER_ROLE_PARENT,
        "broker_order_id": leg.parent_order_id,
        "parent_id": None,
        "client_id": CLIENT_ID,
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
        "client_id": CLIENT_ID,
        "action": leg.protective_action,
        "order_type": order_type,
        "quantity": leg.volume,
        "price": price,
        "oca_group": leg.oca_group,
        "oca_type": 1,
        "execution_status": execution_status,
        "is_active": is_active,
    }


def _build_fixture(
    repository: RuntimeRepository,
) -> tuple[
    list[IBVirtualPositionLeg],
    list[dict[str, Any]],
    dict[str, str | None],
]:
    eur1_trade, eur1_position = _create_legacy_leg(
        repository=repository,
        symbol="EURUSD",
        logical_side="BUY",
        logical_volume=1000.0,
        parent_order_id=111,
        broker_snapshot_side="BUY",
        broker_snapshot_volume=1000.0,
        broker_snapshot_price=1.14885,
        opened_utc="2026-07-16T08:51:37+00:00",
    )
    eur2_trade, eur2_position = _create_legacy_leg(
        repository=repository,
        symbol="EURUSD",
        logical_side="BUY",
        logical_volume=2000.0,
        parent_order_id=114,
        broker_snapshot_side="BUY",
        broker_snapshot_volume=3000.0,
        broker_snapshot_price=1.147383333333333,
        opened_utc="2026-07-16T08:53:31+00:00",
    )
    gbp1_trade, gbp1_position = _create_legacy_leg(
        repository=repository,
        symbol="GBPUSD",
        logical_side="BUY",
        logical_volume=3000.0,
        parent_order_id=117,
        broker_snapshot_side="BUY",
        broker_snapshot_volume=3000.0,
        broker_snapshot_price=1.35225,
        opened_utc="2026-07-16T08:56:44+00:00",
    )
    gbp2_trade, gbp2_position = _create_legacy_leg(
        repository=repository,
        symbol="GBPUSD",
        logical_side="SELL",
        logical_volume=2000.0,
        parent_order_id=120,
        broker_snapshot_side="BUY",
        broker_snapshot_volume=1000.0,
        broker_snapshot_price=1.352916666666667,
        opened_utc="2026-07-16T09:17:36+00:00",
    )

    legs = [
        IBVirtualPositionLeg(
            position_uid=eur1_position,
            trade_uid=eur1_trade,
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
        ),
        IBVirtualPositionLeg(
            position_uid=eur2_position,
            trade_uid=eur2_trade,
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
        ),
        IBVirtualPositionLeg(
            position_uid=gbp1_position,
            trade_uid=gbp1_trade,
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
        ),
        IBVirtualPositionLeg(
            position_uid=gbp2_position,
            trade_uid=gbp2_trade,
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
        ),
    ]

    orders = [_parent_mapping(leg) for leg in legs]
    orders.extend(
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
    closed_utc = {
        legs[0].position_uid: "2026-07-16T15:02:50+00:00",
        legs[1].position_uid: None,
        legs[2].position_uid: "2026-07-16T14:57:54+00:00",
        legs[3].position_uid: "2026-07-16T14:57:54+00:00",
    }
    return legs, orders, closed_utc


def main() -> int:
    with TemporaryDirectory(prefix="lge_ib_leg_bootstrap_") as temp_dir:
        db_path = Path(temp_dir) / "demo.db"
        connection = connect_runtime_db(db_path)
        repository = RuntimeRepository(connection)
        legs, orders, closed_utc = _build_fixture(repository)

        first_result = (
            repository.bootstrap_confirmed_ib_virtual_position_leg_snapshot(
                legs=legs,
                order_mappings=orders,
                closed_utc_by_position_uid=closed_utc,
            )
        )
        digest_after_first = _database_digest(connection)
        repeat_result = (
            repository.bootstrap_confirmed_ib_virtual_position_leg_snapshot(
                legs=legs,
                order_mappings=orders,
                closed_utc_by_position_uid=closed_utc,
            )
        )
        digest_after_repeat = _database_digest(connection)

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
        open_seeds = repository.get_open_ib_virtual_position_leg_seeds(
            account_id=ACCOUNT_ID
        )

        before_conflict = _database_digest(connection)
        conflict_rejected = False

        try:
            repository.bootstrap_confirmed_ib_virtual_position_leg_snapshot(
                legs=[replace(legs[0], parent_order_id=999), *legs[1:]],
                order_mappings=orders,
                closed_utc_by_position_uid=closed_utc,
            )
        except RuntimeError:
            conflict_rejected = True

        after_conflict = _database_digest(connection)
        connection.close()

    if first_result["already_applied"]:
        raise AssertionError("First confirmed bootstrap was not written")

    if not repeat_result["already_applied"]:
        raise AssertionError("Confirmed bootstrap repeat was not idempotent")

    if digest_after_first != digest_after_repeat:
        raise AssertionError("Idempotent bootstrap changed SQLite")

    if leg_count != 4 or order_count != 9 or active_count != 6:
        raise AssertionError("Confirmed bootstrap persistence is incomplete")

    if len(open_seeds) != 1:
        raise AssertionError("Closed confirmed legs remain in open seeds")

    if not conflict_rejected or before_conflict != after_conflict:
        raise AssertionError("Conflicting confirmed bootstrap was not safe")

    print("RuntimeRepository confirmed IB virtual-leg bootstrap result")
    print(f"  legs={leg_count}")
    print(f"  order_history={order_count}")
    print(f"  active_mappings={active_count}")
    print(f"  open_seeds={len(open_seeds)}")
    print(f"  repeat_idempotent={repeat_result['already_applied']}")
    print(f"  conflict_rejected={conflict_rejected}")
    print(
        "RUNTIME_REPOSITORY_IB_VIRTUAL_LEG_CONFIRMED_BOOTSTRAP_CHECK=OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
