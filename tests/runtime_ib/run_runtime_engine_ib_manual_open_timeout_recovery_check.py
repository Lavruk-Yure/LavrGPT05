"""RoadMap91 delayed IB manual Open automatic recovery check."""

from __future__ import annotations

import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ib_order_errors import (
    IBManualOpenConfirmationPendingError,
    IBMarketOrderTimeoutError,
)
from engine.runtime_account_state import RuntimeAccountState
from engine.runtime_broker_health import RuntimeBrokerHealth
from engine.runtime_engine import IBRuntimeServiceProtocol, RuntimeEngine

ACCOUNT_ID = "DUM513747"
SYMBOL_NAME = "USDZAR"
SIDE = "SELL"
QUANTITY = 2000.0
ORDER_ID = 160
PRICE = 16.45209867
CURRENT_CLIENT_ID = 1
POSITION_ID = f"IB:{ACCOUNT_ID}:{SYMBOL_NAME}"


class DelayedOpenService(IBRuntimeServiceProtocol):
    """Synthetic service exposing delayed exact Open evidence."""

    def __init__(
        self,
        *,
        evidence_order_ids: tuple[int, ...] = (),
    ) -> None:
        self.evidence_order_ids = tuple(evidence_order_ids)
        self.place_calls = 0
        self.evidence_calls = 0

    @staticmethod
    def _unexpected(method_name: str) -> NoReturn:
        raise AssertionError(f"Unexpected service call: {method_name}")

    def connect_demo(self) -> object | None:
        self._unexpected("connect_demo")

    def disconnect(self) -> None:
        return None

    def get_broker_health(self) -> RuntimeBrokerHealth:
        self._unexpected("get_broker_health")

    def get_account_state(self) -> RuntimeAccountState:
        return RuntimeAccountState(
            account_id=ACCOUNT_ID,
            broker_name="IB",
            currency="USD",
        )

    def reconnect(self) -> object | None:
        self._unexpected("reconnect")

    def get_positions(self) -> list:
        return []

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict:
        if (
            symbol_name != SYMBOL_NAME
            or side != SIDE
            or quantity != QUANTITY
            or stop_loss is not None
            or take_profit is not None
        ):
            raise AssertionError("Delayed Open placement context differs")

        self.place_calls += 1
        raise IBMarketOrderTimeoutError(
            order_id=ORDER_ID,
            symbol_name=SYMBOL_NAME,
            side=SIDE,
            quantity=QUANTITY,
            status="SUBMITTED",
            filled=0.0,
            remaining=QUANTITY,
            current_client_id=CURRENT_CLIENT_ID,
            comment=comment,
        )

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict:
        del position_id, quantity, comment
        self._unexpected("close_position")

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        del position_id, stop_loss, take_profit
        self._unexpected("modify_position_sl_tp")

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
        self._unexpected("modify_virtual_position_leg_sl_tp")

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
        self._unexpected("close_virtual_position_leg")

    def get_virtual_position_leg_evidence_snapshot(self) -> dict[str, Any]:
        self.evidence_calls += 1
        return deepcopy(_evidence(self.evidence_order_ids))


def _execution(order_id: int) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "perm_id": order_id + 10000,
        "account": ACCOUNT_ID,
        "symbol": "USD",
        "currency": "ZAR",
        "sec_type": "CASH",
        "symbol_name": SYMBOL_NAME,
        "broker_position_id": POSITION_ID,
        "side": "SLD",
        "shares": QUANTITY,
        "price": PRICE + ((order_id - ORDER_ID) * 0.0001),
        "time": "20260721 14:23:00 UTC",
    }


def _evidence(order_ids: tuple[int, ...]) -> dict[str, Any]:
    return {
        "broker": "IB",
        "captured_utc": "2026-07-21T14:23:01+00:00",
        "current_client_id": CURRENT_CLIENT_ID,
        "complete": True,
        "positions_complete": True,
        "open_orders_complete": True,
        "completed_orders_complete": True,
        "executions_complete": True,
        "account_ids": [ACCOUNT_ID],
        "positions": [
            {
                "account_id": ACCOUNT_ID,
                "broker_position_id": POSITION_ID,
                "symbol_name": SYMBOL_NAME,
                "symbol": "USD",
                "currency": "ZAR",
                "sec_type": "CASH",
                "signed_quantity": -QUANTITY,
                "side": SIDE,
                "volume": QUANTITY,
                "average_cost": PRICE,
            }
        ],
        "open_orders": [],
        "completed_orders": [
            {
                "order_id": order_id,
                "account": ACCOUNT_ID,
                "symbol": "USD",
                "currency": "ZAR",
                "sec_type": "CASH",
                "symbol_name": SYMBOL_NAME,
                "broker_position_id": POSITION_ID,
                "action": SIDE,
                "order_type": "MKT",
                "total_quantity": QUANTITY,
                "client_id": CURRENT_CLIENT_ID,
                "same_client_id": True,
                "order_ref": "LGE manual UI order",
                "status": "Filled",
                "completed_status": "Filled",
                "filled": QUANTITY,
                "remaining": 0.0,
            }
            for order_id in order_ids
        ],
        "executions": [_execution(order_id) for order_id in order_ids],
    }


def _new_engine(db_path: Path, service: DelayedOpenService) -> RuntimeEngine:
    engine = RuntimeEngine(db_path=str(db_path))
    engine.ib_runtime_service = service
    engine.context.broker = "IB"
    engine.context.account_mode = "DEMO"
    return engine


def _assert_open_leg(engine: RuntimeEngine) -> str:
    seeds = engine.repository.get_open_ib_virtual_position_leg_seeds(
        account_id=ACCOUNT_ID,
    )

    if len(seeds) != 1:
        raise AssertionError("Recovered delayed Open seed count differs")

    seed = seeds[0]

    if seed["logical_side"] != SIDE or seed["logical_volume"] != QUANTITY:
        raise AssertionError("Recovered delayed Open logical identity differs")

    if int(seed["parent_order_id"]) != ORDER_ID:
        raise AssertionError("Recovered delayed Open parent ID differs")

    if seed["persisted_leg_status"] != "OPEN":
        raise AssertionError("Recovered delayed Open leg is not OPEN")

    return str(seed["position_uid"])


def _check_immediate_recovery() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "immediate.db"
        service = DelayedOpenService(evidence_order_ids=(ORDER_ID,))
        engine = _new_engine(db_path, service)

        with patch(
            "engine.runtime_engine.IB_MANUAL_OPEN_TIMEOUT_RECOVERY_DELAY_SECONDS",
            0.0,
        ):
            result = engine.place_manual_market_order(
                symbol_name=SYMBOL_NAME,
                side=SIDE,
                lots=0.02,
                comment="Delayed Open immediate recovery",
            )

        position_uid = _assert_open_leg(engine)

        if result.get("position_uid") != position_uid:
            raise AssertionError("Immediate recovery position UID differs")

        if not result.get("automatic_timeout_recovery"):
            raise AssertionError("Immediate recovery flag differs")

        if service.place_calls != 1:
            raise AssertionError("Immediate recovery duplicated broker Open")

        if engine.repository.get_pending_ib_manual_opens():
            raise AssertionError("Immediate recovery remained pending")

        engine.connection.close()


def _check_restart_recovery_and_duplicate_guard() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "restart.db"
        first_service = DelayedOpenService(evidence_order_ids=())
        first_engine = _new_engine(db_path, first_service)

        with patch(
            "engine.runtime_engine.IB_MANUAL_OPEN_TIMEOUT_RECOVERY_ATTEMPTS",
            1,
        ), patch(
            "engine.runtime_engine.IB_MANUAL_OPEN_TIMEOUT_RECOVERY_DELAY_SECONDS",
            0.0,
        ):
            try:
                first_engine.place_manual_market_order(
                    symbol_name=SYMBOL_NAME,
                    side=SIDE,
                    lots=0.02,
                    comment="Delayed Open restart recovery",
                )
            except IBManualOpenConfirmationPendingError as error:
                if error.order_id != ORDER_ID:
                    raise AssertionError("Pending Open order ID differs") from error
            else:
                raise AssertionError("Unconfirmed delayed Open did not stay pending")

            try:
                first_engine.place_manual_market_order(
                    symbol_name=SYMBOL_NAME,
                    side=SIDE,
                    lots=0.02,
                    comment="Forbidden duplicate Open",
                )
            except IBManualOpenConfirmationPendingError:
                pass
            else:
                raise AssertionError("Duplicate Open was not blocked")

        if first_service.place_calls != 1:
            raise AssertionError("Pending Open guard sent duplicate broker order")

        if len(first_engine.repository.get_pending_ib_manual_opens()) != 1:
            raise AssertionError("Delayed Open pending row was not saved")

        first_engine.connection.close()
        restart_service = DelayedOpenService(evidence_order_ids=(ORDER_ID,))
        restart_engine = _new_engine(db_path, restart_service)
        recovery = restart_engine.recover_pending_ib_manual_market_order_opens()

        if recovery["recovered"] != [ORDER_ID]:
            raise AssertionError("Restart recovery order IDs differ")

        _assert_open_leg(restart_engine)

        if restart_service.place_calls != 0:
            raise AssertionError("Restart recovery sent a broker Open")

        restart_engine.connection.close()


def _check_legacy_orphan_recovery_and_ambiguity_guard() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "legacy.db"
        service = DelayedOpenService(evidence_order_ids=(ORDER_ID,))
        engine = _new_engine(db_path, service)
        trade_uid = engine.repository.create_trade(
            broker="IB",
            account_id=ACCOUNT_ID,
            symbol=SYMBOL_NAME,
            side=SIDE,
            volume=QUANTITY,
            source="MANUAL",
        )
        engine.repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side=SIDE,
            volume=QUANTITY,
            source="MANUAL",
        )
        recovery = engine.recover_pending_ib_manual_market_order_opens()

        if recovery["adopted"] != [ORDER_ID]:
            raise AssertionError("Legacy delayed Open was not adopted")

        if recovery["recovered"] != [ORDER_ID]:
            raise AssertionError("Legacy delayed Open was not recovered")

        _assert_open_leg(engine)
        engine.connection.close()

    with tempfile.TemporaryDirectory() as temporary_directory:
        db_path = Path(temporary_directory) / "ambiguous.db"
        service = DelayedOpenService(
            evidence_order_ids=(ORDER_ID, ORDER_ID + 1),
        )
        engine = _new_engine(db_path, service)
        trade_uid = engine.repository.create_trade(
            broker="IB",
            account_id=ACCOUNT_ID,
            symbol=SYMBOL_NAME,
            side=SIDE,
            volume=QUANTITY,
            source="MANUAL",
        )
        engine.repository.create_order_plan(
            trade_uid=trade_uid,
            order_type="MARKET",
            side=SIDE,
            volume=QUANTITY,
            source="MANUAL",
        )
        recovery = engine.recover_pending_ib_manual_market_order_opens()

        if recovery["adopted"] or recovery["recovered"]:
            raise AssertionError("Ambiguous legacy Open was adopted")

        if len(engine.repository.get_orphan_ib_manual_market_order_plans()) != 1:
            raise AssertionError("Ambiguous legacy Open did not remain blocked")

        engine.connection.close()


def main() -> int:
    _check_immediate_recovery()
    _check_restart_recovery_and_duplicate_guard()
    _check_legacy_orphan_recovery_and_ambiguity_guard()

    print("RuntimeEngine IB manual Open timeout recovery result")
    print("  timeout_open_auto_recovered=True")
    print("  timeout_open_pending_saved=True")
    print("  duplicate_open_calls=0")
    print("  timeout_open_restart_recovered=True")
    print("  legacy_orphan_open_adopted=True")
    print("  ambiguous_legacy_open_blocked=True")
    print("RUNTIME_ENGINE_IB_MANUAL_OPEN_TIMEOUT_RECOVERY_CHECK=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
