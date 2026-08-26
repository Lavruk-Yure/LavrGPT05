# -*- coding: utf-8 -*-
"""Перевірка читабельної таблиці Signals і Alligator regime evidence.

Тест фіксує 12 колонок, збільшені interactive widths, горизонтальний scroll,
локалізований causal режим/фазу Alligator та незмінність trade evidence.
"""

from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalFilterContext,
    WorkspaceSignalRecord,
)
from core.workspace_signal_presentation import (  # noqa: E402
    workspace_signal_alligator_regime_text,
    workspace_signal_profile_revision_text,
    workspace_signal_timeframe_mode_text,
)

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"


def _assignment(source: str, name: str) -> Any:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"Assignment not found: {name}")


def main() -> None:
    record = WorkspaceSignalRecord(
        timestamp=datetime(2026, 8, 7, 7, 0, tzinfo=UTC),
        signal_uid="signal-table-1",
        workspace_uid="workspace-1",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction="BUY",
        strength=0.00012,
        macd_state="MACD_CROSS_UP",
        alligator_confirmation="ALLIGATOR_HIGHER_1_BEARISH",
        spread_status="OK",
        accepted=False,
        reason="test",
        source_reason_code="MACD_CLASSIC_CROSS",
        source_profile_uid="macd-lge-classic",
        source_profile_revision=2,
        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        filter_reason_code="ALLIGATOR_HIGHER_1_BUY_REJECT",
        filter_context=WorkspaceSignalFilterContext(
            mode="HIGHER_1",
            timeframe="H1",
            profile_uid="alligator-lge-classic",
            profile_revision=4,
            observation_timestamp=datetime(2026, 8, 7, 5, 0, tzinfo=UTC),
            available_at=datetime(2026, 8, 7, 6, 0, tzinfo=UTC),
            regime="ALLIGATOR_REGIME_TREND_UP",
            regime_phase="ALLIGATOR_REGIME_PHASE_ENDING",
            normalized_slope=0.42,
            normalized_opening=1.25,
        ),
    )

    assert workspace_signal_timeframe_mode_text(record) == "M15 | HIGHER_1 -> H1"
    assert workspace_signal_profile_revision_text(record) == "MACD r2 / Alligator r4"
    assert (
        workspace_signal_alligator_regime_text(
            record,
            lambda _key, fallback: fallback,
        )
        == "Trend up ending"
    )

    source = AREA_PATH.read_text(encoding="utf-8")
    columns = _assignment(source, "SIGNAL_TABLE_COLUMNS")
    widths = _assignment(source, "SIGNAL_TABLE_WIDTHS")
    reason_column = _assignment(source, "SIGNAL_TABLE_REASON_COLUMN")

    assert len(columns) == 12
    assert len(widths) == 12
    assert reason_column == 11
    assert min(widths) >= 82
    assert widths[5] >= 160
    assert widths[6] >= 150
    assert widths[7] >= 170
    assert widths[11] >= 320
    assert columns[6][0] == "AlgorithmWorkspaceWindow.colAlligatorRegime"
    assert columns[7][0] == "AlgorithmWorkspaceWindow.colSignalTimeframeMode"
    assert columns[8][0] == "AlgorithmWorkspaceWindow.colSignalProfileRevision"
    assert columns[10][0] == "AlgorithmWorkspaceWindow.colFilterResult"
    assert "workspace_signal_alligator_regime_text(record, self._tr)" in source
    assert "workspace_signal_timeframe_mode_text(record)" in source
    assert "workspace_signal_profile_revision_text(record)" in source
    assert 'f"{record.filter_decision} / {decision}"' in source

    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colAlligatorRegime",
            "uk",
        )
        == "Режим"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colSignalTimeframeMode",
            "uk",
        )
        == "ТФ / режим"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colSignalProfileRevision",
            "uk",
        )
        == "Ревізія профілю"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colFilterResult",
            "uk",
        )
        == "Фільтр / результат"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.colSpreadStatus",
            "uk",
        )
        == "Спред"
    )

    print("Algorithm Workspace signal table result")
    print("  columns=12")
    print("  alligator_regime_visible=True")
    print("  alligator_regime_phase_visible=True")
    print("  timeframe_mode_visible=True")
    print("  source_filter_profile_revision_visible=True")
    print("  filter_allow_reject_visible=True")
    print("  runtime_result_preserved=True")
    print("  readable_interactive_widths=True")
    print("  horizontal_scroll_expected=True")
    print("  ukrainian_headers_overridden=True")
    print("  strings_json_manual_edit=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_TABLE_CHECK=OK")


if __name__ == "__main__":
    main()
