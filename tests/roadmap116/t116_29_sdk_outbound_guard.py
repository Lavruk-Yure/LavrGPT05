"""T116-29 TEST_ONLY — заборона торгових protobuf у трьох межах SDK.

Не створює Client або TCP-з'єднання. Працює лише як тимчасова підміна
в ізольованому процесі тесту; не є production-захистом.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from google.protobuf.message import DecodeError, Message

DEMO_API_ACCOUNT_ID = 46368962
MAX_OUTBOUND_FRAME_BYTES = 65536
PERMITTED_REQUEST_NAMES = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
    "ProtoHeartbeatEvent",
)
UNSCOPED_REQUEST_NAMES = frozenset({
    "ProtoOAApplicationAuthReq",
    "ProtoHeartbeatEvent",
})


@contextmanager
def guarded_sdk_outbound(
    *,
    client_type: type,
    tcp_protocol_type: type,
    frame_sender_type: type,
    request_messages: object,
    common_messages: object,
) -> Iterator[None]:
    """Тимчасово перевірити об'єкт та конверт до мережевого запису.

    SDK-подібний транспорт має бути повністю відомим. Будь-яка зміна
    сигнатури, невідомий payloadType або обхід перевірки — відмова.
    """
    if "sendString" in tcp_protocol_type.__dict__:
        raise RuntimeError("T116-29: TcpProtocol перевизначив sendString")
    original_client_send = getattr(client_type, "send", None)
    original_tcp_send = getattr(tcp_protocol_type, "send", None)
    original_frame_send = getattr(frame_sender_type, "sendString", None)
    if not all(callable(item) for item in (
        original_client_send, original_tcp_send, original_frame_send,
    )):
        raise RuntimeError("T116-29: SDK outbound API змінився")

    envelope_type = getattr(common_messages, "ProtoMessage", None)
    if not isinstance(envelope_type, type) or not issubclass(envelope_type, Message):
        raise RuntimeError("T116-29: ProtoMessage відсутній")

    by_class: dict[type, tuple[str, int]] = {}
    by_payload: dict[int, type] = {}
    for name in PERMITTED_REQUEST_NAMES:
        module = (
            common_messages if name == "ProtoHeartbeatEvent"
            else request_messages
        )
        message_type = getattr(module, name, None)
        if not isinstance(message_type, type) or not issubclass(message_type, Message):
            raise RuntimeError(f"T116-29: тип {name} відсутній")
        payload_type = getattr(message_type(), "payloadType", None)
        if type(payload_type) is not int or payload_type <= 0:
            raise RuntimeError(f"T116-29: payloadType {name} некоректний")
        if payload_type in by_payload:
            raise RuntimeError("T116-29: повторний payloadType")
        by_class[message_type] = (name, payload_type)
        by_payload[payload_type] = message_type

    def validate_object(message: object) -> None:
        details = by_class.get(type(message))
        if details is None:
            raise PermissionError("T116-29: protobuf поза read-only списком")
        allowed_name, allowed_payload_type = details
        if getattr(message, "payloadType", None) != allowed_payload_type:
            raise PermissionError("T116-29: змінено payloadType")
        initialized = getattr(message, "IsInitialized", None)
        if not callable(initialized) or not initialized():
            raise PermissionError("T116-29: неповне повідомлення")
        if allowed_name not in UNSCOPED_REQUEST_NAMES:
            if getattr(message, "ctidTraderAccountId", None) != DEMO_API_ACCOUNT_ID:
                raise PermissionError("T116-29: чужий DEMO API ID")
        if allowed_name == "ProtoOASymbolsListReq":
            if getattr(message, "includeArchivedSymbols", False):
                raise PermissionError("T116-29: архівні символи заборонені")

    def validate_frame(frame: object) -> None:
        if not isinstance(frame, bytes):
            raise PermissionError("T116-29: потрібні серіалізовані байти")
        if not 0 < len(frame) <= MAX_OUTBOUND_FRAME_BYTES:
            raise PermissionError("T116-29: порожній або надмірний кадр")
        try:
            envelope = envelope_type()
            envelope.ParseFromString(frame)
            if not envelope.IsInitialized():
                raise ValueError("неповний конверт")
            frame_payload_type = getattr(envelope, "payloadType", 0)
            frame_message_type = by_payload.get(frame_payload_type)
            if frame_message_type is None:
                raise ValueError("невідомий payloadType")
            payload = frame_message_type()
            payload.ParseFromString(envelope.payload)
            validate_object(payload)
        except (DecodeError, ValueError, TypeError, PermissionError) as exc:
            raise PermissionError("T116-29: заборонений TCP protobuf-кадр") from exc

    def guarded_client_send(client: object, message: object,
                            *args: Any, **kwargs: Any) -> Any:
        validate_object(message)
        return original_client_send(client, message, *args, **kwargs)

    def guarded_tcp_send(protocol: object, message: object,
                         *args: Any, **kwargs: Any) -> Any:
        validate_object(message)
        return original_tcp_send(protocol, message, *args, **kwargs)

    def guarded_frame_send(protocol: object, frame: object,
                           *args: Any, **kwargs: Any) -> Any:
        if not isinstance(protocol, tcp_protocol_type):
            raise PermissionError("T116-29: невідомий protocol instance")
        validate_frame(frame)
        return original_frame_send(protocol, frame, *args, **kwargs)

    with (
        patch.object(client_type, "send", guarded_client_send),
        patch.object(tcp_protocol_type, "send", guarded_tcp_send),
        patch.object(frame_sender_type, "sendString", guarded_frame_send),
    ):
        yield
