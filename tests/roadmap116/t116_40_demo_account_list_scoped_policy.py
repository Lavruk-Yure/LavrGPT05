"""T116-40 TEST_ONLY — локальна scoped-політика AccountList.

Не змінює production або T116-29 на диску. Працює тільки всередині
контекстного менеджера в ізольованому TEST_ONLY процесі; не відкриває TCP.
AccountList дозволений лише для очікуваного токена та не дозволяє торгівлю.
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
from tests.roadmap116.t116_39_demo_account_identity_preflight import (
    ACCOUNT_LIST_REQUEST,
    ACCOUNT_LIST_RESPONSE,
    existing_outbound_policy_locked,
)

TEST_ONLY_TOKEN = "T11640_SYNTHETIC_TOKEN"
EXTENDED_REQUEST_NAMES = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
    ACCOUNT_LIST_REQUEST,
    "ProtoHeartbeatEvent",
)
EXTENDED_UNSCOPED = frozenset({
    "ProtoOAApplicationAuthReq",
    ACCOUNT_LIST_REQUEST,
    "ProtoHeartbeatEvent",
})
SUCCESS_MARKER = "T116-40=GREEN_OFFLINE_SCOPED_ACCOUNT_LIST_POLICY"
SDK_READY = "VERIFIED_NO_EXTERNAL_NETWORK"


@contextmanager
def guarded_scoped_account_list(
    *,
    client_type: type,
    tcp_protocol_type: type,
    frame_sender_type: type,
    request_messages: object,
    common_messages: object,
    expected_token: str,
) -> Iterator[None]:
    """Тимчасово дозволити AccountList, не послаблюючи T116-29.

    Тестувати лише в окремому процесі: тимчасова заміна глобальних
    констант T116-29 не потокобезпечна й НЕ призначена для production.
    """
    if not existing_outbound_policy_locked():
        raise RuntimeError("T116-40: базова політика змінилася")
    if (
        type(expected_token) is not str
        or not expected_token
        or len(expected_token) > 8192
        or expected_token != expected_token.strip()
    ):
        raise PermissionError("T116-40: токен некоректний")

    list_type = getattr(request_messages, ACCOUNT_LIST_REQUEST, None)
    envelope_type = getattr(common_messages, "ProtoMessage", None)
    if not (
        isinstance(list_type, type)
        and issubclass(list_type, Message)
        and isinstance(envelope_type, type)
        and issubclass(envelope_type, Message)
        and "accessToken" in list_type.DESCRIPTOR.fields_by_name
    ):
        raise RuntimeError("T116-40: SDK AccountList схема невідома")
    list_payload_type = getattr(list_type(), "payloadType", None)
    if type(list_payload_type) is not int or list_payload_type <= 0:
        raise RuntimeError("T116-40: payloadType некоректний")

    def check_token(message: object) -> None:
        if type(message) is list_type:
            if getattr(message, "accessToken", None) != expected_token:
                raise PermissionError("T116-40: чужий AccountList токен")

    def check_frame(frame: object) -> None:
        if type(frame) is not bytes:
            return  # T116-29 сам відхилить невірний тип.
        try:
            envelope = envelope_type()
            envelope.ParseFromString(frame)
            if envelope.payloadType != list_payload_type:
                return  # Решту дозволів перевіряє T116-29.
            message = list_type()
            message.ParseFromString(envelope.payload)
            if not message.IsInitialized():
                raise ValueError("неповний protobuf")
            check_token(message)
        except (DecodeError, ValueError, TypeError, PermissionError) as error:
            raise PermissionError("T116-40: AccountList кадр заборонений") from error

    with (
        patch.object(outbound, "PERMITTED_REQUEST_NAMES", EXTENDED_REQUEST_NAMES),
        patch.object(outbound, "UNSCOPED_REQUEST_NAMES", EXTENDED_UNSCOPED),
    ):
        with outbound.guarded_sdk_outbound(
            client_type=client_type,
            tcp_protocol_type=tcp_protocol_type,
            frame_sender_type=frame_sender_type,
            request_messages=request_messages,
            common_messages=common_messages,
        ):
            sdk_client_send = getattr(client_type, "send")
            sdk_tcp_send = getattr(tcp_protocol_type, "send")
            sdk_frame_send = getattr(frame_sender_type, "sendString")

            def client_send(
                client: object, message: object, *args: Any, **kwargs: Any
            ) -> Any:
                check_token(message)
                return sdk_client_send(client, message, *args, **kwargs)

            def tcp_send(
                protocol: object, message: object, *args: Any, **kwargs: Any
            ) -> Any:
                check_token(message)
                return sdk_tcp_send(protocol, message, *args, **kwargs)

            def frame_send(
                protocol: object, frame: object, *args: Any, **kwargs: Any
            ) -> Any:
                check_frame(frame)
                return sdk_frame_send(protocol, frame, *args, **kwargs)

            with (
                patch.object(client_type, "send", client_send),
                patch.object(tcp_protocol_type, "send", tcp_send),
                patch.object(frame_sender_type, "sendString", frame_send),
            ):
                yield


def sdk_schema_preflight() -> str:
    """Перевірити лише protobuf-типи, без Client, credentials і мережі."""
    if find_spec("ctrader_open_api") is None:
        return "NOT_INSTALLED_LOCAL_RUNNER"
    try:
        with external_tcp_denied():
            messages = import_module(
                "ctrader_open_api.messages.OpenApiMessages_pb2"
            )
            list_type = getattr(messages, ACCOUNT_LIST_REQUEST)
            response_type = getattr(messages, ACCOUNT_LIST_RESPONSE)
            if not all(
                isinstance(item, type) and issubclass(item, Message)
                for item in (list_type, response_type)
            ):
                return "SDK_SCHEMA_INCOMPATIBLE"
            fields = list_type.DESCRIPTOR.fields_by_name
            if "accessToken" not in fields:
                return "SDK_SCHEMA_INCOMPATIBLE"
            if type(list_type().payloadType) is not int:
                return "SDK_SCHEMA_INCOMPATIBLE"
    except (
        AttributeError, ImportError, KeyError, OSError,
        RuntimeError, TypeError, ValueError,
    ):
        return "SDK_SCHEMA_FAILED"
    return SDK_READY


def format_report(sdk_status: str) -> str:
    """Звіт без токенів, реальних ID і мережевих результатів."""
    baseline = existing_outbound_policy_locked()
    ready = baseline and sdk_status == SDK_READY
    return "\n".join((
        "T116-40 TEST_ONLY | scoped AccountList policy OFFLINE",
        "baseline_t116_29=" + ("UNCHANGED" if baseline else "CHANGED_DENIED"),
        "account_list_extension=TEST_ONLY_SCOPED_NOT_NETWORK_WIRED",
        "account_list_token=EXACT_MATCH_THREE_OUTBOUND_LEVELS",
        f"sdk_account_list_schema={sdk_status}",
        "allowed_requests=THREE_READONLY_PLUS_ACCOUNT_LIST_PLUS_HEARTBEAT",
        "real_identity_pair=NOT_QUERIED_NO_NETWORK",
        "credentials=NOT_READ",
        "sdk_client_constructor=NOT_CALLED",
        "child_process=NOT_STARTED",
        "external_tcp=BLOCKED",
        "real_broker_requests=0",
        "production_changes=0",
        "network_launch_authorized=NO",
        SUCCESS_MARKER if ready else "T116-40=NOT_READY_OFFLINE",
    ))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI допускає тільки офлайн-пробу SDK схеми."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--offline-preflight", action="store_true", required=True)
    args = parser.parse_args(argv)
    if not args.offline_preflight:
        return 2
    with external_tcp_denied():
        report = format_report(sdk_schema_preflight())
    print(report)
    return 0 if SUCCESS_MARKER in report.splitlines() else 2


if __name__ == "__main__":
    raise SystemExit(main())
