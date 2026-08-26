# -*- coding: utf-8 -*-
"""Перевірка локалізації Signal reason та diagnostic tooltip.

Тест фіксує українські MACD/Alligator тексти, causal режим/фазу ринку й
normalized Alligator diagnostics, не змінюючи технічні reason codes.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

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
    build_workspace_signal_presentation,
    workspace_signal_alligator_regime_text,
    workspace_signal_i18n_entries,
)


def _uk_tr(key: str, fallback: str) -> str:
    return translation_override_for_key(key, "uk") or fallback


def main() -> None:
    signal_time = datetime(2026, 8, 7, 6, 15, tzinfo=UTC)
    observation_time = datetime(2026, 8, 7, 4, 0, tzinfo=UTC)
    available_at = datetime(2026, 8, 7, 5, 0, tzinfo=UTC)
    record = WorkspaceSignalRecord(
        timestamp=signal_time,
        signal_uid="signal-1",
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
        reason=(
            "MACD_CLASSIC_CROSS; mode=LINEAR; "
            "profile_uid=macd-lge-classic; profile_revision=1; "
            "ALLIGATOR_HIGHER_1_BUY_REJECT: higher timeframe does not confirm"
        ),
        source_reason_code="MACD_CLASSIC_CROSS",
        source_profile_uid="macd-lge-classic",
        source_profile_revision=1,
        filter_decision=WORKSPACE_SIGNAL_FILTER_REJECT,
        filter_reason_code="ALLIGATOR_HIGHER_1_BUY_REJECT",
        filter_context=WorkspaceSignalFilterContext(
            mode="HIGHER_1",
            timeframe="H1",
            profile_uid="alligator-lge-classic",
            profile_revision=3,
            observation_timestamp=observation_time,
            available_at=available_at,
            regime="ALLIGATOR_REGIME_TREND_UP",
            regime_phase="ALLIGATOR_REGIME_PHASE_STARTING",
            normalized_slope=0.03125,
            normalized_opening=0.44,
        ),
    )
    presentation = build_workspace_signal_presentation(record, _uk_tr)
    assert (
        workspace_signal_alligator_regime_text(record, _uk_tr)
        == "Початок тренду вгору"
    )

    assert presentation.reason_text == (
        "Класичний перетин MACD. "
        "Alligator HIGHER_1 не підтверджує BUY."
    )
    assert "MACD Quality:" in presentation.tooltip_text
    assert "Рішення: REJECT" in presentation.tooltip_text
    assert "Профіль MACD:" not in presentation.tooltip_text
    assert "Діагностична причина:" not in presentation.tooltip_text
    assert (
        "Причина MACD: Класичний перетин MACD."
        in presentation.detail_text
    )
    assert (
        "Профіль MACD: macd-lge-classic (ревізія 1)"
        in presentation.detail_text
    )
    assert (
        "Причина Alligator: Alligator HIGHER_1 не підтверджує BUY."
        in presentation.detail_text
    )
    assert "Режим Alligator: HIGHER_1" in presentation.detail_text
    assert "Режим Alligator: Початок тренду вгору" in presentation.detail_text
    assert (
        "Нормалізований нахил Alligator: 0.031250"
        in presentation.detail_text
    )
    assert (
        "Нормалізоване розкриття Alligator: 0.440000"
        in presentation.detail_text
    )
    assert "Таймфрейм Alligator: H1" in presentation.detail_text
    assert (
        "Профіль Alligator: alligator-lge-classic (ревізія 3)"
        in presentation.detail_text
    )
    assert (
        f"Час спостереження: {observation_time.isoformat()}"
        in presentation.detail_text
    )
    assert (
        f"Доступно з: {available_at.isoformat()}"
        in presentation.detail_text
    )
    assert (
        "Технічні коди причини: MACD_CLASSIC_CROSS, "
        "ALLIGATOR_HIGHER_1_BUY_REJECT"
        in presentation.detail_text
    )
    assert "Діагностична причина:" in presentation.detail_text

    runtime_record = WorkspaceSignalRecord(
        timestamp=signal_time,
        signal_uid="signal-2",
        workspace_uid="workspace-1",
        broker="IB",
        account_id="DUM513747",
        symbol="EURUSD",
        timeframe="M15",
        source_mode="REPLAY",
        signal_type="MACD_CROSS",
        direction="SELL",
        strength=0.00011,
        macd_state="MACD_CROSS_DOWN",
        alligator_confirmation="DISABLED",
        spread_status="BLOCKED",
        accepted=False,
        reason="spread too wide",
        source_reason_code="MACD_CLASSIC_CROSS",
        source_profile_uid="macd-lge-classic",
        source_profile_revision=1,
    )
    runtime_presentation = build_workspace_signal_presentation(
        runtime_record,
        _uk_tr,
    )
    assert runtime_presentation.reason_text == "Спред завеликий."
    assert "Причина: Спред завеликий." in runtime_presentation.tooltip_text
    assert "Профіль MACD:" not in runtime_presentation.tooltip_text
    assert (
        "Профіль MACD: macd-lge-classic (ревізія 1)"
        in runtime_presentation.detail_text
    )
    assert "MACD_CLASSIC_CROSS" in runtime_presentation.detail_text

    i18n_entries = workspace_signal_i18n_entries()
    assert "AlgorithmWorkspaceSignalReason.macdClassicCross" in i18n_entries
    assert "AlgorithmWorkspaceSignalTooltip.availableAt" in i18n_entries
    assert "AlgorithmWorkspaceAlligatorRegime.flat" in i18n_entries
    assert "AlgorithmWorkspaceAlligatorRegime.trendUp" in i18n_entries
    assert "AlgorithmWorkspaceAlligatorRegime.trendDown" in i18n_entries
    assert "AlgorithmWorkspaceAlligatorRegime.trendUpStarting" in i18n_entries
    assert "AlgorithmWorkspaceAlligatorRegime.trendDownEnding" in i18n_entries
    assert (
        "AlgorithmWorkspaceSignalReason.alligatorSameBuyStartingReject"
        in i18n_entries
    )
    assert (
        "AlgorithmWorkspaceSignalReason.alligatorSameSellEndingReject"
        in i18n_entries
    )
    for key in (
        "AlgorithmWorkspaceSignalReason.macdDeferredRelease",
        "AlgorithmWorkspaceSignalReason.alligatorDeferredArmed",
        "AlgorithmWorkspaceSignalReason.alligatorDeferredRelease",
        "AlgorithmWorkspaceSignalReason.alligatorOpeningCollapseReject",
        "AlgorithmWorkspaceSignalReason.alligatorWeakOpeningReject",
        "AlgorithmWorkspaceSignalReason.alligatorVolatilitySpikeReject",
        "AlgorithmWorkspaceSignalReason.alligatorOverextendedReject",
    ):
        assert key in i18n_entries

    print("Algorithm Workspace signal localization result")
    print("  user_reason_localized=True")
    print("  macd_reason_localized=True")
    print("  alligator_reason_localized=True")
    print("  alligator_regime_localized=True")
    print("  alligator_regime_phase_localized=True")
    print("  alligator_phase_gate_reason_localized=True")
    print("  alligator_candidate_f_reason_localized=True")
    print("  alligator_regime_diagnostics_visible=True")
    print("  source_profile_uid_revision_visible=True")
    print("  filter_profile_uid_revision_visible=True")
    print("  observation_timestamp_visible=True")
    print("  available_at_visible=True")
    print("  technical_reason_codes_preserved=True")
    print("  diagnostic_reason_preserved=True")
    print("  runtime_reason_localized=True")
    print("  strings_json_manual_edit=False")
    print("ALGORITHM_WORKSPACE_SIGNAL_LOCALIZATION_CHECK=OK")


if __name__ == "__main__":
    main()
