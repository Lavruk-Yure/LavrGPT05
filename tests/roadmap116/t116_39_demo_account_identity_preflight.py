"""T116-39 TEST_ONLY — підтвердження пари DEMO account ID / trader login.

Обробляє лише відповідь AccountList, надану ззовні. Не читає токени,
не створює SDK Client і не запускає TCP. Мережевий AccountList запит
залишається поза whitelist T116-29 до окремого рішення.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Protocol, runtime_checkable

from tests.roadmap116 import t116_29_sdk_outbound_guard as outbound
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied

EXPECTED_API_ACCOUNT_ID = 46368962
EXPECTED_GUI_TRADER_LOGIN = 9870599
ACCOUNT_LIST_REQUEST = "ProtoOAGetAccountListByAccessTokenReq"
ACCOUNT_LIST_RESPONSE = "ProtoOAGetAccountListByAccessTokenRes"
REQUIRED_ACCOUNT_FIELDS = (
    "ctidTraderAccountId",
    "traderLogin",
    "isLive",
)
SUCCESS_MARKER = "T116-39=GREEN_OFFLINE_ACCOUNT_IDENTITY_CONTRACT"


@runtime_checkable
class AccountRecord(Protocol):
    """Мінімальний інтерфейс SDK ProtoOACtidTraderAccount."""

    ctidTraderAccountId: int
    traderLogin: int
    isLive: bool

    # noinspection PyPep8Naming
    def HasField(self, field: str) -> bool:  # noqa: N802
        """Перевірка присутності необов'язкового protobuf-поля."""
        ...


@dataclass(frozen=True, slots=True)
class IdentityCheck:
    """Результат без облікових даних, адрес і сирих SDK-повідомлень."""

    matched: bool
    reason: str


def verify_account_identity(accounts: Iterable[object]) -> IdentityCheck:
    """Зіставити тільки одну пару ID/login, відхиливши неоднозначність.

    Значення полів з реального SDK мають бути явно присутніми.
    Різні DEMO/LIVE рахунки одного користувача допустимі, але
    вибраний API ID повинен відповідати DEMO і потрібному GUI login.
    """
    seen_ids: set[int] = set()
    seen_logins: set[int] = set()
    target: AccountRecord | None = None
    count = 0
    try:
        for record in accounts:
            count += 1
            if count > 100:
                return IdentityCheck(False, "ACCOUNT_LIST_TOO_LARGE")
            if not isinstance(record, AccountRecord):
                return IdentityCheck(False, "ACCOUNT_RESPONSE_INVALID")
            if any(
                not record.HasField(name)
                for name in ("traderLogin", "isLive")
            ):
                return IdentityCheck(False, "ACCOUNT_FIELD_MISSING")
            api_id = record.ctidTraderAccountId
            login = record.traderLogin
            live = record.isLive
            if (
                type(api_id) is not int
                or api_id <= 0
                or type(login) is not int
                or login <= 0
                or type(live) is not bool
            ):
                return IdentityCheck(False, "ACCOUNT_FIELD_INVALID")
            if api_id in seen_ids or login in seen_logins:
                return IdentityCheck(False, "DUPLICATE_ACCOUNT_IDENTITY")
            seen_ids.add(api_id)
            seen_logins.add(login)
            if api_id == EXPECTED_API_ACCOUNT_ID:
                target = record
    except (AttributeError, TypeError, ValueError):
        return IdentityCheck(False, "ACCOUNT_RESPONSE_INVALID")

    if target is None:
        return IdentityCheck(False, "TARGET_API_ACCOUNT_NOT_FOUND")
    if target.traderLogin != EXPECTED_GUI_TRADER_LOGIN:
        return IdentityCheck(False, "GUI_TRADER_LOGIN_MISMATCH")
    if target.isLive:
        return IdentityCheck(False, "TARGET_NOT_DEMO")
    return IdentityCheck(True, "IDENTITY_PAIR_MATCHES_DEMO")


def existing_outbound_policy_locked() -> bool:
    """Новий мережевий тип поки відсутній у чинному whitelist."""
    return (
        outbound.PERMITTED_REQUEST_NAMES == (
            "ProtoOAApplicationAuthReq",
            "ProtoOAAccountAuthReq",
            "ProtoOASymbolsListReq",
            "ProtoHeartbeatEvent",
        )
        and ACCOUNT_LIST_REQUEST not in outbound.PERMITTED_REQUEST_NAMES
    )


def sdk_schema_preflight() -> str:
    """Тільки схема реального SDK: без Client, токенів і мережі."""
    if find_spec("ctrader_open_api") is None:
        return "NOT_INSTALLED_LOCAL_RUNNER"
    try:
        with external_tcp_denied():
            messages = import_module(
                "ctrader_open_api.messages.OpenApiMessages_pb2"
            )
            models = import_module(
                "ctrader_open_api.messages.OpenApiModelMessages_pb2"
            )
            request_type = getattr(messages, ACCOUNT_LIST_REQUEST)
            response_type = getattr(messages, ACCOUNT_LIST_RESPONSE)
            account_type = getattr(models, "ProtoOACtidTraderAccount")
            fields = account_type.DESCRIPTOR.fields_by_name
            if not all(name in fields for name in REQUIRED_ACCOUNT_FIELDS):
                return "SCHEMA_INCOMPATIBLE"
            if not all(
                callable(getattr(message_type, "SerializeToString", None))
                for message_type in (request_type, response_type)
            ):
                return "SCHEMA_INCOMPATIBLE"
            if not hasattr(response_type(), "ctidTraderAccount"):
                return "SCHEMA_INCOMPATIBLE"
    except (
        AttributeError, ImportError, KeyError, OSError,
        RuntimeError, TypeError, ValueError,
    ):
        return "SDK_SCHEMA_FAILED"
    return "VERIFIED_NO_EXTERNAL_NETWORK"


def format_report(schema_status: str) -> str:
    """Звіт не містить secrets, payload або неперевірених фактів."""
    locked = existing_outbound_policy_locked()
    ready = locked and schema_status == "VERIFIED_NO_EXTERNAL_NETWORK"
    return "\n".join((
        "T116-39 TEST_ONLY | DEMO account identity OFFLINE preflight",
        f"expected_api_account_id={EXPECTED_API_ACCOUNT_ID}",
        f"expected_gui_trader_login={EXPECTED_GUI_TRADER_LOGIN}",
        "identity_fields=CTID_TRADER_ACCOUNT_ID_TRADER_LOGIN_IS_LIVE",
        "identity_validator=SYNTHETIC_ONLY",
        "real_identity_pair=NOT_QUERIED_NO_NETWORK",
        f"sdk_account_list_schema={schema_status}",
        "account_list_outbound=" + (
            "BLOCKED_PENDING_NEW_POLICY" if locked else "POLICY_MISMATCH"
        ),
        "credentials=NOT_READ",
        "sdk_client_constructor=NOT_CALLED",
        "child_process=NOT_STARTED",
        "external_tcp=BLOCKED",
        "real_broker_requests=0",
        "production_changes=0",
        "network_launch_authorized=NO",
        SUCCESS_MARKER if ready else "T116-39=NOT_READY_OFFLINE",
    ))


def main(argv: Sequence[str] | None = None) -> int:
    """Відмовляти будь-якому режиму, окрім офлайн-перевірки."""
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
