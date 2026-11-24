"""T116-31 TEST_ONLY — callback-driven DEMO Symbol Discovery без мережі.

Приймає тільки три очікувані SDK-відповіді. Не створює Client,
не підключається до TCP, не читає credentials або конфігурацію LGE.
Мережевий запуск у цьому модулі навмисно відсутній.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

from google.protobuf.message import DecodeError, Message

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    sdk_client_spec,
    sdk_message_type,
)
from tests.roadmap116.t116_24_demo_symbol_discovery import DemoSymbolDiscovery
from tests.roadmap116.t116_25_demo_network_safety import (
    OfflineDemoSafetySession,
    OfflineTransport,
)

INBOUND_RESPONSE_NAMES = (
    "ProtoOAApplicationAuthRes",
    "ProtoOAAccountAuthRes",
    "ProtoOASymbolsListRes",
)
MAX_INBOUND_PAYLOAD_BYTES = 4 * 1024 * 1024


class DemoReadOnlyDiscoverySession:
    """Керувати відповідями авторизації та завершувати сесію після EURUSD.

    Транспорт ін'єктований. Підключення, SDK Client і reactor не створюються.
    Зовнішній watchdog має викликати check_deadline(), коли немає подій.
    """

    def __init__(
        self,
        *,
        endpoints: object,
        protocol_type: type,
        messages: ModuleType,
        envelope_type: type,
        response_payload_types: Mapping[str, int],
        transport: OfflineTransport,
        monotonic_clock: Callable[[], float],
        account_mode: str = "DEMO",
        account_id: int = DEMO_API_ACCOUNT_ID,
    ) -> None:
        spec = sdk_client_spec(endpoints, protocol_type)
        if not isinstance(envelope_type, type):
            raise TypeError("T116-31: невизначений тип SDK-конверта")
        if set(response_payload_types) != set(INBOUND_RESPONSE_NAMES):
            raise ValueError("T116-31: неповний білий список відповідей")
        if any(
            type(payload_id) is not int or payload_id <= 0
            for payload_id in response_payload_types.values()
        ):
            raise ValueError("T116-31: некоректний payloadType")
        if len(set(response_payload_types.values())) != len(INBOUND_RESPONSE_NAMES):
            raise ValueError("T116-31: неоднозначні payloadType")

        self._response_types: dict[int, type[Message]] = {}
        for name in INBOUND_RESPONSE_NAMES:
            message_type = sdk_message_type(messages, name)
            sdk_payload_id = getattr(message_type(), "payloadType", None)
            if (
                sdk_payload_id is not None
                and sdk_payload_id != response_payload_types[name]
            ):
                raise PermissionError("T116-31: payloadType не відповідає SDK")
            self._response_types[response_payload_types[name]] = message_type

        self._envelope_type = envelope_type
        self._sender = OfflineDemoSafetySession(
            endpoints=endpoints,
            protocol=protocol_type,
            requested_host=spec.demo_host,
            requested_port=spec.port,
            account_mode=account_mode,
            account_id=account_id,
            messages=messages,
            transport=transport,
            monotonic_clock=monotonic_clock,
        )
        self.discovery = DemoSymbolDiscovery(
            account_mode=account_mode,
            account_id=account_id,
            messages=messages,
            sender=self._sender,
        )
        self.symbol_id: int | None = None
        self._access_token: str | None = None
        self._active = False
        self._closed = False

    def __enter__(self) -> DemoReadOnlyDiscoverySession:
        if self._active or self._closed:
            raise RuntimeError("T116-31: повторна активація заборонена")
        self._sender.__enter__()
        self._active = True
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Закрити транспорт рівно один раз; токен не зберігати після кінця."""
        if self._closed:
            return
        self._closed = True
        self._access_token = None
        if self._active:
            self._active = False
            self._sender.__exit__(None, None, None)

    def _require_active(self) -> None:
        if not self._active or self._closed:
            raise PermissionError("T116-31: сесія неактивна")

    def check_deadline(self) -> None:
        """Перевіряти дедлайн також поза callback, через окремий watchdog."""
        self._require_active()
        try:
            self._sender.check_deadline()
        except BaseException:
            self.close()
            raise

    def on_connected(
        self, *, client_id: str, client_secret: str, access_token: str
    ) -> None:
        """Запустити лише ApplicationAuth після зовнішнього connected-event."""
        self._require_active()
        try:
            self._sender.check_deadline()
            if self.discovery.phase != "NEW":
                raise RuntimeError("T116-31: повторна авторизація заборонена")
            if not isinstance(access_token, str) or not access_token.strip():
                raise PermissionError("T116-31: відсутній DEMO access token")
            self._access_token = access_token
            self.discovery.send_application_auth(
                client_id=client_id,
                client_secret=client_secret,
            )
        except BaseException:
            self.close()
            raise

    def on_envelope(self, envelope: Any) -> int | None:
        """Приймати тільки typed SDK envelope; після SymbolsList закривати."""
        self._require_active()
        try:
            self._sender.check_deadline()
            if self.discovery.phase not in {
                "APPLICATION_AUTH_SENT",
                "ACCOUNT_AUTH_SENT",
                "SYMBOLS_REQUESTED",
            }:
                raise PermissionError("T116-31: відповідь поза очікуваною фазою")
            if type(envelope) is not self._envelope_type:
                raise PermissionError("T116-31: невідомий SDK-конверт")
            initialized = getattr(envelope, "IsInitialized", None)
            if not callable(initialized) or not initialized():
                raise PermissionError("T116-31: неповний SDK-конверт")
            payload_id = getattr(envelope, "payloadType", None)
            response_type = self._response_types.get(payload_id)
            if response_type is None:
                raise PermissionError("T116-31: заборонений тип відповіді")
            payload = getattr(envelope, "payload", None)
            if (
                not isinstance(payload, bytes)
                or len(payload) > MAX_INBOUND_PAYLOAD_BYTES
            ):
                raise PermissionError("T116-31: некоректний розмір payload")
            # Порожня ApplicationAuthRes допустима у proto2 SDK.
            if (
                not payload
                and response_type.DESCRIPTOR.name != "ProtoOAApplicationAuthRes"
            ):
                raise PermissionError("T116-31: порожня відповідь")
            response = response_type()
            try:
                response.ParseFromString(payload)
            except (DecodeError, TypeError, ValueError) as exc:
                raise PermissionError("T116-31: пошкоджений protobuf") from exc
            if not response.IsInitialized():
                raise PermissionError("T116-31: неповна відповідь")

            if type(response) is self._response_types_by_name(
                "ProtoOAApplicationAuthRes"
            ):
                self.discovery.accept_application_auth(response)
                token = self._access_token
                self._access_token = None
                if token is None:
                    raise PermissionError("T116-31: втрачений DEMO token")
                self.discovery.send_account_auth(access_token=token)
                return None
            if type(response) is self._response_types_by_name("ProtoOAAccountAuthRes"):
                self.discovery.accept_account_auth(response)
                self.discovery.send_symbols_list()
                return None

            self.symbol_id = self.discovery.accept_symbols_list(response)
            result = self.symbol_id
            self.close()
            return result
        except BaseException:
            self.close()
            raise

    def _response_types_by_name(self, name: str) -> type[Message]:
        """Повернути клас зі статичного білого списку для перевірки identity."""
        for response_type in self._response_types.values():
            if response_type.DESCRIPTOR.name == name:
                return response_type
        raise RuntimeError("T116-31: неочікувана схема SDK")

    def on_disconnected(self) -> None:
        """Розрив до відповіді EURUSD — помилка, а не успіх."""
        completed = self.symbol_id is not None
        self.close()
        if not completed:
            raise ConnectionError("T116-31: DEMO від'єднано до SymbolsList")
