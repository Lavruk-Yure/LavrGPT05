"""T116-30 TEST_ONLY — підготовка запиту EURUSD symbols без мережі.

Самостійний запуск не створює cTrader Client, не читає LGE.conf і не
виконує LIVE. Дозволено лише --offline-preflight з тестовими credentials.
"""

from __future__ import annotations

import argparse
import socket
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import ip_address
from time import monotonic
from types import ModuleType
from typing import Any
from unittest.mock import patch

from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    load_real_sdk_types,
    sdk_client_spec,
    sdk_message_type,
)
from tests.roadmap116.t116_24_demo_symbol_discovery import DemoSymbolDiscovery
from tests.roadmap116.t116_25_demo_network_safety import OfflineDemoSafetySession

REQUEST_ORDER = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
)


@dataclass(frozen=True, slots=True)
class OfflineDiscoveryPlan:
    """Безпечний опис підготовленої послідовності, не мережевий Client."""

    demo_host: str
    demo_port: int
    account_id: int
    request_names: tuple[str, ...]
    disconnected: bool
    eurusd_symbol_id: None = None
    network_allowed: bool = False


class MemoryOnlyTransport:
    """Транспорт у пам'яті, який ніколи не викликає мережеві API."""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.disconnect_calls = 0

    def send(self, message: Message) -> None:
        if not isinstance(message, Message) or not message.IsInitialized():
            raise PermissionError("T116-30: неповний protobuf")
        self.messages.append(message)

    def disconnect(self) -> None:
        self.disconnect_calls += 1


def prepare_offline_discovery(
    *,
    endpoints: object,
    protocol_type: type,
    sdk_messages: ModuleType,
    account_mode: str = "DEMO",
    account_id: int = DEMO_API_ACCOUNT_ID,
) -> OfflineDiscoveryPlan:
    """Поєднати T116-24/25 на реальних або синтетичних protobuf-класах."""
    spec = sdk_client_spec(endpoints, protocol_type)
    memory_transport = MemoryOnlyTransport()
    with OfflineDemoSafetySession(
        endpoints=endpoints,
        protocol=protocol_type,
        requested_host=spec.demo_host,
        requested_port=spec.port,
        account_mode=account_mode,
        account_id=account_id,
        messages=sdk_messages,
        transport=memory_transport,
        monotonic_clock=monotonic,
    ) as session:
        discovery = DemoSymbolDiscovery(
            account_mode=account_mode,
            account_id=account_id,
            messages=sdk_messages,
            sender=session,
        )
        discovery.send_application_auth(
            client_id="TEST_ONLY_DUMMY_CLIENT",
            client_secret="TEST_ONLY_DUMMY_SECRET",
        )
        app_response = sdk_message_type(
            sdk_messages, "ProtoOAApplicationAuthRes"
        )()
        discovery.accept_application_auth(app_response)
        discovery.send_account_auth(access_token="TEST_ONLY_DUMMY_TOKEN")
        account_response = sdk_message_type(
            sdk_messages, "ProtoOAAccountAuthRes"
        )()
        setattr(account_response, "ctidTraderAccountId", DEMO_API_ACCOUNT_ID)
        discovery.accept_account_auth(account_response)
        discovery.send_symbols_list()
        assert discovery.phase == "SYMBOLS_REQUESTED"
        assert discovery.symbol_id is None

    sent_names = tuple(item.DESCRIPTOR.name for item in memory_transport.messages)
    if sent_names != REQUEST_ORDER or memory_transport.disconnect_calls != 1:
        raise AssertionError("T116-30: порушений порядок або очищення")
    return OfflineDiscoveryPlan(
        demo_host=spec.demo_host,
        demo_port=spec.port,
        account_id=DEMO_API_ACCOUNT_ID,
        request_names=sent_names,
        disconnected=True,
    )


def _local_loopback(address: object) -> bool:
    """Дозволити лише числовий loopback для службового waker Twisted."""
    if not isinstance(address, tuple) or len(address) < 2:
        return False
    host = address[0]
    if not isinstance(host, str):
        return False
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


@contextmanager
def external_tcp_denied() -> Iterator[None]:
    """Заборонити зовнішні TCP-з'єднання навіть під час імпорту SDK."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def checked_connect(sock: socket.socket, address: Any) -> None:
        if not _local_loopback(address):
            raise PermissionError("T116-30: зовнішня мережа заборонена")
        original_connect(sock, address)

    def checked_connect_ex(sock: socket.socket, address: Any) -> int:
        if not _local_loopback(address):
            raise PermissionError("T116-30: зовнішня мережа заборонена")
        return original_connect_ex(sock, address)

    def denied_create_connection(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("T116-30: зовнішня мережа заборонена")

    with (
        patch.object(socket.socket, "connect", checked_connect),
        patch.object(socket.socket, "connect_ex", checked_connect_ex),
        patch.object(socket, "create_connection", denied_create_connection),
    ):
        yield


def main(argv: Sequence[str] | None = None) -> int:
    """Єдина дозволена команда — офлайн-перевірка SDK без Client()."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--offline-preflight", action="store_true")
    args = parser.parse_args(argv)
    if not args.offline_preflight:
        parser.error("T116-30: доступний лише --offline-preflight")

    with external_tcp_denied():
        endpoints, _client_type, protocol_type, messages, _common = (
            load_real_sdk_types()
        )
        plan = prepare_offline_discovery(
            endpoints=endpoints,
            protocol_type=protocol_type,
            sdk_messages=messages,
        )
    print("T116-30 TEST_ONLY | standalone DEMO symbol discovery offline")
    print(f"demo_api_account_id={plan.account_id}")
    print("request_order=" + ",".join(plan.request_names))
    print("client_constructor=NOT_CALLED")
    print("real_eurusd_symbol_id=NOT_QUERIED_NO_NETWORK")
    print("external_tcp=BLOCKED")
    print("live_launch_authorized=NO")
    print("T116-30=GREEN_OFFLINE_DISCOVERY_NETWORK_PREPARATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
