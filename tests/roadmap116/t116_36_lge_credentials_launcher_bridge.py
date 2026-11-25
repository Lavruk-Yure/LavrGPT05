"""T116-36 TEST_ONLY — офлайн-міст LGE credentials до DEMO launcher.

Читає тільки вже наявні джерела LGE через T116-35. Створює в пам'яті
окреме середовище з ключами, які очікує T116-32. Не змінює os.environ,
не створює процеси, не запускає SDK Client і не дозволяє DEMO-мережу.
Жоден режим цього модуля не запускає T116-33 або T116-32.
"""

from __future__ import annotations

import argparse
import getpass
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE,
    authorized_credentials,
)
from tests.roadmap116.t116_35_existing_lge_credentials_readiness import (
    load_lge_tokens,
    read_lge_config_readonly,
    token_valid_by_lge,
)


class BridgeRejected(RuntimeError):
    """Заздалегідь відомий безпечний код відмови, без секретів."""


@dataclass(frozen=True, slots=True, repr=False)
class BridgedCredentials:
    """Секретні значення зберігаються тільки в пам'яті процесу."""

    client_id: str
    client_secret: str
    access_token: str

    def __repr__(self) -> str:
        return "BridgedCredentials(REDACTED)"


def read_credentials_for_bridge(
    password: str,
    *,
    config_reader: Callable[[str], dict] = read_lge_config_readonly,
    tokens_reader: Callable[[], dict | None] = load_lge_tokens,
    token_validator: Callable[[dict | None], bool] = token_valid_by_lge,
    environment: Mapping[str, str] | None = None,
) -> BridgedCredentials:
    """Перевірити DEMO/рахунок/токен без запису й без мережі."""
    env = os.environ if environment is None else environment
    if NETWORK_APPROVAL_VARIABLE in env:
        raise BridgeRejected("APPROVAL_ENV_MUST_BE_UNSET")
    if not password:
        raise BridgeRejected("LGE_PASSWORD_REQUIRED")

    # Заборона TCP діє навіть на передані ззовні функції читання.
    with external_tcp_denied():
        try:
            config: Any = config_reader(password)
        # noinspection PyBroadException
        except Exception:
            raise BridgeRejected("LGE_CONFIG_UNREADABLE") from None
        try:
            tokens: Any = tokens_reader()
        # noinspection PyBroadException
        except Exception:
            raise BridgeRejected("LGE_TOKENS_UNREADABLE") from None
        try:
            valid = bool(token_validator(tokens))
        # noinspection PyBroadException
        except Exception:
            raise BridgeRejected("LGE_TOKEN_VALIDATION_FAILED") from None

    if not isinstance(config, dict):
        raise BridgeRejected("LGE_CONFIG_INVALID")
    ctrader = config.get("ctrader")
    if not isinstance(ctrader, dict):
        raise BridgeRejected("LGE_CTRADER_CONFIG_MISSING")
    if str(ctrader.get("account_mode") or "").strip().upper() != "DEMO":
        raise BridgeRejected("DEMO_MODE_REQUIRED")
    if str(ctrader.get("account_id") or "").strip() != str(DEMO_API_ACCOUNT_ID):
        raise BridgeRejected("DEMO_ACCOUNT_MISMATCH")
    if not isinstance(tokens, dict):
        raise BridgeRejected("LGE_TOKENS_INVALID")
    if not valid:
        raise BridgeRejected("LOCAL_ACCESS_TOKEN_INVALID")

    values = (
        ctrader.get("client_id"),
        ctrader.get("client_secret"),
        tokens.get("access_token"),
    )
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise BridgeRejected("CREDENTIAL_FIELDS_INCOMPLETE")
    return BridgedCredentials(
        client_id=values[0].strip(),
        client_secret=values[1].strip(),
        access_token=values[2].strip(),
    )


def make_launcher_environment(
    credentials: BridgedCredentials,
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Підготувати окремий env для T116-32, нічого не запускаючи."""
    source = os.environ if environment is None else environment
    if NETWORK_APPROVAL_VARIABLE in source:
        raise BridgeRejected("APPROVAL_ENV_MUST_BE_UNSET")
    child_environment = dict(source)
    for name, value in zip(
        CREDENTIAL_VARIABLES,
        (
            credentials.client_id,
            credentials.client_secret,
            credentials.access_token,
        ),
        strict=True,
    ):
        child_environment[name] = value
    return child_environment


def check_machine(
    password: str,
    *,
    config_reader: Callable[[str], dict] = read_lge_config_readonly,
    tokens_reader: Callable[[], dict | None] = load_lge_tokens,
    token_validator: Callable[[dict | None], bool] = token_valid_by_lge,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Перевірити передачу credentials у пам'яті без дозволу мережі."""
    env = os.environ if environment is None else environment
    try:
        credentials = read_credentials_for_bridge(
            password,
            config_reader=config_reader,
            tokens_reader=tokens_reader,
            token_validator=token_validator,
            environment=env,
        )
        child_environment = make_launcher_environment(
            credentials,
            environment=env,
        )
        if not all(child_environment.get(name) for name in CREDENTIAL_VARIABLES):
            raise BridgeRejected("LAUNCHER_ENV_INCOMPLETE")
        # Після підготовки env мережевий запуск усе ще має бути заборонений.
        try:
            authorized_credentials(
                confirmation=None,
                environment=child_environment,
            )
        except PermissionError:
            pass
        else:
            raise BridgeRejected("NETWORK_LAUNCH_GUARD_FAILED")
    except BridgeRejected as exc:
        return _format_report(False, str(exc))
    # Не друкувати traceback: винятки сторонніх адаптерів можуть мати секрети.
    # noinspection PyBroadException
    except Exception:  # noqa
        return _format_report(False, "READONLY_BRIDGE_FAILED")
    return _format_report(True, "NONE")


def _format_report(ready: bool, failure_code: str) -> str:
    """Звіт тільки з констант і безпечних статусів."""
    return "\n".join(
        (
            "T116-36 TEST_ONLY | LGE to DEMO launcher environment NO NETWORK",
            f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
            f"credentials_mapped={'3/3' if ready else 'NOT_READY'}",
            "launcher_environment=IN_MEMORY_ONLY",
            "launcher_contract=T116-32_EXISTING_GUARD",
            "network_approval_env=" + ("UNSET" if ready else "UNVERIFIED_OR_REJECTED"),
            "orders_off=NOT_VERIFIED_OPERATOR_REQUIRED",
            "wsp_stopped=NOT_VERIFIED_OPERATOR_REQUIRED",
            "credentials_values=NOT_LOGGED",
            "config_and_tokens_written=NO",
            "sdk_client_constructor=NOT_CALLED",
            "child_process=NOT_STARTED",
            "external_tcp=BLOCKED",
            "real_broker_requests=0",
            "production_changes=0",
            "network_launch_authorized=NO",
            f"failure_code={failure_code}",
            "T116-36="
            + (
                "READY_FOR_SEPARATE_LAUNCHER_INTEGRATION"
                if ready
                else "NOT_READY_OFFLINE"
            ),
        )
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    ask_password: Callable[[str], str] = getpass.getpass,
    check: Callable[[str], str] = check_machine,
) -> int:
    """Лише --check-machine; CLI ніколи не запускає дочірній процес."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check-machine", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        password = ask_password("Пароль входу LGE (не відображається): ")
    except (EOFError, KeyboardInterrupt):
        password = ""
    report = check(password)
    print(report)
    return 0 if "T116-36=READY_FOR_SEPARATE_LAUNCHER_INTEGRATION" in report else 2


if __name__ == "__main__":
    raise SystemExit(main())
