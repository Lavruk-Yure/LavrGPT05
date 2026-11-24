"""T116-22 TEST_ONLY — ізольований cTrader DEMO читач без мережевого запуску.

Цей модуль не імпортує LGE, RuntimeEngine, IB або cTrader TCP-клієнт.
Виклик транспорту можливий лише через явний список неторгових protobuf.
Реальне мережеве підключення навмисно не реалізоване у T116-22.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Protocol

from google.protobuf.message import Message

DEMO_API_ACCOUNT_ID = 46368962
MAX_CAPTURE_SECONDS = 60.0
ALLOWED_REQUEST_NAMES = frozenset({
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
    "ProtoOASubscribeSpotsReq",
    "ProtoOAUnsubscribeSpotsReq",
    "ProtoHeartbeatEvent",
})
UNSCOPED_REQUEST_NAMES = frozenset({
    "ProtoOAApplicationAuthReq",
    "ProtoHeartbeatEvent",
})


class ReadOnlySender(Protocol):
    """TEST_ONLY transport boundary: приймає лише protobuf-об'єкти."""

    def send(self, message: Message) -> None: ...


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    """Один сирий SpotEvent із незалежним часом останнього Bid/Ask."""

    received_utc: datetime
    broker_event_utc: datetime | None
    raw_bid_present: bool
    raw_ask_present: bool
    bid: float | None
    ask: float | None
    bid_received_utc: datetime | None
    ask_received_utc: datetime | None
    side_age_seconds: float | None
    zero_spread_origin: str


class StandaloneDemoQuoteReader:
    """Читати SpotEvent і не допускати торгових protobuf до свого sender."""

    def __init__(
        self,
        *,
        account_mode: str,
        account_id: int,
        symbol_id: int,
        sender: ReadOnlySender,
        allowed_types: Mapping[str, type[Message]],
        spot_event_type: type[Message],
        now_utc: Callable[[], datetime],
    ) -> None:
        if account_mode != "DEMO" or account_id != DEMO_API_ACCOUNT_ID:
            raise ValueError(
                "T116-22: дозволено тільки підтверджений DEMO API ID"
            )
        if symbol_id <= 0:
            raise ValueError("T116-22: symbol ID повинен бути додатним")
        self.account_id = account_id
        self.symbol_id = symbol_id
        self.sender = sender
        self.allowed_types = allowed_types
        self.spot_event_type = spot_event_type
        self.now_utc = now_utc
        self.records: list[QuoteObservation] = []
        self.bid: float | None = None
        self.ask: float | None = None
        self.bid_received_utc: datetime | None = None
        self.ask_received_utc: datetime | None = None

    def send_read_only(self, message: Message) -> None:
        """Fail-closed: заборонити торгові, невідомі й чужі account-запити."""
        if not isinstance(message, Message):
            raise PermissionError("T116-22: raw/unknown protobuf заборонено")
        name = message.DESCRIPTOR.name
        if name not in ALLOWED_REQUEST_NAMES:
            raise PermissionError(f"T116-22: protobuf {name} заборонено")
        if type(message) is not self.allowed_types.get(name):
            raise PermissionError("T116-22: невідомий клас protobuf")
        if name not in UNSCOPED_REQUEST_NAMES:
            field = message.DESCRIPTOR.fields_by_name.get("ctidTraderAccountId")
            if field is None:
                raise PermissionError(
                    "T116-22: account ID відсутній у схемі"
                )
            if int(getattr(message, "ctidTraderAccountId", 0)) != self.account_id:
                raise PermissionError("T116-22: чужий account ID")
        if not message.IsInitialized():
            raise PermissionError("T116-22: неповний protobuf")
        self.sender.send(message)

    @staticmethod
    def reject_raw_packet(_packet: bytes) -> None:
        """Не дозволяти обхід protobuf-перевірки готовим TCP-пакетом."""
        raise PermissionError("T116-22: raw TCP пакет заборонено")

    @staticmethod
    def _optional_positive(payload: Message, field_name: str) -> int | None:
        """Не приймати default=0 за справжню сторону котирування."""
        if field_name not in payload.DESCRIPTOR.fields_by_name:
            return None
        if not payload.HasField(field_name):
            return None
        value = int(getattr(payload, field_name))
        return value if value > 0 else None

    def on_spot_event(self, payload: Message) -> QuoteObservation | None:
        """Спостерігати лише EURUSD symbol ID і цільовий DEMO account."""
        if not isinstance(payload, Message):
            return None
        if type(payload) is not self.spot_event_type:
            return None
        if payload.DESCRIPTOR.name != "ProtoOASpotEvent":
            return None
        if int(getattr(payload, "ctidTraderAccountId", 0)) != self.account_id:
            return None
        if int(getattr(payload, "symbolId", 0)) != self.symbol_id:
            return None

        received = self.now_utc().astimezone(UTC)
        raw_bid = self._optional_positive(payload, "bid")
        raw_ask = self._optional_positive(payload, "ask")
        raw_time = self._optional_positive(payload, "timestamp")
        broker_event_utc = None
        if raw_time is not None:
            try:
                broker_event_utc = datetime.fromtimestamp(raw_time / 1000, tz=UTC)
            except (ValueError, OverflowError, OSError):
                broker_event_utc = None
        if raw_bid is not None:
            self.bid = raw_bid / 100000
            self.bid_received_utc = received
        if raw_ask is not None:
            self.ask = raw_ask / 100000
            self.ask_received_utc = received
        side_age = None
        if self.bid_received_utc is not None and self.ask_received_utc is not None:
            side_age = abs(
                (self.bid_received_utc - self.ask_received_utc).total_seconds()
            )
            if not isfinite(side_age):
                raise ValueError(
                    "T116-22: некоректний час сторін котирування"
                )
        origin = "NOT_ZERO"
        if self.bid is not None and self.ask is not None and self.bid == self.ask:
            origin = (
                "RAW_BOTH_EQUAL" if raw_bid is not None and raw_ask is not None
                else "CACHE_MERGE_EQUAL"
            )
        observation = QuoteObservation(
            received_utc=received,
            broker_event_utc=broker_event_utc,
            raw_bid_present=raw_bid is not None,
            raw_ask_present=raw_ask is not None,
            bid=self.bid,
            ask=self.ask,
            bid_received_utc=self.bid_received_utc,
            ask_received_utc=self.ask_received_utc,
            side_age_seconds=side_age,
            zero_spread_origin=origin,
        )
        self.records.append(observation)
        return observation


def capture_bounded_offline(
    *,
    connect: Callable[[], None],
    poll: Callable[[float], None],
    disconnect: Callable[[], None],
    monotonic: Callable[[], float],
    duration_seconds: float = MAX_CAPTURE_SECONDS,
) -> None:
    """TEST_ONLY цикл із лімітом часу та disconnect у finally.

    poll зобов'язаний поважати переданий timeout. Для справжнього SDK
    знадобиться окремий тест транспорту та аварійний ліміт процесу.
    """
    if not 0 < duration_seconds <= MAX_CAPTURE_SECONDS:
        raise ValueError("T116-22: недопустима тривалість збору")
    deadline = monotonic() + duration_seconds
    try:
        connect()
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            poll(min(remaining, 1.0))
    finally:
        disconnect()
