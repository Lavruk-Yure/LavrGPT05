# -*- coding: utf-8 -*-
"""Canonical Ukrainian Replay terminology check for Algorithm Workspace."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation_policy import translation_override_for_key  # noqa: E402


INITIAL_BALANCE_KEY = "AlgorithmWorkspaceReplayDialog.lblInitialBalance"

EXPECTED_UK = {
    "AlgorithmWorkspaceWindow.replaySyntheticAccount": "Віртуальний рахунок Replay",
    "AlgorithmWorkspaceWindow.lblReplayEquity": "Кошти Replay:",
    "AlgorithmWorkspaceWindow.lblReplayRealizedPnl": "Закритий PnL:",
    "AlgorithmWorkspaceWindow.lblReplayBalance": "Баланс Replay:",
    "AlgorithmWorkspaceWindow.lblReplaySummaryEquity": "Кошти Replay:",
    "AlgorithmWorkspaceReplayDialog.grpAccount": "Віртуальний рахунок Replay",
    INITIAL_BALANCE_KEY: "Початковий баланс Replay, USD:",
}


def main() -> None:
    strings_path = PROJECT_ROOT / "lang" / "strings.json"
    strings_before = strings_path.read_bytes()

    for key, expected in EXPECTED_UK.items():
        assert translation_override_for_key(key, "uk") == expected

    area_source = (PROJECT_ROOT / "core" / "algorithm_workspace_area.py").read_text(
        encoding="utf-8"
    )
    replay_dialog_source = (
        PROJECT_ROOT / "core" / "algorithm_workspace_replay_dialog.py"
    ).read_text(encoding="utf-8")

    assert '"AlgorithmWorkspaceWindow.lblReplayEquity": "Replay equity:"' in area_source
    assert (
        '"AlgorithmWorkspaceWindow.lblReplayBalance": "Replay balance:"'
        in area_source
    )
    assert (
        '"AlgorithmWorkspaceWindow.lblReplaySummaryEquity": "Replay equity:"'
        in area_source
    )
    assert '"Virtual Replay account"' in replay_dialog_source
    assert '"Initial Replay balance, USD:"' in replay_dialog_source

    assert strings_path.read_bytes() == strings_before

    print("Algorithm Workspace Replay terminology result")
    print("  virtual_replay_account=True")
    print("  replay_funds_term=True")
    print("  replay_balance_term=True")
    print("  closed_pnl_term=True")
    print("  initial_replay_balance_term=True")
    print("  english_fallbacks_unambiguous=True")
    print("  strings_json_manual_edit=False")
    print("ALGORITHM_WORKSPACE_REPLAY_TERMINOLOGY_CHECK=OK")


if __name__ == "__main__":
    main()
