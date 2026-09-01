"""Synthetic IB CLOSE_EVIDENCE_MISSING manual recovery check."""

from __future__ import annotations

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_CLOSED,
    IB_PROTECTION_STATUS_NONE,
    IB_RECONCILIATION_STATUS_RECONCILED_MANUAL,
)
from engine.runtime_engine import RuntimeEngine  # noqa: E402
from engine.runtime_events import RuntimeEventType  # noqa: E402

ACCOUNT_ID = "DUM513747"
POSITION_UID = "78ab6bfb-84a5-40bd-95a0-f3639312f1fc"
TRADE_UID = "1ee17b45-0605-415c-b052-b0d1d3f3a540"
ORDER_PLAN_UID = "manual-recovery-order-plan"
BROKER_ORDER_UID = "manual-recovery-broker-order"
BROKER_POSITION_ID = f"IB:{ACCOUNT_ID}:EURUSD"


class EvidenceOnlyIBService:
    """Read-only fake service that exposes no broker operation methods."""

    def __init__(self, evidence: dict[str, Any]) -> None:
        self.evidence = evidence
        self.evidence_calls = 0

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        self.evidence_calls += 1
        return deepcopy(self.evidence)

    @staticmethod
    def get_positions() -> list:
        return []


def build_evidence(*, broker_position_present: bool) -> dict[str, Any]:
    positions: list[dict[str, Any]] = []

    if broker_position_present:
        positions.append(
            {
                "account": ACCOUNT_ID,
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "symbol_name": "EURUSD",
                "broker_position_id": BROKER_POSITION_ID,
                "signed_quantity": -1000.0,
                "position": -1000.0,
                "avg_cost": 1.13645,
            }
        )

    return {
        "broker": "IB",
        "captured_utc": "2026-07-29T06:00:00+00:00",
        "current_client_id": 1,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": positions,
        "open_orders": [],
        "completed_orders": [],
        "executions": [],
    }


def seed_runtime_rows(engine: RuntimeEngine) -> None:
    connection = engine.connection
    connection.execute(
        """
        INSERT INTO trades (
            trade_uid, broker, account_id, symbol, side, volume,
            created_utc, source, comment
        )
        VALUES (?, 'IB', ?, 'EURUSD', 'SELL', 1000.0, ?, 'MANUAL', ?)
        """,
        (
            TRADE_UID,
            ACCOUNT_ID,
            "2026-07-28T08:09:00+00:00",
            "LGE manual UI order",
        ),
    )
    connection.execute(
        """
        INSERT INTO order_plans (
            order_plan_uid, trade_uid, order_type, side, volume,
            created_utc, source
        )
        VALUES (?, ?, 'MARKET', 'SELL', 1000.0, ?, 'MANUAL')
        """,
        (ORDER_PLAN_UID, TRADE_UID, "2026-07-28T08:09:00+00:00"),
    )
    connection.execute(
        """
        INSERT INTO broker_orders (
            broker_order_uid, trade_uid, order_plan_uid, broker,
            broker_order_id, execution_status, broker_timestamp,
            created_utc, source, broker_comment
        )
        VALUES (?, ?, ?, 'IB', '211', 'FILLED', ?, ?, 'MANUAL', ?)
        """,
        (
            BROKER_ORDER_UID,
            TRADE_UID,
            ORDER_PLAN_UID,
            "20260728 08:09:00 UTC",
            "2026-07-28T08:09:00+00:00",
            "[LGE:M] LGE manual UI order",
        ),
    )
    connection.execute(
        """
        INSERT INTO positions (
            position_uid, trade_uid, broker_order_uid, broker,
            broker_position_id, symbol, side, volume, open_price,
            opened_utc, state, created_utc, source
        )
        VALUES (?, ?, ?, 'IB', ?, 'EURUSD', 'SELL', 1000.0, 1.13645,
                ?, 'OPEN', ?, 'MANUAL')
        """,
        (
            POSITION_UID,
            TRADE_UID,
            BROKER_ORDER_UID,
            BROKER_POSITION_ID,
            "2026-07-28T08:09:00+00:00",
            "2026-07-28T08:09:00+00:00",
        ),
    )
    connection.execute(
        """
        INSERT INTO ib_virtual_position_legs (
            position_uid, trade_uid, broker_position_id, account_id,
            symbol, side, initial_volume, remaining_volume, entry_price,
            opened_utc, source, parent_order_id, stop_loss_order_id,
            take_profit_order_id, stop_loss, take_profit, oca_group,
            leg_status, protection_status, reconciliation_status,
            reconciliation_messages_json, closed_utc, created_utc,
            updated_utc
        )
        VALUES (?, ?, ?, ?, 'EURUSD', 'SELL', 1000.0, 1000.0, 1.13645,
                ?, 'MANUAL', '211', '213', '212', 1.1385, 1.133,
                '1209513133', 'OPEN', 'COMPLETE', 'RECONCILED', '[]',
                NULL, ?, ?)
        """,
        (
            POSITION_UID,
            TRADE_UID,
            BROKER_POSITION_ID,
            ACCOUNT_ID,
            "2026-07-28T08:09:00+00:00",
            "2026-07-28T08:09:00+00:00",
            "2026-07-28T08:09:00+00:00",
        ),
    )

    for role, order_id, order_type, price in (
        ("PARENT", "211", "MKT", None),
        ("STOP_LOSS", "213", "STP", 1.1385),
        ("TAKE_PROFIT", "212", "LMT", 1.133),
    ):
        connection.execute(
            """
            INSERT INTO ib_virtual_position_leg_orders (
                position_uid, order_role, broker_order_id, parent_order_id,
                action, order_type, quantity, price, oca_group, order_ref,
                execution_status, is_active, created_utc, updated_utc
            )
            VALUES (?, ?, ?, '211', ?, ?, 1000.0, ?, '1209513133', ?,
                    'PERSISTED_ACTIVE', 1, ?, ?)
            """,
            (
                POSITION_UID,
                role,
                order_id,
                "SELL" if role == "PARENT" else "BUY",
                order_type,
                price,
                "[LGE:M] LGE manual UI order",
                "2026-07-28T08:09:00+00:00",
                "2026-07-29T05:40:00+00:00",
            ),
        )

    connection.commit()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lge_ib_manual_recovery_") as tmp:
        db_path = Path(tmp) / "test.db"
        engine = RuntimeEngine(db_path=str(db_path))
        engine.set_active_broker("IB", require_connected=False)
        seed_runtime_rows(engine)
        service = EvidenceOnlyIBService(build_evidence(broker_position_present=True))
        service_for_test: Any = service
        engine.ib_runtime_service = service_for_test

        try:
            try:
                engine.resolve_ib_close_evidence_missing(POSITION_UID)
            except RuntimeError as exc:
                if not any(
                    text in str(exc)
                    for text in (
                        "not CLOSE_EVIDENCE_MISSING",
                        "broker position is still present",
                    )
                ):
                    raise
            else:
                raise AssertionError(
                    "Manual recovery was allowed while broker exposure existed"
                )

            service.evidence = build_evidence(broker_position_present=False)
            result = engine.resolve_ib_close_evidence_missing(POSITION_UID)

            if not result.get("closed"):
                raise AssertionError("Manual recovery did not close the leg")

            if result.get("broker_operation_attempted") is not False:
                raise AssertionError("Manual recovery reported broker activity")

            if int(result.get("orders_deactivated") or 0) != 3:
                raise AssertionError("Persisted leg orders were not deactivated")

            position_row = engine.connection.execute(
                "SELECT state FROM positions WHERE position_uid = ?",
                (POSITION_UID,),
            ).fetchone()
            leg_row = engine.connection.execute(
                """
                SELECT remaining_volume, leg_status, protection_status,
                       reconciliation_status, closed_utc,
                       reconciliation_messages_json
                FROM ib_virtual_position_legs
                WHERE position_uid = ?
                """,
                (POSITION_UID,),
            ).fetchone()

            if str(position_row["state"]) != "CLOSED":
                raise AssertionError("Runtime position was not CLOSED")

            if float(leg_row["remaining_volume"]) != 0.0:
                raise AssertionError("Manual recovery retained leg volume")

            if str(leg_row["leg_status"]) != IB_LEG_STATUS_CLOSED:
                raise AssertionError("Virtual leg was not CLOSED")

            if str(leg_row["protection_status"]) != IB_PROTECTION_STATUS_NONE:
                raise AssertionError("Virtual leg retained protection")

            if str(leg_row["reconciliation_status"]) != (
                IB_RECONCILIATION_STATUS_RECONCILED_MANUAL
            ):
                raise AssertionError("Manual reconciliation status was lost")

            messages = json.loads(str(leg_row["reconciliation_messages_json"]))

            if not any("RECONCILED_MANUAL" in value for value in messages):
                raise AssertionError("Manual recovery audit message is absent")

            event_row = engine.connection.execute(
                """
                SELECT event_type, payload_json
                FROM runtime_events
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if str(event_row["event_type"]) != (
                RuntimeEventType.IB_MANUAL_RECONCILIATION_RESOLVED.value
            ):
                raise AssertionError("Runtime audit event type differs")

            payload = json.loads(str(event_row["payload_json"]))

            if payload.get("broker_operation_attempted") is not False:
                raise AssertionError("Audit payload reports broker activity")

            active_mapping_count = engine.connection.execute(
                """
                SELECT COUNT(*)
                FROM ib_virtual_position_leg_orders
                WHERE position_uid = ?
                  AND is_active = 1
                """,
                (POSITION_UID,),
            ).fetchone()[0]

            if int(active_mapping_count) != 0:
                raise AssertionError("Active persisted order mappings remain")

            after_snapshot = engine.get_active_broker_position_groups()

            if any(group.symbol_name == "EURUSD" for group in after_snapshot.groups):
                raise AssertionError("Resolved EURUSD remained active")

            synced_snapshot = engine.sync_active_broker_position_groups()

            if synced_snapshot.groups:
                raise AssertionError("Safe refresh restored a closed group")

            try:
                engine.resolve_ib_close_evidence_missing(POSITION_UID)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Manual recovery was not idempotently blocked")

            audit_count = engine.connection.execute(
                """
                SELECT COUNT(*)
                FROM runtime_events
                WHERE event_type = ?
                """,
                (RuntimeEventType.IB_MANUAL_RECONCILIATION_RESOLVED.value,),
            ).fetchone()[0]

            if int(audit_count) != 1:
                raise AssertionError("Manual recovery audit event was duplicated")

            print("RuntimeEngine IB manual close-evidence recovery result")
            print("  first_attempt_with_broker_exposure_blocked=True")
            print("  broker_operation_attempted=False")
            print("  position_state=CLOSED")
            print("  leg_status=CLOSED")
            print("  remaining_volume=0")
            print("  protection_status=NONE")
            print("  reconciliation_status=RECONCILED_MANUAL")
            print("  persisted_orders_deactivated=3")
            print("  runtime_audit_event=True")
            print("  duplicate_resolution_blocked=True")
            print("  active_groups_after_resolution=0")
            print("RUNTIME_ENGINE_IB_CLOSE_EVIDENCE_MANUAL_RECOVERY_CHECK=OK")
            return 0
        finally:
            engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
