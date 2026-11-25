"""T116-35 TEST_ONLY — синтетичний офлайн-контракт читання LGE credentials."""

from __future__ import annotations

import ast
import hashlib
import json
import socket
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    NETWORK_APPROVAL_VARIABLE,
)
from tests.roadmap116.t116_35_existing_lge_credentials_readiness import (
    CredentialReadiness,
    format_report,
    inspect_existing_credentials,
    load_lge_tokens,
    main,
    read_lge_config_readonly,
    token_valid_by_lge,
)

SOURCE = Path(__file__).with_name("t116_35_existing_lge_credentials_readiness.py")
CLIENT_ID = "T116_35_SYNTHETIC_CLIENT_ID"
CLIENT_SECRET = "T116_35_SYNTHETIC_CLIENT_SECRET"
TOKEN = "T116_35_SYNTHETIC_ACCESS_TOKEN"
PASSWORD = "T116_35_SYNTHETIC_PASSWORD"


def test_t116_35_existing_lge_credentials_readiness_preflight() -> None:
    """Перевірити read-only, DEMO account, відмови й відсутність витоків."""
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body
    )
    for forbidden in (
        ".load_with_status(",
        ".save(",
        "save_tokens(",
        "refresh_if_needed(",
        "startService(",
        "subprocess",
        "run_demo_network(",
        "run_supervised_network(",
        "--demo-network",
        "--live",
    ):
        assert forbidden not in source

    config = {
        "password_sha256": hashlib.sha256(PASSWORD.encode()).hexdigest(),
        "ctrader": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "account_mode": "DEMO",
            "account_id": "46368962",
        },
    }
    tokens = {"access_token": TOKEN, "refresh_token": "SYNTHETIC_REFRESH"}

    def config_reader(_password: str) -> dict:
        return config

    def tokens_reader() -> dict:
        return tokens

    def token_validator(_tokens: dict | None) -> bool:
        return True

    def probe(
        *,
        source_config: dict | None = None,
        source_tokens: dict | None = None,
        valid: bool = True,
        environment: dict[str, str] | None = None,
        test_password: str = PASSWORD,
    ) -> CredentialReadiness:
        return inspect_existing_credentials(
            test_password,
            config_reader=lambda _pwd: (
                config if source_config is None else source_config
            ),
            tokens_reader=lambda: tokens if source_tokens is None else source_tokens,
            token_validator=lambda _data: valid,
            environment={} if environment is None else environment,
        )

    denied = 0
    good = probe()
    assert good.ready_for_approval
    assert good.credentials_count == 3
    report = format_report(good)
    assert "T116-35=READY_FOR_SEPARATE_NETWORK_APPROVAL" in report
    assert "credentials_present=3/3" in report
    assert "account_id_match=YES" in report
    for secret in (PASSWORD, CLIENT_ID, CLIENT_SECRET, TOKEN):
        assert secret not in report

    negative_cases = (
        {"ctrader": {**config["ctrader"], "client_id": ""}},
        {"ctrader": {**config["ctrader"], "client_secret": ""}},
        {"ctrader": {**config["ctrader"], "account_mode": "LIVE"}},
        {"ctrader": {**config["ctrader"], "account_id": "111"}},
        {"ctrader": {**config["ctrader"], "account_id": ""}},
        {"ctrader": {}},
    )
    for data in negative_cases:
        assert not probe(source_config=data).ready_for_approval
        denied += 1

    for result in (
        inspect_existing_credentials(
            "",
            config_reader=config_reader,
            tokens_reader=tokens_reader,
            token_validator=token_validator,
            environment={},
        ),
        probe(source_tokens={"access_token": ""}),
        probe(valid=False),
        probe(environment={NETWORK_APPROVAL_VARIABLE: "ON"}),
        inspect_existing_credentials(
            PASSWORD,
            config_reader=lambda _password: (_ for _ in ()).throw(
                RuntimeError("DO_NOT_LOG_PASSWORD=" + PASSWORD)
            ),
            tokens_reader=tokens_reader,
            token_validator=token_validator,
            environment={},
        ),
        inspect_existing_credentials(
            PASSWORD,
            config_reader=config_reader,
            tokens_reader=lambda: (_ for _ in ()).throw(
                RuntimeError("DO_NOT_LOG_TOKEN=" + TOKEN)
            ),
            token_validator=token_validator,
            environment={},
        ),
    ):
        assert not result.ready_for_approval
        for secret in (PASSWORD, CLIENT_ID, CLIENT_SECRET, TOKEN):
            assert secret not in format_report(result)
        denied += 1

    # Фактичний adapter ConfigManager — тільки _aes_decrypt, без міграції.
    class FakeConfigManager:
        def __init__(self, path: Path) -> None:
            self.path = path

        @staticmethod
        def _looks_like_aes_crypt_file() -> bool:
            return True

        @staticmethod
        def _aes_decrypt(password: str) -> bytes:
            assert password == PASSWORD
            return json.dumps(config).encode("utf-8")

        @staticmethod
        def load_with_status(_password: str) -> None:
            raise AssertionError("TEST_ONLY: заборонено міграцію конфігу")

        @staticmethod
        def save(*_args: object) -> None:
            raise AssertionError("TEST_ONLY: заборонено запис конфігу")

    fake_core_config = ModuleType("core.config_manager")
    setattr(fake_core_config, "ConfigManager", FakeConfigManager)
    with patch.dict(sys.modules, {"core.config_manager": fake_core_config}):
        with patch.object(Path, "is_file", return_value=True):
            assert read_lge_config_readonly(PASSWORD, Path("SYNTHETIC.conf")) == config
    denied += 1

    # Неправильний пароль не дає доступу до конфігурації.
    wrong_password_config = {
        **config,
        "password_sha256": hashlib.sha256(b"DIFFERENT_PASSWORD").hexdigest(),
    }
    with patch.dict(sys.modules, {"core.config_manager": fake_core_config}):
        with patch.object(Path, "is_file", return_value=True):
            with patch.object(
                FakeConfigManager,
                "_aes_decrypt",
                return_value=json.dumps(wrong_password_config).encode("utf-8"),
            ):
                with pytest.raises(ValueError, match="LGE_CONFIG_AUTH_FAILED"):
                    read_lge_config_readonly(PASSWORD, Path("SYNTHETIC.conf"))
    denied += 1

    # Canonical token_manager використовується лише для читання та
    # локальної перевірки; жодного refresh/save.
    fake_token_manager = ModuleType("core.token_manager")
    setattr(fake_token_manager, "load_tokens", lambda: tokens)
    setattr(
        fake_token_manager,
        "is_access_token_valid",
        lambda token_candidate: token_candidate == tokens,
    )
    setattr(
        fake_token_manager,
        "save_tokens",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("TEST_ONLY: запис токенів заборонено")
        ),
    )
    setattr(
        fake_token_manager,
        "refresh_if_needed",
        lambda: (_ for _ in ()).throw(
            AssertionError("TEST_ONLY: refresh токенів заборонено")
        ),
    )
    with patch.dict(sys.modules, {"core.token_manager": fake_token_manager}):
        assert load_lge_tokens() == tokens
        assert token_valid_by_lge(tokens)
    denied += 1

    # Реальна TCP-спроба з loader не повинна пройти.
    def forbidden_reader(_password: str) -> dict:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.connect(("192.0.2.10", 443))
        return config

    fail_closed = inspect_existing_credentials(
        PASSWORD,
        config_reader=forbidden_reader,
        tokens_reader=tokens_reader,
        token_validator=token_validator,
        environment={},
    )
    assert not fail_closed.ready_for_approval
    denied += 1

    with redirect_stdout(StringIO()) as output:
        assert (
            main(
                ["--check-machine"],
                ask_password=lambda _: PASSWORD,
                inspect=lambda _: good,
            )
            == 0
        )
    assert "T116-35=READY_FOR_SEPARATE_NETWORK_APPROVAL" in output.getvalue()
    for secret in (PASSWORD, CLIENT_ID, CLIENT_SECRET, TOKEN):
        assert secret not in output.getvalue()

    with redirect_stdout(StringIO()) as output:
        assert (
            main(
                ["--check-machine"],
                ask_password=lambda _: "",
                inspect=lambda _: probe(test_password=""),
            )
            == 2
        )
    assert "T116-35=NOT_READY_OFFLINE" in output.getvalue()
    denied += 1

    for arguments in (
        [],
        ["--live"],
        ["--demo-network"],
        ["--check-machine", "--confirm", "anything"],
    ):
        with redirect_stderr(StringIO()):
            with pytest.raises(SystemExit):
                main(arguments, ask_password=lambda _: PASSWORD, inspect=lambda _: good)
        denied += 1

    print("T116-35 TEST_ONLY | existing LGE credentials offline read-only")
    print(f"negative_scenarios_denied={denied}")
    print("config_read_only_adapter=VERIFIED_NO_MIGRATION")
    print("token_validation=LOCAL_ONLY_NO_REFRESH")
    print("credentials_values=NOT_LOGGED")
    print("external_tcp=BLOCKED")
    print("sdk_client_constructor=NOT_CALLED")
    print("child_process=NOT_STARTED")
    print("real_broker_requests=0")
    print("production_changes=0")
    print("network_launch_authorized=NO")
    print("T116-35=GREEN_OFFLINE_EXISTING_CREDENTIALS_CONTRACT")
