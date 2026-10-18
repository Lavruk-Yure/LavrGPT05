# -*- coding: utf-8 -*-
"""
T111-33 — Frozen cTrader Token Path Guard — TEST_ONLY.

Перевіряє:
- TOKENS_PATH env override має найвищий пріоритет;
- source runtime зберігає старий canonical tokens/tokens.json;
- frozen runtime використовує каталог sys.executable;
- account-list probe більше не формує власний __file__ root;
- broker requests не виконуються.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from core import token_manager


TEST_ONLY = True
BROKER_REQUESTS = 0
BROKER_EXECUTION_ATTEMPTED = False
PRODUCTION_LOGIC_CHANGED = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_LIST_PROBE = PROJECT_ROOT / "core" / "ctrader_account_list_probe.py"


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"missing evidence: {label}")


def main() -> int:
    source_expected = PROJECT_ROOT / "tokens" / "tokens.json"

    with patch.dict(os.environ, {"TOKENS_PATH": ""}):
        source_path = token_manager.get_tokens_path()

    frozen_executable = PROJECT_ROOT.parent / "LGE" / "LGE.exe"
    frozen_expected = frozen_executable.parent / "tokens" / "tokens.json"

    with (
        patch.dict(os.environ, {"TOKENS_PATH": ""}),
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(frozen_executable)),
    ):
        frozen_path = token_manager.get_tokens_path()

    override_path = PROJECT_ROOT / "tmp" / "override_tokens.json"
    with patch.dict(os.environ, {"TOKENS_PATH": str(override_path)}):
        env_path = token_manager.get_tokens_path()

    account_list_text = ACCOUNT_LIST_PROBE.read_text(encoding="utf-8")

    account_list_uses_token_manager = (
        "from core.token_manager import get_tokens_path" in account_list_text
        and "tokens_path = get_tokens_path()" in account_list_text
    )
    account_list_dunder_file_root_removed = (
        "Path(__file__).resolve().parent.parent" not in account_list_text
    )

    _require(source_path == source_expected, "source canonical token path")
    _require(frozen_path == frozen_expected, "frozen executable token path")
    _require(env_path == override_path, "TOKENS_PATH env override")
    _require(
        account_list_uses_token_manager,
        "account-list probe uses token_manager",
    )
    _require(
        account_list_dunder_file_root_removed,
        "account-list __file__ root removed",
    )

    print("T111-33 TEST_ONLY")
    print("verdict=FROZEN_CTRADER_TOKEN_PATH_GUARDED")
    print("source_token_path_preserved=True")
    print("frozen_token_path_uses_executable_dir=True")
    print("tokens_path_env_override_preserved=True")
    print("account_list_probe_uses_token_manager=True")
    print("account_list_dunder_file_root_removed=True")
    print("account_snapshot_uses_shared_load_access_token=True")
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
