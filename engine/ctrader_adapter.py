# ctrader_adapter.py
"""Production cTrader adapter для LGE runtime.

Модуль ізолює OpenAPI, broker lifecycle, market/history requests та торгові
операції. Історичне завантаження підтримує broker-neutral progress callback;
Qt/UI сюди не імпортуються.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from importlib import import_module

from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints

from core import ctrader_lot as ctr_lot
from core import ctrader_symbols as ctr_symbols
from core.token_manager import load_tokens
from engine.broker_account import BrokerAccount
from engine.broker_connection_state import BrokerConnectionState
from engine.broker_interface import BrokerInterface
from engine.broker_order_identity import (
    ORDER_CONTROL_MODE_MANUAL,
    build_broker_order_comment,
    build_ctrader_order_label,
    get_broker_order_control_mode,
    strip_broker_order_identity,
)
from engine.broker_position import (
    POSITION_SIDE_BUY,
    POSITION_SIDE_SELL,
    BrokerPosition,
)
from engine.ctrader_history import (
    CTraderHistoricalBar,
    CTraderHistoryDownloadResult,
    CTraderHistoryProgressCallback,
    decode_ctrader_trendbars,
    next_ctrader_history_chunk_end,
)
from engine.ctrader_reactor_manager import (
    call_in_ctrader_reactor,
    ensure_ctrader_reactor_started,
    stop_ctrader_reactor_for_diagnostics,
)
from engine.runtime_constants import (
    CTRADER_EXECUTION_TYPE_ORDER_ACCEPTED,
    CTRADER_EXECUTION_TYPE_ORDER_FILLED,
    CTRADER_EXECUTION_TYPE_ORDER_REJECTED,
    CTRADER_HISTORY_CHUNK_SIZE,
    CTRADER_HISTORY_MAX_REQUESTS,
    CTRADER_HISTORY_REQUEST_DELAY_SECONDS,
    CTRADER_HISTORY_TIMEOUT_SECONDS,
    CTRADER_ORDER_TYPE_MARKET,
    CTRADER_POSITIONS_TIMEOUT_SECONDS,
    CTRADER_SPOT_TIMEOUT_SECONDS,
    CTRADER_TRADE_SIDE_BUY,
    CTRADER_TRADE_SIDE_SELL,
    CTRADER_TRENDBAR_PERIOD_BY_TIMEFRAME,
    CTRADER_WAIT_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

oa_messages = import_module("ctrader_open_api.messages.OpenApiMessages_pb2")

HOST_DEMO = EndPoints.PROTOBUF_DEMO_HOST
HOST_LIVE = EndPoints.PROTOBUF_LIVE_HOST
PORT = EndPoints.PROTOBUF_PORT


ProtoOAAccountAuthReq = getattr(oa_messages, "ProtoOAAccountAuthReq")
ProtoOAAccountAuthRes = getattr(oa_messages, "ProtoOAAccountAuthRes")
ProtoOAApplicationAuthReq = getattr(oa_messages, "ProtoOAApplicationAuthReq")
ProtoOAApplicationAuthRes = getattr(oa_messages, "ProtoOAApplicationAuthRes")
ProtoOAErrorRes = getattr(oa_messages, "ProtoOAErrorRes")
ProtoOAGetAccountListByAccessTokenReq = getattr(
    oa_messages,
    "ProtoOAGetAccountListByAccessTokenReq",
)
ProtoOAGetAccountListByAccessTokenRes = getattr(
    oa_messages,
    "ProtoOAGetAccountListByAccessTokenRes",
)
ProtoOAAssetListReq = getattr(oa_messages, "ProtoOAAssetListReq")
ProtoOAAssetListRes = getattr(oa_messages, "ProtoOAAssetListRes")
ProtoOATraderReq = getattr(oa_messages, "ProtoOATraderReq")
ProtoOATraderRes = getattr(oa_messages, "ProtoOATraderRes")
ProtoOAClosePositionReq = getattr(oa_messages, "ProtoOAClosePositionReq")
ProtoOAAmendPositionSLTPReq = getattr(
    oa_messages,
    "ProtoOAAmendPositionSLTPReq",
)
ProtoOANewOrderReq = getattr(oa_messages, "ProtoOANewOrderReq")
ProtoOAExecutionEvent = getattr(oa_messages, "ProtoOAExecutionEvent")
ProtoOAOrderErrorEvent = getattr(oa_messages, "ProtoOAOrderErrorEvent")
ProtoOASubscribeSpotsReq = getattr(
    oa_messages,
    "ProtoOASubscribeSpotsReq",
)
ProtoOASubscribeSpotsRes = getattr(
    oa_messages,
    "ProtoOASubscribeSpotsRes",
)
ProtoOAUnsubscribeSpotsReq = getattr(
    oa_messages,
    "ProtoOAUnsubscribeSpotsReq",
)
ProtoOASpotEvent = getattr(oa_messages, "ProtoOASpotEvent")
ProtoOAGetTrendbarsReq = getattr(oa_messages, "ProtoOAGetTrendbarsReq")
ProtoOAGetTrendbarsRes = getattr(oa_messages, "ProtoOAGetTrendbarsRes")

ProtoOAReconcileReq = getattr(oa_messages, "ProtoOAReconcileReq")
ProtoOAReconcileRes = getattr(oa_messages, "ProtoOAReconcileRes")

ProtoOAGetPositionUnrealizedPnLReq = getattr(
    oa_messages,
    "ProtoOAGetPositionUnrealizedPnLReq",
)
ProtoOAGetPositionUnrealizedPnLRes = getattr(
    oa_messages,
    "ProtoOAGetPositionUnrealizedPnLRes",
)


PAYLOAD_APPLICATION_AUTH_RES = ProtoOAApplicationAuthRes().payloadType
PAYLOAD_ACCOUNT_AUTH_RES = ProtoOAAccountAuthRes().payloadType
PAYLOAD_ERROR_RES = ProtoOAErrorRes().payloadType
PAYLOAD_ACCOUNT_LIST_RES = ProtoOAGetAccountListByAccessTokenRes().payloadType

PAYLOAD_ASSET_LIST_RES = ProtoOAAssetListRes().payloadType
PAYLOAD_TRADER_RES = ProtoOATraderRes().payloadType

PAYLOAD_RECONCILE_RES = ProtoOAReconcileRes().payloadType

PAYLOAD_EXECUTION_EVENT = ProtoOAExecutionEvent().payloadType
PAYLOAD_ORDER_ERROR_EVENT = ProtoOAOrderErrorEvent().payloadType
PAYLOAD_SUBSCRIBE_SPOTS_RES = ProtoOASubscribeSpotsRes().payloadType
PAYLOAD_SPOT_EVENT = ProtoOASpotEvent().payloadType
PAYLOAD_GET_TRENDBARS_RES = ProtoOAGetTrendbarsRes().payloadType

PAYLOAD_POSITION_UNREALIZED_PNL_RES = ProtoOAGetPositionUnrealizedPnLRes().payloadType


@dataclass(slots=True)
class CTraderRuntimeConfig:
    """Runtime config для cTrader adapter."""

    client_id: str
    client_secret: str
    access_token: str
    ctid_trader_account_id: int
    account_mode: str = "DEMO"


@dataclass(slots=True)
class CTraderSessionState:
    """Mutable state cTrader session."""

    connection_state: BrokerConnectionState = BrokerConnectionState.DISCONNECTED
    last_error_text: str = ""
    account_payload: object | None = None
    account_info: BrokerAccount | None = None
    trader_payload: object | None = None
    connected_event: threading.Event = field(default_factory=threading.Event)
    disconnected_event: threading.Event = field(default_factory=threading.Event)


class CTraderAdapter(BrokerInterface):
    """
    Canonical cTrader adapter для RuntimeEngine.
    """

    def __init__(
        self,
        config: CTraderRuntimeConfig,
        logger: logging.Logger | None = None,  # noqa
    ) -> None:
        """
        Ініціалізувати adapter без підключення.
        """

        self._retired: bool = False
        self._session_generation: int = 0

        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.state = CTraderSessionState()
        self.client: Client | None = None

        self._positions_event = threading.Event()
        self._positions_payload: list = []

        self._positions_pnl_event = threading.Event()
        self._positions_pnl_payload: dict[str, float] = {}
        self._positions_pnl_raw_payload: dict[str, dict] = {}

        self._spot_event = threading.Event()
        self._spot_prices: dict[int, dict[str, float | int | None]] = {}
        self._spot_subscribed_symbol_ids: set[int] = set()
        self._position_spot_symbol_ids: set[int] = set()
        self._workspace_spot_symbol_ids: set[int] = set()

        self._trade_event = threading.Event()
        self._trade_payload: object | None = None
        self._trade_error_text = ""

        self._modify_sltp_event = threading.Event()
        self._modify_sltp_payload: object | None = None
        self._modify_sltp_error_text = ""
        self._modify_sltp_position_id: int | None = None

        self._trendbars_event = threading.Event()
        self._trendbars_payload: object | None = None
        self._trendbars_error_text = ""
        self._trendbars_request_active = False

        self._connect_generation = 0
        self._connecting = False
        self._connect_stage = "IDLE"
        self._deferred_error_generation = -1
        self._retired_disconnect_event = threading.Event()

    @classmethod
    def from_env(
        cls,
        account_mode: str = "DEMO",
        logger: logging.Logger | None = None,  # noqa
    ) -> "CTraderAdapter":
        """
        Створити adapter з ENV + tokens.json.

        ENV:
        - CTRADER_CLIENT_ID
        - CTRADER_CLIENT_SECRET
        - CTRADER_ACCOUNT_ID
        """

        client_id = _get_env_required("CTRADER_CLIENT_ID")
        client_secret = _get_env_required("CTRADER_CLIENT_SECRET")
        account_id_text = _get_env_required("CTRADER_ACCOUNT_ID")

        if not account_id_text.isdigit():
            raise RuntimeError("CTRADER_ACCOUNT_ID має бути цілим числом")

        access_token = _ensure_access_token()

        config = CTraderRuntimeConfig(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            ctid_trader_account_id=int(account_id_text),
            account_mode=account_mode.strip().upper(),
        )

        return cls(config=config, logger=logger)

    def _next_connect_generation(self) -> int:
        """
        Створити новий номер cTrader connection session.

        Потрібно для ігнорування старих Twisted callbacks/deferreds
        після reconnect.
        """

        self._connect_generation += 1
        return self._connect_generation

    def _is_current_client(self, client: Client) -> bool:
        """
        Перевірити, чи callback прийшов від поточного client.

        Старі callbacks після internet loss можуть приходити із запізненням.
        """

        if self._retired:
            return False

        return client is self.client

    def connect(self) -> bool:
        """
        Підключитися до cTrader Open API і пройти app/account auth.
        """

        if self.is_connected():
            return True

        if self._connecting:
            self.logger.warning(
                "cTrader connect skipped: connection attempt already running.",
            )
            return False

        self._connecting = True
        self._next_connect_generation()
        self._connect_stage = "TCP_CONNECT"
        self._deferred_error_generation = -1

        self.state.connection_state = BrokerConnectionState.CONNECTING
        self.state.last_error_text = ""
        self.state.connected_event.clear()
        self.state.disconnected_event.clear()

        host = HOST_LIVE if self.config.account_mode == "LIVE" else HOST_DEMO

        self.client = Client(
            host,
            PORT,
            TcpProtocol,
        )
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message_received)

        self._start_reactor_if_needed()
        call_in_ctrader_reactor(self.client.startService)

        if not self.state.connected_event.wait(CTRADER_WAIT_TIMEOUT_SECONDS):
            if self.is_connected():
                self.logger.warning(
                    "cTrader auth timeout ignored: adapter already connected.",
                )
                self.state.connection_state = BrokerConnectionState.CONNECTED
                self._connecting = False
                return True

            self.state.connection_state = BrokerConnectionState.ERROR
            self.state.last_error_text = (
                "TIMEOUT: cTrader auth not completed " f"stage={self._connect_stage}"
            )
            self.logger.error(self.state.last_error_text)
            self._connecting = False
            return False

        if self.state.last_error_text:
            if self.is_connected():
                self.logger.warning(
                    "cTrader auth error ignored: adapter already connected.",
                )
                self.state.connection_state = BrokerConnectionState.CONNECTED
                self.state.last_error_text = ""
                self._connecting = False
                return True

            self.state.connection_state = BrokerConnectionState.ERROR
            self.logger.error(self.state.last_error_text)
            self._connecting = False
            return False

        self.state.connection_state = BrokerConnectionState.CONNECTED
        self._connecting = False
        return True

    def disconnect(self) -> None:
        """
        Відключитися від cTrader Open API.
        """

        current_client = self.client

        if current_client is not None:
            try:
                current_client.setConnectedCallback(lambda _client: None)
                current_client.setDisconnectedCallback(lambda _client, _reason: None)
                current_client.setMessageReceivedCallback(
                    lambda _client, _message: None
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(
                    "cTrader callback detach skipped: %s",
                    exc,
                )

            try:
                call_in_ctrader_reactor(current_client.stopService)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("cTrader stopService failed: %s", exc)

        self.client = None
        self._connecting = False
        self._spot_event.clear()
        self._spot_prices = {}
        self._spot_subscribed_symbol_ids = set()
        self._position_spot_symbol_ids = set()
        self._workspace_spot_symbol_ids = set()
        self.state.connection_state = BrokerConnectionState.DISCONNECTED
        self.state.disconnected_event.set()

    def _reset_runtime_state(self) -> None:
        """
        Скинути runtime state перед clean reconnect.

        Для cTrader після втрати інтернету старий Twisted client/session
        не можна вважати надійним.
        """
        self._next_connect_generation()
        self._connecting = False
        self.client = None
        self.state.account_payload = None
        self.state.account_info = None
        self.state.trader_payload = None
        self.state.last_error_text = ""

        self.state.connected_event.clear()
        self.state.disconnected_event.clear()

        self._positions_event.clear()
        self._positions_payload = []

        self._positions_pnl_event.clear()
        self._positions_pnl_payload = {}
        self._positions_pnl_raw_payload = {}

        self._spot_event.clear()
        self._spot_prices = {}
        self._spot_subscribed_symbol_ids = set()
        self._position_spot_symbol_ids = set()
        self._workspace_spot_symbol_ids = set()

        self._trade_event.clear()
        self._trade_payload = None
        self._trade_error_text = ""

    def wait_for_connect_result(self, timeout_seconds: float) -> bool:
        """Wait for a late cTrader connect/auth result without polling."""
        self.state.connected_event.wait(
            timeout=max(0.0, float(timeout_seconds)),
        )
        return self.is_connected()

    def is_connected(self) -> bool:
        """
        Перевірити, чи adapter вважає broker connected.
        """

        return self.state.connection_state == BrokerConnectionState.CONNECTED

    def get_account_info(self) -> BrokerAccount:
        """
        Повернути нормалізовану інформацію про account.
        """

        if self.state.account_info is None:
            return BrokerAccount(
                broker="CTRADER",
                account_id=str(self.config.ctid_trader_account_id),
                account_mode=self.config.account_mode,
            )

        return self.state.account_info

    def refresh_account_info(self) -> BrokerAccount:
        """
        Перечитати account info з cTrader.

        Важливо:
        get_account_info() повертає кеш.
        refresh_account_info() надсилає новий ProtoOATraderReq.
        """

        if not self.is_connected():
            return self.get_account_info()

        if not self.is_session_alive():
            return self.get_account_info()

        if self.client is None:
            return self.get_account_info()

        self.state.trader_payload = None
        self._send_trader_req()

        return self.get_account_info()

    def get_account_list(self) -> list[dict]:
        """
        Повернути список cTrader accounts з останнього account-list payload.
        """
        payload = self.state.account_payload

        if payload is None:
            return []

        return _build_account_list_from_payload(payload)

    def get_historical_trendbars(
        self,
        symbol_name: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress_callback: CTraderHistoryProgressCallback | None = None,
    ) -> CTraderHistoryDownloadResult:
        """Download and decode cTrader historical OHLC trend bars."""
        if not self.is_connected() or self.client is None:
            raise RuntimeError("cTrader is not connected")

        symbol = str(symbol_name or "").strip().upper()
        frame = str(timeframe or "").strip().upper()
        if frame not in CTRADER_TRENDBAR_PERIOD_BY_TIMEFRAME:
            raise ValueError(f"Unsupported cTrader timeframe: {timeframe}")

        start = self._require_utc_datetime(start_utc, "start_utc")
        end = self._require_utc_datetime(end_utc, "end_utc")
        if start >= end:
            raise ValueError("cTrader history start must be before end")

        symbol_id = ctr_symbols.get_enabled_symbol_id(symbol)
        period = CTRADER_TRENDBAR_PERIOD_BY_TIMEFRAME[frame]
        requested_to_ms = int(end.timestamp() * 1000)
        from_ms = int(start.timestamp() * 1000)
        bars_by_timestamp: dict[int, CTraderHistoricalBar] = {}
        request_count = 0

        while requested_to_ms >= from_ms:
            if request_count >= CTRADER_HISTORY_MAX_REQUESTS:
                raise RuntimeError("cTrader historical request safety limit exceeded")

            payload = self._request_trendbar_chunk(
                symbol_id=symbol_id,
                period=period,
                from_timestamp=from_ms,
                to_timestamp=requested_to_ms,
            )
            request_count += 1
            decoded = self._decode_trendbars(payload)
            if not decoded:
                break

            for bar in decoded:
                timestamp_ms = int(bar.timestamp.timestamp() * 1000)
                if not from_ms <= timestamp_ms <= int(end.timestamp() * 1000):
                    continue
                if timestamp_ms in bars_by_timestamp:
                    raise RuntimeError("cTrader history contains a duplicate timestamp")
                bars_by_timestamp[timestamp_ms] = bar

            if progress_callback is not None:
                progress_callback(
                    request_count,
                    len(bars_by_timestamp),
                    decoded[0].timestamp,
                )

            next_to_ms = next_ctrader_history_chunk_end(decoded, start)
            if next_to_ms is None:
                break
            if next_to_ms >= requested_to_ms:
                raise RuntimeError(
                    "cTrader historical pagination did not move backward"
                )
            requested_to_ms = next_to_ms
            time.sleep(CTRADER_HISTORY_REQUEST_DELAY_SECONDS)

        bars = tuple(bars_by_timestamp[key] for key in sorted(bars_by_timestamp))
        return CTraderHistoryDownloadResult(
            broker="CTRADER",
            symbol=symbol,
            timeframe=frame,
            requested_start_utc=start,
            requested_end_utc=end,
            bars=bars,
            request_count=request_count,
        )

    def _request_trendbar_chunk(
        self,
        *,
        symbol_id: int,
        period: int,
        from_timestamp: int,
        to_timestamp: int,
    ) -> object:
        self._trendbars_event.clear()
        self._trendbars_payload = None
        self._trendbars_error_text = ""
        self._trendbars_request_active = True

        request = ProtoOAGetTrendbarsReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id
        request.symbolId = int(symbol_id)
        request.period = int(period)
        request.fromTimestamp = int(from_timestamp)
        request.toTimestamp = int(to_timestamp)
        request.count = CTRADER_HISTORY_CHUNK_SIZE

        self.logger.info(
            "Requesting cTrader trendbars | symbol_id=%s period=%s "
            "from=%s to=%s count=%s",
            symbol_id,
            period,
            from_timestamp,
            to_timestamp,
            CTRADER_HISTORY_CHUNK_SIZE,
        )

        try:
            deferred = self.client.send(request)
            deferred.addErrback(self._on_trendbars_deferred_error)
            finished = self._trendbars_event.wait(
                timeout=CTRADER_HISTORY_TIMEOUT_SECONDS
            )
            if not finished:
                raise RuntimeError("cTrader historical trendbars timeout")
            if self._trendbars_error_text:
                raise RuntimeError(self._trendbars_error_text)
            if self._trendbars_payload is None:
                raise RuntimeError("cTrader trendbars response is empty")
            return self._trendbars_payload
        finally:
            self._trendbars_request_active = False

    @staticmethod
    def _decode_trendbars(
        payload: object,
    ) -> list[CTraderHistoricalBar]:
        return decode_ctrader_trendbars(payload)

    @staticmethod
    def _require_utc_datetime(value: datetime, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{field_name} must be datetime")
        if value.tzinfo is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    def place_market_buy(
        self,
        symbol_name: str = "EURUSD",
        lots: float = 0.01,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual BUY",
    ):
        """
        Відкрити cTrader BUY MARKET position.
        """

        return self.place_market_order(
            symbol_name=symbol_name,
            side="BUY",
            lots=lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def place_market_sell(
        self,
        symbol_name: str = "EURUSD",
        lots: float = 0.01,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual SELL",
    ):
        """
        Відкрити cTrader SELL MARKET position.
        """

        return self.place_market_order(
            symbol_name=symbol_name,
            side="SELL",
            lots=lots,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )

    def place_market_order(
        self,
        symbol_name: str,
        side: str,
        lots: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "LGE manual order",
    ):
        """
        Відправити cTrader MARKET order.
        """

        self._ensure_trading_ready()

        normalized_side = side.strip().upper()
        if normalized_side == "BUY":
            trade_side = CTRADER_TRADE_SIDE_BUY
        elif normalized_side == "SELL":
            trade_side = CTRADER_TRADE_SIDE_SELL
        else:
            raise ValueError(f"Unsupported cTrader trade side: {side!r}")

        symbol_id = ctr_symbols.get_enabled_symbol_id(symbol_name)
        normalized_lots = ctr_lot.normalize_fx_lots(float(lots))
        api_volume = ctr_lot.lots_to_api_volume(normalized_lots)
        api_volume = ctr_lot.normalize_fx_api_volume(api_volume)

        self._trade_event.clear()
        self._trade_payload = None
        self._trade_error_text = ""

        request = ProtoOANewOrderReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id
        request.symbolId = symbol_id
        request.orderType = CTRADER_ORDER_TYPE_MARKET
        request.tradeSide = trade_side
        request.volume = api_volume
        control_mode = (
            get_broker_order_control_mode(comment) or ORDER_CONTROL_MODE_MANUAL
        )
        broker_comment = build_broker_order_comment(comment, control_mode)
        request.label = build_ctrader_order_label(control_mode)
        request.comment = broker_comment

        if stop_loss is not None:
            request.stopLoss = float(stop_loss)
        if take_profit is not None:
            request.takeProfit = float(take_profit)

        self.logger.info(
            "Sending cTrader MARKET order | symbol=%s side=%s lots=%s "
            "api_volume=%s SL=%s TP=%s",
            symbol_name,
            normalized_side,
            normalized_lots,
            api_volume,
            stop_loss,
            take_profit,
        )

        deferred = self.client.send(request)
        deferred.addErrback(self._on_trade_deferred_error)

        return self._wait_for_trade_result("cTrader MARKET order timeout.")

    def close_position(
        self,
        position_id: int | str,
        lots: float | None = None,
    ):
        """
        Закрити cTrader position повністю або частково.

        Якщо lots is None, береться повний поточний volume з broker snapshot.
        """

        self._ensure_trading_ready()

        api_volume = self._resolve_close_api_volume(
            position_id=position_id,
            lots=lots,
        )

        self._trade_event.clear()
        self._trade_payload = None
        self._trade_error_text = ""

        request = ProtoOAClosePositionReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id
        request.positionId = int(position_id)
        request.volume = api_volume

        self.logger.info(
            "Sending cTrader CLOSE position | position_id=%s api_volume=%s",
            position_id,
            api_volume,
        )

        deferred = self.client.send(request)
        deferred.addErrback(self._on_trade_deferred_error)

        return self._wait_for_trade_result("cTrader CLOSE position timeout.")

    def modify_position_sl_tp(
        self,
        position_id: int | str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Змінити або видалити SL/TP відкритої cTrader position.

        None означає, що відповідний SL або TP треба видалити.
        """
        self._ensure_trading_ready()

        position_id_int = int(position_id)

        if position_id_int <= 0:
            raise ValueError("cTrader position id must be positive")

        stop_loss_price = self._normalize_optional_sltp_price(
            stop_loss,
            field_name="Stop Loss",
        )
        take_profit_price = self._normalize_optional_sltp_price(
            take_profit,
            field_name="Take Profit",
        )

        self._modify_sltp_event.clear()
        self._modify_sltp_payload = None
        self._modify_sltp_error_text = ""
        self._modify_sltp_position_id = position_id_int

        request = ProtoOAAmendPositionSLTPReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id
        request.positionId = position_id_int

        if stop_loss_price is not None:
            request.stopLoss = stop_loss_price

        if take_profit_price is not None:
            request.takeProfit = take_profit_price

        self.logger.info(
            "Sending cTrader MODIFY position SL/TP | " "position_id=%s SL=%s TP=%s",
            position_id_int,
            stop_loss_price,
            take_profit_price,
        )

        try:
            deferred = self.client.send(request)
            deferred.addErrback(self._on_modify_sltp_deferred_error)

            finished = self._modify_sltp_event.wait(
                timeout=CTRADER_WAIT_TIMEOUT_SECONDS,
            )

            if not finished:
                raise RuntimeError("cTrader modify position SL/TP timeout")

            if self._modify_sltp_error_text:
                raise RuntimeError(self._modify_sltp_error_text)

            payload = self._modify_sltp_payload
            position = getattr(payload, "position", None)

            if position is None:
                raise RuntimeError("cTrader modify SL/TP response has no position")

            result_position_id = getattr(position, "positionId", None)

            if str(result_position_id) != str(position_id_int):
                raise RuntimeError("cTrader modify SL/TP returned another position")

            result_stop_loss = getattr(position, "stopLoss", None)
            result_take_profit = getattr(position, "takeProfit", None)

            return {
                "broker": "CTRADER",
                "broker_position_id": str(position_id_int),
                "stop_loss": (float(result_stop_loss) if result_stop_loss else None),
                "take_profit": (
                    float(result_take_profit) if result_take_profit else None
                ),
                "modified": True,
            }
        finally:
            self._modify_sltp_position_id = None

    @staticmethod
    def _normalize_optional_sltp_price(
        value: float | None,
        field_name: str,
    ) -> float | None:
        """
        Нормалізувати optional SL/TP price.

        None означає видалення відповідного захисту.
        """
        if value is None:
            return None

        price = float(value)

        if price <= 0.0:
            raise ValueError(f"cTrader {field_name} must be positive")

        return price

    def _ensure_trading_ready(self) -> None:
        """
        Перевірити, що cTrader adapter готовий до trading request.
        """

        if not self.is_connected():
            raise RuntimeError("cTrader adapter is not connected")

        if self.client is None:
            raise RuntimeError("cTrader client is not initialized")

        if not self.is_session_alive():
            raise RuntimeError("cTrader adapter session is retired")

    def _resolve_close_api_volume(
        self,
        position_id: int | str,
        lots: float | None,
    ) -> int:
        """
        Визначити api-volume для close request.
        """

        if lots is not None:
            api_volume = ctr_lot.lots_to_api_volume(float(lots))
            return ctr_lot.normalize_fx_api_volume(api_volume)

        for position in self.get_positions():
            if str(position.position_id) == str(position_id):
                raw_payload = position.raw_payload or {}
                raw_volume = raw_payload.get("api_volume")
                if raw_volume is not None:
                    return int(raw_volume)

        raise RuntimeError(
            f"Cannot resolve cTrader close volume for position {position_id!r}"
        )

    def _wait_for_trade_result(self, timeout_message: str):
        """
        Дочекатися cTrader execution/error event для trade request.
        """

        finished = self._trade_event.wait(timeout=CTRADER_WAIT_TIMEOUT_SECONDS)

        if not finished:
            self.logger.error(timeout_message)
            raise RuntimeError(timeout_message)

        if self._trade_error_text:
            raise RuntimeError(self._trade_error_text)

        return self._trade_payload

    @staticmethod
    def _start_reactor_if_needed() -> None:
        """
        Забезпечити process-level Twisted reactor для cTrader.
        """

        ensure_ctrader_reactor_started()

    def _on_connected(self, _client: Client) -> None:
        """
        Callback після TCP connect.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        if not self._is_current_client(_client):
            self.logger.debug(
                "cTrader old TCP connect callback ignored.",
            )
            return

        self.logger.info("cTrader TCP connected")
        self._connect_stage = "APPLICATION_AUTH"
        self._send_app_auth()

    def _on_disconnected(self, _client: Client, reason) -> None:
        """
        Callback після disconnect.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        if not self._is_current_client(_client):
            self.logger.debug(
                "cTrader old disconnect callback ignored: %s",
                reason,
            )
            return

        self.logger.info("cTrader disconnected: %s", reason)
        self.state.connection_state = BrokerConnectionState.DISCONNECTED
        self.state.disconnected_event.set()

    def _on_message_received(self, _client: Client, message) -> None:
        """
        Головний callback для protobuf messages.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        if not self._is_current_client(_client):
            self.logger.debug(
                "cTrader old protobuf message ignored.",
            )
            return

        try:
            payload = Protobuf.extract(message)
        except Exception as exc:  # noqa: BLE001
            self.logger.debug("cTrader message extract skipped: %s", exc)
            return

        if message.payloadType == PAYLOAD_APPLICATION_AUTH_RES:
            self.logger.info("cTrader application auth OK")
            self._connect_stage = "ACCOUNT_LIST"
            self._send_get_account_list()
            return

        if message.payloadType == PAYLOAD_ACCOUNT_LIST_RES:
            self.state.account_payload = payload
            self._build_account_info(payload)
            self._connect_stage = "ACCOUNT_AUTH"
            self._send_account_auth()
            return

        if message.payloadType == PAYLOAD_ACCOUNT_AUTH_RES:
            self.logger.info("cTrader account auth OK")
            self._connect_stage = "TRADER"
            self._send_trader_req()
            return

        if message.payloadType == PAYLOAD_TRADER_RES:
            self.logger.info("cTrader trader info received.")
            self.state.trader_payload = payload
            self._connect_stage = "ASSET_LIST"
            self._send_asset_list_req()
            return

        if message.payloadType == PAYLOAD_ASSET_LIST_RES:
            self.logger.info("cTrader asset list received.")
            self._build_account_info_from_trader(
                trader_payload=self.state.trader_payload,
                asset_payload=payload,
            )
            self.state.connection_state = BrokerConnectionState.CONNECTED
            self._connect_stage = "CONNECTED"
            self.state.connected_event.set()
            return

        if message.payloadType == PAYLOAD_RECONCILE_RES:
            self._on_reconcile_res(payload)
            return

        if message.payloadType == PAYLOAD_POSITION_UNREALIZED_PNL_RES:
            self._on_position_unrealized_pnl_res(payload)
            return

        if message.payloadType == PAYLOAD_GET_TRENDBARS_RES:
            self._on_trendbars_res(payload)
            return

        if message.payloadType == PAYLOAD_SUBSCRIBE_SPOTS_RES:
            self.logger.debug("cTrader spot subscription accepted.")
            return

        if message.payloadType == PAYLOAD_SPOT_EVENT:
            self._on_spot_event(payload)
            return

        if message.payloadType == PAYLOAD_EXECUTION_EVENT:
            self._on_execution_event(payload)
            return

        if message.payloadType == PAYLOAD_ORDER_ERROR_EVENT:
            self._on_order_error_event(payload)
            return

        if message.payloadType == PAYLOAD_ERROR_RES:
            error_text = _format_api_error(payload)
            self.state.last_error_text = error_text
            self.logger.error(error_text)
            if self._trendbars_request_active:
                self._trendbars_error_text = error_text
                self._trendbars_event.set()
            self.state.connected_event.set()

    def _on_trendbars_res(self, payload: object) -> None:
        if not self._trendbars_request_active:
            self.logger.debug("Unexpected cTrader trendbars response ignored.")
            return
        account_id = int(getattr(payload, "ctidTraderAccountId", 0) or 0)
        if account_id != int(self.config.ctid_trader_account_id):
            self._trendbars_error_text = "cTrader history account mismatch"
        else:
            self._trendbars_payload = payload
        self._trendbars_event.set()

    def _on_trendbars_deferred_error(self, failure) -> None:
        if not self._trendbars_request_active:
            return
        self._trendbars_error_text = f"cTrader trendbars request failed: {failure}"
        self.logger.error(self._trendbars_error_text)
        self._trendbars_event.set()

    def _on_spot_event(self, payload) -> None:
        """Cache the latest cTrader bid/ask quote for one symbol."""
        if not self.is_session_alive():
            return

        account_id = int(getattr(payload, "ctidTraderAccountId", 0) or 0)

        if account_id != int(self.config.ctid_trader_account_id):
            return

        symbol_id = int(getattr(payload, "symbolId", 0) or 0)

        if symbol_id <= 0:
            return

        current = dict(self._spot_prices.get(symbol_id) or {})
        bid_raw = self._optional_proto_scalar(payload, "bid")
        ask_raw = self._optional_proto_scalar(payload, "ask")
        timestamp = self._optional_proto_scalar(payload, "timestamp")

        if bid_raw is not None and float(bid_raw) > 0.0:
            current["bid"] = float(bid_raw) / 100000.0

        if ask_raw is not None and float(ask_raw) > 0.0:
            current["ask"] = float(ask_raw) / 100000.0

        if timestamp is not None:
            current["timestamp"] = int(timestamp)

        if current.get("bid") is None and current.get("ask") is None:
            return

        self._spot_prices[symbol_id] = current
        self._spot_event.set()

    @staticmethod
    def _optional_proto_scalar(payload, field_name: str):
        """Read one optional protobuf scalar without treating absence as zero."""
        has_field = getattr(payload, "HasField", None)

        if callable(has_field):
            try:
                if not has_field(field_name):
                    return None
            except (ValueError, TypeError):
                pass

        value = getattr(payload, field_name, None)

        if value is None:
            return None

        return value

    def _subscribe_position_spots(self, symbol_ids: set[int]) -> None:
        """Subscribe once and wait briefly for initial live quotes."""
        if not symbol_ids or self.client is None or not self.is_connected():
            return

        requested_ids = {int(value) for value in symbol_ids if int(value) > 0}
        new_ids = requested_ids - self._spot_subscribed_symbol_ids

        if new_ids:
            request = ProtoOASubscribeSpotsReq()
            request.ctidTraderAccountId = self.config.ctid_trader_account_id

            for symbol_id in sorted(new_ids):
                request.symbolId.append(symbol_id)

            request.subscribeToSpotTimestamp = True
            self._spot_event.clear()
            deferred = self.client.send(request)
            deferred.addErrback(
                partial(
                    self._on_spots_deferred_error,
                    symbol_ids=tuple(sorted(new_ids)),
                )
            )
            self._spot_subscribed_symbol_ids.update(new_ids)

        deadline = time.monotonic() + CTRADER_SPOT_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            missing = {
                symbol_id
                for symbol_id in requested_ids
                if not self._spot_price_available(symbol_id)
            }

            if not missing:
                return

            self._spot_event.clear()

            if not any(
                not self._spot_price_available(symbol_id) for symbol_id in missing
            ):
                return

            remaining = deadline - time.monotonic()

            if remaining <= 0.0:
                break

            self._spot_event.wait(timeout=remaining)

        missing = sorted(
            symbol_id
            for symbol_id in requested_ids
            if not self._spot_price_available(symbol_id)
        )

        if missing:
            self.logger.warning(
                "cTrader spot quote timeout | symbol_ids=%s",
                missing,
            )

    def _sync_owned_spot_subscriptions(self) -> None:
        """Synchronize the union of position and WSP spot ownership."""
        desired_ids = self._position_spot_symbol_ids | self._workspace_spot_symbol_ids
        self._subscribe_position_spots(desired_ids)
        stale_ids = self._spot_subscribed_symbol_ids - desired_ids
        if not stale_ids or self.client is None or not self.is_connected():
            return

        request = ProtoOAUnsubscribeSpotsReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id
        for symbol_id in sorted(stale_ids):
            request.symbolId.append(symbol_id)
        deferred = self.client.send(request)
        deferred.addErrback(
            partial(
                self._on_spots_unsubscribe_deferred_error,
                symbol_ids=tuple(sorted(stale_ids)),
            )
        )
        self._spot_subscribed_symbol_ids.difference_update(stale_ids)

    def _on_spots_unsubscribe_deferred_error(
        self,
        failure,
        symbol_ids: tuple[int, ...],
    ) -> None:
        """Restore local ownership when cTrader unsubscribe fails."""
        self.logger.error(
            "cTrader spot unsubscribe failed | symbol_ids=%s | error=%s",
            symbol_ids,
            failure,
        )
        self._spot_subscribed_symbol_ids.update(symbol_ids)

    def _on_spots_deferred_error(
        self,
        failure,
        symbol_ids: tuple[int, ...],
    ) -> None:
        """Release spot waiters when the subscription request fails."""
        self.logger.error(
            "cTrader spot subscription failed | symbol_ids=%s | error=%s",
            symbol_ids,
            failure,
        )
        self._spot_subscribed_symbol_ids.difference_update(symbol_ids)
        self._spot_event.set()

    def get_forex_quote_snapshot(
        self,
        symbol_names: list[str],
        wait_timeout: float | None = None,
    ) -> dict[str, object]:
        """Subscribe to requested Forex spots and return cached quotes."""
        normalized_symbols: list[str] = []
        symbol_ids: dict[str, int] = {}
        for raw_symbol in symbol_names:
            symbol = (
                str(raw_symbol or "").strip().upper().replace("/", "").replace(".", "")
            )
            if not symbol or symbol in symbol_ids:
                continue
            try:
                symbol_id = ctr_symbols.get_enabled_symbol_id(symbol)
            except (KeyError, ValueError):
                continue
            normalized_symbols.append(symbol)
            symbol_ids[symbol] = symbol_id

        captured_utc = datetime.now(UTC).replace(microsecond=0).isoformat()
        if not self.is_connected() or not self.is_session_alive():
            return {
                "captured_utc": captured_utc,
                "complete": False,
                "quotes": {},
                "subscribed_symbols": [],
            }

        timeout = (
            CTRADER_SPOT_TIMEOUT_SECONDS
            if wait_timeout is None
            else max(float(wait_timeout), 0.0)
        )
        self._workspace_spot_symbol_ids = set(symbol_ids.values())
        self._sync_owned_spot_subscriptions()
        if symbol_ids:
            if timeout > CTRADER_SPOT_TIMEOUT_SECONDS:
                self._spot_event.wait(timeout=timeout - CTRADER_SPOT_TIMEOUT_SECONDS)

        quotes: dict[str, dict[str, object]] = {}
        for symbol in normalized_symbols:
            row = dict(self._spot_prices.get(symbol_ids[symbol]) or {})
            timestamp = self._spot_timestamp_iso(row.get("timestamp"))
            quotes[symbol] = {
                "symbol_name": symbol,
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "timestamp": timestamp,
                "volume": 0.0,
            }

        complete = bool(normalized_symbols) and all(
            row.get("bid") is not None and row.get("ask") is not None
            for row in quotes.values()
        )
        return {
            "captured_utc": (datetime.now(UTC).replace(microsecond=0).isoformat()),
            "complete": complete,
            "quotes": quotes,
            "subscribed_symbols": normalized_symbols,
        }

    @staticmethod
    def _spot_timestamp_iso(value: object) -> str:
        """Normalize cTrader spot timestamps to an aware UTC ISO string."""
        if isinstance(value, (str, bytes, bytearray, int, float)):
            try:
                raw = float(value)
            except ValueError:
                raw = 0.0
        else:
            raw = 0.0
        if raw <= 0.0:
            return datetime.now(UTC).replace(microsecond=0).isoformat()
        if raw > 10_000_000_000.0:
            raw /= 1000.0
        return datetime.fromtimestamp(raw, tz=UTC).isoformat()

    def _spot_price_available(self, symbol_id: int) -> bool:
        """Return whether at least one usable side is cached."""
        row = self._spot_prices.get(int(symbol_id)) or {}
        return row.get("bid") is not None or row.get("ask") is not None

    def _current_price_for_position(
        self,
        symbol_id: int,
        side: str,
    ) -> float:
        """Return the executable close side: bid for BUY, ask for SELL."""
        row = self._spot_prices.get(int(symbol_id)) or {}
        bid = row.get("bid")
        ask = row.get("ask")
        side_norm = str(side or "").strip().upper()

        if side_norm == POSITION_SIDE_BUY:
            selected = bid if bid is not None else ask
        elif side_norm == POSITION_SIDE_SELL:
            selected = ask if ask is not None else bid
        elif bid is not None and ask is not None:
            selected = (float(bid) + float(ask)) / 2.0
        else:
            selected = bid if bid is not None else ask

        return float(selected or 0.0)

    def _on_execution_event(self, payload) -> None:
        """
        Обробити cTrader execution event після order/close request.

        Для MARKET order не завершуємо очікування на ORDER_ACCEPTED.
        Канонічно чекаємо ORDER_FILLED або помилку.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        execution_type = int(getattr(payload, "executionType", 0) or 0)

        order = getattr(payload, "order", None)
        position = getattr(payload, "position", None)

        order_id = getattr(order, "orderId", None) if order is not None else None
        position_id = (
            getattr(position, "positionId", None) if position is not None else None
        )

        pending_modify_position_id = self._modify_sltp_position_id

        if pending_modify_position_id is not None and str(position_id) == str(
            pending_modify_position_id
        ):
            self._modify_sltp_payload = payload

            if execution_type == CTRADER_EXECUTION_TYPE_ORDER_REJECTED:
                self._modify_sltp_error_text = (
                    "cTrader modify position SL/TP was rejected."
                )
                self.logger.error(
                    "cTrader MODIFY SL/TP rejected | "
                    "position_id=%s execution_type=%s",
                    position_id,
                    execution_type,
                )
            else:
                self._modify_sltp_error_text = ""
                self.logger.info(
                    "cTrader position SL/TP modified | "
                    "position_id=%s execution_type=%s",
                    position_id,
                    execution_type,
                )

            self._modify_sltp_event.set()
            return

        if execution_type == CTRADER_EXECUTION_TYPE_ORDER_ACCEPTED:
            self.logger.info(
                "cTrader order accepted | order_id=%s",
                order_id,
            )
            return

        if execution_type == CTRADER_EXECUTION_TYPE_ORDER_FILLED:
            self._trade_payload = payload
            self._trade_error_text = ""
            self.logger.info(
                "cTrader order filled | order_id=%s position_id=%s",
                order_id,
                position_id,
            )
            self._trade_event.set()
            return

        if execution_type == CTRADER_EXECUTION_TYPE_ORDER_REJECTED:
            self._trade_payload = payload
            self._trade_error_text = "cTrader order rejected by execution event."
            self.logger.error(
                "cTrader order rejected | order_id=%s position_id=%s",
                order_id,
                position_id,
            )
            self._trade_event.set()
            return

        self.logger.info(
            "cTrader execution event ignored | execution_type=%s "
            "order_id=%s position_id=%s",
            execution_type,
            order_id,
            position_id,
        )

    def _on_order_error_event(self, payload) -> None:
        """
        Обробити cTrader order error event.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        position_id = getattr(payload, "positionId", None)

        if self._modify_sltp_position_id is not None and str(position_id) == str(
            self._modify_sltp_position_id
        ):
            self._modify_sltp_payload = payload
            self._modify_sltp_error_text = _format_api_error(payload)
            self.logger.error(self._modify_sltp_error_text)
            self._modify_sltp_event.set()
            return

        self._trade_payload = payload
        self._trade_error_text = _format_api_error(payload)
        self.logger.error(self._trade_error_text)
        self._trade_event.set()

    def _on_trade_deferred_error(self, failure) -> None:
        """
        Обробити Twisted Deferred помилку trade request.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        self._trade_error_text = f"cTrader trade deferred error: {failure}"
        self.logger.error(self._trade_error_text)
        self._trade_event.set()

    def _on_modify_sltp_deferred_error(self, failure) -> None:
        """
        Обробити Twisted Deferred помилку modify SL/TP request.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        self._modify_sltp_error_text = f"cTrader modify SL/TP deferred error: {failure}"
        self.logger.error(self._modify_sltp_error_text)
        self._modify_sltp_event.set()

    def _send_app_auth(self) -> None:
        """
        Надіслати ProtoOAApplicationAuthReq.
        """

        if self.client is None:
            raise RuntimeError("cTrader client is not initialized")

        request = ProtoOAApplicationAuthReq()
        request.clientId = self.config.client_id
        request.clientSecret = self.config.client_secret

        deferred = self.client.send(request)
        generation = self._connect_generation
        deferred.addErrback(
            lambda failure: self._on_deferred_error(
                failure,
                generation,
            )
        )

    def _send_get_account_list(self) -> None:
        """
        Надіслати ProtoOAGetAccountListByAccessTokenReq.
        """

        if self.client is None:
            raise RuntimeError("cTrader client is not initialized")

        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = self.config.access_token

        deferred = self.client.send(request)
        generation = self._connect_generation
        deferred.addErrback(
            lambda failure: self._on_deferred_error(
                failure,
                generation,
            )
        )

    def _send_account_auth(self) -> None:
        """
        Надіслати ProtoOAAccountAuthReq.
        """

        if self.client is None:
            raise RuntimeError("cTrader client is not initialized")

        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id
        request.accessToken = self.config.access_token

        deferred = self.client.send(request)
        generation = self._connect_generation
        deferred.addErrback(
            lambda failure: self._on_deferred_error(
                failure,
                generation,
            )
        )

    def _send_trader_req(self) -> None:
        """
        Надіслати ProtoOATraderReq для отримання balance/account info.
        """
        if self.client is None:
            raise RuntimeError("cTrader client is not initialized")

        request = ProtoOATraderReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id

        deferred = self.client.send(request)
        generation = self._connect_generation
        deferred.addErrback(
            lambda failure: self._on_deferred_error(
                failure,
                generation,
            )
        )

    def _send_asset_list_req(self) -> None:
        """
        Надіслати ProtoOAAssetListReq для отримання валюти рахунку.
        """
        if self.client is None:
            raise RuntimeError("cTrader client is not initialized")

        request = ProtoOAAssetListReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id

        deferred = self.client.send(request)
        generation = self._connect_generation
        deferred.addErrback(
            lambda failure: self._on_deferred_error(
                failure,
                generation,
            )
        )

    def _on_deferred_error(
        self,
        failure,
        generation: int,
    ) -> None:
        """
        Обробити Twisted Deferred помилку.

        Deferred-и від старих connection sessions ігноруються.
        """
        if self._retired:
            self.logger.debug(
                "cTrader deferred error ignored from retired session: %s",
                failure,
            )
            return

        if generation != self._connect_generation:
            self.logger.debug(
                "cTrader deferred error ignored by generation mismatch. "
                "failure=%s current_generation=%s callback_generation=%s",
                failure,
                self._connect_generation,
                generation,
            )
            return

        error_message_getter = getattr(failure, "getErrorMessage", None)
        if callable(error_message_getter):
            failure_text = str(error_message_getter() or type(failure).__name__)
        else:
            failure_text = str(failure)

        self.state.last_error_text = (
            "cTrader deferred error " f"stage={self._connect_stage}: {failure_text}"
        )
        if self._deferred_error_generation != generation:
            self.logger.error(self.state.last_error_text)
            self._deferred_error_generation = generation
        else:
            self.logger.debug(
                "Duplicate cTrader deferred error ignored for generation=%s",
                generation,
            )
        self.state.connection_state = BrokerConnectionState.ERROR
        self._connecting = False
        self.state.disconnected_event.set()
        self.state.connected_event.set()

    def _build_account_info(self, payload) -> None:
        """
        Побудувати базовий BrokerAccount з account list payload.

        Account-list response не містить balance/currency/leverage.
        Повний financial snapshot треба брати з account-auth / trader response.
        """
        account = _find_account_payload(
            payload=payload,
            account_id=self.config.ctid_trader_account_id,
        )

        trader_login = ""

        if account is not None:
            trader_login = str(getattr(account, "traderLogin", "") or "")

        self.state.account_info = BrokerAccount(
            broker="CTRADER",
            account_id=str(self.config.ctid_trader_account_id),
            account_mode=self.config.account_mode,
            raw_payload={
                "payload_type": payload.__class__.__name__,
                "account_found": account is not None,
                "trader_login": trader_login,
            },
        )

    def _build_account_info_from_trader(
        self,
        trader_payload: object | None,
        asset_payload: object | None,
    ) -> None:
        """
        Побудувати BrokerAccount з ProtoOATraderRes + ProtoOAAssetListRes.
        """
        trader = getattr(trader_payload, "trader", None)

        if trader is None:
            self.logger.warning(
                "ProtoOATraderRes does not contain trader object.",
            )
            return

        deposit_asset_id = getattr(trader, "depositAssetId", None)
        currency = _get_currency_from_assets(
            asset_payload=asset_payload,
            deposit_asset_id=deposit_asset_id,
        )

        money_digits = int(getattr(trader, "moneyDigits", 2) or 2)
        raw_balance = getattr(trader, "balance", None)

        balance = 0.0
        if raw_balance is not None:
            balance = float(raw_balance) / (10**money_digits)

        leverage_in_cents = getattr(trader, "leverageInCents", None)
        leverage = ""

        if leverage_in_cents not in ("", None):
            leverage = f"1:{int(leverage_in_cents) // 100}"

        trader_login = str(getattr(trader, "traderLogin", "") or "")
        broker_name = str(getattr(trader, "brokerName", "") or "CTRADER")

        self.state.account_info = BrokerAccount(
            broker=broker_name,
            account_id=str(getattr(trader, "ctidTraderAccountId", "")),
            account_mode=self.config.account_mode,
            currency=currency,
            balance=balance,
            raw_payload={
                "payload_type": trader_payload.__class__.__name__,
                "trader_login": trader_login,
                "leverage": leverage,
                "money_digits": money_digits,
                "deposit_asset_id": deposit_asset_id,
            },
        )

    @staticmethod
    def _scale_ctrader_money(
        raw_value: float | None,
        money_digits: int = 2,
    ) -> float:
        """
        Перетворити cTrader money integer у нормальне число.

        Якщо поля немає — повертаємо 0.0.
        """
        if raw_value is None:
            return 0.0

        return float(raw_value) / (10**money_digits)

    def _build_positions(self) -> list[BrokerPosition]:
        """
        Build canonical BrokerPosition list from cTrader positions.
        """

        result: list[BrokerPosition] = []

        for position in self._positions_payload:
            trade_data = getattr(position, "tradeData", None)

            if trade_data is None:
                continue

            trade_side_value = getattr(trade_data, "tradeSide", "")
            trade_side_text = str(trade_side_value).upper()

            side = POSITION_SIDE_BUY

            if trade_side_text in {"SELL", "2"}:
                side = POSITION_SIDE_SELL

            volume_raw = int(getattr(trade_data, "volume", 0) or 0)
            volume = ctr_lot.api_volume_to_lots(volume_raw)

            position_id = getattr(position, "positionId", "")

            position_id_text = str(position_id)
            unrealized_pnl = float(
                self._positions_pnl_payload.get(position_id_text, 0.0)
            )
            unrealized_pnl_raw = self._positions_pnl_raw_payload.get(
                position_id_text,
                {},
            )

            symbol_id = getattr(trade_data, "symbolId", "")

            symbol_name = str(symbol_id)

            try:
                symbol_name = ctr_symbols.get_symbol_name(int(symbol_id))
            except (
                TypeError,
                ValueError,
                KeyError,
            ):
                pass

            price = float(getattr(position, "price", 0) or 0)
            symbol_id_int = int(symbol_id or 0)
            current_price = self._current_price_for_position(
                symbol_id=symbol_id_int,
                side=side,
            )
            spot_row = dict(self._spot_prices.get(symbol_id_int) or {})
            account_currency = ""

            if self.state.account_info is not None:
                account_currency = (
                    str(self.state.account_info.currency or "").strip().upper()
                )

            stop_loss = getattr(position, "stopLoss", None)
            take_profit = getattr(position, "takeProfit", None)

            open_timestamp = getattr(trade_data, "openTimestamp", "")
            label = getattr(trade_data, "label", "")
            comment = getattr(trade_data, "comment", "")

            result.append(
                BrokerPosition(
                    broker="CTRADER",
                    account_id=str(self.config.ctid_trader_account_id),
                    account_mode=self.config.account_mode,
                    position_id=position_id_text,
                    symbol_name=symbol_name,
                    side=side,
                    volume=volume,
                    entry_price=price,
                    current_price=current_price,
                    stop_loss=float(stop_loss) if stop_loss else None,
                    take_profit=float(take_profit) if take_profit else None,
                    unrealized_pnl=unrealized_pnl,
                    currency=account_currency,
                    opened_utc=str(open_timestamp) if open_timestamp else "",
                    raw_payload={
                        "positionId": position_id,
                        "symbolId": symbol_id,
                        "tradeSide": trade_side_text,
                        "api_volume": volume_raw,
                        "lots": volume,
                        "price": price,
                        "openTimestamp": open_timestamp,
                        "label": label,
                        "comment": strip_broker_order_identity(comment),
                        "broker_comment": str(comment or "").strip(),
                        "order_control_mode": get_broker_order_control_mode(comment),
                        "unrealized_pnl": unrealized_pnl,
                        "unrealized_pnl_raw": unrealized_pnl_raw,
                        "current_price": current_price,
                        "bid": spot_row.get("bid"),
                        "ask": spot_row.get("ask"),
                        "spot_timestamp": spot_row.get("timestamp"),
                        "pnl_currency": account_currency,
                    },
                )
            )

        return result

    def get_positions(self) -> list[BrokerPosition]:
        """
        Отримати відкриті cTrader positions.
        """

        if not self.is_connected():
            self.logger.warning(
                "cTrader get_positions called while disconnected.",
            )
            return []

        if self.client is None:
            self.logger.warning("cTrader client is not initialized.")
            return []

        self._positions_event.clear()
        self._positions_payload = []

        request = ProtoOAReconcileReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id

        self.logger.info("Requesting cTrader reconcile positions...")

        deferred = self.client.send(request)
        deferred.addErrback(self._on_positions_deferred_error)

        finished = self._positions_event.wait(timeout=CTRADER_POSITIONS_TIMEOUT_SECONDS)

        if not finished:
            self.logger.error("cTrader reconcile timeout.")
            return []

        position_symbol_ids: set[int] = set()
        if self._positions_payload:
            self._request_positions_unrealized_pnl()
            position_symbol_ids = {
                int(
                    getattr(
                        getattr(position, "tradeData", None),
                        "symbolId",
                        0,
                    )
                    or 0
                )
                for position in self._positions_payload
            }
        self._position_spot_symbol_ids = {
            symbol_id for symbol_id in position_symbol_ids if symbol_id > 0
        }
        self._sync_owned_spot_subscriptions()

        return self._build_positions()

    def _on_reconcile_res(self, payload) -> None:
        """
        Обробити ProtoOAReconcileRes.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        self._positions_payload = list(getattr(payload, "position", []))

        self.logger.info(
            "cTrader reconcile received | positions=%s",
            len(self._positions_payload),
        )

        self._positions_event.set()

    def _on_positions_deferred_error(self, failure) -> None:
        """
        Обробити помилку positions request.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        self.logger.error("cTrader reconcile request failed: %s", failure)
        self._positions_event.set()

    @property
    def broker_state(self) -> str:
        """
        Повернути поточний broker connection state.
        """

        return str(self.state.connection_state)

    def set_session_generation(
        self,
        generation: int,
    ) -> None:
        """
        Встановити generation session.
        """
        self._session_generation = generation

    def retire_session(self) -> None:
        """
        Позначити session як застарілу.

        Старі callbacks і deferred-и мають ігноруватись.
        """

        self.logger.warning(
            "Retiring cTrader adapter session. generation=%s",
            self._session_generation,
        )

        self._retired = True
        self._next_connect_generation()
        self._connecting = False
        self._retired_disconnect_event.clear()

        current_client = self.client

        if current_client is None:
            self._retired_disconnect_event.set()
            self.state.connection_state = BrokerConnectionState.DISCONNECTED
            self.state.disconnected_event.set()
            return

        try:
            current_client.setConnectedCallback(lambda _client: None)
            current_client.setDisconnectedCallback(
                lambda _client, _reason: self._retired_disconnect_event.set()
            )
            current_client.setMessageReceivedCallback(lambda _client, _message: None)
        except Exception as exc:  # noqa: BLE001
            self.logger.debug(
                "cTrader callback detach during retire skipped: %s",
                exc,
            )

        try:
            call_in_ctrader_reactor(current_client.stopService)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "cTrader stopService during retire failed: %s",
                exc,
            )

        self.client = None
        self._spot_event.clear()
        self._spot_prices = {}
        self._spot_subscribed_symbol_ids = set()
        self._position_spot_symbol_ids = set()
        self._workspace_spot_symbol_ids = set()
        self.state.connection_state = BrokerConnectionState.DISCONNECTED
        self.state.disconnected_event.set()

    def wait_for_retired_disconnect(self, timeout_seconds: float) -> bool:
        """Wait for bounded evidence that a retired client disconnected."""
        return self._retired_disconnect_event.wait(
            timeout=max(0.0, float(timeout_seconds)),
        )

    def is_session_alive(self) -> bool:
        """
        Перевірка актуальності session.
        """
        return not self._retired

    def _request_positions_unrealized_pnl(self) -> None:
        """
        Отримати unrealized P/L для відкритих cTrader positions.

        P/L приходить не в ProtoOAReconcileRes, а окремим response:
        ProtoOAGetPositionUnrealizedPnLRes.
        """
        if self.client is None:
            return

        self._positions_pnl_event.clear()
        self._positions_pnl_payload = {}
        self._positions_pnl_raw_payload = {}

        request = ProtoOAGetPositionUnrealizedPnLReq()
        request.ctidTraderAccountId = self.config.ctid_trader_account_id

        self.logger.info("Requesting cTrader unrealized P/L...")

        deferred = self.client.send(request)
        deferred.addErrback(self._on_positions_pnl_deferred_error)

        finished = self._positions_pnl_event.wait(
            timeout=CTRADER_POSITIONS_TIMEOUT_SECONDS
        )

        if not finished:
            self.logger.warning("cTrader unrealized P/L timeout.")

    def _on_position_unrealized_pnl_res(
        self,
        payload,
    ) -> None:
        """
        Обробити ProtoOAGetPositionUnrealizedPnLRes.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        money_digits = int(getattr(payload, "moneyDigits", 2) or 2)

        pnl_map: dict[str, float] = {}
        raw_map: dict[str, dict] = {}

        for item in getattr(payload, "positionUnrealizedPnL", []):
            position_id = str(getattr(item, "positionId", "") or "")

            if not position_id:
                continue

            raw_gross = getattr(item, "grossUnrealizedPnL", None)
            raw_net = getattr(item, "netUnrealizedPnL", None)

            gross_pnl = self._scale_ctrader_money(
                raw_gross,
                money_digits,
            )
            net_pnl = self._scale_ctrader_money(
                raw_net,
                money_digits,
            )

            pnl_map[position_id] = net_pnl
            raw_map[position_id] = {
                "moneyDigits": money_digits,
                "raw_gross_unrealized_pnl": raw_gross,
                "raw_net_unrealized_pnl": raw_net,
                "gross_unrealized_pnl": gross_pnl,
                "net_unrealized_pnl": net_pnl,
            }

        self._positions_pnl_payload = pnl_map
        self._positions_pnl_raw_payload = raw_map

        self.logger.info(
            "cTrader unrealized P/L received | positions=%s",
            len(pnl_map),
        )

        self._positions_pnl_event.set()

    def _on_positions_pnl_deferred_error(
        self,
        failure,
    ) -> None:
        """
        Обробити помилку запиту cTrader unrealized P/L.
        """
        if not self.is_session_alive():
            self.logger.warning("Ignoring callback from retired session.")
            return

        self.logger.error(
            "cTrader unrealized P/L deferred error: %s",
            failure,
        )
        self._positions_pnl_event.set()


def _get_env_required(name: str) -> str:
    """
    Прочитати обов'язкову змінну середовища.
    """

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Не задано змінну середовища {name}")
    return value


def _ensure_access_token() -> str:
    """
    Отримати чинний access_token з tokens.json.

    Важливо: production adapter не генерує фейковий token і не викликає
    старий refresh_if_needed(), бо він зараз небезпечний для runtime flow.
    Якщо token прострочений — зупиняємося до TCP connect з чітким текстом.
    """

    try:
        tokens = load_tokens()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            "cTrader tokens.json не читається. "
            "Спочатку онови tokens/tokens.json через manual auth tool."
        ) from exc

    if not tokens:
        raise RuntimeError(
            "cTrader tokens.json відсутній або порожній. "
            "Спочатку онови tokens/tokens.json через manual auth tool."
        )

    access_token = str(tokens.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError(
            "cTrader access_token порожній. "
            "Спочатку онови tokens/tokens.json через manual auth tool."
        )

    expires_at = _safe_int(tokens.get("expires_at", 0))
    if expires_at and int(time.time()) >= expires_at - 60:
        raise RuntimeError(
            "cTrader access_token прострочений або майже прострочений. "
            "Спочатку онови tokens/tokens.json через manual auth tool."
        )

    return access_token


def _safe_int(value: int | str | float | None) -> int:
    """
    Безпечно перетворити значення на int.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_api_error(payload) -> str:
    """
    Сформувати короткий текст cTrader API error.
    """

    error_code = getattr(payload, "errorCode", None)
    description = getattr(payload, "description", None)
    return f"cTrader API ERROR: {error_code} | {description}"


def _find_account_payload(payload, account_id: int):
    """
    Знайти account payload по ctidTraderAccountId.
    """

    accounts = list(getattr(payload, "ctidTraderAccount", []))
    for account in accounts:
        current_id = getattr(account, "ctidTraderAccountId", None)
        if current_id == account_id:
            return account
    return None


def _get_currency_from_assets(
    asset_payload: object | None,
    deposit_asset_id: object | None,
) -> str:
    """
    Повернути валюту рахунку за depositAssetId.
    """
    if asset_payload is None or deposit_asset_id in ("", None):
        return ""

    assets = getattr(asset_payload, "asset", [])

    for asset in assets:
        asset_id = getattr(asset, "assetId", None)
        if str(asset_id) != str(deposit_asset_id):
            continue

        name = str(getattr(asset, "name", "") or "").strip()
        display_name = str(getattr(asset, "displayName", "") or "").strip()

        return name or display_name

    return ""


def _build_account_list_from_payload(payload: object) -> list[dict]:
    """
    Побудувати список cTrader accounts з ProtoOAGetAccountListByAccessTokenRes.
    """
    result = []

    for account in getattr(payload, "ctidTraderAccount", []):
        account_id = str(getattr(account, "ctidTraderAccountId", "") or "").strip()
        trader_login = str(getattr(account, "traderLogin", "") or "").strip()
        account_number = str(getattr(account, "accountNumber", "") or "").strip()
        is_live = bool(getattr(account, "isLive", False))

        if not account_id:
            continue

        result.append(
            {
                "account_id": account_id,
                "trader_login": trader_login,
                "account_number": account_number,
                "account_mode": "LIVE" if is_live else "DEMO",
            }
        )

    return result


def stop_global_reactor() -> None:
    """
    Diagnostic helper для ручного завершення reactor.

    У production flow RuntimeEngine не має зупиняти глобальний reactor
    після кожного disconnect/reconnect.
    """

    stop_ctrader_reactor_for_diagnostics()
