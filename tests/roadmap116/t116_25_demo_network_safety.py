"""T116-25 TEST_ONLY — офлайн-межа безпеки запиту символів cTrader DEMO.

Тільки підставний транспорт. Модуль не створює SDK Client і не відкриває TCP.
Це перевірка політики, а не реалізація мережевого запуску.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Protocol

from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    sdk_client_spec,
    sdk_message_type,
)

DISCOVERY_REQUEST_ORDER = (
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
)
DISCOVERY_TIMEOUT_SECONDS = 60.0


class OfflineTransport(Protocol):
    """Ін'єктований транспорт без TCP; лише контракт його методів."""

    def send(self, message: Message) -> None: ...

    def disconnect(self) -> None: ...


class OfflineDemoSafetySession:
    """Перевіряти DEMO endpoint та кожен вихідний protobuf до sender."""

    def __init__(
        self,
        *,
        endpoints: object,
        protocol: type,
        requested_host: str,
        requested_port: int,
        account_mode: str,
        account_id: int,
        messages: ModuleType,
        transport: OfflineTransport,
        monotonic_clock: Callable[[], float],
    ) -> None:
        spec = sdk_client_spec(endpoints, protocol)
        if account_mode != "DEMO" or account_id != DEMO_API_ACCOUNT_ID:
            raise PermissionError("T116-25: дозволено лише DEMO API ID")
        if requested_host != spec.demo_host or requested_port != spec.port:
            raise PermissionError("T116-25: адреса відрізняється від DEMO SDK endpoint")
        self._account_id = account_id
        self._messages = messages
        self._transport = transport
        self._clock = monotonic_clock
        self._deadline = monotonic_clock() + DISCOVERY_TIMEOUT_SECONDS
        self._sent_count = 0
        self._active = False

    def __enter__(self) -> OfflineDemoSafetySession:
        if self._active:
            raise RuntimeError("T116-25: сесію вже активовано")
        self._active = True
        return self

    def __exit__(self, _exc_type: object, _exc_value: object,
                 _traceback: object) -> None:
        self._active = False
        self._transport.disconnect()

    def check_deadline(self) -> None:
        """Синхронна перевірка; не замінює supervisor без подій."""
        if self._clock() >= self._deadline:
            raise TimeoutError("T116-25: діагностичний час вичерпано")

    def send(self, message: Message) -> None:
        """Зупиняти торгові, сторонні та позачергові protobuf перед sender."""
        if not self._active:
            raise PermissionError("T116-25: транспорт поза тестовою сесією")
        self.check_deadline()
        if not isinstance(message, Message):
            raise PermissionError("T116-25: нетипізований пакет")
        name = message.DESCRIPTOR.name
        if self._sent_count >= len(DISCOVERY_REQUEST_ORDER):
            raise PermissionError("T116-25: додаткові запити заборонені")
        if name != DISCOVERY_REQUEST_ORDER[self._sent_count]:
            raise PermissionError("T116-25: неочікуваний або торговий protobuf")
        if type(message) is not sdk_message_type(self._messages, name):
            raise PermissionError("T116-25: неправильний protobuf-клас")
        if name == "ProtoOAApplicationAuthReq":
            if not all(
                str(getattr(message, field_name, "")).strip()
                for field_name in ("clientId", "clientSecret")
            ):
                raise PermissionError("T116-25: відсутні credentials")
        else:
            if int(getattr(message, "ctidTraderAccountId", 0)) != self._account_id:
                raise PermissionError("T116-25: чужий рахунок")
            if name == "ProtoOAAccountAuthReq":
                if not str(getattr(message, "accessToken", "")).strip():
                    raise PermissionError("T116-25: відсутній token")
            elif bool(getattr(message, "includeArchivedSymbols", True)):
                raise PermissionError("T116-25: архівні символи заборонено")
        if not message.IsInitialized():
            raise PermissionError("T116-25: неповний protobuf")
        self._transport.send(message)
        self._sent_count += 1

    @staticmethod
    def reject_raw(_payload: bytes) -> None:
        """Жодні вже серіалізовані пакети не приймати напряму."""
        raise PermissionError("T116-25: обхід protobuf-перевірки заборонено")
