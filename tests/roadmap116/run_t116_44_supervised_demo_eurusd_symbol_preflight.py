"""T116-44 TEST_ONLY — жодного реального підключення під час pytest."""

from __future__ import annotations

import ast
import os
import socket
import subprocess
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tests.roadmap116.t116_26_process_watchdog import SupervisedResult
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE as T11632_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgedCredentials,
)
from tests.roadmap116.t116_43_first_demo_account_list_network import (
    APPROVAL_VARIABLE as T11643_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_44_supervised_demo_eurusd_symbol import (
    APPROVAL_VALUE,
    APPROVAL_VARIABLE,
    CHILD_SUCCESS,
    CLI_CONFIRMATION,
    OFFLINE_SUCCESS,
    ORDERS_CONFIRMATION,
    ORDERS_VARIABLE,
    PARENT_SUCCESS,
    WSP_CONFIRMATION,
    WSP_VARIABLE,
    approved,
    main,
    prepare_child_environment,
    run_network_child,
    safe_failure_code,
    supervise_network_child,
    verified_symbol_id,
)

SOURCE = Path(__file__).with_name("t116_44_supervised_demo_eurusd_symbol.py")
CREDENTIALS = BridgedCredentials(
    client_id="T11644_SYNTHETIC_CLIENT_ID",
    client_secret="T11644_SYNTHETIC_CLIENT_SECRET",
    access_token="T11644_SYNTHETIC_ACCESS_TOKEN",
)
SYMBOL_ID = 1234567
GOOD_LINES = (
    "demo_api_account_id=46368962",
    f"real_eurusd_symbol_id={SYMBOL_ID}",
    "outbound_request_policy=APPLICATION_ACCOUNT_SYMBOLS_HEARTBEAT_ONLY",
    "production_changes=0",
    CHILD_SUCCESS,
)


def synthetic_result(
    *, stdout: str | None = None, stderr: str = "", returncode: int = 0,
    hard_timeout: bool = False, reaped: bool = True,
) -> SupervisedResult:
    """Сформувати результат без запуску SDK або мережевого процесу."""
    return SupervisedResult(
        returncode=returncode,
        hard_timeout=hard_timeout,
        reaped=reaped,
        stdout="\n".join(GOOD_LINES) + "\n" if stdout is None else stdout,
        stderr=stderr,
    )


class FakeProcess:
    """Синтетичний supervisor-процес для timeout/reap."""

    def __init__(self, *, timed_out: bool = False) -> None:
        self.timed_out = timed_out
        self.killed = False
        self.returncode: int | None = None
        self.timeouts: list[float] = []

    def communicate(self, *, timeout: float) -> tuple[str, str]:
        self.timeouts.append(timeout)
        if self.timed_out and not self.killed:
            raise subprocess.TimeoutExpired("synthetic", timeout)
        self.returncode = 124 if self.killed else 0
        return "\n".join(GOOD_LINES) + "\n", ""

    def wait(self, timeout: float | None = None) -> int:
        if timeout is not None:
            assert timeout == 5.0
        assert self.returncode is not None
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = 124


def test_t116_44_supervised_demo_eurusd_symbol_preflight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Перевірити два дозволи, strict output, kill/reap та LGE bridge."""
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "run_network_child"
        for node in tree.body
    )
    assert "run_demo_network(credentials=verified)" in source
    assert "sdk_offline_preflight" in source
    assert "supervise_network_child" in source
    assert "production_changes=0" in source

    denied = 0
    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_probe:
            with pytest.raises(PermissionError):
                tcp_probe.connect(("192.0.2.1", 443))
        denied += 1

        system_env = {
            key: system_value for key in (
                "SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP",
                "VIRTUAL_ENV", "PYTHONIOENCODING",
            ) if (system_value := os.environ.get(key))
        }
        invalid_envs = (
            system_env,
            {**system_env, APPROVAL_VARIABLE: "WRONG"},
            {**system_env, T11632_APPROVAL_VARIABLE: "X",
             APPROVAL_VARIABLE: APPROVAL_VALUE},
            {**system_env, T11643_APPROVAL_VARIABLE: "X",
             APPROVAL_VARIABLE: APPROVAL_VALUE},
        )
        for candidate in invalid_envs:
            assert not approved(
                confirmation=CLI_CONFIRMATION,
                environment=candidate,
            )
            denied += 1

        permitted_env = {**system_env, APPROVAL_VARIABLE: APPROVAL_VALUE}
        for bad_cli in (None, "", "WRONG", "READONLY_DEMO_46368962"):
            assert not approved(confirmation=bad_cli, environment=permitted_env)
            denied += 1
        assert approved(
            confirmation=CLI_CONFIRMATION,
            environment=permitted_env,
        )
        assert not approved(
            confirmation=CLI_CONFIRMATION,
            environment=permitted_env,
            operator_confirmations=True,
        )
        denied += 1

        for orders, wsp in (
            ("", WSP_CONFIRMATION),
            (ORDERS_CONFIRMATION, ""),
            ("OFF", WSP_CONFIRMATION),
            (ORDERS_CONFIRMATION, "STOPPED"),
        ):
            with pytest.raises(PermissionError):
                prepare_child_environment(
                    CREDENTIALS, environment=permitted_env,
                    orders_confirmation=orders, wsp_confirmation=wsp,
                )
            denied += 1

        with pytest.raises(PermissionError):
            prepare_child_environment(
                CREDENTIALS, environment=system_env,
                orders_confirmation=ORDERS_CONFIRMATION,
                wsp_confirmation=WSP_CONFIRMATION,
            )
        denied += 1

        child_env = prepare_child_environment(
            CREDENTIALS, environment=permitted_env,
            orders_confirmation=ORDERS_CONFIRMATION,
            wsp_confirmation=WSP_CONFIRMATION,
        )
        assert approved(
            confirmation=CLI_CONFIRMATION,
            environment=child_env,
            operator_confirmations=True,
        )
        assert child_env["CTRADER_ACCESS_TOKEN"] == CREDENTIALS.access_token
        assert T11632_APPROVAL_VARIABLE not in child_env
        assert T11643_APPROVAL_VARIABLE not in child_env
        assert all(child_env[name] for name in CREDENTIAL_VARIABLES)
        if os.name == "nt":
            assert child_env["SystemRoot"]

        for changed in (
            {APPROVAL_VARIABLE: ""},
            {ORDERS_VARIABLE: ""},
            {WSP_VARIABLE: ""},
            {"CTRADER_ACCESS_TOKEN": ""},
            {T11632_APPROVAL_VARIABLE: "WRONG"},
        ):
            with pytest.raises(PermissionError):
                supervise_network_child({**child_env, **changed})
            denied += 1

        for bad_lines in (
            GOOD_LINES[:4],
            (*GOOD_LINES, "EXTRA=LEAK"),
            ("demo_api_account_id=999", *GOOD_LINES[1:]),
            (GOOD_LINES[0], "real_eurusd_symbol_id=0", *GOOD_LINES[2:]),
            (GOOD_LINES[0], "real_eurusd_symbol_id=-3", *GOOD_LINES[2:]),
            (GOOD_LINES[0], "real_eurusd_symbol_id=0001", *GOOD_LINES[2:]),
            (GOOD_LINES[0], "real_eurusd_symbol_id=9223372036854775808",
             *GOOD_LINES[2:]),
            (GOOD_LINES[0], GOOD_LINES[1], "request_policy=WRONG",
             *GOOD_LINES[3:]),
        ):
            assert verified_symbol_id(synthetic_result(
                stdout="\n".join(bad_lines) + "\n"
            )) is None
            denied += 1

        for bad_result in (
            synthetic_result(stderr="SECRET SHOULD NOT LEAK"),
            synthetic_result(returncode=1),
            synthetic_result(hard_timeout=True),
            synthetic_result(reaped=False),
        ):
            assert verified_symbol_id(bad_result) is None
            denied += 1
        assert verified_symbol_id(synthetic_result()) == SYMBOL_ID
        assert safe_failure_code(synthetic_result(
            hard_timeout=True
        )) == "HARD_PROCESS_TIMEOUT"
        assert safe_failure_code(synthetic_result(
            returncode=1, stdout="failure_code=DISCOVERY_TIMEOUT\n"
        )) == "DISCOVERY_TIMEOUT"
        assert safe_failure_code(synthetic_result(
            returncode=1, stdout="failure_code=FAKE_SECRET\n"
        )) == "CHILD_PROCESS_FAILED"
        denied += 1

        popen_calls: list[dict[str, Any]] = []
        fake_child = FakeProcess()

        def fake_popen(_command: list[str], **kwargs: Any) -> FakeProcess:
            assert "--network-child" in _command
            assert "--confirm" in _command
            assert kwargs["shell"] is False
            assert kwargs["env"] == child_env
            assert kwargs["stdin"] == subprocess.DEVNULL
            popen_calls.append(kwargs)
            return fake_child

        normal = supervise_network_child(child_env, popen=fake_popen)
        assert verified_symbol_id(normal) == SYMBOL_ID
        assert fake_child.timeouts == [75]
        assert len(popen_calls) == 1
        timeout_child = FakeProcess(timed_out=True)
        timeout_result = supervise_network_child(
            child_env, popen=lambda _command, **_kwargs: timeout_child
        )
        assert timeout_child.killed
        assert timeout_result.hard_timeout
        assert timeout_result.reaped
        assert safe_failure_code(timeout_result) == "HARD_PROCESS_TIMEOUT"
        assert timeout_child.timeouts == [75, 5.0]

        launch_count = 0

        def forbidden_child(_credentials: BridgedCredentials) -> int:
            nonlocal launch_count
            launch_count += 1
            raise AssertionError("мережевий child не можна запускати в pytest")

        # Звичайний offline-run жодного разу не торкається до SDK Client.
        assert main(
            ["--offline-preflight"], environment=system_env,
            sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
            child_runner=forbidden_child,
        ) == 0
        assert OFFLINE_SUCCESS in capsys.readouterr().out
        assert launch_count == 0

        for invalid_arguments in (
            [], ["--live"], ["--demo-network", "--network-child"],
        ):
            with redirect_stderr(StringIO()):
                with pytest.raises(SystemExit) as parse_error:
                    main(invalid_arguments, environment=system_env)
            assert parse_error.value.code == 2
            denied += 1

        for arguments, candidate in (
            (["--demo-network"], permitted_env),
            (["--demo-network", "--confirm", "WRONG"], permitted_env),
            (["--demo-network", "--confirm", CLI_CONFIRMATION], system_env),
            (["--network-child", "--confirm", CLI_CONFIRMATION], permitted_env),
        ):
            with pytest.raises(PermissionError):
                main(
                    arguments, environment=candidate,
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                    child_runner=forbidden_child,
                )
            denied += 1

        # Child-режим з правильним env може викликати лише явний mock.
        child_seen: list[BridgedCredentials] = []

        def fake_child_runner(value: BridgedCredentials) -> int:
            child_seen.append(value)
            return 0

        assert main(
            ["--network-child", "--confirm", CLI_CONFIRMATION],
            environment=child_env, child_runner=fake_child_runner,
        ) == 0
        assert len(child_seen) == 1
        assert child_seen[0].access_token == CREDENTIALS.access_token
        assert launch_count == 0

        # В реальній функції T116-32 network замінений на синтетичний mock.
        passed_credentials: list[tuple[str, str, str]] = []

        def fake_discovery(*, credentials: tuple[str, str, str]) -> int:
            passed_credentials.append(credentials)
            return 0

        with patch(
            "tests.roadmap116.t116_44_supervised_demo_eurusd_symbol.run_demo_network",
            side_effect=fake_discovery,
        ):
            assert run_network_child(CREDENTIALS) == 0
        assert passed_credentials == [(
            CREDENTIALS.client_id, CREDENTIALS.client_secret,
            CREDENTIALS.access_token,
        )]

        # Parent happy path: усе замінено на mock, TCP залишається забороненим.
        parent_env = {**system_env, APPROVAL_VARIABLE: APPROVAL_VALUE}
        with patch.dict(os.environ, parent_env, clear=True):
            assert main(
                ["--demo-network", "--confirm", CLI_CONFIRMATION],
                ask=lambda message: (
                    ORDERS_CONFIRMATION if "Orders" in message
                    else WSP_CONFIRMATION
                ),
                ask_password=lambda _message: "T11644_FAKE_PASSWORD",
                credential_reader=lambda _password: CREDENTIALS,
                runner=lambda _environment: synthetic_result(),
                sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
            ) == 0
        parent_output = capsys.readouterr().out
        assert PARENT_SUCCESS in parent_output
        assert f"real_eurusd_symbol_id={SYMBOL_ID}" in parent_output
        assert CREDENTIALS.access_token not in parent_output
        assert "T11644_FAKE_PASSWORD" not in parent_output

        # Несподівані винятки не мають розкривати значення credentials.
        def unsafe_failure(_value: object) -> BridgedCredentials:
            raise RuntimeError("SYNTHETIC_SECRET_SHOULD_NOT_APPEAR")

        with patch.dict(os.environ, parent_env, clear=True):
            with pytest.raises(PermissionError) as secret_failure:
                main(
                    ["--demo-network", "--confirm", CLI_CONFIRMATION],
                    ask=lambda message: (
                        ORDERS_CONFIRMATION if "Orders" in message
                        else WSP_CONFIRMATION
                    ),
                    ask_password=lambda _message: "SYNTHETIC_PASSWORD",
                    credential_reader=unsafe_failure,
                    sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
                )
            assert "SYNTHETIC_SECRET" not in str(secret_failure.value)
            denied += 1

            def failed_supervisor(_environment: object) -> SupervisedResult:
                raise RuntimeError("SYNTHETIC_SECRET_SHOULD_NOT_APPEAR")

            assert main(
                ["--demo-network", "--confirm", CLI_CONFIRMATION],
                ask=lambda message: (
                    ORDERS_CONFIRMATION if "Orders" in message
                    else WSP_CONFIRMATION
                ),
                ask_password=lambda _message: "SYNTHETIC_PASSWORD",
                credential_reader=lambda _password: CREDENTIALS,
                runner=failed_supervisor,
                sdk_check=lambda: "VERIFIED_NO_EXTERNAL_NETWORK",
            ) == 1
            assert "SYNTHETIC_SECRET" not in capsys.readouterr().out
            denied += 1

    print("T116-44 TEST_ONLY | supervised DEMO EURUSD offline preflight")
    print(f"negative_scenarios_denied={denied}")
    print("request_order=APPLICATION_ACCOUNT_SYMBOLS")
    print("outbound_guard=T116-29_EXISTING_THREE_LEVELS")
    print("supervisor_timeout_seconds=75")
    print("credentials=SYNTHETIC_ONLY")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-44=GREEN_OFFLINE_SYMBOL_NETWORK_PREFLIGHT")
