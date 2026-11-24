"""T116-24 TEST_ONLY — послідовне визначення EURUSD для cTrader DEMO.

Без SDK Client, TCP, GUI, LGE, WSP, RuntimeEngine та конфігураційних файлів.
Приймає тільки три дозволені типи protobuf через ін'єктований sender.
"""

from __future__ import annotations

from types import ModuleType

from google.protobuf.message import Message

from tests.roadmap116.t116_22_standalone_demo_reader import (
    DEMO_API_ACCOUNT_ID,
    ReadOnlySender,
)
from tests.roadmap116.t116_23_sdk_offline_bridge import (
    new_symbols_request,
    resolve_eurusd_id,
    sdk_message_type,
)

ALLOWED_DISCOVERY_REQUESTS = frozenset({
    "ProtoOAApplicationAuthReq",
    "ProtoOAAccountAuthReq",
    "ProtoOASymbolsListReq",
})


class DemoSymbolDiscovery:
    """Виконувати офлайн-контракт авторизації та вибору одного EURUSD."""

    def __init__(
        self,
        *,
        account_mode: str,
        account_id: int,
        messages: ModuleType,
        sender: ReadOnlySender,
    ) -> None:
        if account_mode != "DEMO" or account_id != DEMO_API_ACCOUNT_ID:
            raise PermissionError("T116-24: дозволений лише підтверджений DEMO API ID")
        self.account_id = account_id
        self.messages = messages
        self._sender = sender
        self.phase = "NEW"
        self.symbol_id: int | None = None

    def send_read_only(self, request: Message) -> None:
        """Відхилити торгові та невідомі protobuf до транспорту."""
        if not isinstance(request, Message):
            raise PermissionError("T116-24: потрібен типізований protobuf")
        name = request.DESCRIPTOR.name
        if name not in ALLOWED_DISCOVERY_REQUESTS:
            raise PermissionError("T116-24: protobuf поза білим списком")
        if type(request) is not sdk_message_type(self.messages, name):
            raise PermissionError("T116-24: невідомий клас protobuf")
        allowed_phase = {
            "ProtoOAApplicationAuthReq": "NEW",
            "ProtoOAAccountAuthReq": "APPLICATION_AUTHORIZED",
            "ProtoOASymbolsListReq": "ACCOUNT_AUTHORIZED",
        }[name]
        self._require_phase(allowed_phase)
        if name == "ProtoOAApplicationAuthReq":
            for field_name in ("clientId", "clientSecret"):
                if not str(getattr(request, field_name, "")).strip():
                    raise PermissionError("T116-24: порожні credentials")
        else:
            account = int(getattr(request, "ctidTraderAccountId", 0))
            if account != self.account_id:
                raise PermissionError("T116-24: чужий API ID")
        if name == "ProtoOAAccountAuthReq":
            if not str(getattr(request, "accessToken", "")).strip():
                raise PermissionError("T116-24: порожній token")
        if name == "ProtoOASymbolsListReq":
            if "includeArchivedSymbols" not in request.DESCRIPTOR.fields_by_name:
                raise PermissionError("T116-24: немає прапорця archived")
            if bool(getattr(request, "includeArchivedSymbols")):
                raise PermissionError("T116-24: archived символи заборонені")
        if not request.IsInitialized():
            raise PermissionError("T116-24: неповний protobuf")
        self._sender.send(request)

    @staticmethod
    def reject_raw_packet(_packet: bytes) -> None:
        """Сирі байти не можуть обійти перевірку типу."""
        raise PermissionError("T116-24: raw TCP заборонено")

    def _require_phase(self, expected: str) -> None:
        if self.phase != expected:
            raise RuntimeError("T116-24: неправильна послідовність авторизації")

    def _require_response(self, payload: Message, name: str) -> None:
        if type(payload) is not sdk_message_type(self.messages, name):
            raise PermissionError("T116-24: неочікуваний тип відповіді")
        if not payload.IsInitialized():
            raise PermissionError("T116-24: неповна відповідь")

    def send_application_auth(self, *, client_id: str, client_secret: str) -> None:
        """Перший крок: лише авторизація застосунку."""
        self._require_phase("NEW")
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("T116-24: порожні TEST_ONLY credentials")
        request = sdk_message_type(self.messages, "ProtoOAApplicationAuthReq")()
        setattr(request, "clientId", client_id)
        setattr(request, "clientSecret", client_secret)
        self.send_read_only(request)
        self.phase = "APPLICATION_AUTH_SENT"

    def accept_application_auth(self, response: Message) -> None:
        self._require_phase("APPLICATION_AUTH_SENT")
        self._require_response(response, "ProtoOAApplicationAuthRes")
        self.phase = "APPLICATION_AUTHORIZED"

    def send_account_auth(self, *, access_token: str) -> None:
        """Другий крок: авторизувати тільки потрібний DEMO-рахунок."""
        self._require_phase("APPLICATION_AUTHORIZED")
        if not access_token.strip():
            raise ValueError("T116-24: порожній TEST_ONLY token")
        request = sdk_message_type(self.messages, "ProtoOAAccountAuthReq")()
        setattr(request, "ctidTraderAccountId", self.account_id)
        setattr(request, "accessToken", access_token)
        self.send_read_only(request)
        self.phase = "ACCOUNT_AUTH_SENT"

    def accept_account_auth(self, response: Message) -> None:
        self._require_phase("ACCOUNT_AUTH_SENT")
        self._require_response(response, "ProtoOAAccountAuthRes")
        account = int(getattr(response, "ctidTraderAccountId", 0))
        if account != self.account_id:
            raise PermissionError("T116-24: відповідь для чужого рахунку")
        self.phase = "ACCOUNT_AUTHORIZED"

    def send_symbols_list(self) -> None:
        """Третій крок: запитати тільки активні символи рахунку."""
        self._require_phase("ACCOUNT_AUTHORIZED")
        request = new_symbols_request(self.messages)
        if "includeArchivedSymbols" in request.DESCRIPTOR.fields_by_name:
            setattr(request, "includeArchivedSymbols", False)
        self.send_read_only(request)
        self.phase = "SYMBOLS_REQUESTED"

    def accept_symbols_list(self, response: Message) -> int:
        """Визначити ID тільки з відповіді цього DEMO-рахунку."""
        self._require_phase("SYMBOLS_REQUESTED")
        symbol_id = resolve_eurusd_id(self.messages, response)
        self.symbol_id = symbol_id
        self.phase = "RESOLVED"
        return symbol_id
