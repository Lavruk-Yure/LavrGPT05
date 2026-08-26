# runtime_repository.py
"""
Runtime Repository для persistence layer LGE.

Поточний етап RoadMap82:
- create_trade;
- SQLite-only;
- без Qt;
- без broker API;
- без UI.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from engine.ib_fx_external_exposure import (
    IB_FX_EXECUTION_POLICY_LGE_EXCLUSIVE,
    IB_FX_EXTERNAL_EXPOSURE_CLEARED,
    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
    IB_FX_EXTERNAL_EXPOSURE_STALE,
    IBFxExternalExposure,
)
from engine.ib_virtual_position_leg import (
    IBVirtualPositionLeg,
    IBVirtualPositionLegReconciliationSnapshot,
)
from engine.runtime_constants import (
    IB_LEG_CLOSE_EXECUTION_STATUS_PENDING,
    IB_LEG_ORDER_ROLE_CLOSE,
    IB_LEG_ORDER_ROLE_PARENT,
    IB_LEG_ORDER_ROLE_STOP_LOSS,
    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
    IB_LEG_ORDER_ROLES,
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_LEG_STATUS_PARTIALLY_CLOSED,
    IB_MANUAL_OPEN_EXECUTION_STATUS_PENDING,
    IB_POSITION_QUANTITY_ABS_TOLERANCE,
    IB_PROTECTION_STATUS_NONE,
    IB_PROTECTIVE_ORDER_TYPES,
    IB_RECONCILIATION_STATUS_RECONCILED,
    IB_RECONCILIATION_STATUS_RECONCILED_MANUAL,
    IB_STOP_ORDER_TYPES,
)
from engine.runtime_events import RuntimeEventType


def utc_now_iso() -> str:
    """
    Повернути поточний UTC timestamp без microseconds.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class RuntimeRepository:
    """
    Єдина точка доступу Runtime до persistence layer.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Ініціалізувати repository.
        """
        self._connection = connection
        self._connection.row_factory = sqlite3.Row

    def get_active_ib_fx_external_exposures(
        self,
        *,
        account_id: str | None = None,
    ) -> list[IBFxExternalExposure]:
        """Return persisted active external IB CASH Forex exposures."""
        parameters: list[object] = [
            IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
            IB_FX_EXTERNAL_EXPOSURE_STALE,
        ]
        account_filter = ""

        if account_id is not None:
            account_clean = str(account_id or "").strip()

            if not account_clean:
                return []

            account_filter = " AND account_id = ?"
            parameters.append(account_clean)

        rows = self._connection.execute(
            f"""
            SELECT *
            FROM ib_fx_external_exposures
            WHERE evidence_status IN (?, ?)
              AND ABS(signed_volume) > ?
              {account_filter}
            ORDER BY account_id, symbol, broker_position_id
            """,
            [
                *parameters[:2],
                IB_POSITION_QUANTITY_ABS_TOLERANCE,
                *parameters[2:],
            ],
        ).fetchall()
        return [self._ib_fx_external_exposure_from_row(row) for row in rows]

    @staticmethod
    def _ib_fx_external_exposure_from_row(
        row: sqlite3.Row,
    ) -> IBFxExternalExposure:
        return IBFxExternalExposure(
            broker_position_id=str(row["broker_position_id"] or "").strip(),
            account_id=str(row["account_id"] or "").strip(),
            symbol_name=str(row["symbol"] or "").strip().upper(),
            signed_volume=float(row["signed_volume"] or 0.0),
            evidence_status=str(row["evidence_status"] or "").strip().upper(),
            last_confirmed_utc=str(row["last_confirmed_utc"] or "").strip(),
            last_observed_utc=str(row["last_observed_utc"] or "").strip(),
            updated_utc=str(row["updated_utc"] or "").strip(),
        )

    def create_trade(
        self,
        broker: str,
        account_id: str,
        symbol: str,
        side: str,
        volume: float,
        source: str = "MANUAL",
        comment: str = "",
    ) -> str:
        """
        Створити Trade до відправлення order брокеру.

        Повертає trade_uid.
        """
        trade_uid = str(uuid4())

        self._connection.execute(
            """
            INSERT INTO trades (
                trade_uid,
                broker,
                account_id,
                symbol,
                side,
                volume,
                created_utc,
                source,
                comment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_uid,
                str(broker).strip().upper(),
                str(account_id).strip(),
                str(symbol).strip().upper(),
                str(side).strip().upper(),
                float(volume),
                utc_now_iso(),
                str(source).strip().upper(),
                str(comment or "").strip(),
            ),
        )

        self._connection.commit()

        return trade_uid

    def create_order_plan(
        self,
        trade_uid: str,
        order_type: str,
        side: str,
        volume: float,
        source: str = "MANUAL",
    ) -> str:
        """
        Створити OrderPlan для існуючого Trade.

        Повертає order_plan_uid.
        """
        order_plan_uid = str(uuid4())

        self._connection.execute(
            """
            INSERT INTO order_plans (
                order_plan_uid,
                trade_uid,
                order_type,
                side,
                volume,
                created_utc,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_plan_uid,
                str(trade_uid).strip(),
                str(order_type).strip().upper(),
                str(side).strip().upper(),
                float(volume),
                utc_now_iso(),
                str(source).strip().upper(),
            ),
        )

        self._connection.commit()

        return order_plan_uid

    def create_broker_order(
        self,
        trade_uid: str,
        order_plan_uid: str,
        broker: str,
        broker_order_id: str | None,
        execution_status: str,
        broker_timestamp: str | None = None,
        source: str = "MANUAL",
        broker_comment: str = "",
    ) -> str:
        """
        Створити BrokerOrder після відправлення order брокеру.

        Повертає broker_order_uid.
        """
        broker_order_uid = str(uuid4())

        self._connection.execute(
            """
            INSERT INTO broker_orders (
                broker_order_uid,
                trade_uid,
                order_plan_uid,
                broker,
                broker_order_id,
                execution_status,
                broker_timestamp,
                created_utc,
                source,
                broker_comment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                broker_order_uid,
                str(trade_uid).strip(),
                str(order_plan_uid).strip(),
                str(broker).strip().upper(),
                None if broker_order_id is None else str(broker_order_id).strip(),
                str(execution_status).strip().upper(),
                broker_timestamp,
                utc_now_iso(),
                str(source).strip().upper(),
                str(broker_comment or "").strip(),
            ),
        )

        self._connection.commit()

        return broker_order_uid

    def get_broker_order_by_broker_order_id(
        self,
        broker: str,
        broker_order_id: str | int,
        trade_uid: str | None = None,
    ) -> dict[str, Any] | None:
        """Return latest persisted broker order for one exact identity."""
        broker_clean = str(broker or "").strip().upper()
        order_id_clean = str(broker_order_id or "").strip()

        if not broker_clean or not order_id_clean:
            return None

        parameters: list[object] = [broker_clean, order_id_clean]
        trade_filter = ""

        if trade_uid is not None:
            trade_uid_clean = str(trade_uid or "").strip()

            if not trade_uid_clean:
                return None

            trade_filter = " AND trade_uid = ?"
            parameters.append(trade_uid_clean)

        row = self._connection.execute(
            f"""
            SELECT *
            FROM broker_orders
            WHERE broker = ?
              AND broker_order_id = ?
              {trade_filter}
            ORDER BY id DESC
            LIMIT 1
            """,
            parameters,
        ).fetchone()
        return None if row is None else dict(row)

    def update_broker_order_execution_status(
        self,
        broker_order_uid: str,
        execution_status: str,
        broker_timestamp: str | None = None,
    ) -> None:
        """Update one persisted broker-order execution status."""
        broker_order_uid_clean = str(broker_order_uid or "").strip()

        if not broker_order_uid_clean:
            raise ValueError("Broker order uid is empty")

        self._connection.execute(
            """
            UPDATE broker_orders
            SET execution_status = ?,
                broker_timestamp = COALESCE(?, broker_timestamp)
            WHERE broker_order_uid = ?
            """,
            (
                str(execution_status or "").strip().upper(),
                broker_timestamp,
                broker_order_uid_clean,
            ),
        )
        self._connection.commit()

    def get_position_by_trade_uid(
        self,
        trade_uid: str,
    ) -> dict[str, Any] | None:
        """Return the latest Runtime position for one trade."""
        row = self._connection.execute(
            """
            SELECT *
            FROM positions
            WHERE trade_uid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(trade_uid or "").strip(),),
        ).fetchone()
        return None if row is None else dict(row)

    def create_pending_ib_manual_open(
        self,
        *,
        trade_uid: str,
        order_plan_uid: str,
        broker_order_uid: str,
        broker_order_id: int,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        stop_loss: float | None,
        take_profit: float | None,
        client_id: int | None,
        comment: str,
        execution_status: str = IB_MANUAL_OPEN_EXECUTION_STATUS_PENDING,
        last_error: str = "",
    ) -> None:
        """Persist exact identity for one delayed IB manual Open."""
        now_utc = utc_now_iso()
        self._connection.execute(
            """
            INSERT INTO ib_pending_open_orders (
                trade_uid,
                order_plan_uid,
                broker_order_uid,
                broker_order_id,
                account_id,
                symbol,
                side,
                quantity,
                stop_loss_order_id,
                take_profit_order_id,
                stop_loss,
                take_profit,
                client_id,
                comment,
                execution_status,
                last_error,
                recovery_attempts,
                is_active,
                created_utc,
                updated_utc,
                resolved_utc
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1,
                ?, ?, NULL
            )
            ON CONFLICT(trade_uid) DO UPDATE SET
                order_plan_uid = excluded.order_plan_uid,
                broker_order_uid = excluded.broker_order_uid,
                broker_order_id = excluded.broker_order_id,
                account_id = excluded.account_id,
                symbol = excluded.symbol,
                side = excluded.side,
                quantity = excluded.quantity,
                stop_loss_order_id = excluded.stop_loss_order_id,
                take_profit_order_id = excluded.take_profit_order_id,
                stop_loss = excluded.stop_loss,
                take_profit = excluded.take_profit,
                client_id = excluded.client_id,
                comment = excluded.comment,
                execution_status = excluded.execution_status,
                last_error = excluded.last_error,
                is_active = 1,
                updated_utc = excluded.updated_utc,
                resolved_utc = NULL
            """,
            (
                str(trade_uid or "").strip(),
                str(order_plan_uid or "").strip(),
                str(broker_order_uid or "").strip(),
                str(int(broker_order_id)),
                str(account_id or "").strip(),
                str(symbol or "").strip().upper(),
                str(side or "").strip().upper(),
                abs(float(quantity)),
                None if stop_loss_order_id is None else str(int(stop_loss_order_id)),
                (
                    None
                    if take_profit_order_id is None
                    else str(int(take_profit_order_id))
                ),
                stop_loss,
                take_profit,
                client_id,
                str(comment or "").strip(),
                str(execution_status or "").strip().upper(),
                str(last_error or "").strip(),
                now_utc,
                now_utc,
            ),
        )
        self._connection.commit()

    def get_pending_ib_manual_opens(self) -> list[dict[str, Any]]:
        """Return delayed IB manual Opens awaiting exact recovery."""
        rows = self._connection.execute(
            """
            SELECT pending.*, broker_orders.execution_status
                AS broker_execution_status
            FROM ib_pending_open_orders pending
            INNER JOIN broker_orders
                ON broker_orders.broker_order_uid = pending.broker_order_uid
            WHERE pending.is_active = 1
            ORDER BY pending.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def update_pending_ib_manual_open_attempt(
        self,
        trade_uid: str,
        last_error: str,
    ) -> None:
        """Increment delayed Open recovery attempts and save last error."""
        self._connection.execute(
            """
            UPDATE ib_pending_open_orders
            SET recovery_attempts = recovery_attempts + 1,
                last_error = ?,
                updated_utc = ?
            WHERE trade_uid = ?
              AND is_active = 1
            """,
            (
                str(last_error or "").strip(),
                utc_now_iso(),
                str(trade_uid or "").strip(),
            ),
        )
        self._connection.commit()

    def resolve_pending_ib_manual_open(
        self,
        trade_uid: str,
        execution_status: str = "FILLED",
    ) -> None:
        """Mark one delayed IB manual Open as recovered."""
        now_utc = utc_now_iso()
        self._connection.execute(
            """
            UPDATE ib_pending_open_orders
            SET execution_status = ?,
                is_active = 0,
                updated_utc = ?,
                resolved_utc = ?
            WHERE trade_uid = ?
            """,
            (
                str(execution_status or "").strip().upper(),
                now_utc,
                now_utc,
                str(trade_uid or "").strip(),
            ),
        )
        self._connection.commit()

    def get_orphan_ib_manual_market_order_plans(
        self,
    ) -> list[dict[str, Any]]:
        """Return legacy IB manual Opens left before BrokerOrder persistence."""
        rows = self._connection.execute(
            """
            SELECT
                trades.trade_uid,
                trades.account_id,
                trades.symbol,
                trades.side,
                trades.volume,
                trades.created_utc,
                trades.source,
                order_plans.order_plan_uid
            FROM trades
            INNER JOIN order_plans
                ON order_plans.trade_uid = trades.trade_uid
            WHERE trades.broker = 'IB'
              AND order_plans.order_type = 'MARKET'
              AND NOT EXISTS (
                  SELECT 1
                  FROM broker_orders
                  WHERE broker_orders.trade_uid = trades.trade_uid
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM positions
                  WHERE positions.trade_uid = trades.trade_uid
              )
            ORDER BY trades.id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_known_ib_broker_order_ids(self) -> set[int]:
        """Return positive IB broker order IDs already owned by Runtime."""
        rows = self._connection.execute(
            """
            SELECT broker_order_id
            FROM broker_orders
            WHERE broker = 'IB'
              AND broker_order_id IS NOT NULL
            """
        ).fetchall()
        result: set[int] = set()

        for row in rows:
            try:
                value = int(row["broker_order_id"])
            except (TypeError, ValueError):
                continue

            if value > 0:
                result.add(value)

        return result

    def create_position(
        self,
        trade_uid: str,
        broker_order_uid: str,
        broker: str,
        broker_position_id: str | None,
        symbol: str,
        side: str,
        volume: float,
        open_price: float | None,
        opened_utc: str | None,
        state: str = "OPEN",
        source: str = "BROKER",
    ) -> str:
        """
        Створити Runtime Position після виконання BrokerOrder.

        Повертає position_uid.
        """
        position_uid = str(uuid4())

        self._connection.execute(
            """
            INSERT INTO positions (
                position_uid,
                trade_uid,
                broker_order_uid,
                broker,
                broker_position_id,
                symbol,
                side,
                volume,
                open_price,
                opened_utc,
                state,
                created_utc,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position_uid,
                str(trade_uid).strip(),
                str(broker_order_uid).strip(),
                str(broker).strip().upper(),
                None if broker_position_id is None else str(broker_position_id).strip(),
                str(symbol).strip().upper(),
                str(side).strip().upper(),
                float(volume),
                open_price,
                opened_utc,
                str(state).strip().upper(),
                utc_now_iso(),
                str(source).strip().upper(),
            ),
        )

        self._connection.commit()

        return position_uid

    def get_trade_chain(
        self,
        trade_uid: str,
    ) -> dict:
        """
        Прочитати повний Runtime chain для Trade.

        Trade -> OrderPlan -> BrokerOrder -> Position
        """
        trade_uid_clean = str(trade_uid).strip()

        trade = self._connection.execute(
            """
            SELECT *
            FROM trades
            WHERE trade_uid = ?
            """,
            (trade_uid_clean,),
        ).fetchone()

        order_plans = self._connection.execute(
            """
            SELECT *
            FROM order_plans
            WHERE trade_uid = ?
            ORDER BY id
            """,
            (trade_uid_clean,),
        ).fetchall()

        broker_orders = self._connection.execute(
            """
            SELECT *
            FROM broker_orders
            WHERE trade_uid = ?
            ORDER BY id
            """,
            (trade_uid_clean,),
        ).fetchall()

        positions = self._connection.execute(
            """
            SELECT *
            FROM positions
            WHERE trade_uid = ?
            ORDER BY id
            """,
            (trade_uid_clean,),
        ).fetchall()

        return {
            "trade": dict(trade) if trade is not None else None,
            "order_plans": [dict(row) for row in order_plans],
            "broker_orders": [dict(row) for row in broker_orders],
            "positions": [dict(row) for row in positions],
        }

    def get_latest_trade_uid(self) -> str | None:
        """
        Повернути trade_uid останнього Trade.
        """
        row = self._connection.execute(
            """
            SELECT trade_uid
            FROM trades
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return None

        return str(row["trade_uid"])

    def get_open_position_by_broker_position_id(
        self,
        broker: str,
        broker_position_id: str,
    ) -> dict | None:
        """
        Знайти OPEN Runtime Position за broker_position_id.
        """
        row = self._connection.execute(
            """
            SELECT *
            FROM positions
            WHERE broker = ?
              AND broker_position_id = ?
              AND state = 'OPEN'
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                str(broker).strip().upper(),
                str(broker_position_id).strip(),
            ),
        ).fetchone()

        if row is None:
            return None

        return dict(row)

    def get_ib_virtual_position_leg_order_identity(
        self,
        position_uid: str,
    ) -> dict[str, str] | None:
        """Return persisted comment identity for one IB virtual leg."""
        position_uid_clean = str(position_uid or "").strip()

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        row = self._connection.execute(
            """
            SELECT
                trades.source AS trade_source,
                trades.comment AS trade_comment,
                broker_orders.broker_comment AS broker_comment,
                COALESCE((
                    SELECT parent_orders.order_ref
                    FROM ib_virtual_position_leg_orders parent_orders
                    WHERE parent_orders.position_uid = positions.position_uid
                      AND parent_orders.order_role = 'PARENT'
                    ORDER BY parent_orders.id DESC
                    LIMIT 1
                ), '') AS parent_order_ref
            FROM positions
            INNER JOIN trades
                ON trades.trade_uid = positions.trade_uid
            INNER JOIN broker_orders
                ON broker_orders.broker_order_uid = positions.broker_order_uid
            WHERE positions.position_uid = ?
              AND positions.broker = 'IB'
            LIMIT 1
            """,
            (position_uid_clean,),
        ).fetchone()

        if row is None:
            return None

        return {
            "trade_source": str(row["trade_source"] or "").strip(),
            "trade_comment": str(row["trade_comment"] or "").strip(),
            "broker_comment": str(row["broker_comment"] or "").strip(),
            "parent_order_ref": str(row["parent_order_ref"] or "").strip(),
        }

    def get_open_ib_virtual_position_leg_seeds(
        self,
        account_id: str | None = None,
        evidence_order_ids: set[int] | None = None,
        evidence_order_perm_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Прочитати read-only seeds для IB virtual-leg reconciliation.

        Без evidence order identity повертаються тільки OPEN legs. Поточна
        IB execution/completed history може додатково підтягнути persisted
        CLOSED legs, потрібні для cumulative CASH Virtual FX arithmetic.
        permId використовується як стабільний fallback, коли IB повертає
        historical/cross-session orderId=0.
        Логічні side/volume завжди беруться з Trade.
        """
        account_id_clean = str(account_id or "").strip()
        parameters: list[object] = []
        account_filter = ""
        evidence_filter = ""
        evidence_perm_filter = ""

        if account_id_clean:
            account_filter = "AND trades.account_id = ?"
            parameters.append(account_id_clean)

        normalized_evidence_ids = sorted(
            {int(value) for value in (evidence_order_ids or set()) if int(value) > 0}
        )

        if normalized_evidence_ids:
            placeholders = ", ".join("?" for _value in normalized_evidence_ids)
            evidence_filter = f"""
                  OR ib_virtual_position_legs.parent_order_id
                      IN ({placeholders})
                  OR ib_virtual_position_legs.stop_loss_order_id
                      IN ({placeholders})
                  OR ib_virtual_position_legs.take_profit_order_id
                      IN ({placeholders})
                  OR EXISTS (
                      SELECT 1
                      FROM ib_virtual_position_leg_orders close_orders
                      WHERE close_orders.position_uid = positions.position_uid
                        AND close_orders.order_role = 'CLOSE'
                        AND close_orders.broker_order_id IN ({placeholders})
                  )
            """
            order_id_values = [str(value) for value in normalized_evidence_ids]
            parameters.extend(order_id_values)
            parameters.extend(order_id_values)
            parameters.extend(order_id_values)
            parameters.extend(order_id_values)

        normalized_evidence_perm_ids = sorted(
            {
                int(value)
                for value in (evidence_order_perm_ids or set())
                if int(value) > 0
            }
        )

        if normalized_evidence_perm_ids:
            placeholders = ", ".join("?" for _value in normalized_evidence_perm_ids)
            evidence_perm_filter = f"""
                  OR EXISTS (
                      SELECT 1
                      FROM ib_virtual_position_leg_orders evidence_orders
                      WHERE evidence_orders.position_uid = positions.position_uid
                        AND evidence_orders.perm_id IN ({placeholders})
                  )
            """
            parameters.extend(str(value) for value in normalized_evidence_perm_ids)

        rows = self._connection.execute(
            f"""
            SELECT
                positions.id AS position_row_id,
                positions.position_uid,
                positions.trade_uid,
                positions.broker_position_id,
                trades.account_id,
                trades.symbol AS symbol_name,
                trades.side AS logical_side,
                trades.volume AS logical_volume,
                trades.created_utc AS trade_created_utc,
                trades.source AS trade_source,
                broker_orders.broker_order_id AS parent_order_id,
                broker_orders.execution_status
                    AS parent_execution_status,
                broker_orders.broker_timestamp
                    AS parent_broker_timestamp,
                positions.side AS broker_snapshot_side,
                positions.volume AS broker_snapshot_volume,
                positions.open_price AS broker_snapshot_open_price,
                positions.opened_utc AS broker_snapshot_opened_utc,
                positions.created_utc AS runtime_position_created_utc,
                positions.source AS runtime_position_source,
                ib_virtual_position_legs.entry_price
                    AS persisted_entry_price,
                ib_virtual_position_legs.opened_utc
                    AS persisted_opened_utc,
                ib_virtual_position_legs.parent_order_id
                    AS persisted_parent_order_id,
                (
                    SELECT parent_orders.perm_id
                    FROM ib_virtual_position_leg_orders parent_orders
                    WHERE parent_orders.position_uid = positions.position_uid
                      AND parent_orders.order_role = 'PARENT'
                      AND parent_orders.broker_order_id
                          = ib_virtual_position_legs.parent_order_id
                    ORDER BY parent_orders.id DESC
                    LIMIT 1
                ) AS persisted_parent_perm_id,
                ib_virtual_position_legs.stop_loss_order_id
                    AS persisted_stop_loss_order_id,
                (
                    SELECT stop_orders.perm_id
                    FROM ib_virtual_position_leg_orders stop_orders
                    WHERE stop_orders.position_uid = positions.position_uid
                      AND stop_orders.order_role = 'STOP_LOSS'
                      AND stop_orders.broker_order_id
                          = ib_virtual_position_legs.stop_loss_order_id
                    ORDER BY stop_orders.id DESC
                    LIMIT 1
                ) AS persisted_stop_loss_perm_id,
                ib_virtual_position_legs.take_profit_order_id
                    AS persisted_take_profit_order_id,
                (
                    SELECT take_orders.perm_id
                    FROM ib_virtual_position_leg_orders take_orders
                    WHERE take_orders.position_uid = positions.position_uid
                      AND take_orders.order_role = 'TAKE_PROFIT'
                      AND take_orders.broker_order_id
                          = ib_virtual_position_legs.take_profit_order_id
                    ORDER BY take_orders.id DESC
                    LIMIT 1
                ) AS persisted_take_profit_perm_id,
                ib_virtual_position_legs.stop_loss
                    AS persisted_stop_loss,
                ib_virtual_position_legs.take_profit
                    AS persisted_take_profit,
                ib_virtual_position_legs.oca_group
                    AS persisted_oca_group,
                (
                    SELECT GROUP_CONCAT(close_orders.broker_order_id)
                    FROM ib_virtual_position_leg_orders close_orders
                    WHERE close_orders.position_uid = positions.position_uid
                      AND close_orders.order_role = 'CLOSE'
                ) AS persisted_close_order_ids,
                ib_virtual_position_legs.leg_status
                    AS persisted_leg_status,
                ib_virtual_position_legs.protection_status
                    AS persisted_protection_status,
                ib_virtual_position_legs.reconciliation_status
                    AS persisted_reconciliation_status,
                ib_virtual_position_legs.reconciliation_messages_json
                    AS persisted_reconciliation_messages_json
            FROM positions
            INNER JOIN trades
                ON trades.trade_uid = positions.trade_uid
            INNER JOIN broker_orders
                ON broker_orders.broker_order_uid
                    = positions.broker_order_uid
            INNER JOIN order_plans
                ON order_plans.order_plan_uid
                    = broker_orders.order_plan_uid
            LEFT JOIN ib_virtual_position_legs
                ON ib_virtual_position_legs.position_uid
                    = positions.position_uid
            WHERE positions.broker = 'IB'
              AND trades.broker = 'IB'
              AND broker_orders.broker = 'IB'
              AND positions.state = 'OPEN'
              AND order_plans.order_type = 'MARKET'
              {account_filter}
              AND (
                  ib_virtual_position_legs.leg_status IS NULL
                  OR ib_virtual_position_legs.leg_status != 'CLOSED'
                  {evidence_filter}
                  {evidence_perm_filter}
              )
            ORDER BY positions.id
            """,
            parameters,
        ).fetchall()

        return [dict(row) for row in rows]

    def upsert_ib_virtual_position_leg(
        self,
        leg: IBVirtualPositionLeg,
        remaining_volume: float | None = None,
        closed_utc: str | None = None,
    ) -> None:
        """
        Створити або оновити поточний persistence state IB virtual leg.

        Trade зберігає початковий volume. У leg table окремо фіксуються
        initial_volume та remaining_volume для майбутнього partial close.
        """
        position_uid = str(leg.position_uid or "").strip()
        trade_uid = str(leg.trade_uid or "").strip()

        if not position_uid or not trade_uid:
            raise ValueError("IB virtual leg identity is incomplete")

        initial_volume = abs(float(leg.volume))

        if remaining_volume is None:
            remaining = initial_volume

            if leg.leg_status == IB_LEG_STATUS_CLOSED:
                remaining = 0.0
        else:
            remaining = abs(float(remaining_volume))

        if remaining > initial_volume:
            raise ValueError("IB virtual leg remaining volume exceeds initial volume")

        now_utc = utc_now_iso()
        messages_json = json.dumps(
            list(leg.reconciliation_messages),
            ensure_ascii=False,
        )

        self._connection.execute(
            """
            INSERT INTO ib_virtual_position_legs (
                position_uid,
                trade_uid,
                broker_position_id,
                account_id,
                symbol,
                side,
                initial_volume,
                remaining_volume,
                entry_price,
                opened_utc,
                source,
                parent_order_id,
                stop_loss_order_id,
                take_profit_order_id,
                stop_loss,
                take_profit,
                oca_group,
                leg_status,
                protection_status,
                reconciliation_status,
                reconciliation_messages_json,
                closed_utc,
                created_utc,
                updated_utc
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(position_uid) DO UPDATE SET
                trade_uid = excluded.trade_uid,
                broker_position_id = excluded.broker_position_id,
                account_id = excluded.account_id,
                symbol = excluded.symbol,
                side = excluded.side,
                remaining_volume = excluded.remaining_volume,
                entry_price = excluded.entry_price,
                opened_utc = excluded.opened_utc,
                source = excluded.source,
                parent_order_id = excluded.parent_order_id,
                stop_loss_order_id = excluded.stop_loss_order_id,
                take_profit_order_id = excluded.take_profit_order_id,
                stop_loss = excluded.stop_loss,
                take_profit = excluded.take_profit,
                oca_group = excluded.oca_group,
                leg_status = excluded.leg_status,
                protection_status = excluded.protection_status,
                reconciliation_status = excluded.reconciliation_status,
                reconciliation_messages_json =
                    excluded.reconciliation_messages_json,
                closed_utc = excluded.closed_utc,
                updated_utc = excluded.updated_utc
            """,
            (
                position_uid,
                trade_uid,
                str(leg.broker_position_id or "").strip(),
                str(leg.account_id or "").strip(),
                str(leg.symbol_name or "").strip().upper(),
                str(leg.side or "").strip().upper(),
                initial_volume,
                remaining,
                leg.entry_price,
                str(leg.opened_utc or "").strip() or None,
                str(leg.source or "").strip().upper(),
                self._optional_order_id_text(leg.parent_order_id),
                self._optional_order_id_text(leg.stop_loss_order_id),
                self._optional_order_id_text(leg.take_profit_order_id),
                leg.stop_loss,
                leg.take_profit,
                str(leg.oca_group or "").strip(),
                str(leg.leg_status or "").strip().upper(),
                str(leg.protection_status or "").strip().upper(),
                str(leg.reconciliation_status or "").strip().upper(),
                messages_json,
                str(closed_utc or "").strip() or None,
                now_utc,
                now_utc,
            ),
        )
        self._connection.commit()

    def set_active_ib_virtual_position_leg_order(
        self,
        position_uid: str,
        order_role: str,
        broker_order_id: int | str,
        execution_status: str,
        parent_order_id: int | str | None = None,
        perm_id: int | str | None = None,
        client_id: int | None = None,
        action: str | None = None,
        order_type: str | None = None,
        quantity: float | None = None,
        price: float | None = None,
        oca_group: str = "",
        oca_type: int | None = None,
        order_ref: str = "",
    ) -> None:
        """
        Зберегти active broker order mapping для однієї leg role.

        Попередній active order цієї role лишається в history як inactive.
        """
        position_uid_clean = str(position_uid or "").strip()
        role = str(order_role or "").strip().upper()
        order_id_text = self._optional_order_id_text(broker_order_id)

        if not position_uid_clean or order_id_text is None:
            raise ValueError("IB virtual leg order identity is incomplete")

        if role not in IB_LEG_ORDER_ROLES:
            raise ValueError(f"Unsupported IB virtual leg order role: {role}")

        now_utc = utc_now_iso()

        try:
            self._connection.execute(
                """
                UPDATE ib_virtual_position_leg_orders
                SET is_active = 0,
                    updated_utc = ?
                WHERE position_uid = ?
                  AND order_role = ?
                  AND broker_order_id != ?
                  AND is_active = 1
                """,
                (
                    now_utc,
                    position_uid_clean,
                    role,
                    order_id_text,
                ),
            )

            self._connection.execute(
                """
                INSERT INTO ib_virtual_position_leg_orders (
                    position_uid,
                    order_role,
                    broker_order_id,
                    parent_order_id,
                    perm_id,
                    client_id,
                    action,
                    order_type,
                    quantity,
                    price,
                    oca_group,
                    oca_type,
                    order_ref,
                    execution_status,
                    is_active,
                    created_utc,
                    updated_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(position_uid, broker_order_id) DO UPDATE SET
                    order_role = excluded.order_role,
                    parent_order_id = excluded.parent_order_id,
                    perm_id = excluded.perm_id,
                    client_id = excluded.client_id,
                    action = excluded.action,
                    order_type = excluded.order_type,
                    quantity = excluded.quantity,
                    price = excluded.price,
                    oca_group = excluded.oca_group,
                    oca_type = excluded.oca_type,
                    order_ref = CASE
                        WHEN excluded.order_ref != '' THEN excluded.order_ref
                        ELSE ib_virtual_position_leg_orders.order_ref
                    END,
                    execution_status = excluded.execution_status,
                    is_active = 1,
                    updated_utc = excluded.updated_utc
                """,
                (
                    position_uid_clean,
                    role,
                    order_id_text,
                    self._optional_order_id_text(parent_order_id),
                    self._optional_order_id_text(perm_id),
                    client_id,
                    self._optional_upper_text(action),
                    self._optional_upper_text(order_type),
                    None if quantity is None else abs(float(quantity)),
                    price,
                    str(oca_group or "").strip(),
                    oca_type,
                    str(order_ref or "").strip(),
                    str(execution_status or "").strip().upper(),
                    now_utc,
                    now_utc,
                ),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def deactivate_ib_virtual_position_leg_order(
        self,
        position_uid: str,
        order_role: str,
        execution_status: str,
    ) -> int:
        """
        Деактивувати поточний broker order mapping вказаної leg role.
        """
        position_uid_clean = str(position_uid or "").strip()
        role = str(order_role or "").strip().upper()

        if role not in IB_LEG_ORDER_ROLES:
            raise ValueError(f"Unsupported IB virtual leg order role: {role}")

        cursor = self._connection.execute(
            """
            UPDATE ib_virtual_position_leg_orders
            SET is_active = 0,
                execution_status = ?,
                updated_utc = ?
            WHERE position_uid = ?
              AND order_role = ?
              AND is_active = 1
            """,
            (
                str(execution_status or "").strip().upper(),
                utc_now_iso(),
                position_uid_clean,
                role,
            ),
        )
        self._connection.commit()
        return int(cursor.rowcount or 0)

    def get_ib_virtual_position_leg(
        self,
        position_uid: str,
    ) -> dict | None:
        """
        Прочитати persistence state однієї IB virtual leg.
        """
        row = self._connection.execute(
            """
            SELECT *
            FROM ib_virtual_position_legs
            WHERE position_uid = ?
            """,
            (str(position_uid or "").strip(),),
        ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result["reconciliation_messages"] = json.loads(
            str(result.pop("reconciliation_messages_json") or "[]")
        )
        return result

    def get_ib_virtual_position_leg_orders(
        self,
        position_uid: str,
        active_only: bool = False,
    ) -> list[dict]:
        """
        Прочитати current або historical broker order mappings leg.
        """
        active_filter = ""

        if active_only:
            active_filter = "AND is_active = 1"

        rows = self._connection.execute(
            f"""
            SELECT *
            FROM ib_virtual_position_leg_orders
            WHERE position_uid = ?
              {active_filter}
            ORDER BY id
            """,
            (str(position_uid or "").strip(),),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_pending_ib_virtual_position_leg_close_orders(
        self,
    ) -> list[dict]:
        """Return active virtual-leg Close mappings awaiting confirmation."""
        rows = self._connection.execute(
            """
            SELECT
                close_orders.*,
                ib_virtual_position_legs.leg_status,
                ib_virtual_position_legs.reconciliation_status
            FROM ib_virtual_position_leg_orders close_orders
            INNER JOIN ib_virtual_position_legs
                ON ib_virtual_position_legs.position_uid
                    = close_orders.position_uid
            WHERE close_orders.order_role = ?
              AND close_orders.is_active = 1
              AND close_orders.execution_status = ?
            ORDER BY close_orders.id
            """,
            (
                IB_LEG_ORDER_ROLE_CLOSE,
                IB_LEG_CLOSE_EXECUTION_STATUS_PENDING,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def persist_confirmed_ib_virtual_position_leg_open(
        self,
        leg: IBVirtualPositionLeg,
        evidence_snapshot: dict[str, Any],
        parent_order_ref: str = "",
    ) -> dict[str, Any]:
        """
        Atomically persist one freshly confirmed LGE-owned IB Open leg.

        The caller must provide a leg built from exact parent execution and
        exact active child-order evidence. Broker Virtual FX quantity is not
        used as an identity source for this operation.
        """
        if leg.leg_status != IB_LEG_STATUS_OPEN:
            raise RuntimeError("Fresh IB virtual-leg persistence requires OPEN leg")

        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise RuntimeError(
                "Fresh IB virtual-leg persistence requires RECONCILED leg"
            )

        for flag_name in (
            "complete",
            "positions_complete",
            "open_orders_complete",
            "completed_orders_complete",
            "executions_complete",
        ):
            flag_value = evidence_snapshot.get(flag_name)

            if not isinstance(flag_value, bool) or not flag_value:
                raise RuntimeError(
                    "Fresh IB virtual-leg evidence is incomplete: " f"{flag_name}"
                )

        if leg.parent_order_id is None:
            raise RuntimeError("Fresh IB virtual-leg parent order id is missing")

        open_orders = list(evidence_snapshot.get("open_orders") or [])
        completed_orders = list(evidence_snapshot.get("completed_orders") or [])
        executions = list(evidence_snapshot.get("executions") or [])
        parent_perm_id = self._ib_effective_parent_perm_id(leg)
        parent_row = self._find_ib_order_evidence_row(
            order_id=leg.parent_order_id,
            perm_id=parent_perm_id,
            open_orders=open_orders,
            completed_orders=completed_orders,
        )
        parent_executions = self._execution_rows_for_order(
            order_id=leg.parent_order_id,
            perm_id=parent_perm_id,
            executions=executions,
        )

        if not parent_executions:
            raise RuntimeError(
                "Fresh IB virtual-leg parent execution evidence is missing"
            )

        child_rows: list[tuple[str, int, int | None, dict[str, Any], float | None]] = []

        for order_role, order_id, order_perm_id, price in (
            (
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                leg.stop_loss_order_id,
                leg.stop_loss_order_perm_id,
                leg.stop_loss,
            ),
            (
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
                leg.take_profit_order_id,
                leg.take_profit_order_perm_id,
                leg.take_profit,
            ),
        ):
            if order_id is None:
                continue

            row = self._find_order_row_by_identity(
                rows=open_orders,
                order_id=order_id,
                perm_id=order_perm_id,
            )

            if row is None:
                raise RuntimeError(
                    "Fresh IB virtual-leg active child evidence is missing"
                )

            child_rows.append((order_role, order_id, order_perm_id, row, price))

        self._connection.execute("SAVEPOINT ib_virtual_leg_fresh_open")

        try:
            self._upsert_ib_virtual_position_leg_no_commit(
                leg=leg,
                remaining_volume=leg.volume,
                closed_utc=None,
            )
            self._upsert_ib_virtual_position_leg_order_no_commit(
                position_uid=leg.position_uid,
                order_role=IB_LEG_ORDER_ROLE_PARENT,
                broker_order_id=leg.parent_order_id,
                evidence_row=parent_row,
                execution_rows=parent_executions,
                default_action=leg.side,
                default_order_type="MKT",
                default_quantity=leg.volume,
                default_price=leg.entry_price,
                default_status="FILLED",
                is_active=True,
                default_order_ref=parent_order_ref,
                default_perm_id=parent_perm_id,
            )
            orders_written = 1

            for order_role, order_id, order_perm_id, row, price in child_rows:
                self._upsert_ib_virtual_position_leg_order_no_commit(
                    position_uid=leg.position_uid,
                    order_role=order_role,
                    broker_order_id=order_id,
                    evidence_row=row,
                    execution_rows=(),
                    default_action=leg.protective_action,
                    default_order_type=(
                        "STP" if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS else "LMT"
                    ),
                    default_quantity=leg.volume,
                    default_price=price,
                    default_status="SUBMITTED",
                    is_active=True,
                    default_order_ref=parent_order_ref,
                    default_perm_id=order_perm_id,
                )
                orders_written += 1

            self._connection.execute("RELEASE ib_virtual_leg_fresh_open")
            self._connection.commit()
        except Exception:
            self._connection.execute("ROLLBACK TO ib_virtual_leg_fresh_open")
            self._connection.execute("RELEASE ib_virtual_leg_fresh_open")
            self._connection.rollback()
            raise

        return {
            "position_uid": leg.position_uid,
            "legs_written": 1,
            "orders_written": orders_written,
            "open_legs": 1,
        }

    def persist_confirmed_ib_virtual_position_leg_modify(
        self,
        leg: IBVirtualPositionLeg,
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist one exact broker-confirmed SL/TP state for an OPEN leg."""
        if leg.leg_status != IB_LEG_STATUS_OPEN:
            raise RuntimeError("Modified IB virtual leg is not OPEN")

        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise RuntimeError("Modified IB virtual leg is not RECONCILED")

        for flag_name in (
            "complete",
            "positions_complete",
            "open_orders_complete",
            "completed_orders_complete",
            "executions_complete",
        ):
            if not bool(evidence_snapshot.get(flag_name)):
                raise RuntimeError(
                    "IB virtual-leg Modify evidence is incomplete: " f"{flag_name}"
                )

        if leg.parent_order_id is None:
            raise RuntimeError("Modified IB virtual leg parent order id is missing")

        open_orders = list(evidence_snapshot.get("open_orders") or [])
        completed_orders = list(evidence_snapshot.get("completed_orders") or [])
        executions = list(evidence_snapshot.get("executions") or [])
        current_client_id = self._optional_int_value(
            evidence_snapshot.get("current_client_id")
        )
        child_rows: dict[str, tuple[int, int | None, dict[str, Any], float | None]] = {}

        for order_role, order_id, order_perm_id, price in (
            (
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                leg.stop_loss_order_id,
                leg.stop_loss_order_perm_id,
                leg.stop_loss,
            ),
            (
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
                leg.take_profit_order_id,
                leg.take_profit_order_perm_id,
                leg.take_profit,
            ),
        ):
            if order_id is None:
                continue

            row = self._find_order_row_by_identity(
                open_orders,
                order_id,
                order_perm_id,
            )

            if row is None:
                raise RuntimeError(
                    "Modified IB virtual-leg active child evidence is missing"
                )

            if not self._ib_protective_order_belongs_to_leg(
                row=row,
                leg=leg,
                current_client_id=current_client_id,
                allow_zero_quantity=False,
            ):
                raise RuntimeError(
                    "Modified IB virtual-leg active child evidence differs"
                )

            child_rows[order_role] = (
                order_id,
                order_perm_id,
                row,
                price,
            )

        parent_perm_id = self._ib_effective_parent_perm_id(leg)
        parent_row = self._find_ib_order_evidence_row(
            order_id=leg.parent_order_id,
            perm_id=parent_perm_id,
            open_orders=open_orders,
            completed_orders=completed_orders,
        )
        parent_executions = self._execution_rows_for_order(
            order_id=leg.parent_order_id,
            perm_id=parent_perm_id,
            executions=executions,
        )
        self._connection.execute("SAVEPOINT ib_virtual_leg_modify")

        try:
            self._upsert_ib_virtual_position_leg_no_commit(
                leg=leg,
                remaining_volume=leg.volume,
                closed_utc=None,
            )
            self._upsert_ib_virtual_position_leg_order_no_commit(
                position_uid=leg.position_uid,
                order_role=IB_LEG_ORDER_ROLE_PARENT,
                broker_order_id=leg.parent_order_id,
                evidence_row=parent_row,
                execution_rows=parent_executions,
                default_action=leg.side,
                default_order_type="MKT",
                default_quantity=leg.volume,
                default_price=leg.entry_price,
                default_status="FILLED",
                is_active=True,
                default_perm_id=parent_perm_id,
            )
            orders_written = 1

            for order_role in (
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            ):
                child = child_rows.get(order_role)

                if child is None:
                    self._deactivate_ib_virtual_position_leg_order_no_commit(
                        position_uid=leg.position_uid,
                        order_role=order_role,
                        execution_status="CANCELLED_AFTER_MODIFY",
                    )
                    continue

                order_id, order_perm_id, row, price = child
                self._upsert_ib_virtual_position_leg_order_no_commit(
                    position_uid=leg.position_uid,
                    order_role=order_role,
                    broker_order_id=order_id,
                    evidence_row=row,
                    execution_rows=(),
                    default_action=leg.protective_action,
                    default_order_type=(
                        "STP" if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS else "LMT"
                    ),
                    default_quantity=leg.volume,
                    default_price=price,
                    default_status="SUBMITTED",
                    is_active=True,
                    default_perm_id=order_perm_id,
                )
                orders_written += 1

            self._connection.execute("RELEASE ib_virtual_leg_modify")
            self._connection.commit()
        except Exception:
            self._connection.execute("ROLLBACK TO ib_virtual_leg_modify")
            self._connection.execute("RELEASE ib_virtual_leg_modify")
            self._connection.rollback()
            raise

        return {
            "position_uid": leg.position_uid,
            "legs_written": 1,
            "orders_written": orders_written,
            "open_legs": 1,
        }

    def bootstrap_confirmed_ib_virtual_position_leg_snapshot(
        self,
        legs: list[IBVirtualPositionLeg],
        order_mappings: list[dict[str, Any]],
        closed_utc_by_position_uid: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """
        Atomically persist one externally confirmed historical snapshot.

        This method does not infer broker ownership. The caller must supply
        exact leg identities and exact parent/child order mappings that were
        already confirmed by a previous complete live reconciliation. Legacy
        Trade -> BrokerOrder -> Position identities are verified before any
        write. Existing identical bootstrap data is treated as an idempotent
        no-op; conflicting data is rejected.
        """
        closed_utc_map = dict(closed_utc_by_position_uid or {})
        self._validate_confirmed_ib_virtual_leg_bootstrap(
            legs=legs,
            order_mappings=order_mappings,
        )

        if self._confirmed_ib_virtual_leg_bootstrap_already_applied(
            legs=legs,
            order_mappings=order_mappings,
            closed_utc_by_position_uid=closed_utc_map,
        ):
            return {
                "already_applied": True,
                "legs_written": 0,
                "orders_written": 0,
            }

        self._connection.execute("SAVEPOINT ib_virtual_leg_bootstrap")

        try:
            for leg in legs:
                self._upsert_ib_virtual_position_leg_no_commit(
                    leg=leg,
                    remaining_volume=(
                        0.0
                        if leg.leg_status == IB_LEG_STATUS_CLOSED
                        else abs(float(leg.volume))
                    ),
                    closed_utc=closed_utc_map.get(leg.position_uid),
                )

            for mapping in order_mappings:
                row = dict(mapping)
                self._upsert_ib_virtual_position_leg_order_no_commit(
                    position_uid=str(row.get("position_uid") or "").strip(),
                    order_role=str(row.get("order_role") or "").strip().upper(),
                    broker_order_id=row.get("broker_order_id"),
                    evidence_row=row,
                    execution_rows=(),
                    default_action=str(row.get("action") or ""),
                    default_order_type=str(row.get("order_type") or ""),
                    default_quantity=self._safe_float_value(row.get("quantity")),
                    default_price=(
                        None
                        if row.get("price") is None
                        else self._safe_float_value(row.get("price"))
                    ),
                    default_status=str(row.get("execution_status") or ""),
                    is_active=bool(row.get("is_active")),
                )

            self._connection.execute("RELEASE ib_virtual_leg_bootstrap")
            self._connection.commit()
        except Exception:
            self._connection.execute("ROLLBACK TO ib_virtual_leg_bootstrap")
            self._connection.execute("RELEASE ib_virtual_leg_bootstrap")
            self._connection.rollback()
            raise

        return {
            "already_applied": False,
            "legs_written": len(legs),
            "orders_written": len(order_mappings),
        }

    def _validate_confirmed_ib_virtual_leg_bootstrap(
        self,
        legs: list[IBVirtualPositionLeg],
        order_mappings: list[dict[str, Any]],
    ) -> None:
        if not legs:
            raise ValueError("Confirmed IB virtual-leg bootstrap is empty")

        position_uids = [str(leg.position_uid).strip() for leg in legs]
        trade_uids = [str(leg.trade_uid).strip() for leg in legs]

        if len(position_uids) != len(set(position_uids)):
            raise ValueError("Duplicate position_uid in confirmed bootstrap")

        if len(trade_uids) != len(set(trade_uids)):
            raise ValueError("Duplicate trade_uid in confirmed bootstrap")

        leg_by_uid = {leg.position_uid: leg for leg in legs}
        parent_roles: set[str] = set()
        active_protective_roles: set[tuple[str, str]] = set()
        order_ids: set[str] = set()

        for leg in legs:
            if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
                raise ValueError("Confirmed bootstrap contains unreconciled leg")

            if leg.leg_status not in {
                IB_LEG_STATUS_OPEN,
                IB_LEG_STATUS_CLOSED,
            }:
                raise ValueError(
                    "Confirmed bootstrap supports OPEN or CLOSED legs only"
                )

            self._validate_confirmed_ib_virtual_leg_legacy_identity(leg)

        for mapping in order_mappings:
            position_uid = str(mapping.get("position_uid") or "").strip()
            role = str(mapping.get("order_role") or "").strip().upper()
            order_id = self._optional_order_id_text(mapping.get("broker_order_id"))

            if position_uid not in leg_by_uid:
                raise ValueError("Confirmed order mapping references unknown leg")

            if role not in IB_LEG_ORDER_ROLES or order_id is None:
                raise ValueError("Confirmed order mapping identity is incomplete")

            if order_id in order_ids:
                raise ValueError("Broker order id is mapped to multiple confirmed legs")

            order_ids.add(order_id)

            if role == IB_LEG_ORDER_ROLE_PARENT:
                parent_roles.add(position_uid)

            if bool(mapping.get("is_active")) and role in {
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            }:
                active_protective_roles.add((position_uid, role))

        if parent_roles != set(position_uids):
            raise ValueError("Every confirmed leg requires one parent order mapping")

        for leg in legs:
            active_roles = {
                role
                for position_uid, role in active_protective_roles
                if position_uid == leg.position_uid
            }

            if leg.leg_status == IB_LEG_STATUS_CLOSED and active_roles:
                raise ValueError("Closed confirmed leg has active protective mapping")

            if leg.leg_status == IB_LEG_STATUS_OPEN and active_roles != {
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            }:
                raise ValueError(
                    "Open confirmed leg requires active SL and TP mappings"
                )

        existing_leg_count = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM ib_virtual_position_legs"
            ).fetchone()[0]
        )

        if existing_leg_count not in {0, len(legs)}:
            raise RuntimeError(
                "Confirmed bootstrap cannot merge with unrelated leg data"
            )

    def _validate_confirmed_ib_virtual_leg_legacy_identity(
        self,
        leg: IBVirtualPositionLeg,
    ) -> None:
        row = self._connection.execute(
            """
            SELECT
                positions.position_uid,
                positions.trade_uid,
                positions.broker_position_id,
                positions.broker,
                trades.account_id,
                trades.symbol,
                trades.side,
                trades.volume,
                trades.source,
                broker_orders.broker_order_id
            FROM positions
            JOIN trades
                ON trades.trade_uid = positions.trade_uid
            JOIN broker_orders
                ON broker_orders.broker_order_uid
                    = positions.broker_order_uid
            WHERE positions.position_uid = ?
            """,
            (str(leg.position_uid or "").strip(),),
        ).fetchone()

        if row is None:
            raise RuntimeError("Confirmed virtual leg has no legacy position identity")

        expected = {
            "trade_uid": str(leg.trade_uid or "").strip(),
            "broker_position_id": str(leg.broker_position_id or "").strip(),
            "broker": "IB",
            "account_id": str(leg.account_id or "").strip(),
            "symbol": str(leg.symbol_name or "").strip().upper(),
            "side": str(leg.side or "").strip().upper(),
            "source": str(leg.source or "").strip().upper(),
            "broker_order_id": self._optional_order_id_text(leg.parent_order_id),
        }

        for key, value in expected.items():
            actual = str(row[key] or "").strip()

            if actual.upper() != str(value or "").strip().upper():
                raise RuntimeError(
                    "Confirmed virtual-leg legacy identity differs: "
                    f"position_uid={leg.position_uid}, field={key}"
                )

        if not self._float_values_equal(row["volume"], leg.volume):
            raise RuntimeError("Confirmed virtual-leg legacy volume differs")

    def _confirmed_ib_virtual_leg_bootstrap_already_applied(
        self,
        legs: list[IBVirtualPositionLeg],
        order_mappings: list[dict[str, Any]],
        closed_utc_by_position_uid: dict[str, str | None],
    ) -> bool:
        rows = self._connection.execute(
            "SELECT * FROM ib_virtual_position_legs ORDER BY position_uid"
        ).fetchall()

        if not rows:
            return False

        if len(rows) != len(legs):
            raise RuntimeError("Existing confirmed bootstrap leg count differs")

        rows_by_uid = {str(row["position_uid"]): row for row in rows}

        for leg in legs:
            row = rows_by_uid.get(leg.position_uid)

            if row is None:
                raise RuntimeError("Existing confirmed bootstrap position_uid differs")

            expected_values = {
                "trade_uid": leg.trade_uid,
                "broker_position_id": leg.broker_position_id,
                "account_id": leg.account_id,
                "symbol": leg.symbol_name,
                "side": leg.side,
                "source": leg.source,
                "opened_utc": leg.opened_utc,
                "parent_order_id": self._optional_order_id_text(leg.parent_order_id),
                "stop_loss_order_id": self._optional_order_id_text(
                    leg.stop_loss_order_id
                ),
                "take_profit_order_id": self._optional_order_id_text(
                    leg.take_profit_order_id
                ),
                "oca_group": leg.oca_group,
                "leg_status": leg.leg_status,
                "protection_status": leg.protection_status,
                "reconciliation_status": leg.reconciliation_status,
                "closed_utc": closed_utc_by_position_uid.get(leg.position_uid),
            }

            for key, value in expected_values.items():
                if (
                    str(row[key] or "").strip().upper()
                    != str(value or "").strip().upper()
                ):
                    raise RuntimeError(
                        "Existing confirmed bootstrap leg data differs: "
                        f"position_uid={leg.position_uid}, field={key}"
                    )

            numeric_values = {
                "initial_volume": leg.volume,
                "remaining_volume": (
                    0.0 if leg.leg_status == IB_LEG_STATUS_CLOSED else leg.volume
                ),
                "entry_price": leg.entry_price,
                "stop_loss": leg.stop_loss,
                "take_profit": leg.take_profit,
            }

            for key, value in numeric_values.items():
                if not self._float_values_equal(row[key], value):
                    raise RuntimeError(
                        "Existing confirmed bootstrap numeric data differs: "
                        f"position_uid={leg.position_uid}, field={key}"
                    )

        existing_orders = self._connection.execute(
            """
            SELECT *
            FROM ib_virtual_position_leg_orders
            ORDER BY position_uid, broker_order_id
            """
        ).fetchall()

        if len(existing_orders) != len(order_mappings):
            raise RuntimeError("Existing confirmed bootstrap order count differs")

        existing_by_key = {
            (str(row["position_uid"]), str(row["broker_order_id"])): row
            for row in existing_orders
        }

        for mapping in order_mappings:
            key = (
                str(mapping.get("position_uid") or "").strip(),
                str(mapping.get("broker_order_id") or "").strip(),
            )
            row = existing_by_key.get(key)

            if row is None:
                raise RuntimeError(
                    "Existing confirmed bootstrap order identity differs"
                )

            text_values = {
                "order_role": mapping.get("order_role"),
                "parent_order_id": mapping.get("parent_id"),
                "perm_id": mapping.get("perm_id"),
                "action": mapping.get("action"),
                "order_type": mapping.get("order_type"),
                "oca_group": mapping.get("oca_group"),
                "execution_status": mapping.get("execution_status"),
            }

            for field_name, value in text_values.items():
                if (
                    str(row[field_name] or "").strip().upper()
                    != str(value or "").strip().upper()
                ):
                    raise RuntimeError(
                        "Existing confirmed bootstrap order data differs: "
                        f"order_id={key[1]}, field={field_name}"
                    )

            if int(row["is_active"]) != int(bool(mapping.get("is_active"))):
                raise RuntimeError("Existing confirmed bootstrap active state differs")

            for field_name in ("client_id", "oca_type"):
                if self._optional_int_value(row[field_name]) != (
                    self._optional_int_value(mapping.get(field_name))
                ):
                    raise RuntimeError(
                        "Existing confirmed bootstrap order integer differs: "
                        f"order_id={key[1]}, field={field_name}"
                    )

            for field_name in ("quantity", "price"):
                if not self._float_values_equal(
                    row[field_name],
                    mapping.get(field_name),
                ):
                    raise RuntimeError(
                        "Existing confirmed bootstrap order number differs: "
                        f"order_id={key[1]}, field={field_name}"
                    )

        return True

    @staticmethod
    def _optional_float_value(value: object) -> float | None:
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

    @staticmethod
    def _float_values_equal(
        left: object,
        right: object,
        tolerance: float = 1e-9,
    ) -> bool:
        left_number = RuntimeRepository._optional_float_value(left)
        right_number = RuntimeRepository._optional_float_value(right)

        if left_number is None or right_number is None:
            return left_number is None and right_number is None

        return abs(left_number - right_number) <= tolerance

    def sync_reconciled_ib_virtual_position_leg_snapshot(
        self,
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Atomically persist one fully reconciled IB virtual-leg snapshot.

        Incomplete, BLOCKED, UNRECONCILED or orphan-containing snapshots
        are rejected before the first SQLite write.
        """
        self._validate_ib_virtual_leg_sync_snapshot(
            snapshot=snapshot,
            evidence_snapshot=evidence_snapshot,
        )

        open_orders = list(evidence_snapshot.get("open_orders") or [])
        completed_orders = list(evidence_snapshot.get("completed_orders") or [])
        executions = list(evidence_snapshot.get("executions") or [])
        current_client_id = self._optional_int_value(
            evidence_snapshot.get("current_client_id")
        )
        captured_utc = str(snapshot.captured_utc or "").strip()
        legs_written = 0
        orders_written = 0
        open_legs = 0
        closed_legs = 0

        self._connection.execute("SAVEPOINT ib_virtual_leg_sync")

        try:
            for leg in snapshot.legs:
                closed_utc = self._ib_virtual_leg_closed_utc(
                    leg=leg,
                    executions=executions,
                    fallback_utc=captured_utc,
                )
                self._upsert_ib_virtual_position_leg_no_commit(
                    leg=leg,
                    remaining_volume=(
                        0.0
                        if leg.leg_status == IB_LEG_STATUS_CLOSED
                        else abs(float(leg.volume))
                    ),
                    closed_utc=closed_utc,
                )
                legs_written += 1

                if leg.leg_status == IB_LEG_STATUS_CLOSED:
                    closed_legs += 1
                else:
                    open_legs += 1

                parent_perm_id = self._ib_effective_parent_perm_id(leg)
                parent_row = self._find_ib_order_evidence_row(
                    order_id=leg.parent_order_id,
                    perm_id=parent_perm_id,
                    open_orders=open_orders,
                    completed_orders=completed_orders,
                )
                parent_execution_rows = self._execution_rows_for_order(
                    order_id=leg.parent_order_id,
                    perm_id=parent_perm_id,
                    executions=executions,
                )
                self._upsert_ib_virtual_position_leg_order_no_commit(
                    position_uid=leg.position_uid,
                    order_role=IB_LEG_ORDER_ROLE_PARENT,
                    broker_order_id=leg.parent_order_id,
                    evidence_row=parent_row,
                    execution_rows=parent_execution_rows,
                    default_action=leg.side,
                    default_order_type="MKT",
                    default_quantity=leg.volume,
                    default_price=leg.entry_price,
                    default_status="FILLED",
                    is_active=True,
                    default_perm_id=parent_perm_id,
                )
                orders_written += 1

                for close_order_id in leg.close_order_ids:
                    close_perm_id = self._persisted_ib_leg_order_perm_id(
                        position_uid=leg.position_uid,
                        order_role=IB_LEG_ORDER_ROLE_CLOSE,
                        broker_order_id=close_order_id,
                    )
                    close_row = (
                        self._find_ib_order_evidence_row(
                            order_id=close_order_id,
                            perm_id=close_perm_id,
                            open_orders=open_orders,
                            completed_orders=completed_orders,
                        )
                        if close_perm_id is not None
                        else None
                    )
                    close_executions = (
                        self._execution_rows_for_order(
                            order_id=close_order_id,
                            perm_id=close_perm_id,
                            executions=executions,
                        )
                        if close_perm_id is not None
                        else []
                    )
                    self._upsert_ib_virtual_position_leg_order_no_commit(
                        position_uid=leg.position_uid,
                        order_role=IB_LEG_ORDER_ROLE_CLOSE,
                        broker_order_id=close_order_id,
                        evidence_row=close_row,
                        execution_rows=close_executions,
                        default_action=leg.protective_action,
                        default_order_type="MKT",
                        default_quantity=leg.volume,
                        default_price=None,
                        default_status="FILLED",
                        is_active=False,
                        default_perm_id=close_perm_id,
                    )
                    orders_written += 1

                active_roles: set[str] = set()

                for order_role, order_id, order_perm_id in (
                    (
                        IB_LEG_ORDER_ROLE_STOP_LOSS,
                        leg.stop_loss_order_id,
                        leg.stop_loss_order_perm_id,
                    ),
                    (
                        IB_LEG_ORDER_ROLE_TAKE_PROFIT,
                        leg.take_profit_order_id,
                        leg.take_profit_order_perm_id,
                    ),
                ):
                    active_row = self._find_order_row_by_identity(
                        rows=open_orders,
                        order_id=order_id,
                        perm_id=order_perm_id,
                    )

                    if active_row is None:
                        continue

                    if not self._ib_protective_order_belongs_to_leg(
                        row=active_row,
                        leg=leg,
                        current_client_id=current_client_id,
                        allow_zero_quantity=False,
                    ):
                        if leg.leg_status == IB_LEG_STATUS_CLOSED:
                            continue

                        raise RuntimeError(
                            "Active protective order evidence changed "
                            "after reconciliation"
                        )

                    self._upsert_ib_virtual_position_leg_order_no_commit(
                        position_uid=leg.position_uid,
                        order_role=order_role,
                        broker_order_id=order_id,
                        evidence_row=active_row,
                        execution_rows=(),
                        default_action=leg.protective_action,
                        default_order_type=(
                            "STP"
                            if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS
                            else "LMT"
                        ),
                        default_quantity=leg.volume,
                        default_price=(
                            leg.stop_loss
                            if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS
                            else leg.take_profit
                        ),
                        default_status="SUBMITTED",
                        is_active=True,
                        default_perm_id=order_perm_id,
                    )
                    active_roles.add(order_role)
                    orders_written += 1

                for completed_row in completed_orders:
                    if not self._ib_protective_order_belongs_to_leg(
                        row=completed_row,
                        leg=leg,
                        current_client_id=current_client_id,
                        allow_zero_quantity=True,
                    ):
                        continue

                    order_role = self._ib_order_role_from_row(completed_row)

                    if order_role is None:
                        continue

                    completed_order_id = self._optional_int_value(
                        completed_row.get("order_id")
                    )

                    if completed_order_id is None:
                        continue

                    completed_perm_id = self._optional_int_value(
                        completed_row.get("perm_id")
                    )
                    completed_executions = self._execution_rows_for_order(
                        order_id=completed_order_id,
                        perm_id=completed_perm_id,
                        executions=executions,
                    )
                    self._upsert_ib_virtual_position_leg_order_no_commit(
                        position_uid=leg.position_uid,
                        order_role=order_role,
                        broker_order_id=completed_order_id,
                        evidence_row=completed_row,
                        execution_rows=completed_executions,
                        default_action=leg.protective_action,
                        default_order_type=(
                            "STP"
                            if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS
                            else "LMT"
                        ),
                        default_quantity=leg.volume,
                        default_price=(
                            leg.stop_loss
                            if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS
                            else leg.take_profit
                        ),
                        default_status="COMPLETED",
                        is_active=False,
                        default_perm_id=completed_perm_id,
                    )
                    orders_written += 1

                for order_role in (
                    IB_LEG_ORDER_ROLE_STOP_LOSS,
                    IB_LEG_ORDER_ROLE_TAKE_PROFIT,
                ):
                    if order_role in active_roles:
                        continue

                    self._deactivate_ib_virtual_position_leg_order_no_commit(
                        position_uid=leg.position_uid,
                        order_role=order_role,
                        execution_status=(
                            "CLOSED"
                            if leg.leg_status == IB_LEG_STATUS_CLOSED
                            else "NOT_ACTIVE"
                        ),
                    )

            external_exposures = self._sync_ib_fx_external_exposures_no_commit(snapshot)
            self._connection.execute("RELEASE ib_virtual_leg_sync")
            self._connection.commit()
        except Exception:
            self._connection.execute("ROLLBACK TO ib_virtual_leg_sync")
            self._connection.execute("RELEASE ib_virtual_leg_sync")
            self._connection.rollback()
            raise

        return {
            "captured_utc": captured_utc,
            "legs_written": legs_written,
            "orders_written": orders_written,
            "open_legs": open_legs,
            "closed_legs": closed_legs,
            "external_exposures": external_exposures,
        }

    def _sync_ib_fx_external_exposures_no_commit(
        self,
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
    ) -> int:
        """Persist external FX facts and lifecycle events atomically."""
        captured_utc = str(snapshot.captured_utc or "").strip() or utc_now_iso()
        legs_by_group: dict[str, IBVirtualPositionLeg] = {}

        for leg in snapshot.legs:
            legs_by_group.setdefault(leg.broker_position_id, leg)

        residuals = snapshot.group_broker_residual_signed_volumes
        statuses = snapshot.group_broker_residual_evidence_statuses
        external_exposures = snapshot.group_external_exposures
        rows_written = 0

        for broker_position_id, evidence_status in statuses.items():
            leg = legs_by_group.get(broker_position_id)
            external_exposure = external_exposures.get(broker_position_id)

            if leg is not None:
                account_id = leg.account_id
                symbol_name = leg.symbol_name
            elif external_exposure is not None:
                account_id = external_exposure.account_id
                symbol_name = external_exposure.symbol_name
            else:
                continue

            signed_volume = float(residuals.get(broker_position_id, 0.0))
            status = str(evidence_status or "").strip().upper()

            if status not in {
                IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
                IB_FX_EXTERNAL_EXPOSURE_STALE,
            }:
                continue

            existing = self._connection.execute(
                """
                SELECT account_id,
                       symbol,
                       signed_volume,
                       evidence_status,
                       last_confirmed_utc
                FROM ib_fx_external_exposures
                WHERE broker_position_id = ?
                LIMIT 1
                """,
                (broker_position_id,),
            ).fetchone()

            if abs(signed_volume) <= IB_POSITION_QUANTITY_ABS_TOLERANCE:
                if status != IB_FX_EXTERNAL_EXPOSURE_CONFIRMED:
                    continue
                if existing is None:
                    continue

                previous_status = str(existing["evidence_status"] or "").upper()
                previous_volume = float(existing["signed_volume"] or 0.0)
                cursor = self._connection.execute(
                    """
                    UPDATE ib_fx_external_exposures
                    SET signed_volume = 0.0,
                        evidence_status = ?,
                        last_observed_utc = ?,
                        cleared_utc = ?,
                        updated_utc = ?
                    WHERE broker_position_id = ?
                    """,
                    (
                        IB_FX_EXTERNAL_EXPOSURE_CLEARED,
                        captured_utc,
                        captured_utc,
                        captured_utc,
                        broker_position_id,
                    ),
                )
                rows_written += max(0, int(cursor.rowcount or 0))

                if (
                    previous_status != IB_FX_EXTERNAL_EXPOSURE_CLEARED
                    or abs(previous_volume) > IB_POSITION_QUANTITY_ABS_TOLERANCE
                ):
                    self._insert_ib_fx_external_exposure_event_no_commit(
                        event_type=RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_CLEARED,
                        broker_position_id=broker_position_id,
                        account_id=account_id,
                        symbol_name=symbol_name,
                        signed_volume=0.0,
                        evidence_status=IB_FX_EXTERNAL_EXPOSURE_CLEARED,
                        captured_utc=captured_utc,
                        previous_signed_volume=previous_volume,
                        previous_evidence_status=previous_status,
                    )
                continue

            previous_status = (
                str(existing["evidence_status"] or "").upper()
                if existing is not None
                else ""
            )
            previous_volume = (
                float(existing["signed_volume"] or 0.0) if existing is not None else 0.0
            )
            previous_account = (
                str(existing["account_id"] or "").strip()
                if existing is not None
                else ""
            )
            previous_symbol = (
                str(existing["symbol"] or "").strip().upper()
                if existing is not None
                else ""
            )
            last_confirmed_utc = (
                captured_utc
                if status == IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
                else str(
                    existing["last_confirmed_utc"] if existing is not None else ""
                ).strip()
            )

            self._connection.execute(
                """
                INSERT INTO ib_fx_external_exposures (
                    broker_position_id,
                    account_id,
                    symbol,
                    signed_volume,
                    evidence_status,
                    last_confirmed_utc,
                    last_observed_utc,
                    cleared_utc,
                    updated_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(broker_position_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    symbol = excluded.symbol,
                    signed_volume = excluded.signed_volume,
                    evidence_status = excluded.evidence_status,
                    last_confirmed_utc = CASE
                        WHEN excluded.evidence_status = ?
                            THEN excluded.last_confirmed_utc
                        ELSE ib_fx_external_exposures.last_confirmed_utc
                    END,
                    last_observed_utc = excluded.last_observed_utc,
                    cleared_utc = NULL,
                    updated_utc = excluded.updated_utc
                """,
                (
                    broker_position_id,
                    account_id,
                    symbol_name,
                    signed_volume,
                    status,
                    last_confirmed_utc or None,
                    captured_utc,
                    captured_utc,
                    IB_FX_EXTERNAL_EXPOSURE_CONFIRMED,
                ),
            )
            rows_written += 1

            changed = bool(
                existing is None
                or previous_status != status
                or abs(previous_volume - signed_volume)
                > IB_POSITION_QUANTITY_ABS_TOLERANCE
                or previous_account != account_id
                or previous_symbol != symbol_name
            )

            if changed:
                event_type = (
                    RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
                    if status == IB_FX_EXTERNAL_EXPOSURE_CONFIRMED
                    else RuntimeEventType.IB_FX_EXTERNAL_EXPOSURE_STALE
                )
                self._insert_ib_fx_external_exposure_event_no_commit(
                    event_type=event_type,
                    broker_position_id=broker_position_id,
                    account_id=account_id,
                    symbol_name=symbol_name,
                    signed_volume=signed_volume,
                    evidence_status=status,
                    captured_utc=captured_utc,
                    previous_signed_volume=previous_volume,
                    previous_evidence_status=previous_status,
                )

        return rows_written

    def _insert_ib_fx_external_exposure_event_no_commit(
        self,
        *,
        event_type: RuntimeEventType,
        broker_position_id: str,
        account_id: str,
        symbol_name: str,
        signed_volume: float,
        evidence_status: str,
        captured_utc: str,
        previous_signed_volume: float,
        previous_evidence_status: str,
    ) -> None:
        """Append one durable external-exposure transition in the same tx."""
        payload = {
            "policy": IB_FX_EXECUTION_POLICY_LGE_EXCLUSIVE,
            "broker": "IB",
            "broker_position_id": broker_position_id,
            "account_id": account_id,
            "symbol": symbol_name,
            "signed_volume": float(signed_volume),
            "evidence_status": evidence_status,
            "previous_signed_volume": float(previous_signed_volume),
            "previous_evidence_status": previous_evidence_status,
        }
        message = (
            f"IB FX external exposure {evidence_status}: "
            f"account={account_id}, symbol={symbol_name}, "
            f"signed_volume={signed_volume:g}"
        )
        self._connection.execute(
            """
            INSERT INTO runtime_events (
                event_type,
                message,
                payload_json,
                created_utc
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                event_type.value,
                message,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                captured_utc,
            ),
        )

    def resolve_ib_virtual_position_leg_close_evidence_missing(
        self,
        *,
        position_uid: str,
        expected_broker_position_id: str,
        expected_account_id: str,
        expected_symbol_name: str,
        expected_side: str,
        expected_volume: float,
        resolution_reason: str,
    ) -> dict[str, Any]:
        """Persist an explicit user-confirmed broker-side close recovery.

        This method never contacts IB and never creates a broker order. The
        caller must validate a fresh complete evidence snapshot immediately
        before invoking this transaction.
        """
        position_uid_clean = str(position_uid or "").strip()
        broker_position_id_clean = str(expected_broker_position_id or "").strip()
        account_id_clean = str(expected_account_id or "").strip()
        symbol_name_clean = str(expected_symbol_name or "").strip().upper()
        side_clean = str(expected_side or "").strip().upper()
        reason_clean = str(resolution_reason or "").strip()

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        if (
            not broker_position_id_clean
            or not account_id_clean
            or not symbol_name_clean
        ):
            raise ValueError("IB manual reconciliation identity is incomplete")

        if side_clean not in {"BUY", "SELL"}:
            raise ValueError("IB manual reconciliation side is invalid")

        expected_volume_value = abs(float(expected_volume))

        if expected_volume_value <= 0.0:
            raise ValueError("IB manual reconciliation volume is invalid")

        row = self._connection.execute(
            """
            SELECT
                positions.state AS position_state,
                positions.broker AS position_broker,
                positions.symbol AS position_symbol,
                positions.side AS position_side,
                positions.volume AS position_volume,
                ib_virtual_position_legs.*
            FROM positions
            INNER JOIN ib_virtual_position_legs
                ON ib_virtual_position_legs.position_uid
                    = positions.position_uid
            WHERE positions.position_uid = ?
            LIMIT 1
            """,
            (position_uid_clean,),
        ).fetchone()

        if row is None:
            raise RuntimeError("IB virtual leg was not found in persistence")

        persisted = dict(row)

        if str(persisted.get("position_broker") or "").upper() != "IB":
            raise RuntimeError("Manual reconciliation target is not an IB leg")

        if str(persisted.get("position_state") or "").upper() != "OPEN":
            raise RuntimeError("IB virtual leg position is not OPEN")

        if str(persisted.get("leg_status") or "").upper() != IB_LEG_STATUS_OPEN:
            raise RuntimeError("IB virtual leg is not OPEN")

        identity_checks = {
            "broker_position_id": broker_position_id_clean,
            "account_id": account_id_clean,
            "symbol": symbol_name_clean,
            "side": side_clean,
        }

        for field_name, expected_value in identity_checks.items():
            actual_value = str(persisted.get(field_name) or "").strip().upper()

            if actual_value != expected_value.upper():
                raise RuntimeError(
                    f"IB manual reconciliation identity changed: {field_name}"
                )

        persisted_volume = abs(float(persisted.get("initial_volume") or 0.0))

        if abs(persisted_volume - expected_volume_value) > (
            IB_POSITION_QUANTITY_ABS_TOLERANCE
        ):
            raise RuntimeError("IB manual reconciliation volume changed")

        resolved_utc = utc_now_iso()
        previous_reconciliation_status = (
            str(persisted.get("reconciliation_status") or "").strip().upper()
        )
        try:
            previous_messages = json.loads(
                str(persisted.get("reconciliation_messages_json") or "[]")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            previous_messages = []

        if not isinstance(previous_messages, list):
            previous_messages = []

        manual_message = (
            "RECONCILED_MANUAL: user confirmed that the broker position "
            "was already closed while exact close execution evidence was "
            "unavailable. No broker order was sent."
        )
        messages = [
            str(message) for message in previous_messages if str(message or "").strip()
        ]

        if manual_message not in messages:
            messages.append(manual_message)

        payload = {
            "position_uid": position_uid_clean,
            "broker_position_id": str(
                persisted.get("broker_position_id") or ""
            ).strip(),
            "account_id": account_id_clean,
            "symbol_name": symbol_name_clean,
            "side": side_clean,
            "volume": expected_volume_value,
            "previous_reconciliation_status": previous_reconciliation_status,
            "new_reconciliation_status": IB_RECONCILIATION_STATUS_RECONCILED_MANUAL,
            "resolution_reason": reason_clean,
            "broker_operation_attempted": False,
            "resolved_utc": resolved_utc,
        }
        self._connection.execute("SAVEPOINT ib_manual_close_recovery")

        try:
            position_cursor = self._connection.execute(
                """
                UPDATE positions
                SET state = 'CLOSED'
                WHERE position_uid = ?
                  AND state = 'OPEN'
                """,
                (position_uid_clean,),
            )

            if int(position_cursor.rowcount or 0) != 1:
                raise RuntimeError(
                    "IB virtual leg position changed during manual recovery"
                )

            leg_cursor = self._connection.execute(
                """
                UPDATE ib_virtual_position_legs
                SET remaining_volume = 0.0,
                    leg_status = ?,
                    protection_status = ?,
                    reconciliation_status = ?,
                    reconciliation_messages_json = ?,
                    closed_utc = ?,
                    updated_utc = ?
                WHERE position_uid = ?
                  AND leg_status = ?
                """,
                (
                    IB_LEG_STATUS_CLOSED,
                    IB_PROTECTION_STATUS_NONE,
                    IB_RECONCILIATION_STATUS_RECONCILED_MANUAL,
                    json.dumps(messages, ensure_ascii=False),
                    resolved_utc,
                    resolved_utc,
                    position_uid_clean,
                    IB_LEG_STATUS_OPEN,
                ),
            )

            if int(leg_cursor.rowcount or 0) != 1:
                raise RuntimeError("IB virtual leg changed during manual recovery")

            orders_cursor = self._connection.execute(
                """
                UPDATE ib_virtual_position_leg_orders
                SET is_active = 0,
                    execution_status = 'MANUAL_RECOVERY_CLOSED',
                    updated_utc = ?
                WHERE position_uid = ?
                  AND is_active = 1
                """,
                (resolved_utc, position_uid_clean),
            )
            self._connection.execute(
                """
                INSERT INTO runtime_events (
                    event_type,
                    message,
                    payload_json,
                    created_utc
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    RuntimeEventType.IB_MANUAL_RECONCILIATION_RESOLVED.value,
                    (
                        "IB CLOSE_EVIDENCE_MISSING manually resolved "
                        f"for {symbol_name_clean} {side_clean} "
                        f"{expected_volume_value:g}"
                    ),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    resolved_utc,
                ),
            )
            self._connection.execute("RELEASE ib_manual_close_recovery")
            self._connection.commit()
        except Exception:
            self._connection.execute("ROLLBACK TO ib_manual_close_recovery")
            self._connection.execute("RELEASE ib_manual_close_recovery")
            self._connection.rollback()
            raise

        return {
            **payload,
            "closed": True,
            "orders_deactivated": int(orders_cursor.rowcount or 0),
            "audit_event_type": (
                RuntimeEventType.IB_MANUAL_RECONCILIATION_RESOLVED.value
            ),
            "audit_payload": payload,
        }

    def persist_confirmed_ib_virtual_position_leg_close(
        self,
        leg: IBVirtualPositionLeg,
        close_order_id: int,
        evidence_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist one exact broker-confirmed explicit virtual-leg Close."""
        if leg.leg_status != IB_LEG_STATUS_CLOSED:
            raise RuntimeError("Confirmed virtual leg is not CLOSED")

        if leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED:
            raise RuntimeError("Confirmed virtual leg is not RECONCILED")

        if close_order_id not in leg.close_order_ids:
            raise RuntimeError("Confirmed close order identity differs")

        if not bool(evidence_snapshot.get("complete")):
            raise RuntimeError("IB virtual-leg close evidence is incomplete")

        for flag_name in (
            "positions_complete",
            "open_orders_complete",
            "completed_orders_complete",
            "executions_complete",
        ):
            if not bool(evidence_snapshot.get(flag_name)):
                raise RuntimeError(
                    f"IB virtual-leg close evidence flag is false: {flag_name}"
                )

        open_orders = list(evidence_snapshot.get("open_orders") or [])
        completed_orders = list(evidence_snapshot.get("completed_orders") or [])
        executions = list(evidence_snapshot.get("executions") or [])
        order_id_execution_rows = self._execution_rows_for_order(
            order_id=close_order_id,
            perm_id=None,
            executions=executions,
        )
        execution_rows = [
            row
            for row in order_id_execution_rows
            if self._ib_close_execution_matches_leg([row], leg)
        ]
        close_perm_id = self._optional_int_value(
            self._first_execution_value(execution_rows, "perm_id")
        )

        if not self._ib_close_execution_matches_leg(execution_rows, leg):
            raise RuntimeError("IB virtual-leg close execution evidence differs")

        active_child_ids = {
            self._optional_int_value(row.get("order_id")) for row in open_orders
        } & {
            value
            for value in (
                leg.stop_loss_order_id,
                leg.take_profit_order_id,
            )
            if value is not None
        }

        if active_child_ids:
            raise RuntimeError("Closed IB virtual leg still has active protection")

        close_row = self._find_ib_order_evidence_row(
            order_id=close_order_id,
            perm_id=close_perm_id,
            open_orders=open_orders,
            completed_orders=completed_orders,
        )
        closed_utc = self._first_execution_value(execution_rows, "time")
        self._connection.execute("SAVEPOINT ib_virtual_leg_close")

        try:
            self._upsert_ib_virtual_position_leg_no_commit(
                leg=leg,
                remaining_volume=0.0,
                closed_utc=str(closed_utc or "").strip() or None,
            )
            self._upsert_ib_virtual_position_leg_order_no_commit(
                position_uid=leg.position_uid,
                order_role=IB_LEG_ORDER_ROLE_CLOSE,
                broker_order_id=close_order_id,
                evidence_row=close_row,
                execution_rows=execution_rows,
                default_action=leg.protective_action,
                default_order_type="MKT",
                default_quantity=leg.volume,
                default_price=None,
                default_status="FILLED",
                is_active=False,
                default_perm_id=close_perm_id,
            )

            for order_role in (
                IB_LEG_ORDER_ROLE_STOP_LOSS,
                IB_LEG_ORDER_ROLE_TAKE_PROFIT,
            ):
                self._deactivate_ib_virtual_position_leg_order_no_commit(
                    position_uid=leg.position_uid,
                    order_role=order_role,
                    execution_status="CANCELLED_BEFORE_CLOSE",
                )

            self._connection.execute("RELEASE ib_virtual_leg_close")
            self._connection.commit()
        except Exception:
            self._connection.execute("ROLLBACK TO ib_virtual_leg_close")
            self._connection.execute("RELEASE ib_virtual_leg_close")
            self._connection.rollback()
            raise

        return {
            "position_uid": leg.position_uid,
            "close_order_id": close_order_id,
            "legs_written": 1,
            "orders_written": 1,
            "closed_utc": str(closed_utc or "").strip() or None,
        }

    @staticmethod
    def _ib_close_execution_matches_leg(
        rows: list[dict[str, Any]],
        leg: IBVirtualPositionLeg,
    ) -> bool:
        if not rows:
            return False

        quantity = sum(
            RuntimeRepository._safe_float_value(row.get("shares")) for row in rows
        )

        if not RuntimeRepository._float_values_equal(
            quantity,
            leg.volume,
            tolerance=IB_POSITION_QUANTITY_ABS_TOLERANCE,
        ):
            return False

        expected_sides = (
            {"BOT", "BUY"} if leg.protective_action == "BUY" else {"SLD", "SELL"}
        )

        for row in rows:
            if str(row.get("account") or "").strip() != leg.account_id:
                return False

            if RuntimeRepository._ib_symbol_name_from_row(row) != leg.symbol_name:
                return False

            if str(row.get("side") or "").strip().upper() not in expected_sides:
                return False

        return True

    @staticmethod
    def _ib_symbol_name_from_row(row: dict[str, Any]) -> str:
        symbol_name = str(row.get("symbol_name") or "").strip().upper()

        if symbol_name:
            return symbol_name

        symbol = str(row.get("symbol") or "").strip().upper()
        currency = str(row.get("currency") or "").strip().upper()
        return f"{symbol}{currency}" if symbol and currency else symbol

    @staticmethod
    def _validate_ib_virtual_leg_sync_snapshot(
        snapshot: IBVirtualPositionLegReconciliationSnapshot,
        evidence_snapshot: dict[str, Any],
    ) -> None:
        """
        Reject unsafe persistence input before any SQLite write.
        """
        if not snapshot.complete:
            raise RuntimeError("IB virtual-leg snapshot is incomplete")

        if not bool(evidence_snapshot.get("complete")):
            raise RuntimeError("IB virtual-leg evidence is incomplete")

        for flag_name in (
            "positions_complete",
            "open_orders_complete",
            "completed_orders_complete",
            "executions_complete",
        ):
            if not bool(evidence_snapshot.get(flag_name)):
                raise RuntimeError(
                    f"IB virtual-leg evidence flag is false: {flag_name}"
                )

        if snapshot.unmapped_protective_order_ids:
            raise RuntimeError(
                "IB virtual-leg snapshot contains unmapped protective orders"
            )

        if any(
            status != IB_RECONCILIATION_STATUS_RECONCILED
            for status in snapshot.group_statuses.values()
        ):
            raise RuntimeError(
                "Only fully reconciled IB virtual-leg groups may be persisted"
            )

        if any(
            leg.reconciliation_status != IB_RECONCILIATION_STATUS_RECONCILED
            for leg in snapshot.legs
        ):
            raise RuntimeError("Only reconciled IB virtual legs may be persisted")

        if any(
            leg.leg_status == IB_LEG_STATUS_PARTIALLY_CLOSED for leg in snapshot.legs
        ):
            raise RuntimeError("PARTIALLY_CLOSED persistence requires remaining volume")

        position_uids = [leg.position_uid for leg in snapshot.legs]

        if len(position_uids) != len(set(position_uids)):
            raise RuntimeError("Duplicate position_uid in virtual-leg snapshot")

    def _upsert_ib_virtual_position_leg_no_commit(
        self,
        leg: IBVirtualPositionLeg,
        remaining_volume: float,
        closed_utc: str | None,
    ) -> None:
        position_uid = str(leg.position_uid or "").strip()
        trade_uid = str(leg.trade_uid or "").strip()

        if not position_uid or not trade_uid:
            raise ValueError("IB virtual leg identity is incomplete")

        initial_volume = abs(float(leg.volume))
        remaining = abs(float(remaining_volume))

        if remaining > initial_volume:
            raise ValueError("IB virtual leg remaining volume exceeds initial volume")

        now_utc = utc_now_iso()
        messages_json = json.dumps(
            list(leg.reconciliation_messages),
            ensure_ascii=False,
        )

        self._connection.execute(
            """
            INSERT INTO ib_virtual_position_legs (
                position_uid,
                trade_uid,
                broker_position_id,
                account_id,
                symbol,
                side,
                initial_volume,
                remaining_volume,
                entry_price,
                opened_utc,
                source,
                parent_order_id,
                stop_loss_order_id,
                take_profit_order_id,
                stop_loss,
                take_profit,
                oca_group,
                leg_status,
                protection_status,
                reconciliation_status,
                reconciliation_messages_json,
                closed_utc,
                created_utc,
                updated_utc
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(position_uid) DO UPDATE SET
                trade_uid = excluded.trade_uid,
                broker_position_id = excluded.broker_position_id,
                account_id = excluded.account_id,
                symbol = excluded.symbol,
                side = excluded.side,
                remaining_volume = excluded.remaining_volume,
                entry_price = excluded.entry_price,
                opened_utc = excluded.opened_utc,
                source = excluded.source,
                parent_order_id = excluded.parent_order_id,
                stop_loss_order_id = excluded.stop_loss_order_id,
                take_profit_order_id = excluded.take_profit_order_id,
                stop_loss = excluded.stop_loss,
                take_profit = excluded.take_profit,
                oca_group = excluded.oca_group,
                leg_status = excluded.leg_status,
                protection_status = excluded.protection_status,
                reconciliation_status = excluded.reconciliation_status,
                reconciliation_messages_json =
                    excluded.reconciliation_messages_json,
                closed_utc = excluded.closed_utc,
                updated_utc = excluded.updated_utc
            """,
            (
                position_uid,
                trade_uid,
                str(leg.broker_position_id or "").strip(),
                str(leg.account_id or "").strip(),
                str(leg.symbol_name or "").strip().upper(),
                str(leg.side or "").strip().upper(),
                initial_volume,
                remaining,
                leg.entry_price,
                str(leg.opened_utc or "").strip() or None,
                str(leg.source or "").strip().upper(),
                self._optional_order_id_text(leg.parent_order_id),
                self._optional_order_id_text(leg.stop_loss_order_id),
                self._optional_order_id_text(leg.take_profit_order_id),
                leg.stop_loss,
                leg.take_profit,
                str(leg.oca_group or "").strip(),
                str(leg.leg_status or "").strip().upper(),
                str(leg.protection_status or "").strip().upper(),
                str(leg.reconciliation_status or "").strip().upper(),
                messages_json,
                str(closed_utc or "").strip() or None,
                now_utc,
                now_utc,
            ),
        )

    def _upsert_ib_virtual_position_leg_order_no_commit(
        self,
        position_uid: str,
        order_role: str,
        broker_order_id: int | str | None,
        evidence_row: dict[str, Any] | None,
        execution_rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        default_action: str,
        default_order_type: str,
        default_quantity: float,
        default_price: float | None,
        default_status: str,
        is_active: bool,
        default_order_ref: str = "",
        default_perm_id: int | None = None,
    ) -> None:
        order_id_text = self._optional_order_id_text(broker_order_id)

        if order_id_text is None:
            raise ValueError("IB virtual leg broker order id is missing")

        row = evidence_row or {}
        role = str(order_role or "").strip().upper()

        if role not in IB_LEG_ORDER_ROLES:
            raise ValueError(f"Unsupported IB virtual leg order role: {role}")

        if is_active:
            self._connection.execute(
                """
                UPDATE ib_virtual_position_leg_orders
                SET is_active = 0,
                    updated_utc = ?
                WHERE position_uid = ?
                  AND order_role = ?
                  AND broker_order_id != ?
                  AND is_active = 1
                """,
                (
                    utc_now_iso(),
                    str(position_uid or "").strip(),
                    role,
                    order_id_text,
                ),
            )

        quantity = self._ib_order_quantity(
            row=row,
            execution_rows=execution_rows,
            fallback=default_quantity,
        )
        price = self._ib_order_price(
            row=row,
            execution_rows=execution_rows,
            fallback=default_price,
        )
        execution_status = self._ib_order_status(
            row=row,
            fallback=default_status,
        )
        now_utc = utc_now_iso()

        self._connection.execute(
            """
            INSERT INTO ib_virtual_position_leg_orders (
                position_uid,
                order_role,
                broker_order_id,
                parent_order_id,
                perm_id,
                client_id,
                action,
                order_type,
                quantity,
                price,
                oca_group,
                oca_type,
                order_ref,
                execution_status,
                is_active,
                created_utc,
                updated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(position_uid, broker_order_id) DO UPDATE SET
                order_role = excluded.order_role,
                parent_order_id = excluded.parent_order_id,
                perm_id = excluded.perm_id,
                client_id = excluded.client_id,
                action = excluded.action,
                order_type = excluded.order_type,
                quantity = excluded.quantity,
                price = excluded.price,
                oca_group = excluded.oca_group,
                oca_type = excluded.oca_type,
                order_ref = CASE
                    WHEN excluded.order_ref != '' THEN excluded.order_ref
                    ELSE ib_virtual_position_leg_orders.order_ref
                END,
                execution_status = excluded.execution_status,
                is_active = excluded.is_active,
                updated_utc = excluded.updated_utc
            """,
            (
                str(position_uid or "").strip(),
                role,
                order_id_text,
                self._optional_order_id_text(row.get("parent_id")),
                self._optional_order_id_text(
                    row.get("perm_id")
                    or self._first_execution_value(
                        execution_rows,
                        "perm_id",
                    )
                    or default_perm_id
                ),
                self._optional_int_value(row.get("client_id")),
                self._optional_upper_text(row.get("action") or default_action),
                self._optional_upper_text(row.get("order_type") or default_order_type),
                quantity,
                price,
                str(row.get("oca_group") or "").strip(),
                self._optional_int_value(row.get("oca_type")),
                str(row.get("order_ref") or default_order_ref or "").strip(),
                execution_status,
                1 if is_active else 0,
                now_utc,
                now_utc,
            ),
        )

    def _deactivate_ib_virtual_position_leg_order_no_commit(
        self,
        position_uid: str,
        order_role: str,
        execution_status: str,
    ) -> None:
        self._connection.execute(
            """
            UPDATE ib_virtual_position_leg_orders
            SET is_active = 0,
                execution_status = ?,
                updated_utc = ?
            WHERE position_uid = ?
              AND order_role = ?
              AND is_active = 1
            """,
            (
                str(execution_status or "").strip().upper(),
                utc_now_iso(),
                str(position_uid or "").strip(),
                str(order_role or "").strip().upper(),
            ),
        )

    @staticmethod
    def _find_order_row_by_id(
        rows: list[dict[str, Any]],
        order_id: int | None,
    ) -> dict[str, Any] | None:
        if order_id is None:
            return None

        for row in rows:
            try:
                row_order_id = int(row.get("order_id"))
            except (TypeError, ValueError):
                continue

            if row_order_id == int(order_id):
                return row

        return None

    @classmethod
    def _find_order_row_by_identity(
        cls,
        rows: list[dict[str, Any]],
        order_id: int | None,
        perm_id: int | None,
    ) -> dict[str, Any] | None:
        if order_id is None:
            return None

        for row in rows:
            if cls._ib_order_identity_matches(
                row=row,
                order_id=order_id,
                perm_id=perm_id,
            ):
                return row

        return None

    def _find_ib_order_evidence_row(
        self,
        order_id: int | None,
        perm_id: int | None,
        open_orders: list[dict[str, Any]],
        completed_orders: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        row = self._find_order_row_by_identity(
            open_orders,
            order_id,
            perm_id,
        )

        if row is not None:
            return row

        return self._find_order_row_by_identity(
            completed_orders,
            order_id,
            perm_id,
        )

    @classmethod
    def _execution_rows_for_order(
        cls,
        order_id: int | None,
        perm_id: int | None,
        executions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if order_id is None:
            return []

        return [
            row
            for row in executions
            if cls._ib_order_identity_matches(
                row=row,
                order_id=order_id,
                perm_id=perm_id,
            )
        ]

    @classmethod
    def _ib_order_identity_matches(
        cls,
        *,
        row: dict[str, Any],
        order_id: int | None,
        perm_id: int | None,
    ) -> bool:
        if order_id is None:
            return False

        row_order_id = cls._optional_int_value(row.get("order_id"))

        if perm_id is None:
            return row_order_id == order_id

        if cls._optional_int_value(row.get("perm_id")) != perm_id:
            return False

        return row_order_id in {None, 0, order_id}

    def _ib_protective_order_belongs_to_leg(
        self,
        row: dict[str, Any],
        leg: IBVirtualPositionLeg,
        current_client_id: int | None,
        allow_zero_quantity: bool,
    ) -> bool:
        order_type = str(row.get("order_type") or "").strip().upper()

        if order_type not in IB_PROTECTIVE_ORDER_TYPES:
            return False

        parent_id = self._optional_int_value(row.get("parent_id"))
        order_role = self._ib_order_role_from_row(row)

        if order_role == IB_LEG_ORDER_ROLE_STOP_LOSS:
            persisted_order_id = leg.stop_loss_order_id
            persisted_perm_id = leg.stop_loss_order_perm_id
        elif order_role == IB_LEG_ORDER_ROLE_TAKE_PROFIT:
            persisted_order_id = leg.take_profit_order_id
            persisted_perm_id = leg.take_profit_order_perm_id
        else:
            return False

        if persisted_order_id is not None:
            if not self._ib_order_identity_matches(
                row=row,
                order_id=persisted_order_id,
                perm_id=persisted_perm_id,
            ):
                return False
        elif parent_id != leg.parent_order_id:
            return False

        persisted_oca_group = str(leg.oca_group or "").strip()

        if persisted_oca_group and str(row.get("oca_group") or "").strip() != (
            persisted_oca_group
        ):
            return False

        account_id = str(row.get("account") or "").strip()

        if account_id != leg.account_id:
            return False

        broker_position_id = str(row.get("broker_position_id") or "").strip()
        symbol_name = str(row.get("symbol_name") or "").strip().upper()

        if broker_position_id:
            if broker_position_id != leg.broker_position_id:
                return False
        elif symbol_name != leg.symbol_name:
            return False

        if str(row.get("action") or "").strip().upper() != leg.protective_action:
            return False

        if not self._ib_order_is_owned_by_client(
            row=row,
            current_client_id=current_client_id,
        ):
            return False

        quantity = self._safe_float_value(
            row.get("total_quantity", row.get("quantity"))
        )

        if allow_zero_quantity and quantity == 0.0:
            return True

        return abs(quantity - abs(float(leg.volume))) <= 1e-9

    @classmethod
    def _ib_effective_parent_perm_id(
        cls,
        leg: IBVirtualPositionLeg,
    ) -> int | None:
        numeric_oca_group = cls._optional_int_value(leg.oca_group)

        if numeric_oca_group is not None:
            return numeric_oca_group

        return leg.parent_order_perm_id

    @staticmethod
    def _ib_order_is_owned_by_client(
        row: dict[str, Any],
        current_client_id: int | None,
    ) -> bool:
        same_client = row.get("same_client_id")

        if same_client is not None:
            return bool(same_client)

        if current_client_id is None:
            return False

        try:
            return int(row.get("client_id")) == current_client_id
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _ib_order_role_from_row(
        row: dict[str, Any],
    ) -> str | None:
        order_type = str(row.get("order_type") or "").strip().upper()

        if order_type in IB_STOP_ORDER_TYPES:
            return IB_LEG_ORDER_ROLE_STOP_LOSS

        if order_type in IB_PROTECTIVE_ORDER_TYPES:
            return IB_LEG_ORDER_ROLE_TAKE_PROFIT

        return None

    @staticmethod
    def _ib_order_status(
        row: dict[str, Any],
        fallback: str,
    ) -> str:
        for key in ("completed_status", "status"):
            value = str(row.get(key) or "").strip().upper()

            if value:
                return value

        return str(fallback or "").strip().upper()

    def _ib_order_quantity(
        self,
        row: dict[str, Any],
        execution_rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        fallback: float,
    ) -> float:
        quantity = self._safe_float_value(
            row.get("total_quantity", row.get("quantity"))
        )

        if quantity > 0.0:
            return abs(quantity)

        execution_quantity = sum(
            self._safe_float_value(execution.get("shares"))
            for execution in execution_rows
        )

        if execution_quantity > 0.0:
            return abs(execution_quantity)

        return abs(float(fallback))

    def _ib_order_price(
        self,
        row: dict[str, Any],
        execution_rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        fallback: float | None,
    ) -> float | None:
        order_type = str(row.get("order_type") or "").strip().upper()

        if order_type in IB_STOP_ORDER_TYPES:
            price = self._safe_float_value(row.get("aux_price"))
        elif order_type in IB_PROTECTIVE_ORDER_TYPES:
            price = self._safe_float_value(row.get("lmt_price"))
        else:
            price = 0.0

        if price > 0.0:
            return price

        if execution_rows:
            quantity = sum(
                self._safe_float_value(execution.get("shares"))
                for execution in execution_rows
            )

            if quantity > 0.0:
                weighted_value = sum(
                    self._safe_float_value(execution.get("shares"))
                    * self._safe_float_value(execution.get("price"))
                    for execution in execution_rows
                )
                return weighted_value / quantity

        return fallback

    @staticmethod
    def _first_execution_value(
        execution_rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        key: str,
    ) -> object | None:
        for row in execution_rows:
            value = row.get(key)

            if value not in (None, "", 0):
                return value

        return None

    def _ib_virtual_leg_closed_utc(
        self,
        leg: IBVirtualPositionLeg,
        executions: list[dict[str, Any]],
        fallback_utc: str,
    ) -> str | None:
        if leg.leg_status != IB_LEG_STATUS_CLOSED:
            return None

        order_identities = [
            (leg.stop_loss_order_id, leg.stop_loss_order_perm_id),
            (leg.take_profit_order_id, leg.take_profit_order_perm_id),
        ]
        order_identities.extend(
            (
                close_order_id,
                self._persisted_ib_leg_order_perm_id(
                    position_uid=leg.position_uid,
                    order_role=IB_LEG_ORDER_ROLE_CLOSE,
                    broker_order_id=close_order_id,
                ),
            )
            for close_order_id in leg.close_order_ids
        )

        for order_id, perm_id in order_identities:
            if order_id is None or perm_id is None:
                continue

            for execution in executions:
                if not self._ib_order_identity_matches(
                    row=execution,
                    order_id=order_id,
                    perm_id=perm_id,
                ):
                    continue

                if str(execution.get("account") or "").strip() != leg.account_id:
                    continue

                symbol_name = str(execution.get("symbol_name") or "").strip().upper()

                if not symbol_name:
                    symbol = str(execution.get("symbol") or "").strip().upper()
                    currency = str(execution.get("currency") or "").strip().upper()
                    symbol_name = f"{symbol}{currency}"

                if symbol_name != leg.symbol_name:
                    continue

                closed_utc = str(execution.get("time") or "").strip()

                if closed_utc:
                    return closed_utc

        existing = self._connection.execute(
            """
            SELECT closed_utc
            FROM ib_virtual_position_legs
            WHERE position_uid = ?
            LIMIT 1
            """,
            (leg.position_uid,),
        ).fetchone()

        if existing is not None:
            persisted_closed_utc = str(existing["closed_utc"] or "").strip()

            if persisted_closed_utc:
                return persisted_closed_utc

        return fallback_utc or None

    def _persisted_ib_leg_order_perm_id(
        self,
        *,
        position_uid: str,
        order_role: str,
        broker_order_id: int | str,
    ) -> int | None:
        row = self._connection.execute(
            """
            SELECT perm_id
            FROM ib_virtual_position_leg_orders
            WHERE position_uid = ?
              AND order_role = ?
              AND broker_order_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                str(position_uid or "").strip(),
                str(order_role or "").strip().upper(),
                str(broker_order_id or "").strip(),
            ),
        ).fetchone()

        if row is None:
            return None

        return self._optional_int_value(row["perm_id"])

    @staticmethod
    def _safe_float_value(value: object) -> float:
        number = RuntimeRepository._optional_float_value(value)
        return number if number is not None else 0.0

    @staticmethod
    def _optional_int_value(value: object) -> int | None:
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

    @staticmethod
    def _optional_order_id_text(value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _optional_upper_text(value: object) -> str | None:
        text = str(value or "").strip().upper()
        return text or None

    def mark_position_closed_by_broker_position_id(
        self,
        broker: str,
        broker_position_id: str,
    ) -> int:
        """
        Позначити Runtime Position як CLOSED за broker_position_id.
        """
        cursor = self._connection.execute(
            """
            UPDATE positions
            SET state = 'CLOSED'
            WHERE broker = ?
              AND broker_position_id = ?
              AND state = 'OPEN'
            """,
            (
                str(broker).strip().upper(),
                str(broker_position_id).strip(),
            ),
        )

        self._connection.commit()

        return int(cursor.rowcount or 0)
