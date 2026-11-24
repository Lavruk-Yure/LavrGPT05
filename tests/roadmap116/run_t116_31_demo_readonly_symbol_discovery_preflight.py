"""T116-31 TEST_ONLY — офлайн callback-driven DEMO Symbol Discovery."""

from __future__ import annotations

import ast
import socket
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from google.protobuf.message import Message

from tests.roadmap116.run_t116_24_demo_symbol_discovery_contract import (
    proto,
    symbols_response,
    synthetic_sdk_messages,
)
from tests.roadmap116.run_t116_25_demo_network_safety_preflight import (
    FakeClock,
    FakeEndpoints,
    FakeProtocol,
    FakeTransport,
)
from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import load_real_sdk_types
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_31_demo_readonly_discovery_session import (
    INBOUND_RESPONSE_NAMES,
    DemoReadOnlyDiscoverySession,
)

SOURCE = Path(__file__).with_name("t116_31_demo_readonly_discovery_session.py")
SYNTHETIC_EURUSD_SYMBOL_ID = 116031
FAKE_PAYLOAD_TYPES = {
    "ProtoOAApplicationAuthRes": 2101,
    "ProtoOAAccountAuthRes": 2102,
    "ProtoOASymbolsListRes": 2103,
}


@dataclass(slots=True)
class FakeEnvelope:
    """Синтетичний SDK-конверт без сокетів."""

    payloadType: int
    payload: bytes

    # Назва методу повторює API protobuf і має залишатися без змін.
    # noinspection PyPep8Naming
    def IsInitialized(self) -> bool:
        return self.payloadType > 0 and isinstance(self.payload, bytes)


def make_session(
    *,
    messages: ModuleType,
    envelope_type: type,
    payload_types: dict[str, int],
    endpoints: object,
    protocol_type: type,
    transport: FakeTransport,
    clock: FakeClock,
    account_mode: str = "DEMO",
    account_id: int = DEMO_API_ACCOUNT_ID,
) -> DemoReadOnlyDiscoverySession:
    return DemoReadOnlyDiscoverySession(
        endpoints=endpoints,
        protocol_type=protocol_type,
        messages=messages,
        envelope_type=envelope_type,
        response_payload_types=payload_types,
        transport=transport,
        monotonic_clock=clock,
        account_mode=account_mode,
        account_id=account_id,
    )


def envelope_for(
    message: Message,
    envelope_type: type,
    payload_types: dict[str, int],
) -> Any:
    if envelope_type is FakeEnvelope:
        return FakeEnvelope(
            payload_types[message.DESCRIPTOR.name],
            message.SerializeToString(),
        )
    envelope = envelope_type()
    setattr(envelope, "payloadType", payload_types[message.DESCRIPTOR.name])
    setattr(envelope, "payload", message.SerializeToString())
    return envelope


def response_sequence(
    messages: ModuleType,
    *,
    account_id: int = DEMO_API_ACCOUNT_ID,
) -> tuple[Message, Message, Message]:
    return (
        proto(messages, "ProtoOAApplicationAuthRes"),
        proto(messages, "ProtoOAAccountAuthRes", ctidTraderAccountId=account_id),
        symbols_response(
            messages,
            account_id=account_id,
            names=(("EURUSD", SYNTHETIC_EURUSD_SYMBOL_ID, True),),
        ),
    )


def exercise_success(
    *,
    messages: ModuleType,
    envelope_type: type,
    payload_types: dict[str, int],
    endpoints: object,
    protocol_type: type,
) -> None:
    transport = FakeTransport()
    clock = FakeClock()
    session = make_session(
        messages=messages,
        envelope_type=envelope_type,
        payload_types=payload_types,
        endpoints=endpoints,
        protocol_type=protocol_type,
        transport=transport,
        clock=clock,
    )
    with session:
        session.on_connected(
            client_id="TEST_ONLY_CLIENT",
            client_secret="TEST_ONLY_SECRET",
            access_token="TEST_ONLY_TOKEN",
        )
        for expected, response in zip(
            (None, None, SYNTHETIC_EURUSD_SYMBOL_ID),
            response_sequence(messages),
            strict=True,
        ):
            result = session.on_envelope(
                envelope_for(response, envelope_type, payload_types)
            )
            assert result == expected
    assert session.symbol_id == SYNTHETIC_EURUSD_SYMBOL_ID
    assert session.discovery.phase == "RESOLVED"
    assert [item.DESCRIPTOR.name for item in transport.sent] == [
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
    ]
    assert transport.disconnect_calls == 1
    with pytest.raises(PermissionError):
        session.on_envelope(
            envelope_for(response_sequence(messages)[-1], envelope_type, payload_types)
        )
    assert transport.disconnect_calls == 1


def exercise_fail_closed(messages: ModuleType) -> int:
    """Невпорядковані, некоректні, прострочені події не відправляють orders."""
    denied = 0
    examples = response_sequence(messages)

    def fresh() -> tuple[DemoReadOnlyDiscoverySession, FakeTransport, FakeClock]:
        fresh_transport = FakeTransport()
        fresh_clock = FakeClock()
        current = make_session(
            messages=messages,
            envelope_type=FakeEnvelope,
            payload_types=FAKE_PAYLOAD_TYPES,
            endpoints=FakeEndpoints(),
            protocol_type=FakeProtocol,
            transport=fresh_transport,
            clock=fresh_clock,
        )
        current.__enter__()
        current.on_connected(
            client_id="TEST_ONLY_CLIENT",
            client_secret="TEST_ONLY_SECRET",
            access_token="TEST_ONLY_TOKEN",
        )
        return current, fresh_transport, fresh_clock

    out_of_order = envelope_for(examples[1], FakeEnvelope, FAKE_PAYLOAD_TYPES)
    session, transport, _clock = fresh()
    with pytest.raises(RuntimeError):
        session.on_envelope(out_of_order)
    assert transport.disconnect_calls == 1
    assert [msg.DESCRIPTOR.name for msg in transport.sent] == [
        "ProtoOAApplicationAuthReq"
    ]
    denied += 1

    bad_messages: tuple[Any, ...] = (
        FakeEnvelope(999999, b"no"),
        FakeEnvelope(FAKE_PAYLOAD_TYPES[INBOUND_RESPONSE_NAMES[0]], b"\x80"),
        FakeEnvelope(FAKE_PAYLOAD_TYPES[INBOUND_RESPONSE_NAMES[1]], b""),
        b"raw-bytes",
    )
    for unexpected in bad_messages:
        session, transport, _clock = fresh()
        with pytest.raises(PermissionError):
            session.on_envelope(unexpected)
        assert transport.disconnect_calls == 1
        assert [msg.DESCRIPTOR.name for msg in transport.sent] == [
            "ProtoOAApplicationAuthReq"
        ]
        denied += 1

    session, transport, _clock = fresh()
    with pytest.raises(ConnectionError):
        session.on_disconnected()
    assert transport.disconnect_calls == 1
    denied += 1

    session, transport, clock = fresh()
    clock.seconds += 61.0
    with pytest.raises(TimeoutError):
        session.check_deadline()
    assert transport.disconnect_calls == 1
    denied += 1

    session, transport, _clock = fresh()
    session.on_envelope(envelope_for(examples[0], FakeEnvelope, FAKE_PAYLOAD_TYPES))
    with pytest.raises(PermissionError):
        session.on_envelope(
            envelope_for(
                proto(
                    messages,
                    "ProtoOAAccountAuthRes",
                    ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1,
                ),
                FakeEnvelope,
                FAKE_PAYLOAD_TYPES,
            )
        )
    assert transport.disconnect_calls == 1
    assert [msg.DESCRIPTOR.name for msg in transport.sent] == [
        "ProtoOAApplicationAuthReq",
        "ProtoOAAccountAuthReq",
    ]
    denied += 1

    session, transport, _clock = fresh()
    session.on_envelope(envelope_for(examples[0], FakeEnvelope, FAKE_PAYLOAD_TYPES))
    session.on_envelope(envelope_for(examples[1], FakeEnvelope, FAKE_PAYLOAD_TYPES))
    with pytest.raises(ValueError):
        session.on_envelope(
            envelope_for(
                symbols_response(messages, names=(("GBPUSD", 231, True),)),
                FakeEnvelope,
                FAKE_PAYLOAD_TYPES,
            )
        )
    assert transport.disconnect_calls == 1
    denied += 1

    for bad_mode, bad_id in (
        ("LIVE", DEMO_API_ACCOUNT_ID),
        ("DEMO", DEMO_API_ACCOUNT_ID + 1),
    ):
        with pytest.raises(PermissionError):
            make_session(
                messages=messages,
                envelope_type=FakeEnvelope,
                payload_types=FAKE_PAYLOAD_TYPES,
                endpoints=FakeEndpoints(),
                protocol_type=FakeProtocol,
                transport=FakeTransport(),
                clock=FakeClock(),
                account_mode=bad_mode,
                account_id=bad_id,
            )
        denied += 1
    return denied


def test_t116_31_demo_readonly_symbol_discovery_preflight() -> None:
    """Перевірити сесію на synthetic + реальних SDK protobuf без мережі."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    imported.extend(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden = (
        "core",
        "engine",
        "ibapi",
        "PySide6",
        "subprocess",
        "socket",
        "ctrader_open_api",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imported
        for prefix in forbidden
    )

    with external_tcp_denied():
        messages = synthetic_sdk_messages()
        exercise_success(
            messages=messages,
            envelope_type=FakeEnvelope,
            payload_types=FAKE_PAYLOAD_TYPES,
            endpoints=FakeEndpoints(),
            protocol_type=FakeProtocol,
        )
        denied = exercise_fail_closed(messages)
        status = "NOT_INSTALLED_LOCAL_RUNNER"
        if find_spec("ctrader_open_api") is not None:
            endpoints, _client_type, protocol_type, real_messages, common = (
                load_real_sdk_types()
            )
            real_types = {
                name: int(getattr(getattr(real_messages, name)(), "payloadType"))
                for name in INBOUND_RESPONSE_NAMES
            }
            exercise_success(
                messages=real_messages,
                envelope_type=getattr(common, "ProtoMessage"),
                payload_types=real_types,
                endpoints=endpoints,
                protocol_type=protocol_type,
            )
            status = "VERIFIED_NO_EXTERNAL_NETWORK"

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            with pytest.raises(PermissionError):
                probe.connect(("192.0.2.10", 443))

    print("T116-31 TEST_ONLY | callback-driven read-only DEMO Symbol Discovery")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print("authorization_order=APPLICATION_ACCOUNT_SYMBOLS")
    print("sdk_callback_lifecycle=VERIFIED_OFFLINE")
    print("synthetic_eurusd_symbol_id=VERIFIED_NOT_REAL")
    print(f"negative_scenarios_denied={denied}")
    print(f"actual_ctrader_sdk={status}")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-31=GREEN_OFFLINE_CALLBACK_DISCOVERY_PREFLIGHT")
