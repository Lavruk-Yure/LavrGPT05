"""T116-44 TEST_ONLY — перше кероване DEMO визначення EURUSD symbolId.

Повторно використовує перевірену T116-32 discovery-сесію та guard T116-29.
Offline-режим не читає credentials і не створює SDK Client або child.
Мережевий режим потребує окремого дозволу, ручних підтверджень та LGE.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS,
    SupervisedResult,
)
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VALUE as T11632_APPROVAL_VALUE,
    NETWORK_APPROVAL_VARIABLE as T11632_APPROVAL_VARIABLE,
    NETWORK_CONFIRMATION as T11632_CONFIRMATION,
    authorized_credentials,
    run_demo_network,
)
from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
    sdk_offline_preflight,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgeRejected,
    BridgedCredentials,
    make_launcher_environment,
    read_credentials_for_bridge,
)
from tests.roadmap116.t116_42_supervised_account_list_offline import (
    SYSTEM_ENV_KEYS,
)
from tests.roadmap116.t116_43_first_demo_account_list_network import (
    APPROVAL_VARIABLE as T11643_APPROVAL_VARIABLE,
)

APPROVAL_VARIABLE = "T11644_ALLOW_DEMO_SYMBOL_NETWORK"
APPROVAL_VALUE = "DEMO_EURUSD_46368962_ONE_SHOT"
CLI_CONFIRMATION = "READONLY_SYMBOLS_46368962"
ORDERS_VARIABLE = "T11644_ORDERS_OFF_ATTESTED"
WSP_VARIABLE = "T11644_WSP_STOPPED_ATTESTED"
ORDERS_CONFIRMATION = "ORDERS_OFF"
WSP_CONFIRMATION = "WSP_STOPPED"
CHILD_MODULE = "tests.roadmap116.t116_44_supervised_demo_eurusd_symbol"
CHILD_SUCCESS = "T116-32=GREEN_DEMO_READONLY_SYMBOL_DISCOVERY"
PARENT_SUCCESS = "T116-44=GREEN_SUPERVISED_DEMO_EURUSD_SYMBOL"
OFFLINE_SUCCESS = "T116-44=GREEN_OFFLINE_SYMBOL_NETWORK_PREFLIGHT"
SYMBOL_PATTERN = re.compile(r"^real_eurusd_symbol_id=([1-9][0-9]*)$")
ERROR_PATTERN = re.compile(r"^failure_code=([A-Z][A-Z0-9_]*)$")
ALLOWED_FAILURE_CODES = frozenset({
    "SDK_START_FAILED", "APPLICATION_AUTH_REQUEST_FAILED",
    "UNEXPECTED_OR_INVALID_RESPONSE", "DISCONNECTED_BEFORE_SYMBOLS",
    "DISCOVERY_TIMEOUT", "WATCHDOG_SCHEDULING_FAILED", "SDK_SEND_FAILED",
    "SDK_STOP_FAILED", "REACTOR_OR_SDK_FAILED",
    "REACTOR_EXITED_WITHOUT_RESULT", "NO_RESULT", "SDK_CHILD_FAILED",
})


def approved(
    *, confirmation: str | None, environment: Mapping[str, str],
    operator_confirmations: bool = False,
) -> bool:
    """Вимагати окремий дозвіл, заборонити змішування режимів T116-32/43."""
    if confirmation != CLI_CONFIRMATION:
        return False
    if environment.get(APPROVAL_VARIABLE) != APPROVAL_VALUE:
        return False
    if any(name in environment for name in (
        T11632_APPROVAL_VARIABLE, T11643_APPROVAL_VARIABLE,
    )):
        return False
    if operator_confirmations and (
        environment.get(ORDERS_VARIABLE) != ORDERS_CONFIRMATION
        or environment.get(WSP_VARIABLE) != WSP_CONFIRMATION
    ):
        return False
    return True


def prepare_child_environment(
    credentials: BridgedCredentials,
    *, environment: Mapping[str, str],
    orders_confirmation: str, wsp_confirmation: str,
) -> dict[str, str]:
    """Передати тільки системні змінні й три credentials через Popen env."""
    if not approved(confirmation=CLI_CONFIRMATION, environment=environment):
        raise PermissionError("T116-44: відсутній окремий DEMO дозвіл")
    if (
        orders_confirmation != ORDERS_CONFIRMATION
        or wsp_confirmation != WSP_CONFIRMATION
    ):
        raise PermissionError("T116-44: оператор не підтвердив safety gate")
    safe_env = {
        key: value for key in SYSTEM_ENV_KEYS
        if isinstance((value := environment.get(key)), str) and value
    }
    if os.name == "nt" and not safe_env.get("SystemRoot"):
        raise PermissionError("T116-44: Windows SystemRoot відсутній")
    safe_env[APPROVAL_VARIABLE] = APPROVAL_VALUE
    safe_env[ORDERS_VARIABLE] = ORDERS_CONFIRMATION
    safe_env[WSP_VARIABLE] = WSP_CONFIRMATION
    child_env = make_launcher_environment(credentials, environment=safe_env)
    if not approved(
        confirmation=CLI_CONFIRMATION,
        environment=child_env,
        operator_confirmations=True,
    ):
        raise PermissionError("T116-44: child approval відхилений")
    if not all(child_env.get(name) for name in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-44: credentials не передано")
    return child_env


def run_network_child(credentials: BridgedCredentials) -> int:
    """T116-32 повторно перевіряє credentials та залишає T116-29 guard."""
    temporary_env = {
        T11632_APPROVAL_VARIABLE: T11632_APPROVAL_VALUE,
        **dict(zip(
            CREDENTIAL_VARIABLES,
            (credentials.client_id, credentials.client_secret,
             credentials.access_token),
            strict=True,
        )),
    }
    verified = authorized_credentials(
        confirmation=T11632_CONFIRMATION,
        environment=temporary_env,
    )
    return run_demo_network(credentials=verified)


def supervise_network_child(
    environment: Mapping[str, str],
    *, popen: Callable[..., Any] = subprocess.Popen,
) -> SupervisedResult:
    """Один child, 75 с, shell=False, stderr та raw stdout не виводимо."""
    if not approved(
        confirmation=CLI_CONFIRMATION,
        environment=environment,
        operator_confirmations=True,
    ):
        raise PermissionError("T116-44: child не авторизований")
    if not all(environment.get(name) for name in CREDENTIAL_VARIABLES):
        raise PermissionError("T116-44: немає credentials")
    process = popen(
        [sys.executable, "-m", CHILD_MODULE, "--network-child",
         "--confirm", CLI_CONFIRMATION],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).resolve().parents[2]),
        env=dict(environment),
    )
    try:
        try:
            stdout, stderr = process.communicate(
                timeout=SUPERVISOR_TIMEOUT_SECONDS
            )
            return SupervisedResult(
                returncode=process.wait(), hard_timeout=False,
                reaped=process.poll() is not None,
                stdout=stdout, stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            return SupervisedResult(
                returncode=124, hard_timeout=True,
                reaped=process.poll() is not None,
                stdout=stdout, stderr=stderr,
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


def verified_symbol_id(result: SupervisedResult) -> int | None:
    """Лише точний whitelisted output T116-32, без довіри до зайвих рядків."""
    if (
        result.hard_timeout or not result.reaped
        or result.returncode != 0 or result.stderr
    ):
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 5:
        return None
    match = SYMBOL_PATTERN.fullmatch(lines[1])
    if match is None:
        return None
    symbol_id = int(match.group(1))
    expected = [
        f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
        f"real_eurusd_symbol_id={symbol_id}",
        "outbound_request_policy=APPLICATION_ACCOUNT_SYMBOLS_HEARTBEAT_ONLY",
        "production_changes=0",
        CHILD_SUCCESS,
    ]
    return symbol_id if 0 < symbol_id < 2**63 and lines == expected else None


def safe_failure_code(result: SupervisedResult) -> str:
    """Не показувати необроблений stdout/stderr дочірнього процесу."""
    if result.hard_timeout:
        return "HARD_PROCESS_TIMEOUT"
    if not result.reaped:
        return "CHILD_NOT_REAPED"
    if result.returncode == 0:
        return "INVALID_CHILD_RESULT"
    matches = [
        ERROR_PATTERN.fullmatch(line)
        for line in result.stdout.splitlines()
    ]
    recognized = [
        match.group(1) for match in matches
        if match is not None and match.group(1) in ALLOWED_FAILURE_CODES
    ]
    return recognized[0] if len(recognized) == 1 else "CHILD_PROCESS_FAILED"


def main(
    argv: Sequence[str] | None = None,
    *, environment: Mapping[str, str] | None = None,
    ask: Callable[[str], str] = input,
    ask_password: Callable[[str], str] = getpass.getpass,
    credential_reader: Callable[[str], BridgedCredentials] = (
        read_credentials_for_bridge
    ),
    runner: Callable[[Mapping[str, str]], SupervisedResult] = (
        supervise_network_child
    ),
    sdk_check: Callable[[], str] = sdk_offline_preflight,
    child_runner: Callable[[BridgedCredentials], int] = run_network_child,
) -> int:
    """Без окремого дозволу, перевіреного DEMO SDK та підтверджень — STOP."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--offline-preflight", action="store_true")
    modes.add_argument("--demo-network", action="store_true")
    modes.add_argument("--network-child", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args(argv)
    env = os.environ if environment is None else environment

    if args.offline_preflight:
        if args.confirm is not None:
            parser.error("T116-44: offline не приймає --confirm")
        # noinspection PyBroadException
        try:
            status = sdk_check()
        except Exception:
            status = "SDK_PREFLIGHT_FAILED"
        ready = status == "VERIFIED_NO_EXTERNAL_NETWORK"
        print("T116-44 TEST_ONLY | EURUSD SymbolsList OFFLINE preflight")
        print(f"sdk_offline_preflight={status}")
        print("sdk_client_constructor=NOT_CALLED")
        print("child_process=NOT_STARTED")
        print("real_broker_requests=0")
        print("production_changes=0")
        print("network_launch_authorized=NO")
        print(OFFLINE_SUCCESS if ready else "T116-44=NOT_READY_OFFLINE")
        return 0 if ready else 2

    if not approved(
        confirmation=args.confirm,
        environment=env,
        operator_confirmations=args.network_child,
    ):
        raise PermissionError("T116-44: немає дозволу DEMO-мережі")

    if args.network_child:
        values = tuple(env.get(name, "") for name in CREDENTIAL_VARIABLES)
        if len(values) != 3 or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise PermissionError("T116-44: child credentials відсутні")
        # noinspection PyBroadException
        try:
            return child_runner(BridgedCredentials(*values))
        except Exception:
            print("failure_code=SDK_CHILD_FAILED")
            return 2

    if env is not os.environ:
        raise PermissionError("T116-44: мережа лише з реального environment")
    # noinspection PyBroadException
    try:
        sdk_status = sdk_check()
    except Exception:
        raise PermissionError("T116-44: SDK preflight не пройдено") from None
    if sdk_status != "VERIFIED_NO_EXTERNAL_NETWORK":
        raise PermissionError("T116-44: SDK preflight не пройдено")
    try:
        orders = ask("Перевір Orders=OFF; введи ORDERS_OFF: ")
        wsp = ask("Перевір усі WSP STOPPED; введи WSP_STOPPED: ")
    except (EOFError, KeyboardInterrupt):
        orders, wsp = "", ""
    if orders != ORDERS_CONFIRMATION or wsp != WSP_CONFIRMATION:
        raise PermissionError("T116-44: safety gate відхилений")
    try:
        password = ask_password("Пароль LGE (не відображається): ")
    except (EOFError, KeyboardInterrupt):
        password = ""
    try:
        credentials = credential_reader(password)
        child_env = prepare_child_environment(
            credentials, environment=env,
            orders_confirmation=orders,
            wsp_confirmation=wsp,
        )
    except (BridgeRejected, PermissionError):
        raise PermissionError("T116-44: LGE credentials відхилено") from None
    # noinspection PyBroadException
    except Exception:
        raise PermissionError("T116-44: credentials reader failed") from None
    # noinspection PyBroadException
    try:
        result = runner(child_env)
    except Exception:
        print("failure_code=SUPERVISOR_FAILED")
        print("T116-44=FAILED_SUPERVISED_DEMO_EURUSD_SYMBOL")
        return 1
    symbol_id = verified_symbol_id(result)
    if symbol_id is None:
        print(f"failure_code={safe_failure_code(result)}")
        print("T116-44=FAILED_SUPERVISED_DEMO_EURUSD_SYMBOL")
        return 1
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"real_eurusd_symbol_id={symbol_id}")
    print("request_order=APPLICATION_ACCOUNT_SYMBOLS")
    print("production_changes=0")
    print(PARENT_SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
