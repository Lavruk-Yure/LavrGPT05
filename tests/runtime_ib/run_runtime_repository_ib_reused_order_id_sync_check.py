# run_runtime_repository_ib_reused_order_id_sync_check.py
"""Regression check for reused IB orderId persistence synchronization."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db.runtime_db import connect_runtime_db  # noqa: E402
from engine.ib_virtual_position_leg import (  # noqa: E402
    IBVirtualPositionLeg,
    build_ib_virtual_position_legs_from_repository_seeds,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_ORDER_ROLE_CLOSE,
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_repository import RuntimeRepository  # noqa: E402

ACCOUNT_ID = "DUM513747"
CURRENT_CLIENT_ID = 1


def _create_runtime_chain(
    repository: RuntimeRepository,
    *,
    symbol_name: str,
    parent_order_id: int,
    entry_price: float,
    opened_utc: str,
) -> tuple[str, str]:
    trade_uid = repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol=symbol_name,
        side="BUY",
        volume=1000.0,
    )
    order_plan_uid = repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side="BUY",
        volume=1000.0,
    )
    broker_order_uid = repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id=str(parent_order_id),
        execution_status="FILLED",
        broker_timestamp=opened_utc,
    )
    position_uid = repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=f"IB:{ACCOUNT_ID}:{symbol_name}",
        symbol=symbol_name,
        side="BUY",
        volume=1000.0,
        open_price=entry_price,
        opened_utc=opened_utc,
        state="OPEN",
    )
    return trade_uid, position_uid


def _persist_leg(
    repository: RuntimeRepository,
    *,
    symbol_name: str,
    parent_order_id: int,
    stop_loss_order_id: int,
    take_profit_order_id: int,
    parent_perm_id: int,
    stop_loss_perm_id: int,
    take_profit_perm_id: int,
    oca_group: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    opened_utc: str,
    leg_status: str,
    close_order_id: int | None = None,
) -> IBVirtualPositionLeg:
    trade_uid, position_uid = _create_runtime_chain(
        repository,
        symbol_name=symbol_name,
        parent_order_id=parent_order_id,
        entry_price=entry_price,
        opened_utc=opened_utc,
    )
    leg = IBVirtualPositionLeg(
        position_uid=position_uid,
        trade_uid=trade_uid,
        broker_position_id=f"IB:{ACCOUNT_ID}:{symbol_name}",
        account_id=ACCOUNT_ID,
        symbol_name=symbol_name,
        side="BUY",
        volume=1000.0,
        entry_price=entry_price,
        opened_utc=opened_utc,
        source="MANUAL",
        parent_order_id=parent_order_id,
        stop_loss_order_id=stop_loss_order_id,
        take_profit_order_id=take_profit_order_id,
        stop_loss=stop_loss,
        take_profit=take_profit,
        oca_group=oca_group,
        close_order_ids=(() if close_order_id is None else (close_order_id,)),
        parent_order_perm_id=parent_perm_id,
        stop_loss_order_perm_id=stop_loss_perm_id,
        take_profit_order_perm_id=take_profit_perm_id,
        leg_status=leg_status,
        protection_status=(
            IB_PROTECTION_STATUS_NONE
            if leg_status == IB_LEG_STATUS_CLOSED
            else IB_PROTECTION_STATUS_COMPLETE
        ),
        reconciliation_status=IB_RECONCILIATION_STATUS_RECONCILED,
    )
    repository.upsert_ib_virtual_position_leg(
        leg,
        remaining_volume=(0.0 if leg_status == IB_LEG_STATUS_CLOSED else 1000.0),
        closed_utc=(opened_utc if leg_status == IB_LEG_STATUS_CLOSED else None),
    )
    repository.set_active_ib_virtual_position_leg_order(
        position_uid=position_uid,
        order_role=IB_LEG_ORDER_ROLE_PARENT,
        broker_order_id=parent_order_id,
        perm_id=parent_perm_id,
        client_id=CURRENT_CLIENT_ID,
        action="BUY",
        order_type="MKT",
        quantity=1000.0,
        price=entry_price,
        execution_status="FILLED",
    )
    for role, order_id, perm_id, order_type, price in (
        (
            IB_LEG_ORDER_ROLE_STOP_LOSS,
            stop_loss_order_id,
            stop_loss_perm_id,
            "STP",
            stop_loss,
        ),
        (
            IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            take_profit_order_id,
            take_profit_perm_id,
            "LMT",
            take_profit,
        ),
    ):
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=role,
            broker_order_id=order_id,
            parent_order_id=parent_order_id,
            perm_id=perm_id,
            client_id=CURRENT_CLIENT_ID,
            action="SELL",
            order_type=order_type,
            quantity=1000.0,
            price=price,
            oca_group=oca_group,
            oca_type=3,
            execution_status="SUBMITTED",
        )

        if leg_status == IB_LEG_STATUS_CLOSED:
            repository.deactivate_ib_virtual_position_leg_order(
                position_uid=position_uid,
                order_role=role,
                execution_status="CLOSED",
            )

    if close_order_id is not None:
        repository.set_active_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_CLOSE,
            broker_order_id=close_order_id,
            execution_status="FILLED",
            client_id=CURRENT_CLIENT_ID,
            action="SELL",
            order_type="MKT",
            quantity=1000.0,
        )
        repository.deactivate_ib_virtual_position_leg_order(
            position_uid=position_uid,
            order_role=IB_LEG_ORDER_ROLE_CLOSE,
            execution_status="FILLED",
        )

    return leg


def _protective_order(
    *,
    symbol_name: str,
    order_id: int,
    parent_id: int,
    perm_id: int,
    oca_group: int,
    order_type: str,
    price: float,
) -> dict:
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "perm_id": perm_id,
        "account": ACCOUNT_ID,
        "symbol": symbol_name[:3],
        "currency": symbol_name[3:],
        "symbol_name": symbol_name,
        "broker_position_id": f"IB:{ACCOUNT_ID}:{symbol_name}",
        "action": "SELL",
        "order_type": order_type,
        "total_quantity": 1000.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "oca_group": str(oca_group),
        "oca_type": 3,
        "lmt_price": 0.0,
        "aux_price": 0.0,
    }

    if order_type == "STP":
        row["aux_price"] = price
    else:
        row["lmt_price"] = price

    return row


def _evidence() -> dict:
    return {
        "captured_utc": "2026-08-03T08:10:35+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "broker_position_id": f"IB:{ACCOUNT_ID}:EURUSD",
                "signed_quantity": 1000.0,
                "sec_type": "CASH",
            },
            {
                "broker_position_id": f"IB:{ACCOUNT_ID}:GBPUSD",
                "signed_quantity": 1000.0,
                "sec_type": "CASH",
            },
        ],
        "executions": [
            {
                "order_id": 243,
                "perm_id": 963655516,
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "symbol_name": "EURUSD",
                "side": "BOT",
                "shares": 1000.0,
                "price": 1.15285,
                "time": "20260803 02:38:22 US/Eastern",
            },
            {
                "order_id": 246,
                "perm_id": 963655532,
                "account": ACCOUNT_ID,
                "symbol": "GBP",
                "currency": "USD",
                "symbol_name": "GBPUSD",
                "side": "BOT",
                "shares": 1000.0,
                "price": 1.3463,
                "time": "20260803 04:07:10 US/Eastern",
            },
        ],
        "open_orders": [
            _protective_order(
                symbol_name="EURUSD",
                order_id=245,
                parent_id=243,
                perm_id=963655518,
                oca_group=963655516,
                order_type="STP",
                price=1.145,
            ),
            _protective_order(
                symbol_name="EURUSD",
                order_id=244,
                parent_id=243,
                perm_id=963655517,
                oca_group=963655516,
                order_type="LMT",
                price=1.157,
            ),
            _protective_order(
                symbol_name="GBPUSD",
                order_id=248,
                parent_id=246,
                perm_id=963655534,
                oca_group=963655532,
                order_type="STP",
                price=1.3357,
            ),
            _protective_order(
                symbol_name="GBPUSD",
                order_id=247,
                parent_id=246,
                perm_id=963655533,
                oca_group=963655532,
                order_type="LMT",
                price=1.35225,
            ),
        ],
        "completed_orders": [],
    }


def _build_snapshot(
    repository: RuntimeRepository,
    evidence: dict,
):
    evidence_order_ids = {
        int(row["order_id"])
        for collection_name in ("open_orders", "executions")
        for row in evidence[collection_name]
    }
    seeds = repository.get_open_ib_virtual_position_leg_seeds(
        account_id=ACCOUNT_ID,
        evidence_order_ids=evidence_order_ids,
    )
    legs = build_ib_virtual_position_legs_from_repository_seeds(seeds)
    return reconcile_ib_virtual_position_legs(
        legs=legs,
        evidence_snapshot=evidence,
    )


def main() -> int:
    with TemporaryDirectory(prefix="lge_ib_reused_order_id_sync_") as temp_dir:
        connection = connect_runtime_db(Path(temp_dir) / "demo.db")
        repository = RuntimeRepository(connection)

        old_eur = _persist_leg(
            repository,
            symbol_name="EURUSD",
            parent_order_id=243,
            stop_loss_order_id=245,
            take_profit_order_id=244,
            # Deliberately corrupted by a prior orderId-only sync.
            parent_perm_id=963655516,
            stop_loss_perm_id=963655518,
            take_profit_perm_id=963655517,
            oca_group="1900828147",
            entry_price=1.1515,
            stop_loss=1.15,
            take_profit=1.155,
            opened_utc="20260731 03:59:51 US/Eastern",
            leg_status=IB_LEG_STATUS_CLOSED,
            close_order_id=246,
        )
        _persist_leg(
            repository,
            symbol_name="EURUSD",
            parent_order_id=247,
            stop_loss_order_id=249,
            take_profit_order_id=248,
            parent_perm_id=1900828195,
            stop_loss_perm_id=1900828197,
            take_profit_perm_id=1900828196,
            oca_group="1900828195",
            entry_price=1.15115,
            stop_loss=1.149,
            take_profit=1.155,
            opened_utc="20260731 05:32:47 US/Eastern",
            leg_status=IB_LEG_STATUS_CLOSED,
            close_order_id=250,
        )
        current_eur = _persist_leg(
            repository,
            symbol_name="EURUSD",
            parent_order_id=243,
            stop_loss_order_id=245,
            take_profit_order_id=244,
            parent_perm_id=963655516,
            stop_loss_perm_id=963655518,
            take_profit_perm_id=963655517,
            oca_group="963655516",
            entry_price=1.15285,
            stop_loss=1.145,
            take_profit=1.157,
            opened_utc="20260803 02:38:22 US/Eastern",
            leg_status=IB_LEG_STATUS_OPEN,
        )
        current_gbp = _persist_leg(
            repository,
            symbol_name="GBPUSD",
            parent_order_id=246,
            stop_loss_order_id=248,
            take_profit_order_id=247,
            parent_perm_id=963655532,
            stop_loss_perm_id=963655534,
            take_profit_perm_id=963655533,
            oca_group="963655532",
            entry_price=1.3463,
            stop_loss=1.3357,
            take_profit=1.35225,
            opened_utc="20260803 04:07:10 US/Eastern",
            leg_status=IB_LEG_STATUS_OPEN,
        )
        evidence = _evidence()
        first_snapshot = _build_snapshot(repository, evidence)
        first_reconciled = all(
            status == IB_RECONCILIATION_STATUS_RECONCILED
            for status in first_snapshot.group_statuses.values()
        )
        first_no_unmapped = not first_snapshot.unmapped_protective_order_ids
        repository.sync_reconciled_ib_virtual_position_leg_snapshot(
            snapshot=first_snapshot,
            evidence_snapshot=evidence,
        )
        second_snapshot = _build_snapshot(repository, evidence)
        repeat_reconciled = all(
            status == IB_RECONCILIATION_STATUS_RECONCILED
            for status in second_snapshot.group_statuses.values()
        )

        old_parent_row = connection.execute(
            """
            SELECT perm_id
            FROM ib_virtual_position_leg_orders
            WHERE position_uid = ?
              AND order_role = 'PARENT'
              AND broker_order_id = '243'
            """,
            (old_eur.position_uid,),
        ).fetchone()
        old_close_row = connection.execute(
            """
            SELECT perm_id, is_active
            FROM ib_virtual_position_leg_orders
            WHERE position_uid = ?
              AND order_role = 'CLOSE'
              AND broker_order_id = '246'
            """,
            (old_eur.position_uid,),
        ).fetchone()
        current_eur_orders = repository.get_ib_virtual_position_leg_orders(
            position_uid=current_eur.position_uid,
            active_only=True,
        )
        current_gbp_orders = repository.get_ib_virtual_position_leg_orders(
            position_uid=current_gbp.position_uid,
            active_only=True,
        )
        old_parent_repaired = int(old_parent_row["perm_id"]) == 1900828147
        old_close_not_rebound = (
            old_close_row["perm_id"] is None and int(old_close_row["is_active"]) == 0
        )
        current_eur_active = {
            (row["order_role"], int(row["perm_id"])) for row in current_eur_orders
        } == {
            (IB_LEG_ORDER_ROLE_PARENT, 963655516),
            (IB_LEG_ORDER_ROLE_STOP_LOSS, 963655518),
            (IB_LEG_ORDER_ROLE_TAKE_PROFIT, 963655517),
        }
        current_gbp_active = {
            (row["order_role"], int(row["perm_id"])) for row in current_gbp_orders
        } == {
            (IB_LEG_ORDER_ROLE_PARENT, 963655532),
            (IB_LEG_ORDER_ROLE_STOP_LOSS, 963655534),
            (IB_LEG_ORDER_ROLE_TAKE_PROFIT, 963655533),
        }

        print("RuntimeRepository IB reused orderId sync result")
        print(f"  first_reconciled={first_reconciled}")
        print(f"  first_no_unmapped={first_no_unmapped}")
        print(f"  repeat_reconciled={repeat_reconciled}")
        print(f"  old_parent_repaired={old_parent_repaired}")
        print(f"  old_close_not_rebound={old_close_not_rebound}")
        print(f"  current_eur_active={current_eur_active}")
        print(f"  current_gbp_active={current_gbp_active}")

        if not all(
            (
                first_reconciled,
                first_no_unmapped,
                repeat_reconciled,
                old_parent_repaired,
                old_close_not_rebound,
                current_eur_active,
                current_gbp_active,
            )
        ):
            raise AssertionError("IB reused orderId persistence sync differs")

        connection.close()

    print("RUNTIME_REPOSITORY_IB_REUSED_ORDER_ID_SYNC_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
