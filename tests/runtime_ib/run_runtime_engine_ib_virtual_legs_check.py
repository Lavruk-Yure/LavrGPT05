# run_runtime_engine_ib_virtual_legs_check.py
"""
RuntimeEngine IB virtual-leg read-only reconciliation check.

RoadMap90:
- repository seeds + complete IB evidence;
- one EURUSD leg broker-closed by STP;
- both GBPUSD opposite legs broker-closed;
- remaining EURUSD 2K leg stays OPEN with its own protection;
- no SQLite writes during get_open_runtime_position_legs().
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_virtual_position_leg import (  # noqa: E402
    build_ib_virtual_position_legs_from_repository_seeds,
    reconcile_ib_virtual_position_legs,
)
from engine.runtime_constants import (  # noqa: E402
    IB_LEG_STATUS_CLOSED,
    IB_LEG_STATUS_OPEN,
    IB_PROTECTION_STATUS_COMPLETE,
    IB_RECONCILIATION_STATUS_BLOCKED,
    IB_RECONCILIATION_STATUS_RECONCILED,
)
from engine.runtime_account_state import RuntimeAccountState  # noqa: E402
from engine.runtime_broker_health import RuntimeBrokerHealth  # noqa: E402
from engine.runtime_engine import (  # noqa: E402
    IBRuntimeServiceProtocol,
    RuntimeEngine,
)

ACCOUNT_ID = "DUM513747"
CURRENT_CLIENT_ID = 1


class DummyIBRuntimeService(IBRuntimeServiceProtocol):
    """
    Read-only dummy service for the RuntimeEngine integration check.
    """

    def __init__(self, snapshot: dict[str, Any]) -> None:
        """
        Store the complete synthetic evidence snapshot.
        """
        self.snapshot = snapshot
        self.evidence_calls = 0

    @staticmethod
    def _unexpected_call(method_name: str) -> NoReturn:
        """
        Fail if the read-only integration check uses another service path.
        """
        raise AssertionError(f"Unexpected dummy service call: {method_name}")

    def connect_demo(self) -> object | None:
        """
        Reject broker connection calls in this read-only synthetic test.
        """
        self._unexpected_call("connect_demo")

    def disconnect(self) -> None:
        """
        Reject broker disconnect calls in this read-only synthetic test.
        """
        self._unexpected_call("disconnect")

    def get_broker_health(self) -> RuntimeBrokerHealth:
        """
        Reject broker-health calls in this read-only synthetic test.
        """
        self._unexpected_call("get_broker_health")

    def get_account_state(self) -> RuntimeAccountState:
        """
        Reject account-state calls in this read-only synthetic test.
        """
        self._unexpected_call("get_account_state")

    def reconnect(self) -> object | None:
        """
        Reject reconnect calls in this read-only synthetic test.
        """
        self._unexpected_call("reconnect")

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        """
        Return one complete synthetic evidence snapshot.
        """
        self.evidence_calls += 1
        return deepcopy(self.snapshot)

    def get_positions(self) -> list:
        """
        Reject legacy position calls in this read-only synthetic test.
        """
        self._unexpected_call("get_positions")

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        """
        Reject order placement in this read-only synthetic test.
        """
        del symbol_name, side, quantity, stop_loss, take_profit, comment
        self._unexpected_call("place_market_order")

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        """
        Reject position close in this read-only synthetic test.
        """
        del position_id, quantity, comment
        self._unexpected_call("close_position")

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Reject SL/TP modification in this read-only synthetic test.
        """
        del position_id, stop_loss, take_profit
        self._unexpected_call("modify_position_sl_tp")

    def close_virtual_position_leg(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        comment: str = "LGE virtual-leg close",
    ) -> dict:
        del (
            position_uid,
            position_id,
            account_id,
            symbol_name,
            position_side,
            position_volume,
            parent_order_id,
            stop_loss_order_id,
            take_profit_order_id,
            current_oca_group,
            comment,
        )
        self._unexpected_call("close_virtual_position_leg")

    def modify_virtual_position_leg_sl_tp(
        self,
        position_uid: str,
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        current_oca_group: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        order_ref: str = "",
    ) -> dict:
        del (
            position_uid,
            position_id,
            account_id,
            symbol_name,
            position_side,
            position_volume,
            parent_order_id,
            stop_loss_order_id,
            take_profit_order_id,
            current_oca_group,
            stop_loss,
            take_profit,
        )
        self._unexpected_call("modify_virtual_position_leg_sl_tp")


def _create_open_ib_position(
    engine: RuntimeEngine,
    *,
    symbol_name: str,
    logical_side: str,
    logical_volume: float,
    parent_order_id: int,
    broker_snapshot_side: str,
    broker_snapshot_volume: float,
    broker_snapshot_open_price: float,
) -> str:
    """
    Create one legacy RoadMap84-style Runtime chain row.
    """
    trade_uid = engine.repository.create_trade(
        broker="IB",
        account_id=ACCOUNT_ID,
        symbol=symbol_name,
        side=logical_side,
        volume=logical_volume,
        source="MANUAL",
    )
    order_plan_uid = engine.repository.create_order_plan(
        trade_uid=trade_uid,
        order_type="MARKET",
        side=logical_side,
        volume=logical_volume,
        source="MANUAL",
    )
    broker_order_uid = engine.repository.create_broker_order(
        trade_uid=trade_uid,
        order_plan_uid=order_plan_uid,
        broker="IB",
        broker_order_id=str(parent_order_id),
        execution_status="FILLED",
        source="MANUAL",
    )
    return engine.repository.create_position(
        trade_uid=trade_uid,
        broker_order_uid=broker_order_uid,
        broker="IB",
        broker_position_id=f"IB:{ACCOUNT_ID}:{symbol_name}",
        symbol=symbol_name,
        side=broker_snapshot_side,
        volume=broker_snapshot_volume,
        open_price=broker_snapshot_open_price,
        opened_utc="2026-07-16T12:00:00+00:00",
        source="BROKER",
    )


def _execution(
    order_id: int,
    symbol: str,
    side: str,
    shares: float,
    price: float,
    time_text: str,
) -> dict[str, Any]:
    """
    Build one scalar IB execution evidence row.
    """
    return {
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": "USD",
        "side": side,
        "shares": shares,
        "price": price,
        "time": time_text,
        "order_id": order_id,
        "perm_id": order_id + 10000,
    }


def _order(
    order_id: int,
    parent_id: int,
    symbol: str,
    action: str,
    order_type: str,
    quantity: float,
    price: float,
) -> dict[str, Any]:
    """
    Build one active protective order evidence row.
    """
    symbol_name = f"{symbol}USD"
    row = {
        "order_id": order_id,
        "parent_id": parent_id,
        "account": ACCOUNT_ID,
        "symbol": symbol,
        "currency": "USD",
        "sec_type": "CASH",
        "symbol_name": symbol_name,
        "broker_position_id": f"IB:{ACCOUNT_ID}:{symbol_name}",
        "action": action,
        "order_type": order_type,
        "total_quantity": quantity,
        "lmt_price": 0.0,
        "aux_price": 0.0,
        "client_id": CURRENT_CLIENT_ID,
        "same_client_id": True,
        "oca_group": f"LGE_{parent_id}",
    }

    if order_type == "LMT":
        row["lmt_price"] = price
    else:
        row["aux_price"] = price

    return row


def _completed_order(
    order_id: int,
    parent_id: int,
    symbol: str,
    action: str,
    order_type: str,
    quantity: float,
    price: float,
    completed_status: str,
) -> dict[str, Any]:
    """
    Build one completed protective order evidence row.
    """
    row = _order(
        order_id=order_id,
        parent_id=parent_id,
        symbol=symbol,
        action=action,
        order_type=order_type,
        quantity=quantity,
        price=price,
    )
    row.update(
        {
            "total_quantity": 0.0,
            "status": completed_status,
            "completed_status": completed_status,
            "completed_time": "20260716 18:00:00",
            "filled": quantity if completed_status == "Filled" else 0.0,
            "remaining": 0.0,
        }
    )
    return row


def _build_evidence() -> dict[str, Any]:
    """
    Build evidence after real-style broker-triggered closes.
    """
    return {
        "broker": "IB",
        "captured_utc": "2026-07-16T15:05:00+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "broker_position_id": f"IB:{ACCOUNT_ID}:EURUSD",
                "signed_quantity": 2000.0,
            }
        ],
        "open_orders": [
            _order(115, 114, "EUR", "SELL", "LMT", 2000.0, 1.152),
            _order(116, 114, "EUR", "SELL", "STP", 2000.0, 1.143),
        ],
        "completed_orders": [
            _completed_order(
                112,
                111,
                "EUR",
                "SELL",
                "LMT",
                1000.0,
                1.151,
                "Cancelled",
            ),
            _completed_order(
                113,
                111,
                "EUR",
                "SELL",
                "STP",
                1000.0,
                1.144,
                "Filled",
            ),
            _completed_order(
                118,
                117,
                "GBP",
                "SELL",
                "LMT",
                3000.0,
                1.361,
                "Cancelled",
            ),
            _completed_order(
                119,
                117,
                "GBP",
                "SELL",
                "STP",
                3000.0,
                1.349,
                "Filled",
            ),
            _completed_order(
                121,
                120,
                "GBP",
                "BUY",
                "LMT",
                2000.0,
                1.349,
                "Filled",
            ),
            _completed_order(
                122,
                120,
                "GBP",
                "BUY",
                "STP",
                2000.0,
                1.359,
                "Cancelled",
            ),
        ],
        "executions": [
            _execution(111, "EUR", "BOT", 1000.0, 1.14885, "12:00"),
            _execution(114, "EUR", "BOT", 2000.0, 1.14765, "12:05"),
            _execution(117, "GBP", "BOT", 3000.0, 1.35225, "12:10"),
            _execution(120, "GBP", "SLD", 2000.0, 1.35125, "12:15"),
            _execution(119, "GBP", "SLD", 3000.0, 1.349, "17:57"),
            _execution(121, "GBP", "BOT", 2000.0, 1.349, "17:57"),
            _execution(113, "EUR", "SLD", 1000.0, 1.144, "18:02"),
        ],
    }


def _build_cash_fx_stop_event_evidence() -> dict[str, Any]:
    """
    Відтворити новий trading-day event: STP 116 закрив BUY 2K leg.

    TWS Virtual FX row після SELL execution показує SELL 2K, а не zero.
    """
    eurusd_id = f"IB:{ACCOUNT_ID}:EURUSD"
    return {
        "broker": "IB",
        "captured_utc": "2026-07-17T10:51:12+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "completed_orders_api_only": False,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "broker_position_id": eurusd_id,
                "account_id": ACCOUNT_ID,
                "symbol_name": "EURUSD",
                "symbol": "EUR",
                "currency": "USD",
                "sec_type": "CASH",
                "signed_quantity": -2000.0,
                "average_cost": 1.14185,
            }
        ],
        "open_orders": [],
        "completed_orders": [
            _completed_order(
                115,
                114,
                "EUR",
                "SELL",
                "LMT",
                2000.0,
                1.152,
                "Cancelled",
            ),
            _completed_order(
                116,
                114,
                "EUR",
                "SELL",
                "STP",
                2000.0,
                1.143,
                "Filled",
            ),
        ],
        "executions": [
            _execution(
                116,
                "EUR",
                "SLD",
                2000.0,
                1.14185,
                "13:51:12",
            )
        ],
    }


def _table_counts(engine: RuntimeEngine) -> dict[str, int]:
    """
    Read persistence counts to prove the operation is read-only.
    """
    result: dict[str, int] = {}

    for table_name in ("trades", "order_plans", "broker_orders", "positions"):
        row = engine.connection.execute(
            f"SELECT COUNT(*) AS count_value FROM {table_name}"
        ).fetchone()
        result[table_name] = int(row["count_value"])

    return result


def _virtual_leg_counts(engine: RuntimeEngine) -> dict[str, int]:
    """
    Return current virtual-leg persistence row counts.
    """
    result: dict[str, int] = {}

    for table_name in (
        "ib_virtual_position_legs",
        "ib_virtual_position_leg_orders",
    ):
        row = engine.connection.execute(
            f"SELECT COUNT(*) AS count_value FROM {table_name}"
        ).fetchone()
        result[table_name] = int(row["count_value"])

    return result


def _virtual_leg_state(engine: RuntimeEngine) -> dict[str, list[tuple]]:
    """
    Return complete persisted rows to prove rejected sync is write-free.
    """
    result: dict[str, list[tuple]] = {}

    for table_name in (
        "ib_virtual_position_legs",
        "ib_virtual_position_leg_orders",
    ):
        cursor = engine.connection.execute(f"SELECT * FROM {table_name} ORDER BY id")
        result[table_name] = [tuple(row) for row in cursor.fetchall()]

    return result


def main() -> int:
    """
    Run RuntimeEngine repository + evidence reconciliation check.
    """
    engine = RuntimeEngine(db_path=":memory:")
    position_uids = [
        _create_open_ib_position(
            engine,
            symbol_name="EURUSD",
            logical_side="BUY",
            logical_volume=1000.0,
            parent_order_id=111,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=1000.0,
            broker_snapshot_open_price=1.14885,
        ),
        _create_open_ib_position(
            engine,
            symbol_name="EURUSD",
            logical_side="BUY",
            logical_volume=2000.0,
            parent_order_id=114,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=3000.0,
            broker_snapshot_open_price=1.1473833333,
        ),
        _create_open_ib_position(
            engine,
            symbol_name="GBPUSD",
            logical_side="BUY",
            logical_volume=3000.0,
            parent_order_id=117,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=3000.0,
            broker_snapshot_open_price=1.35225,
        ),
        _create_open_ib_position(
            engine,
            symbol_name="GBPUSD",
            logical_side="SELL",
            logical_volume=2000.0,
            parent_order_id=120,
            broker_snapshot_side="BUY",
            broker_snapshot_volume=1000.0,
            broker_snapshot_open_price=1.3529166667,
        ),
    ]
    service = DummyIBRuntimeService(_build_evidence())

    try:
        engine.set_ib_runtime_service(service)
        engine.set_broker("IB")
        counts_before = _table_counts(engine)
        snapshot = engine.get_open_runtime_position_legs()
        counts_after = _table_counts(engine)

        legs_by_uid = {leg.position_uid: leg for leg in snapshot.legs}
        eurusd_id = f"IB:{ACCOUNT_ID}:EURUSD"
        gbpusd_id = f"IB:{ACCOUNT_ID}:GBPUSD"

        if counts_after != counts_before:
            raise AssertionError("Virtual-leg snapshot changed SQLite")

        if service.evidence_calls != 1:
            raise AssertionError("Unexpected evidence service call count")

        if snapshot.group_statuses[eurusd_id] != (IB_RECONCILIATION_STATUS_RECONCILED):
            raise AssertionError("EURUSD group was not reconciled")

        if snapshot.group_statuses[gbpusd_id] != (IB_RECONCILIATION_STATUS_RECONCILED):
            raise AssertionError("GBPUSD zero-net group was not reconciled")

        expected_statuses = [
            IB_LEG_STATUS_CLOSED,
            IB_LEG_STATUS_OPEN,
            IB_LEG_STATUS_CLOSED,
            IB_LEG_STATUS_CLOSED,
        ]
        actual_statuses = [
            legs_by_uid[position_uid].leg_status for position_uid in position_uids
        ]

        if actual_statuses != expected_statuses:
            raise AssertionError(f"Unexpected leg statuses: {actual_statuses}")

        remaining_leg = legs_by_uid[position_uids[1]]

        if remaining_leg.protection_status != IB_PROTECTION_STATUS_COMPLETE:
            raise AssertionError("Remaining EURUSD leg protection mismatch")

        if remaining_leg.stop_loss_order_id != 116:
            raise AssertionError("Remaining EURUSD SL order mismatch")

        if remaining_leg.take_profit_order_id != 115:
            raise AssertionError("Remaining EURUSD TP order mismatch")

        if legs_by_uid[position_uids[0]].stop_loss_order_id != 113:
            raise AssertionError("EURUSD broker-close STP mapping mismatch")

        if legs_by_uid[position_uids[2]].stop_loss_order_id != 119:
            raise AssertionError("GBPUSD BUY close STP mapping mismatch")

        if legs_by_uid[position_uids[3]].take_profit_order_id != 121:
            raise AssertionError("GBPUSD SELL close TP mapping mismatch")

        open_legs = [
            leg for leg in snapshot.legs if leg.leg_status == IB_LEG_STATUS_OPEN
        ]
        closed_legs = [
            leg for leg in snapshot.legs if leg.leg_status == IB_LEG_STATUS_CLOSED
        ]

        orphan_evidence = _build_evidence()
        orphan_evidence["open_orders"].append(
            _order(123, 111, "EUR", "SELL", "LMT", 1000.0, 1.151)
        )
        seeds = engine.repository.get_open_ib_virtual_position_leg_seeds(
            account_id=ACCOUNT_ID,
        )
        seed_legs = build_ib_virtual_position_legs_from_repository_seeds(seeds)
        orphan_snapshot = reconcile_ib_virtual_position_legs(
            seed_legs,
            orphan_evidence,
        )

        if orphan_snapshot.group_statuses[eurusd_id] != (
            IB_RECONCILIATION_STATUS_BLOCKED
        ):
            raise AssertionError("Closed-leg orphan order did not block group")

        foreign_client_evidence = _build_evidence()
        foreign_client_evidence["completed_orders"][4]["same_client_id"] = False
        foreign_client_snapshot = reconcile_ib_virtual_position_legs(
            seed_legs,
            foreign_client_evidence,
        )

        if foreign_client_snapshot.group_statuses[gbpusd_id] != (
            IB_RECONCILIATION_STATUS_BLOCKED
        ):
            raise AssertionError(
                "Different-client completed protection did not block group"
            )

        service.snapshot = _build_evidence()
        sync_result = engine.sync_reconciled_ib_virtual_position_legs()
        persisted_counts = _virtual_leg_counts(engine)

        if sync_result["persistence"]["legs_written"] != 4:
            raise AssertionError("Unexpected persisted virtual-leg count")

        if persisted_counts["ib_virtual_position_legs"] != 4:
            raise AssertionError("Virtual-leg state rows were not persisted")

        if persisted_counts["ib_virtual_position_leg_orders"] != 12:
            raise AssertionError("Virtual-leg order history is incomplete")

        active_order_count = int(
            engine.connection.execute(
                """
                SELECT COUNT(*) AS count_value
                FROM ib_virtual_position_leg_orders
                WHERE is_active = 1
                """
            ).fetchone()["count_value"]
        )

        if active_order_count != 6:
            raise AssertionError("Unexpected active virtual-leg order count")

        persisted_open_seeds = engine.repository.get_open_ib_virtual_position_leg_seeds(
            account_id=ACCOUNT_ID,
        )

        if len(persisted_open_seeds) != 1:
            raise AssertionError("Persisted CLOSED legs remained open seeds")

        persisted_open_seed = persisted_open_seeds[0]

        if int(persisted_open_seed["persisted_stop_loss_order_id"]) != 116:
            raise AssertionError("Persisted open-leg SL mapping mismatch")

        if int(persisted_open_seed["persisted_take_profit_order_id"]) != 115:
            raise AssertionError("Persisted open-leg TP mapping mismatch")

        counts_before_repeat = _virtual_leg_counts(engine)
        repeat_result = engine.sync_reconciled_ib_virtual_position_legs()
        counts_after_repeat = _virtual_leg_counts(engine)

        if counts_after_repeat != counts_before_repeat:
            raise AssertionError("Repeated persistence sync created duplicates")

        blocked_evidence = _build_evidence()
        blocked_evidence["positions"][0]["signed_quantity"] = 1000.0
        service.snapshot = blocked_evidence
        state_before_blocked = _virtual_leg_state(engine)

        try:
            engine.sync_reconciled_ib_virtual_position_legs()
        except RuntimeError:
            pass
        else:
            raise AssertionError("BLOCKED snapshot was persisted")

        state_after_blocked = _virtual_leg_state(engine)

        if state_after_blocked != state_before_blocked:
            raise AssertionError("BLOCKED sync changed virtual-leg tables")

        cash_fx_event_evidence = _build_cash_fx_stop_event_evidence()
        service.snapshot = cash_fx_event_evidence
        cash_fx_event_result = engine.sync_reconciled_ib_virtual_position_legs()
        cash_fx_event_snapshot = cash_fx_event_result["snapshot"]
        cash_fx_event_leg = cash_fx_event_snapshot.legs[0]

        if cash_fx_event_snapshot.group_statuses[eurusd_id] != (
            IB_RECONCILIATION_STATUS_RECONCILED
        ):
            raise AssertionError("CASH FX stop event was not reconciled")

        if cash_fx_event_leg.leg_status != IB_LEG_STATUS_CLOSED:
            raise AssertionError("CASH FX stop event did not close the leg")

        if cash_fx_event_leg.stop_loss_order_id != 116:
            raise AssertionError("CASH FX stop event order mapping mismatch")

        event_open_seeds = engine.repository.get_open_ib_virtual_position_leg_seeds(
            account_id=ACCOUNT_ID,
        )

        if event_open_seeds:
            raise AssertionError("Closed CASH FX leg remained an open seed")

        print("RuntimeEngine IB virtual-leg result")
        print(f"  complete={snapshot.complete}")
        print(f"  legs={len(snapshot.legs)}")
        print(f"  open_legs={len(open_legs)}")
        print(f"  closed_legs={len(closed_legs)}")
        print(f"  eurusd_status={snapshot.group_statuses[eurusd_id]}")
        print(f"  gbpusd_status={snapshot.group_statuses[gbpusd_id]}")
        print(f"  remaining_parent_id={remaining_leg.parent_order_id}")
        print(f"  service_calls={service.evidence_calls}")
        print("  sqlite_read_only=True")
        print("  persisted_legs=" f"{persisted_counts['ib_virtual_position_legs']}")
        print(
            "  persisted_order_history="
            f"{persisted_counts['ib_virtual_position_leg_orders']}"
        )
        print(f"  active_order_mappings={active_order_count}")
        print("  repeat_sync_legs=" f"{repeat_result['persistence']['legs_written']}")
        print("  blocked_sync_rejected=True")
        print("  orphan_status=" f"{orphan_snapshot.group_statuses[eurusd_id]}")
        print(
            "  foreign_client_status="
            f"{foreign_client_snapshot.group_statuses[gbpusd_id]}"
        )
        print("  completed_total_quantity_zero=True")
        print(
            "  cash_fx_event_status="
            f"{cash_fx_event_snapshot.group_statuses[eurusd_id]}"
        )
        print(f"  cash_fx_event_leg={cash_fx_event_leg.leg_status}")
        print(f"  cash_fx_event_open_seeds={len(event_open_seeds)}")
        print("RUNTIME_ENGINE_IB_VIRTUAL_LEGS_CHECK=OK")
        return 0
    finally:
        engine.connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
