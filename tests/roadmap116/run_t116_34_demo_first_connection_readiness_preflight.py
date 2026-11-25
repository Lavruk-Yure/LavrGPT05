"""T116-34 TEST_ONLY — перевірка offline readiness і захисту секретів."""

from __future__ import annotations

import ast
import socket
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_34_demo_first_connection_readiness import (
    SDK_ABSENT,
    SDK_READY,
    format_report,
    inspect_readiness,
    main,
)

SOURCE = Path(__file__).with_name("t116_34_demo_first_connection_readiness.py")


def test_t116_34_demo_first_connection_readiness_preflight() -> None:
    """Відхилити приховану мережу та не допустити витік credentials."""
    source = SOURCE.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in parsed.body)
    assert "run_demo_network(" not in source
    assert "run_supervised_network(" not in source
    assert "subprocess" not in source
    assert "startService(" not in source
    assert "--demo-network" not in source
    assert "--live" not in source

    private_values = (
        "SECRET_TEST_ONLY_CLIENT_IDENTIFIER",
        "SECRET_TEST_ONLY_APPLICATION_SECRET",
        "SECRET_TEST_ONLY_ACCESS_TOKEN",
    )
    environment = dict(zip(CREDENTIAL_VARIABLES, private_values, strict=True))
    denied = 0

    with external_tcp_denied():
        def checked_sdk() -> str:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                with pytest.raises(PermissionError):
                    probe.connect(("192.0.2.10", 443))
            return SDK_READY

        ready = inspect_readiness(environment=environment, check_sdk=checked_sdk)
        assert ready.ready_for_approval
        report = format_report(ready)
        assert "credential_fields_present=3/3" in report
        assert "network_launch_authorized=NO" in report
        for secret in private_values:
            assert secret not in report
        with redirect_stdout(StringIO()) as output:
            assert main(["--check-machine"], environment=environment,
                        check_sdk=checked_sdk) == 0
        assert "T116-34=READY_FOR_SEPARATE_APPROVAL" in output.getvalue()

        for bad_environment, sdk_status in (
            ({}, SDK_READY),
            ({CREDENTIAL_VARIABLES[0]: "  "}, SDK_READY),
            (environment, SDK_ABSENT),
            ({**environment, NETWORK_APPROVAL_VARIABLE: "TEST_ONLY"}, SDK_READY),
        ):
            with redirect_stdout(StringIO()) as output:
                assert main(["--check-machine"], environment=bad_environment,
                            check_sdk=lambda status=sdk_status: status) == 2
            assert "T116-34=NOT_READY_OFFLINE" in output.getvalue()
            denied += 1

        def forbidden_sdk() -> str:
            socket.create_connection(("192.0.2.10", 443))
            return SDK_READY

        with redirect_stdout(StringIO()) as output:
            assert main(["--check-machine"], environment=environment,
                        check_sdk=forbidden_sdk) == 2
        assert "sdk_offline_preflight=SDK_PREFLIGHT_FAILED" in output.getvalue()
        denied += 1

        for argv in ([], ["--live"], ["--demo-network"],
                     ["--check-machine", "--confirm", "TEST_ONLY"]):
            with redirect_stderr(StringIO()):
                with pytest.raises(SystemExit):
                    main(argv, environment=environment, check_sdk=checked_sdk)
            denied += 1

        # Навіть якщо launcher T116-33 присутній, його тут не викликають.
        with patch(
            "tests.roadmap116.t116_33_supervised_demo_readonly_discovery."
            "run_supervised_network",
            side_effect=AssertionError("TEST_ONLY: child заборонено"),
        ) as network_launch:
            with redirect_stdout(StringIO()):
                assert main(["--check-machine"], environment=environment,
                            check_sdk=checked_sdk) == 0
            assert network_launch.call_count == 0

    print("T116-34 TEST_ONLY | offline local readiness contract")
    print(f"negative_scenarios_denied={denied}")
    print("credentials_values=NOT_LOGGED")
    print("external_tcp=BLOCKED")
    print("sdk_client_constructor=NOT_CALLED")
    print("child_process=NOT_STARTED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-34=GREEN_OFFLINE_READINESS_CONTRACT")
