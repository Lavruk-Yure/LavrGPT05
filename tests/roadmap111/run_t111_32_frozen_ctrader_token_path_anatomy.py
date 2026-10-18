# -*- coding: utf-8 -*-
"""
T111-32 — Frozen cTrader Token Path Anatomy — TEST_ONLY.

Мета:
- статично зафіксувати, як token_manager і cTrader account-list probe
  формують шлях до tokens/tokens.json;
- довести відсутність frozen-aware runtime root через sys.executable;
- не виконувати broker requests;
- не змінювати production.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOKEN_MANAGER = PROJECT_ROOT / "core" / "token_manager.py"
ACCOUNT_LIST_PROBE = PROJECT_ROOT / "core" / "ctrader_account_list_probe.py"

TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = False


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    token_manager_text = TOKEN_MANAGER.read_text(encoding="utf-8")
    account_list_text = ACCOUNT_LIST_PROBE.read_text(encoding="utf-8")

    token_manager_uses_dunder_file_root = (
        'PROJECT_ROOT = Path(__file__).resolve().parents[1]'
        in token_manager_text
    )
    token_manager_default_tokens_path = (
        'DEFAULT_TOKENS_PATH = PROJECT_ROOT / "tokens" / "tokens.json"'
        in token_manager_text
    )
    token_manager_has_env_override = all(
        needle in token_manager_text
        for needle in (
            'os.getenv("TOKENS_PATH", "")',
            "return Path(env_path).expanduser()",
        )
    )

    account_list_probe_uses_dunder_file_root = (
        "root_dir = Path(__file__).resolve().parent.parent"
        in account_list_text
    )
    account_list_probe_direct_tokens_path = (
        'root_dir / "tokens" / "tokens.json"'
        in account_list_text
    )

    account_list_probe_uses_token_manager = any(
        needle in account_list_text
        for needle in (
            "from core.token_manager import",
            "from .token_manager import",
            "get_tokens_path(",
        )
    )

    frozen_needles = (
        'getattr(sys, "frozen"',
        "getattr(sys, 'frozen'",
        "sys.executable",
        "_MEIPASS",
    )
    token_manager_has_frozen_root_support = any(
        needle in token_manager_text
        for needle in frozen_needles
    )
    account_list_has_frozen_root_support = any(
        needle in account_list_text
        for needle in frozen_needles
    )
    frozen_executable_root_support = (
        token_manager_has_frozen_root_support
        or account_list_has_frozen_root_support
    )

    _require(
        token_manager_uses_dunder_file_root,
        "token_manager uses __file__ project root",
    )
    _require(
        token_manager_default_tokens_path,
        "token_manager default tokens/tokens.json path",
    )
    _require(
        token_manager_has_env_override,
        "token_manager TOKENS_PATH env override",
    )
    _require(
        account_list_probe_uses_dunder_file_root,
        "account-list probe uses __file__ root",
    )
    _require(
        account_list_probe_direct_tokens_path,
        "account-list probe builds tokens path directly",
    )
    _require(
        not account_list_probe_uses_token_manager,
        "account-list probe bypasses token_manager",
    )
    _require(
        not frozen_executable_root_support,
        "frozen runtime root support is absent",
    )

    print("T111-32 TEST_ONLY")
    print("verdict=FROZEN_CTRADER_TOKEN_PATH_BROKEN")
    print(
        "token_manager_uses_dunder_file_root="
        f"{token_manager_uses_dunder_file_root}"
    )
    print(
        "token_manager_default_tokens_path="
        f"{token_manager_default_tokens_path}"
    )
    print(
        "token_manager_has_env_override="
        f"{token_manager_has_env_override}"
    )
    print(
        "account_list_probe_uses_dunder_file_root="
        f"{account_list_probe_uses_dunder_file_root}"
    )
    print(
        "account_list_probe_direct_tokens_path="
        f"{account_list_probe_direct_tokens_path}"
    )
    print(
        "account_list_probe_uses_token_manager="
        f"{account_list_probe_uses_token_manager}"
    )
    print(
        "frozen_executable_root_support="
        f"{frozen_executable_root_support}"
    )
    print(f"TEST_ONLY={TEST_ONLY}")
    print(f"broker_requests={BROKER_REQUESTS}")
    print(
        "broker_execution_attempted="
        f"{BROKER_EXECUTION_ATTEMPTED}"
    )
    print(f"production_logic_changed={PRODUCTION_LOGIC_CHANGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
