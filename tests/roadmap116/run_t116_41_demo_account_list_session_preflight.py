"""T116-41 TEST_ONLY — callback AccountList + outbound guard без мережі."""

from __future__ import annotations

import ast
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from tests.roadmap116.run_t116_29_sdk_outbound_transport_guard import (
    FakeClient,
    FakeFrameSender,
    FakeTcpProtocol,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_39_demo_account_identity_preflight import (
    EXPECTED_API_ACCOUNT_ID,
    EXPECTED_GUI_TRADER_LOGIN,
    existing_outbound_policy_locked,
)
from tests.roadmap116.t116_40_demo_account_list_scoped_policy import (
    guarded_scoped_account_list,
)
from tests.roadmap116.t116_41_demo_account_list_session import (
    OfflineAccountListSession,
    RESPONSE_NAMES,
    SESSION_TIMEOUT_SECONDS,
)

SOURCE = Path(__file__).with_name("t116_41_demo_account_list_session.py")
SYNTHETIC_TOKEN = "T11641_SYNTHETIC_ACCESS_TOKEN"
RESPONSE_IDS = {
    "ProtoOAApplicationAuthRes": 1407,
    "ProtoOAGetAccountListByAccessTokenRes": 1408,
}


class Clock:
    """Керований монотонний годинник."""

    def __init__(self) -> None:
        self.seconds = 100.0

    def __call__(self) -> float:
        return self.seconds


def synthetic_sdk() -> tuple[object, object]:
    """Побудувати protobuf-схему для реальної перевірки серіалізації."""
    schema = getattr(descriptor_pb2, "FileDescriptorProto")()
    field_type = getattr(descriptor_pb2, "FieldDescriptorProto")
    schema.name = "t11641_demo_account_list.proto"
    schema.package = "t11641"
    schema.syntax = "proto2"
    names = (
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
        "ProtoOAGetAccountListByAccessTokenReq",
        "ProtoHeartbeatEvent",
        "ProtoOANewOrderReq",
        "ProtoOAApplicationAuthRes",
        "ProtoOAGetAccountListByAccessTokenRes",
        "ProtoOACtidTraderAccount",
        "ProtoMessage",
    )

    def field(
        message_descriptor: Any,
        field_name: str,
        tag: int,
        kind: int,
        label: int,
        type_name: str = "",
    ) -> None:
        item = message_descriptor.field.add()
        item.name = field_name
        item.number = tag
        item.type = kind
        item.label = label
        if type_name:
            item.type_name = type_name

    for number, name in enumerate(names, start=1):
        message = schema.message_type.add()
        message.name = name
        if name == "ProtoMessage":
            field(message, "payloadType", 1, field_type.TYPE_UINT32,
                  field_type.LABEL_REQUIRED)
            field(message, "payload", 2, field_type.TYPE_BYTES,
                  field_type.LABEL_REQUIRED)
            continue
        if name == "ProtoOACtidTraderAccount":
            field(message, "ctidTraderAccountId", 1, field_type.TYPE_UINT64,
                  field_type.LABEL_REQUIRED)
            field(message, "traderLogin", 2, field_type.TYPE_UINT64,
                  field_type.LABEL_OPTIONAL)
            field(message, "isLive", 3, field_type.TYPE_BOOL,
                  field_type.LABEL_OPTIONAL)
            continue
        field(message, "payloadType", 1, field_type.TYPE_UINT32,
              field_type.LABEL_OPTIONAL)
        message.field[-1].default_value = str(1400 + number)
        if name == "ProtoOAApplicationAuthReq":
            field(message, "clientId", 2, field_type.TYPE_STRING,
                  field_type.LABEL_REQUIRED)
            field(message, "clientSecret", 3, field_type.TYPE_STRING,
                  field_type.LABEL_REQUIRED)
        elif name == "ProtoOAGetAccountListByAccessTokenReq":
            field(message, "accessToken", 2, field_type.TYPE_STRING,
                  field_type.LABEL_REQUIRED)
        elif name in (
            "ProtoOAAccountAuthReq", "ProtoOASymbolsListReq", "ProtoOANewOrderReq"
        ):
            field(message, "ctidTraderAccountId", 2, field_type.TYPE_UINT64,
                  field_type.LABEL_OPTIONAL)
        elif name == "ProtoOAGetAccountListByAccessTokenRes":
            field(message, "ctidTraderAccount", 2, field_type.TYPE_MESSAGE,
                  field_type.LABEL_REPEATED,
                  ".t11641.ProtoOACtidTraderAccount")

    pool = descriptor_pool.DescriptorPool()
    pool.Add(schema)
    classes = {
        name: message_factory.GetMessageClass(
            pool.FindMessageTypeByName(f"t11641.{name}")
        )
        for name in names
    }
    return SimpleNamespace(**classes), SimpleNamespace(**classes)


def make_envelope(messages: object, message: Any) -> Any:
    envelope = getattr(messages, "ProtoMessage")()
    envelope.payloadType = message.payloadType
    envelope.payload = message.SerializeToString()
    return envelope


def account_list(
    messages: object,
    *,
    api_id: int = EXPECTED_API_ACCOUNT_ID,
    login: int = EXPECTED_GUI_TRADER_LOGIN,
    live: bool = False,
    missing: str = "",
) -> Any:
    response = getattr(messages, RESPONSE_NAMES[1])()
    item = response.ctidTraderAccount.add()
    item.ctidTraderAccountId = api_id
    if missing != "traderLogin":
        item.traderLogin = login
    if missing != "isLive":
        item.isLive = live
    return response


def test_t116_41_demo_account_list_session_preflight() -> None:
    """Перевірити callback-порядок, scoped token і fail-closed."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = [
        item.module or "" for item in ast.walk(tree)
        if isinstance(item, ast.ImportFrom)
    ]
    modules += [
        alias.name for item in ast.walk(tree) if isinstance(item, ast.Import)
        for alias in item.names
    ]
    for module in modules:
        assert not module.startswith((
            "core", "runtime", "ctrader_open_api", "subprocess", "socket"
        ))

    denied = 0
    messages, common = synthetic_sdk()
    assert existing_outbound_policy_locked()
    from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
    before_policy = outbound.PERMITTED_REQUEST_NAMES

    def scenario() -> tuple[
        OfflineAccountListSession, FakeTcpProtocol, Clock, list[str]
    ]:
        fake_protocol = FakeTcpProtocol()
        fake_protocol.envelope_class = getattr(common, "ProtoMessage")
        fake_client = FakeClient(fake_protocol)
        fake_clock = Clock()
        closed_events: list[str] = []
        child_session = OfflineAccountListSession(
            sdk_messages=messages,
            envelope_type=getattr(common, "ProtoMessage"),
            response_payload_types=RESPONSE_IDS,
            sender=fake_client.send,
            disconnect=lambda: closed_events.append("CLOSED"),
            clock=fake_clock,
        )
        return child_session, fake_protocol, fake_clock, closed_events

    def connect(active_session: OfflineAccountListSession) -> None:
        active_session.on_connected(
            client_id="TEST_ONLY_CLIENT",
            client_secret="TEST_ONLY_SECRET",
            access_token=SYNTHETIC_TOKEN,
        )

    auth_response = getattr(messages, RESPONSE_NAMES[0])()
    auth_envelope = make_envelope(messages, auth_response)
    good_list = make_envelope(messages, account_list(messages))

    with external_tcp_denied(), guarded_scoped_account_list(
        client_type=FakeClient,
        tcp_protocol_type=FakeTcpProtocol,
        frame_sender_type=FakeFrameSender,
        request_messages=messages,
        common_messages=common,
        expected_token=SYNTHETIC_TOKEN,
    ):
        session, protocol, clock, closes = scenario()
        connect(session)
        assert session.phase == "APP_SENT"
        assert session.on_envelope(auth_envelope) is None
        assert session.phase == "LIST_SENT"
        identity = session.on_envelope(good_list)
        assert identity is not None and identity.matched
        assert identity.reason == "IDENTITY_PAIR_MATCHES_DEMO"
        assert session.phase == "CLOSED"
        assert closes == ["CLOSED"]
        assert len(protocol.transport.writes) == 2
        for wire, expected in zip(
            protocol.transport.writes,
            ("ProtoOAApplicationAuthReq", "ProtoOAGetAccountListByAccessTokenReq"),
            strict=True,
        ):
            assert len(wire) - 4 == int.from_bytes(wire[:4], "big")
            envelope = getattr(common, "ProtoMessage")()
            envelope.ParseFromString(wire[4:])
            message_type = getattr(messages, expected)
            assert envelope.payloadType == message_type().payloadType
            decoded = message_type()
            decoded.ParseFromString(envelope.payload)
            assert decoded.IsInitialized()
            if expected == "ProtoOAGetAccountListByAccessTokenReq":
                assert getattr(decoded, "accessToken", None) == SYNTHETIC_TOKEN

        with pytest.raises(PermissionError):
            session.on_envelope(good_list)
        denied += 1
        assert closes == ["CLOSED"]

        session, protocol, _, closes = scenario()
        with pytest.raises(PermissionError):
            session.on_envelope(auth_envelope)
        denied += 1
        assert not protocol.transport.writes
        assert not closes

        for error_envelope in (
            good_list,
            make_envelope(messages, getattr(messages, "ProtoHeartbeatEvent")()),
            b"not-an-envelope",
            make_envelope(messages, getattr(messages, "ProtoOANewOrderReq")()),
        ):
            session, protocol, _, closes = scenario()
            connect(session)
            with pytest.raises(PermissionError):
                session.on_envelope(error_envelope)
            assert closes == ["CLOSED"]
            assert len(protocol.transport.writes) == 1
            denied += 1

        malformed = getattr(common, "ProtoMessage")()
        malformed.payloadType = RESPONSE_IDS[RESPONSE_NAMES[0]]
        malformed.payload = b"\x80"
        session, _, _, closes = scenario()
        connect(session)
        with pytest.raises(PermissionError):
            session.on_envelope(malformed)
        assert closes == ["CLOSED"]
        denied += 1

        for bad in (
            make_envelope(messages, account_list(messages, live=True)),
            make_envelope(messages, account_list(messages, login=1234)),
            make_envelope(messages, account_list(messages, api_id=1234)),
            make_envelope(messages, account_list(messages, missing="isLive")),
            make_envelope(messages, account_list(messages, missing="traderLogin")),
            make_envelope(messages, getattr(messages, RESPONSE_NAMES[1])()),
        ):
            session, protocol, _, closes = scenario()
            connect(session)
            session.on_envelope(auth_envelope)
            with pytest.raises(PermissionError):
                session.on_envelope(bad)
            assert len(protocol.transport.writes) == 2
            assert closes == ["CLOSED"]
            assert session.identity is None
            denied += 1

        session, _, clock, closes = scenario()
        connect(session)
        clock.seconds += SESSION_TIMEOUT_SECONDS
        with pytest.raises(TimeoutError):
            session.check_deadline()
        assert closes == ["CLOSED"]
        denied += 1

        session, _, _, closes = scenario()
        connect(session)
        with pytest.raises(ConnectionError):
            session.on_disconnected()
        assert closes == ["CLOSED"]
        denied += 1

        session, _, _, closes = scenario()
        connect(session)
        with pytest.raises(RuntimeError):
            session.on_sdk_error()
        assert closes == ["CLOSED"]
        denied += 1

        for credentials in (
            {"client_id": "", "client_secret": "a", "access_token": "b"},
            {"client_id": "a", "client_secret": "", "access_token": "b"},
            {"client_id": "a", "client_secret": "b", "access_token": ""},
            {"client_id": "a", "client_secret": "b", "access_token": " b"},
        ):
            session, protocol, _, closes = scenario()
            with pytest.raises(PermissionError):
                session.on_connected(**credentials)
            assert not protocol.transport.writes
            assert closes == ["CLOSED"]
            denied += 1

        session, _, _, closes = scenario()
        connect(session)
        with pytest.raises(PermissionError):
            connect(session)
        assert closes == []
        session.close()
        denied += 1

        for mode, identifier in (
            ("LIVE", EXPECTED_API_ACCOUNT_ID),
            ("DEMO", EXPECTED_API_ACCOUNT_ID + 1),
        ):
            with pytest.raises(PermissionError):
                OfflineAccountListSession(
                    sdk_messages=messages,
                    envelope_type=getattr(common, "ProtoMessage"),
                    response_payload_types=RESPONSE_IDS,
                    sender=lambda _message: None,
                    disconnect=lambda: None,
                    clock=Clock(),
                    account_mode=mode,
                    account_id=identifier,
                )
            denied += 1

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_probe:
            with pytest.raises(PermissionError):
                tcp_probe.connect(("192.0.2.18", 443))
        denied += 1

        session, protocol, _, closes = scenario()
        connect(session)
        protocol.queue.clear()
        with pytest.raises(PermissionError):
            client = FakeClient(protocol)
            trade = getattr(messages, "ProtoOANewOrderReq")()
            trade.ctidTraderAccountId = EXPECTED_API_ACCOUNT_ID
            client.send(trade)
        assert len(protocol.transport.writes) == 1
        assert closes == []
        session.close()
        denied += 1

    assert existing_outbound_policy_locked()
    assert outbound.PERMITTED_REQUEST_NAMES is before_policy

    print("T116-41 TEST_ONLY | DEMO AccountList callback session OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("request_order=APPLICATION_AUTH_ACCOUNT_LIST")
    print("identity_validator=T116-39_ACCOUNT_ID_LOGIN_IS_LIVE")
    print("account_list_guard=T116-40_EXACT_TOKEN_SCOPED")
    print("existing_t116_29_policy=UNCHANGED_AFTER_SCOPE")
    print("session_timeout_seconds=60")
    print("real_identity_pair=NOT_QUERIED_NO_NETWORK")
    print("credentials=SYNTHETIC_ONLY")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-41=GREEN_OFFLINE_ACCOUNT_LIST_SESSION_INTEGRATION")
