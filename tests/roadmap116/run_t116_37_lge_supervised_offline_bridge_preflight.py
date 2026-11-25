"""T116-37 TEST_ONLY — offline subprocess та контроль передачі env."""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_26_process_watchdog import SupervisedResult
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VALUE,
    NETWORK_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_37_lge_supervised_offline_bridge import (
    CHILD_MARKER,
    CHILD_MODULE,
    READY_MARKER,
    BridgedCredentials,
    BridgeRejected,
    assert_offline_environment,
    check_machine,
    child_result_valid,
    main,
    offline_child,
    prepare_child_environment,
    run_offline_child,
    safe_report,
)

SOURCE = Path(__file__).with_name("t116_37_lge_supervised_offline_bridge.py")
SYNTHETIC_VALUES = (
    "T11637_TEST_ONLY_ID_CANARY",
    "T11637_TEST_ONLY_SECRET_CANARY",
    "T11637_TEST_ONLY_TOKEN_CANARY",
)


def fake_credentials(_password: str) -> BridgedCredentials:
    """Не читати LGE.conf/tokens.json у pytest."""
    return BridgedCredentials(*SYNTHETIC_VALUES)


def sample_result(
    *,
    stdout: str,
    returncode: int = 0,
    reaped: bool = True,
    hard_timeout: bool = False,
    stderr: str = "",
) -> SupervisedResult:
    return SupervisedResult(
        returncode=returncode,
        reaped=reaped,
        hard_timeout=hard_timeout,
        stdout=stdout,
        stderr=stderr,
    )


def test_t116_37_lge_supervised_offline_bridge_preflight() -> None:
    """Реальний subprocess лише синтетичний; TCP заблокований."""
    parsed = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in parsed.body if isinstance(node, ast.FunctionDef)
    }
    expected_names = {"prepare_child_environment", "run_offline_child", "offline_child"}
    assert expected_names <= function_names
    assert 't116_33_main(["--offline-preflight"]' in SOURCE.read_text(encoding="utf-8")
    assert "--demo-network" not in SOURCE.read_text(encoding="utf-8")
    assert "run_demo_network(" not in SOURCE.read_text(encoding="utf-8")

    denied = 0
    source_env = {"EXISTING_SAFE_KEY": "keep", "CTRADER_CLIENT_ID": "stale"}
    # На Windows _overlapped потребує SystemRoot навіть в офлайн-child.
    if os.name == "nt":
        source_env["SystemRoot"] = os.environ["SystemRoot"]
    child_env = prepare_child_environment(
        "TEST_ONLY_PASSWORD",
        credential_reader=fake_credentials,
        environment=source_env,
    )
    assert source_env["CTRADER_CLIENT_ID"] == "stale"
    if os.name == "nt":
        assert child_env["SystemRoot"] == os.environ["SystemRoot"]
    assert all(
        child_env[key] == value
        for key, value in zip(CREDENTIAL_VARIABLES, SYNTHETIC_VALUES, strict=True)
    )
    assert child_env["EXISTING_SAFE_KEY"] == "keep"
    assert NETWORK_APPROVAL_VARIABLE not in child_env
    assert "CANARY" not in repr(BridgedCredentials(*SYNTHETIC_VALUES))
    assert_offline_environment(child_env)

    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_probe:
            with pytest.raises(PermissionError):
                tcp_probe.connect(("192.0.2.7", 443))
        denied += 1

        # T116-37 не повинен дозволяти навіть синтетичну мережеву спробу.
        for broken_env in (
            {},
            {"CTRADER_CLIENT_ID": "one"},
            {**child_env, NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE},
            {**child_env, "CTRADER_CLIENT_SECRET": ""},
            {**child_env, "CTRADER_ACCESS_TOKEN": "  "},
        ):
            with pytest.raises(BridgeRejected):
                assert_offline_environment(broken_env)
            denied += 1

        for base_env in (
            {**source_env, NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE},
        ):
            with pytest.raises(BridgeRejected):
                prepare_child_environment(
                    "TEST_ONLY_PASSWORD",
                    credential_reader=fake_credentials,
                    environment=base_env,
                )
            denied += 1

        with pytest.raises(BridgeRejected):
            prepare_child_environment(
                "TEST_ONLY_PASSWORD",
                credential_reader=Mock(return_value=None),
                environment=source_env,
            )
        denied += 1

        # Child справжній, але виконує тільки T116-33 --offline-preflight.
        actual_popen = subprocess.Popen
        with patch(
            "tests.roadmap116.t116_37_lge_supervised_offline_bridge."
            "subprocess.Popen",
            wraps=actual_popen,
        ) as popen_spy:
            supervised = run_offline_child(child_env)
        assert child_result_valid(supervised)
        assert supervised.returncode == 0
        assert supervised.reaped and not supervised.hard_timeout
        assert popen_spy.call_count == 1
        assert popen_spy.call_args.args[0] == [
            sys.executable,
            "-m",
            CHILD_MODULE,
            "--offline-child",
        ]
        assert popen_spy.call_args.kwargs["shell"] is False
        assert popen_spy.call_args.kwargs["env"] == child_env
        assert popen_spy.call_args.kwargs["stdin"] == subprocess.DEVNULL
        assert "--demo-network" not in popen_spy.call_args.args[0]
        assert all(value not in supervised.stdout for value in SYNTHETIC_VALUES)
        assert all(value not in supervised.stderr for value in SYNTHETIC_VALUES)

        # Завислий child обов'язково зупиняється та reap у межах watchdog.
        class TimeoutChild:
            def __init__(self) -> None:
                self.killed = False
                self.communications = 0

            def communicate(self, *, timeout: float) -> tuple[str, str]:
                self.communications += 1
                if self.communications == 1:
                    raise subprocess.TimeoutExpired(cmd="TEST_ONLY", timeout=timeout)
                return "", ""

            def kill(self) -> None:
                self.killed = True

            def poll(self) -> int | None:
                return 124 if self.killed else None

            def wait(self, *, timeout: float | None = None) -> int:
                assert timeout is None or timeout == 5.0
                assert self.killed
                return 124

        timeout_child = TimeoutChild()
        with patch(
            "tests.roadmap116.t116_37_lge_supervised_offline_bridge."
            "subprocess.Popen",
            return_value=timeout_child,
        ) as timeout_popen:
            timed_out = run_offline_child(child_env)
        assert timed_out.hard_timeout and timed_out.reaped
        assert timed_out.returncode == 124
        assert timeout_child.killed and timeout_child.communications == 2
        assert timeout_popen.call_count == 1
        denied += 1

        # Валідація результату — жодного довір'я довільному stdout child.
        green_stdout = supervised.stdout
        for fake_child in (
            sample_result(stdout=""),
            sample_result(stdout=green_stdout, returncode=1),
            sample_result(stdout=green_stdout, reaped=False),
            sample_result(stdout=green_stdout, hard_timeout=True),
            sample_result(stdout=green_stdout + CHILD_MARKER + "\n"),
            sample_result(stdout=green_stdout.replace("credentials_mapped=3/3", "")),
            sample_result(
                stdout=green_stdout.replace(
                    f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
                    "demo_api_account_id=111",
                )
            ),
            sample_result(
                stdout=green_stdout.replace(
                    "network_launch_authorized=NO", "network_launch_authorized=YES"
                )
            ),
            sample_result(
                stdout=green_stdout.replace(
                    "real_broker_requests=0", "real_broker_requests=1"
                )
            ),
        ):
            assert not child_result_valid(fake_child)
            denied += 1

        # Секретний текст у дочірньому stderr/stdout не повторюємо у звіті.
        injected_secret = SYNTHETIC_VALUES[1]
        redacted_report = check_machine(
            "TEST_ONLY_PASSWORD",
            credential_reader=fake_credentials,
            environment=source_env,
            child_runner=lambda _: sample_result(
                stdout="failure=" + injected_secret,
                stderr=injected_secret,
                returncode=1,
            ),
        )
        assert "T116-37=NOT_READY_OFFLINE" in redacted_report
        assert injected_secret not in redacted_report
        denied += 1

        # Виняток із reader може містити секрет: не друкувати його.
        with patch(
            "tests.roadmap116.t116_37_lge_supervised_offline_bridge."
            "run_offline_child",
            side_effect=AssertionError("Не запускати child при помилці reader"),
        ):
            unreadable = check_machine(
                "TEST_ONLY_PASSWORD",
                credential_reader=lambda _: (_ for _ in ()).throw(
                    RuntimeError(injected_secret)
                ),
                environment=source_env,
            )
        assert injected_secret not in unreadable
        assert "T116-37=NOT_READY_OFFLINE" in unreadable
        denied += 1

        # Child не повинен приймати невідомі прапорці (включно з --live).
        for invalid_args in (
            [],
            ["--demo-network"],
            ["--live"],
            ["--offline-child", "--confirm"],
        ):
            with redirect_stderr(StringIO()):
                with pytest.raises(SystemExit):
                    main(invalid_args)
            denied += 1

        # Режим check-machine без реальних credentials запускаємо із fake.
        with redirect_stdout(StringIO()) as output:
            rc = main(
                ["--check-machine"],
                ask_password=lambda _: "TEST_ONLY_PASSWORD",
                checker=lambda _: check_machine(
                    "TEST_ONLY_PASSWORD",
                    credential_reader=fake_credentials,
                    environment=source_env,
                    child_runner=lambda _: supervised,
                ),
            )
        assert rc == 0 and READY_MARKER in output.getvalue()
        assert all(value not in output.getvalue() for value in SYNTHETIC_VALUES)

        for password_reader in (
            lambda _: "",
            lambda _: (_ for _ in ()).throw(EOFError()),
        ):
            with redirect_stdout(StringIO()) as output:
                rc = main(
                    ["--check-machine"],
                    ask_password=password_reader,
                    checker=lambda _: safe_report(
                        succeeded=False, failure_code="OFFLINE_REJECTED"
                    ),
                )
            assert rc == 2
            assert READY_MARKER not in output.getvalue()
            denied += 1

        # Пряме offline-child без credentials fail-closed.
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(StringIO()) as output:
                assert offline_child() == 2
            assert "OFFLINE_CHILD_REJECTED" in output.getvalue()
        denied += 1

    print("T116-37 TEST_ONLY | LGE to supervised OFFLINE child integration")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"negative_scenarios_denied={denied}")
    print("credential_source=T116-36_READONLY_LGE_BRIDGE")
    print("child_contract=T116-33_OFFLINE_PREFLIGHT_ONLY")
    print("child_process=SYNTHETIC_STARTED_AND_REAPED")
    print("supervisor_timeout_seconds=75")
    print("credentials_mapping=SYNTHETIC_EXPLICIT_ENV_ONLY")
    print("credentials_values=NOT_LOGGED")
    print("external_tcp=BLOCKED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-37=GREEN_OFFLINE_SUPERVISED_CREDENTIALS_BRIDGE")
