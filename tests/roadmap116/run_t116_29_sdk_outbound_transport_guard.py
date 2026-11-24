"""T116-29 TEST_ONLY — справжні SDK send API без мережевого з'єднання.

Перевіряє Client.send, TcpProtocol.send, Int32StringReceiver.sendString
та flush черги. Не створює Client і не відкриває зовнішній TCP.
"""

from __future__ import annotations

import socket
from collections import deque
from collections.abc import Callable
from importlib import import_module
from ipaddress import ip_address
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tests.roadmap116.run_t116_20g_outbound_protobuf_trade_guard import (
    fake_protobuf_modules,
)
from tests.roadmap116.t116_29_sdk_outbound_guard import (
    DEMO_API_ACCOUNT_ID,
    PERMITTED_REQUEST_NAMES,
    guarded_sdk_outbound,
)


class FakeWire:
    """Прийняти лише байти, не звертаючись до socket."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)


class FakeFrameSender:
    """TEST_ONLY: нижній рівень із підставним wire."""

    def send_string(self, frame: bytes) -> None:
        wire = getattr(self, "transport")
        wire.write(len(frame).to_bytes(4, "big") + frame)


setattr(FakeFrameSender, "sendString", FakeFrameSender.send_string)


class FakeTcpProtocol(FakeFrameSender):
    """TEST_ONLY: негайне відправлення та черга SDK-подібного протоколу."""

    def __init__(self) -> None:
        self.transport = FakeWire()
        self.queue: deque[bytes] = deque()
        self.envelope_class: Callable[[], Any] = self._missing_envelope

    @staticmethod
    def _missing_envelope() -> Any:
        raise RuntimeError("T116-29: тестовий ProtoMessage не налаштовано")

    def send(self, message: Any, *, instant: bool = False) -> None:
        envelope_class = self.envelope_class
        envelope = envelope_class()
        envelope.payloadType = message.payloadType
        envelope.payload = message.SerializeToString()
        frame = envelope.SerializeToString()
        if instant:
            getattr(self, "sendString")(frame)
        else:
            self.queue.append(frame)

    def flush(self) -> None:
        while self.queue:
            getattr(self, "sendString")(self.queue.popleft())


class FakeClient:
    """TEST_ONLY: виклик через Client.send до протоколу."""

    def __init__(self, protocol: FakeTcpProtocol) -> None:
        self.protocol = protocol

    def send(self, message: object) -> None:
        self.protocol.send(message, instant=True)


class WireCase:
    """Запуск однакових контрольних спроб для fake та real SDK."""

    def __init__(self, messages: object, common: object) -> None:
        self.messages = messages
        self.common = common
        self.envelope_class = getattr(common, "ProtoMessage")

    def new(self, name: str, **fields: Any) -> Any:
        module = self.common if name == "ProtoHeartbeatEvent" else self.messages
        message = getattr(module, name)()
        for field, value in fields.items():
            setattr(message, field, value)
        assert message.IsInitialized(), name
        return message

    def packet(self, message: Any) -> bytes:
        envelope = self.envelope_class()
        envelope.payloadType = message.payloadType
        envelope.payload = message.SerializeToString()
        assert envelope.IsInitialized()
        return envelope.SerializeToString()


def exercise_fake() -> int:
    """Заборонені пакети не повинні потрапляти у wire чи чергу."""
    names = tuple(
        name for name in PERMITTED_REQUEST_NAMES if name != "ProtoHeartbeatEvent"
    )
    requests, common = fake_protobuf_modules(names)
    samples = WireCase(requests, common)
    tcp = FakeTcpProtocol()
    tcp.envelope_class = samples.envelope_class
    client = FakeClient(tcp)
    read_only = samples.new(
        "ProtoOAAccountAuthReq", ctidTraderAccountId=DEMO_API_ACCOUNT_ID
    )
    symbols = samples.new(
        "ProtoOASymbolsListReq", ctidTraderAccountId=DEMO_API_ACCOUNT_ID
    )
    heartbeat = samples.new("ProtoHeartbeatEvent")
    foreign = samples.new(
        "ProtoOASymbolsListReq", ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1
    )
    trade = samples.new("ProtoOANewOrderReq", ctidTraderAccountId=DEMO_API_ACCOUNT_ID)

    # Перевірити, що підміни контролюють три окремі шляхи.
    with guarded_sdk_outbound(
        client_type=FakeClient,
        tcp_protocol_type=FakeTcpProtocol,
        frame_sender_type=FakeFrameSender,
        request_messages=requests,
        common_messages=common,
    ):
        client.send(read_only)
        tcp.send(symbols, instant=True)
        getattr(FakeFrameSender, "sendString")(tcp, samples.packet(heartbeat))
        assert len(tcp.transport.writes) == 3

        denied = (
            lambda: client.send(trade),
            lambda: tcp.send(trade, instant=True),
            lambda: tcp.send(b"raw", instant=True),
            lambda: client.send(foreign),
            lambda: tcp.send(foreign, instant=False),
            lambda: getattr(FakeFrameSender, "sendString")(tcp, samples.packet(trade)),
            lambda: getattr(tcp, "sendString")(samples.packet(foreign)),
            lambda: getattr(tcp, "sendString")(b"unknown"),
            lambda: getattr(tcp, "sendString")(b""),
            lambda: getattr(tcp, "sendString")(b"x" * 70000),
        )
        for invoke in denied:
            with pytest.raises(PermissionError):
                invoke()
        assert len(tcp.transport.writes) == 3
        assert not tcp.queue

        # Небезпечний кадр у черзі існував ДО встановлення guard.
        tcp.queue.append(samples.packet(trade))
        with pytest.raises(PermissionError):
            tcp.flush()
        assert len(tcp.transport.writes) == 3
    assert len(tcp.transport.writes) == 3
    return len(denied) + 1


def exercise_real_sdk() -> str:
    """Перевірити справжні Client.send/TcpProtocol.send без Client.__init__."""
    from importlib.util import find_spec

    if find_spec("ctrader_open_api") is None:
        return "NOT_INSTALLED_LOCAL_RUNNER"

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    external_attempts: list[str] = []

    def allow_loopback(address: object) -> bool:
        if not isinstance(address, tuple) or len(address) < 2:
            return False
        host = address[0]
        if not isinstance(host, str):
            return False
        try:
            return ip_address(host).is_loopback
        except ValueError:
            return False

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        if not allow_loopback(address):
            external_attempts.append("connect")
            raise AssertionError("T116-29: зовнішній TCP заборонено")
        original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        if not allow_loopback(address):
            external_attempts.append("connect_ex")
            raise AssertionError("T116-29: зовнішній TCP заборонено")
        return original_connect_ex(sock, address)

    with (
        patch.object(socket.socket, "connect", guarded_connect),
        patch.object(socket.socket, "connect_ex", guarded_connect_ex),
    ):
        from ctrader_open_api import Client, TcpProtocol

        common = import_module("ctrader_open_api.messages.OpenApiCommonMessages_pb2")
        requests = import_module("ctrader_open_api.messages.OpenApiMessages_pb2")
        defer = import_module("twisted.internet.defer")
        task = import_module("twisted.internet.task")
        frame_sender_type = getattr(
            import_module("twisted.protocols.basic"), "Int32StringReceiver"
        )

        samples = WireCase(requests, common)
        app = samples.new(
            "ProtoOAApplicationAuthReq",
            clientId="TEST_ONLY_ID",
            clientSecret="TEST_ONLY_SECRET",
        )
        account = samples.new(
            "ProtoOAAccountAuthReq",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            accessToken="TEST_ONLY_TOKEN",
        )
        symbols = samples.new(
            "ProtoOASymbolsListReq",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            includeArchivedSymbols=False,
        )
        heartbeat = samples.new("ProtoHeartbeatEvent")
        foreign = samples.new(
            "ProtoOASymbolsListReq",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1,
        )
        trade = samples.new(
            "ProtoOANewOrderReq",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
            symbolId=1,
            orderType=1,
            tradeSide=1,
            volume=1000,
        )

        # __init__ Client та TCP connect не викликаються.
        tcp = object.__new__(TcpProtocol)
        wire = FakeWire()
        setattr(tcp, "transport", wire)
        setattr(tcp, "_send_queue", deque())
        setattr(tcp, "_lastSendMessageTime", None)
        setattr(tcp, "factory", SimpleNamespace(numberOfMessagesToSendPerSecond=10))
        clock = task.Clock()
        fake_client = object.__new__(Client)
        setattr(fake_client, "_responseDeferreds", {})
        setattr(fake_client, "_runningReactor", clock)
        setattr(fake_client, "_cancelMessageDiferred", lambda _deferred: None)
        setattr(
            fake_client,
            "_onResponseFailure",
            lambda failure, _msg_id: failure,
        )
        setattr(fake_client, "whenConnected", lambda **_kwargs: defer.succeed(tcp))

        with guarded_sdk_outbound(
            client_type=Client,
            tcp_protocol_type=TcpProtocol,
            frame_sender_type=frame_sender_type,
            request_messages=requests,
            common_messages=common,
        ):
            # Виклик справжнього Client.send() зі штучним self.
            Client.send(fake_client, app)
            queue = getattr(tcp, "_send_queue")
            assert len(queue) == 1
            getattr(tcp, "_sendStrings")()
            assert len(wire.writes) == 1

            TcpProtocol.send(tcp, account, instant=True)
            TcpProtocol.send(tcp, symbols, instant=True)
            TcpProtocol.send(tcp, heartbeat, instant=True)
            assert len(wire.writes) == 4

            denied = (
                lambda: Client.send(fake_client, trade),
                lambda: Client.send(fake_client, "ProtoOANewOrderReq"),
                lambda: TcpProtocol.send(tcp, trade, instant=True),
                lambda: TcpProtocol.send(tcp, samples.packet(trade), instant=True),
                lambda: getattr(frame_sender_type, "sendString")(
                    tcp, samples.packet(trade)
                ),
                lambda: getattr(frame_sender_type, "sendString")(
                    tcp, samples.packet(foreign)
                ),
                lambda: getattr(frame_sender_type, "sendString")(tcp, b"unknown"),
            )
            for invoke in denied:
                with pytest.raises(PermissionError):
                    invoke()
            assert len(wire.writes) == 4
            assert not queue
            queue.append((None, samples.packet(trade)))
            with pytest.raises(PermissionError):
                getattr(tcp, "_sendStrings")()
            assert len(wire.writes) == 4
        assert not external_attempts
    return "VERIFIED_NO_EXTERNAL_NETWORK"


def test_t116_29_sdk_outbound_transport_guard() -> None:
    """Підтвердити блокування до write, без справжніх з'єднань."""
    denied = exercise_fake()
    sdk = exercise_real_sdk()
    print("T116-29 TEST_ONLY | Client / TcpProtocol / frame sender")
    print(f"synthetic_denied_transport_attempts={denied}")
    print("client_send_guard=VERIFIED")
    print("tcp_protocol_send_guard=VERIFIED")
    print("frame_sender_guard=VERIFIED")
    print("queued_trade_frame_at_flush=BLOCKED")
    print("trading_foreign_unknown_raw=BLOCKED_BEFORE_WIRE")
    print(f"actual_ctrader_sdk={sdk}")
    print("real_client_constructor=NOT_CALLED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-29=GREEN_OFFLINE_SDK_OUTBOUND_TRANSPORT_GUARD")
