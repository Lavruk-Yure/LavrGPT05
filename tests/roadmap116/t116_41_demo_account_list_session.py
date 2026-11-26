"""T116-41 TEST_ONLY — callback-сесія DEMO AccountList без мережі.

Лише ApplicationAuth -> AccountList -> перевірка ідентичності T116-39.
Передавання повідомлень ін'єктоване; Client, TCP, credentials LGE відсутні.
T116-40 забезпечує окремий scoped outbound guard у runnable-тесті.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from google.protobuf.message import DecodeError, Message

from tests.roadmap116.t116_39_demo_account_identity_preflight import (
    EXPECTED_API_ACCOUNT_ID,
    IdentityCheck,
    verify_account_identity,
)

RESPONSE_NAMES = (
    "ProtoOAApplicationAuthRes",
    "ProtoOAGetAccountListByAccessTokenRes",
)
MAX_RESPONSE_BYTES = 1024 * 1024
SESSION_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, slots=True)
class AccountRecordAdapter:
    """Незмінна форма protobuf-запису для Protocol T116-39."""

    ctidTraderAccountId: int
    traderLogin: int
    isLive: bool
    present: frozenset[str]

    # noinspection PyPep8Naming
    def HasField(self, field: str) -> bool:
        return field in self.present


def normalize_accounts(records: Any) -> tuple[AccountRecordAdapter, ...]:
    """Зняти protobuf presence-флаги; жодних secrets чи network."""
    converted: list[AccountRecordAdapter] = []
    try:
        for record in records:
            if len(converted) >= 100:
                raise PermissionError("T116-41: AccountList завеликий")
            present = frozenset(
                name for name in ("ctidTraderAccountId", "traderLogin", "isLive")
                if record.HasField(name)
            )
            if "ctidTraderAccountId" not in present:
                raise PermissionError("T116-41: account ID відсутній")
            converted.append(AccountRecordAdapter(
                ctidTraderAccountId=record.ctidTraderAccountId,
                traderLogin=record.traderLogin,
                isLive=record.isLive,
                present=present,
            ))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PermissionError("T116-41: неправильний AccountList") from exc
    return tuple(converted)


class OfflineAccountListSession:
    """Обробити рівно дві відповіді SDK та завершитися fail-closed."""

    def __init__(
        self,
        *,
        sdk_messages: object,
        envelope_type: type,
        response_payload_types: Mapping[str, int],
        sender: Callable[[Message], None],
        disconnect: Callable[[], None],
        clock: Callable[[], float],
        account_mode: str = "DEMO",
        account_id: int = EXPECTED_API_ACCOUNT_ID,
    ) -> None:
        if account_mode != "DEMO" or type(account_id) is not int:
            raise PermissionError("T116-41: лише обраний DEMO")
        if account_id != EXPECTED_API_ACCOUNT_ID:
            raise PermissionError("T116-41: чужий API account")
        if set(response_payload_types) != set(RESPONSE_NAMES):
            raise ValueError("T116-41: неправильний whitelist відповідей")
        values = tuple(response_payload_types.values())
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("T116-41: невірний payloadType")
        if len(set(values)) != len(RESPONSE_NAMES):
            raise ValueError("T116-41: дубль payloadType")
        if not isinstance(envelope_type, type):
            raise TypeError("T116-41: envelope type відсутній")
        if not all(callable(item) for item in (sender, disconnect, clock)):
            raise TypeError("T116-41: неповний офлайн транспорт")

        self._requests: dict[str, type[Message]] = {}
        for name in (
            "ProtoOAApplicationAuthReq",
            "ProtoOAGetAccountListByAccessTokenReq",
        ):
            message_type = getattr(sdk_messages, name, None)
            if not isinstance(message_type, type) or not issubclass(
                message_type, Message
            ) or message_type.DESCRIPTOR.name != name:
                raise TypeError("T116-41: невірна SDK request schema")
            self._requests[name] = message_type

        self._responses: dict[int, type[Message]] = {}
        for name in RESPONSE_NAMES:
            message_type = getattr(sdk_messages, name, None)
            if not isinstance(message_type, type) or not issubclass(
                message_type, Message
            ) or message_type.DESCRIPTOR.name != name:
                raise TypeError("T116-41: невірна SDK response schema")
            declared_payload = getattr(message_type(), "payloadType", None)
            if declared_payload is not None and declared_payload != (
                response_payload_types[name]
            ):
                raise ValueError("T116-41: невірний SDK response payloadType")
            self._responses[response_payload_types[name]] = message_type

        self._envelope_type = envelope_type
        self._sender = sender
        self._disconnect = disconnect
        self._clock = clock
        self._phase = "NEW"
        self._deadline: float | None = None
        self._access_token: str | None = None
        self._closed = False
        self.identity: IdentityCheck | None = None

    @property
    def phase(self) -> str:
        return self._phase

    def close(self) -> None:
        """Знищити посилання на токен і закрити транспорт один раз."""
        if self._closed:
            return
        self._closed = True
        self._access_token = None
        self._phase = "CLOSED"
        self._disconnect()

    def _require_active(self) -> None:
        if self._closed or self._phase == "NEW":
            raise PermissionError("T116-41: сесія не активна")

    def check_deadline(self) -> None:
        self._require_active()
        now = self._clock()
        deadline = self._deadline
        if not isfinite(now) or deadline is None or now >= deadline:
            self.close()
            raise TimeoutError("T116-41: deadline")

    def on_connected(
        self, *, client_id: str, client_secret: str, access_token: str
    ) -> None:
        """Тільки перший SDK connected-event запускає ApplicationAuth."""
        if self._closed or self._phase != "NEW":
            raise PermissionError("T116-41: повторний connect")
        try:
            for value in (client_id, client_secret, access_token):
                if type(value) is not str or not value or value != value.strip():
                    raise PermissionError("T116-41: неповні credentials")
            now = self._clock()
            if not isfinite(now):
                raise TimeoutError("T116-41: невідомий час")
            self._deadline = now + SESSION_TIMEOUT_SECONDS
            self._access_token = access_token
            message = self._requests["ProtoOAApplicationAuthReq"]()
            setattr(message, "clientId", client_id)
            setattr(message, "clientSecret", client_secret)
            if not message.IsInitialized():
                raise PermissionError("T116-41: неповний ApplicationAuth")
            self._phase = "APP_SENT"
            self._sender(message)
        except BaseException:
            self.close()
            raise

    def on_envelope(self, envelope: Any) -> IdentityCheck | None:
        """Відхилити сторонні, пошкоджені, повторні та невчасні відповіді."""
        self._require_active()
        try:
            self.check_deadline()
            if self._phase not in ("APP_SENT", "LIST_SENT"):
                raise PermissionError("T116-41: невірна фаза")
            if type(envelope) is not self._envelope_type:
                raise PermissionError("T116-41: сторонній envelope")
            initialized = getattr(envelope, "IsInitialized", None)
            if not callable(initialized) or not initialized():
                raise PermissionError("T116-41: неповний envelope")
            payload_id = getattr(envelope, "payloadType", None)
            message_type = self._responses.get(payload_id)
            if message_type is None:
                raise PermissionError("T116-41: неочікуваний payloadType")
            expected_name = RESPONSE_NAMES[0 if self._phase == "APP_SENT" else 1]
            if message_type.DESCRIPTOR.name != expected_name:
                raise PermissionError("T116-41: порушено порядок відповідей")
            payload = getattr(envelope, "payload", None)
            if type(payload) is not bytes or len(payload) > MAX_RESPONSE_BYTES:
                raise PermissionError("T116-41: неправильний payload")
            if not payload and expected_name != RESPONSE_NAMES[0]:
                raise PermissionError("T116-41: порожній AccountList")
            response = message_type()
            try:
                response.ParseFromString(payload)
            except (DecodeError, TypeError, ValueError) as exc:
                raise PermissionError("T116-41: пошкоджений protobuf") from exc
            if not response.IsInitialized():
                raise PermissionError("T116-41: неповний protobuf")

            if self._phase == "APP_SENT":
                token = self._access_token
                self._access_token = None
                if token is None:
                    raise PermissionError("T116-41: токен втрачений")
                request = self._requests[
                    "ProtoOAGetAccountListByAccessTokenReq"
                ]()
                setattr(request, "accessToken", token)
                if not request.IsInitialized():
                    raise PermissionError("T116-41: неповний AccountList request")
                self._phase = "LIST_SENT"
                self._sender(request)
                return None

            accounts = getattr(response, "ctidTraderAccount", None)
            check = verify_account_identity(normalize_accounts(accounts))
            if not check.matched:
                raise PermissionError(f"T116-41: {check.reason}")
            self.identity = check
            self.close()
            return check
        except BaseException:
            self.close()
            raise

    def on_disconnected(self) -> None:
        completed = self.identity is not None and self.identity.matched
        self.close()
        if not completed:
            raise ConnectionError("T116-41: disconnect до AccountList")

    def on_sdk_error(self) -> None:
        self.close()
        raise RuntimeError("T116-41: SDK error до завершення")
