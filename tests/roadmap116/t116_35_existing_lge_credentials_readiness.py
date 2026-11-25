"""T116-35 TEST_ONLY — читання наявних credentials LGE без мережі й запису.

Не викликає ConfigManager.load_with_status: цей метод може автоматично
зберегти мігрований LGE.conf. Тільки локальне дешифрування у пам'яті.
Токен перевіряється за локальним правилом LGE, а не через сервер cTrader.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.roadmap116.t116_22_standalone_demo_reader import DEMO_API_ACCOUNT_ID
from tests.roadmap116.t116_30_offline_symbol_preparation import external_tcp_denied
from tests.roadmap116.t116_32_demo_network_readonly_discovery import (
    NETWORK_APPROVAL_VARIABLE,
)


@dataclass(frozen=True, slots=True)
class CredentialReadiness:
    """Безпечний результат: без значень credentials і шляхів до файлів."""

    config_readable: bool
    tokens_readable: bool
    client_fields_count: int
    access_token_present: bool
    token_valid_locally: bool
    demo_mode: bool
    account_id_match: bool
    approval_env_present: bool

    @property
    def credentials_count(self) -> int:
        return self.client_fields_count + int(self.access_token_present)

    @property
    def ready_for_approval(self) -> bool:
        return (
            self.config_readable
            and self.tokens_readable
            and self.credentials_count == 3
            and self.token_valid_locally
            and self.demo_mode
            and self.account_id_match
            and not self.approval_env_present
        )


def read_lge_config_readonly(password: str, path: Path | None = None) -> dict:
    """Використати AES-decrypt ConfigManager, але без міграції й save."""
    from core.app_paths import ROOT_CONF_PATH
    from core.config_manager import ConfigManager

    manager = ConfigManager(ROOT_CONF_PATH if path is None else path)
    # noinspection PyProtectedMember
    if not manager.path.is_file() or not manager._looks_like_aes_crypt_file():
        raise ValueError("LGE_CONFIG_UNREADABLE")
    # noinspection PyProtectedMember
    payload = json.loads(manager._aes_decrypt(password).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("LGE_CONFIG_INVALID")
    stored_hash = payload.get("password_sha256")
    actual_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if not isinstance(stored_hash, str) or not hmac.compare_digest(
        actual_hash, stored_hash
    ):
        raise ValueError("LGE_CONFIG_AUTH_FAILED")
    return payload


def load_lge_tokens() -> dict | None:
    """Використати тільки штатне локальне читання tokens.json."""
    from core.token_manager import load_tokens

    return load_tokens()


def token_valid_by_lge(tokens: dict | None) -> bool:
    """Локальний expires_at, без refresh-token OAuth і HTTP."""
    from core.token_manager import is_access_token_valid

    return is_access_token_valid(tokens)


def inspect_existing_credentials(
    password: str,
    *,
    config_reader: Callable[[str], dict] = read_lge_config_readonly,
    tokens_reader: Callable[[], dict | None] = load_lge_tokens,
    token_validator: Callable[[dict | None], bool] = token_valid_by_lge,
    environment: Mapping[str, str] | None = None,
) -> CredentialReadiness:
    """Дослідити джерела в TCP-забороні, перетворити секрети на статуси."""
    env = os.environ if environment is None else environment
    approval_present = NETWORK_APPROVAL_VARIABLE in env
    config_data: dict[str, Any] | None = None
    token_data: dict[str, Any] | None = None
    config_ok = False
    tokens_ok = False
    locally_valid = False

    with external_tcp_denied():
        if password:
            try:
                loaded_config = config_reader(password)
                if isinstance(loaded_config, dict):
                    config_data = loaded_config
                    config_ok = True
            # noinspection PyBroadException
            except Exception:  # noqa
                pass  # TEST_ONLY: ні traceback, ні секрети з помилки не друкувати

        try:
            loaded_tokens = tokens_reader()
            if isinstance(loaded_tokens, dict):
                token_data = loaded_tokens
                tokens_ok = True
        # noinspection PyBroadException
        except Exception:  # noqa
            pass  # TEST_ONLY: безпечний код статусу замість тексту винятку

        if tokens_ok:
            try:
                locally_valid = bool(token_validator(token_data))
            # noinspection PyBroadException
            except Exception:  # noqa
                locally_valid = False

    ctrader = config_data.get("ctrader") if config_data is not None else None
    settings = ctrader if isinstance(ctrader, dict) else {}
    id_ok = bool(str(settings.get("client_id") or "").strip())
    secret_ok = bool(str(settings.get("client_secret") or "").strip())
    access_present = bool(
        str(token_data.get("access_token") or "").strip()
        if token_data is not None
        else False
    )
    mode_demo = str(settings.get("account_mode") or "").strip().upper() == "DEMO"
    account_match = str(settings.get("account_id") or "").strip() == str(
        DEMO_API_ACCOUNT_ID
    )
    return CredentialReadiness(
        config_readable=config_ok,
        tokens_readable=tokens_ok,
        client_fields_count=int(id_ok) + int(secret_ok),
        access_token_present=access_present,
        token_valid_locally=locally_valid,
        demo_mode=mode_demo,
        account_id_match=account_match,
        approval_env_present=approval_present,
    )


def format_report(readiness: CredentialReadiness) -> str:
    """Тільки агреговані ознаки, без password, token, client_id або path."""
    verdict = (
        "READY_FOR_SEPARATE_NETWORK_APPROVAL"
        if readiness.ready_for_approval
        else "NOT_READY_OFFLINE"
    )
    return "\n".join(
        (
            "T116-35 TEST_ONLY | existing LGE credentials NO NETWORK",
            f"demo_api_account_id={DEMO_API_ACCOUNT_ID}",
            f"lge_config_readable={'YES' if readiness.config_readable else 'NO'}",
            f"tokens_readable={'YES' if readiness.tokens_readable else 'NO'}",
            f"client_fields_present={readiness.client_fields_count}/2",
            f"access_token_present={'YES' if readiness.access_token_present else 'NO'}",
            f"credentials_present={readiness.credentials_count}/3",
            "token_validity=LOCAL_EXPIRY_ONLY_"
            + ("VALID" if readiness.token_valid_locally else "INVALID_OR_EXPIRED"),
            f"account_mode_demo={'YES' if readiness.demo_mode else 'NO'}",
            f"account_id_match={'YES' if readiness.account_id_match else 'NO'}",
            "network_approval_env="
            + (
                "PRESENT_CLEAR_BEFORE_NEXT_STEP"
                if readiness.approval_env_present
                else "UNSET"
            ),
            "orders_off=NOT_VERIFIED_OPERATOR_REQUIRED",
            "wsp_stopped=NOT_VERIFIED_OPERATOR_REQUIRED",
            "credentials_values=NOT_LOGGED",
            "config_and_tokens_written=NO",
            "external_tcp=BLOCKED",
            "sdk_client_constructor=NOT_CALLED",
            "child_process=NOT_STARTED",
            "real_broker_requests=0",
            "production_changes=0",
            "network_launch_authorized=NO",
            f"T116-35={verdict}",
        )
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    ask_password: Callable[[str], str] = getpass.getpass,
    inspect: Callable[[str], CredentialReadiness] = inspect_existing_credentials,
) -> int:
    """Єдиний режим --check-machine: один прихований запит пароля LGE."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check-machine", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        password = ask_password("Пароль входу LGE (не відображається): ")
    except (EOFError, KeyboardInterrupt):
        password = ""
    result = inspect(password)
    print(format_report(result))
    return 0 if result.ready_for_approval else 2


if __name__ == "__main__":
    raise SystemExit(main())
