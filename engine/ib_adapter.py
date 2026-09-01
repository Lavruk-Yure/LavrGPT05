# ib_adapter.py
"""
IB runtime adapter.

RoadMap67+:
- runtime connection lifecycle foundation;
- account summary and order execution;
- no UI dependency;
- streaming Forex quote cache for active virtual legs.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.execution import ExecutionFilter
from ibapi.order import Order
from ibapi.order_cancel import OrderCancel
from ibapi.wrapper import EWrapper

from engine.broker_account import BrokerAccount
from engine.broker_interface import BrokerInterface
from engine.broker_order_identity import (
    ORDER_CONTROL_MODE_MANUAL,
    build_broker_order_comment,
    get_broker_order_control_mode,
    strip_broker_order_identity,
)
from engine.broker_position import (
    POSITION_SIDE_BUY,
    POSITION_SIDE_SELL,
    BrokerPosition,
)
from engine.ib_history import (
    IBHistoricalBar,
    IBHistoryDownloadResult,
    IBHistoryProgressCallback,
    decode_ib_historical_bar,
    format_ib_historical_end_datetime,
    is_ib_historical_no_data_error,
)
from engine.ib_order_errors import IBMarketOrderTimeoutError
from engine.runtime_constants import (
    IB_ACCOUNT_SUMMARY_TIMEOUT_SECONDS,
    IB_COMPLETED_ORDERS_TIMEOUT_SECONDS,
    IB_CONNECT_TIMEOUT_SECONDS,
    IB_EXECUTIONS_TIMEOUT_SECONDS,
    IB_HISTORY_BAR_SECONDS_BY_TIMEFRAME,
    IB_HISTORY_BAR_SIZE_BY_TIMEFRAME,
    IB_HISTORY_DURATION_BY_TIMEFRAME,
    IB_HISTORY_EMPTY_CHUNK_SECONDS_BY_TIMEFRAME,
    IB_HISTORY_MAX_CONSECUTIVE_EMPTY_REQUESTS,
    IB_HISTORY_MAX_REQUESTS,
    IB_HISTORY_REQUEST_DELAY_SECONDS,
    IB_HISTORY_TIMEOUT_SECONDS,
    IB_MARKET_DATA_TIMEOUT_SECONDS,
    IB_OPEN_ORDER_TERMINAL_STATUSES,
    IB_OPEN_ORDERS_TIMEOUT_SECONDS,
    IB_ORDER_TIMEOUT_SECONDS,
    IB_PNL_TIMEOUT_SECONDS,
    IB_PORTFOLIO_TIMEOUT_SECONDS,
    IB_POSITION_QUANTITY_ABS_TOLERANCE,
    IB_POSITIONS_TIMEOUT_SECONDS,
    IB_SL_TP_COVERAGE_ABS_TOLERANCE,
    IB_SL_TP_COVERAGE_REL_TOLERANCE,
    IB_SL_TP_OCA_GROUP_PREFIX,
    IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK,
    IB_SL_TP_OPERATION_ACCEPTED_STATUSES,
    IB_SL_TP_OPERATION_CANCELLED_STATUSES,
    IB_SL_TP_OPERATION_FAILURE_STATUSES,
    IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    IB_SL_TP_ORDER_REF,
    IB_SL_TP_REPLACEMENT_STAGE_SETTLE_SECONDS,
    IB_THREAD_JOIN_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

ACCOUNT_SUMMARY_TAGS = (
    "NetLiquidation," "TotalCashValue," "AvailableFunds," "MaintMarginReq"
)
IB_PROTECTION_ACTION_KEEP = "KEEP"
IB_PROTECTION_ACTION_MODIFY = "MODIFY"
IB_PROTECTION_ACTION_CANCEL = "CANCEL"
IB_PROTECTION_ACTION_CREATE = "CREATE"
IB_PROTECTION_ACTION_BLOCK = "BLOCK"


def _to_float(value: str) -> float:
    """
    Безпечно перетворити IB string value у float.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class _IBWrapper(EWrapper):
    """
    Minimal IB wrapper for runtime lifecycle and account summary.
    """

    def __init__(self, logger: logging.Logger) -> None:  # noqa
        super().__init__()
        self._logger = logger

        self.state_callback: Callable[[str], None] | None = None

        self.connected_event = threading.Event()
        self.account_summary_event = threading.Event()

        self.position_event = threading.Event()
        self.positions: list[dict[str, Any]] = []

        self.portfolio_event = threading.Event()
        self.portfolio_rows: list[dict[str, Any]] = []

        self.pnl_single_event = threading.Event()
        self.pnl_single_rows: dict[int, dict[str, Any]] = {}

        self.order_event = threading.Event()
        self.open_orders_event = threading.Event()
        self.active_order_id: int | None = None
        self.active_order_ids: set[int] = set()
        self.open_orders: list[dict[str, Any]] = []
        self.open_order_objects: dict[int, dict[str, Any]] = {}

        self.order_statuses: list[dict[str, Any]] = []

        self.sl_tp_operation_lock = threading.RLock()
        self.sl_tp_operation_event = threading.Event()
        self.sl_tp_operation_order_ids: set[int] = set()

        self.sl_tp_operation_open_orders: dict[
            int,
            dict[str, Any],
        ] = {}

        self.sl_tp_operation_statuses: dict[
            int,
            dict[str, Any],
        ] = {}

        self.sl_tp_operation_cancelled_order_ids: set[int] = set()

        self.sl_tp_operation_errors: dict[
            int,
            list[str],
        ] = {}

        self.execution_event = threading.Event()
        self.executions: list[dict[str, Any]] = []

        self.completed_orders_event = threading.Event()
        self.completed_orders: list[dict[str, Any]] = []

        self.order_errors: list[str] = []

        self.next_valid_id: int | None = None
        self.account_id: str = ""
        self.account_values: dict[str, dict[str, str]] = {}
        self.managed_accounts: list[str] = []

        self.market_data_lock = threading.RLock()
        self.market_data_event = threading.Event()
        self.market_data_symbol_by_req_id: dict[int, str] = {}
        self.market_data_quotes: dict[str, dict[str, Any]] = {}

        self.historical_data_lock = threading.RLock()
        self.historical_data_event = threading.Event()
        self.historical_data_req_id: int | None = None
        self.historical_data_bars: list[object] = []
        self.historical_data_error: str = ""

    def register_market_data_request(
        self,
        req_id: int,
        symbol_name: str,
    ) -> None:
        """Register one streaming market-data request."""
        req_id_value = int(req_id)
        symbol = str(symbol_name or "").strip().upper()

        if req_id_value <= 0 or not symbol:
            raise ValueError("IB market-data request identity is incomplete")

        with self.market_data_lock:
            self.market_data_symbol_by_req_id[req_id_value] = symbol
            self.market_data_quotes.setdefault(
                symbol,
                {
                    "symbol_name": symbol,
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "close": None,
                    "market_data_type": None,
                    "timestamp": "",
                    "error_code": None,
                    "error_message": "",
                },
            )

    def unregister_market_data_request(self, req_id: int) -> None:
        """Forget one cancelled streaming market-data request."""
        with self.market_data_lock:
            symbol = self.market_data_symbol_by_req_id.pop(
                int(req_id),
                None,
            )

            if symbol:
                self.market_data_quotes.pop(symbol, None)

    def clear_market_data_requests(self) -> None:
        """Clear request identities while retaining no stale quotes."""
        with self.market_data_lock:
            self.market_data_symbol_by_req_id.clear()
            self.market_data_quotes.clear()
            self.market_data_event.clear()

    def is_market_data_request(self, req_id: int) -> bool:
        """Return whether req_id belongs to the quote cache."""
        with self.market_data_lock:
            return int(req_id) in self.market_data_symbol_by_req_id

    def get_market_data_snapshot(
        self,
        symbol_names: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Return independent quote rows for requested symbols."""
        result: dict[str, dict[str, Any]] = {}

        with self.market_data_lock:
            for symbol_name in symbol_names:
                symbol = str(symbol_name or "").strip().upper()
                row = self.market_data_quotes.get(symbol)

                if row is not None:
                    result[symbol] = dict(row)

        return result

    def start_historical_data_request(self, req_id: int) -> None:
        """Reset callback state for one synchronous historical request."""
        request_id = int(req_id)
        if request_id <= 0:
            raise ValueError("IB historical request id must be positive")
        with self.historical_data_lock:
            self.historical_data_event.clear()
            self.historical_data_req_id = request_id
            self.historical_data_bars.clear()
            self.historical_data_error = ""

    def get_historical_data_snapshot(self) -> tuple[list[object], str]:
        """Return independent callback data for the active request."""
        with self.historical_data_lock:
            return list(self.historical_data_bars), self.historical_data_error

    def clear_historical_data_request(self) -> None:
        """Clear request identity and callback data after completion."""
        with self.historical_data_lock:
            self.historical_data_req_id = None
            self.historical_data_bars.clear()
            self.historical_data_error = ""
            self.historical_data_event.clear()

    def start_sl_tp_operation(
        self,
        order_ids: set[int],
    ) -> None:
        """
        Почати окрему IB SL/TP execution operation.
        """
        normalized_order_ids: set[int] = set()

        for value in order_ids:
            try:
                order_id = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid IB SL/TP operation order id: {value}"
                ) from exc

            if order_id <= 0:
                raise ValueError(f"Invalid IB SL/TP operation order id: {order_id}")

            normalized_order_ids.add(order_id)

        if not normalized_order_ids:
            raise ValueError("IB SL/TP operation order ids are empty")

        with self.sl_tp_operation_lock:
            self.sl_tp_operation_event.clear()

            self.sl_tp_operation_order_ids = set(normalized_order_ids)

            self.sl_tp_operation_open_orders.clear()
            self.sl_tp_operation_statuses.clear()
            self.sl_tp_operation_cancelled_order_ids.clear()
            self.sl_tp_operation_errors.clear()

    def get_sl_tp_operation_snapshot(
        self,
    ) -> dict[str, Any]:
        """
        Отримати незалежну копію поточного SL/TP operation state.
        """
        with self.sl_tp_operation_lock:
            return {
                "order_ids": set(self.sl_tp_operation_order_ids),
                "open_orders": {
                    order_id: dict(row)
                    for order_id, row in self.sl_tp_operation_open_orders.items()
                },
                "statuses": {
                    order_id: dict(row)
                    for order_id, row in self.sl_tp_operation_statuses.items()
                },
                "cancelled_order_ids": set(self.sl_tp_operation_cancelled_order_ids),
                "errors": {
                    order_id: list(messages)
                    for order_id, messages in self.sl_tp_operation_errors.items()
                },
            }

    def clear_sl_tp_operation(self) -> None:
        """
        Очистити SL/TP operation state після завершення.
        """
        with self.sl_tp_operation_lock:
            self.sl_tp_operation_order_ids.clear()
            self.sl_tp_operation_open_orders.clear()
            self.sl_tp_operation_statuses.clear()
            self.sl_tp_operation_cancelled_order_ids.clear()
            self.sl_tp_operation_errors.clear()
            self.sl_tp_operation_event.clear()

    def nextValidId(self, orderId: int) -> None:  # noqa
        """
        IB connection confirmation callback.
        """
        self.next_valid_id = orderId
        self.connected_event.set()
        self._logger.info("IB nextValidId received | orderId=%s", orderId)

    def accountSummary(  # noqa
        self,
        reqId: int,  # noqa
        account: str,
        tag: str,
        value: str,
        currency: str,
    ) -> None:
        """
        IB account summary callback.
        """
        if not self.account_id:
            self.account_id = account

        self.account_values[tag] = {
            "account": account,
            "value": value,
            "currency": currency,
        }

        self._logger.info(
            "IB accountSummary | reqId=%s | account=%s | tag=%s | "
            "value=%s | currency=%s",
            reqId,
            account,
            tag,
            value,
            currency,
        )

    def accountSummaryEnd(self, reqId: int) -> None:  # noqa
        """
        IB account summary end callback.
        """
        self._logger.info("IB accountSummaryEnd | reqId=%s", reqId)
        self.account_summary_event.set()

    def position(  # noqa: N802
        self,
        account: str,
        contract,
        position: float,
        avg_cost: float,  # noqa: N803
    ) -> None:
        """
        IB position callback.
        """

        item = {
            "account": account,
            "contract": contract,
            "position": position,
            "avg_cost": avg_cost,
        }
        self.positions.append(item)

        self._logger.info(
            "IB position | account=%s | symbol=%s | secType=%s | "
            "currency=%s | exchange=%s | position=%s | avg_cost=%s",
            account,
            getattr(contract, "symbol", ""),
            getattr(contract, "secType", ""),
            getattr(contract, "currency", ""),
            getattr(contract, "exchange", ""),
            position,
            avg_cost,
        )

    def positionEnd(self) -> None:  # noqa: N802
        """
        IB positions end callback.
        """

        self._logger.info("IB positionEnd received.")
        self.position_event.set()

    def updatePortfolio(  # noqa: N802
        self,
        contract,
        position,
        market_price,
        market_value,
        average_cost,
        unrealized_pnl,
        realized_pnl,
        account_name,
    ) -> None:
        """
        IB portfolio callback with broker-provided market price and PnL.
        """

        item = {
            "account": str(account_name or ""),
            "contract": contract,
            "position": float(position or 0.0),
            "market_price": float(market_price or 0.0),
            "market_value": float(market_value or 0.0),
            "average_cost": float(average_cost or 0.0),
            "unrealized_pnl": float(unrealized_pnl or 0.0),
            "realized_pnl": float(realized_pnl or 0.0),
        }
        self.portfolio_rows.append(item)

        self._logger.info(
            "IB updatePortfolio | account=%s | symbol=%s | secType=%s | "
            "currency=%s | position=%s | marketPrice=%s | "
            "averageCost=%s | unrealizedPNL=%s",
            item["account"],
            getattr(contract, "symbol", ""),
            getattr(contract, "secType", ""),
            getattr(contract, "currency", ""),
            item["position"],
            item["market_price"],
            item["average_cost"],
            item["unrealized_pnl"],
        )

    def accountDownloadEnd(self, account_name: str) -> None:  # noqa: N802
        """
        IB account update snapshot end callback.
        """

        self._logger.info("IB accountDownloadEnd | account=%s", account_name)
        self.portfolio_event.set()

    def pnlSingle(  # noqa: N802
        self,
        req_id: int,
        pos: float,
        daily_pnl: float,
        unrealized_pnl: float,
        realized_pnl: float,
        value: float,
    ) -> None:
        """
        IB single-position PnL callback.

        Це broker-provided PnL, не ручний розрахунок.
        """
        item = {
            "position": self._clean_ib_float(pos) or 0.0,
            "daily_pnl": self._clean_ib_float(daily_pnl),
            "unrealized_pnl": self._clean_ib_float(unrealized_pnl),
            "realized_pnl": self._clean_ib_float(realized_pnl),
            "value": self._clean_ib_float(value),
        }

        self.pnl_single_rows[int(req_id)] = item

        self._logger.info(
            "IB pnlSingle | reqId=%s | position=%s | dailyPnL=%s | "
            "unrealizedPnL=%s | realizedPnL=%s | value=%s",
            req_id,
            item["position"],
            item["daily_pnl"],
            item["unrealized_pnl"],
            item["realized_pnl"],
            item["value"],
        )

        self.pnl_single_event.set()

    @staticmethod
    def _clean_ib_float(
        value,
    ) -> float | None:
        """
        Очистити IB float value.

        IB інколи повертає 1.7976931348623157e+308 як sentinel,
        тобто реального значення немає.
        """
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        if abs(number) >= 1.0e100:
            return None

        return number

    def tickPrice(  # noqa: N802
        self,
        req_id: int,
        tick_type: int,
        price: float,
        attrib,
    ) -> None:
        """Cache live or delayed bid/ask prices for one request."""
        del attrib

        tick_field = {
            1: "bid",
            2: "ask",
            4: "last",
            9: "close",
            66: "bid",
            67: "ask",
            68: "last",
            75: "close",
        }.get(int(tick_type))

        if tick_field is None:
            return

        price_value = self._clean_ib_float(price)

        if price_value is None or price_value <= 0.0:
            return

        req_id_value = int(req_id)

        with self.market_data_lock:
            symbol = self.market_data_symbol_by_req_id.get(req_id_value)

            if not symbol:
                return

            row = self.market_data_quotes.setdefault(
                symbol,
                {
                    "symbol_name": symbol,
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "close": None,
                    "market_data_type": None,
                    "timestamp": "",
                    "error_code": None,
                    "error_message": "",
                },
            )
            row[tick_field] = price_value
            row["timestamp"] = datetime.now(UTC).replace(microsecond=0).isoformat()
            row["delayed"] = int(tick_type) in {66, 67, 68, 75}
            row["error_code"] = None
            row["error_message"] = ""
            self.market_data_event.set()

        self._logger.debug(
            "IB tickPrice | reqId=%s | symbol=%s | field=%s | price=%s",
            req_id_value,
            symbol,
            tick_field,
            price_value,
        )

    def marketDataType(  # noqa: N802
        self,
        req_id: int,
        market_data_type: int,
    ) -> None:
        """Record whether one subscription is live, frozen or delayed."""
        req_id_value = int(req_id)

        with self.market_data_lock:
            symbol = self.market_data_symbol_by_req_id.get(req_id_value)

            if not symbol:
                return

            row = self.market_data_quotes.setdefault(
                symbol,
                {
                    "symbol_name": symbol,
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "close": None,
                    "market_data_type": None,
                    "timestamp": "",
                    "error_code": None,
                    "error_message": "",
                },
            )
            row["market_data_type"] = int(market_data_type)
            self.market_data_event.set()

    def historicalData(self, req_id, bar) -> None:  # noqa: N802
        """Collect one historical bar for the active request."""
        request_id = int(req_id)
        with self.historical_data_lock:
            if request_id != self.historical_data_req_id:
                return
            self.historical_data_bars.append(bar)

    def historicalDataEnd(  # noqa: N802
        self,
        req_id,
        start,
        end,
    ) -> None:
        """Signal completion of one historical-data response."""
        del start, end
        request_id = int(req_id)
        with self.historical_data_lock:
            if request_id != self.historical_data_req_id:
                return
            self.historical_data_event.set()

    def connectionClosed(self) -> None:  # noqa: N802
        """
        Обробити закриття IB API connection.

        Викликається, коли socket до TWS / IB Gateway закритий.
        """

        if self.state_callback is not None:
            self.state_callback("DISCONNECTED")

        self._logger.warning("IB connectionClosed received.")

    def error(  # noqa: N802
        self,
        req_id: int,
        error_time: int,
        error_code: int,
        error_string: str,
        advanced_order_reject_json: str = "",
    ) -> None:
        """
        Обробити IB error/status callback.

        Важливо:
        IB через error callback передає не тільки помилки,
        а й службові connectivity/status events.
        """

        message = (
            "IB MESSAGE | reqId=%s | time=%s | code=%s | " "message=%s | advanced=%s"
        )

        args = (
            req_id,
            error_time,
            error_code,
            error_string,
            advanced_order_reject_json,
        )

        active_order_ids = set(self.active_order_ids)

        if self.active_order_id is not None:
            active_order_ids.add(int(self.active_order_id))

        try:
            req_id_int = int(req_id)
        except (TypeError, ValueError):
            req_id_int = -1

        with self.historical_data_lock:
            if req_id_int == self.historical_data_req_id:
                if error_code not in {2104, 2106, 2158}:
                    self.historical_data_error = (
                        f"IB historical data error {error_code}: " f"{error_string}"
                    )
                    self.historical_data_event.set()

        with self.market_data_lock:
            quote_symbol = self.market_data_symbol_by_req_id.get(req_id_int)

            if quote_symbol:
                row = self.market_data_quotes.setdefault(
                    quote_symbol,
                    {
                        "symbol_name": quote_symbol,
                        "bid": None,
                        "ask": None,
                        "last": None,
                        "close": None,
                        "market_data_type": None,
                        "timestamp": "",
                        "error_code": None,
                        "error_message": "",
                    },
                )
                row["error_code"] = int(error_code)
                row["error_message"] = str(error_string or "").strip()
                self.market_data_event.set()

        with self.sl_tp_operation_lock:
            if req_id_int in self.sl_tp_operation_order_ids:
                if error_code == 202:
                    self.sl_tp_operation_cancelled_order_ids.add(req_id_int)
                elif error_code not in {399, 2109}:
                    error_message = (
                        f"IB SL/TP order error {error_code}: " f"{error_string}"
                    )

                    self.sl_tp_operation_errors.setdefault(
                        req_id_int,
                        [],
                    ).append(error_message)

                self.sl_tp_operation_event.set()

        if req_id_int in active_order_ids and error_code not in {202, 399, 2109}:
            self.order_errors.append(f"IB order error {error_code}: {error_string}")
            self.order_event.set()

        if error_code in {202, 2100, 2104, 2106, 2158, 399, 2109}:
            self._logger.info(message, *args)
            return

        if error_code in {1101, 1102}:
            if self.state_callback is not None:
                self.state_callback("CONNECTED")

            self._logger.info(message, *args)
            return

        if error_code in {1100, 2103, 2105, 2157}:
            if self.state_callback is not None:
                self.state_callback("DEGRADED")

            self._logger.warning(message, *args)
            return

        self._logger.error(message, *args)

    def openOrder(self, orderId, contract, order, orderState) -> None:  # noqa
        """
        IB openOrder callback.
        """

        order_id = int(orderId)

        item = {
            "order_id": order_id,
            "account": str(getattr(order, "account", "") or ""),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "sec_type": str(getattr(contract, "secType", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "action": str(getattr(order, "action", "") or ""),
            "order_type": str(getattr(order, "orderType", "") or ""),
            "total_quantity": float(getattr(order, "totalQuantity", 0.0) or 0.0),
            "lmt_price": float(getattr(order, "lmtPrice", 0.0) or 0.0),
            "aux_price": float(getattr(order, "auxPrice", 0.0) or 0.0),
            "parent_id": int(getattr(order, "parentId", 0) or 0),
            "client_id": int(getattr(order, "clientId", 0) or 0),
            "perm_id": int(getattr(order, "permId", 0) or 0),
            "order_ref": str(getattr(order, "orderRef", "") or ""),
            "display_order_ref": strip_broker_order_identity(
                getattr(order, "orderRef", ""),
            ),
            "order_control_mode": get_broker_order_control_mode(
                getattr(order, "orderRef", ""),
            ),
            "tif": str(getattr(order, "tif", "") or ""),
            "transmit": bool(getattr(order, "transmit", False)),
            "oca_group": str(getattr(order, "ocaGroup", "") or ""),
            "oca_type": int(getattr(order, "ocaType", 0) or 0),
            "status": str(getattr(orderState, "status", "") or ""),
        }

        self.open_order_objects[order_id] = {
            "contract_object": contract,
            "order_object": order,
        }

        self.open_orders.append(item)

        with self.sl_tp_operation_lock:
            if order_id in self.sl_tp_operation_order_ids:
                self.sl_tp_operation_open_orders[order_id] = dict(item)

                self.sl_tp_operation_event.set()

        self._logger.info(
            "IB openOrder | orderId=%s | account=%s | symbol=%s.%s | "
            "action=%s | type=%s | qty=%s | lmt=%s | aux=%s | "
            "parentId=%s | clientId=%s | permId=%s | "
            "orderRef=%s | status=%s",
            item["order_id"],
            item["account"],
            item["symbol"],
            item["currency"],
            item["action"],
            item["order_type"],
            item["total_quantity"],
            item["lmt_price"],
            item["aux_price"],
            item["parent_id"],
            item["client_id"],
            item["perm_id"],
            item["order_ref"],
            item["status"],
        )

    def openOrderEnd(self) -> None:  # noqa: N802
        """
        IB open orders snapshot end callback.
        """
        self._logger.info("IB openOrderEnd received.")
        self.open_orders_event.set()

    def execDetails(  # noqa: N802
        self,
        req_id: int,
        contract,
        execution,
    ) -> None:
        """
        IB execution callback.

        Використовується для часу manual TWS positions.
        """
        item = {
            "req_id": int(req_id),
            "account": str(getattr(execution, "acctNumber", "") or ""),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "sec_type": str(getattr(contract, "secType", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "side": str(getattr(execution, "side", "") or ""),
            "shares": float(getattr(execution, "shares", 0.0) or 0.0),
            "price": float(getattr(execution, "price", 0.0) or 0.0),
            "time": str(getattr(execution, "time", "") or ""),
            "order_id": int(getattr(execution, "orderId", 0) or 0),
            "perm_id": int(getattr(execution, "permId", 0) or 0),
        }

        self.executions.append(item)

        self._logger.info(
            "IB execDetails | reqId=%s | account=%s | symbol=%s.%s | "
            "side=%s | shares=%s | price=%s | time=%s | orderId=%s",
            item["req_id"],
            item["account"],
            item["symbol"],
            item["currency"],
            item["side"],
            item["shares"],
            item["price"],
            item["time"],
            item["order_id"],
        )

    def execDetailsEnd(  # noqa: N802
        self,
        req_id: int,
    ) -> None:
        """
        IB executions snapshot end callback.
        """
        self._logger.info("IB execDetailsEnd received. reqId=%s", req_id)
        self.execution_event.set()

    def completedOrder(self, *args) -> None:  # noqa: N802
        """
        IB completedOrder callback.

        Підтримує обидва Python API callback layouts:
        - completedOrder(contract, order, orderState);
        - completedOrder(orderId, contract, order, orderState).
        """
        if len(args) == 3:
            contract, order, order_state = args
            order_id = int(getattr(order, "orderId", 0) or 0)
        elif len(args) == 4:
            raw_order_id, contract, order, order_state = args
            order_id = int(raw_order_id or getattr(order, "orderId", 0) or 0)
        else:
            self._logger.error(
                "Unexpected IB completedOrder callback args: %s",
                len(args),
            )
            return

        item = {
            "order_id": order_id,
            "account": str(getattr(order, "account", "") or ""),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "sec_type": str(getattr(contract, "secType", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "con_id": int(getattr(contract, "conId", 0) or 0),
            "action": str(getattr(order, "action", "") or ""),
            "order_type": str(getattr(order, "orderType", "") or ""),
            "total_quantity": float(getattr(order, "totalQuantity", 0.0) or 0.0),
            "lmt_price": float(getattr(order, "lmtPrice", 0.0) or 0.0),
            "aux_price": float(getattr(order, "auxPrice", 0.0) or 0.0),
            "parent_id": int(getattr(order, "parentId", 0) or 0),
            "client_id": int(getattr(order, "clientId", 0) or 0),
            "perm_id": int(getattr(order, "permId", 0) or 0),
            "order_ref": str(getattr(order, "orderRef", "") or ""),
            "display_order_ref": strip_broker_order_identity(
                getattr(order, "orderRef", ""),
            ),
            "order_control_mode": get_broker_order_control_mode(
                getattr(order, "orderRef", ""),
            ),
            "tif": str(getattr(order, "tif", "") or ""),
            "oca_group": str(getattr(order, "ocaGroup", "") or ""),
            "oca_type": int(getattr(order, "ocaType", 0) or 0),
            "status": str(getattr(order_state, "status", "") or ""),
            "completed_status": str(getattr(order_state, "completedStatus", "") or ""),
            "completed_time": str(getattr(order_state, "completedTime", "") or ""),
            "filled": float(getattr(order_state, "filled", 0.0) or 0.0),
            "remaining": float(getattr(order_state, "remaining", 0.0) or 0.0),
            "avg_fill_price": float(getattr(order_state, "avgFillPrice", 0.0) or 0.0),
            "last_fill_price": float(getattr(order_state, "lastFillPrice", 0.0) or 0.0),
            "why_held": str(getattr(order_state, "whyHeld", "") or ""),
        }

        self.completed_orders.append(item)

        self._logger.info(
            "IB completedOrder | orderId=%s | account=%s | "
            "symbol=%s.%s | action=%s | type=%s | qty=%s | "
            "parentId=%s | clientId=%s | permId=%s | "
            "status=%s | completedStatus=%s | completedTime=%s",
            item["order_id"],
            item["account"],
            item["symbol"],
            item["currency"],
            item["action"],
            item["order_type"],
            item["total_quantity"],
            item["parent_id"],
            item["client_id"],
            item["perm_id"],
            item["status"],
            item["completed_status"],
            item["completed_time"],
        )

    def completedOrdersEnd(self) -> None:  # noqa: N802
        """
        IB completed-orders snapshot end callback.
        """
        self._logger.info("IB completedOrdersEnd received.")
        self.completed_orders_event.set()

    def orderStatus(  # noqa: N802
        self,
        order_id,
        status,
        filled,
        remaining,
        avg_fill_price,
        perm_id,
        parent_id,
        last_fill_price,
        client_id,
        why_held,
        mkt_cap_price,
    ) -> None:
        """
        IB orderStatus callback.
        """
        item = {
            "order_id": int(order_id),
            "status": str(status or ""),
            "filled": float(filled or 0.0),
            "remaining": float(remaining or 0.0),
            "avg_fill_price": float(avg_fill_price or 0.0),
            "perm_id": int(perm_id or 0),
            "parent_id": int(parent_id or 0),
            "last_fill_price": float(last_fill_price or 0.0),
            "client_id": int(client_id or 0),
            "why_held": str(why_held or ""),
            "mkt_cap_price": float(mkt_cap_price or 0.0),
        }
        self.order_statuses.append(item)

        operation_order_id = item["order_id"]

        with self.sl_tp_operation_lock:
            if operation_order_id in self.sl_tp_operation_order_ids:
                self.sl_tp_operation_statuses[operation_order_id] = dict(item)

                operation_status = str(item.get("status") or "").strip().upper()

                if operation_status in {
                    "CANCELLED",
                    "APICANCELLED",
                }:
                    self.sl_tp_operation_cancelled_order_ids.add(operation_order_id)

                self.sl_tp_operation_event.set()

        self._logger.info(
            "IB orderStatus | orderId=%s | status=%s | filled=%s | "
            "remaining=%s | avgFillPrice=%s",
            item["order_id"],
            item["status"],
            item["filled"],
            item["remaining"],
            item["avg_fill_price"],
        )

        terminal_statuses = {
            "FILLED",
            "CANCELLED",
            "API CANCELLED",
            "INACTIVE",
        }

        active_order_ids = set(self.active_order_ids)

        if self.active_order_id is not None:
            active_order_ids.add(int(self.active_order_id))

        if (
            int(order_id) in active_order_ids
            and item["status"].strip().upper() in terminal_statuses
        ):
            self.order_event.set()

    def managedAccounts(self, accountsList: str) -> None:  # noqa
        """
        Отримати список доступних IB accounts від TWS / IB Gateway.
        """
        self.managed_accounts = [
            item.strip() for item in accountsList.split(",") if item.strip()
        ]

        self._logger.info("IB managed accounts received: %s", self.managed_accounts)


class IBAdapter(BrokerInterface):
    """
    Canonical IB runtime adapter.
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        logger: logging.Logger | None = None,  # noqa
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)

        self._host = host
        self._port = port
        self._client_id = client_id

        self._wrapper = _IBWrapper(self._logger)

        self._wrapper.state_callback = self._set_broker_state

        self._order_id_lock = threading.RLock()

        self._pnl_lock = threading.RLock()
        self._pnl_req_id = 910000

        self._execution_lock = threading.RLock()
        self._execution_req_id = 920000

        self._positions_lock = threading.RLock()
        self._open_orders_lock = threading.RLock()
        self._completed_orders_lock = threading.RLock()
        self._market_data_lock = threading.RLock()
        self._market_data_req_id = 930000
        self._market_data_requests_by_symbol: dict[str, int] = {}
        self._market_data_delayed_mode_requested = False
        self._historical_data_lock = threading.RLock()
        self._historical_data_req_id = 940000

        self._client = EClient(self._wrapper)

        self._thread: threading.Thread | None = None

        self._connected = False
        self._stopping = False
        self._broker_state = "DISCONNECTED"

    @property
    def broker_state(self) -> str:
        """
        Current broker connection state.
        """
        return self._broker_state

    def connect(self) -> bool:
        """
        Connect to IB runtime API.
        """
        if self._connected:
            self._logger.info("IB already connected.")
            return True

        self._broker_state = "CONNECTING"

        self._logger.info(
            "Connecting to IB | host=%s | port=%s | clientId=%s",
            self._host,
            self._port,
            self._client_id,
        )

        self._stopping = False
        self._wrapper.connected_event.clear()

        self._client.connect(
            self._host,
            self._port,
            self._client_id,
        )

        self._thread = threading.Thread(
            target=self._run_client_loop,
            daemon=True,
            name="IBApiThread",
        )
        self._thread.start()

        connected = self._wrapper.connected_event.wait(
            timeout=IB_CONNECT_TIMEOUT_SECONDS
        )

        if connected:
            self._connected = True
            self._broker_state = "CONNECTED"
            self._logger.info("IB runtime connected.")
            return True

        self._broker_state = "ERROR"
        self._logger.error("IB connection timeout.")
        return False

    def disconnect(self) -> None:
        """
        Відключитися від IB і коректно завершити API thread.
        """

        self._logger.info("Disconnecting from IB...")
        self._stopping = True
        self._cancel_all_forex_quote_subscriptions()

        try:
            self._client.disconnect()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("IB disconnect failed: %s", exc)

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=IB_THREAD_JOIN_TIMEOUT_SECONDS)

            if self._thread.is_alive():
                self._logger.warning("IB API thread did not stop cleanly.")

        self._connected = False
        self._broker_state = "DISCONNECTED"
        self._logger.info("IB disconnected.")

    def is_connected(self) -> bool:
        """
        Return runtime connection state.
        """
        return self._connected

    def get_account_info(self) -> BrokerAccount:
        """
        Return IB account info through reqAccountSummary.
        """
        if not self._connected:
            return self._empty_account_info()

        req_id = 1

        self._wrapper.account_summary_event.clear()
        self._wrapper.account_values.clear()

        self._logger.info("Requesting IB account summary...")

        self._client.reqAccountSummary(
            req_id,
            "All",
            ACCOUNT_SUMMARY_TAGS,
        )

        finished = self._wrapper.account_summary_event.wait(
            timeout=IB_ACCOUNT_SUMMARY_TIMEOUT_SECONDS
        )

        try:
            self._client.cancelAccountSummary(req_id)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("cancelAccountSummary failed: %s", exc)

        if not finished:
            self._logger.error("IB account summary timeout.")
            return self._empty_account_info()

        return self._build_account_info()

    def _empty_account_info(self) -> BrokerAccount:
        """
        Return empty BrokerAccount.
        """
        return BrokerAccount(
            broker="IB",
            account_id="",
            account_mode="DEMO",
            raw_payload={
                "connected": self._connected,
                "broker_state": self._broker_state,
                "next_valid_id": self._wrapper.next_valid_id,
            },
        )

    def _build_account_info(self) -> BrokerAccount:
        """
        Build BrokerAccount from collected IB account summary values.
        """
        values = self._wrapper.account_values

        net_liquidation = values.get("NetLiquidation", {})
        total_cash = values.get("TotalCashValue", {})
        available_funds = values.get("AvailableFunds", {})
        maint_margin = values.get("MaintMarginReq", {})

        currency = (
            net_liquidation.get("currency")
            or total_cash.get("currency")
            or available_funds.get("currency")
            or maint_margin.get("currency")
            or ""
        )

        raw_payload: dict[str, Any] = {
            "connected": self._connected,
            "broker_state": self._broker_state,
            "next_valid_id": self._wrapper.next_valid_id,
            "account_values": values,
        }

        return BrokerAccount(
            broker="IB",
            account_id=self._wrapper.account_id,
            account_mode="DEMO",
            currency=currency,
            balance=_to_float(total_cash.get("value", "")),
            equity=_to_float(net_liquidation.get("value", "")),
            margin_used=_to_float(maint_margin.get("value", "")),
            margin_free=_to_float(available_funds.get("value", "")),
            raw_payload=raw_payload,
        )

    def _account_currency_from_summary_cache(self) -> str:
        """Return cached IB account/base currency without a new request."""
        values = self._wrapper.account_values

        for tag in (
            "NetLiquidation",
            "TotalCashValue",
            "AvailableFunds",
            "MaintMarginReq",
        ):
            currency = (
                str((values.get(tag) or {}).get("currency") or "").strip().upper()
            )

            if currency and currency != "BASE":
                return currency

        return ""

    def _build_positions(
        self,
        position_rows: list[dict[str, Any]] | None = None,
        portfolio_by_id: dict[str, dict[str, Any]] | None = None,
        pnl_by_id: dict[str, dict[str, Any]] | None = None,
        sl_tp_by_id: dict[str, dict[str, Any]] | None = None,
        execution_time_by_id: dict[str, str] | None = None,
    ) -> list[BrokerPosition]:
        """
        Build canonical BrokerPosition list from IB positions.

        IB API інколи може повернути дубльований callback для тієї самої
        account + CASH contract position. Для OrdersPage потрібна одна
        канонічна broker position на account + symbol.
        """

        if position_rows is None:
            position_rows = self._wrapper.positions
        portfolio_by_id = portfolio_by_id or {}

        pnl_by_id = pnl_by_id or {}
        sl_tp_by_id = sl_tp_by_id or {}
        execution_time_by_id = execution_time_by_id or {}

        result_by_id: dict[str, BrokerPosition] = {}
        account_pnl_currency = self._account_currency_from_summary_cache()

        for item in position_rows:
            position_value = float(item.get("position") or 0.0)
            if position_value == 0.0:
                continue

            contract = item.get("contract")
            symbol = str(getattr(contract, "symbol", "") or "").strip().upper()
            currency = str(getattr(contract, "currency", "") or "").strip().upper()
            sec_type = str(getattr(contract, "secType", "") or "").strip().upper()
            account_id = str(item.get("account") or "").strip()

            symbol_name = self._build_symbol_name_from_contract(contract)

            side = POSITION_SIDE_BUY
            volume = position_value

            if position_value < 0:
                side = POSITION_SIDE_SELL
                volume = abs(position_value)

            position_id = f"IB:{account_id}:{symbol_name}"

            portfolio_row = portfolio_by_id.get(position_id) or {}

            pnl_row = pnl_by_id.get(position_id) or {}
            sl_tp_row = sl_tp_by_id.get(position_id) or {}
            execution_time = str(execution_time_by_id.get(position_id) or "").strip()

            entry_price = float(item.get("avg_cost") or 0.0)
            current_price = 0.0
            unrealized_pnl = 0.0

            raw_payload: dict[str, Any] = {
                "account": item.get("account"),
                "pnl_currency": account_pnl_currency,
                "position": item.get("position"),
                "avg_cost": item.get("avg_cost"),
                "contract": {
                    "symbol": symbol,
                    "secType": sec_type,
                    "currency": currency,
                    "exchange": getattr(contract, "exchange", ""),
                    "conId": getattr(contract, "conId", 0),
                },
            }

            if pnl_row:
                current_price = float(pnl_row.get("current_price") or 0.0)
                unrealized_pnl = float(pnl_row.get("unrealized_pnl") or 0.0)

                raw_payload["current_price"] = current_price
                raw_payload["unrealized_pnl"] = unrealized_pnl
                raw_payload["pnl_single"] = {
                    "position": pnl_row.get("position"),
                    "daily_pnl": pnl_row.get("daily_pnl"),
                    "unrealized_pnl": pnl_row.get("unrealized_pnl"),
                    "realized_pnl": pnl_row.get("realized_pnl"),
                    "value": pnl_row.get("value"),
                    "current_price": pnl_row.get("current_price"),
                    "source": pnl_row.get("source"),
                }

                self._logger.info(
                    "IB position enriched from pnlSingle | "
                    "position_id=%s | current_price=%s | unrealized_pnl=%s",
                    position_id,
                    current_price,
                    unrealized_pnl,
                )

            elif portfolio_row:
                current_price = float(portfolio_row.get("market_price") or 0.0)
                unrealized_pnl = float(portfolio_row.get("unrealized_pnl") or 0.0)

                portfolio_average_cost = float(portfolio_row.get("average_cost") or 0.0)

                if portfolio_average_cost > 0.0:
                    entry_price = portfolio_average_cost

                raw_payload["current_price"] = current_price
                raw_payload["unrealized_pnl"] = unrealized_pnl
                raw_payload["portfolio"] = {
                    "position": portfolio_row.get("position"),
                    "market_price": portfolio_row.get("market_price"),
                    "market_value": portfolio_row.get("market_value"),
                    "average_cost": portfolio_row.get("average_cost"),
                    "unrealized_pnl": portfolio_row.get("unrealized_pnl"),
                    "realized_pnl": portfolio_row.get("realized_pnl"),
                }
            stop_loss = sl_tp_row.get("stop_loss")
            take_profit = sl_tp_row.get("take_profit")

            if sl_tp_row:
                raw_payload["sl_tp_orders"] = dict(sl_tp_row)

            if execution_time:
                raw_payload["execution_time"] = execution_time

            result_by_id[position_id] = BrokerPosition(
                broker="IB",
                account_id=account_id,
                account_mode="DEMO",
                position_id=position_id,
                symbol_name=symbol_name,
                side=side,
                volume=volume,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                currency=currency,
                raw_payload=raw_payload,
                stop_loss=stop_loss,
                take_profit=take_profit,
                opened_utc=execution_time,
            )

        return list(result_by_id.values())

    @staticmethod
    def _build_symbol_name_from_contract(contract) -> str:
        """
        Побудувати LGE symbol name з IB Contract.
        """
        symbol = str(getattr(contract, "symbol", "") or "").strip().upper()
        currency = str(getattr(contract, "currency", "") or "").strip().upper()
        sec_type = str(getattr(contract, "secType", "") or "").strip().upper()

        if sec_type == "CASH" and currency:
            return f"{symbol}{currency}"

        return symbol

    def _request_portfolio_by_position_id(
        self,
        position_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Отримати broker-provided PnL/current price через IB account updates.
        """
        accounts: list[str] = []

        for row in position_rows:
            account = str(row.get("account") or "").strip()

            if account and account not in accounts:
                accounts.append(account)

        if not accounts:
            return {}

        portfolio_rows: list[dict[str, Any]] = []

        for account in accounts:
            self._wrapper.portfolio_event.clear()
            self._wrapper.portfolio_rows.clear()

            self._logger.info(
                "Requesting IB portfolio snapshot | account=%s",
                account,
            )

            self._client.reqAccountUpdates(
                True,
                account,
            )

            finished = self._wrapper.portfolio_event.wait(
                timeout=IB_PORTFOLIO_TIMEOUT_SECONDS,
            )

            rows = list(self._wrapper.portfolio_rows)
            self._logger.info(
                "IB portfolio snapshot rows | account=%s | rows=%s | finished=%s",
                account,
                len(rows),
                finished,
            )

            try:
                self._client.reqAccountUpdates(
                    False,
                    account,
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("cancel IB account updates failed: %s", exc)

            if not finished and not rows:
                self._logger.warning(
                    "IB portfolio snapshot timeout | account=%s",
                    account,
                )
                continue

            portfolio_rows.extend(rows)

        return self._build_portfolio_by_position_id(portfolio_rows)

    def _build_portfolio_by_position_id(
        self,
        portfolio_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Побудувати map IB position_id -> portfolio row.
        """
        result: dict[str, dict[str, Any]] = {}

        for row in portfolio_rows:
            position_value = float(row.get("position") or 0.0)

            if position_value == 0.0:
                continue

            contract = row.get("contract")
            account_id = str(row.get("account") or "").strip()
            symbol_name = self._build_symbol_name_from_contract(contract)

            if not account_id or not symbol_name:
                continue

            position_id = f"IB:{account_id}:{symbol_name}"
            self._logger.info(
                "IB portfolio row mapped | position_id=%s | position=%s | "
                "market_price=%s | average_cost=%s | unrealized_pnl=%s",
                position_id,
                row.get("position"),
                row.get("market_price"),
                row.get("average_cost"),
                row.get("unrealized_pnl"),
            )
            result[position_id] = row

        return result

    def _request_open_orders_snapshot(
        self,
        include_objects: bool = False,
        require_complete: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Прочитати поточні IB open orders одним snapshot-ом.

        Для read-only path timeout лише фіксується у log.
        Для execution path require_complete=True блокує операцію,
        якщо broker не підтвердив завершення snapshot.
        """
        if require_complete and not self._connected:
            raise RuntimeError("IB adapter is not connected")

        with self._open_orders_lock:
            self._wrapper.open_orders_event.clear()
            self._wrapper.open_orders.clear()
            self._wrapper.open_order_objects.clear()

            self._logger.info(
                "Requesting all IB open orders snapshot | "
                "include_objects=%s | require_complete=%s",
                include_objects,
                require_complete,
            )

            self._client.reqAllOpenOrders()

            finished = self._wrapper.open_orders_event.wait(
                timeout=IB_OPEN_ORDERS_TIMEOUT_SECONDS,
            )

            if not finished:
                if require_complete:
                    self._logger.error("IB open orders snapshot timeout for execution.")
                    raise RuntimeError(
                        "IB open orders snapshot timeout for SL/TP modify"
                    )

                self._logger.warning("IB open orders snapshot timeout.")

            self._logger.info(
                "IB open orders snapshot rows | rows=%s | finished=%s",
                len(self._wrapper.open_orders),
                finished,
            )

            snapshot = self.build_open_order_snapshot_rows(
                open_orders=self._wrapper.open_orders,
                open_order_objects=self._wrapper.open_order_objects,
                current_client_id=self._client_id,
                include_objects=include_objects,
            )

            for row in snapshot:
                self._logger.info(
                    "IB open order ownership candidate | "
                    "order_id=%s | order_client_id=%s | "
                    "current_client_id=%s | same_client_id=%s",
                    row.get("order_id"),
                    row.get("client_id"),
                    self._client_id,
                    row.get("same_client_id"),
                )

            return snapshot

    def _request_open_orders_by_position_id(
        self,
        position_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Прочитати IB open orders і зібрати SL/TP по broker position id.

        IB Forex positions netted. Тому SL/TP треба показувати
        з урахуванням coverage:
        - повне покриття -> звичайне SL/TP;
        - часткове покриття -> SL/TP + partial flags.
        """
        open_orders = self._request_open_orders_snapshot(
            include_objects=False,
        )

        return self._build_sl_tp_by_position_id(
            open_orders=open_orders,
            position_rows=position_rows,
        )

    def _build_position_meta_by_id(
        self,
        position_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Побудувати map position_id -> net position metadata.

        Потрібно для coverage-aware SL/TP enrichment.
        """
        result: dict[str, dict[str, Any]] = {}

        for row in position_rows:
            position_value = float(row.get("position") or 0.0)

            if position_value == 0.0:
                continue

            contract = row.get("contract")
            account_id = str(row.get("account") or "").strip()
            symbol_name = self._build_symbol_name_from_contract(contract)

            if not account_id or not symbol_name:
                continue

            side = POSITION_SIDE_BUY
            protective_action = "SELL"

            if position_value < 0.0:
                side = POSITION_SIDE_SELL
                protective_action = "BUY"

            position_id = f"IB:{account_id}:{symbol_name}"

            result[position_id] = {
                "side": side,
                "volume": abs(position_value),
                "protective_action": protective_action,
            }

        return result

    @staticmethod
    def _append_sl_tp_candidate(
        grouped: dict[str, list[dict[str, Any]]],
        key: str,
        price: float,
        quantity: float,
        order: dict[str, Any],
    ) -> None:
        """
        Додати SL/TP candidate order з execution metadata.
        """
        if price <= 0.0 or quantity <= 0.0:
            return

        grouped.setdefault(key, []).append(
            {
                "price": float(price),
                "quantity": abs(float(quantity)),
                "order_id": int(order.get("order_id") or 0),
                "client_id": int(order.get("client_id") or 0),
                "perm_id": int(order.get("perm_id") or 0),
                "same_client_id": bool(order.get("same_client_id")),
                "oca_group": str(order.get("oca_group") or ""),
                "oca_type": int(order.get("oca_type") or 0),
                "contract_object": order.get("contract_object"),
                "order_object": order.get("order_object"),
            }
        )

    @staticmethod
    def _pick_sl_tp_coverage_row(
        candidates: list[dict[str, Any]],
        position_volume: float,
    ) -> dict[str, Any] | None:
        """
        Визначити price, coverage та execution metadata для SL/TP.

        operational_ambiguous=True означає, що один protection leg
        представлений кількома broker orders і його не можна мовчки
        трактувати як один order для modify.
        """
        if not candidates or position_volume <= 0.0:
            return None

        by_price: dict[float, dict[str, Any]] = {}

        for item in candidates:
            price = float(item.get("price") or 0.0)
            quantity = abs(float(item.get("quantity") or 0.0))

            if price <= 0.0 or quantity <= 0.0:
                continue

            price_key = round(price, 10)
            row = by_price.setdefault(
                price_key,
                {
                    "price": price,
                    "quantity": 0.0,
                    "orders": [],
                },
            )

            row["quantity"] += quantity
            row["orders"].append(dict(item))

        if not by_price:
            return None

        all_orders: list[dict[str, Any]] = []

        for row in by_price.values():
            all_orders.extend(row.get("orders") or [])

        order_ids = sorted(
            {
                int(order.get("order_id") or 0)
                for order in all_orders
                if int(order.get("order_id") or 0) > 0
            }
        )

        order_count = len(order_ids)

        if not order_ids:
            order_count = len(all_orders)

        all_same_client_id = bool(all_orders) and all(
            bool(order.get("same_client_id")) for order in all_orders
        )

        if len(by_price) == 1:
            row = next(iter(by_price.values()))
            quantity = float(row.get("quantity") or 0.0)
            orders = list(row.get("orders") or [])

            result: dict[str, Any] = {
                "price": float(row.get("price") or 0.0),
                "quantity": quantity,
                "position_volume": position_volume,
                "partial": not math.isclose(
                    quantity,
                    position_volume,
                    rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
                    abs_tol=IB_SL_TP_COVERAGE_ABS_TOLERANCE,
                ),
                "ambiguous": False,
                "operational_ambiguous": order_count != 1,
                "order_ids": order_ids,
                "order_count": order_count,
                "same_client_id": all_same_client_id,
            }

            if order_count == 1 and orders:
                single_order = orders[0]

                result["order_id"] = int(single_order.get("order_id") or 0)
                result["client_id"] = int(single_order.get("client_id") or 0)

                result["perm_id"] = int(single_order.get("perm_id") or 0)
                result["oca_group"] = str(single_order.get("oca_group") or "")
                result["oca_type"] = int(single_order.get("oca_type") or 0)

                contract_object = single_order.get("contract_object")
                order_object = single_order.get("order_object")

                if contract_object is not None:
                    result["contract_object"] = contract_object

                if order_object is not None:
                    result["order_object"] = order_object

            return result

        total_quantity = sum(
            float(row.get("quantity") or 0.0) for row in by_price.values()
        )

        return {
            "price": 0.0,
            "quantity": total_quantity,
            "position_volume": position_volume,
            "partial": True,
            "ambiguous": True,
            "operational_ambiguous": True,
            "order_ids": order_ids,
            "order_count": order_count,
            "same_client_id": all_same_client_id,
        }

    def _build_sl_tp_by_position_id(
        self,
        open_orders: list[dict[str, Any]],
        position_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Побудувати map position_id -> SL/TP з IB open orders.

        Важливо:
        IB Forex positions netted. Якщо позиція BUY 2K, а STP тільки 1K,
        це частковий SL, а не SL всієї позиції.
        """
        result: dict[str, dict[str, Any]] = {}
        candidates_by_position_id: dict[
            str,
            dict[str, list[dict[str, Any]]],
        ] = {}

        position_meta_by_id = self._build_position_meta_by_id(position_rows)
        fallback_account_id = self._get_primary_account_id()

        for order in open_orders:
            account_id = str(order.get("account") or "").strip()

            if not account_id:
                account_id = fallback_account_id

            symbol = str(order.get("symbol") or "").strip().upper()
            currency = str(order.get("currency") or "").strip().upper()
            sec_type = str(order.get("sec_type") or "").strip().upper()
            order_type = str(order.get("order_type") or "").strip().upper()
            action = str(order.get("action") or "").strip().upper()
            quantity = abs(float(order.get("total_quantity") or 0.0))

            if sec_type != "CASH":
                continue

            if not account_id or not symbol or not currency:
                continue

            if order_type not in {"STP", "STOP", "LMT", "LIMIT"}:
                continue

            symbol_name = f"{symbol}{currency}"
            position_id = f"IB:{account_id}:{symbol_name}"
            position_meta = position_meta_by_id.get(position_id)

            if not position_meta:
                continue

            protective_action = (
                str(position_meta.get("protective_action") or "").strip().upper()
            )

            if action != protective_action:
                continue

            grouped = candidates_by_position_id.setdefault(position_id, {})

            lmt_price = float(order.get("lmt_price") or 0.0)
            aux_price = float(order.get("aux_price") or 0.0)

            if order_type in {"STP", "STOP"}:
                self._append_sl_tp_candidate(
                    grouped=grouped,
                    key="stop_loss",
                    price=aux_price,
                    quantity=quantity,
                    order=order,
                )

            if order_type in {"LMT", "LIMIT"}:
                self._append_sl_tp_candidate(
                    grouped=grouped,
                    key="take_profit",
                    price=lmt_price,
                    quantity=quantity,
                    order=order,
                )

        for position_id, grouped in candidates_by_position_id.items():
            position_meta = position_meta_by_id.get(position_id) or {}
            position_volume = float(position_meta.get("volume") or 0.0)

            row: dict[str, Any] = {}

            stop_loss_row = self._pick_sl_tp_coverage_row(
                candidates=grouped.get("stop_loss", []),
                position_volume=position_volume,
            )
            take_profit_row = self._pick_sl_tp_coverage_row(
                candidates=grouped.get("take_profit", []),
                position_volume=position_volume,
            )

            if stop_loss_row:
                stop_loss_price = float(stop_loss_row.get("price") or 0.0)

                if stop_loss_price > 0.0:
                    row["stop_loss"] = stop_loss_price

                row["stop_loss_quantity"] = float(stop_loss_row.get("quantity") or 0.0)
                row["stop_loss_position_volume"] = float(
                    stop_loss_row.get("position_volume") or 0.0
                )
                row["stop_loss_partial"] = bool(stop_loss_row.get("partial"))
                row["stop_loss_ambiguous"] = bool(stop_loss_row.get("ambiguous"))

                row["stop_loss_operational_ambiguous"] = bool(
                    stop_loss_row.get("operational_ambiguous")
                )
                row["stop_loss_order_ids"] = list(stop_loss_row.get("order_ids") or [])
                row["stop_loss_order_count"] = int(
                    stop_loss_row.get("order_count") or 0
                )
                row["stop_loss_same_client_id"] = bool(
                    stop_loss_row.get("same_client_id")
                )

                stop_loss_order_id = int(stop_loss_row.get("order_id") or 0)

                if stop_loss_order_id > 0:
                    row["stop_loss_order_id"] = stop_loss_order_id
                    row["stop_loss_client_id"] = int(
                        stop_loss_row.get("client_id") or 0
                    )
                    row["stop_loss_perm_id"] = int(stop_loss_row.get("perm_id") or 0)
                    row["stop_loss_oca_group"] = str(
                        stop_loss_row.get("oca_group") or ""
                    )
                    row["stop_loss_oca_type"] = int(stop_loss_row.get("oca_type") or 0)

                stop_contract = stop_loss_row.get("contract_object")
                stop_order = stop_loss_row.get("order_object")

                if stop_contract is not None:
                    row["stop_loss_contract_object"] = stop_contract

                if stop_order is not None:
                    row["stop_loss_order_object"] = stop_order

            if take_profit_row:
                take_profit_price = float(take_profit_row.get("price") or 0.0)

                if take_profit_price > 0.0:
                    row["take_profit"] = take_profit_price

                row["take_profit_quantity"] = float(
                    take_profit_row.get("quantity") or 0.0
                )
                row["take_profit_position_volume"] = float(
                    take_profit_row.get("position_volume") or 0.0
                )
                row["take_profit_partial"] = bool(take_profit_row.get("partial"))
                row["take_profit_ambiguous"] = bool(take_profit_row.get("ambiguous"))

                row["take_profit_operational_ambiguous"] = bool(
                    take_profit_row.get("operational_ambiguous")
                )
                row["take_profit_order_ids"] = list(
                    take_profit_row.get("order_ids") or []
                )
                row["take_profit_order_count"] = int(
                    take_profit_row.get("order_count") or 0
                )
                row["take_profit_same_client_id"] = bool(
                    take_profit_row.get("same_client_id")
                )

                take_profit_order_id = int(take_profit_row.get("order_id") or 0)

                if take_profit_order_id > 0:
                    row["take_profit_order_id"] = take_profit_order_id
                    row["take_profit_client_id"] = int(
                        take_profit_row.get("client_id") or 0
                    )
                    row["take_profit_perm_id"] = int(
                        take_profit_row.get("perm_id") or 0
                    )
                    row["take_profit_oca_group"] = str(
                        take_profit_row.get("oca_group") or ""
                    )
                    row["take_profit_oca_type"] = int(
                        take_profit_row.get("oca_type") or 0
                    )

                take_contract = take_profit_row.get("contract_object")
                take_order = take_profit_row.get("order_object")

                if take_contract is not None:
                    row["take_profit_contract_object"] = take_contract

                if take_order is not None:
                    row["take_profit_order_object"] = take_order

            if row:
                result[position_id] = row

            self._logger.info(
                "IB SL/TP coverage mapped | position_id=%s | "
                "position_volume=%s | row=%s | raw_candidates=%s",
                position_id,
                position_volume,
                row,
                grouped,
            )

        return result

    def _get_primary_account_id(self) -> str:
        """
        Отримати primary IB account id для mapping open orders.
        """
        account_id = str(self._wrapper.account_id or "").strip()

        if account_id:
            return account_id

        accounts = list(self._wrapper.managed_accounts)

        if accounts:
            return str(accounts[0] or "").strip()

        return ""

    def _request_execution_times_by_position_id(
        self,
        position_rows: list[dict[str, Any]],
    ) -> dict[str, str]:
        """
        Отримати час відкриття manual TWS positions через IB executions.

        Для позицій, відкритих через LGE, час уже може бути взятий з SQLite.
        Для TWS manual positions SQLite запису немає, тому беремо останній
        execution того самого account + symbol + side.
        """
        accounts: list[str] = []

        for row in position_rows:
            account = str(row.get("account") or "").strip()

            if account and account not in accounts:
                accounts.append(account)

        if not accounts:
            return {}

        result: dict[str, str] = {}

        for account in accounts:
            req_id = self._get_next_execution_req_id()

            self._wrapper.execution_event.clear()
            self._wrapper.executions.clear()

            execution_filter = ExecutionFilter()
            execution_filter.acctCode = account

            self._logger.info(
                "Requesting IB executions | reqId=%s | account=%s",
                req_id,
                account,
            )

            self._client.reqExecutions(
                req_id,
                execution_filter,
            )

            finished = self._wrapper.execution_event.wait(
                timeout=IB_EXECUTIONS_TIMEOUT_SECONDS,
            )

            executions = list(self._wrapper.executions)

            if not finished:
                self._logger.warning(
                    "IB executions snapshot timeout | reqId=%s | account=%s",
                    req_id,
                    account,
                )

            self._logger.info(
                "IB executions snapshot rows | reqId=%s | account=%s | "
                "rows=%s | finished=%s",
                req_id,
                account,
                len(executions),
                finished,
            )

            result.update(
                self._build_execution_time_by_position_id(
                    position_rows=position_rows,
                    executions=executions,
                )
            )

        return result

    def _build_execution_time_by_position_id(
        self,
        position_rows: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> dict[str, str]:
        """
        Побудувати map position_id -> execution time.
        """
        position_side_by_id: dict[str, str] = {}

        for row in position_rows:
            contract = row.get("contract")
            position_value = float(row.get("position") or 0.0)

            if position_value == 0.0:
                continue

            account_id = str(row.get("account") or "").strip()
            symbol_name = self._build_symbol_name_from_contract(contract)

            if not account_id or not symbol_name:
                continue

            side = POSITION_SIDE_BUY

            if position_value < 0.0:
                side = POSITION_SIDE_SELL

            position_id = f"IB:{account_id}:{symbol_name}"
            position_side_by_id[position_id] = side

        result: dict[str, str] = {}
        fallback_account_id = self._get_primary_account_id()

        for execution in executions:
            account_id = str(execution.get("account") or "").strip()

            if not account_id:
                account_id = fallback_account_id

            symbol_name = self._build_symbol_name_from_execution_row(execution)

            if not account_id or not symbol_name:
                continue

            position_id = f"IB:{account_id}:{symbol_name}"
            position_side = position_side_by_id.get(position_id)

            if not position_side:
                continue

            execution_side = str(execution.get("side") or "").strip().upper()

            if not self._execution_side_matches_position(
                execution_side=execution_side,
                position_side=position_side,
            ):
                continue

            execution_time = self._normalize_ib_execution_time(
                execution.get("time"),
            )

            if not execution_time:
                continue

            current_time = result.get(position_id)

            if not current_time or execution_time > current_time:
                result[position_id] = execution_time

                self._logger.info(
                    "IB execution time mapped | position_id=%s | " "side=%s | time=%s",
                    position_id,
                    execution_side,
                    execution_time,
                )

        return result

    @staticmethod
    def _build_symbol_name_from_execution_row(
        execution: dict[str, Any],
    ) -> str:
        """
        Побудувати LGE symbol name з execution payload.
        """
        symbol = str(execution.get("symbol") or "").strip().upper()
        currency = str(execution.get("currency") or "").strip().upper()
        sec_type = str(execution.get("sec_type") or "").strip().upper()

        if sec_type == "CASH" and currency:
            return f"{symbol}{currency}"

        return symbol

    @staticmethod
    def _execution_side_matches_position(
        execution_side: str,
        position_side: str,
    ) -> bool:
        """
        Зіставити IB execution side з поточним side позиції.
        """
        execution_side_norm = str(execution_side or "").strip().upper()
        position_side_norm = str(position_side or "").strip().upper()

        if position_side_norm == POSITION_SIDE_BUY:
            return execution_side_norm in {"BOT", "BUY", "BOUGHT"}

        if position_side_norm == POSITION_SIDE_SELL:
            return execution_side_norm in {"SLD", "SELL", "SOLD"}

        return False

    @staticmethod
    def _normalize_ib_execution_time(
        value,
    ) -> str:
        """
        Нормалізувати IB execution time до ISO-like формату.

        IB часто дає:
        - 20260709  16:52:08
        - 20260709-16:52:08

        Повертаємо:
        - 2026-07-09T16:52:08
        """
        text = str(value or "").strip()

        if not text:
            return ""

        compact = " ".join(text.replace("-", " ", 1).split())

        if len(compact) >= 17 and compact[:8].isdigit():
            date_part = compact[:8]
            time_part = compact[9:17]

            return f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]}" f"T{time_part}"

        return text

    def _get_next_execution_req_id(self) -> int:
        """
        Взяти наступний reqId для IB executions request.
        """
        with self._execution_lock:
            self._execution_req_id += 1

            return self._execution_req_id

    def _request_pnl_by_position_id(
        self,
        position_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Отримати broker-provided PnL через IB reqPnLSingle.
        """
        result: dict[str, dict[str, Any]] = {}

        for row in position_rows:
            contract = row.get("contract")
            position_value = float(row.get("position") or 0.0)
            account_id = str(row.get("account") or "").strip()

            if position_value == 0.0:
                continue

            con_id = int(getattr(contract, "conId", 0) or 0)
            symbol_name = self._build_symbol_name_from_contract(contract)

            if not account_id or not symbol_name or con_id <= 0:
                self._logger.warning(
                    "IB pnlSingle skipped | account=%s | symbol=%s | conId=%s",
                    account_id,
                    symbol_name,
                    con_id,
                )
                continue

            req_id = self._get_next_pnl_req_id()
            position_id = f"IB:{account_id}:{symbol_name}"

            self._wrapper.pnl_single_event.clear()
            self._wrapper.pnl_single_rows.pop(req_id, None)

            self._logger.info(
                "Requesting IB pnlSingle | reqId=%s | account=%s | "
                "conId=%s | position_id=%s",
                req_id,
                account_id,
                con_id,
                position_id,
            )

            self._client.reqPnLSingle(
                req_id,
                account_id,
                "",
                con_id,
            )

            finished = self._wrapper.pnl_single_event.wait(
                timeout=IB_PNL_TIMEOUT_SECONDS,
            )

            pnl_row = dict(self._wrapper.pnl_single_rows.get(req_id, {}))

            try:
                self._client.cancelPnLSingle(req_id)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("IB cancelPnLSingle failed: %s", exc)

            if not finished and not pnl_row:
                self._logger.warning(
                    "IB pnlSingle timeout | reqId=%s | position_id=%s",
                    req_id,
                    position_id,
                )
                continue

            if not pnl_row:
                self._logger.warning(
                    "IB pnlSingle empty result | reqId=%s | position_id=%s",
                    req_id,
                    position_id,
                )
                continue

            volume = abs(position_value)
            raw_market_value = pnl_row.get("value")
            market_value = 0.0

            if raw_market_value is not None:
                market_value = abs(float(raw_market_value or 0.0))

            current_price = 0.0

            if volume > 0.0 and market_value > 0.0:
                current_price = market_value / volume

            pnl_row["current_price"] = current_price
            pnl_row["source"] = "IB_PNL_SINGLE"

            result[position_id] = pnl_row

        return result

    def _get_next_pnl_req_id(self) -> int:
        """
        Взяти наступний reqId для IB PnL subscription.
        """
        with self._pnl_lock:
            self._pnl_req_id += 1

            return self._pnl_req_id

    def _request_positions_snapshot_for_execution(
        self,
    ) -> list[dict[str, Any]]:
        """
        Отримати повний raw IB positions snapshot для execution path.

        На відміну від read-only get_positions(), timeout тут є
        блокувальною помилкою. Modify SL/TP не може працювати з
        неповним або невідомим broker snapshot.
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        with self._positions_lock:
            self._wrapper.position_event.clear()
            self._wrapper.positions.clear()

            self._logger.info("Requesting IB positions snapshot for execution.")

            finished = False

            try:
                self._client.reqPositions()

                finished = self._wrapper.position_event.wait(
                    timeout=IB_POSITIONS_TIMEOUT_SECONDS,
                )
            finally:
                try:
                    self._client.cancelPositions()
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning(
                        "cancelPositions failed after execution snapshot: %s",
                        exc,
                    )

            if not finished:
                self._logger.error("IB positions snapshot timeout for execution.")
                raise RuntimeError("IB positions snapshot timeout for SL/TP modify")

            snapshot = [dict(position_row) for position_row in self._wrapper.positions]

            self._logger.info(
                "IB positions snapshot for execution received | rows=%s",
                len(snapshot),
            )

            return snapshot

    def _find_position_row_for_sl_tp_modify(
        self,
        position_id: str,
        position_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Знайти raw IB position row для SL/TP modify.

        Runtime position id має формат:
        IB:<account_id>:<symbol_name>
        """
        position_id_clean = str(position_id or "").strip()

        if not position_id_clean:
            raise ValueError("IB position id is empty")

        position_id_parts = position_id_clean.split(":", 2)

        if len(position_id_parts) != 3 or position_id_parts[0].strip().upper() != "IB":
            raise ValueError(f"Invalid IB position id: {position_id_clean}")

        account_id = position_id_parts[1].strip()
        symbol_name = position_id_parts[2].strip().upper()

        if not account_id:
            raise ValueError(
                f"IB account id is missing in position id: " f"{position_id_clean}"
            )

        if not symbol_name:
            raise ValueError(
                f"IB symbol is missing in position id: " f"{position_id_clean}"
            )

        matches: list[dict[str, Any]] = []

        for row in position_rows:
            row_account_id = str(row.get("account") or "").strip()
            contract = row.get("contract")

            row_symbol_name = self._build_symbol_name_from_contract(
                contract,
            )

            if row_account_id == account_id and row_symbol_name == symbol_name:
                matches.append(row)

        if not matches:
            raise RuntimeError(f"IB position was not found: {position_id_clean}")

        reference_row = matches[-1]

        if len(matches) > 1:
            reference_position = float(reference_row.get("position") or 0.0)
            reference_contract = reference_row.get("contract")

            reference_identity = (
                int(getattr(reference_contract, "conId", 0) or 0),
                str(getattr(reference_contract, "symbol", "") or "").strip().upper(),
                str(getattr(reference_contract, "currency", "") or "").strip().upper(),
                str(getattr(reference_contract, "secType", "") or "").strip().upper(),
            )

            for row in matches[:-1]:
                row_position = float(row.get("position") or 0.0)
                row_contract = row.get("contract")

                row_identity = (
                    int(getattr(row_contract, "conId", 0) or 0),
                    str(getattr(row_contract, "symbol", "") or "").strip().upper(),
                    str(getattr(row_contract, "currency", "") or "").strip().upper(),
                    str(getattr(row_contract, "secType", "") or "").strip().upper(),
                )

                if (
                    not math.isclose(
                        row_position,
                        reference_position,
                        rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
                        abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
                    )
                    or row_identity != reference_identity
                ):
                    raise RuntimeError(
                        "IB position snapshot is ambiguous: " f"{position_id_clean}"
                    )

            self._logger.warning(
                "Duplicate identical IB position callbacks collapsed | "
                "position_id=%s | rows=%s",
                position_id_clean,
                len(matches),
            )

        return dict(reference_row)

    def _build_position_sl_tp_modify_context(
        self,
        position_id: str,
        position_row: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Побудувати broker context для зміни SL/TP IB position.
        """
        position_id_clean = str(position_id or "").strip()
        account_id = str(position_row.get("account") or "").strip()
        contract = position_row.get("contract")
        symbol_name = self._build_symbol_name_from_contract(contract)

        if not account_id:
            raise RuntimeError(f"IB position account is missing: {position_id_clean}")

        if not symbol_name:
            raise RuntimeError(f"IB position symbol is missing: {position_id_clean}")

        try:
            position_value = float(position_row.get("position") or 0.0)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid IB position volume: {position_id_clean}"
            ) from exc

        if not math.isfinite(position_value):
            raise RuntimeError(f"Invalid IB position volume: {position_id_clean}")

        volume = abs(position_value)

        if math.isclose(
            volume,
            0.0,
            rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
            abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
        ):
            raise RuntimeError(f"IB position volume is zero: {position_id_clean}")

        if position_value > 0.0:
            side = POSITION_SIDE_BUY
            protective_action = "SELL"
        elif position_value < 0.0:
            side = POSITION_SIDE_SELL
            protective_action = "BUY"
        else:
            raise RuntimeError(f"Unknown IB position side: {position_id_clean}")

        normalized_position_id = f"IB:{account_id}:{symbol_name}"

        if normalized_position_id != position_id_clean:
            raise RuntimeError(
                "IB position identity changed during snapshot: "
                f"requested={position_id_clean}, "
                f"broker={normalized_position_id}"
            )

        return {
            "position_id": normalized_position_id,
            "account_id": account_id,
            "symbol_name": symbol_name,
            "side": side,
            "volume": volume,
            "protective_action": protective_action,
            "contract_object": contract,
            "position_row": dict(position_row),
        }

    def get_virtual_position_leg_evidence_snapshot(
        self,
    ) -> dict[str, Any]:
        """
        Отримати повний read-only IB evidence для virtual position legs.

        Метод не змінює SQLite і не виконує broker orders. Якщо IB не
        завершив хоча б одну request-серію, snapshot не повертається.
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        raw_position_rows = self._request_positions_snapshot_for_execution()
        position_rows = self.build_virtual_leg_position_evidence_rows(
            position_rows=raw_position_rows,
        )

        open_order_rows = self._request_open_orders_snapshot(
            include_objects=False,
            require_complete=True,
        )

        for row in open_order_rows:
            row["symbol_name"] = self._build_symbol_name_from_order_row(row)
            row["broker_position_id"] = self._build_position_id_from_open_order(row)

        completed_order_rows = self._request_completed_orders_snapshot(
            api_only=False,
            require_complete=True,
        )

        for row in completed_order_rows:
            row["symbol_name"] = self._build_symbol_name_from_order_row(row)
            row["broker_position_id"] = self._build_position_id_from_open_order(row)

        account_ids = self._build_virtual_leg_evidence_account_ids(
            position_rows=position_rows,
            open_order_rows=open_order_rows,
            completed_order_rows=completed_order_rows,
        )
        execution_rows = self._request_virtual_leg_execution_evidence(
            account_ids=account_ids,
        )

        snapshot = {
            "broker": "IB",
            "captured_utc": (datetime.now(UTC).replace(microsecond=0).isoformat()),
            "current_client_id": int(self._client_id),
            "complete": True,
            "positions_complete": True,
            "open_orders_complete": True,
            "completed_orders_complete": True,
            "executions_complete": True,
            "completed_orders_api_only": False,
            "account_ids": account_ids,
            "positions": position_rows,
            "open_orders": open_order_rows,
            "completed_orders": completed_order_rows,
            "executions": execution_rows,
        }

        self._logger.info(
            "IB virtual leg evidence snapshot | positions=%s | "
            "open_orders=%s | completed_orders=%s | executions=%s",
            len(position_rows),
            len(open_order_rows),
            len(completed_order_rows),
            len(execution_rows),
        )

        return snapshot

    def _request_completed_orders_snapshot(
        self,
        api_only: bool = False,
        require_complete: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Прочитати IB completed orders для поточного trading day.

        api_only=False включає також TWS-submitted orders. Це evidence,
        а не доказ LGE ownership; ownership визначається reconciler-ом.
        """
        if require_complete and not self._connected:
            raise RuntimeError("IB adapter is not connected")

        with self._completed_orders_lock:
            self._wrapper.completed_orders_event.clear()
            self._wrapper.completed_orders.clear()

            self._logger.info(
                "Requesting IB completed orders snapshot | "
                "api_only=%s | require_complete=%s",
                api_only,
                require_complete,
            )

            self._client.reqCompletedOrders(bool(api_only))

            finished = self._wrapper.completed_orders_event.wait(
                timeout=IB_COMPLETED_ORDERS_TIMEOUT_SECONDS,
            )

            if not finished:
                if require_complete:
                    self._logger.error(
                        "IB completed orders snapshot timeout for evidence."
                    )
                    raise RuntimeError(
                        "IB completed orders snapshot timeout for "
                        "virtual-leg evidence"
                    )

                self._logger.warning("IB completed orders snapshot timeout.")

            snapshot = self.build_completed_order_snapshot_rows(
                completed_orders=self._wrapper.completed_orders,
                current_client_id=self._client_id,
            )

            self._logger.info(
                "IB completed orders snapshot rows | rows=%s | " "finished=%s",
                len(snapshot),
                finished,
            )

            return snapshot

    def _request_virtual_leg_execution_evidence(
        self,
        account_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Прочитати повний IB executions snapshot для evidence accounts.
        """
        if not account_ids:
            raise RuntimeError("IB virtual-leg evidence accounts are empty")

        result: list[dict[str, Any]] = []

        with self._execution_lock:
            for account_id in account_ids:
                req_id = self._get_next_execution_req_id()

                self._wrapper.execution_event.clear()
                self._wrapper.executions.clear()

                execution_filter = ExecutionFilter()
                execution_filter.acctCode = account_id

                self._client.reqExecutions(
                    req_id,
                    execution_filter,
                )

                finished = self._wrapper.execution_event.wait(
                    timeout=IB_EXECUTIONS_TIMEOUT_SECONDS,
                )

                if not finished:
                    self._logger.error(
                        "IB virtual-leg execution evidence timeout | " "account=%s",
                        account_id,
                    )
                    raise RuntimeError(
                        "IB executions snapshot timeout for virtual-leg evidence"
                    )

                result.extend(dict(row) for row in self._wrapper.executions)

        return result

    def _build_virtual_leg_evidence_account_ids(
        self,
        position_rows: list[dict[str, Any]],
        open_order_rows: list[dict[str, Any]],
        completed_order_rows: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """
        Побудувати стабільний список IB accounts для executions request.
        """
        account_ids: list[str] = []

        evidence_rows = [
            *position_rows,
            *open_order_rows,
            *(completed_order_rows or []),
        ]

        for row in evidence_rows:
            account_id = str(row.get("account_id") or row.get("account") or "").strip()

            if account_id and account_id not in account_ids:
                account_ids.append(account_id)

        primary_account_id = self._get_primary_account_id()

        if primary_account_id and primary_account_id not in account_ids:
            account_ids.append(primary_account_id)

        for managed_account in self._wrapper.managed_accounts:
            account_id = str(managed_account or "").strip()

            if account_id and account_id not in account_ids:
                account_ids.append(account_id)

        return account_ids

    @classmethod
    def build_virtual_leg_position_evidence_rows(
        cls,
        position_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Перетворити IB position callbacks на scalar evidence rows.
        """
        result: list[dict[str, Any]] = []

        for source_row in position_rows:
            contract = source_row.get("contract")
            account_id = str(source_row.get("account") or "").strip()
            symbol_name = cls._build_symbol_name_from_contract(contract)
            signed_quantity = float(source_row.get("position") or 0.0)

            if signed_quantity > 0.0:
                side = POSITION_SIDE_BUY
            elif signed_quantity < 0.0:
                side = POSITION_SIDE_SELL
            else:
                side = "FLAT"

            result.append(
                {
                    "account_id": account_id,
                    "broker_position_id": (
                        f"IB:{account_id}:{symbol_name}"
                        if account_id and symbol_name
                        else ""
                    ),
                    "symbol_name": symbol_name,
                    "symbol": str(getattr(contract, "symbol", "") or "")
                    .strip()
                    .upper(),
                    "sec_type": str(getattr(contract, "secType", "") or "")
                    .strip()
                    .upper(),
                    "currency": str(getattr(contract, "currency", "") or "")
                    .strip()
                    .upper(),
                    "exchange": str(getattr(contract, "exchange", "") or "")
                    .strip()
                    .upper(),
                    "con_id": int(getattr(contract, "conId", 0) or 0),
                    "signed_quantity": signed_quantity,
                    "side": side,
                    "volume": abs(signed_quantity),
                    "average_cost": float(source_row.get("avg_cost") or 0.0),
                }
            )

        return result

    @staticmethod
    def _build_symbol_name_from_order_row(
        order_row: dict[str, Any],
    ) -> str:
        """
        Побудувати LGE symbol name зі scalar open-order row.
        """
        symbol = str(order_row.get("symbol") or "").strip().upper()
        currency = str(order_row.get("currency") or "").strip().upper()
        sec_type = str(order_row.get("sec_type") or "").strip().upper()

        if sec_type == "CASH" and currency:
            return f"{symbol}{currency}"

        return symbol

    @staticmethod
    def _normalize_forex_quote_symbols(
        symbol_names: list[str],
    ) -> list[str]:
        """Return unique canonical six-letter Forex symbols."""
        result: list[str] = []

        for value in symbol_names:
            symbol = str(value or "").strip().upper().replace("/", "")
            symbol = symbol.replace(".", "")

            if len(symbol) != 6 or not symbol.isalpha():
                continue

            if symbol not in result:
                result.append(symbol)

        return result

    def _next_market_data_request_id(self) -> int:
        """Allocate one request id from the market-data namespace."""
        request_id = self._market_data_req_id
        self._market_data_req_id += 1
        return request_id

    def _cancel_forex_quote_subscription(
        self,
        symbol_name: str,
    ) -> None:
        """Cancel and forget one streaming Forex quote subscription."""
        symbol = str(symbol_name or "").strip().upper()
        request_id = self._market_data_requests_by_symbol.pop(symbol, None)

        if request_id is None:
            return

        try:
            self._client.cancelMktData(request_id)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "IB cancelMktData failed | symbol=%s | reqId=%s | error=%s",
                symbol,
                request_id,
                exc,
            )
        finally:
            self._wrapper.unregister_market_data_request(request_id)

    def _cancel_all_forex_quote_subscriptions(self) -> None:
        """Cancel every active quote subscription owned by this adapter."""
        with self._market_data_lock:
            symbols = list(self._market_data_requests_by_symbol)

            for symbol in symbols:
                self._cancel_forex_quote_subscription(symbol)

            self._wrapper.clear_market_data_requests()

    def _sync_forex_quote_subscriptions(
        self,
        symbol_names: list[str],
    ) -> None:
        """Match streaming subscriptions to the requested symbol set."""
        desired_symbols = set(symbol_names)

        with self._market_data_lock:
            stale_symbols = set(self._market_data_requests_by_symbol) - (
                desired_symbols
            )

            for symbol in sorted(stale_symbols):
                self._cancel_forex_quote_subscription(symbol)

            if not desired_symbols:
                return

            if not self._market_data_delayed_mode_requested:
                try:
                    self._client.reqMarketDataType(3)
                    self._market_data_delayed_mode_requested = True
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning(
                        "IB reqMarketDataType failed: %s",
                        exc,
                    )

            for symbol in sorted(desired_symbols):
                if symbol in self._market_data_requests_by_symbol:
                    continue

                base_symbol, quote_symbol = self._split_forex_symbol(symbol)
                contract = self._build_forex_contract(
                    base_symbol=base_symbol,
                    quote_symbol=quote_symbol,
                )
                request_id = self._next_market_data_request_id()
                self._market_data_requests_by_symbol[symbol] = request_id
                self._wrapper.register_market_data_request(
                    request_id,
                    symbol,
                )

                try:
                    self._client.reqMktData(
                        request_id,
                        contract,
                        "",
                        False,
                        False,
                        [],
                    )
                except Exception:
                    self._market_data_requests_by_symbol.pop(symbol, None)
                    self._wrapper.unregister_market_data_request(request_id)
                    raise

                self._logger.info(
                    "IB Forex quote subscribed | symbol=%s | reqId=%s",
                    symbol,
                    request_id,
                )

    @staticmethod
    def _quote_has_bid_and_ask(row: dict[str, Any]) -> bool:
        """Return whether one quote row can price BUY and SELL legs."""
        return row.get("bid") is not None and row.get("ask") is not None

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
        wait_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Synchronize subscriptions and return cached Forex quotes."""
        symbols = self._normalize_forex_quote_symbols(symbol_names)
        captured_utc = datetime.now(UTC).replace(microsecond=0).isoformat()

        if not self._connected:
            return {
                "captured_utc": captured_utc,
                "complete": False,
                "quotes": {},
                "subscribed_symbols": [],
            }

        self._wrapper.market_data_event.clear()
        self._sync_forex_quote_subscriptions(symbols)

        timeout = (
            IB_MARKET_DATA_TIMEOUT_SECONDS
            if wait_timeout is None
            else max(float(wait_timeout), 0.0)
        )
        deadline = time.monotonic() + timeout

        while symbols:
            quotes = self._wrapper.get_market_data_snapshot(symbols)

            if all(
                self._quote_has_bid_and_ask(quotes.get(symbol) or {})
                for symbol in symbols
            ):
                break

            remaining = deadline - time.monotonic()

            if remaining <= 0.0:
                break

            self._wrapper.market_data_event.wait(
                timeout=min(remaining, 0.25),
            )
            self._wrapper.market_data_event.clear()

        quotes = self._wrapper.get_market_data_snapshot(symbols)
        complete = all(
            self._quote_has_bid_and_ask(quotes.get(symbol) or {}) for symbol in symbols
        )

        return {
            "captured_utc": (datetime.now(UTC).replace(microsecond=0).isoformat()),
            "complete": complete,
            "quotes": quotes,
            "subscribed_symbols": sorted(self._market_data_requests_by_symbol),
        }

    def get_historical_bars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: IBHistoryProgressCallback | None = None,
    ) -> IBHistoryDownloadResult:
        """Download normalized IB Forex MIDPOINT bars in UTC."""
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        symbol = str(symbol_name or "").strip().upper()
        frame = str(timeframe or "").strip().upper()
        if frame not in IB_HISTORY_BAR_SIZE_BY_TIMEFRAME:
            raise ValueError(f"Unsupported IB timeframe: {timeframe}")

        start = self._require_utc_datetime(start_utc, "start_utc")
        end = self._require_utc_datetime(end_utc, "end_utc")
        if start >= end:
            raise ValueError("IB history start must be before end")

        base_symbol, quote_symbol = self._split_forex_symbol(symbol)
        contract = self._build_forex_contract(base_symbol, quote_symbol)
        bar_size = IB_HISTORY_BAR_SIZE_BY_TIMEFRAME[frame]
        duration = IB_HISTORY_DURATION_BY_TIMEFRAME[frame]
        bar_seconds = IB_HISTORY_BAR_SECONDS_BY_TIMEFRAME[frame]
        bars_by_timestamp: dict[int, IBHistoricalBar] = {}
        request_end = end
        request_count = 0
        consecutive_empty_requests = 0
        empty_chunk_seconds = IB_HISTORY_EMPTY_CHUNK_SECONDS_BY_TIMEFRAME[frame]

        with self._historical_data_lock:
            while request_end >= start:
                if request_count >= IB_HISTORY_MAX_REQUESTS:
                    raise RuntimeError("IB historical request safety limit exceeded")
                request_count += 1
                try:
                    raw_bars = self._request_historical_chunk(
                        contract=contract,
                        end_utc=request_end,
                        duration=duration,
                        bar_size=bar_size,
                    )
                except RuntimeError as exc:
                    if not is_ib_historical_no_data_error(str(exc)):
                        raise
                    raw_bars = []

                decoded = [decode_ib_historical_bar(bar) for bar in raw_bars]
                if not decoded:
                    consecutive_empty_requests += 1
                    if (
                        consecutive_empty_requests
                        > IB_HISTORY_MAX_CONSECUTIVE_EMPTY_REQUESTS
                    ):
                        raise RuntimeError(
                            "IB historical data remained empty for too many "
                            "consecutive chunks"
                        )
                    next_end = request_end - timedelta(seconds=empty_chunk_seconds)
                    if next_end < start:
                        break
                    request_end = next_end
                    time.sleep(IB_HISTORY_REQUEST_DELAY_SECONDS)
                    continue

                consecutive_empty_requests = 0
                decoded.sort(key=lambda item: item.timestamp)
                for bar in decoded:
                    if not start <= bar.timestamp <= end:
                        continue
                    timestamp = int(bar.timestamp.timestamp())
                    existing = bars_by_timestamp.get(timestamp)
                    if existing is not None and existing != bar:
                        raise RuntimeError(
                            "IB history contains conflicting duplicate timestamp"
                        )
                    bars_by_timestamp[timestamp] = bar

                earliest = decoded[0].timestamp
                if progress_callback is not None:
                    progress_callback(
                        request_count,
                        len(bars_by_timestamp),
                        earliest,
                    )
                if earliest <= start:
                    break
                next_end = earliest - timedelta(seconds=bar_seconds)
                if next_end >= request_end:
                    raise RuntimeError("IB historical pagination did not move backward")
                request_end = next_end
                time.sleep(IB_HISTORY_REQUEST_DELAY_SECONDS)

        bars = tuple(bars_by_timestamp[key] for key in sorted(bars_by_timestamp))
        return IBHistoryDownloadResult(
            broker="IB",
            symbol=symbol,
            timeframe=frame,
            requested_start_utc=start,
            requested_end_utc=end,
            bars=bars,
            request_count=request_count,
        )

    def _request_historical_chunk(
        self,
        *,
        contract: Contract,
        end_utc: datetime,
        duration: str,
        bar_size: str,
    ) -> list[object]:
        request_id = self._next_historical_data_request_id()
        self._wrapper.start_historical_data_request(request_id)
        completed = False
        try:
            self._client.reqHistoricalData(
                request_id,
                contract,
                format_ib_historical_end_datetime(end_utc),
                duration,
                bar_size,
                "MIDPOINT",
                0,
                2,
                False,
                [],
            )
            completed = self._wrapper.historical_data_event.wait(
                timeout=IB_HISTORY_TIMEOUT_SECONDS
            )
            bars, error_text = self._wrapper.get_historical_data_snapshot()
            if error_text:
                raise RuntimeError(error_text)
            if not completed:
                raise RuntimeError("IB historical data request timed out")
            return bars
        finally:
            if not completed:
                try:
                    self._client.cancelHistoricalData(request_id)
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning(
                        "IB cancelHistoricalData failed: %s",
                        exc,
                    )
            self._wrapper.clear_historical_data_request()

    def _next_historical_data_request_id(self) -> int:
        self._historical_data_req_id += 1
        return self._historical_data_req_id

    @staticmethod
    def _require_utc_datetime(value: datetime, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{field_name} must be datetime")
        if value.tzinfo is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    def get_positions(self) -> list[BrokerPosition]:
        """
        Отримати відкриті IB positions у canonical форматі.
        """
        if not self._connected:
            self._logger.warning("IB get_positions called while disconnected.")
            return []

        with self._positions_lock:
            self._wrapper.position_event.clear()
            self._wrapper.positions.clear()

            self._logger.info("Requesting IB positions...")

            finished = False

            try:
                self._client.reqPositions()

                finished = self._wrapper.position_event.wait(
                    timeout=IB_POSITIONS_TIMEOUT_SECONDS,
                )
            finally:
                try:
                    self._client.cancelPositions()
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning(
                        "cancelPositions failed: %s",
                        exc,
                    )

            if not finished:
                self._logger.error("IB positions timeout.")
                return []

            position_rows = [
                dict(position_row) for position_row in self._wrapper.positions
            ]

        portfolio_by_id = self._request_portfolio_by_position_id(
            position_rows,
        )

        pnl_by_id = self._request_pnl_by_position_id(
            position_rows,
        )

        sl_tp_by_id = self._request_open_orders_by_position_id(
            position_rows,
        )

        execution_time_by_id = self._request_execution_times_by_position_id(
            position_rows,
        )

        return self._build_positions(
            position_rows=position_rows,
            portfolio_by_id=portfolio_by_id,
            pnl_by_id=pnl_by_id,
            sl_tp_by_id=sl_tp_by_id,
            execution_time_by_id=execution_time_by_id,
        )

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ) -> dict[str, Any]:
        """
        Відправити IB Forex MARKET order.

        RoadMap86:
        - без SL/TP: звичайний MARKET order, як у RoadMap84;
        - з SL/TP: parent MARKET + attached child STP/LMT orders.
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        side_norm = str(side or "").strip().upper()
        if side_norm not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported IB order side: {side}")

        quantity_float = float(quantity)
        if quantity_float <= 0.0:
            raise ValueError("IB order quantity must be positive")

        stop_loss_price = self._normalize_optional_ib_price(stop_loss)
        take_profit_price = self._normalize_optional_ib_price(take_profit)

        self._validate_ib_sl_tp_prices(
            side=side_norm,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
        )

        base_symbol, quote_symbol = self._split_forex_symbol(symbol_name)
        contract = self._build_forex_contract(base_symbol, quote_symbol)

        child_action = "SELL" if side_norm == "BUY" else "BUY"
        has_children = stop_loss_price is not None or take_profit_price is not None

        parent_order_id = self._get_next_order_id()
        parent_order = self._build_market_order(
            action=side_norm,
            quantity=quantity_float,
            transmit=not has_children,
        )
        control_mode = (
            get_broker_order_control_mode(comment) or ORDER_CONTROL_MODE_MANUAL
        )
        comment_clean = build_broker_order_comment(comment, control_mode)
        parent_order.orderRef = comment_clean

        orders_to_place: list[tuple[int, Order]] = [(parent_order_id, parent_order)]

        child_order_ids: list[int] = []
        take_profit_order_id: int | None = None
        stop_loss_order_id: int | None = None

        if take_profit_price is not None:
            take_profit_order_id = self._get_next_order_id()
            take_profit_order = self._build_limit_order(
                action=child_action,
                quantity=quantity_float,
                limit_price=take_profit_price,
                parent_id=parent_order_id,
                transmit=False,
            )
            take_profit_order.orderRef = comment_clean
            orders_to_place.append((take_profit_order_id, take_profit_order))
            child_order_ids.append(take_profit_order_id)

        if stop_loss_price is not None:
            stop_loss_order_id = self._get_next_order_id()
            stop_loss_order = self._build_stop_order(
                action=child_action,
                quantity=quantity_float,
                stop_price=stop_loss_price,
                parent_id=parent_order_id,
                transmit=False,
            )
            stop_loss_order.orderRef = comment_clean
            orders_to_place.append((stop_loss_order_id, stop_loss_order))
            child_order_ids.append(stop_loss_order_id)

        if has_children:
            last_order_id = orders_to_place[-1][0]
            for order_id, order in orders_to_place:
                order.transmit = order_id == last_order_id

        active_order_ids = {order_id for order_id, _order in orders_to_place}

        self._wrapper.order_event.clear()
        self._wrapper.open_orders.clear()
        self._wrapper.order_statuses.clear()
        self._wrapper.order_errors.clear()
        self._wrapper.active_order_id = parent_order_id
        self._wrapper.active_order_ids = set(active_order_ids)

        self._logger.warning(
            "Placing IB MARKET order | parentOrderId=%s | symbol=%s.%s | "
            "side=%s | quantity=%s | stop_loss=%s | take_profit=%s | "
            "child_order_ids=%s | comment=%s",
            parent_order_id,
            base_symbol,
            quote_symbol,
            side_norm,
            quantity_float,
            stop_loss_price,
            take_profit_price,
            child_order_ids,
            comment_clean,
        )

        try:
            for order_id, order in orders_to_place:
                self._client.placeOrder(order_id, contract, order)

            finished = self._wrapper.order_event.wait(
                timeout=IB_ORDER_TIMEOUT_SECONDS,
            )
        finally:
            self._wrapper.active_order_id = None
            self._wrapper.active_order_ids.clear()

        if self._wrapper.order_errors:
            raise RuntimeError("; ".join(self._wrapper.order_errors))

        status_row = self._get_last_order_status(parent_order_id)
        status_text = str(status_row.get("status", "") or "").strip().upper()

        if not finished and status_text != "FILLED":
            raise IBMarketOrderTimeoutError(
                order_id=parent_order_id,
                symbol_name=f"{base_symbol}{quote_symbol}",
                side=side_norm,
                quantity=quantity_float,
                status=status_text,
                filled=float(status_row.get("filled", 0.0) or 0.0),
                remaining=float(status_row.get("remaining", 0.0) or 0.0),
                child_order_ids=child_order_ids,
                stop_loss_order_id=stop_loss_order_id,
                take_profit_order_id=take_profit_order_id,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
                current_client_id=self._client_id,
                comment=comment_clean,
            )

        if status_text != "FILLED":
            raise RuntimeError(f"IB MARKET order was not filled: {status_text}")

        return {
            "broker": "IB",
            "order_id": str(parent_order_id),
            "broker_order_id": str(parent_order_id),
            "parent_order_id": str(parent_order_id),
            "child_order_ids": [str(order_id) for order_id in child_order_ids],
            "stop_loss_order_id": (
                None if stop_loss_order_id is None else str(stop_loss_order_id)
            ),
            "take_profit_order_id": (
                None if take_profit_order_id is None else str(take_profit_order_id)
            ),
            "current_client_id": int(self._client_id),
            "symbol_name": f"{base_symbol}{quote_symbol}",
            "side": side_norm,
            "quantity": quantity_float,
            "status": status_text,
            "filled": float(status_row.get("filled", 0.0) or 0.0),
            "remaining": float(status_row.get("remaining", 0.0) or 0.0),
            "avg_fill_price": float(status_row.get("avg_fill_price", 0.0) or 0.0),
            "control_mode": control_mode,
            "display_comment": strip_broker_order_identity(comment_clean),
            "broker_comment": comment_clean,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "open_orders": list(self._wrapper.open_orders),
            "order_statuses": list(self._wrapper.order_statuses),
        }

    def close_position(
        self,
        position_id: str,
        quantity: float | None = None,
        comment: str = "LGE manual close",
    ) -> dict[str, Any]:
        """
        Закрити IB Forex position через протилежний MARKET order.

        IB не має cTrader-style positionId.
        Наш runtime position_id має вигляд:
        IB:<account_id>:<symbol_name>
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        position_id_clean = str(position_id or "").strip()

        if not position_id_clean:
            raise ValueError("IB position id is empty")

        positions_before = self.get_positions()

        target_position = None

        for position in positions_before:
            if str(position.position_id) == position_id_clean:
                target_position = position
                break

        if target_position is None:
            raise RuntimeError(f"IB position was not found: {position_id_clean}")

        position_side = str(target_position.side or "").strip().upper()

        if position_side == "BUY":
            close_side = "SELL"
        elif position_side == "SELL":
            close_side = "BUY"
        else:
            raise RuntimeError(f"Unsupported IB position side: {target_position.side}")

        position_volume = float(target_position.volume or 0.0)

        if position_volume <= 0.0:
            raise RuntimeError(
                f"IB position volume is not positive: {position_id_clean}"
            )

        close_quantity = position_volume

        if quantity is not None:
            close_quantity = float(quantity)

        if close_quantity <= 0.0:
            raise ValueError("IB close quantity must be positive")

        if close_quantity > position_volume:
            raise ValueError("IB close quantity cannot be greater than position volume")

        cancelled_order_ids = self._cancel_related_sl_tp_open_orders(
            position_id=position_id_clean,
        )

        broker_result = self.place_market_order(
            symbol_name=target_position.symbol_name,
            side=close_side,
            quantity=close_quantity,
            stop_loss=None,
            take_profit=None,
            comment=comment,
        )

        positions_after = self.get_positions()

        still_open = any(
            str(position.position_id) == position_id_clean
            for position in positions_after
        )

        return {
            "broker": "IB",
            "broker_position_id": position_id_clean,
            "symbol_name": target_position.symbol_name,
            "position_side": position_side,
            "close_side": close_side,
            "close_quantity": close_quantity,
            "closed": not still_open,
            "cancelled_order_ids": [str(order_id) for order_id in cancelled_order_ids],
            "broker_result": broker_result,
        }

    @staticmethod
    def _normalize_sl_tp_operation_status(
        value: Any,
    ) -> str:
        """
        Нормалізувати IB order status для confirmation policy.
        """
        return "".join(str(value or "").strip().upper().split())

    @classmethod
    def build_sl_tp_operation_action_result(
        cls,
        *,
        action: str,
        leg: str,
        order_id: int | None,
        operation_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Оцінити broker confirmation однієї SL/TP execution action.
        """
        action_name = str(action or "").strip().upper()
        leg_name = str(leg or "").strip().upper()

        allowed_actions = {
            IB_PROTECTION_ACTION_KEEP,
            IB_PROTECTION_ACTION_MODIFY,
            IB_PROTECTION_ACTION_CANCEL,
            IB_PROTECTION_ACTION_CREATE,
            IB_PROTECTION_ACTION_BLOCK,
        }

        if action_name not in allowed_actions:
            raise ValueError(f"Unsupported IB SL/TP operation action: {action}")

        if not leg_name:
            raise ValueError("IB SL/TP operation leg is empty")

        if action_name == IB_PROTECTION_ACTION_KEEP:
            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": order_id,
                "confirmed": True,
                "terminal": True,
                "status": "KEEP",
                "callback_received": False,
                "open_order_received": False,
                "status_received": False,
                "cancel_confirmed": False,
                "errors": [],
            }

        if action_name == IB_PROTECTION_ACTION_BLOCK:
            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": order_id,
                "confirmed": False,
                "terminal": True,
                "status": "BLOCKED",
                "callback_received": False,
                "open_order_received": False,
                "status_received": False,
                "cancel_confirmed": False,
                "errors": [],
            }

        try:
            normalized_order_id = int(order_id or 0)
        except (TypeError, ValueError):
            normalized_order_id = 0

        if normalized_order_id <= 0:
            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": order_id,
                "confirmed": False,
                "terminal": True,
                "status": "ORDER_ID_MISSING",
                "callback_received": False,
                "open_order_received": False,
                "status_received": False,
                "cancel_confirmed": False,
                "errors": [],
            }

        open_orders = dict(operation_snapshot.get("open_orders") or {})
        statuses = dict(operation_snapshot.get("statuses") or {})
        cancelled_order_ids = set(
            operation_snapshot.get("cancelled_order_ids") or set()
        )
        errors_by_order_id = dict(operation_snapshot.get("errors") or {})

        open_order_row = dict(open_orders.get(normalized_order_id) or {})
        status_row = dict(statuses.get(normalized_order_id) or {})

        error_messages = [
            str(message)
            for message in (errors_by_order_id.get(normalized_order_id) or [])
        ]

        open_order_received = normalized_order_id in open_orders
        status_received = normalized_order_id in statuses
        cancel_confirmed = normalized_order_id in cancelled_order_ids

        broker_status = str(
            status_row.get("status") or open_order_row.get("status") or ""
        ).strip()

        normalized_status = cls._normalize_sl_tp_operation_status(broker_status)

        callback_received = any(
            (
                open_order_received,
                status_received,
                cancel_confirmed,
                bool(error_messages),
            )
        )

        if error_messages:
            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": normalized_order_id,
                "confirmed": False,
                "terminal": True,
                "status": broker_status or "ERROR",
                "callback_received": callback_received,
                "open_order_received": open_order_received,
                "status_received": status_received,
                "cancel_confirmed": cancel_confirmed,
                "errors": error_messages,
            }

        if action_name == IB_PROTECTION_ACTION_CANCEL:
            if (
                cancel_confirmed
                or normalized_status in IB_SL_TP_OPERATION_CANCELLED_STATUSES
            ):
                return {
                    "action": action_name,
                    "leg": leg_name,
                    "order_id": normalized_order_id,
                    "confirmed": True,
                    "terminal": True,
                    "status": broker_status or "Cancelled",
                    "callback_received": callback_received,
                    "open_order_received": open_order_received,
                    "status_received": status_received,
                    "cancel_confirmed": True,
                    "errors": [],
                }

            if normalized_status in IB_SL_TP_OPERATION_FAILURE_STATUSES:
                return {
                    "action": action_name,
                    "leg": leg_name,
                    "order_id": normalized_order_id,
                    "confirmed": False,
                    "terminal": True,
                    "status": broker_status,
                    "callback_received": callback_received,
                    "open_order_received": open_order_received,
                    "status_received": status_received,
                    "cancel_confirmed": False,
                    "errors": [],
                }

            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": normalized_order_id,
                "confirmed": False,
                "terminal": False,
                "status": broker_status or "WAITING_CONFIRMATION",
                "callback_received": callback_received,
                "open_order_received": open_order_received,
                "status_received": status_received,
                "cancel_confirmed": False,
                "errors": [],
            }

        if normalized_status in IB_SL_TP_OPERATION_ACCEPTED_STATUSES:
            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": normalized_order_id,
                "confirmed": True,
                "terminal": True,
                "status": broker_status,
                "callback_received": callback_received,
                "open_order_received": open_order_received,
                "status_received": status_received,
                "cancel_confirmed": False,
                "errors": [],
            }

        if (
            normalized_status in IB_SL_TP_OPERATION_CANCELLED_STATUSES
            or normalized_status in IB_SL_TP_OPERATION_FAILURE_STATUSES
        ):
            return {
                "action": action_name,
                "leg": leg_name,
                "order_id": normalized_order_id,
                "confirmed": False,
                "terminal": True,
                "status": broker_status,
                "callback_received": callback_received,
                "open_order_received": open_order_received,
                "status_received": status_received,
                "cancel_confirmed": cancel_confirmed,
                "errors": [],
            }

        return {
            "action": action_name,
            "leg": leg_name,
            "order_id": normalized_order_id,
            "confirmed": False,
            "terminal": False,
            "status": broker_status or "WAITING_CONFIRMATION",
            "callback_received": callback_received,
            "open_order_received": open_order_received,
            "status_received": status_received,
            "cancel_confirmed": cancel_confirmed,
            "errors": [],
        }

    def _wait_for_sl_tp_operation_results(
        self,
        *,
        execution_actions: list[dict[str, Any]],
        timeout: float = IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    ) -> list[dict[str, Any]]:
        """
        Дочекатися terminal broker confirmation для всіх actions.

        Метод не виконує broker orders. Він лише читає callback state.
        """
        try:
            timeout_seconds = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid IB SL/TP operation timeout: {timeout}") from exc

        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0.0:
            raise ValueError(
                f"Invalid IB SL/TP operation timeout: " f"{timeout_seconds}"
            )

        deadline = time.monotonic() + timeout_seconds

        while True:
            self._wrapper.sl_tp_operation_event.clear()

            operation_snapshot = self._wrapper.get_sl_tp_operation_snapshot()

            results = self.build_sl_tp_operation_results(
                execution_actions=execution_actions,
                operation_snapshot=operation_snapshot,
            )

            if all(bool(result.get("terminal")) for result in results):
                return results

            remaining_seconds = deadline - time.monotonic()

            if remaining_seconds <= 0.0:
                timeout_results: list[dict[str, Any]] = []

                for result in results:
                    timeout_result = dict(result)

                    if not bool(timeout_result.get("terminal")):
                        timeout_result.update(
                            {
                                "confirmed": False,
                                "terminal": True,
                                "status": "TIMEOUT",
                                "timeout": True,
                            }
                        )

                    timeout_results.append(timeout_result)

                return timeout_results

            self._wrapper.sl_tp_operation_event.wait(
                timeout=remaining_seconds,
            )

    @classmethod
    def build_sl_tp_operation_results(
        cls,
        *,
        execution_actions: list[dict[str, Any]],
        operation_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Оцінити confirmation state усіх SL/TP operation actions.
        """
        if not execution_actions:
            raise ValueError("IB SL/TP execution actions are empty")

        results: list[dict[str, Any]] = []
        seen_legs: set[str] = set()

        for action_row in execution_actions:
            action = str(action_row.get("action") or "").strip().upper()

            leg = str(action_row.get("leg") or "").strip().upper()

            if not leg:
                raise ValueError("IB SL/TP execution action leg is empty")

            if leg in seen_legs:
                raise ValueError("Duplicate IB SL/TP execution action leg: " f"{leg}")

            seen_legs.add(leg)

            result = cls.build_sl_tp_operation_action_result(
                action=action,
                leg=leg,
                order_id=action_row.get("order_id"),
                operation_snapshot=operation_snapshot,
            )

            if bool(action_row.get("require_transmit_true")):
                order_id = int(action_row.get("order_id") or 0)
                open_orders = dict(operation_snapshot.get("open_orders") or {})
                open_order_row = dict(open_orders.get(order_id) or {})
                transmit = bool(open_order_row.get("transmit"))

                result["require_transmit_true"] = True
                result["transmit"] = transmit

                if bool(result.get("confirmed")) and (
                    not bool(result.get("open_order_received")) or not transmit
                ):
                    result.update(
                        {
                            "confirmed": False,
                            "terminal": False,
                            "status": "WAITING_TRANSMIT_CONFIRMATION",
                        }
                    )

            result["timeout"] = False
            results.append(result)

        return results

    @classmethod
    def build_sl_tp_execution_actions(
        cls,
        *,
        plan: dict[str, Any],
        create_order_ids: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Перетворити IB SL/TP planner result на execution actions.

        Метод не виконує broker-викликів і не отримує nextValidId.
        Для CREATE order ids мають бути передані зовні.
        """
        plan_data = dict(plan or {})
        create_ids = dict(create_order_ids or {})

        if bool(plan_data.get("blocked")):
            blocked_flags = list(plan_data.get("blocked_flags") or [])

            blocked_details = ", ".join(str(flag) for flag in blocked_flags)

            reason = str(plan_data.get("reason") or "").strip()

            if blocked_details:
                reason = f"{reason} blocked_flags={blocked_details}".strip()

            raise RuntimeError(reason or "IB SL/TP execution plan is blocked")

        oca_relink_legs = {
            str(leg_name).strip().lower()
            for leg_name in (plan_data.get("oca_relink_legs") or [])
        }
        leg_definitions = (
            {
                "key": "stop_loss",
                "name": "STOP_LOSS",
                "order_type": "STP",
            },
            {
                "key": "take_profit",
                "name": "TAKE_PROFIT",
                "order_type": "LMT",
            },
        )

        allowed_actions = {
            IB_PROTECTION_ACTION_KEEP,
            IB_PROTECTION_ACTION_MODIFY,
            IB_PROTECTION_ACTION_CANCEL,
            IB_PROTECTION_ACTION_CREATE,
        }

        execution_actions: list[dict[str, Any]] = []
        broker_order_ids: set[int] = set()

        for leg_definition in leg_definitions:
            leg_key = str(leg_definition["key"])
            leg_name = str(leg_definition["name"])
            order_type = str(leg_definition["order_type"])

            planner_action = (
                str(plan_data.get(f"{leg_key}_action") or "").strip().upper()
            )

            if planner_action not in allowed_actions:
                raise ValueError(
                    "Unsupported IB SL/TP planner action | "
                    f"leg={leg_name} | action={planner_action}"
                )

            oca_relink = leg_key in oca_relink_legs
            execution_action = planner_action

            if planner_action == IB_PROTECTION_ACTION_KEEP and oca_relink:
                execution_action = IB_PROTECTION_ACTION_MODIFY

            existing_order_id = int(plan_data.get(f"{leg_key}_order_id") or 0)

            if execution_action == IB_PROTECTION_ACTION_CREATE:
                order_id = int(create_ids.get(leg_key) or 0)
            elif execution_action in {
                IB_PROTECTION_ACTION_MODIFY,
                IB_PROTECTION_ACTION_CANCEL,
            }:
                order_id = existing_order_id
            else:
                order_id = existing_order_id if existing_order_id > 0 else None

            broker_call_required = execution_action in {
                IB_PROTECTION_ACTION_MODIFY,
                IB_PROTECTION_ACTION_CANCEL,
                IB_PROTECTION_ACTION_CREATE,
            }

            if broker_call_required:
                if order_id is None or int(order_id) <= 0:
                    raise RuntimeError(
                        "IB SL/TP execution order id is missing | "
                        f"leg={leg_name} | "
                        f"action={execution_action}"
                    )

                normalized_order_id = int(order_id)

                if normalized_order_id in broker_order_ids:
                    raise RuntimeError(
                        "Duplicate IB SL/TP execution order id: "
                        f"{normalized_order_id}"
                    )

                broker_order_ids.add(normalized_order_id)
                order_id = normalized_order_id

            price = cls._normalize_optional_ib_price(plan_data.get(f"new_{leg_key}"))

            if (
                execution_action
                in {
                    IB_PROTECTION_ACTION_MODIFY,
                    IB_PROTECTION_ACTION_CREATE,
                }
                and price is None
            ):
                raise RuntimeError(
                    "IB SL/TP execution price is missing | "
                    f"leg={leg_name} | "
                    f"action={execution_action}"
                )

            contract_object = plan_data.get(f"{leg_key}_contract_object")
            order_object = plan_data.get(f"{leg_key}_order_object")

            if execution_action == IB_PROTECTION_ACTION_MODIFY:
                if contract_object is None:
                    raise RuntimeError(
                        "IB SL/TP Contract object is missing | " f"leg={leg_name}"
                    )

                if order_object is None:
                    raise RuntimeError(
                        "IB SL/TP Order object is missing | " f"leg={leg_name}"
                    )

            execution_actions.append(
                {
                    "leg": leg_name,
                    "leg_key": leg_key,
                    "order_type": order_type,
                    "planner_action": planner_action,
                    "action": execution_action,
                    "order_id": order_id,
                    "price": price,
                    "broker_call_required": broker_call_required,
                    "oca_relink": oca_relink,
                    "contract_object": contract_object,
                    "order_object": order_object,
                }
            )

        return execution_actions

    @classmethod
    def build_sl_tp_broker_order_payloads(
        cls,
        *,
        execution_actions: list[dict[str, Any]],
        account_id: str,
        protective_action: str,
        position_volume: float,
        position_contract_object: Contract,
        requires_oca_group: bool,
        oca_group: str | None = None,
        order_ref: str = "",
    ) -> list[dict[str, Any]]:
        """
        Побудувати broker Contract/Order payloads для IB SL/TP.

        Метод не викликає placeOrder() або cancelOrder().
        """
        if not execution_actions:
            raise ValueError("IB SL/TP execution actions are empty")

        account_id_clean = str(account_id or "").strip()

        if not account_id_clean:
            raise ValueError("IB SL/TP position account is empty")

        protective_action_clean = str(protective_action or "").strip().upper()

        if protective_action_clean not in {"BUY", "SELL"}:
            raise ValueError(
                "Unsupported IB SL/TP protective action: " f"{protective_action}"
            )

        try:
            position_volume_float = float(position_volume)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid IB SL/TP position volume: " f"{position_volume}"
            ) from exc

        if not math.isfinite(position_volume_float) or position_volume_float <= 0.0:
            raise ValueError(
                f"Invalid IB SL/TP position volume: " f"{position_volume_float}"
            )

        if position_contract_object is None:
            raise RuntimeError("IB SL/TP position Contract object is missing")

        requires_oca = bool(requires_oca_group)
        oca_group_clean = str(oca_group or "").strip()
        order_ref_clean = str(order_ref or "").strip()

        if requires_oca and not oca_group_clean:
            raise RuntimeError("IB SL/TP OCA group is missing")

        payloads: list[dict[str, Any]] = []
        place_payload_indexes: list[int] = []

        for source_action in execution_actions:
            action_row = dict(source_action)

            leg_name = str(action_row.get("leg") or "").strip().upper()

            order_type = str(action_row.get("order_type") or "").strip().upper()

            execution_action = str(action_row.get("action") or "").strip().upper()

            try:
                order_id = int(action_row.get("order_id") or 0)
            except (TypeError, ValueError):
                order_id = 0

            if leg_name not in {
                "STOP_LOSS",
                "TAKE_PROFIT",
            }:
                raise ValueError("Unsupported IB SL/TP execution leg: " f"{leg_name}")

            expected_order_type = "STP" if leg_name == "STOP_LOSS" else "LMT"

            if order_type != expected_order_type:
                raise RuntimeError(
                    "IB SL/TP execution order type mismatch | "
                    f"leg={leg_name} | "
                    f"expected={expected_order_type} | "
                    f"actual={order_type}"
                )

            payload_row = dict(action_row)
            payload_row.update(
                {
                    "broker_contract_object": None,
                    "broker_order_object": None,
                }
            )

            if execution_action in {
                IB_PROTECTION_ACTION_KEEP,
                IB_PROTECTION_ACTION_CANCEL,
            }:
                payloads.append(payload_row)
                continue

            if execution_action not in {
                IB_PROTECTION_ACTION_MODIFY,
                IB_PROTECTION_ACTION_CREATE,
            }:
                raise ValueError(
                    "Unsupported IB SL/TP broker payload action | "
                    f"leg={leg_name} | "
                    f"action={execution_action}"
                )

            if order_id <= 0:
                raise RuntimeError(
                    "IB SL/TP broker payload order id is missing | "
                    f"leg={leg_name} | "
                    f"action={execution_action}"
                )

            price = cls._normalize_optional_ib_price(action_row.get("price"))

            if price is None:
                raise RuntimeError(
                    "IB SL/TP broker payload price is missing | "
                    f"leg={leg_name} | "
                    f"action={execution_action}"
                )

            if execution_action == IB_PROTECTION_ACTION_MODIFY:
                broker_contract = action_row.get("contract_object")
                existing_order = action_row.get("order_object")

                if broker_contract is None:
                    raise RuntimeError(
                        "IB SL/TP modify Contract object is missing | "
                        f"leg={leg_name}"
                    )

                if existing_order is None:
                    raise RuntimeError(
                        "IB SL/TP modify Order object is missing | " f"leg={leg_name}"
                    )

                existing_order_type = (
                    str(
                        getattr(
                            existing_order,
                            "orderType",
                            "",
                        )
                        or ""
                    )
                    .strip()
                    .upper()
                )

                if existing_order_type != expected_order_type:
                    raise RuntimeError(
                        "IB SL/TP broker Order type mismatch | "
                        f"leg={leg_name} | "
                        f"expected={expected_order_type} | "
                        f"actual={existing_order_type}"
                    )

                existing_account = str(
                    getattr(
                        existing_order,
                        "account",
                        "",
                    )
                    or ""
                ).strip()

                if existing_account and existing_account != account_id_clean:
                    raise RuntimeError(
                        "IB SL/TP broker Order account mismatch | "
                        f"leg={leg_name} | "
                        f"expected={account_id_clean} | "
                        f"actual={existing_account}"
                    )

                existing_action = (
                    str(
                        getattr(
                            existing_order,
                            "action",
                            "",
                        )
                        or ""
                    )
                    .strip()
                    .upper()
                )

                if existing_action and existing_action != protective_action_clean:
                    raise RuntimeError(
                        "IB SL/TP broker Order action mismatch | "
                        f"leg={leg_name} | "
                        f"expected={protective_action_clean} | "
                        f"actual={existing_action}"
                    )

                broker_order = deepcopy(existing_order)

                if leg_name == "STOP_LOSS":
                    broker_order.auxPrice = price
                else:
                    broker_order.lmtPrice = price

            else:
                broker_contract = position_contract_object

                if leg_name == "STOP_LOSS":
                    broker_order = cls._build_stop_order(
                        action=protective_action_clean,
                        quantity=position_volume_float,
                        stop_price=price,
                        parent_id=0,
                        transmit=not requires_oca,
                    )
                else:
                    broker_order = cls._build_limit_order(
                        action=protective_action_clean,
                        quantity=position_volume_float,
                        limit_price=price,
                        parent_id=0,
                        transmit=not requires_oca,
                    )

            broker_order.orderId = order_id
            broker_order.account = account_id_clean
            broker_order.action = protective_action_clean
            broker_order.totalQuantity = position_volume_float

            current_order_ref = str(
                getattr(
                    broker_order,
                    "orderRef",
                    "",
                )
                or ""
            ).strip()

            if order_ref_clean:
                broker_order.orderRef = order_ref_clean
            elif not current_order_ref:
                broker_order.orderRef = IB_SL_TP_ORDER_REF

            if requires_oca:
                broker_order.ocaGroup = oca_group_clean
                broker_order.ocaType = IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK

            broker_order.transmit = True

            payload_row.update(
                {
                    "broker_contract_object": broker_contract,
                    "broker_order_object": broker_order,
                }
            )

            payloads.append(payload_row)
            place_payload_indexes.append(len(payloads) - 1)

        if requires_oca and len(place_payload_indexes) != 2:
            raise RuntimeError(
                "IB SL/TP OCA operation must contain " "exactly two placeOrder payloads"
            )

        return payloads

    def _allocate_sl_tp_create_order_ids(
        self,
        *,
        plan: dict[str, Any],
    ) -> dict[str, int]:
        """
        Зарезервувати nextValidId лише для planner CREATE actions.
        """
        plan_data = dict(plan or {})

        if bool(plan_data.get("blocked")):
            blocked_flags = list(plan_data.get("blocked_flags") or [])

            blocked_details = ", ".join(str(flag) for flag in blocked_flags)

            raise RuntimeError(
                "IB SL/TP create-order id allocation is blocked"
                + (f" | blocked_flags={blocked_details}" if blocked_details else "")
            )

        create_order_ids: dict[str, int] = {}

        leg_keys = (
            "stop_loss",
            "take_profit",
        )

        for leg_key in leg_keys:
            action = str(plan_data.get(f"{leg_key}_action") or "").strip().upper()

            if action == IB_PROTECTION_ACTION_CREATE:
                create_order_ids[leg_key] = self._get_next_order_id()

        return create_order_ids

    def _build_sl_tp_oca_group(
        self,
        *,
        execution_actions: list[dict[str, Any]],
    ) -> str:
        """
        Побудувати стабільну унікальну OCA group для двох legs.
        """
        broker_order_ids: list[int] = []

        for action_row in execution_actions:
            execution_action = str(action_row.get("action") or "").strip().upper()

            if execution_action not in {
                IB_PROTECTION_ACTION_MODIFY,
                IB_PROTECTION_ACTION_CREATE,
            }:
                continue

            try:
                order_id = int(action_row.get("order_id") or 0)
            except (TypeError, ValueError):
                order_id = 0

            if order_id <= 0:
                raise RuntimeError("IB SL/TP OCA order id is missing")

            broker_order_ids.append(order_id)

        unique_order_ids = sorted(set(broker_order_ids))

        if len(unique_order_ids) != 2:
            raise RuntimeError(
                "IB SL/TP OCA group requires exactly " "two placeOrder order ids"
            )

        return (
            f"{IB_SL_TP_OCA_GROUP_PREFIX}_"
            f"{self._client_id}_"
            f"{unique_order_ids[0]}_"
            f"{unique_order_ids[1]}"
        )

    def _prepare_sl_tp_execution(
        self,
        *,
        plan: dict[str, Any],
        account_id: str,
        protective_action: str,
        position_volume: float,
        position_contract_object: Contract,
        order_ref: str = "",
    ) -> dict[str, Any]:
        """
        Підготувати повний IB SL/TP execution package без broker calls.
        """
        plan_data = dict(plan or {})

        create_order_ids = self._allocate_sl_tp_create_order_ids(
            plan=plan_data,
        )

        execution_actions = self.build_sl_tp_execution_actions(
            plan=plan_data,
            create_order_ids=create_order_ids,
        )

        requires_oca_group = bool(plan_data.get("requires_oca_group"))

        oca_group: str | None = None

        if requires_oca_group:
            oca_group = self._build_sl_tp_oca_group(
                execution_actions=execution_actions,
            )

        broker_payloads = self.build_sl_tp_broker_order_payloads(
            execution_actions=execution_actions,
            account_id=account_id,
            protective_action=protective_action,
            position_volume=position_volume,
            position_contract_object=position_contract_object,
            requires_oca_group=requires_oca_group,
            oca_group=oca_group,
            order_ref=order_ref,
        )

        operation_order_ids = {
            int(payload["order_id"])
            for payload in broker_payloads
            if bool(payload.get("broker_call_required"))
        }

        if not operation_order_ids:
            raise RuntimeError(
                "IB SL/TP execution package contains " "no broker operations"
            )

        return {
            "create_order_ids": create_order_ids,
            "execution_actions": execution_actions,
            "oca_group": oca_group,
            "broker_payloads": broker_payloads,
            "operation_order_ids": operation_order_ids,
        }

    def _prepare_sl_tp_replacement_survivor_execution(
        self,
        *,
        plan: dict[str, Any],
        position_id: str,
        position_side: str,
        account_id: str,
        protective_action: str,
        position_volume: float,
        position_contract_object: Contract,
        virtual_leg_execution_guard: dict[str, Any] | None = None,
        order_ref: str = "",
    ) -> dict[str, Any]:
        """
        Підготувати staged replacement survivor для старої OCA-пари.
        """
        plan_data = dict(plan or {})

        position_id_clean = str(position_id or "").strip()
        position_side_clean = str(position_side or "").strip().upper()

        if not position_id_clean:
            raise ValueError("IB SL/TP replacement position id is empty")

        if position_side_clean not in {
            POSITION_SIDE_BUY,
            POSITION_SIDE_SELL,
        }:
            raise ValueError(
                "Invalid IB SL/TP replacement position side: " f"{position_side}"
            )

        if bool(plan_data.get("blocked")):
            raise RuntimeError("IB SL/TP replacement plan is blocked")

        survivor_leg = (
            str(plan_data.get("replacement_survivor_leg") or "").strip().lower()
        )
        cancel_leg = str(plan_data.get("replacement_cancel_leg") or "").strip().lower()

        valid_legs = {"stop_loss", "take_profit"}

        if survivor_leg not in valid_legs:
            raise RuntimeError("IB SL/TP replacement survivor leg is missing")

        if cancel_leg not in valid_legs or cancel_leg == survivor_leg:
            raise RuntimeError("IB SL/TP replacement cancel leg is invalid")

        survivor_action = (
            str(plan_data.get(f"{survivor_leg}_action") or "").strip().upper()
        )
        cancel_action = str(plan_data.get(f"{cancel_leg}_action") or "").strip().upper()

        if survivor_action not in {
            IB_PROTECTION_ACTION_KEEP,
            IB_PROTECTION_ACTION_MODIFY,
        }:
            raise RuntimeError(
                "IB SL/TP replacement survivor action is invalid | "
                f"action={survivor_action}"
            )

        if cancel_action != IB_PROTECTION_ACTION_CANCEL:
            raise RuntimeError(
                "IB SL/TP replacement cancel action is invalid | "
                f"action={cancel_action}"
            )

        replacement_price = self._normalize_optional_ib_price(
            plan_data.get(f"new_{survivor_leg}")
        )

        if replacement_price is None:
            raise RuntimeError("IB SL/TP replacement survivor price is missing")

        old_survivor_order_id = int(plan_data.get(f"{survivor_leg}_order_id") or 0)
        old_cancel_order_id = int(plan_data.get(f"{cancel_leg}_order_id") or 0)

        if old_survivor_order_id <= 0 or old_cancel_order_id <= 0:
            raise RuntimeError("IB SL/TP replacement old order id is missing")

        if old_survivor_order_id == old_cancel_order_id:
            raise RuntimeError("IB SL/TP replacement old order ids are duplicated")

        account_id_clean = str(account_id or "").strip()
        protective_action_clean = str(protective_action or "").strip().upper()
        position_volume_float = float(position_volume)

        if not account_id_clean:
            raise ValueError("IB SL/TP replacement account is empty")

        if protective_action_clean not in {"BUY", "SELL"}:
            raise ValueError(
                "Unsupported IB SL/TP replacement action: " f"{protective_action}"
            )

        if not math.isfinite(position_volume_float) or position_volume_float <= 0.0:
            raise ValueError(
                "Invalid IB SL/TP replacement position volume: "
                f"{position_volume_float}"
            )

        if position_contract_object is None:
            raise RuntimeError("IB SL/TP replacement Contract object is missing")

        replacement_order_id = self._get_next_order_id()

        if survivor_leg == "stop_loss":
            leg_name = "STOP_LOSS"
            order_type = "STP"
            staged_order = self._build_stop_order(
                action=protective_action_clean,
                quantity=position_volume_float,
                stop_price=replacement_price,
                parent_id=0,
                transmit=False,
            )
        else:
            leg_name = "TAKE_PROFIT"
            order_type = "LMT"
            staged_order = self._build_limit_order(
                action=protective_action_clean,
                quantity=position_volume_float,
                limit_price=replacement_price,
                parent_id=0,
                transmit=False,
            )

        staged_order.orderId = replacement_order_id
        staged_order.account = account_id_clean
        staged_order.orderRef = str(order_ref or "").strip() or IB_SL_TP_ORDER_REF
        staged_order.ocaGroup = ""
        staged_order.ocaType = 0
        staged_order.transmit = False

        active_order = deepcopy(staged_order)
        active_order.transmit = True

        replacement_action = {
            "leg": leg_name,
            "leg_key": survivor_leg,
            "order_type": order_type,
            "planner_action": survivor_action,
            "action": IB_PROTECTION_ACTION_CREATE,
            "order_id": replacement_order_id,
            "price": replacement_price,
            "broker_call_required": True,
            "replacement_survivor": True,
            "require_transmit_true": True,
        }
        cancel_action_row = {
            "leg": cancel_leg.upper(),
            "leg_key": cancel_leg,
            "planner_action": IB_PROTECTION_ACTION_CANCEL,
            "action": IB_PROTECTION_ACTION_CANCEL,
            "order_id": old_cancel_order_id,
            "broker_call_required": True,
            "replacement_old_oca_leg": True,
        }

        return {
            "create_order_ids": {survivor_leg: replacement_order_id},
            "execution_actions": [
                replacement_action,
                cancel_action_row,
            ],
            "oca_group": None,
            "replacement_survivor_leg": survivor_leg,
            "replacement_cancel_leg": cancel_leg,
            "replacement_order_id": replacement_order_id,
            "old_survivor_order_id": old_survivor_order_id,
            "old_cancel_order_id": old_cancel_order_id,
            "replacement_contract_object": position_contract_object,
            "replacement_staged_order_object": staged_order,
            "replacement_active_order_object": active_order,
            "operation_order_ids": {
                replacement_order_id,
                old_survivor_order_id,
                old_cancel_order_id,
            },
            "position_id": position_id_clean,
            "position_side": position_side_clean,
            "position_volume": position_volume_float,
            "virtual_leg_execution_guard": (
                dict(virtual_leg_execution_guard)
                if virtual_leg_execution_guard
                else None
            ),
        }

    def _wait_for_sl_tp_replacement_staged(
        self,
        *,
        order_id: int,
        leg: str,
        timeout: float = IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """
        Дочекатися завершення local validation для transmit=False order.

        Untransmitted IB order не повертається API як open order.
        Тому успіх визначається як відсутність callback-помилки
        протягом короткого settle interval.
        """
        timeout_seconds = float(timeout)

        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0.0:
            raise ValueError(f"Invalid IB SL/TP replacement timeout: {timeout_seconds}")

        settle_seconds = min(
            timeout_seconds,
            IB_SL_TP_REPLACEMENT_STAGE_SETTLE_SECONDS,
        )
        deadline = time.monotonic() + settle_seconds

        while True:
            self._wrapper.sl_tp_operation_event.clear()
            snapshot = self._wrapper.get_sl_tp_operation_snapshot()
            errors = [
                str(message)
                for message in (dict(snapshot.get("errors") or {}).get(order_id) or [])
            ]

            if errors:
                return {
                    "action": "STAGE_LOCAL",
                    "leg": leg,
                    "order_id": order_id,
                    "confirmed": False,
                    "terminal": True,
                    "status": "ERROR",
                    "timeout": False,
                    "errors": errors,
                }

            remaining_seconds = deadline - time.monotonic()

            if remaining_seconds <= 0.0:
                return {
                    "action": "STAGE_LOCAL",
                    "leg": leg,
                    "order_id": order_id,
                    "confirmed": True,
                    "terminal": True,
                    "status": "STAGED_LOCAL_NO_ERROR",
                    "timeout": False,
                    "errors": [],
                    "transmit": False,
                }

            self._wrapper.sl_tp_operation_event.wait(
                timeout=remaining_seconds,
            )

    def _execute_sl_tp_replacement_survivor_operation(
        self,
        *,
        execution_package: dict[str, Any],
        timeout: float = IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """
        Виконати staged replacement survivor для старої OCA-пари.
        """
        package = dict(execution_package or {})

        expected_position_id = str(package.get("position_id") or "").strip()
        expected_position_side = str(package.get("position_side") or "").strip().upper()
        expected_position_volume = float(package.get("position_volume") or 0.0)

        if not expected_position_id:
            raise RuntimeError("IB SL/TP replacement position id is missing")

        replacement_order_id = int(package.get("replacement_order_id") or 0)
        old_survivor_order_id = int(package.get("old_survivor_order_id") or 0)
        old_cancel_order_id = int(package.get("old_cancel_order_id") or 0)
        operation_order_ids = {
            int(order_id) for order_id in (package.get("operation_order_ids") or set())
        }

        expected_order_ids = {
            replacement_order_id,
            old_survivor_order_id,
            old_cancel_order_id,
        }

        if operation_order_ids != expected_order_ids or 0 in expected_order_ids:
            raise RuntimeError("IB SL/TP replacement operation order ids mismatch")

        replacement_contract = package.get("replacement_contract_object")
        staged_order = package.get("replacement_staged_order_object")
        active_order = package.get("replacement_active_order_object")
        survivor_leg = str(package.get("replacement_survivor_leg") or "").upper()
        cancel_leg = str(package.get("replacement_cancel_leg") or "").upper()

        if replacement_contract is None:
            raise RuntimeError("IB SL/TP replacement Contract object is missing")

        if staged_order is None or active_order is None:
            raise RuntimeError("IB SL/TP replacement Order object is missing")

        dispatched_calls: list[dict[str, Any]] = []
        action_results: list[dict[str, Any]] = []
        execution_guard_result: dict[str, Any] = {}
        old_cancel_requested = False

        self._wrapper.start_sl_tp_operation(operation_order_ids)

        try:
            self._client.placeOrder(
                replacement_order_id,
                replacement_contract,
                staged_order,
            )
            dispatched_calls.append(
                {
                    "call": "placeOrder",
                    "stage": "STAGE_LOCAL",
                    "leg": survivor_leg,
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "order_id": replacement_order_id,
                }
            )

            stage_result = self._wait_for_sl_tp_replacement_staged(
                order_id=replacement_order_id,
                leg=survivor_leg,
                timeout=timeout,
            )
            action_results.append(stage_result)

            if not bool(stage_result.get("confirmed")):
                raise RuntimeError(
                    "IB SL/TP replacement local stage was not confirmed | "
                    f"leg={survivor_leg} | "
                    f"status={stage_result.get('status')}"
                )

            self._client.cancelOrder(
                old_cancel_order_id,
                OrderCancel(),
            )
            old_cancel_requested = True
            dispatched_calls.append(
                {
                    "call": "cancelOrder",
                    "stage": "CANCEL_OLD_OCA",
                    "leg": cancel_leg,
                    "action": IB_PROTECTION_ACTION_CANCEL,
                    "order_id": old_cancel_order_id,
                }
            )

            old_cancel_actions = [
                {
                    "action": IB_PROTECTION_ACTION_CANCEL,
                    "leg": f"OLD_{survivor_leg}",
                    "order_id": old_survivor_order_id,
                },
                {
                    "action": IB_PROTECTION_ACTION_CANCEL,
                    "leg": f"OLD_{cancel_leg}",
                    "order_id": old_cancel_order_id,
                },
            ]
            old_cancel_results = self._wait_for_sl_tp_operation_results(
                execution_actions=old_cancel_actions,
                timeout=timeout,
            )
            action_results.extend(old_cancel_results)

            failed_old_legs = [
                str(result.get("leg") or "")
                for result in old_cancel_results
                if not bool(result.get("confirmed"))
            ]

            if failed_old_legs:
                raise RuntimeError(
                    "IB SL/TP old OCA cancellation was not confirmed | "
                    f"failed_legs={failed_old_legs}"
                )

            virtual_guard = package.get("virtual_leg_execution_guard")

            if isinstance(virtual_guard, dict) and virtual_guard:
                execution_guard_result = (
                    self._validate_virtual_leg_replacement_execution_guard(
                        virtual_guard
                    )
                )
            else:
                fresh_position_rows = self._request_positions_snapshot_for_execution()
                fresh_position_row = self._find_position_row_for_sl_tp_modify(
                    position_id=expected_position_id,
                    position_rows=fresh_position_rows,
                )
                fresh_position_context = self._build_position_sl_tp_modify_context(
                    position_id=expected_position_id,
                    position_row=fresh_position_row,
                )
                fresh_position_side = (
                    str(fresh_position_context["side"]).strip().upper()
                )
                fresh_position_volume = float(fresh_position_context["volume"])

                if fresh_position_side != expected_position_side:
                    raise RuntimeError(
                        "IB SL/TP replacement activation blocked: "
                        "position side changed | "
                        f"expected={expected_position_side} | "
                        f"actual={fresh_position_side}"
                    )

                if not math.isclose(
                    fresh_position_volume,
                    expected_position_volume,
                    rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
                    abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
                ):
                    raise RuntimeError(
                        "IB SL/TP replacement activation blocked: "
                        "position volume changed | "
                        f"expected={expected_position_volume} | "
                        f"actual={fresh_position_volume}"
                    )

            self._client.placeOrder(
                replacement_order_id,
                replacement_contract,
                active_order,
            )
            dispatched_calls.append(
                {
                    "call": "placeOrder",
                    "stage": "ACTIVATE",
                    "leg": survivor_leg,
                    "action": IB_PROTECTION_ACTION_CREATE,
                    "order_id": replacement_order_id,
                }
            )

            activation_action = {
                "action": IB_PROTECTION_ACTION_CREATE,
                "leg": survivor_leg,
                "order_id": replacement_order_id,
                "require_transmit_true": True,
            }
            activation_results = self._wait_for_sl_tp_operation_results(
                execution_actions=[activation_action],
                timeout=timeout,
            )
            action_results.extend(activation_results)
            activation_result = activation_results[0]

            if not bool(activation_result.get("confirmed")):
                raise RuntimeError(
                    "IB SL/TP replacement activation was not confirmed | "
                    f"leg={survivor_leg} | "
                    f"status={activation_result.get('status')}"
                )

            operation_snapshot = self._wrapper.get_sl_tp_operation_snapshot()

            return {
                "operation_order_ids": operation_order_ids,
                "dispatched_calls": dispatched_calls,
                "action_results": action_results,
                "operation_snapshot": operation_snapshot,
                "executed": True,
                "confirmed": True,
                "terminal": True,
                "timeout": any(
                    bool(result.get("timeout")) for result in action_results
                ),
                "failed_legs": [],
                "execution_guard_result": execution_guard_result,
            }

        except Exception:

            if not old_cancel_requested:
                self._logger.warning(
                    "IB SL/TP replacement aborted before old OCA "
                    "cancellation | staged transmit=False order may "
                    "remain local until TWS restart | order_id=%s",
                    replacement_order_id,
                )

            raise

        finally:
            self._wrapper.clear_sl_tp_operation()

    def _prepare_sl_tp_replacement_pair_execution(
        self,
        *,
        plan: dict[str, Any],
        position_id: str,
        position_side: str,
        account_id: str,
        protective_action: str,
        position_volume: float,
        position_contract_object: Contract,
        virtual_leg_execution_guard: dict[str, Any] | None = None,
        order_ref: str = "",
    ) -> dict[str, Any]:
        """
        Підготувати staged replacement pair для KEEP/MODIFY + CREATE.
        """
        plan_data = dict(plan or {})

        if bool(plan_data.get("blocked")):
            raise RuntimeError("IB SL/TP replacement pair plan is blocked")

        position_id_clean = str(position_id or "").strip()
        position_side_clean = str(position_side or "").strip().upper()
        account_id_clean = str(account_id or "").strip()
        protective_action_clean = str(protective_action or "").strip().upper()
        position_volume_float = float(position_volume)

        if not position_id_clean:
            raise ValueError("IB SL/TP replacement pair position id is empty")

        if position_side_clean not in {
            POSITION_SIDE_BUY,
            POSITION_SIDE_SELL,
        }:
            raise ValueError(
                "Invalid IB SL/TP replacement pair position side: " f"{position_side}"
            )

        if not account_id_clean:
            raise ValueError("IB SL/TP replacement pair account is empty")

        if protective_action_clean not in {"BUY", "SELL"}:
            raise ValueError(
                "Unsupported IB SL/TP replacement pair action: " f"{protective_action}"
            )

        if not math.isfinite(position_volume_float) or position_volume_float <= 0.0:
            raise ValueError(
                "Invalid IB SL/TP replacement pair position volume: "
                f"{position_volume_float}"
            )

        if position_contract_object is None:
            raise RuntimeError("IB SL/TP replacement pair Contract object is missing")

        survivor_leg = (
            str(plan_data.get("replacement_pair_survivor_leg") or "").strip().lower()
        )
        create_leg = (
            str(plan_data.get("replacement_pair_create_leg") or "").strip().lower()
        )
        valid_legs = {"stop_loss", "take_profit"}

        if survivor_leg not in valid_legs:
            raise RuntimeError("IB SL/TP replacement pair survivor leg is missing")

        if create_leg not in valid_legs or create_leg == survivor_leg:
            raise RuntimeError("IB SL/TP replacement pair create leg is invalid")

        survivor_action = (
            str(plan_data.get(f"{survivor_leg}_action") or "").strip().upper()
        )
        create_action = str(plan_data.get(f"{create_leg}_action") or "").strip().upper()

        if survivor_action not in {
            IB_PROTECTION_ACTION_KEEP,
            IB_PROTECTION_ACTION_MODIFY,
        }:
            raise RuntimeError(
                "IB SL/TP replacement pair survivor action is invalid | "
                f"action={survivor_action}"
            )

        if create_action != IB_PROTECTION_ACTION_CREATE:
            raise RuntimeError(
                "IB SL/TP replacement pair create action is invalid | "
                f"action={create_action}"
            )

        old_survivor_order_id = int(plan_data.get(f"{survivor_leg}_order_id") or 0)

        if old_survivor_order_id <= 0:
            raise RuntimeError(
                "IB SL/TP replacement pair old survivor order id is missing"
            )

        stop_loss_price = self._normalize_optional_ib_price(
            plan_data.get("new_stop_loss")
        )
        take_profit_price = self._normalize_optional_ib_price(
            plan_data.get("new_take_profit")
        )

        if stop_loss_price is None or take_profit_price is None:
            raise RuntimeError("IB SL/TP replacement pair prices are incomplete")

        stop_loss_order_id = self._get_next_order_id()
        take_profit_order_id = self._get_next_order_id()

        if stop_loss_order_id == take_profit_order_id:
            raise RuntimeError("IB SL/TP replacement pair order ids are duplicated")

        create_order_ids = {
            "stop_loss": stop_loss_order_id,
            "take_profit": take_profit_order_id,
        }
        pair_actions = [
            {
                "leg": "STOP_LOSS",
                "leg_key": "stop_loss",
                "order_type": "STP",
                "planner_action": plan_data.get("stop_loss_action"),
                "action": IB_PROTECTION_ACTION_CREATE,
                "order_id": stop_loss_order_id,
                "price": stop_loss_price,
                "broker_call_required": True,
                "replacement_pair": True,
                "require_transmit_true": True,
            },
            {
                "leg": "TAKE_PROFIT",
                "leg_key": "take_profit",
                "order_type": "LMT",
                "planner_action": plan_data.get("take_profit_action"),
                "action": IB_PROTECTION_ACTION_CREATE,
                "order_id": take_profit_order_id,
                "price": take_profit_price,
                "broker_call_required": True,
                "replacement_pair": True,
                "require_transmit_true": True,
            },
        ]
        oca_group = self._build_sl_tp_oca_group(execution_actions=pair_actions)

        staged_stop_loss_order = self._build_stop_order(
            action=protective_action_clean,
            quantity=position_volume_float,
            stop_price=stop_loss_price,
            parent_id=0,
            transmit=False,
        )
        staged_take_profit_order = self._build_limit_order(
            action=protective_action_clean,
            quantity=position_volume_float,
            limit_price=take_profit_price,
            parent_id=0,
            transmit=False,
        )

        staged_orders = {
            "stop_loss": staged_stop_loss_order,
            "take_profit": staged_take_profit_order,
        }

        for leg_key, staged_order in staged_orders.items():
            staged_order.orderId = create_order_ids[leg_key]
            staged_order.account = account_id_clean
            staged_order.orderRef = str(order_ref or "").strip() or IB_SL_TP_ORDER_REF
            staged_order.ocaGroup = oca_group
            staged_order.ocaType = IB_SL_TP_OCA_TYPE_CANCEL_WITH_BLOCK
            staged_order.transmit = False

        active_orders = {
            leg_key: deepcopy(staged_order)
            for leg_key, staged_order in staged_orders.items()
        }

        for active_order in active_orders.values():
            active_order.transmit = True

        cancel_action = {
            "leg": f"OLD_{survivor_leg.upper()}",
            "leg_key": survivor_leg,
            "planner_action": IB_PROTECTION_ACTION_CANCEL,
            "action": IB_PROTECTION_ACTION_CANCEL,
            "order_id": old_survivor_order_id,
            "broker_call_required": True,
            "replacement_pair_old_survivor": True,
        }

        return {
            "create_order_ids": create_order_ids,
            "execution_actions": pair_actions + [cancel_action],
            "oca_group": oca_group,
            "replacement_pair_survivor_leg": survivor_leg,
            "replacement_pair_create_leg": create_leg,
            "old_survivor_order_id": old_survivor_order_id,
            "replacement_contract_object": position_contract_object,
            "replacement_staged_orders": staged_orders,
            "replacement_active_orders": active_orders,
            "operation_order_ids": {
                stop_loss_order_id,
                take_profit_order_id,
                old_survivor_order_id,
            },
            "position_id": position_id_clean,
            "position_side": position_side_clean,
            "position_volume": position_volume_float,
            "virtual_leg_execution_guard": (
                dict(virtual_leg_execution_guard)
                if virtual_leg_execution_guard
                else None
            ),
        }

    def _execute_sl_tp_replacement_pair_operation(
        self,
        *,
        execution_package: dict[str, Any],
        timeout: float = IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """
        Замінити standalone survivor новою staged OCA-парою.
        """
        package = dict(execution_package or {})

        expected_position_id = str(package.get("position_id") or "").strip()
        expected_position_side = str(package.get("position_side") or "").strip().upper()
        expected_position_volume = float(package.get("position_volume") or 0.0)
        old_survivor_order_id = int(package.get("old_survivor_order_id") or 0)
        create_order_ids = dict(package.get("create_order_ids") or {})
        stop_loss_order_id = int(create_order_ids.get("stop_loss") or 0)
        take_profit_order_id = int(create_order_ids.get("take_profit") or 0)
        operation_order_ids = {
            int(order_id) for order_id in package.get("operation_order_ids") or set()
        }
        expected_order_ids = {
            old_survivor_order_id,
            stop_loss_order_id,
            take_profit_order_id,
        }

        if not expected_position_id:
            raise RuntimeError("IB SL/TP replacement pair position id is missing")

        if operation_order_ids != expected_order_ids or 0 in expected_order_ids:
            raise RuntimeError("IB SL/TP replacement pair operation order ids mismatch")

        replacement_contract = package.get("replacement_contract_object")
        staged_orders = dict(package.get("replacement_staged_orders") or {})
        active_orders = dict(package.get("replacement_active_orders") or {})

        if replacement_contract is None:
            raise RuntimeError("IB SL/TP replacement pair Contract object is missing")

        for leg_key in ("stop_loss", "take_profit"):
            if staged_orders.get(leg_key) is None:
                raise RuntimeError(
                    "IB SL/TP replacement pair staged Order is missing | "
                    f"leg={leg_key}"
                )

            if active_orders.get(leg_key) is None:
                raise RuntimeError(
                    "IB SL/TP replacement pair active Order is missing | "
                    f"leg={leg_key}"
                )

        dispatched_calls: list[dict[str, Any]] = []
        action_results: list[dict[str, Any]] = []
        execution_guard_result: dict[str, Any] = {}
        old_cancel_requested = False

        self._wrapper.start_sl_tp_operation(operation_order_ids)

        try:
            for leg_key, leg_name in (
                ("stop_loss", "STOP_LOSS"),
                ("take_profit", "TAKE_PROFIT"),
            ):
                order_id = create_order_ids[leg_key]
                self._client.placeOrder(
                    order_id,
                    replacement_contract,
                    staged_orders[leg_key],
                )
                dispatched_calls.append(
                    {
                        "call": "placeOrder",
                        "stage": "STAGE_LOCAL",
                        "leg": leg_name,
                        "action": IB_PROTECTION_ACTION_CREATE,
                        "order_id": order_id,
                    }
                )

                stage_result = self._wait_for_sl_tp_replacement_staged(
                    order_id=order_id,
                    leg=leg_name,
                    timeout=timeout,
                )
                action_results.append(stage_result)

                if not bool(stage_result.get("confirmed")):
                    raise RuntimeError(
                        "IB SL/TP replacement pair local stage was not "
                        "confirmed | "
                        f"leg={leg_name} | "
                        f"status={stage_result.get('status')}"
                    )

            self._client.cancelOrder(
                old_survivor_order_id,
                OrderCancel(),
            )
            old_cancel_requested = True
            dispatched_calls.append(
                {
                    "call": "cancelOrder",
                    "stage": "CANCEL_OLD_SURVIVOR",
                    "leg": "OLD_SURVIVOR",
                    "action": IB_PROTECTION_ACTION_CANCEL,
                    "order_id": old_survivor_order_id,
                }
            )

            old_cancel_action = {
                "action": IB_PROTECTION_ACTION_CANCEL,
                "leg": "OLD_SURVIVOR",
                "order_id": old_survivor_order_id,
            }
            old_cancel_results = self._wait_for_sl_tp_operation_results(
                execution_actions=[old_cancel_action],
                timeout=timeout,
            )
            action_results.extend(old_cancel_results)
            old_cancel_result = old_cancel_results[0]

            if not bool(old_cancel_result.get("confirmed")):
                raise RuntimeError(
                    "IB SL/TP replacement pair old survivor cancellation "
                    "was not confirmed"
                )

            virtual_guard = package.get("virtual_leg_execution_guard")

            if isinstance(virtual_guard, dict) and virtual_guard:
                execution_guard_result = (
                    self._validate_virtual_leg_replacement_execution_guard(
                        virtual_guard
                    )
                )
            else:
                fresh_position_rows = self._request_positions_snapshot_for_execution()
                fresh_position_row = self._find_position_row_for_sl_tp_modify(
                    position_id=expected_position_id,
                    position_rows=fresh_position_rows,
                )
                fresh_position_context = self._build_position_sl_tp_modify_context(
                    position_id=expected_position_id,
                    position_row=fresh_position_row,
                )
                fresh_position_side = (
                    str(fresh_position_context["side"]).strip().upper()
                )
                fresh_position_volume = float(fresh_position_context["volume"])

                if fresh_position_side != expected_position_side:
                    raise RuntimeError(
                        "IB SL/TP replacement pair activation blocked: "
                        "position side changed | "
                        f"expected={expected_position_side} | "
                        f"actual={fresh_position_side}"
                    )

                if not math.isclose(
                    fresh_position_volume,
                    expected_position_volume,
                    rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
                    abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
                ):
                    raise RuntimeError(
                        "IB SL/TP replacement pair activation blocked: "
                        "position volume changed | "
                        f"expected={expected_position_volume} | "
                        f"actual={fresh_position_volume}"
                    )

            activation_actions: list[dict[str, Any]] = []

            for leg_key, leg_name in (
                ("stop_loss", "STOP_LOSS"),
                ("take_profit", "TAKE_PROFIT"),
            ):
                order_id = create_order_ids[leg_key]
                self._client.placeOrder(
                    order_id,
                    replacement_contract,
                    active_orders[leg_key],
                )
                dispatched_calls.append(
                    {
                        "call": "placeOrder",
                        "stage": "ACTIVATE",
                        "leg": leg_name,
                        "action": IB_PROTECTION_ACTION_CREATE,
                        "order_id": order_id,
                    }
                )
                activation_actions.append(
                    {
                        "action": IB_PROTECTION_ACTION_CREATE,
                        "leg": leg_name,
                        "order_id": order_id,
                        "require_transmit_true": True,
                    }
                )

            activation_results = self._wait_for_sl_tp_operation_results(
                execution_actions=activation_actions,
                timeout=timeout,
            )
            action_results.extend(activation_results)
            failed_activation_legs = [
                str(result.get("leg") or "")
                for result in activation_results
                if not bool(result.get("confirmed"))
            ]

            if failed_activation_legs:
                raise RuntimeError(
                    "IB SL/TP replacement pair activation was not "
                    "confirmed | "
                    f"failed_legs={failed_activation_legs}"
                )

            operation_snapshot = self._wrapper.get_sl_tp_operation_snapshot()

            return {
                "operation_order_ids": operation_order_ids,
                "dispatched_calls": dispatched_calls,
                "action_results": action_results,
                "operation_snapshot": operation_snapshot,
                "executed": True,
                "confirmed": True,
                "terminal": True,
                "timeout": any(
                    bool(result.get("timeout")) for result in action_results
                ),
                "failed_legs": [],
                "execution_guard_result": execution_guard_result,
            }

        except Exception:
            if not old_cancel_requested:
                self._logger.warning(
                    "IB SL/TP replacement pair aborted before old survivor "
                    "cancellation | staged transmit=False orders may remain "
                    "local until TWS restart | order_ids=%s",
                    sorted(create_order_ids.values()),
                )
            else:
                self._logger.error(
                    "IB SL/TP replacement pair failed after old survivor "
                    "cancellation | manual TWS review required | order_ids=%s",
                    sorted(create_order_ids.values()),
                )

            raise

        finally:
            self._wrapper.clear_sl_tp_operation()

    def _dispatch_sl_tp_broker_payloads(
        self,
        *,
        broker_payloads: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Передати підготовлені SL/TP payloads у IB API.

        Усі payloads спочатку повністю перевіряються.
        placeOrder виконується перед cancelOrder, щоб не створювати
        зайвий проміжок без broker protection.
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        payload_rows = [dict(payload) for payload in (broker_payloads or [])]

        if not payload_rows:
            raise ValueError("IB SL/TP broker payloads are empty")

        place_rows: list[dict[str, Any]] = []
        cancel_rows: list[dict[str, Any]] = []
        seen_order_ids: set[int] = set()

        allowed_actions = {
            IB_PROTECTION_ACTION_KEEP,
            IB_PROTECTION_ACTION_MODIFY,
            IB_PROTECTION_ACTION_CANCEL,
            IB_PROTECTION_ACTION_CREATE,
        }

        for payload_row in payload_rows:
            leg_name = str(payload_row.get("leg") or "").strip().upper()

            execution_action = str(payload_row.get("action") or "").strip().upper()

            if not leg_name:
                raise ValueError("IB SL/TP broker payload leg is empty")

            if execution_action not in allowed_actions:
                raise ValueError(
                    "Unsupported IB SL/TP broker dispatch action | "
                    f"leg={leg_name} | "
                    f"action={execution_action}"
                )

            broker_call_required = bool(payload_row.get("broker_call_required"))

            expected_broker_call = execution_action != IB_PROTECTION_ACTION_KEEP

            if broker_call_required != expected_broker_call:
                raise RuntimeError(
                    "IB SL/TP broker-call flag mismatch | "
                    f"leg={leg_name} | "
                    f"action={execution_action} | "
                    f"expected={expected_broker_call} | "
                    f"actual={broker_call_required}"
                )

            if not broker_call_required:
                continue

            try:
                order_id = int(payload_row.get("order_id") or 0)
            except (TypeError, ValueError):
                order_id = 0

            if order_id <= 0:
                raise RuntimeError(
                    "IB SL/TP broker dispatch order id is missing | "
                    f"leg={leg_name} | "
                    f"action={execution_action}"
                )

            if order_id in seen_order_ids:
                raise RuntimeError(
                    "Duplicate IB SL/TP broker dispatch order id: " f"{order_id}"
                )

            seen_order_ids.add(order_id)
            payload_row["order_id"] = order_id

            if execution_action in {
                IB_PROTECTION_ACTION_MODIFY,
                IB_PROTECTION_ACTION_CREATE,
            }:
                broker_contract = payload_row.get("broker_contract_object")
                broker_order = payload_row.get("broker_order_object")

                if broker_contract is None:
                    raise RuntimeError(
                        "IB SL/TP placeOrder Contract is missing | " f"leg={leg_name}"
                    )

                if broker_order is None:
                    raise RuntimeError(
                        "IB SL/TP placeOrder Order is missing | " f"leg={leg_name}"
                    )

                try:
                    broker_order_id = int(
                        getattr(
                            broker_order,
                            "orderId",
                            0,
                        )
                        or 0
                    )
                except (TypeError, ValueError):
                    broker_order_id = 0

                if broker_order_id != order_id:
                    raise RuntimeError(
                        "IB SL/TP placeOrder id mismatch | "
                        f"leg={leg_name} | "
                        f"payload_id={order_id} | "
                        f"order_object_id={broker_order_id}"
                    )

                place_rows.append(payload_row)
                continue

            if execution_action == IB_PROTECTION_ACTION_CANCEL:
                cancel_rows.append(payload_row)
                continue

            raise RuntimeError(
                "IB SL/TP broker dispatch routing failed | "
                f"leg={leg_name} | "
                f"action={execution_action}"
            )

        if not place_rows and not cancel_rows:
            raise RuntimeError("IB SL/TP broker dispatch contains no broker calls")

        dispatched_calls: list[dict[str, Any]] = []

        # Спочатку CREATE/MODIFY.
        # Незалежні OCA orders передаються окремо з transmit=True.
        # OCA association визначається через ocaGroup та ocaType.

        for payload_row in place_rows:
            order_id = int(payload_row["order_id"])
            leg_name = str(payload_row["leg"])
            execution_action = str(payload_row["action"])

            broker_contract = payload_row["broker_contract_object"]
            broker_order = payload_row["broker_order_object"]

            self._logger.info(
                "Dispatching IB SL/TP placeOrder | "
                "leg=%s | action=%s | order_id=%s | "
                "order_type=%s | transmit=%s",
                leg_name,
                execution_action,
                order_id,
                getattr(broker_order, "orderType", ""),
                getattr(broker_order, "transmit", None),
            )

            self._client.placeOrder(
                order_id,
                broker_contract,
                broker_order,
            )

            dispatched_calls.append(
                {
                    "call": "placeOrder",
                    "leg": leg_name,
                    "action": execution_action,
                    "order_id": order_id,
                }
            )

        # CANCEL виконується після всіх CREATE/MODIFY payloads.
        for payload_row in cancel_rows:
            order_id = int(payload_row["order_id"])
            leg_name = str(payload_row["leg"])

            self._logger.info(
                "Dispatching IB SL/TP cancelOrder | " "leg=%s | order_id=%s",
                leg_name,
                order_id,
            )

            self._client.cancelOrder(
                order_id,
                OrderCancel(),
            )

            dispatched_calls.append(
                {
                    "call": "cancelOrder",
                    "leg": leg_name,
                    "action": IB_PROTECTION_ACTION_CANCEL,
                    "order_id": order_id,
                }
            )

        return dispatched_calls

    def _execute_sl_tp_broker_operation(
        self,
        *,
        execution_actions: list[dict[str, Any]],
        broker_payloads: list[dict[str, Any]],
        operation_order_ids: set[int],
        timeout: float = IB_SL_TP_OPERATION_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """
        Виконати одну підготовлену IB SL/TP broker operation.

        Послідовність:
        - перевірити відповідність order ids;
        - увімкнути callback aggregation;
        - передати payloads у IB API;
        - дочекатися broker confirmation;
        - повернути структурований результат;
        - очистити operation state.
        """
        action_rows = [dict(action) for action in (execution_actions or [])]

        payload_rows = [dict(payload) for payload in (broker_payloads or [])]

        if not action_rows:
            raise ValueError("IB SL/TP execution actions are empty")

        if not payload_rows:
            raise ValueError("IB SL/TP broker payloads are empty")

        normalized_operation_order_ids: set[int] = set()

        for source_order_id in operation_order_ids or set():
            try:
                order_id = int(source_order_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Invalid IB SL/TP operation order id: " f"{source_order_id}"
                ) from exc

            if order_id <= 0:
                raise ValueError("Invalid IB SL/TP operation order id: " f"{order_id}")

            normalized_operation_order_ids.add(order_id)

        if not normalized_operation_order_ids:
            raise ValueError("IB SL/TP operation order ids are empty")

        action_order_ids: set[int] = set()

        for action_row in action_rows:
            if not bool(action_row.get("broker_call_required")):
                continue

            try:
                order_id = int(action_row.get("order_id") or 0)
            except (TypeError, ValueError):
                order_id = 0

            if order_id <= 0:
                raise RuntimeError("IB SL/TP execution action order id " "is missing")

            action_order_ids.add(order_id)

        payload_order_ids: set[int] = set()

        for payload_row in payload_rows:
            if not bool(payload_row.get("broker_call_required")):
                continue

            try:
                order_id = int(payload_row.get("order_id") or 0)
            except (TypeError, ValueError):
                order_id = 0

            if order_id <= 0:
                raise RuntimeError("IB SL/TP broker payload order id " "is missing")

            payload_order_ids.add(order_id)

        if action_order_ids != normalized_operation_order_ids:
            raise RuntimeError(
                "IB SL/TP execution action order ids mismatch | "
                f"expected="
                f"{sorted(normalized_operation_order_ids)} | "
                f"actual={sorted(action_order_ids)}"
            )

        if payload_order_ids != normalized_operation_order_ids:
            raise RuntimeError(
                "IB SL/TP broker payload order ids mismatch | "
                f"expected="
                f"{sorted(normalized_operation_order_ids)} | "
                f"actual={sorted(payload_order_ids)}"
            )

        self._wrapper.start_sl_tp_operation(normalized_operation_order_ids)

        try:
            dispatched_calls = self._dispatch_sl_tp_broker_payloads(
                broker_payloads=payload_rows,
            )

            action_results = self._wait_for_sl_tp_operation_results(
                execution_actions=action_rows,
                timeout=timeout,
            )

            operation_snapshot = self._wrapper.get_sl_tp_operation_snapshot()

            failed_legs = [
                str(result.get("leg") or "")
                for result in action_results
                if not bool(result.get("confirmed"))
            ]

            all_terminal = all(
                bool(result.get("terminal")) for result in action_results
            )

            timed_out = any(bool(result.get("timeout")) for result in action_results)

            return {
                "operation_order_ids": normalized_operation_order_ids,
                "dispatched_calls": dispatched_calls,
                "action_results": action_results,
                "operation_snapshot": operation_snapshot,
                "executed": True,
                "confirmed": not failed_legs,
                "terminal": all_terminal,
                "timeout": timed_out,
                "failed_legs": failed_legs,
            }

        finally:
            self._wrapper.clear_sl_tp_operation()

    def modify_position_sl_tp(
        self,
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """
        Побудувати production IB SL/TP modify plan без execution.

        RoadMap88, перший етап:
        - strict positions snapshot;
        - lookup вибраної position;
        - broker position context;
        - strict open-orders snapshot з broker objects;
        - coverage metadata;
        - planner;
        - без placeOrder() і cancelOrder().
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        position_id_clean = str(position_id or "").strip()

        if not position_id_clean:
            raise ValueError("IB position id is empty")

        stop_loss_price = self._normalize_optional_ib_price(
            stop_loss,
        )
        take_profit_price = self._normalize_optional_ib_price(
            take_profit,
        )

        position_rows = self._request_positions_snapshot_for_execution()

        position_row = self._find_position_row_for_sl_tp_modify(
            position_id=position_id_clean,
            position_rows=position_rows,
        )

        position_context = self._build_position_sl_tp_modify_context(
            position_id=position_id_clean,
            position_row=position_row,
        )

        self._validate_ib_sl_tp_prices(
            side=position_context["side"],
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
        )

        open_orders = self._request_open_orders_snapshot(
            include_objects=True,
            require_complete=True,
        )

        protection_by_position_id = self._build_sl_tp_by_position_id(
            open_orders=open_orders,
            position_rows=position_rows,
        )

        current_protection = dict(
            protection_by_position_id.get(
                position_context["position_id"],
            )
            or {}
        )

        return self._execute_sl_tp_modify_from_context(
            position_context=position_context,
            current_protection=current_protection,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

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
    ) -> dict[str, Any]:
        """
        Modify one exact LGE-owned IB virtual leg protective pair.

        Identity comes from schema v5 child mappings, not from broker net
        quantity or symbol/price guessing. The RoadMap89 planner and broker
        execution path are reused unchanged.
        """
        if not self._connected:
            raise RuntimeError("IB adapter is not connected")

        position_uid_clean = str(position_uid or "").strip()
        position_id_clean = str(position_id or "").strip()
        account_id_clean = str(account_id or "").strip()
        symbol_name_clean = str(symbol_name or "").strip().upper()
        side_clean = str(position_side or "").strip().upper()
        oca_group_clean = str(current_oca_group or "").strip()
        order_ref_clean = str(order_ref or "").strip()

        if not position_uid_clean:
            raise ValueError("IB virtual-leg position_uid is empty")

        if not account_id_clean or not symbol_name_clean:
            raise ValueError("IB virtual-leg account or symbol is empty")

        normalized_position_id = f"IB:{account_id_clean}:{symbol_name_clean}"

        if position_id_clean != normalized_position_id:
            raise RuntimeError("IB virtual-leg broker position identity differs")

        if side_clean not in {POSITION_SIDE_BUY, POSITION_SIDE_SELL}:
            raise ValueError(f"Unsupported IB virtual-leg side: {side_clean!r}")

        volume = abs(float(position_volume))

        if not math.isfinite(volume) or math.isclose(
            volume,
            0.0,
            rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
            abs_tol=IB_POSITION_QUANTITY_ABS_TOLERANCE,
        ):
            raise ValueError("IB virtual-leg volume must be positive")

        parent_id = int(parent_order_id)

        if parent_id <= 0:
            raise ValueError("IB virtual-leg parent order id is invalid")

        stop_loss_price = self._normalize_optional_ib_price(stop_loss)
        take_profit_price = self._normalize_optional_ib_price(take_profit)
        self._validate_ib_sl_tp_prices(
            side=side_clean,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
        )

        open_orders = self._request_open_orders_snapshot(
            include_objects=True,
            require_complete=True,
        )
        current_protection, contract_object = (
            self._build_virtual_leg_sl_tp_current_protection(
                open_orders=open_orders,
                position_id=position_id_clean,
                account_id=account_id_clean,
                symbol_name=symbol_name_clean,
                position_side=side_clean,
                position_volume=volume,
                parent_order_id=parent_id,
                stop_loss_order_id=stop_loss_order_id,
                take_profit_order_id=take_profit_order_id,
                expected_oca_group=oca_group_clean,
            )
        )
        protective_action = (
            POSITION_SIDE_SELL if side_clean == POSITION_SIDE_BUY else POSITION_SIDE_BUY
        )
        position_context = {
            "position_id": position_id_clean,
            "account_id": account_id_clean,
            "symbol_name": symbol_name_clean,
            "side": side_clean,
            "volume": volume,
            "protective_action": protective_action,
            "contract_object": contract_object,
        }
        child_order_ids = (
            stop_loss_order_id,
            take_profit_order_id,
        )
        has_existing_child_order = any(
            self._virtual_leg_guard_positive_int(value) is not None
            for value in child_order_ids
        )
        virtual_leg_execution_guard = (
            self._build_virtual_leg_replacement_execution_guard(
                account_id=account_id_clean,
                symbol_name=symbol_name_clean,
                child_order_ids=child_order_ids,
            )
            if has_existing_child_order
            and self._virtual_leg_presence_change_count(
                current_protection=current_protection,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
            )
            == 1
            else None
        )
        result = self._execute_sl_tp_modify_from_context(
            position_context=position_context,
            current_protection=current_protection,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            virtual_leg_execution_guard=virtual_leg_execution_guard,
            order_ref=order_ref_clean,
        )
        result.update(
            {
                "position_uid": position_uid_clean,
                "parent_order_id": parent_id,
                "virtual_leg_operation": True,
            }
        )
        return result

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
    ) -> dict[str, Any]:
        """Cancel only this leg protection and close its exact volume."""
        side_clean = str(position_side or "").strip().upper()

        if side_clean == POSITION_SIDE_BUY:
            close_side = POSITION_SIDE_SELL
        elif side_clean == POSITION_SIDE_SELL:
            close_side = POSITION_SIDE_BUY
        else:
            raise ValueError(f"Unsupported IB virtual-leg side: {side_clean!r}")

        protection_result = self.modify_virtual_position_leg_sl_tp(
            position_uid=position_uid,
            position_id=position_id,
            account_id=account_id,
            symbol_name=symbol_name,
            position_side=side_clean,
            position_volume=position_volume,
            parent_order_id=parent_order_id,
            stop_loss_order_id=stop_loss_order_id,
            take_profit_order_id=take_profit_order_id,
            current_oca_group=current_oca_group,
            stop_loss=None,
            take_profit=None,
        )
        close_result = self.place_market_order(
            symbol_name=symbol_name,
            side=close_side,
            quantity=abs(float(position_volume)),
            stop_loss=None,
            take_profit=None,
            comment=comment,
        )
        return {
            "position_uid": str(position_uid or "").strip(),
            "broker_position_id": str(position_id or "").strip(),
            "close_side": close_side,
            "close_quantity": abs(float(position_volume)),
            "close_order_id": close_result.get("parent_order_id"),
            "cancelled_order_ids": list(
                protection_result.get("operation_order_ids") or []
            ),
            "protection_result": protection_result,
            "broker_result": close_result,
        }

    @staticmethod
    def _virtual_leg_presence_change_count(
        *,
        current_protection: dict[str, Any],
        stop_loss: float | None,
        take_profit: float | None,
    ) -> int:
        """Count child-presence changes for one exact virtual leg."""
        current_stop_loss = current_protection.get("stop_loss")
        current_take_profit = current_protection.get("take_profit")
        return sum(
            (current_price is None) != (requested_price is None)
            for current_price, requested_price in (
                (current_stop_loss, stop_loss),
                (current_take_profit, take_profit),
            )
        )

    def _build_virtual_leg_replacement_execution_guard(
        self,
        *,
        account_id: str,
        symbol_name: str,
        child_order_ids: tuple[int | None, int | None],
    ) -> dict[str, Any]:
        """Capture exact execution baseline before an OCA critical window."""
        account_id_clean = str(account_id or "").strip()
        symbol_name_clean = str(symbol_name or "").strip().upper()

        if not account_id_clean or not symbol_name_clean:
            raise ValueError("IB virtual-leg execution guard identity is incomplete")

        protected_order_ids = sorted(
            {
                order_id
                for value in child_order_ids
                for order_id in [self._virtual_leg_guard_positive_int(value)]
                if order_id is not None
            }
        )

        if not protected_order_ids:
            raise RuntimeError("IB virtual-leg execution guard has no child order IDs")

        baseline_rows = self._request_virtual_leg_execution_evidence([account_id_clean])
        group_rows = self._virtual_leg_guard_group_execution_rows(
            rows=baseline_rows,
            account_id=account_id_clean,
            symbol_name=symbol_name_clean,
        )
        return {
            "account_id": account_id_clean,
            "symbol_name": symbol_name_clean,
            "protected_order_ids": protected_order_ids,
            "baseline_fingerprints": [
                self._virtual_leg_execution_fingerprint(row) for row in group_rows
            ],
            "baseline_execution_count": len(group_rows),
        }

    def _validate_virtual_leg_replacement_execution_guard(
        self,
        guard: dict[str, Any],
    ) -> dict[str, Any]:
        """Block survivor activation if any same-contract execution appeared."""
        guard_data = dict(guard or {})
        account_id = str(guard_data.get("account_id") or "").strip()
        symbol_name = str(guard_data.get("symbol_name") or "").strip().upper()
        raw_protected_order_ids = guard_data.get("protected_order_ids")
        protected_order_ids: set[int] = set()

        if isinstance(raw_protected_order_ids, (list, tuple, set)):
            for value in raw_protected_order_ids:
                order_id = self._virtual_leg_guard_positive_int(value)

                if order_id is not None:
                    protected_order_ids.add(order_id)

        if not account_id or not symbol_name or not protected_order_ids:
            raise RuntimeError("IB virtual-leg execution guard metadata is invalid")

        raw_fingerprints = guard_data.get("baseline_fingerprints")
        baseline_fingerprints: list[tuple[Any, ...]] = []

        if isinstance(raw_fingerprints, (list, tuple)):
            baseline_fingerprints = [
                tuple(value)
                for value in raw_fingerprints
                if isinstance(value, (list, tuple))
            ]

        baseline_counter = Counter(baseline_fingerprints)
        fresh_rows = self._request_virtual_leg_execution_evidence([account_id])
        fresh_group_rows = self._virtual_leg_guard_group_execution_rows(
            rows=fresh_rows,
            account_id=account_id,
            symbol_name=symbol_name,
        )
        fresh_by_fingerprint: dict[tuple[Any, ...], dict[str, Any]] = {}
        fresh_counter: Counter[tuple[Any, ...]] = Counter()

        for row in fresh_group_rows:
            fingerprint = self._virtual_leg_execution_fingerprint(row)
            fresh_counter[fingerprint] += 1
            fresh_by_fingerprint[fingerprint] = row

        new_counter = fresh_counter - baseline_counter
        new_rows: list[dict[str, Any]] = []

        for fingerprint, count in new_counter.items():
            row = fresh_by_fingerprint[fingerprint]
            new_rows.extend(dict(row) for _ in range(count))

        if new_rows:
            new_order_ids = sorted(
                {
                    order_id
                    for row in new_rows
                    for order_id in [
                        self._virtual_leg_guard_positive_int(row.get("order_id"))
                    ]
                    if order_id is not None
                }
            )
            triggered_order_ids = sorted(set(new_order_ids) & protected_order_ids)

            if triggered_order_ids:
                raise RuntimeError(
                    "IB virtual-leg OCA replacement blocked: protective "
                    "execution occurred during the critical window | "
                    f"order_ids={triggered_order_ids}"
                )

            raise RuntimeError(
                "IB virtual-leg OCA replacement blocked: unexpected "
                "same-contract execution occurred during the critical "
                f"window | order_ids={new_order_ids}"
            )

        return {
            "confirmed": True,
            "account_id": account_id,
            "symbol_name": symbol_name,
            "protected_order_ids": sorted(protected_order_ids),
            "baseline_execution_count": sum(baseline_counter.values()),
            "fresh_execution_count": len(fresh_group_rows),
            "new_execution_order_ids": [],
        }

    @classmethod
    def _virtual_leg_guard_group_execution_rows(
        cls,
        *,
        rows: list[dict[str, Any]],
        account_id: str,
        symbol_name: str,
    ) -> list[dict[str, Any]]:
        """Filter execution rows to one exact account and CASH contract."""
        result: list[dict[str, Any]] = []

        for source_row in rows:
            row = dict(source_row)
            row_account = str(row.get("account_id") or row.get("account") or "").strip()

            if row_account != account_id:
                continue

            if cls._virtual_leg_execution_symbol_name(row) != symbol_name:
                continue

            result.append(row)

        return result

    @staticmethod
    def _virtual_leg_execution_symbol_name(
        row: dict[str, Any],
    ) -> str:
        symbol_name = str(row.get("symbol_name") or "").strip().upper()

        if symbol_name:
            return symbol_name

        symbol = str(row.get("symbol") or "").strip().upper()
        currency = str(row.get("currency") or "").strip().upper()
        return f"{symbol}{currency}" if symbol and currency else symbol

    @staticmethod
    def _virtual_leg_execution_fingerprint(
        row: dict[str, Any],
    ) -> tuple[Any, ...]:
        """Build a stable fingerprint independent of reqExecutions reqId."""
        return (
            str(row.get("account") or row.get("account_id") or ""),
            str(row.get("symbol") or ""),
            str(row.get("currency") or ""),
            str(row.get("sec_type") or ""),
            str(row.get("side") or ""),
            IBAdapter._virtual_leg_guard_float(row.get("shares")),
            IBAdapter._virtual_leg_guard_float(row.get("price")),
            str(row.get("time") or ""),
            IBAdapter._virtual_leg_guard_int(row.get("order_id")),
            IBAdapter._virtual_leg_guard_int(row.get("perm_id")),
        )

    @staticmethod
    def _virtual_leg_guard_float(value: object) -> float:
        if value is None or isinstance(value, bool):
            return 0.0

        if isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            try:
                result = float(value.strip() or "0")
            except ValueError:
                return 0.0
        else:
            return 0.0

        return result if math.isfinite(result) else 0.0

    @staticmethod
    def _virtual_leg_guard_int(value: object) -> int:
        if value is None or isinstance(value, bool):
            return 0

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                return 0

            return int(value)

        if isinstance(value, str):
            try:
                return int(value.strip() or "0")
            except ValueError:
                return 0

        return 0

    @classmethod
    def _virtual_leg_guard_positive_int(
        cls,
        value: object,
    ) -> int | None:
        result = cls._virtual_leg_guard_int(value)
        return result if result > 0 else None

    def _build_virtual_leg_sl_tp_current_protection(
        self,
        open_orders: list[dict[str, Any]],
        position_id: str,
        account_id: str,
        symbol_name: str,
        position_side: str,
        position_volume: float,
        parent_order_id: int,
        stop_loss_order_id: int | None,
        take_profit_order_id: int | None,
        expected_oca_group: str,
    ) -> tuple[dict[str, Any], Contract]:
        """Build exact current protection from persisted child IDs."""
        protective_action = (
            POSITION_SIDE_SELL
            if position_side == POSITION_SIDE_BUY
            else POSITION_SIDE_BUY
        )
        result: dict[str, Any] = {}
        contract_object: Contract | None = None
        mapped_oca_groups: set[str] = set()

        for leg_name, raw_order_id, allowed_types in (
            ("stop_loss", stop_loss_order_id, {"STP", "STOP"}),
            (
                "take_profit",
                take_profit_order_id,
                {"LMT", "LIMIT"},
            ),
        ):
            if raw_order_id is None:
                continue

            order_id = int(raw_order_id)

            if order_id <= 0:
                raise ValueError(f"IB virtual-leg {leg_name} order id is invalid")

            matches = [
                row for row in open_orders if int(row.get("order_id") or 0) == order_id
            ]

            if len(matches) != 1:
                raise RuntimeError(
                    f"IB virtual-leg {leg_name} order was not found " "uniquely"
                )

            row = matches[0]
            row_position_id = self._build_position_id_from_open_order(row)

            if row_position_id != position_id:
                raise RuntimeError(
                    f"IB virtual-leg {leg_name} contract identity differs"
                )

            if str(row.get("account") or "").strip() != account_id:
                raise RuntimeError(f"IB virtual-leg {leg_name} account differs")

            row_symbol_name = self._build_symbol_name_from_order_row(row)

            if row_symbol_name != symbol_name:
                raise RuntimeError(f"IB virtual-leg {leg_name} symbol differs")

            row_action = str(row.get("action") or "").strip().upper()

            if row_action != protective_action:
                raise RuntimeError(f"IB virtual-leg {leg_name} action differs")

            row_quantity = abs(float(row.get("total_quantity") or 0.0))

            if not math.isclose(
                row_quantity,
                position_volume,
                rel_tol=IB_SL_TP_COVERAGE_REL_TOLERANCE,
                abs_tol=IB_SL_TP_COVERAGE_ABS_TOLERANCE,
            ):
                raise RuntimeError(f"IB virtual-leg {leg_name} quantity differs")

            if not bool(row.get("same_client_id")):
                raise RuntimeError(f"IB virtual-leg {leg_name} ownership is unknown")

            row_parent_id = int(row.get("parent_id") or 0)

            if row_parent_id not in {0, parent_order_id}:
                raise RuntimeError(f"IB virtual-leg {leg_name} parent id differs")

            order_type = str(row.get("order_type") or "").strip().upper()

            if order_type not in allowed_types:
                raise RuntimeError(f"IB virtual-leg {leg_name} order type differs")

            row_contract = row.get("contract_object")
            row_order = row.get("order_object")

            if row_contract is None or row_order is None:
                raise RuntimeError(
                    f"IB virtual-leg {leg_name} broker objects are missing"
                )

            if contract_object is None:
                contract_object = row_contract

            oca_group = str(row.get("oca_group") or "").strip()

            if oca_group:
                mapped_oca_groups.add(oca_group)

            oca_group_rows = (
                [
                    candidate
                    for candidate in open_orders
                    if str(candidate.get("oca_group") or "").strip() == oca_group
                ]
                if oca_group
                else []
            )
            oca_group_order_ids = sorted(
                {
                    candidate_order_id
                    for candidate in oca_group_rows
                    for candidate_order_id in [
                        self._virtual_leg_guard_positive_int(candidate.get("order_id"))
                    ]
                    if candidate_order_id is not None
                }
            )
            oca_group_accounts = {
                str(candidate.get("account") or "").strip()
                for candidate in oca_group_rows
            }
            oca_group_is_orphaned = bool(
                oca_group
                and len(oca_group_rows) == 1
                and oca_group_order_ids == [order_id]
                and oca_group_accounts == {account_id}
            )

            price = (
                float(row.get("aux_price") or 0.0)
                if leg_name == "stop_loss"
                else float(row.get("lmt_price") or 0.0)
            )

            if price <= 0.0:
                raise RuntimeError(f"IB virtual-leg {leg_name} price is invalid")

            result.update(
                {
                    leg_name: price,
                    f"{leg_name}_quantity": row_quantity,
                    f"{leg_name}_position_volume": position_volume,
                    f"{leg_name}_partial": False,
                    f"{leg_name}_ambiguous": False,
                    f"{leg_name}_operational_ambiguous": False,
                    f"{leg_name}_order_ids": [order_id],
                    f"{leg_name}_order_count": 1,
                    f"{leg_name}_same_client_id": True,
                    f"{leg_name}_order_id": order_id,
                    f"{leg_name}_client_id": int(row.get("client_id") or 0),
                    f"{leg_name}_perm_id": int(row.get("perm_id") or 0),
                    f"{leg_name}_oca_group": oca_group,
                    f"{leg_name}_oca_type": int(row.get("oca_type") or 0),
                    f"{leg_name}_oca_group_order_ids": oca_group_order_ids,
                    f"{leg_name}_oca_group_order_count": len(oca_group_rows),
                    f"{leg_name}_oca_group_is_orphaned": oca_group_is_orphaned,
                    f"{leg_name}_contract_object": row_contract,
                    f"{leg_name}_order_object": row_order,
                }
            )

        if len(mapped_oca_groups) > 1:
            raise RuntimeError("IB virtual-leg protective OCA groups differ")

        if expected_oca_group and (mapped_oca_groups != {expected_oca_group}):
            raise RuntimeError("IB virtual-leg persisted OCA group differs from broker")

        if contract_object is None:
            base_symbol, quote_symbol = self._split_forex_symbol(symbol_name)
            contract_object = self._build_forex_contract(
                base_symbol=base_symbol,
                quote_symbol=quote_symbol,
            )

        return result, contract_object

    def _execute_sl_tp_modify_from_context(
        self,
        position_context: dict[str, Any],
        current_protection: dict[str, Any],
        stop_loss_price: float | None,
        take_profit_price: float | None,
        virtual_leg_execution_guard: dict[str, Any] | None = None,
        order_ref: str = "",
    ) -> dict[str, Any]:
        """
        Execute the shared RoadMap89 SL/TP planner and broker operation.

        Both broker-net modify and RoadMap90 virtual-leg modify build their
        own identity context, then reuse this single execution path.
        """
        plan = self.build_position_sl_tp_modify_plan(
            current_protection=current_protection,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
        )

        result = dict(plan)

        result.update(
            {
                "broker": "IB",
                "broker_position_id": position_context["position_id"],
                "account_id": position_context["account_id"],
                "symbol_name": position_context["symbol_name"],
                "position_side": position_context["side"],
                "position_volume": position_context["volume"],
                "protective_action": position_context["protective_action"],
                "position_contract_object": position_context["contract_object"],
                "current_protection": current_protection,
                "order_ref": str(order_ref or "").strip(),
                "plan_only": False,
            }
        )

        self._logger.info(
            "IB SL/TP modify plan built | "
            "position_id=%s | side=%s | volume=%s | "
            "SL=%s action=%s | TP=%s action=%s | "
            "blocked=%s | blocked_flags=%s",
            result["broker_position_id"],
            result["position_side"],
            result["position_volume"],
            stop_loss_price,
            result["stop_loss_action"],
            take_profit_price,
            result["take_profit_action"],
            result["blocked"],
            result["blocked_flags"],
        )

        if bool(plan.get("blocked")):
            blocked_flags = [str(flag) for flag in (plan.get("blocked_flags") or [])]

            blocked_details = ", ".join(blocked_flags)

            reason = str(plan.get("reason") or "").strip()

            error_text = reason or "IB SL/TP modify plan is blocked"

            if blocked_details:
                error_text += f" | blocked_flags={blocked_details}"

            self._logger.error(
                "IB SL/TP modify blocked | " "position_id=%s | error=%s",
                position_context["position_id"],
                error_text,
            )

            raise RuntimeError(error_text)

        stop_loss_action = str(plan.get("stop_loss_action") or "").strip().upper()

        take_profit_action = str(plan.get("take_profit_action") or "").strip().upper()

        is_no_operation = (
            stop_loss_action == IB_PROTECTION_ACTION_KEEP
            and take_profit_action == IB_PROTECTION_ACTION_KEEP
        )

        if is_no_operation:
            execution_actions = self.build_sl_tp_execution_actions(
                plan=plan,
            )

            action_results = self.build_sl_tp_operation_results(
                execution_actions=execution_actions,
                operation_snapshot={},
            )

            result.update(
                {
                    "create_order_ids": {},
                    "execution_actions": execution_actions,
                    "oca_group": None,
                    "operation_order_ids": set(),
                    "dispatched_calls": [],
                    "action_results": action_results,
                    "operation_snapshot": {},
                    "executed": False,
                    "confirmed": True,
                    "terminal": True,
                    "timeout": False,
                    "failed_legs": [],
                    "execution_guard_result": {},
                    "no_operation": True,
                }
            )

            self._logger.info(
                "IB SL/TP modify contains no broker changes | " "position_id=%s",
                position_context["position_id"],
            )

            return result

        replacement_pair_survivor_leg = str(
            plan.get("replacement_pair_survivor_leg") or ""
        ).strip()
        replacement_survivor_leg = str(
            plan.get("replacement_survivor_leg") or ""
        ).strip()

        if replacement_pair_survivor_leg:
            prepare_pair = self._prepare_sl_tp_replacement_pair_execution
            execute_pair = self._execute_sl_tp_replacement_pair_operation
            execution_package = prepare_pair(
                plan=plan,
                position_id=position_context["position_id"],
                position_side=position_context["side"],
                account_id=position_context["account_id"],
                protective_action=position_context["protective_action"],
                position_volume=position_context["volume"],
                position_contract_object=position_context["contract_object"],
                virtual_leg_execution_guard=virtual_leg_execution_guard,
                order_ref=order_ref,
            )
            operation_result = execute_pair(
                execution_package=execution_package,
            )
        elif replacement_survivor_leg:
            prepare_replacement = self._prepare_sl_tp_replacement_survivor_execution
            execute_replacement = self._execute_sl_tp_replacement_survivor_operation
            execution_package = prepare_replacement(
                plan=plan,
                position_id=position_context["position_id"],
                position_side=position_context["side"],
                account_id=position_context["account_id"],
                protective_action=position_context["protective_action"],
                position_volume=position_context["volume"],
                position_contract_object=position_context["contract_object"],
                virtual_leg_execution_guard=virtual_leg_execution_guard,
                order_ref=order_ref,
            )
            operation_result = execute_replacement(
                execution_package=execution_package,
            )
        else:
            execution_package = self._prepare_sl_tp_execution(
                plan=plan,
                account_id=position_context["account_id"],
                protective_action=position_context["protective_action"],
                position_volume=position_context["volume"],
                position_contract_object=position_context["contract_object"],
                order_ref=order_ref,
            )
            operation_result = self._execute_sl_tp_broker_operation(
                execution_actions=execution_package["execution_actions"],
                broker_payloads=execution_package["broker_payloads"],
                operation_order_ids=execution_package["operation_order_ids"],
            )

        result.update(
            {
                "create_order_ids": dict(execution_package["create_order_ids"]),
                "execution_actions": list(execution_package["execution_actions"]),
                "oca_group": execution_package["oca_group"],
                "operation_order_ids": set(operation_result["operation_order_ids"]),
                "dispatched_calls": list(operation_result["dispatched_calls"]),
                "action_results": list(operation_result["action_results"]),
                "operation_snapshot": dict(operation_result["operation_snapshot"]),
                "executed": bool(operation_result["executed"]),
                "confirmed": bool(operation_result["confirmed"]),
                "terminal": bool(operation_result["terminal"]),
                "timeout": bool(operation_result["timeout"]),
                "failed_legs": list(operation_result["failed_legs"]),
                "execution_guard_result": dict(
                    operation_result.get("execution_guard_result") or {}
                ),
                "no_operation": False,
            }
        )

        if not result["confirmed"]:
            failure_details: list[str] = []

            for action_result in result["action_results"]:
                if bool(action_result.get("confirmed")):
                    continue

                leg_name = str(action_result.get("leg") or "UNKNOWN")

                status = str(action_result.get("status") or "UNKNOWN")

                detail = f"{leg_name}={status}"

                errors = [str(error) for error in (action_result.get("errors") or [])]

                if errors:
                    detail += " (" + " | ".join(errors) + ")"

                failure_details.append(detail)

            error_text = "IB SL/TP broker operation was not " "fully confirmed"

            if failure_details:
                error_text += " | " + "; ".join(failure_details)

            self._logger.error(
                "IB SL/TP modify confirmation failed | "
                "position_id=%s | timeout=%s | error=%s",
                position_context["position_id"],
                result["timeout"],
                error_text,
            )

            raise RuntimeError(error_text)

        self._logger.info(
            "IB SL/TP modify confirmed | "
            "position_id=%s | order_ids=%s | "
            "SL=%s | TP=%s | oca_group=%s",
            position_context["position_id"],
            sorted(result["operation_order_ids"]),
            stop_loss_price,
            take_profit_price,
            result["oca_group"],
        )

        return result

    @staticmethod
    def _normalize_optional_ib_price(value: float | None) -> float | None:
        """
        Нормалізувати optional IB price.

        None або порожнє значення означає: SL/TP не заданий.
        """
        if value is None:
            return None

        price = float(value)

        if price <= 0.0:
            raise ValueError("IB SL/TP price must be positive")

        return price

    @staticmethod
    def _validate_ib_sl_tp_prices(
        side: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> None:
        """
        Базова перевірка напрямку SL/TP без market data.

        RoadMap86 first step:
        - не тягнемо reqMktData;
        - перевіряємо тільки очевидну логіку між SL і TP.
        """
        if stop_loss is None or take_profit is None:
            return

        side_norm = str(side or "").strip().upper()

        if side_norm == "BUY" and stop_loss >= take_profit:
            raise ValueError("IB BUY SL must be lower than TP")

        if side_norm == "SELL" and stop_loss <= take_profit:
            raise ValueError("IB SELL SL must be higher than TP")

    @staticmethod
    def _normalize_existing_ib_protection_price(
        value: Any,
    ) -> float | None:
        """
        Нормалізувати поточну broker protection price.

        Відсутнє або нульове значення означає, що protection order нема.
        """
        try:
            price = float(value or 0.0)
        except (TypeError, ValueError):
            return None

        if price <= 0.0:
            return None

        return price

    @staticmethod
    def _plan_ib_protection_leg(
        current_price: float | None,
        new_price: float | None,
    ) -> str:
        """
        Визначити дію для одного IB protection leg.

        Matrix:
        - нема -> нема: KEEP;
        - є -> те саме: KEEP;
        - є -> інше: MODIFY;
        - є -> нема: CANCEL;
        - нема -> є: CREATE.
        """
        current_exists = current_price is not None
        new_exists = new_price is not None

        if current_exists and new_exists:
            if math.isclose(
                current_price,
                new_price,
                rel_tol=1e-9,
                abs_tol=1e-10,
            ):
                return IB_PROTECTION_ACTION_KEEP

            return IB_PROTECTION_ACTION_MODIFY

        if current_exists and not new_exists:
            return IB_PROTECTION_ACTION_CANCEL

        if not current_exists and new_exists:
            return IB_PROTECTION_ACTION_CREATE

        return IB_PROTECTION_ACTION_KEEP

    @classmethod
    def build_position_sl_tp_modify_plan(
        cls,
        current_protection: dict[str, Any] | None,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, Any]:
        """
        Побудувати IB SL/TP modify plan без broker-викликів.

        Дозволено:
        - full coverage;
        - no coverage;
        - один broker order на protection leg;
        - MODIFY/CANCEL тільки для order поточного client;
        - MODIFY тільки за наявності Contract і Order objects.
        """
        protection = dict(current_protection or {})

        new_stop_loss = cls._normalize_optional_ib_price(stop_loss)
        new_take_profit = cls._normalize_optional_ib_price(take_profit)

        current_stop_loss = cls._normalize_existing_ib_protection_price(
            protection.get("stop_loss")
        )
        current_take_profit = cls._normalize_existing_ib_protection_price(
            protection.get("take_profit")
        )

        stop_loss_action = cls._plan_ib_protection_leg(
            current_price=current_stop_loss,
            new_price=new_stop_loss,
        )
        take_profit_action = cls._plan_ib_protection_leg(
            current_price=current_take_profit,
            new_price=new_take_profit,
        )

        blocked_flags: list[str] = []

        coverage_flags = (
            "stop_loss_partial",
            "stop_loss_ambiguous",
            "take_profit_partial",
            "take_profit_ambiguous",
        )

        for flag_name in coverage_flags:
            if bool(protection.get(flag_name)):
                blocked_flags.append(flag_name)

        leg_actions = {
            "stop_loss": stop_loss_action,
            "take_profit": take_profit_action,
        }

        oca_relink_legs: list[str] = []
        replacement_pair_survivor_leg: str | None = None
        replacement_pair_create_leg: str | None = None
        replacement_survivor_leg: str | None = None
        replacement_cancel_leg: str | None = None

        requires_oca_group = (
            new_stop_loss is not None
            and new_take_profit is not None
            and IB_PROTECTION_ACTION_CREATE in leg_actions.values()
        )

        for leg_name, action in leg_actions.items():
            if action not in {
                IB_PROTECTION_ACTION_MODIFY,
                IB_PROTECTION_ACTION_CANCEL,
            }:
                continue

            if bool(protection.get(f"{leg_name}_operational_ambiguous")):
                blocked_flags.append(f"{leg_name}_operational_ambiguous")

            if not bool(protection.get(f"{leg_name}_same_client_id")):
                blocked_flags.append(f"{leg_name}_different_client")

            order_id = int(protection.get(f"{leg_name}_order_id") or 0)

            if order_id <= 0:
                blocked_flags.append(f"{leg_name}_order_id_missing")

            if action == IB_PROTECTION_ACTION_MODIFY:
                contract_object = protection.get(f"{leg_name}_contract_object")
                order_object = protection.get(f"{leg_name}_order_object")

                if contract_object is None:
                    blocked_flags.append(f"{leg_name}_contract_object_missing")

                if order_object is None:
                    blocked_flags.append(f"{leg_name}_order_object_missing")

        if requires_oca_group:
            for leg_name, action in leg_actions.items():
                if action != IB_PROTECTION_ACTION_KEEP:
                    continue

                current_price = (
                    current_stop_loss
                    if leg_name == "stop_loss"
                    else current_take_profit
                )

                if current_price is None:
                    continue

                blocked_count_before = len(blocked_flags)

                if bool(protection.get(f"{leg_name}_operational_ambiguous")):
                    blocked_flags.append(f"{leg_name}_oca_operational_ambiguous")

                if not bool(protection.get(f"{leg_name}_same_client_id")):
                    blocked_flags.append(f"{leg_name}_oca_different_client")

                order_id = int(protection.get(f"{leg_name}_order_id") or 0)

                if order_id <= 0:
                    blocked_flags.append(f"{leg_name}_oca_order_id_missing")

                contract_object = protection.get(f"{leg_name}_contract_object")
                order_object = protection.get(f"{leg_name}_order_object")

                if contract_object is None:
                    blocked_flags.append(f"{leg_name}_oca_contract_object_missing")

                if order_object is None:
                    blocked_flags.append(f"{leg_name}_oca_order_object_missing")

                if len(blocked_flags) == blocked_count_before:
                    oca_relink_legs.append(leg_name)

        create_legs = [
            leg_name
            for leg_name, action in leg_actions.items()
            if action == IB_PROTECTION_ACTION_CREATE
        ]
        pair_survivor_legs = [
            leg_name
            for leg_name, action in leg_actions.items()
            if action
            in {
                IB_PROTECTION_ACTION_KEEP,
                IB_PROTECTION_ACTION_MODIFY,
            }
        ]

        if (
            requires_oca_group
            and len(create_legs) == 1
            and len(pair_survivor_legs) == 1
        ):
            create_leg = create_legs[0]
            survivor_leg = pair_survivor_legs[0]
            blocked_count_before = len(blocked_flags)

            if bool(protection.get(f"{survivor_leg}_operational_ambiguous")):
                blocked_flags.append(
                    f"replacement_pair_{survivor_leg}_operational_ambiguous"
                )

            if not bool(protection.get(f"{survivor_leg}_same_client_id")):
                blocked_flags.append(
                    f"replacement_pair_{survivor_leg}_different_client"
                )

            survivor_order_id = int(protection.get(f"{survivor_leg}_order_id") or 0)

            if survivor_order_id <= 0:
                blocked_flags.append(
                    f"replacement_pair_{survivor_leg}_order_id_missing"
                )

            survivor_oca_group = str(
                protection.get(f"{survivor_leg}_oca_group") or ""
            ).strip()

            survivor_oca_group_is_orphaned = bool(
                protection.get(f"{survivor_leg}_oca_group_is_orphaned")
            )

            if survivor_oca_group and not survivor_oca_group_is_orphaned:
                blocked_flags.append(f"replacement_pair_{survivor_leg}_not_standalone")

            if len(blocked_flags) == blocked_count_before:
                replacement_pair_survivor_leg = survivor_leg
                replacement_pair_create_leg = create_leg
                oca_relink_legs.clear()

        cancel_legs = [
            leg_name
            for leg_name, action in leg_actions.items()
            if action == IB_PROTECTION_ACTION_CANCEL
        ]
        survivor_legs = [
            leg_name
            for leg_name, action in leg_actions.items()
            if action
            in {
                IB_PROTECTION_ACTION_KEEP,
                IB_PROTECTION_ACTION_MODIFY,
            }
        ]

        if len(cancel_legs) == 1 and len(survivor_legs) == 1:
            cancel_leg = cancel_legs[0]
            survivor_leg = survivor_legs[0]

            cancel_oca_group = str(
                protection.get(f"{cancel_leg}_oca_group") or ""
            ).strip()
            survivor_oca_group = str(
                protection.get(f"{survivor_leg}_oca_group") or ""
            ).strip()

            old_oca_exists = bool(cancel_oca_group or survivor_oca_group)

            if old_oca_exists:
                cancel_oca_type = int(protection.get(f"{cancel_leg}_oca_type") or 0)
                survivor_oca_type = int(protection.get(f"{survivor_leg}_oca_type") or 0)

                if not cancel_oca_group or not survivor_oca_group:
                    blocked_flags.append("replacement_oca_group_missing")
                elif survivor_oca_group != cancel_oca_group:
                    blocked_flags.append("replacement_oca_group_mismatch")
                elif cancel_oca_type <= 0:
                    blocked_flags.append("replacement_oca_type_missing")
                elif survivor_oca_type != cancel_oca_type:
                    blocked_flags.append("replacement_oca_type_mismatch")
                else:
                    blocked_count_before = len(blocked_flags)

                    for old_leg in (survivor_leg, cancel_leg):
                        if bool(protection.get(f"{old_leg}_operational_ambiguous")):
                            blocked_flags.append(
                                f"replacement_{old_leg}_" "operational_ambiguous"
                            )

                        if not bool(protection.get(f"{old_leg}_same_client_id")):
                            blocked_flags.append(
                                f"replacement_{old_leg}_different_client"
                            )

                        old_order_id = int(protection.get(f"{old_leg}_order_id") or 0)

                        if old_order_id <= 0:
                            blocked_flags.append(
                                f"replacement_{old_leg}_order_id_missing"
                            )

                    if len(blocked_flags) == blocked_count_before:
                        replacement_survivor_leg = survivor_leg
                        replacement_cancel_leg = cancel_leg

        result: dict[str, Any] = {
            "blocked": bool(blocked_flags),
            "reason": "",
            "blocked_flags": blocked_flags,
            "stop_loss_action": stop_loss_action,
            "take_profit_action": take_profit_action,
            "current_stop_loss": current_stop_loss,
            "current_take_profit": current_take_profit,
            "new_stop_loss": new_stop_loss,
            "new_take_profit": new_take_profit,
            "requires_oca_group": requires_oca_group,
            "oca_relink_legs": oca_relink_legs,
            "replacement_pair_survivor_leg": replacement_pair_survivor_leg,
            "replacement_pair_create_leg": replacement_pair_create_leg,
            "replacement_survivor_leg": replacement_survivor_leg,
            "replacement_cancel_leg": replacement_cancel_leg,
        }

        metadata_suffixes = (
            "order_id",
            "order_ids",
            "order_count",
            "client_id",
            "perm_id",
            "oca_group",
            "oca_type",
            "oca_group_order_ids",
            "oca_group_order_count",
            "oca_group_is_orphaned",
            "same_client_id",
            "operational_ambiguous",
            "contract_object",
            "order_object",
        )

        for leg_name in ("stop_loss", "take_profit"):
            for suffix in metadata_suffixes:
                metadata_key = f"{leg_name}_{suffix}"

                if metadata_key in protection:
                    result[metadata_key] = protection[metadata_key]

        if blocked_flags:
            result["reason"] = (
                "IB SL/TP modify is blocked because protection "
                "coverage, ownership, or broker order metadata "
                "is unsafe."
            )
            result["planned_stop_loss_action"] = stop_loss_action
            result["planned_take_profit_action"] = take_profit_action
            result["stop_loss_action"] = IB_PROTECTION_ACTION_BLOCK
            result["take_profit_action"] = IB_PROTECTION_ACTION_BLOCK

        return result

    @staticmethod
    def build_open_order_snapshot_rows(
        open_orders: list[dict[str, Any]],
        open_order_objects: dict[int, dict[str, Any]],
        current_client_id: int,
        include_objects: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Побудувати IB open-order snapshot rows без broker-викликів.

        same_client_id є лише ownership candidate.
        Остаточну можливість modify/cancel підтверджує IB API.
        """
        snapshot: list[dict[str, Any]] = []

        for source_row in open_orders:
            row = dict(source_row)
            status = str(row.get("status") or "").strip().upper()

            if status in IB_OPEN_ORDER_TERMINAL_STATUSES:
                continue

            order_id = int(row.get("order_id") or 0)
            order_client_id = int(row.get("client_id") or 0)

            row["same_client_id"] = order_client_id == int(current_client_id)

            if include_objects:
                object_row = open_order_objects.get(order_id) or {}
                row.update(object_row)

            snapshot.append(row)

        return snapshot

    @staticmethod
    def build_completed_order_snapshot_rows(
        completed_orders: list[dict[str, Any]],
        current_client_id: int,
    ) -> list[dict[str, Any]]:
        """
        Побудувати scalar completed-order evidence rows.
        """
        snapshot: list[dict[str, Any]] = []

        for source_row in completed_orders:
            row = dict(source_row)
            order_client_id = int(row.get("client_id") or 0)

            row["same_client_id"] = order_client_id == int(current_client_id)

            snapshot.append(row)

        return snapshot

    def _cancel_related_sl_tp_open_orders(
        self,
        position_id: str,
    ) -> list[int]:
        """
        Скасувати відкриті IB SL/TP orders, пов'язані з position_id.

        Потрібно перед LGE close, щоб у TWS не лишались dangling STP/LMT.
        """
        position_id_clean = str(position_id or "").strip()

        if not position_id_clean:
            return []

        open_orders = self._request_open_orders_snapshot()
        order_ids: list[int] = []

        for order in open_orders:
            mapped_position_id = self._build_position_id_from_open_order(order)

            if mapped_position_id != position_id_clean:
                continue

            order_type = str(order.get("order_type") or "").strip().upper()

            if order_type not in {"STP", "STOP", "LMT", "LIMIT"}:
                continue

            order_id = int(order.get("order_id") or 0)

            if order_id > 0:
                order_ids.append(order_id)

        cancelled_order_ids: list[int] = []

        for order_id in order_ids:
            try:
                self._logger.warning(
                    "Cancelling related IB SL/TP order before close | "
                    "position_id=%s | order_id=%s",
                    position_id_clean,
                    order_id,
                )
                self._client.cancelOrder(order_id, OrderCancel())
                cancelled_order_ids.append(order_id)
                time.sleep(0.10)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "Failed to cancel related IB SL/TP order | "
                    "position_id=%s | order_id=%s | error=%s",
                    position_id_clean,
                    order_id,
                    exc,
                )

        return cancelled_order_ids

    def _build_position_id_from_open_order(
        self,
        order: dict[str, Any],
    ) -> str:
        """
        Побудувати IB runtime position_id з open order row.
        """
        account_id = str(order.get("account") or "").strip()

        if not account_id:
            account_id = self._get_primary_account_id()

        symbol = str(order.get("symbol") or "").strip().upper()
        currency = str(order.get("currency") or "").strip().upper()
        sec_type = str(order.get("sec_type") or "").strip().upper()

        if sec_type != "CASH":
            return ""

        if not account_id or not symbol or not currency:
            return ""

        return f"IB:{account_id}:{symbol}{currency}"

    def _get_next_order_id(self) -> int:
        """
        Взяти наступний IB order id і локально інкрементувати його.
        """
        with self._order_id_lock:
            value = self._wrapper.next_valid_id

            if value is None:
                raise RuntimeError("IB nextValidId is not available")

            order_id = int(value)
            self._wrapper.next_valid_id = order_id + 1

            return order_id

    @staticmethod
    def _split_forex_symbol(symbol_name: str) -> tuple[str, str]:
        """
        Розбити EURUSD або EUR.USD на base/quote для IB CASH contract.
        """
        text = str(symbol_name or "").strip().upper().replace("/", ".")

        if "." in text:
            parts = [part for part in text.split(".") if part]
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                return parts[0], parts[1]

        compact = text.replace(".", "")
        if len(compact) == 6:
            return compact[:3], compact[3:]

        raise ValueError(f"Unsupported IB Forex symbol: {symbol_name}")

    @staticmethod
    def _build_forex_contract(
        base_symbol: str,
        quote_symbol: str,
    ) -> Contract:
        """
        Створити IB Forex CASH contract.
        """
        contract = Contract()
        contract.symbol = base_symbol
        contract.secType = "CASH"
        contract.exchange = "IDEALPRO"
        contract.currency = quote_symbol
        return contract

    @staticmethod
    def _build_market_order(
        action: str,
        quantity: float,
        transmit: bool = True,
    ) -> Order:
        """
        Створити IB MARKET order.
        """
        order = Order()
        order.action = action
        order.orderType = "MKT"
        order.totalQuantity = quantity
        order.tif = "DAY"
        order.transmit = transmit
        return order

    @staticmethod
    def _build_stop_order(
        action: str,
        quantity: float,
        stop_price: float,
        parent_id: int,
        transmit: bool = False,
    ) -> Order:
        """
        Створити IB attached Stop Loss order.
        """
        order = Order()
        order.action = action
        order.orderType = "STP"
        order.totalQuantity = quantity
        order.auxPrice = stop_price
        order.parentId = int(parent_id)
        order.tif = "GTC"
        order.transmit = transmit
        return order

    @staticmethod
    def _build_limit_order(
        action: str,
        quantity: float,
        limit_price: float,
        parent_id: int,
        transmit: bool = False,
    ) -> Order:
        """
        Створити IB attached Take Profit LIMIT order.
        """
        order = Order()
        order.action = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = limit_price
        order.parentId = int(parent_id)
        order.tif = "GTC"
        order.transmit = transmit
        return order

    def _get_last_order_status(
        self,
        order_id: int,
    ) -> dict[str, Any]:
        """
        Повернути останній orderStatus для order_id.
        """
        rows = [
            row
            for row in self._wrapper.order_statuses
            if int(row.get("order_id", -1)) == int(order_id)
        ]

        if not rows:
            return {}

        return rows[-1]

    def _run_client_loop(self) -> None:
        """
        Safe wrapper навколо IB API run loop.

        IB API інколи після disconnect кидає TypeError:
        serverVersion() == None під час завершення thread.
        Для керованого shutdown це не runtime error.
        """

        try:
            self._client.run()
        except TypeError as exc:
            if self._stopping and "NoneType" in str(exc):
                self._logger.debug(
                    "IB API thread stopped during disconnect: %s",
                    exc,
                )
                return

            self._logger.exception("IB API thread failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            if self._stopping:
                self._logger.debug(
                    "IB API thread stopped during disconnect: %s",
                    exc,
                )
                return

            self._logger.exception("IB API thread failed: %s", exc)

    def _set_broker_state(self, state: str) -> None:
        """
        Встановити broker state з callback-шару IB API.

        Важливо:
        IB має два рівні connection:
        - local API socket LGE -> TWS / IB Gateway;
        - broker backend connectivity TWS / IB Gateway -> IBKR.

        Для CONNECTED треба відновити logical flag тільки якщо
        локальний IB socket справді живий.
        """

        self._broker_state = state

        if state == "CONNECTED":
            self._connected = bool(self._client.isConnected())
            return

        self._connected = False

    def get_managed_accounts(self) -> list[str]:
        """
        Повернути список доступних IB accounts.

        IB зазвичай надсилає managedAccounts після підключення.
        Якщо список ще порожній, fallback — account_id з account summary.
        """
        accounts = list(self._wrapper.managed_accounts)

        if accounts:
            return accounts

        account_info = self.get_account_info()

        if account_info.account_id:
            return [str(account_info.account_id)]

        return []
