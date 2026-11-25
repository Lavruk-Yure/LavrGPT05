"""T116-36 TEST_ONLY — офлайн-контракт LGE credentials → T116-32 guard."""

from __future__ import annotations

import ast
import socket
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    CREDENTIAL_VARIABLES,
    NETWORK_APPROVAL_VALUE,
    NETWORK_APPROVAL_VARIABLE,
    NETWORK_CONFIRMATION,
    authorized_credentials,
)
from tests.roadmap116.t116_36_lge_credentials_launcher_bridge import (
    BridgedCredentials,
    BridgeRejected,
    check_machine,
    main,
    make_launcher_environment,
    read_credentials_for_bridge,
)

SOURCE = Path(__file__).with_name("t116_36_lge_credentials_launcher_bridge.py")
PASSWORD = "T116_36_SYNTHETIC_PASSWORD"
CLIENT_ID = "T116_36_SYNTHETIC_CLIENT_ID"
CLIENT_SECRET = "T116_36_SYNTHETIC_CLIENT_SECRET"
ACCESS_TOKEN = "T116_36_SYNTHETIC_ACCESS_TOKEN"


def test_t116_36_lge_credentials_launcher_bridge_preflight() -> None:
    """Перевірити синтетичну передачу й усі fail-closed межі без мережі."""
    source = SOURCE.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "main"
        for node in parsed.body
    )
    for forbidden in (
        "run_supervised_network(",
        "run_demo_network(",
        "startService(",
        "subprocess.",
        "Popen(",
        ".load_with_status(",
        ".save(",
        "save_tokens(",
        "refresh_if_needed(",
        "--demo-network",
        "--live",
    ):
        assert forbidden not in source

    config = {
        "ctrader": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "account_mode": "DEMO",
            "account_id": "46368962",
        }
    }
    tokens = {"access_token": ACCESS_TOKEN, "refresh_token": "SYNTHETIC"}
    original_env = {"EXISTING_SAFE_KEY": "keep", "CTRADER_CLIENT_ID": "stale"}

    def bridge(
        *,
        password: str = PASSWORD,
        source_config: Any = ...,
        source_tokens: Any = ...,
        locally_valid: bool = True,
        environment: dict[str, str] | None = None,
    ) -> BridgedCredentials:
        return read_credentials_for_bridge(
            password,
            config_reader=lambda _: config if source_config is ... else source_config,
            tokens_reader=lambda: tokens if source_tokens is ... else source_tokens,
            token_validator=lambda _: locally_valid,
            environment={} if environment is None else environment,
        )

    denied = 0
    with external_tcp_denied():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            with pytest.raises(PermissionError):
                sock.connect(("192.0.2.1", 443))

        credentials = bridge()
        assert repr(credentials) == "BridgedCredentials(REDACTED)"
        assert credentials.client_id == CLIENT_ID
        assert credentials.client_secret == CLIENT_SECRET
        assert credentials.access_token == ACCESS_TOKEN
        child_env = make_launcher_environment(
            credentials,
            environment=original_env,
        )
        assert child_env["EXISTING_SAFE_KEY"] == "keep"
        assert original_env["CTRADER_CLIENT_ID"] == "stale"
        assert NETWORK_APPROVAL_VARIABLE not in child_env
        assert tuple(child_env[name] for name in CREDENTIAL_VARIABLES) == (
            CLIENT_ID,
            CLIENT_SECRET,
            ACCESS_TOKEN,
        )

        # Без дозволу мережі T116-32 має заблокувати навіть повні credentials.
        with pytest.raises(PermissionError):
            authorized_credentials(
                confirmation=None,
                environment=child_env,
            )
        denied += 1
        with pytest.raises(PermissionError):
            authorized_credentials(
                confirmation=NETWORK_CONFIRMATION,
                environment=child_env,
            )
        denied += 1

        # Тільки в пам'яті перевіряємо точний контракт читача T116-32.
        synthetic_approved_env = {
            **child_env,
            NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE,
        }
        assert authorized_credentials(
            confirmation=NETWORK_CONFIRMATION,
            environment=synthetic_approved_env,
        ) == (CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN)
        # Жодного запуску Client(), Reactor або subprocess.

        negative = (
            {"password": ""},
            {"source_config": None},
            {"source_config": {}},
            {"source_config": {"ctrader": "bad"}},
            {
                "source_config": {
                    "ctrader": {**config["ctrader"], "account_mode": "LIVE"}
                }
            },
            {"source_config": {"ctrader": {**config["ctrader"], "account_id": "111"}}},
            {"source_config": {"ctrader": {**config["ctrader"], "client_id": ""}}},
            {"source_config": {"ctrader": {**config["ctrader"], "client_secret": ""}}},
            {"source_config": {"ctrader": {**config["ctrader"], "client_id": 123}}},
            {"source_tokens": None},
            {"source_tokens": {}},
            {"source_tokens": {"access_token": ""}},
            {"source_tokens": {"access_token": 123}},
            {"locally_valid": False},
            {"environment": {NETWORK_APPROVAL_VARIABLE: ""}},
        )
        for parameters in negative:
            with pytest.raises(BridgeRejected):
                bridge(**parameters)
            denied += 1

        with pytest.raises(BridgeRejected):
            make_launcher_environment(
                credentials,
                environment={NETWORK_APPROVAL_VARIABLE: NETWORK_APPROVAL_VALUE},
            )
        denied += 1

        for case_config, case_tokens in (
            (config, tokens),
            (config, {}),
        ):
            report = check_machine(
                PASSWORD,
                config_reader=lambda _: case_config,
                tokens_reader=lambda: case_tokens,
                token_validator=lambda _: True,
                environment={},
            )
            assert "credentials_values=NOT_LOGGED" in report
            assert "network_launch_authorized=NO" in report
            assert "child_process=NOT_STARTED" in report
            for secret in (PASSWORD, CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN):
                assert secret not in report

        safe_success = check_machine(
            PASSWORD,
            config_reader=lambda _: config,
            tokens_reader=lambda: tokens,
            token_validator=lambda _: True,
            environment={},
        )
        assert "credentials_mapped=3/3" in safe_success
        assert "T116-36=READY_FOR_SEPARATE_LAUNCHER_INTEGRATION" in safe_success

        for faulty_reader in (
            lambda _: (_ for _ in ()).throw(RuntimeError("SECRET=" + CLIENT_SECRET)),
            lambda _: (_ for _ in ()).throw(PermissionError("PASSWORD=" + PASSWORD)),
        ):
            report = check_machine(
                PASSWORD,
                config_reader=faulty_reader,
                tokens_reader=lambda: tokens,
                token_validator=lambda _: True,
                environment={},
            )
            assert "T116-36=NOT_READY_OFFLINE" in report
            assert PASSWORD not in report
            assert CLIENT_SECRET not in report
            denied += 1

        for argument_list in ([], ["--demo-network"], ["--live"]):
            with redirect_stderr(StringIO()):
                with pytest.raises(SystemExit):
                    main(argument_list, ask_password=lambda _: PASSWORD)
            denied += 1

        with redirect_stdout(StringIO()) as output:
            result = main(
                ["--check-machine"],
                ask_password=lambda _: PASSWORD,
                check=lambda _: safe_success,
            )
        assert result == 0
        assert "network_launch_authorized=NO" in output.getvalue()
        for secret in (PASSWORD, CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN):
            assert secret not in output.getvalue()

    print("T116-36 TEST_ONLY | LGE to DEMO launcher offline bridge")
    print(f"negative_scenarios_denied={denied}")
    print("lge_credentials_source=T116-35_READONLY")
    print("launcher_guard=T116-32_AUTHORIZED_CREDENTIALS_CONTRACT")
    print("credentials_mapping=SYNTHETIC_IN_MEMORY_ONLY")
    print("real_credentials=NOT_READ_DURING_PYTEST")
    print("credentials_values=NOT_LOGGED")
    print("external_tcp=BLOCKED")
    print("sdk_client_constructor=NOT_CALLED")
    print("child_process=NOT_STARTED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-36=GREEN_OFFLINE_LGE_TO_LAUNCHER_BRIDGE")
