"""T116-37 TEST_ONLY — офлайн-передача LGE credentials у supervised child.

Секрети читаються через T116-36 та передаються тільки в ``Popen(env=...)``.
Child викликає виключно ``T116-33 --offline-preflight``. Жоден режим
T116-37 не запускає DEMO-мережу, торгівлю чи production-логіку.
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS,
    SupervisedResult,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE,
    authorized_credentials,
)
from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
    RESULT_OFFLINE,
)
from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
    main as t116_33_main,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgedCredentials,
    BridgeRejected,
    make_launcher_environment,
    read_credentials_for_bridge,
)

CHILD_MODULE = "tests.roadmap116.t116_37_lge_supervised_offline_bridge"
CHILD_MARKER = "T116-37=GREEN_SYNTHETIC_OFFLINE_CHILD"
READY_MARKER = "T116-37=READY_FOR_SEPARATE_NETWORK_APPROVAL"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CredentialReader = Callable[[str], BridgedCredentials]
ChildRunner = Callable[[Mapping[str, str]], SupervisedResult]


def assert_offline_environment(environment: Mapping[str, str]) -> None:
    """Заборонити approval і неповні credentials до запуску процесу."""
    if NETWORK_APPROVAL_VARIABLE in environment:
        raise BridgeRejected("NETWORK_APPROVAL_MUST_BE_UNSET")
    if not all(
        isinstance(environment.get(name), str) and bool(environment[name].strip())
        for name in CREDENTIAL_VARIABLES
    ):
        raise BridgeRejected("OFFLINE_CHILD_CREDENTIALS_INCOMPLETE")
    try:
        authorized_credentials(confirmation=None, environment=environment)
    except PermissionError:
        pass
    else:
        raise BridgeRejected("READONLY_LAUNCH_GUARD_FAILED")


def prepare_child_environment(
    password: str,
    *,
    credential_reader: CredentialReader = read_credentials_for_bridge,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """З'єднати T116-36 з child-env, не змінюючи ``os.environ``."""
    source = os.environ if environment is None else environment
    if NETWORK_APPROVAL_VARIABLE in source:
        raise BridgeRejected("NETWORK_APPROVAL_MUST_BE_UNSET")
    with external_tcp_denied():
        credentials = credential_reader(password)
    if not isinstance(credentials, BridgedCredentials):
        raise BridgeRejected("CREDENTIAL_READER_INVALID")
    child_env = make_launcher_environment(credentials, environment=source)
    assert_offline_environment(child_env)
    return child_env


def run_offline_child(environment: Mapping[str, str]) -> SupervisedResult:
    """Один контрольований offline subprocess, hard timeout = T116-26."""
    assert_offline_environment(environment)
    command = [sys.executable, "-m", CHILD_MODULE, "--offline-child"]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        cwd=str(PROJECT_ROOT),
        env=dict(environment),
    )
    try:
        try:
            stdout, stderr = process.communicate(timeout=SUPERVISOR_TIMEOUT_SECONDS)
            return SupervisedResult(
                returncode=process.wait(),
                hard_timeout=False,
                reaped=process.poll() is not None,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
            return SupervisedResult(
                returncode=124,
                hard_timeout=True,
                reaped=process.poll() is not None,
                stdout=stdout,
                stderr=stderr,
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)


def child_result_valid(result: SupervisedResult) -> bool:
    """Оцінити child лише за безпечними константними маркерами."""
    if result.hard_timeout or not result.reaped or result.returncode != 0:
        return False
    lines = result.stdout.splitlines()
    return (
        lines.count(CHILD_MARKER) == 1
        and lines.count(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}") == 1
        and lines.count("credentials_mapped=3/3") == 1
        and lines.count("network_launch_authorized=NO") == 1
        and lines.count("real_broker_requests=0") == 1
    )


def safe_report(*, succeeded: bool, failure_code: str) -> str:
    """Жодного raw stdout/stderr, credentials, env або traceback."""
    return "\n".join(
        (
            "T116-37 TEST_ONLY | LGE supervised OFFLINE child integration",
            f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
            f"credentials_mapped={'3/3' if succeeded else 'NOT_READY'}",
            "child_environment=EXPLICIT_ENV_ONLY",
            "child_module=T116-37_CALLS_T116-33_OFFLINE_PREFLIGHT_ONLY",
            "child_process="
            + ("SYNTHETIC_STARTED_AND_REAPED" if succeeded else "NOT_READY_OR_FAILED"),
            f"supervisor_timeout_seconds={int(SUPERVISOR_TIMEOUT_SECONDS)}",
            "network_approval_env=UNSET_OR_REJECTED",
            "orders_off=NOT_VERIFIED_OPERATOR_REQUIRED",
            "wsp_stopped=NOT_VERIFIED_OPERATOR_REQUIRED",
            "credentials_values=NOT_LOGGED",
            "config_and_tokens_written=NO",
            "sdk_client_constructor=NOT_CALLED",
            "real_broker_requests=0",
            "production_changes=0",
            "network_launch_authorized=NO",
            f"failure_code={failure_code}",
            READY_MARKER if succeeded else "T116-37=NOT_READY_OFFLINE",
        )
    )


def check_machine(
    password: str,
    *,
    credential_reader: CredentialReader = read_credentials_for_bridge,
    environment: Mapping[str, str] | None = None,
    child_runner: ChildRunner = run_offline_child,
) -> str:
    """Тільки підготовка env і офлайн-дочірній процес, без мережі."""
    try:
        child_env = prepare_child_environment(
            password,
            credential_reader=credential_reader,
            environment=environment,
        )
        result = child_runner(child_env)
        if not child_result_valid(result):
            return safe_report(succeeded=False, failure_code="OFFLINE_CHILD_FAILED")
    except BridgeRejected:
        return safe_report(succeeded=False, failure_code="BRIDGE_REJECTED")
    # noinspection PyBroadException
    except Exception:  # noqa
        return safe_report(succeeded=False, failure_code="SUPERVISOR_FAILED")
    return safe_report(succeeded=True, failure_code="NONE")


def offline_child() -> int:
    """Child не приймає мережевих аргументів; лише T116-33 офлайн."""
    try:
        with external_tcp_denied():
            assert_offline_environment(os.environ)
            with redirect_stdout(StringIO()) as output:
                status = t116_33_main(["--offline-preflight"], environment=os.environ)
            if status != 0 or output.getvalue().splitlines().count(RESULT_OFFLINE) != 1:
                raise BridgeRejected("T11633_OFFLINE_PREFLIGHT_FAILED")
    except (BridgeRejected, PermissionError):
        print("T116-37=OFFLINE_CHILD_REJECTED")
        return 2
    # noinspection PyBroadException
    except Exception:  # noqa
        print("T116-37=OFFLINE_CHILD_FAILED")
        return 2
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print("credentials_mapped=3/3")
    print("real_broker_requests=0")
    print("network_launch_authorized=NO")
    print(CHILD_MARKER)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    ask_password: Callable[[str], str] = getpass.getpass,
    checker: Callable[[str], str] = check_machine,
) -> int:
    """Лише локальна офлайн-перевірка або синтетичний offline child."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-machine", action="store_true")
    modes.add_argument("--offline-child", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.offline_child:
        return offline_child()
    try:
        password = ask_password("Пароль входу LGE (не відображається): ")
    except (EOFError, KeyboardInterrupt):
        password = ""
    report = checker(password)
    print(report)
    return 0 if READY_MARKER in report.splitlines() else 2


if __name__ == "__main__":
    raise SystemExit(main())
