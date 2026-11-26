"""T116-42 TEST_ONLY — синтетична DEMO AccountList child-регресія."""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.roadmap116.t116_26_process_watchdog import SupervisedResult
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VALUE,
    NETWORK_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import BridgeRejected
from tests.roadmap116.t116_42_supervised_account_list_offline import (
    CHILD_LINES,
    READY_MARKER,
    child_result_valid,
    main,
    prepare_synthetic_child_environment,
    run_offline_child,
)

SOURCE = Path(__file__).with_name("t116_42_supervised_account_list_offline.py")


def synthetic_result(
    *,
    returncode: int = 0,
    hard_timeout: bool = False,
    reaped: bool = True,
    stdout: str = "\n".join(CHILD_LINES) + "\n",
    stderr: str = "",
) -> SupervisedResult:
    """Підготувати незалежний синтетичний результат supervisor."""
    return SupervisedResult(
        returncode=returncode,
        hard_timeout=hard_timeout,
        reaped=reaped,
        stdout=stdout,
        stderr=stderr,
    )


def test_t116_42_supervised_account_list_offline_preflight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Перевірити справжній child, fail-closed та відсутність DEMO network."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imports = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        name.startswith(("core", "runtime", "ctrader_open_api")) for name in imports
    )
    assert not any(
        isinstance(node, ast.Constant) and node.value == "--demo-network"
        for node in ast.walk(tree)
    )

    synthetic_environment = prepare_synthetic_child_environment(os.environ)
    assert NETWORK_APPROVAL_VARIABLE not in synthetic_environment
    assert all(synthetic_environment.get(name) for name in CREDENTIAL_VARIABLES)
    assert not any(
        synthetic_environment[name] == os.environ.get(name)
        for name in CREDENTIAL_VARIABLES
        if os.environ.get(name)
    )
    if os.name == "nt":
        assert synthetic_environment.get("SystemRoot")

    result = run_offline_child(synthetic_environment)
    assert child_result_valid(result)
    assert result.stdout.splitlines() == list(CHILD_LINES)
    assert result.returncode == 0 and result.reaped
    assert result.stderr == ""
    denied = 0

    for replacement in (
        synthetic_result(returncode=1),
        synthetic_result(returncode=2),
        synthetic_result(hard_timeout=True),
        synthetic_result(reaped=False),
        synthetic_result(stdout=""),
        synthetic_result(stdout="\n".join(CHILD_LINES[:-1])),
        synthetic_result(stdout="\n".join(CHILD_LINES) + "\nUNEXPECTED"),
        synthetic_result(stdout="\n".join(CHILD_LINES + (CHILD_LINES[-1],))),
        synthetic_result(
            stdout="\n".join(CHILD_LINES).replace(
                "account_identity=SYNTHETIC_DEMO_ONLY", "account_identity=LIVE"
            )
        ),
        synthetic_result(stderr="hidden-debug-trace"),
    ):
        assert not child_result_valid(replacement)
        denied += 1

    for field_name in CREDENTIAL_VARIABLES:
        invalid_environment = dict(synthetic_environment)
        invalid_environment[field_name] = "INVALID"
        with pytest.raises(PermissionError):
            run_offline_child(invalid_environment)
        denied += 1

    with pytest.raises(PermissionError):
        prepare_synthetic_child_environment(
            {
                **os.environ,
                NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE,
            }
        )
    denied += 1

    with pytest.raises(BridgeRejected):
        run_offline_child(
            {
                **synthetic_environment,
                NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE,
            }
        )
    denied += 1

    for invalid_arguments in (
        ["--demo-network"],
        ["--check-machine"],
        ["--offline-preflight", "--offline-child"],
        [],
    ):
        with pytest.raises(SystemExit):
            main(invalid_arguments)
        denied += 1
    capsys.readouterr()

    class TimeoutChild:
        """Симуляція залежного child, що потребує примусового kill."""

        def __init__(self) -> None:
            self.killed = False

        def communicate(self, *, timeout: float) -> tuple[str, str]:
            if not self.killed:
                raise subprocess.TimeoutExpired("TEST_ONLY", timeout)
            return "", ""

        def kill(self) -> None:
            self.killed = True

        def poll(self) -> int | None:
            return 124 if self.killed else None

        def wait(self, timeout: float | None = None) -> int:
            assert timeout is None or timeout > 0
            assert self.killed
            return 124

    timed_out_process = TimeoutChild()
    timeout_result = run_offline_child(
        synthetic_environment,
        popen=Mock(return_value=timed_out_process),
    )
    assert timeout_result.hard_timeout
    assert timeout_result.reaped and timed_out_process.killed
    assert not child_result_valid(timeout_result)
    denied += 1

    # Після timeout або malformed child жодного raw-stdout у звіті.
    def invalid_runner(_environment: object) -> SupervisedResult:
        return synthetic_result(stderr="SENSITIVE_TOKEN_IN_TRACE")

    assert (
        main(
            ["--offline-preflight"],
            environment={},
            runner=invalid_runner,
        )
        == 2
    )
    printed = capsys.readouterr().out
    assert "SENSITIVE_TOKEN_IN_TRACE" not in printed
    assert "T116-42=NOT_READY_OFFLINE" in printed
    denied += 1

    assert (
        main(
            ["--offline-preflight"],
            environment=os.environ,
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert READY_MARKER in printed
    assert "real_broker_requests=0" in printed
    assert "network_launch_authorized=NO" in printed
    assert "credentials_values=NOT_LOGGED" in printed
    assert "T11642_SYNTHETIC_ACCESS_TOKEN" not in printed

    print("T116-42 TEST_ONLY | supervised synthetic AccountList OFFLINE")
    print(f"negative_scenarios_denied={denied}")
    print("request_order=APPLICATION_AUTH_ACCOUNT_LIST")
    print("account_identity=SYNTHETIC_DEMO_ONLY")
    print("child_process=SYNTHETIC_STARTED_AND_REAPED")
    print("supervisor_timeout_seconds=75")
    print("existing_guard=T116-40_SCOPED_T116-29_RESTORED")
    print("credentials_values=NOT_LOGGED")
    print("sdk_client_constructor=NOT_CALLED")
    print("external_tcp=BLOCKED")
    print("real_identity_pair=NOT_QUERIED_NO_NETWORK")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print(READY_MARKER)
