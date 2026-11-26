"""T116-46 TEST_ONLY — ізольований DEMO EURUSD SpotEvent preflight.

Лише перевірка protobuf, котирувань і триступеневого outbound guard.
Жодного мережевого launcher, Client(), credentials чи production-змін.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from importlib import import_module
from importlib.util import find_spec
from typing import Any
from unittest.mock import patch

from google.protobuf.message import DecodeError, Message

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied

DEMO_ACCOUNT_ID = 46368962
OBSERVED_EURUSD_SYMBOL_ID = 1
SUBSCRIBE_NAME = "ProtoOASubscribeSpotsReq"
SPOT_NAME = "ProtoOASpotEvent"
SUBSCRIBE_RESPONSE_NAME = "ProtoOASubscribeSpotsRes"
EXTENDED_REQUEST_NAMES = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
    SUBSCRIBE_NAME,
    "ProtoHeartbeatEvent",
)
BASELINE_NAMES = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
    "ProtoHeartbeatEvent",
)
SUCCESS = "T116-46=GREEN_OFFLINE_DEMO_EURUSD_QUOTES_PREFLIGHT"


def validate_spot_subscription(message: Any, request_type: type) -> None:
    """Пропускати лише EURUSD=1 з timestamp для заданого DEMO ID."""
    if type(message) is not request_type:
        raise PermissionError("T116-46: невідомий тип підписки")
    if getattr(message, "ctidTraderAccountId", None) != DEMO_ACCOUNT_ID:
        raise PermissionError("T116-46: сторонній DEMO account")
    if list(getattr(message, "symbolId", ())) != [OBSERVED_EURUSD_SYMBOL_ID]:
        raise PermissionError("T116-46: підписка лише EURUSD symbolId=1")
    if (
        "subscribeToSpotTimestamp" not in message.DESCRIPTOR.fields_by_name
        or not message.HasField("subscribeToSpotTimestamp")
        or getattr(message, "subscribeToSpotTimestamp", None) is not True
    ):
        raise PermissionError("T116-46: підписка без timestamp заборонена")
    if not message.IsInitialized():
        raise PermissionError("T116-46: неповний SubscribeSpotsReq")


@contextmanager
def guarded_scoped_quote_subscription(
    *,
    client_type: type,
    tcp_protocol_type: type,
    frame_sender_type: type,
    request_messages: object,
    common_messages: object,
) -> Iterator[None]:
    """У локальному TEST_ONLY контексті дозволити рівно один SubscribeSpots.

    Модифікація глобальних констант T116-29 тимчасова і не потокобезпечна.
    Використовувати тільки в ізольованому тестовому процесі.
    """
    if (
        outbound.PERMITTED_REQUEST_NAMES != BASELINE_NAMES
        or outbound.UNSCOPED_REQUEST_NAMES != frozenset({
            "ProtoOAApplicationAuthReq", "ProtoHeartbeatEvent",
        })
    ):
        raise RuntimeError("T116-46: базова політика T116-29 змінилася")
    request_type = getattr(request_messages, SUBSCRIBE_NAME, None)
    envelope_type = getattr(common_messages, "ProtoMessage", None)
    if not (
        isinstance(request_type, type)
        and issubclass(request_type, Message)
        and isinstance(envelope_type, type)
        and issubclass(envelope_type, Message)
    ):
        raise RuntimeError("T116-46: немає protobuf-схеми підписки")
    field_names = request_type.DESCRIPTOR.fields_by_name
    if not {
        "ctidTraderAccountId", "symbolId", "subscribeToSpotTimestamp",
    }.issubset(field_names):
        raise RuntimeError("T116-46: схема SubscribeSpotsReq несумісна")
    subscribe_payload_type = getattr(request_type(), "payloadType", None)
    if type(subscribe_payload_type) is not int or subscribe_payload_type <= 0:
        raise RuntimeError("T116-46: некоректний payloadType")

    def check_object(message: object) -> None:
        if type(message) is request_type:
            validate_spot_subscription(message, request_type)

    def check_frame(frame: object) -> None:
        if type(frame) is not bytes:
            return  # Остаточно відхиляє T116-29.
        try:
            envelope = envelope_type()
            envelope.ParseFromString(frame)
            if not envelope.IsInitialized():
                raise ValueError("незаповнений конверт")
            if envelope.payloadType != subscribe_payload_type:
                return  # Усі інші типи перевіряє T116-29.
            message = request_type()
            message.ParseFromString(envelope.payload)
            validate_spot_subscription(message, request_type)
        except (DecodeError, ValueError, TypeError, PermissionError) as error:
            raise PermissionError(
                "T116-46: заборонений SubscribeSpots frame"
            ) from error

    with patch.object(
        outbound, "PERMITTED_REQUEST_NAMES", EXTENDED_REQUEST_NAMES,
    ):
        with outbound.guarded_sdk_outbound(
            client_type=client_type,
            tcp_protocol_type=tcp_protocol_type,
            frame_sender_type=frame_sender_type,
            request_messages=request_messages,
            common_messages=common_messages,
        ):
            original_client = getattr(client_type, "send")
            original_tcp = getattr(tcp_protocol_type, "send")
            original_frame = getattr(frame_sender_type, "sendString")

            def client_send(
                client: object, message: object, *args: Any, **kwargs: Any,
            ) -> Any:
                check_object(message)
                return original_client(client, message, *args, **kwargs)

            def tcp_send(
                protocol: object, message: object, *args: Any, **kwargs: Any,
            ) -> Any:
                check_object(message)
                return original_tcp(protocol, message, *args, **kwargs)

            def frame_send(
                protocol: object, frame: object, *args: Any, **kwargs: Any,
            ) -> Any:
                check_frame(frame)
                return original_frame(protocol, frame, *args, **kwargs)

            with (
                patch.object(client_type, "send", client_send),
                patch.object(tcp_protocol_type, "send", tcp_send),
                patch.object(frame_sender_type, "sendString", frame_send),
            ):
                yield


def sdk_schema_preflight() -> str:
    """Перевірити справжні protobuf-класи без створення SDK Client."""
    if find_spec("ctrader_open_api") is None:
        return "NOT_INSTALLED_LOCAL_RUNNER"
    try:
        with external_tcp_denied():
            module = import_module(
                "ctrader_open_api.messages.OpenApiMessages_pb2"
            )
            subscribe_type = getattr(module, SUBSCRIBE_NAME)
            response_type = getattr(module, SUBSCRIBE_RESPONSE_NAME)
            spot_type = getattr(module, SPOT_NAME)
            if not all(
                isinstance(item, type) and issubclass(item, Message)
                for item in (subscribe_type, response_type, spot_type)
            ):
                return "SDK_SCHEMA_INCOMPATIBLE"
            fields = subscribe_type.DESCRIPTOR.fields_by_name
            spot_fields = spot_type.DESCRIPTOR.fields_by_name
            if not {
                "ctidTraderAccountId", "symbolId",
                "subscribeToSpotTimestamp",
            }.issubset(fields):
                return "SDK_SCHEMA_INCOMPATIBLE"
            if not {
                "ctidTraderAccountId", "symbolId", "bid", "ask", "timestamp",
            }.issubset(spot_fields):
                return "SDK_SCHEMA_INCOMPATIBLE"
            request = subscribe_type()
            request.ctidTraderAccountId = DEMO_ACCOUNT_ID
            request.symbolId.append(OBSERVED_EURUSD_SYMBOL_ID)
            request.subscribeToSpotTimestamp = True
            validate_spot_subscription(request, subscribe_type)
    except (
        AttributeError, ImportError, KeyError, OSError,
        RuntimeError, TypeError, ValueError, PermissionError,
    ):
        return "SDK_SCHEMA_FAILED"
    return "VERIFIED_NO_EXTERNAL_NETWORK"


def main(argv: Sequence[str] | None = None) -> int:
    """Дозволити лише офлайн-пробу; ні --live, ні --demo-network."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--offline-preflight", action="store_true", required=True)
    args = parser.parse_args(argv)
    if not args.offline_preflight:
        return 2
    with external_tcp_denied():
        status = sdk_schema_preflight()
    print("T116-46 TEST_ONLY | EURUSD quotes OFFLINE preflight")
    print(f"sdk_quotes_schema={status}")
    print("symbol_id=1_DEMO_ACCOUNT_ONLY")
    print("subscribe_outbound=TEST_ONLY_SCOPED_NOT_NETWORK_WIRED")
    print("quote_fields=BID_ASK_OPTIONAL_TIMESTAMP_OPTIONAL")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(SUCCESS if status == "VERIFIED_NO_EXTERNAL_NETWORK" else
          "T116-46=NOT_READY_OFFLINE")
    return 0 if status == "VERIFIED_NO_EXTERNAL_NETWORK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
