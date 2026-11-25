"""T116-33 TEST_ONLY — повністю офлайновий контракт першого DEMO запуску."""

from __future__ import annotations

import ast
import os
import socket
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_26_process_watchdog import (
    SUPERVISOR_TIMEOUT_SECONDS,
    SupervisedResult,
)
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VALUE,
    NETWORK_APPROVAL_VARIABLE,
    NETWORK_CONFIRMATION,
)
from tests.roadmap116.t116_33_supervised_demo_readonly_discovery import (
    CHILD_GREEN,
    CHILD_MODULE,
    RESULT_GREEN,
    RESULT_OFFLINE,
    main,
    run_supervised_network,
    sdk_offline_preflight,
    summarize_child,
)

SOURCE = Path(__file__).with_name("t116_33_supervised_demo_readonly_discovery.py")


def fake_result(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    hard_timeout: bool = False,
    reaped: bool = True,
) -> SupervisedResult:
    return SupervisedResult(
        returncode=returncode,
        hard_timeout=hard_timeout,
        reaped=reaped,
        stdout=stdout,
        stderr=stderr,
    )


def test_t116_33_supervised_demo_readonly_discovery_preflight() -> None:
    """Без реального Client або subprocess перевірити всі межі launcher."""
    source = SOURCE.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "main"
        for node in parsed.body
    )
    assert "supervise_process" in source
    assert "authorized_credentials" in source
    assert "run_demo_network(" not in source
    assert "ProtoOANewOrderReq" not in source
    assert CHILD_MODULE.startswith("tests.roadmap116.")
    assert SUPERVISOR_TIMEOUT_SECONDS == 75.0

    blocked = 0
    good_env = {
        NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE,
        **dict(
            zip(
                CREDENTIAL_VARIABLES,
                ("TEST_ONLY_ID", "TEST_ONLY_SECRET", "TEST_ONLY_TOKEN"),
                strict=True,
            )
        ),
    }

    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            with pytest.raises(PermissionError):
                probe.connect(("192.0.2.10", 443))

        with patch(
            "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
            "run_supervised_network",
            side_effect=AssertionError("Subprocess під час offline тесту"),
        ) as network_launch:
            # Некоректний CLI повинен завершуватися через argparse.
            for arguments in (
                [],
                ["--live"],
                ["--offline-preflight", "--confirm", "WRONG"],
            ):
                with redirect_stderr(StringIO()):
                    with pytest.raises(SystemExit):
                        main(arguments, environment=good_env)
                blocked += 1

            # Відсутні дозволи/credentials повинні давати PermissionError.
            for arguments, environment in (
                (["--demo-network"], good_env),
                (["--demo-network", "--confirm", "WRONG"], good_env),
                (["--demo-network", "--confirm", NETWORK_CONFIRMATION], {}),
                (
                    ["--demo-network", "--confirm", NETWORK_CONFIRMATION],
                    {NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE},
                ),
            ):
                with pytest.raises(PermissionError):
                    main(arguments, environment=environment)
                blocked += 1
            assert network_launch.call_count == 0

            with patch(
                "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
                "sdk_offline_preflight",
                return_value="VERIFIED_NO_EXTERNAL_NETWORK",
            ):
                with pytest.raises(PermissionError):
                    main(
                        ["--demo-network", "--confirm", NETWORK_CONFIRMATION],
                        environment=good_env,
                    )
                blocked += 1
            assert network_launch.call_count == 0

            with redirect_stdout(StringIO()) as output:
                assert main(["--offline-preflight"], environment={}) == 0
            assert RESULT_OFFLINE in output.getvalue()
            assert "real_broker_requests=0" in output.getvalue()
            assert network_launch.call_count == 0

        # Навіть два дозволи не запускають child без перевіреного SDK.
        with (
            patch.dict(os.environ, good_env, clear=True),
            patch(
                "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
                "sdk_offline_preflight",
                return_value="NOT_INSTALLED_LOCAL_RUNNER",
            ),
            patch(
                "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
                "run_supervised_network",
                side_effect=AssertionError("SDK відсутній, запуск заборонено"),
            ) as denied_launch,
        ):
            with pytest.raises(RuntimeError):
                main(["--demo-network", "--confirm", NETWORK_CONFIRMATION])
            assert denied_launch.call_count == 0
        blocked += 1

        # Позитивний шлях моделюємо лише mock — справжній child не створюємо.
        with (
            patch.dict(os.environ, good_env, clear=True),
            patch(
                "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
                "sdk_offline_preflight",
                return_value="VERIFIED_NO_EXTERNAL_NETWORK",
            ),
            patch(
                "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
                "run_supervised_network",
                return_value=0,
            ) as approved_launch,
        ):
            assert main(["--demo-network", "--confirm", NETWORK_CONFIRMATION]) == 0
            assert approved_launch.call_count == 1

        # Child cmd допускає тільки модуль T116-32 з двома підтвердженнями.
        with patch(
            "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
            "supervise_process",
            return_value=fake_result(
                stdout=(
                    f"demo_api_account_id={DEMO_API_ACCOUNT_ID}\n"
                    "real_eurusd_symbol_id=17\n"
                    f"{CHILD_GREEN}\n"
                ),
            ),
        ) as supervisor:
            with redirect_stdout(StringIO()) as output:
                assert run_supervised_network() == 0
            assert RESULT_GREEN in output.getvalue()
            assert "real_eurusd_symbol_id=17" in output.getvalue()
            assert supervisor.call_count == 1
            command = supervisor.call_args.args[0]
            assert command == [
                sys.executable,
                "-m",
                CHILD_MODULE,
                "--demo-network",
                "--confirm",
                NETWORK_CONFIRMATION,
            ]
            assert supervisor.call_args.kwargs["hard_timeout_seconds"] == 75.0

        for simulated_result in (
            fake_result(returncode=1, stdout="failure_code=SDK_SEND_FAILED"),
            fake_result(returncode=124, hard_timeout=True),
            fake_result(reaped=False),
            fake_result(stdout=f"real_eurusd_symbol_id=17\n{CHILD_GREEN}"),
            fake_result(stdout=f"{CHILD_GREEN}"),
            fake_result(
                stdout=(
                    "demo_api_account_id=111\n"
                    "real_eurusd_symbol_id=17\n"
                    f"{CHILD_GREEN}\n"
                )
            ),
        ):
            with redirect_stdout(StringIO()) as output:
                assert summarize_child(simulated_result) == 1
            assert "T116-33=FAILED_DEMO_READONLY_DISCOVERY" in output.getvalue()
            blocked += 1

        # Жодного перенесення raw stderr, токенів або незнайомих рядків.
        with redirect_stdout(StringIO()) as output:
            assert (
                summarize_child(
                    fake_result(
                        returncode=1,
                        stderr="TEST_ONLY_SECRET: TEST_ONLY_TOKEN",
                    )
                )
                == 1
            )
        assert "TEST_ONLY_SECRET" not in output.getvalue()
        assert "TEST_ONLY_TOKEN" not in output.getvalue()
        blocked += 1

    print("T116-33 TEST_ONLY | supervised DEMO first network offline preflight")
    print(f"demo_api_account_id={DEMO_API_ACCOUNT_ID}")
    print(f"negative_scenarios_denied={blocked}")
    print("supervisor_timeout_seconds=75")
    print("child_module=T116-32_EXISTING_READONLY_LAUNCHER")
    print("sdk_offline_preflight=" + sdk_offline_preflight())
    print("external_tcp=BLOCKED")
    print("sdk_client_constructor=NOT_CALLED")
    print("child_process=NOT_STARTED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(RESULT_OFFLINE)
