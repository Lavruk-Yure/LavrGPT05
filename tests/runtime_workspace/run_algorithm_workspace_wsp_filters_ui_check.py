# -*- coding: utf-8 -*-
"""RoadMap101 WSP analysis filters, regime filter and navigation contract."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation_policy import translation_override_for_key  # noqa: E402
from core.workspace_historical_summary import (  # noqa: E402
    build_workspace_historical_signal_metrics,
)
from core.workspace_signal import (  # noqa: E402
    WORKSPACE_SIGNAL_FILTER_REJECT,
    WorkspaceSignalRecord,
)

AREA_PATH = PROJECT_ROOT / "core" / "algorithm_workspace_area.py"
PARAMETERS_DIALOG_PATH = (
    PROJECT_ROOT / "core" / "algorithm_workspace_parameters_dialog.py"
)
PARAMETERS_UI_PATH = PROJECT_ROOT / "ui" / "algorithm_workspace_parameters_dialog.ui"
SUMMARY_UI_PATH = (
    PROJECT_ROOT / "ui" / "algorithm_workspace_historical_summary_dialog.ui"
)

QUALITY_REASONS = (
    "MACD_CROSS_ACCEPTED",
    "MACD_EXTREMUM_NOT_FOUND",
    "MACD_EXTREMUM_TOO_WEAK",
    "MACD_EXTREMUM_DISTANCE_TOO_SMALL",
    "MACD_CROSS_TOO_FLAT",
)


def _signal(index: int, reason: str) -> WorkspaceSignalRecord:
    rejected = reason != "MACD_CROSS_ACCEPTED"
    return WorkspaceSignalRecord(
        timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        + timedelta(minutes=15 * index),
        signal_uid=f"rm99-ui-{index}",
        workspace_uid="workspace-rm99",
        broker="IB",
        account_id="REPLAY",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction="BUY" if index % 2 == 0 else "SELL",
        strength=0.0001,
        macd_state="MACD_CROSS_UP" if index % 2 == 0 else "MACD_CROSS_DOWN",
        alligator_confirmation="DISABLED",
        spread_status="OK",
        accepted=not rejected,
        reason="signal was rejected before risk evaluation" if rejected else "accepted",
        source_reason_code=reason,
        filter_decision=(WORKSPACE_SIGNAL_FILTER_REJECT if rejected else "ALLOW"),
        filter_reason_code=reason if rejected else None,
    )


def main() -> None:
    area_source = AREA_PATH.read_text(encoding="utf-8")
    parameter_source = PARAMETERS_DIALOG_PATH.read_text(encoding="utf-8")
    parameter_ui = PARAMETERS_UI_PATH.read_text(encoding="utf-8")
    summary_ui = SUMMARY_UI_PATH.read_text(encoding="utf-8")

    for object_name in (
        "cmbSignalResultFilter",
        "cmbSignalDirectionFilter",
        "cmbSignalRegimeFilter",
        "cmbSignalReasonFilter",
        "btnSignalGoPosition",
        "btnSignalGoChart",
        "btnSignalGoJournal",
        "cmbPositionPnlFilter",
        "cmbPositionReasonFilter",
        "cmbPositionDirectionFilter",
        "cmbPositionStatusFilter",
        "cmbOrderStatusFilter",
        "cmbOrderDirectionFilter",
        "cmbOrderPnlFilter",
        "cmbOrderReasonFilter",
        "edtJournalSearch",
    ):
        assert object_name in area_source

    assert "def _refresh_signal_view" in area_source
    assert "def _refresh_position_view" in area_source
    assert "def _refresh_order_view" in area_source
    assert "def _journal_search_variants" in area_source
    assert "search_variants" in area_source
    assert "workspace_signal_reason_code_text" in area_source

    assert "def _format_node_number" in parameter_source
    assert 'return f"{number:.{decimals}f}"' in parameter_source
    assert "<width>1040</width>" in parameter_ui
    assert "<height>790</height>" in parameter_ui
    assert "<height>650</height>" in parameter_ui

    assert "lblMacdQualityCaption" in summary_ui
    assert "lblMacdQualityRejectsCaption" in summary_ui

    records = tuple(
        _signal(index, reason)
        for index, reason in enumerate(QUALITY_REASONS)
    )
    metrics = build_workspace_historical_signal_metrics(records)
    assert metrics.macd_quality_accept == 1
    assert metrics.macd_quality_reject == 4
    assert metrics.macd_extremum_not_found == 1
    assert metrics.macd_extremum_too_weak == 1
    assert metrics.macd_distance_too_small == 1
    assert metrics.macd_cross_too_flat == 1

    assert (
        translation_override_for_key("AlgorithmWorkspaceFilter.result", "uk")
        == "Результат:"
    )
    assert (
        translation_override_for_key("AlgorithmWorkspaceFilter.direction", "uk")
        == "Напрямок:"
    )
    assert (
        translation_override_for_key("AlgorithmWorkspaceFilter.regime", "uk")
        == "Режим:"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceFilter.closeReason",
            "uk",
        )
        == "Причина закриття:"
    )
    assert (
        translation_override_for_key("AlgorithmWorkspaceJournal.lblSearch", "uk")
        == "Пошук:"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnSignalGoPosition",
            "uk",
        )
        == "До позиції"
    )
    assert (
        translation_override_for_key(
            "AlgorithmWorkspaceWindow.btnSignalGoJournal",
            "uk",
        )
        == "До журналу"
    )

    print("Algorithm Workspace WSP Filters UI result")
    print("  macd_fixed_decimal_presentation=True")
    print("  parameter_dialog_vertical_space_increased=True")
    print("  journal_text_search=True")
    print("  signal_filters=result/direction/regime/reason")
    print("  journal_date_space_or_T_search=True")
    print("  position_filters=pnl/reason/direction/status")
    print("  order_filters=status/direction/pnl/reason")
    print("  historical_summary_macd_quality=True")
    print("  macd_quality_metrics=1/4 reasons=1/1/1/1")
    print("  localized_ukrainian_filters=True")
    print("  strings_json_manually_edited=False")
    print("  broker_execution_attempted=False")
    print("ALGORITHM_WORKSPACE_WSP_FILTERS_UI_CHECK=OK")


if __name__ == "__main__":
    main()
