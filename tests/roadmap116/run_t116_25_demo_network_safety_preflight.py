"""T116-25 TEST_ONLY — мережевий preflight на підставному транспорті."""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

import pytest
from google.protobuf.message import Message

from tests.roadmap116.run_t116_24_demo_symbol_discovery_contract import (
    proto,
    symbols_response,
    synthetic_sdk_messages,
)
from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_24_demo_symbol_discovery import DemoSymbolDiscovery
from tests.roadmap116.t116_25_demo_network_safety import (
    DISCOVERY_TIMEOUT_SECONDS,
    OfflineDemoSafetySession,
)

SOURCE = Path(__file__).with_name("t116_25_demo_network_safety.py")
SYNTHETIC_ID = 987654


class FakeEndpoints:
    """Тестові адреси, які не використовуються для TCP."""

    PROTOBUF_DEMO_HOST = "demo.test.invalid"
    PROTOBUF_LIVE_HOST = "live.test.invalid"
    PROTOBUF_PORT = 5035


class FakeProtocol:
    """Маркер SDK-протоколу без мережі."""


class FakeClock:
    """Керований монотонний час."""

    def __init__(self) -> None:
        self.seconds = 100.0

    def __call__(self) -> float:
        return self.seconds


class FakeTransport:
    """Фіксувати повідомлення тільки в пам'яті."""

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.disconnect_calls = 0
        self.fail_send = False
        self.fail_disconnect = False

    def send(self, message: Message) -> None:
        if self.fail_send:
            raise RuntimeError("T116-25: тестова помилка відправлення")
        self.sent.append(message)

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        if self.fail_disconnect:
            raise RuntimeError("T116-25: тестова помилка відключення")


def session(
    messages: ModuleType,
    transport: FakeTransport,
    clock: FakeClock,
    *,
    requested_host: str = "demo.test.invalid",
    account_mode: str = "DEMO",
    account_id: int = DEMO_API_ACCOUNT_ID,
) -> OfflineDemoSafetySession:
    """Створити контрактну сесію без SDK Client і TCP."""
    return OfflineDemoSafetySession(
        endpoints=FakeEndpoints(), protocol=FakeProtocol,
        requested_host=requested_host, requested_port=5035,
        account_mode=account_mode, account_id=account_id,
        messages=messages, transport=transport, monotonic_clock=clock,
    )


def test_t116_25_demo_network_safety_preflight() -> None:
    """Окремо перевірити endpoint, wire allowlist, timeout та cleanup."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = [
        item.module or ""
        for item in ast.walk(tree) if isinstance(item, ast.ImportFrom)
    ]
    imported.extend(
        alias.name
        for item in ast.walk(tree) if isinstance(item, ast.Import)
        for alias in item.names
    )
    forbidden = ("LGE", "core", "engine", "ibapi", "PySide6", "socket",
                 "ctrader_open_api", "subprocess")
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imported for prefix in forbidden
    )

    messages = synthetic_sdk_messages()
    transport = FakeTransport()
    clock = FakeClock()
    for wrong_mode, wrong_id, wrong_host in (
        ("LIVE", DEMO_API_ACCOUNT_ID, "demo.test.invalid"),
        ("DEMO", DEMO_API_ACCOUNT_ID + 1, "demo.test.invalid"),
        ("DEMO", DEMO_API_ACCOUNT_ID, "live.test.invalid"),
        ("DEMO", DEMO_API_ACCOUNT_ID, "unexpected.test.invalid"),
    ):
        with pytest.raises(PermissionError):
            session(messages, transport, clock, account_mode=wrong_mode,
                    account_id=wrong_id, requested_host=wrong_host)
    assert not transport.sent and transport.disconnect_calls == 0

    offline = session(messages, transport, clock)
    discovery = DemoSymbolDiscovery(
        account_mode="DEMO", account_id=DEMO_API_ACCOUNT_ID,
        messages=messages, sender=offline,
    )
    with pytest.raises(PermissionError):
        offline.send(proto(messages, "ProtoOAApplicationAuthReq",
                           clientId="X", clientSecret="Y"))
    with offline:
        with pytest.raises(PermissionError):
            offline.send(proto(messages, "ProtoOANewOrderReq",
                               ctidTraderAccountId=DEMO_API_ACCOUNT_ID))
        with pytest.raises(PermissionError):
            offline.send(proto(messages, "ProtoOAApplicationAuthRes"))
        with pytest.raises(PermissionError):
            offline.send(proto(messages, "ProtoOASymbolsListReq",
                               ctidTraderAccountId=DEMO_API_ACCOUNT_ID))
        with pytest.raises(PermissionError):
            offline.reject_raw(b"TEST_ONLY_TRADE_PACKET")
        assert transport.sent == []
        discovery.send_application_auth(
            client_id="TEST_ONLY_CLIENT_ID", client_secret="TEST_ONLY_SECRET"
        )
        discovery.accept_application_auth(proto(messages, "ProtoOAApplicationAuthRes"))
        discovery.send_account_auth(access_token="TEST_ONLY_TOKEN")
        discovery.accept_account_auth(proto(
            messages, "ProtoOAAccountAuthRes",
            ctidTraderAccountId=DEMO_API_ACCOUNT_ID,
        ))
        with pytest.raises(PermissionError):
            offline.send(proto(messages, "ProtoOASymbolsListReq",
                               ctidTraderAccountId=DEMO_API_ACCOUNT_ID + 1))
        discovery.send_symbols_list()
        assert discovery.accept_symbols_list(symbols_response(messages)) == SYNTHETIC_ID
        with pytest.raises(PermissionError):
            offline.send(proto(messages, "ProtoOASymbolsListReq",
                               ctidTraderAccountId=DEMO_API_ACCOUNT_ID))
    assert transport.disconnect_calls == 1
    assert [item.DESCRIPTOR.name for item in transport.sent] == [
        "ProtoOAApplicationAuthReq", "ProtoOAAccountAuthReq",
        "ProtoOASymbolsListReq",
    ]

    no_events = FakeTransport()
    time_clock = FakeClock()
    with session(messages, no_events, time_clock) as timed:
        time_clock.seconds += DISCOVERY_TIMEOUT_SECONDS
        with pytest.raises(TimeoutError):
            timed.send(proto(messages, "ProtoOAApplicationAuthReq",
                             clientId="X", clientSecret="Y"))
    assert no_events.disconnect_calls == 1 and not no_events.sent

    failed = FakeTransport()
    failed.fail_send = True
    with pytest.raises(RuntimeError, match="помилка відправлення"):
        with session(messages, failed, FakeClock()) as attempt:
            attempt.send(proto(messages, "ProtoOAApplicationAuthReq",
                               clientId="X", clientSecret="Y"))
    assert failed.disconnect_calls == 1

    exited = FakeTransport()
    with pytest.raises(SystemExit):
        with session(messages, exited, FakeClock()):
            raise SystemExit(7)
    assert exited.disconnect_calls == 1

    print("T116-25 TEST_ONLY | standalone DEMO network safety preflight")
    print("demo_endpoint_only=VERIFIED_FAKE_ENDPOINTS")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print("outbound_auth_account_symbols_only=3/3")
    print("trading_unknown_wrong_account_raw=BLOCKED")
    print("authorization_order=APPLICATION_ACCOUNT_SYMBOLS")
    print("real_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print(f"deadline_check_seconds={int(DISCOVERY_TIMEOUT_SECONDS)}")
    print("idle_event_loop_watchdog=NOT_IMPLEMENTED")
    print("normal_error_system_exit_disconnect_attempts=VERIFIED_FAKE_TRANSPORT")
    print("actual_sdk_client_tcp_guard=NOT_WIRED")
    print("real_network_disconnect=NOT_VERIFIED")
    print("sdk_client_real_constructor=NOT_CALLED")
    print("real_broker_requests=0")
    print("real_config_disk_writes=0")
    print("production_changes=0")
    print("live_launch_authorized=NO")
    print("T116-25=GREEN_OFFLINE_DEMO_NETWORK_SAFETY_POLICY")
